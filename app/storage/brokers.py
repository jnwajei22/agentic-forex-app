import base64
import hashlib
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

from app.config.settings import settings


class BrokerStorageError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrokerConnection:
    connection_id: str
    base_url: str
    username: str
    password: str = field(repr=False)
    server: str
    account_id: str | None
    account_number: str | None
    environment: str


def infer_tradelocker_environment(base_url: str) -> str:
    lowered = base_url.lower()
    if "live.tradelocker" in lowered:
        return "live"
    if "demo.tradelocker" in lowered:
        return "demo"
    configured = settings.tradelocker_environment.lower()
    return configured if configured in {"demo", "live"} else "demo"


class BrokerRepository:
    def __init__(self, db_path: str | Path | None = None, secret: str | None = None) -> None:
        self.db_path = Path(db_path or settings.sqlite_path)
        self.secret = secret if secret is not None else settings.broker_secret_key
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    auth0_sub TEXT NOT NULL UNIQUE,
                    email TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS broker_connections (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL UNIQUE,
                    provider TEXT NOT NULL CHECK(provider = 'tradelocker'),
                    base_url TEXT NOT NULL,
                    username TEXT NOT NULL,
                    password_encrypted BLOB NOT NULL,
                    server TEXT NOT NULL,
                    account_id TEXT,
                    account_number TEXT,
                    environment TEXT NOT NULL DEFAULT 'demo' CHECK(environment IN ('demo', 'live')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
                );
                """
            )
            columns = {
                row["name"] for row in connection.execute("PRAGMA table_info(broker_connections)")
            }
            if "environment" not in columns:
                connection.execute(
                    "ALTER TABLE broker_connections ADD COLUMN environment TEXT NOT NULL DEFAULT 'demo'"
                )
                connection.execute(
                    """UPDATE broker_connections SET environment = 'live'
                       WHERE lower(base_url) LIKE '%live.tradelocker%'"""
                )

    def _fernet(self) -> Fernet:
        if not self.secret:
            raise BrokerStorageError("BROKER_SECRET_KEY is not configured.")
        key = base64.urlsafe_b64encode(hashlib.sha256(self.secret.encode()).digest())
        return Fernet(key)

    def ensure_user(self, auth0_sub: str, email: str | None = None) -> int:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO users(auth0_sub, email, created_at, updated_at)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(auth0_sub) DO UPDATE SET
                     email = COALESCE(excluded.email, users.email), updated_at = excluded.updated_at""",
                (auth0_sub, email, now, now),
            )
            row = connection.execute(
                "SELECT id FROM users WHERE auth0_sub = ?", (auth0_sub,)
            ).fetchone()
            return int(row["id"])

    def save_connection(
        self,
        auth0_sub: str,
        *,
        base_url: str,
        username: str,
        password: str,
        server: str,
        environment: str | None = None,
        email: str | None = None,
    ) -> None:
        user_id = self.ensure_user(auth0_sub, email)
        resolved_environment = (environment or infer_tradelocker_environment(base_url)).lower()
        if resolved_environment not in {"demo", "live"}:
            raise BrokerStorageError("TradeLocker environment must be 'demo' or 'live'.")
        encrypted = self._fernet().encrypt(password.encode())
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO broker_connections(
                       user_id, provider, base_url, username, password_encrypted, server,
                       environment, created_at, updated_at
                   ) VALUES (?, 'tradelocker', ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id) DO UPDATE SET
                       base_url = excluded.base_url, username = excluded.username,
                       password_encrypted = excluded.password_encrypted,
                       server = excluded.server, environment = excluded.environment,
                       account_id = NULL, account_number = NULL,
                       updated_at = excluded.updated_at""",
                (
                    user_id, base_url.rstrip("/"), username, encrypted, server,
                    resolved_environment, now, now,
                ),
            )

    def get_connection(self, auth0_sub: str) -> BrokerConnection | None:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT b.id, b.base_url, b.username, b.password_encrypted, b.server,
                          b.account_id, b.account_number, b.environment
                   FROM broker_connections b JOIN users u ON u.id = b.user_id
                   WHERE u.auth0_sub = ? AND b.provider = 'tradelocker'""",
                (auth0_sub,),
            ).fetchone()
        if row is None:
            return None
        try:
            password = self._fernet().decrypt(row["password_encrypted"]).decode()
        except InvalidToken as exc:
            raise BrokerStorageError("Stored broker credentials cannot be decrypted.") from None
        return BrokerConnection(
            connection_id=str(row["id"]), base_url=row["base_url"],
            username=row["username"], password=password,
            server=row["server"], account_id=row["account_id"],
            account_number=row["account_number"], environment=row["environment"],
        )

    def select_account(self, auth0_sub: str, account_id: str, account_number: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE broker_connections SET account_id = ?, account_number = ?, updated_at = ?
                   WHERE user_id = (SELECT id FROM users WHERE auth0_sub = ?)""",
                (account_id, account_number, now, auth0_sub),
            )
            return cursor.rowcount == 1

    def delete_connection(self, auth0_sub: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """DELETE FROM broker_connections
                   WHERE user_id = (SELECT id FROM users WHERE auth0_sub = ?)""",
                (auth0_sub,),
            )
            return cursor.rowcount == 1

    def status(self, auth0_sub: str) -> dict:
        with self._connect() as connection:
            row = connection.execute(
                """SELECT b.username, b.server, b.account_id, b.account_number, b.environment
                   FROM broker_connections b JOIN users u ON u.id = b.user_id
                   WHERE u.auth0_sub = ? AND b.provider = 'tradelocker'""",
                (auth0_sub,),
            ).fetchone()
        if row is None:
            return {"status": "not_connected", "connected": False, "selected_account": None}
        selected = bool(row["account_id"] and row["account_number"])
        return {
            "status": "ready" if selected else "connected_no_account",
            "connected": True,
            "selected_account": ({
                "server": row["server"],
                "environment": row["environment"],
                "account_id": row["account_id"],
                "account_number": row["account_number"],
            } if selected else None),
        }
