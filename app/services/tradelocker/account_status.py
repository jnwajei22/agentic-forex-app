from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from math import isfinite
from time import perf_counter
from typing import Any, Callable

from app.brokers.tradelocker.client import TradeLockerClient, TradeLockerError
from app.brokers.tradelocker.mapping import (
    TradeLockerMappingError,
    configured_field_count,
    map_configured_array,
    positional_value_count,
)
from app.models.tradelocker import (
    TradeLockerAccountIdentity,
    TradeLockerAccountStatus,
    TradeLockerMarginStatus,
    TradeLockerTodayStatus,
)
from app.services.tradelocker.config_cache import (
    TradeLockerConfigCache,
    TradeLockerConfigCacheKey,
    tradelocker_config_cache,
)
from app.storage.brokers import BrokerConnection, BrokerRepository, BrokerStorageError


logger = logging.getLogger(__name__)


class AccountStatusUnavailable(RuntimeError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SelectedTradeLockerContext:
    auth0_user_id: str
    connection_id: str
    account_id: str
    account_number: str
    account_name: str | None
    currency: str | None
    environment: str
    server: str
    active: bool

    @property
    def cache_key(self) -> TradeLockerConfigCacheKey:
        return TradeLockerConfigCacheKey(
            self.auth0_user_id, self.environment, self.server,
            self.account_id, self.account_number,
        )


def _number(values: dict[str, Any], name: str) -> float:
    value = values.get(name)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TradeLockerMappingError(f"Unsupported numeric value for {name}.")
    converted = float(value)
    if not isfinite(converted):
        raise TradeLockerMappingError(f"Unsupported numeric value for {name}.")
    return converted


def _integer(values: dict[str, Any], name: str) -> int:
    value = _number(values, name)
    if not value.is_integer():
        raise TradeLockerMappingError(f"Unsupported integer value for {name}.")
    return int(value)


def _active(account: dict[str, Any]) -> bool:
    status = account.get("status")
    if status is None:
        return True
    return str(status).lower() not in {"inactive", "disabled", "closed", "blocked"}


class TradeLockerAccountStatusService:
    def __init__(
        self,
        *,
        repository: BrokerRepository | None = None,
        cache: TradeLockerConfigCache = tradelocker_config_cache,
        client_factory: Callable[..., TradeLockerClient] = TradeLockerClient,
    ) -> None:
        self.repository = repository or BrokerRepository()
        self.cache = cache
        self.client_factory = client_factory

    async def retrieve(self, auth0_user_id: str) -> TradeLockerAccountStatus:
        started = perf_counter()
        context: SelectedTradeLockerContext | None = None
        mapping_success = False
        config_from_cache = False
        config_fields: int | None = None
        state_values: int | None = None
        refresh_occurred = False
        client: TradeLockerClient | None = None
        try:
            connection = self._connection(auth0_user_id)
            client = self.client_factory(
                base_url=connection.base_url,
                username=connection.username,
                password=connection.password,
                server=connection.server,
                account_id=connection.account_id,
                account_number=connection.account_number,
            )
            try:
                accounts = await client.get_accounts()
                selected = self._selected_account(connection, accounts)
                context = SelectedTradeLockerContext(
                    auth0_user_id=auth0_user_id,
                    connection_id=connection.connection_id,
                    account_id=connection.account_id or "",
                    account_number=connection.account_number or "",
                    account_name=self._optional_text(selected.get("name")),
                    currency=self._optional_text(selected.get("currency")),
                    environment=connection.environment,
                    server=connection.server,
                    active=_active(selected),
                )
                config = self.cache.get(context.cache_key)
                config_from_cache = config is not None
                if config is None:
                    config = await self._fetch_config(client, context)
                    self.cache.put(context.cache_key, config)
                state = await self._fetch_state(client, context)
                config_fields = configured_field_count(config, "accountDetailsConfig")
                state_values = positional_value_count(state, "accountDetailsData")
                try:
                    values = map_configured_array(
                        config_response=config, data_response=state,
                        config_key="accountDetailsConfig", data_key="accountDetailsData",
                    )
                except TradeLockerMappingError as exc:
                    if not exc.mismatch:
                        raise
                    config = await self._fetch_config(client, context)
                    self.cache.put(context.cache_key, config)
                    config_from_cache = False
                    config_fields = configured_field_count(config, "accountDetailsConfig")
                    values = map_configured_array(
                        config_response=config, data_response=state,
                        config_key="accountDetailsConfig", data_key="accountDetailsData",
                    )
                result = self._normalize(context, values)
                mapping_success = True
                return result
            finally:
                await client.aclose()
        except BrokerStorageError as exc:
            raise AccountStatusUnavailable(
                "broker_storage_error", "The stored TradeLocker connection is unavailable."
            ) from exc
        except TradeLockerMappingError as exc:
            raise AccountStatusUnavailable(
                "account_field_mapping_unavailable",
                "TradeLocker account values were received, but their field mapping could not be verified.",
            ) from exc
        except TradeLockerError:
            raise
        finally:
            refresh_occurred = bool(getattr(client, "token_refresh_count", 0))
            logger.info(
                "TradeLocker account_status user_id=%s connection_id=%s account_id=%s "
                "acc_num=%s environment=%s config_cache_hit=%s config_fields=%s "
                "state_values=%s mapping_success=%s latency_ms=%.2f token_refresh=%s",
                auth0_user_id,
                context.connection_id if context else None,
                context.account_id if context else None,
                context.account_number if context else None,
                context.environment if context else None,
                config_from_cache, config_fields, state_values, mapping_success,
                (perf_counter() - started) * 1000, refresh_occurred,
            )

    def _connection(self, auth0_user_id: str) -> BrokerConnection:
        connection = self.repository.get_connection(auth0_user_id)
        if connection is None:
            raise AccountStatusUnavailable(
                "setup_required", "TradeLocker setup is required for the current user."
            )
        if not connection.account_id or not connection.account_number:
            raise AccountStatusUnavailable(
                "selected_account_required", "Select a TradeLocker account before requesting status."
            )
        return connection

    @staticmethod
    def _selected_account(connection: BrokerConnection, payload: Any) -> dict[str, Any]:
        accounts = payload.get("accounts") if isinstance(payload, dict) else None
        if not isinstance(accounts, list):
            raise AccountStatusUnavailable(
                "account_discovery_unavailable", "The selected TradeLocker account could not be verified."
            )
        for account in accounts:
            if (
                isinstance(account, dict)
                and str(account.get("accountId")) == connection.account_id
                and str(account.get("accNum")) == connection.account_number
            ):
                return account
        raise AccountStatusUnavailable(
            "selected_account_unavailable", "The selected TradeLocker account could not be verified."
        )

    @staticmethod
    def _assert_context(client: TradeLockerClient, context: SelectedTradeLockerContext) -> None:
        if str(client.account_id) != context.account_id or str(client.account_number) != context.account_number:
            raise AccountStatusUnavailable(
                "selected_account_context_mismatch", "The selected TradeLocker account context is inconsistent."
            )

    async def _fetch_config(
        self, client: TradeLockerClient, context: SelectedTradeLockerContext
    ) -> dict[str, Any]:
        self._assert_context(client, context)
        payload = await client.get_config()
        if not isinstance(payload, dict):
            raise TradeLockerMappingError("Malformed TradeLocker config payload.")
        if configured_field_count(payload, "accountDetailsConfig") is None:
            raise TradeLockerMappingError("Missing TradeLocker account details configuration.")
        return payload

    async def _fetch_state(
        self, client: TradeLockerClient, context: SelectedTradeLockerContext
    ) -> dict[str, Any]:
        self._assert_context(client, context)
        payload = await client.get_account_state_payload()
        if not isinstance(payload, dict):
            raise TradeLockerMappingError("Malformed TradeLocker account state payload.")
        return payload

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _normalize(
        context: SelectedTradeLockerContext, values: dict[str, Any]
    ) -> TradeLockerAccountStatus:
        return TradeLockerAccountStatus(
            retrieved_at=datetime.now(timezone.utc),
            account=TradeLockerAccountIdentity(
                account_id=context.account_id, account_number=context.account_number,
                name=context.account_name, currency=context.currency,
                environment=context.environment, active=context.active,
            ),
            balance=_number(values, "balance"),
            projected_balance=_number(values, "projectedBalance"),
            available_funds=_number(values, "availableFunds"),
            blocked_balance=_number(values, "blockedBalance"),
            cash_balance=_number(values, "cashBalance"),
            withdrawal_available=_number(values, "withdrawalAvailable"),
            open_gross_pnl=_number(values, "openGrossPnL"),
            open_net_pnl=_number(values, "openNetPnL"),
            positions_count=_integer(values, "positionsCount"),
            pending_orders_count=_integer(values, "ordersCount"),
            today=TradeLockerTodayStatus(
                gross=_number(values, "todayGross"), net=_number(values, "todayNet"),
                fees=_number(values, "todayFees"), volume=_number(values, "todayVolume"),
                trades_count=_integer(values, "todayTradesCount"),
            ),
            margin=TradeLockerMarginStatus(
                initial_requirement=_number(values, "initialMarginReq"),
                maintenance_requirement=_number(values, "maintMarginReq"),
                warning_level=_number(values, "marginWarningLevel"),
                stop_out_level=_number(values, "stopOutLevel"),
                warning_requirement=_number(values, "warningMarginReq"),
                margin_before_warning=_number(values, "marginBeforeWarning"),
            ),
        )
