from __future__ import annotations

from dataclasses import dataclass, field

from app.storage.brokers import BrokerRepository, BrokerStorageError


class AccountResolutionError(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class BrokerAccountContext:
    auth0_user_id: str
    connection_id: str
    connection_ref: str
    account_record_id: str
    account_alias: str
    account_id: str
    account_number: str
    account_name: str | None
    currency: str | None
    environment: str
    server: str
    active: bool
    base_url: str = field(repr=False)
    username: str = field(repr=False)
    password: str = field(repr=False)

    def safe_identity(self) -> dict:
        return {
            "account_alias": self.account_alias,
            "account_id": self.account_record_id,
            "connection_id": self.connection_ref,
            "name": self.account_name,
            "currency": self.currency,
            "environment": self.environment,
            "active": self.active,
        }


class BrokerAccountResolver:
    def __init__(self, repository: BrokerRepository | None = None) -> None:
        self.repository = repository or BrokerRepository()

    def resolve(
        self,
        auth0_user_id: str,
        *,
        account_alias: str | None = None,
        profile: str | None = None,
        require_available: bool = True,
    ) -> BrokerAccountContext:
        if account_alias and profile:
            raise AccountResolutionError("invalid_account_selector", "Choose an account alias or profile, not both.")
        try:
            row = self.repository.get_account_record(auth0_user_id, alias=account_alias, profile=profile)
        except BrokerStorageError as exc:
            raise AccountResolutionError("broker_storage_error", "Stored broker account data is unavailable.") from exc
        if row is None:
            code = "account_alias_not_found" if account_alias else "profile_not_found" if profile else "default_account_required"
            raise AccountResolutionError(code, "No owned TradeLocker account matches that selector.")
        if row["connection_status"] != "active" or not row["locally_enabled"]:
            raise AccountResolutionError("account_disabled", "The selected TradeLocker account is disabled.")
        if require_available and (not row["available"] or not row["broker_active"]):
            raise AccountResolutionError("account_unavailable", "The selected TradeLocker account is unavailable.")
        try:
            password = self.repository._fernet().decrypt(row["password_encrypted"]).decode()
        except Exception as exc:
            raise AccountResolutionError("broker_storage_error", "Stored broker credentials cannot be decrypted.") from exc
        return BrokerAccountContext(
            auth0_user_id=auth0_user_id,
            connection_id=str(row["connection_id"]),
            connection_ref=row["connection_ref"],
            account_record_id=row["public_id"],
            account_alias=row["account_alias"],
            account_id=row["broker_account_id"],
            account_number=row["acc_num"],
            account_name=row["account_name"],
            currency=row["currency"],
            environment=row["environment"],
            server=row["server"],
            active=bool(row["broker_active"]),
            base_url=row["base_url"], username=row["username"], password=password,
        )
