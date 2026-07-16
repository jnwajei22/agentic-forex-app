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
        connection.execute("PRAGMA foreign_keys = ON")
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
                CREATE TABLE IF NOT EXISTS oauth_refresh_tokens (
                    token_hash TEXT PRIMARY KEY,
                    family_id TEXT NOT NULL,
                    parent_token_hash TEXT,
                    replaced_by_token_hash TEXT,
                    user_sub TEXT NOT NULL,
                    client_id TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    resource TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    rotated_at TEXT,
                    revoked_at TEXT,
                    reuse_detected_at TEXT,
                    FOREIGN KEY(parent_token_hash) REFERENCES oauth_refresh_tokens(token_hash),
                    FOREIGN KEY(replaced_by_token_hash) REFERENCES oauth_refresh_tokens(token_hash)
                );
                CREATE INDEX IF NOT EXISTS idx_oauth_refresh_family
                    ON oauth_refresh_tokens(family_id);
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
        if transaction.user_sub == user_sub:
            return transaction
        with self._connect() as connection:
            connection.execute(
                """UPDATE oauth_transactions SET user_sub = ?, status = 'AUTH0_COMPLETE'
                   WHERE reference_hash = ? AND user_sub IS NULL""",
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
            connection.execute("BEGIN IMMEDIATE")
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
            now = _now()
            connection.execute(
                "UPDATE oauth_authorization_codes SET used_at = ? WHERE code_hash = ? AND used_at IS NULL",
                (_iso(now), _hash(code)),
            )
            return self._issue_token_pair(
                connection, user_sub=row["user_sub"], client_id=client_id,
                scope=row["scope"], resource=resource, now=now,
            )

    def _issue_token_pair(
        self, connection: sqlite3.Connection, *, user_sub: str, client_id: str,
        scope: str, resource: str, now: datetime, family_id: str | None = None,
        parent_token_hash: str | None = None,
    ) -> dict:
        access_token = secrets.token_urlsafe(40)
        refresh_token = secrets.token_urlsafe(48)
        access_expires = now + timedelta(seconds=settings.oauth_access_token_ttl_seconds)
        refresh_expires = now + timedelta(seconds=settings.oauth_refresh_token_ttl_seconds)
        refresh_hash = _hash(refresh_token)
        connection.execute(
            """INSERT INTO oauth_access_tokens(
                token_hash, user_sub, client_id, scope, created_at, expires_at, resource
            ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (_hash(access_token), user_sub, client_id, scope, _iso(now),
             _iso(access_expires), resource),
        )
        connection.execute(
            """INSERT INTO oauth_refresh_tokens(
                token_hash, family_id, parent_token_hash, user_sub, client_id,
                scope, resource, issued_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (refresh_hash, family_id or secrets.token_urlsafe(24), parent_token_hash,
             user_sub, client_id, scope, resource, _iso(now), _iso(refresh_expires)),
        )
        return {
            "access_token": access_token, "token_type": "Bearer",
            "expires_in": settings.oauth_access_token_ttl_seconds,
            "refresh_token": refresh_token, "scope": scope,
        }

    def exchange_refresh_token(
        self, *, refresh_token: str, client_id: str, resource: str,
        scope: str | None = None,
    ) -> dict | None:
        token_hash = _hash(refresh_token)
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM oauth_refresh_tokens WHERE token_hash = ?", (token_hash,)
            ).fetchone()
            if row is None:
                return None
            # Client/resource mismatches fail without revoking a legitimate family.
            if row["client_id"] != client_id or row["resource"] != resource:
                return None
            if row["rotated_at"] or row["replaced_by_token_hash"]:
                connection.execute(
                    """UPDATE oauth_refresh_tokens SET
                         revoked_at=COALESCE(revoked_at, ?),
                         reuse_detected_at=CASE WHEN token_hash=? THEN ? ELSE reuse_detected_at END
                       WHERE family_id=?""",
                    (_iso(now), token_hash, _iso(now), row["family_id"]),
                )
                return None
            if row["revoked_at"] or datetime.fromisoformat(row["expires_at"]) <= now:
                return None
            original_scopes = set(row["scope"].split())
            requested_scopes = set(scope.split()) if scope is not None else original_scopes
            if not requested_scopes or not requested_scopes <= original_scopes:
                return None
            granted_scope = " ".join(
                item for item in row["scope"].split() if item in requested_scopes
            )
            result = self._issue_token_pair(
                connection, user_sub=row["user_sub"], client_id=client_id,
                scope=granted_scope, resource=resource, now=now,
                family_id=row["family_id"], parent_token_hash=token_hash,
            )
            replacement_hash = _hash(result["refresh_token"])
            cursor = connection.execute(
                """UPDATE oauth_refresh_tokens
                   SET rotated_at=?, replaced_by_token_hash=?
                   WHERE token_hash=? AND rotated_at IS NULL AND revoked_at IS NULL""",
                (_iso(now), replacement_hash, token_hash),
            )
            if cursor.rowcount != 1:
                raise OAuthStorageError("Refresh-token rotation could not be completed safely.")
            return result

    def revoke_refresh_token(self, refresh_token: str) -> bool:
        with self._connect() as connection:
            cursor = connection.execute(
                """UPDATE oauth_refresh_tokens SET revoked_at=COALESCE(revoked_at, ?)
                   WHERE token_hash=?""", (_iso(_now()), _hash(refresh_token)),
            )
            return cursor.rowcount == 1

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
