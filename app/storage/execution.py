from __future__ import annotations

import json
import math
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config.settings import settings
from app.models.autonomous import ExecutionMode


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class ExecutionRepository:
    """Durable, account-scoped autonomous-demo state."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or settings.sqlite_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS execution_settings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_sub TEXT NOT NULL, connection_id TEXT NOT NULL,
                    account_id TEXT NOT NULL, acc_num TEXT NOT NULL,
                    execution_mode TEXT NOT NULL DEFAULT 'read_only'
                      CHECK(execution_mode IN ('read_only','demo_manual','demo_autonomous')),
                    strategy_name TEXT NOT NULL DEFAULT 'ai_competition_v1',
                    strategy_version TEXT NOT NULL DEFAULT '1.0',
                    risk_per_trade_percent REAL NOT NULL DEFAULT 1.0,
                    daily_loss_limit_percent REAL NOT NULL DEFAULT 3.0,
                    drawdown_cutoff_percent REAL NOT NULL DEFAULT 10.0,
                    maximum_open_positions INTEGER NOT NULL DEFAULT 1,
                    maximum_pending_orders INTEGER NOT NULL DEFAULT 1,
                    minimum_reward_risk REAL NOT NULL DEFAULT 1.5,
                    equity_high_watermark REAL,
                    allowed_pairs_json TEXT NOT NULL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(user_sub, connection_id, account_id, acc_num)
                );
                CREATE TABLE IF NOT EXISTS autonomous_snapshots (
                    id TEXT PRIMARY KEY, user_sub TEXT NOT NULL, connection_id TEXT NOT NULL,
                    account_id TEXT NOT NULL, acc_num TEXT NOT NULL, environment TEXT NOT NULL,
                    strategy_name TEXT NOT NULL, strategy_version TEXT NOT NULL,
                    normalized_snapshot_json TEXT NOT NULL,
                    retrieved_at TEXT NOT NULL, expires_at TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS autonomous_order_previews (
                    id TEXT PRIMARY KEY, snapshot_id TEXT NOT NULL, user_sub TEXT NOT NULL,
                    connection_id TEXT NOT NULL, account_id TEXT NOT NULL, acc_num TEXT NOT NULL,
                    environment TEXT NOT NULL, pair TEXT NOT NULL, instrument_id TEXT NOT NULL,
                    route_id TEXT NOT NULL, side TEXT NOT NULL, order_type TEXT NOT NULL,
                    entry REAL NOT NULL, stop_loss REAL NOT NULL, take_profit REAL NOT NULL,
                    quantity REAL NOT NULL, lot_size REAL NOT NULL, estimated_risk REAL NOT NULL,
                    risk_percent REAL NOT NULL, estimated_reward REAL NOT NULL, reward_risk REAL NOT NULL,
                    broker_metadata_json TEXT NOT NULL, status TEXT NOT NULL,
                    violations_json TEXT NOT NULL, expires_at TEXT NOT NULL,
                    submitted_at TEXT, created_at TEXT NOT NULL,
                    FOREIGN KEY(snapshot_id) REFERENCES autonomous_snapshots(id)
                );
                CREATE TABLE IF NOT EXISTS autonomous_runs (
                    id TEXT PRIMARY KEY, user_sub TEXT NOT NULL, connection_id TEXT NOT NULL,
                    account_id TEXT NOT NULL, acc_num TEXT NOT NULL, snapshot_id TEXT,
                    preview_id TEXT, strategy_name TEXT NOT NULL, strategy_version TEXT NOT NULL,
                    decision TEXT NOT NULL, selected_pair TEXT, selected_side TEXT,
                    no_trade_reason_codes_json TEXT NOT NULL DEFAULT '[]',
                    rejection_reason_codes_json TEXT NOT NULL DEFAULT '[]',
                    result_status TEXT NOT NULL, broker_order_id TEXT,
                    result_json TEXT NOT NULL, started_at TEXT NOT NULL,
                    completed_at TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_submissions (
                    id TEXT PRIMARY KEY, preview_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL UNIQUE, request_fingerprint TEXT NOT NULL,
                    submission_state TEXT NOT NULL, broker_order_id TEXT UNIQUE,
                    broker_position_id TEXT, broker_response_sanitized_json TEXT NOT NULL DEFAULT '{}',
                    reconciliation_json TEXT NOT NULL DEFAULT '{}', submitted_at TEXT,
                    verified_at TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    FOREIGN KEY(preview_id) REFERENCES autonomous_order_previews(id)
                );
                """
            )
            columns = {row["name"] for row in db.execute("PRAGMA table_info(execution_settings)")}
            if "equity_high_watermark" not in columns:
                db.execute("ALTER TABLE execution_settings ADD COLUMN equity_high_watermark REAL")

    def get_or_create_settings(self, user_sub: str, connection_id: str, account_id: str, acc_num: str) -> dict[str, Any]:
        now = utcnow().isoformat()
        pairs = json.dumps(["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD"])
        with self._connect() as db:
            db.execute(
                """INSERT OR IGNORE INTO execution_settings(
                    user_sub, connection_id, account_id, acc_num, allowed_pairs_json, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (user_sub, connection_id, account_id, acc_num, pairs, now, now),
            )
            row = db.execute(
                """SELECT * FROM execution_settings WHERE user_sub=? AND connection_id=?
                   AND account_id=? AND acc_num=?""", (user_sub, connection_id, account_id, acc_num)
            ).fetchone()
        return self._decode(row)

    def set_mode(self, user_sub: str, connection_id: str, account_id: str, acc_num: str, mode: ExecutionMode) -> dict[str, Any]:
        self.get_or_create_settings(user_sub, connection_id, account_id, acc_num)
        with self._connect() as db:
            db.execute(
                """UPDATE execution_settings SET execution_mode=?, updated_at=? WHERE user_sub=?
                   AND connection_id=? AND account_id=? AND acc_num=?""",
                (mode.value, utcnow().isoformat(), user_sub, connection_id, account_id, acc_num),
            )
        return self.get_or_create_settings(user_sub, connection_id, account_id, acc_num)

    def observe_equity(self, user_sub: str, connection_id: str, account_id: str, acc_num: str, equity: float) -> float:
        if not math.isfinite(equity) or equity < 0:
            raise ValueError("equity must be a non-negative finite number")
        with self._connect() as db:
            db.execute(
                """UPDATE execution_settings SET equity_high_watermark = CASE
                     WHEN equity_high_watermark IS NULL OR equity_high_watermark < ? THEN ?
                     ELSE equity_high_watermark END, updated_at=?
                   WHERE user_sub=? AND connection_id=? AND account_id=? AND acc_num=?""",
                (equity, equity, utcnow().isoformat(), user_sub, connection_id, account_id, acc_num),
            )
            row = db.execute(
                """SELECT equity_high_watermark FROM execution_settings WHERE user_sub=?
                   AND connection_id=? AND account_id=? AND acc_num=?""",
                (user_sub, connection_id, account_id, acc_num),
            ).fetchone()
        return float(row["equity_high_watermark"])

    @staticmethod
    def _decode(row: sqlite3.Row | None) -> dict[str, Any]:
        if row is None:
            raise KeyError("record not found")
        result = dict(row)
        for key in ("allowed_pairs_json", "normalized_snapshot_json", "violations_json", "broker_metadata_json", "result_json", "reconciliation_json", "broker_response_sanitized_json", "no_trade_reason_codes_json", "rejection_reason_codes_json"):
            if key in result:
                result[key.removesuffix("_json")] = json.loads(result.pop(key))
        return result

    def insert_snapshot(self, record: dict[str, Any]) -> None:
        with self._connect() as db:
            db.execute(
                """INSERT INTO autonomous_snapshots VALUES
                   (:id,:user_sub,:connection_id,:account_id,:acc_num,:environment,
                    :strategy_name,:strategy_version,:normalized_snapshot_json,
                    :retrieved_at,:expires_at,:created_at)""", record,
            )

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM autonomous_snapshots WHERE id=?", (snapshot_id,)).fetchone()
        return self._decode(row) if row else None

    def insert_preview(self, record: dict[str, Any]) -> None:
        columns = ",".join(record)
        values = ",".join(f":{key}" for key in record)
        with self._connect() as db:
            db.execute(f"INSERT INTO autonomous_order_previews({columns}) VALUES ({values})", record)

    def get_preview(self, preview_id: str) -> dict[str, Any] | None:
        with self._connect() as db:
            row = db.execute("SELECT * FROM autonomous_order_previews WHERE id=?", (preview_id,)).fetchone()
        return self._decode(row) if row else None

    def has_active_preview(self, user_sub: str, account_id: str, acc_num: str, pair: str, now: str) -> bool:
        with self._connect() as db:
            row = db.execute(
                """SELECT 1 FROM autonomous_order_previews WHERE user_sub=? AND account_id=?
                   AND acc_num=? AND pair=? AND status='approved' AND expires_at>? LIMIT 1""",
                (user_sub, account_id, acc_num, pair, now),
            ).fetchone()
        return row is not None

    def claim_submission(self, submission_id: str, preview_id: str, idempotency_key: str, fingerprint: str) -> tuple[bool, dict[str, Any]]:
        now = utcnow().isoformat()
        try:
            with self._connect() as db:
                db.execute("BEGIN IMMEDIATE")
                db.execute(
                    """INSERT INTO broker_submissions(id,preview_id,idempotency_key,request_fingerprint,
                       submission_state,created_at,updated_at) VALUES (?,?,?,?, 'claimed',?,?)""",
                    (submission_id, preview_id, idempotency_key, fingerprint, now, now),
                )
            return True, self.get_submission(preview_id=preview_id) or {}
        except sqlite3.IntegrityError:
            existing = self.get_submission(preview_id=preview_id) or self.get_submission(idempotency_key=idempotency_key)
            return False, existing or {}

    def get_submission(self, *, preview_id: str | None = None, idempotency_key: str | None = None) -> dict[str, Any] | None:
        key, value = ("preview_id", preview_id) if preview_id is not None else ("idempotency_key", idempotency_key)
        with self._connect() as db:
            row = db.execute(f"SELECT * FROM broker_submissions WHERE {key}=?", (value,)).fetchone()
        return self._decode(row) if row else None

    def update_submission(self, submission_id: str, **updates: Any) -> None:
        updates["updated_at"] = utcnow().isoformat()
        encoded = {key: json.dumps(value, separators=(",", ":"), sort_keys=True) if key.endswith("_json") else value for key, value in updates.items()}
        assignments = ",".join(f"{key}=:{key}" for key in encoded)
        with self._connect() as db:
            db.execute(f"UPDATE broker_submissions SET {assignments} WHERE id=:id", {**encoded, "id": submission_id})

    def mark_preview_submitted(self, preview_id: str) -> None:
        with self._connect() as db:
            db.execute("UPDATE autonomous_order_previews SET status='submitted',submitted_at=? WHERE id=?", (utcnow().isoformat(), preview_id))

    def insert_run(self, record: dict[str, Any]) -> None:
        encoded = {key: json.dumps(value, separators=(",", ":"), sort_keys=True) if key.endswith("_json") else value for key, value in record.items()}
        columns = ",".join(encoded)
        values = ",".join(f":{key}" for key in encoded)
        with self._connect() as db:
            db.execute(f"INSERT INTO autonomous_runs({columns}) VALUES ({values})", encoded)

    def get_run(self, user_sub: str, run_id: str | None = None) -> dict[str, Any] | None:
        with self._connect() as db:
            if run_id:
                row = db.execute("SELECT * FROM autonomous_runs WHERE id=? AND user_sub=?", (run_id, user_sub)).fetchone()
            else:
                row = db.execute("SELECT * FROM autonomous_runs WHERE user_sub=? ORDER BY created_at DESC LIMIT 1", (user_sub,)).fetchone()
        return self._decode(row) if row else None
