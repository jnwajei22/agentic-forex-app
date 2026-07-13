import base64
import hashlib
import hmac
import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.config.settings import settings


class OAuthStorageError(RuntimeError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.isoformat()


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


@dataclass(frozen=True)
class PendingAuthorization:
    reference_hash: str
    client_id: str
    redirect_uri: str
    state: str
    scope: str
    code_challenge: str
    code_challenge_method: str
    nonce: str | None
    user_sub: str | None
    csrf_token: str
    expires_at: str
    status: str
    resource: str


class OAuthRepository:
    def __init__(self, db_path: str | Path | None = None, secret: str | None = None) -> None:
        self.db_path = Path(db_path or settings.sqlite_path)
        self.secret = secret or settings.oauth_transaction_secret or settings.broker_secret_key
        if not self.secret:
            raise OAuthStorageError("OAUTH_TRANSACTION_SECRET or BROKER_SECRET_KEY is required.")
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS oauth_transactions (
                    reference_hash TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    oauth_state TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    code_challenge_method TEXT NOT NULL,
                    nonce TEXT,
                    user_sub TEXT,
                    csrf_token TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    completed_at TEXT
                );
                CREATE TABLE IF NOT EXISTS oauth_authorization_codes (
                    code_hash TEXT PRIMARY KEY,
                    transaction_hash TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    redirect_uri TEXT NOT NULL,
                    user_sub TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    code_challenge TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    used_at TEXT,
                    FOREIGN KEY(transaction_hash) REFERENCES oauth_transactions(reference_hash)
                );
                CREATE TABLE IF NOT EXISTS oauth_access_tokens (
                    token_hash TEXT PRIMARY KEY,
                    user_sub TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS oauth_onboarding_assertion_nonces (
                    nonce_hash TEXT PRIMARY KEY,
                    expires_at TEXT NOT NULL
                );
                """
            )
            for table in ("oauth_transactions", "oauth_authorization_codes", "oauth_access_tokens"):
                columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
                if "resource" not in columns:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN resource TEXT")

    def _signed_reference(self) -> str:
        opaque = secrets.token_urlsafe(32)
        signature = hmac.new(self.secret.encode(), opaque.encode(), hashlib.sha256).hexdigest()
        return f"{opaque}.{signature}"

    def _valid_reference(self, reference: str) -> bool:
        opaque, separator, supplied = reference.partition(".")
        expected = hmac.new(self.secret.encode(), opaque.encode(), hashlib.sha256).hexdigest()
        return bool(separator and opaque and hmac.compare_digest(supplied, expected))

    def create_transaction(self, *, client_id: str, redirect_uri: str, state: str,
                           scope: str, code_challenge: str, code_challenge_method: str,
                           resource: str, nonce: str | None = None) -> str:
        reference = self._signed_reference()
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO oauth_transactions(
                    reference_hash, client_id, redirect_uri, oauth_state, scope,
                    code_challenge, code_challenge_method, nonce, csrf_token, status,
                    created_at, expires_at, resource
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'AUTH0_REQUIRED', ?, ?, ?)""",
                (_hash(reference), client_id, redirect_uri, state, scope, code_challenge,
                 code_challenge_method, nonce, secrets.token_urlsafe(24), _iso(now),
                 _iso(now + timedelta(minutes=10)), resource),
            )
        return reference

    def get_transaction(self, reference: str) -> PendingAuthorization | None:
        if not self._valid_reference(reference):
            return None
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_transactions WHERE reference_hash = ?",
                (_hash(reference),),
            ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= _now():
            return None
        return PendingAuthorization(
            reference_hash=row["reference_hash"], client_id=row["client_id"],
            redirect_uri=row["redirect_uri"], state=row["oauth_state"], scope=row["scope"],
            code_challenge=row["code_challenge"], code_challenge_method=row["code_challenge_method"],
            nonce=row["nonce"], user_sub=row["user_sub"], csrf_token=row["csrf_token"],
            expires_at=row["expires_at"],
            status=row["status"],
            resource=row["resource"],
        )

    def bind_user(self, reference: str, user_sub: str) -> PendingAuthorization | None:
        transaction = self.get_transaction(reference)
        if transaction is None or (transaction.user_sub and transaction.user_sub != user_sub):
            return None
        with self._connect() as connection:
            connection.execute(
                "UPDATE oauth_transactions SET user_sub = ?, status = 'AUTH0_COMPLETE' WHERE reference_hash = ?",
                (user_sub, transaction.reference_hash),
            )
        return self.get_transaction(reference)

    def issue_code(self, reference: str, user_sub: str) -> tuple[str, PendingAuthorization] | None:
        transaction = self.get_transaction(reference)
        if transaction is None or transaction.user_sub != user_sub or transaction.status == "CHATGPT_OAUTH_COMPLETE":
            return None
        code = secrets.token_urlsafe(32)
        now = _now()
        with self._connect() as connection:
            connection.execute(
                """INSERT INTO oauth_authorization_codes(
                    code_hash, transaction_hash, client_id, redirect_uri, user_sub,
                    scope, code_challenge, expires_at
                    , resource
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (_hash(code), transaction.reference_hash, transaction.client_id,
                 transaction.redirect_uri, user_sub, transaction.scope,
                 transaction.code_challenge, _iso(now + timedelta(minutes=5)), transaction.resource),
            )
            connection.execute(
                "UPDATE oauth_transactions SET status = 'CHATGPT_OAUTH_COMPLETE', completed_at = ? WHERE reference_hash = ?",
                (_iso(now), transaction.reference_hash),
            )
        return code, transaction

    def exchange_code(self, *, code: str, client_id: str, redirect_uri: str,
                      code_verifier: str, resource: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_authorization_codes WHERE code_hash = ?",
                (_hash(code),),
            ).fetchone()
            if row is None or row["used_at"] or datetime.fromisoformat(row["expires_at"]) <= _now():
                return None
            if (row["client_id"] != client_id or row["redirect_uri"] != redirect_uri
                    or row["resource"] != resource):
                return None
            challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode()).digest()).decode().rstrip("=")
            if not hmac.compare_digest(challenge, row["code_challenge"]):
                return None
            access_token = secrets.token_urlsafe(40)
            now = _now()
            expires = now + timedelta(hours=1)
            connection.execute(
                "UPDATE oauth_authorization_codes SET used_at = ? WHERE code_hash = ?",
                (_iso(now), _hash(code)),
            )
            connection.execute(
                "INSERT INTO oauth_access_tokens(token_hash, user_sub, client_id, scope, created_at, expires_at, resource) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (_hash(access_token), row["user_sub"], client_id, row["scope"], _iso(now), _iso(expires), resource),
            )
        return {"access_token": access_token, "token_type": "Bearer", "expires_in": 3600, "scope": row["scope"]}

    def access_token_claims(self, token: str) -> dict | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM oauth_access_tokens WHERE token_hash = ?", (_hash(token),)
            ).fetchone()
        if row is None or datetime.fromisoformat(row["expires_at"]) <= _now():
            return None
        return {"sub": row["user_sub"], "scope": row["scope"], "client_id": row["client_id"],
                "aud": row["resource"], "resource": row["resource"]}

    def consume_onboarding_assertion_nonce(self, nonce: str, expires_at: datetime) -> bool:
        now = _now()
        try:
            with self._connect() as connection:
                connection.execute(
                    "DELETE FROM oauth_onboarding_assertion_nonces WHERE expires_at <= ?",
                    (_iso(now),),
                )
                connection.execute(
                    "INSERT INTO oauth_onboarding_assertion_nonces(nonce_hash, expires_at) VALUES (?, ?)",
                    (_hash(nonce), _iso(expires_at)),
                )
            return True
        except sqlite3.IntegrityError:
            return False
