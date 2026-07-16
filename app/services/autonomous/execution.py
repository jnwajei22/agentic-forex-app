from __future__ import annotations

import hashlib
import json
import logging
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.brokers.tradelocker.client import TradeLockerClient, TradeLockerError
from app.brokers.tradelocker.mapping import TradeLockerMappingError, map_configured_rows
from app.config.settings import settings
from app.models.autonomous import AutonomousOrderProposal, ExecutionMode
from app.services.providers.errors import ProviderError
from app.services.providers.finnhub import FinnhubClient
from app.services.providers.fred import FredClient
from app.services.tradelocker.account_status import AccountStatusUnavailable, TradeLockerAccountStatusService
from app.storage.brokers import BrokerConnection, BrokerRepository, BrokerStorageError
from app.storage.execution import ExecutionRepository, utcnow


logger = logging.getLogger(__name__)
ALLOWED_PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "USDCAD")


class AutonomousExecutionError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: str = "blocked", reasons: list[str] | None = None) -> None:
        super().__init__(message)
        self.code, self.status, self.reasons = code, status, reasons or [code]

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": "1.0", "status": self.status, "error": self.code, "message": str(self), "blocking_reasons": self.reasons}


@dataclass(frozen=True)
class VerifiedDemoContext:
    user_sub: str
    connection_id: str
    account_id: str
    acc_num: str
    account_name: str | None
    currency: str | None
    environment: str
    server: str
    base_url: str
    execution_mode: ExecutionMode
    risk: dict[str, Any]
    connection: BrokerConnection


@dataclass(frozen=True)
class InstrumentMetadata:
    instrument_id: str
    route_id: str
    contract_size: float
    pip_size: float
    lot_step: float
    min_lots: float
    max_lots: float | None
    quote_currency: str
    minimum_stop_distance: float
    commission_per_lot: float


def normalize_pair(pair: str) -> str:
    return pair.replace("/", "").replace("_", "").upper().strip()


def _normalized_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip("/"), "", ""))


def _find_value(value: Any, aliases: tuple[str, ...]) -> Any:
    targets = {alias.lower() for alias in aliases}
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in targets and item is not None:
                return item
        for item in value.values():
            found = _find_value(item, aliases)
            if found is not None:
                return found
    elif isinstance(value, list):
        for item in value:
            found = _find_value(item, aliases)
            if found is not None:
                return found
    return None


def _positive(value: Any, field: str) -> float:
    if isinstance(value, bool):
        raise AutonomousExecutionError("position_size_unverifiable", f"Broker {field} is unverifiable.", status="rejected")
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AutonomousExecutionError("position_size_unverifiable", f"Broker {field} is unverifiable.", status="rejected") from None
    if not math.isfinite(number) or number <= 0:
        raise AutonomousExecutionError("position_size_unverifiable", f"Broker {field} is unverifiable.", status="rejected")
    return number


def _nonnegative(value: Any, field: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise AutonomousExecutionError("broker_protection_unverifiable", f"Broker {field} is unverifiable.", status="rejected") from None
    if not math.isfinite(number) or number < 0:
        raise AutonomousExecutionError("broker_protection_unverifiable", f"Broker {field} is unverifiable.", status="rejected")
    return number


def parse_instrument_metadata(payload: dict[str, Any], pair: str) -> InstrumentMetadata:
    details, listing = payload.get("details", {}), payload.get("listing", {})
    combined = {"details": details, "listing": listing}
    routes = listing.get("routes", []) if isinstance(listing, dict) else []
    trade_route = next((r.get("id", r.get("routeId")) for r in routes if isinstance(r, dict) and str(r.get("type", "")).upper() == "TRADE"), None)
    route_id = trade_route or _find_value(details, ("tradeRouteId", "routeId"))
    instrument_id = payload.get("instrument_id")
    quote = _find_value(combined, ("quoteCurrency", "quotingCurrency", "currency")) or pair[3:]
    max_value = _find_value(combined, ("maxOrderQty", "maxQuantity", "maxLots"))
    return InstrumentMetadata(
        instrument_id=str(instrument_id) if instrument_id is not None else "",
        route_id=str(route_id) if route_id is not None else "",
        contract_size=_positive(_find_value(combined, ("contractSize", "lotSize", "unitsPerLot")), "contract size"),
        pip_size=_positive(_find_value(combined, ("pipSize", "pipValue", "priceIncrement")), "pip size"),
        lot_step=_positive(_find_value(combined, ("lotStep", "qtyStep", "quantityStep", "minOrderQtyIncrement")), "quantity increment"),
        min_lots=_positive(_find_value(combined, ("minOrderQty", "minQuantity", "minLots")), "minimum quantity"),
        max_lots=_positive(max_value, "maximum quantity") if max_value is not None else None,
        quote_currency=str(quote).upper(),
        minimum_stop_distance=_nonnegative(
            _find_value(combined, ("minStopLossDistance", "stopLossDistance", "stopsLevel")),
            "minimum stop distance",
        ),
        commission_per_lot=_nonnegative(
            _find_value(combined, ("commissionPerLot", "roundTurnCommission")) or 0,
            "commission",
        ),
    )


def calculate_broker_position_size(
    *, balance: float, available_funds: float, risk_percent: float,
    entry: float, stop_loss: float, metadata: InstrumentMetadata,
    quote_to_account_rate: float, spread: float = 0.0,
    commission_per_lot: float = 0.0,
) -> dict[str, float]:
    if balance <= 0 or available_funds <= 0:
        raise AutonomousExecutionError("insufficient_account_funds", "Account balance and available funds must be positive.", status="rejected")
    conversion = _positive(quote_to_account_rate, "currency conversion rate")
    price_risk = float(
        abs(Decimal(str(entry)) - Decimal(str(stop_loss)))
        + max(Decimal("0"), Decimal(str(spread)))
    )
    risk_per_lot = price_risk * metadata.contract_size * conversion + max(0.0, commission_per_lot)
    if risk_per_lot <= 0:
        raise AutonomousExecutionError("position_size_unverifiable", "The broker-specific position size could not be verified safely.", status="rejected")
    risk_budget = balance * risk_percent / 100.0
    raw_lots = risk_budget / risk_per_lot
    step = Decimal(str(metadata.lot_step))
    lots = float((Decimal(str(raw_lots)) / step).to_integral_value(rounding=ROUND_DOWN) * step)
    if lots < metadata.min_lots or (metadata.max_lots is not None and lots > metadata.max_lots):
        raise AutonomousExecutionError("position_size_unverifiable", "The calculated size violates broker quantity limits.", status="rejected")
    estimated = lots * risk_per_lot
    return {
        "lot_size": lots, "quantity": lots * metadata.contract_size,
        "estimated_risk": estimated, "risk_percent": estimated / balance * 100,
    }


class AutonomousDemoService:
    def __init__(
        self, *, broker_repository: BrokerRepository | None = None,
        execution_repository: ExecutionRepository | None = None,
        client_factory: Callable[..., TradeLockerClient] = TradeLockerClient,
        account_status_service: TradeLockerAccountStatusService | None = None,
        finnhub_factory: Callable[[], FinnhubClient] = FinnhubClient,
        fred_factory: Callable[[], FredClient] = FredClient,
    ) -> None:
        self.brokers = broker_repository or BrokerRepository()
        self.execution = execution_repository or ExecutionRepository()
        self.client_factory = client_factory
        self.account_status_service = account_status_service or TradeLockerAccountStatusService(repository=self.brokers, client_factory=client_factory)
        self.finnhub_factory, self.fred_factory = finnhub_factory, fred_factory

    async def context(self, user_sub: str, *, require_mode: bool = True) -> VerifiedDemoContext:
        try:
            connection = self.brokers.get_connection(user_sub)
        except BrokerStorageError:
            raise AutonomousExecutionError("broker_storage_error", "The stored TradeLocker connection is unavailable.") from None
        if not connection or not connection.account_id or not connection.account_number:
            raise AutonomousExecutionError("no_selected_account", "Select a TradeLocker account before demo execution.")
        risk = self.execution.get_or_create_settings(user_sub, connection.connection_id, connection.account_id, connection.account_number)
        mode = ExecutionMode(risk["execution_mode"])
        base_matches = _normalized_url(connection.base_url) == _normalized_url(settings.tradelocker_demo_base_url)
        if connection.environment != "demo" or not base_matches:
            raise AutonomousExecutionError("demo_environment_verification_failed", "Order execution is available only for a verified TradeLocker demo account.", reasons=["account_not_demo"])
        client = self._client(connection)
        try:
            discovered = await client.get_accounts()
        except TradeLockerError:
            raise AutonomousExecutionError("broker_unreachable", "TradeLocker account discovery is unavailable.") from None
        finally:
            await client.aclose()
        account = next((row for row in discovered.get("accounts", []) if isinstance(row, dict) and str(row.get("accountId")) == connection.account_id and str(row.get("accNum")) == connection.account_number), None) if isinstance(discovered, dict) else None
        if account is None:
            raise AutonomousExecutionError("demo_environment_verification_failed", "The selected demo account could not be verified during account discovery.")
        if require_mode and mode == ExecutionMode.READ_ONLY:
            raise AutonomousExecutionError("execution_mode_read_only", "The selected account is read-only.")
        return VerifiedDemoContext(
            user_sub, connection.connection_id, connection.account_id, connection.account_number,
            account.get("name"), account.get("currency"), connection.environment,
            connection.server, connection.base_url, mode, risk, connection,
        )

    def _client(self, connection: BrokerConnection) -> TradeLockerClient:
        return self.client_factory(base_url=connection.base_url, username=connection.username, password=connection.password, server=connection.server, account_id=connection.account_id, account_number=connection.account_number)

    async def status(self, user_sub: str) -> dict[str, Any]:
        reasons = []
        context = None
        try:
            context = await self.context(user_sub, require_mode=False)
            if context.execution_mode == ExecutionMode.READ_ONLY:
                reasons.append("execution_mode_read_only")
        except AutonomousExecutionError as exc:
            reasons.extend(exc.reasons)
        if settings.kill_switch_enabled:
            reasons.append("kill_switch_enabled")
        if not settings.finnhub_enabled or not settings.finnhub_api_key:
            reasons.append("provider_unavailable")
        return {
            "schema_version": "1.0", "status": "ready" if not reasons else "blocked",
            "account_environment": context.environment if context else None,
            "execution_mode": context.execution_mode.value if context else ExecutionMode.READ_ONLY.value,
            "kill_switch": settings.kill_switch_enabled, "strategy_enabled": True,
            "can_submit_demo_orders": not reasons, "blocking_reasons": list(dict.fromkeys(reasons)),
        }

    async def _provider_state(self) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
        providers: dict[str, Any] = {}
        blackouts: list[dict[str, Any]] = []
        context: dict[str, Any] = {"finnhub": {}, "fred": {}}
        finn = self.finnhub_factory()
        try:
            events = await finn.economic_calendar(date.today(), date.today(), 100)
            news = await finn.market_news("forex", 25)
            providers["finnhub"] = {"enabled": settings.finnhub_enabled, "required": True, "available": True, "stale": False}
            context["finnhub"] = {
                "economic_events": [
                    {"scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
                     "currency": event.currency, "country": event.country, "impact": event.impact}
                    for event in events
                ],
                "news_item_count": len(news),
                "latest_news_at": max((item.published_at for item in news), default=None).isoformat() if news else None,
                "related_symbols": sorted({symbol for item in news for symbol in item.related_symbols})[:50],
            }
            now = utcnow()
            for event in events:
                if event.scheduled_at and abs((event.scheduled_at - now).total_seconds()) <= settings.autonomous_news_blackout_minutes * 60:
                    blackouts.append({"scheduled_at": event.scheduled_at.isoformat(), "currency": event.currency, "impact": event.impact})
        except ProviderError:
            providers["finnhub"] = {"enabled": settings.finnhub_enabled, "required": True, "available": False, "stale": True}
        finally:
            await finn.aclose()
        fred = self.fred_factory()
        try:
            releases = await fred.release_dates(date.today(), date.today(), 25)
            providers["fred"] = {"enabled": settings.fred_enabled, "required": False, "available": True, "stale": False}
            context["fred"] = {
                "release_dates": [
                    {"release_id": item.release_id, "date": item.date.isoformat()}
                    for item in releases
                ]
            }
        except ProviderError:
            providers["fred"] = {"enabled": settings.fred_enabled, "required": False, "available": False, "stale": True}
        finally:
            await fred.aclose()
        return providers, blackouts, context

    async def snapshot(self, user_sub: str) -> dict[str, Any]:
        context = await self.context(user_sub)
        if settings.kill_switch_enabled:
            raise AutonomousExecutionError("kill_switch_enabled", "The kill switch blocks new snapshots.")
        try:
            account = await self.account_status_service.retrieve(user_sub)
        except (AccountStatusUnavailable, TradeLockerError, TradeLockerMappingError):
            raise AutonomousExecutionError("account_mapping_unavailable", "Normalized TradeLocker account state is unavailable.") from None
        account_json = account.model_dump(mode="json")
        if account.account.account_id != context.account_id or account.account.account_number != context.acc_num:
            raise AutonomousExecutionError("selected_account_context_mismatch", "The selected account changed during snapshot retrieval.")
        providers, blackouts, provider_context = await self._provider_state()
        client = self._client(context.connection)
        market: dict[str, Any] = {}
        try:
            config = await client.get_config()
            raw_positions, raw_orders = await client.get_open_positions(), await client.get_orders()
            positions = map_configured_rows(
                config_response=config, data_response=raw_positions,
                config_key="positionsConfig", data_key="positions",
            )
            orders = map_configured_rows(
                config_response=config, data_response=raw_orders,
                config_key="ordersConfig", data_key="orders",
            )
            for pair in context.risk["allowed_pairs"]:
                quote = await client.get_quote(pair)
                h1 = await client.get_candles(pair, "1h", 100)
                m15 = await client.get_candles(pair, "15m", 100)
                market[pair] = {"quote": quote, "candles_1h": [c.model_dump(mode="json") for c in h1.candles], "candles_15m": [c.model_dump(mode="json") for c in m15.candles], "complete": h1.complete and m15.complete}
        except (TradeLockerError, TradeLockerMappingError):
            raise AutonomousExecutionError("market_snapshot_unavailable", "A complete mapped TradeLocker snapshot is unavailable.") from None
        finally:
            await client.aclose()
        now, snapshot_id = utcnow(), f"snap_{uuid4().hex}"
        daily_pnl = account.today.net + account.open_net_pnl
        equity = account.projected_balance
        high_watermark = self.execution.observe_equity(
            user_sub, context.connection_id, context.account_id, context.acc_num, equity
        )
        risk_state = {
            "daily_realized_pnl": account.today.net, "open_pnl": account.open_net_pnl,
            "daily_loss_remaining": max(0.0, account.balance * context.risk["daily_loss_limit_percent"] / 100 + daily_pnl),
            "maximum_new_trade_risk": account.balance * context.risk["risk_per_trade_percent"] / 100,
            "current_drawdown_percent": max(0.0, (high_watermark - equity) / high_watermark * 100) if high_watermark > 0 else 100.0,
            "can_open_position": account.positions_count < context.risk["maximum_open_positions"] and account.pending_orders_count < context.risk["maximum_pending_orders"],
            "blocking_reasons": [],
        }
        result = {
            "schema_version": "1.0", "status": "ok", "snapshot_id": snapshot_id,
            "retrieved_at": now.isoformat(), "expires_at": (now + timedelta(seconds=settings.autonomous_snapshot_ttl_seconds)).isoformat(),
            "account": account_json, "positions": positions, "pending_orders": orders,
            "risk_state": risk_state, "strategy": {"name": context.risk["strategy_name"], "version": context.risk["strategy_version"]},
            "providers": providers, "news_blackouts": blackouts,
            "provider_context": provider_context,
            "market": {"pairs": market}, "execution_eligibility": not blackouts and providers["finnhub"]["available"] and risk_state["can_open_position"],
        }
        self.execution.insert_snapshot({
            "id": snapshot_id, "user_sub": user_sub, "connection_id": context.connection_id,
            "account_id": context.account_id, "acc_num": context.acc_num, "environment": context.environment,
            "strategy_name": context.risk["strategy_name"], "strategy_version": context.risk["strategy_version"],
            "normalized_snapshot_json": json.dumps(result, separators=(",", ":"), sort_keys=True),
            "retrieved_at": now.isoformat(), "expires_at": result["expires_at"], "created_at": now.isoformat(),
        })
        logger.info(
            "autonomous_demo snapshot_created user_id=%s connection_id=%s account_id=%s acc_num=%s environment=demo mode=%s snapshot_id=%s kill_switch=%s finnhub_available=%s fred_available=%s",
            user_sub, context.connection_id, context.account_id, context.acc_num,
            context.execution_mode.value, snapshot_id, settings.kill_switch_enabled,
            providers["finnhub"]["available"], providers["fred"]["available"],
        )
        return result

    @staticmethod
    def _quote(quote: Any) -> tuple[float, float]:
        bid = _find_value(quote, ("bid", "bidPrice", "bp", "b"))
        ask = _find_value(quote, ("ask", "askPrice", "ap", "a"))
        return _positive(bid, "bid quote"), _positive(ask, "ask quote")

    @classmethod
    def _conversion_rate(cls, from_currency: str, to_currency: str, market_pairs: dict[str, Any]) -> float:
        if from_currency == to_currency:
            return 1.0
        direct, inverse = f"{from_currency}{to_currency}", f"{to_currency}{from_currency}"
        if direct in market_pairs:
            bid, ask = cls._quote(market_pairs[direct]["quote"])
            return (bid + ask) / 2
        if inverse in market_pairs:
            bid, ask = cls._quote(market_pairs[inverse]["quote"])
            return 1 / ((bid + ask) / 2)
        raise AutonomousExecutionError("position_size_unverifiable", "A verified currency-conversion quote is unavailable.", status="rejected")

    @classmethod
    async def _fresh_conversion_rate(cls, client: TradeLockerClient, from_currency: str, to_currency: str) -> float:
        if from_currency == to_currency:
            return 1.0
        for symbol, inverse in ((f"{from_currency}{to_currency}", False), (f"{to_currency}{from_currency}", True)):
            try:
                bid, ask = cls._quote(await client.get_quote(symbol))
                midpoint = (bid + ask) / 2
                return 1 / midpoint if inverse else midpoint
            except TradeLockerError as exc:
                if exc.code != "symbol_not_found":
                    raise
        raise AutonomousExecutionError("position_size_unverifiable", "A fresh currency-conversion quote is unavailable.", status="rejected")

    async def review(self, user_sub: str, proposal: AutonomousOrderProposal) -> dict[str, Any]:
        context = await self.context(user_sub)
        if settings.kill_switch_enabled:
            raise AutonomousExecutionError("kill_switch_enabled", "The kill switch blocks new previews.")
        snapshot = self.execution.get_snapshot(proposal.snapshot_id)
        if not snapshot or snapshot["user_sub"] != user_sub:
            raise AutonomousExecutionError("snapshot_not_found", "The snapshot is unavailable.", status="rejected")
        if snapshot["account_id"] != context.account_id or snapshot["acc_num"] != context.acc_num or snapshot["environment"] != "demo":
            raise AutonomousExecutionError("snapshot_account_mismatch", "The snapshot does not belong to the selected demo account.", status="rejected")
        if datetime.fromisoformat(snapshot["expires_at"]) <= utcnow():
            raise AutonomousExecutionError("snapshot_expired", "The snapshot has expired.", status="rejected")
        pair = normalize_pair(proposal.pair)
        violations = []
        if pair not in context.risk["allowed_pairs"] or pair not in ALLOWED_PAIRS:
            violations.append("pair_not_allowed")
        if self.execution.has_active_preview(user_sub, context.account_id, context.acc_num, pair, utcnow().isoformat()):
            violations.append("duplicate_setup")
        risk_distance, reward_distance = abs(proposal.entry - proposal.stop_loss), abs(proposal.take_profit - proposal.entry)
        if (proposal.side == "long" and not (proposal.stop_loss < proposal.entry < proposal.take_profit)) or (proposal.side == "short" and not (proposal.take_profit < proposal.entry < proposal.stop_loss)):
            violations.append("invalid_protective_prices")
        rr = reward_distance / risk_distance if risk_distance else 0
        if rr < context.risk["minimum_reward_risk"]:
            violations.append("reward_risk_too_low")
        normalized = snapshot["normalized_snapshot"]
        if not normalized["providers"]["finnhub"]["available"] or normalized["providers"]["finnhub"]["stale"]:
            violations.append("provider_unavailable")
        if normalized["news_blackouts"]:
            violations.append("news_blackout")
        if not normalized["risk_state"]["can_open_position"]:
            violations.append("position_or_order_limit")
        market = normalized.get("market", {}).get("pairs", {}).get(pair, {})
        if not market.get("complete"):
            violations.append("market_data_incomplete")
        if violations:
            raise AutonomousExecutionError("risk_validation_failed", "The proposed order failed deterministic risk validation.", status="rejected", reasons=violations)
        client = self._client(context.connection)
        try:
            instrument_payload = await client.get_instrument_details(pair)
        except TradeLockerError:
            raise AutonomousExecutionError("position_size_unverifiable", "Broker instrument metadata is unavailable.", status="rejected") from None
        finally:
            await client.aclose()
        metadata = parse_instrument_metadata(instrument_payload, pair)
        if risk_distance < metadata.minimum_stop_distance:
            raise AutonomousExecutionError("broker_stop_distance_invalid", "The stop distance is below the broker minimum.", status="rejected")
        bid, ask = self._quote(market["quote"])
        spread = ask - bid
        if spread / metadata.pip_size > settings.autonomous_max_spread_pips:
            raise AutonomousExecutionError("spread_too_wide", "The snapshot spread exceeds the configured maximum.", status="rejected")
        account_currency = (context.currency or normalized["account"]["account"].get("currency") or "").upper()
        quote_to_account = self._conversion_rate(
            metadata.quote_currency, account_currency,
            normalized.get("market", {}).get("pairs", {}),
        )
        size = calculate_broker_position_size(
            balance=float(normalized["account"]["balance"]), available_funds=float(normalized["account"]["available_funds"]),
            risk_percent=float(context.risk["risk_per_trade_percent"]), entry=proposal.entry,
            stop_loss=proposal.stop_loss, metadata=metadata, quote_to_account_rate=quote_to_account,
            spread=spread,
            commission_per_lot=metadata.commission_per_lot,
        )
        preview_id, now = f"preview_{uuid4().hex}", utcnow()
        estimated_reward = size["lot_size"] * reward_distance * metadata.contract_size * quote_to_account
        record = {
            "id": preview_id, "snapshot_id": proposal.snapshot_id, "user_sub": user_sub,
            "connection_id": context.connection_id, "account_id": context.account_id, "acc_num": context.acc_num,
            "environment": "demo", "pair": pair, "instrument_id": metadata.instrument_id,
            "route_id": metadata.route_id, "side": proposal.side, "order_type": proposal.order_type,
            "entry": proposal.entry, "stop_loss": proposal.stop_loss, "take_profit": proposal.take_profit,
            "quantity": size["quantity"], "lot_size": size["lot_size"], "estimated_risk": size["estimated_risk"],
            "risk_percent": size["risk_percent"], "estimated_reward": estimated_reward, "reward_risk": rr,
            "broker_metadata_json": json.dumps(metadata.__dict__, separators=(",", ":"), sort_keys=True),
            "status": "approved", "violations_json": "[]",
            "expires_at": (now + timedelta(seconds=settings.autonomous_preview_ttl_seconds)).isoformat(), "created_at": now.isoformat(),
        }
        self.execution.insert_preview(record)
        logger.info(
            "autonomous_demo preview_validated user_id=%s connection_id=%s account_id=%s acc_num=%s environment=demo mode=%s snapshot_id=%s preview_id=%s instrument=%s side=%s quantity=%s estimated_risk=%.6f result=approved kill_switch=%s",
            user_sub, context.connection_id, context.account_id, context.acc_num,
            context.execution_mode.value, proposal.snapshot_id, preview_id, pair,
            proposal.side, size["lot_size"], size["estimated_risk"], settings.kill_switch_enabled,
        )
        return {"schema_version": "1.0", "status": "approved", "preview_id": preview_id, "snapshot_id": proposal.snapshot_id, "pair": pair, "side": proposal.side, "order_type": proposal.order_type, "entry": proposal.entry, "stop_loss": proposal.stop_loss, "take_profit": proposal.take_profit, **size, "estimated_reward": estimated_reward, "reward_risk": rr, "expires_at": record["expires_at"], "violations": []}

    async def submit(self, user_sub: str, preview_id: str, idempotency_key: str) -> dict[str, Any]:
        context = await self.context(user_sub)
        preview = self.execution.get_preview(preview_id)
        if not preview or preview["user_sub"] != user_sub:
            raise AutonomousExecutionError("preview_not_found", "The approved preview is unavailable.", status="rejected")
        if (preview["connection_id"], preview["account_id"], preview["acc_num"], preview["environment"]) != (context.connection_id, context.account_id, context.acc_num, "demo"):
            raise AutonomousExecutionError("preview_account_mismatch", "The preview does not match the currently selected demo account.", status="rejected")
        if preview["status"] != "approved" or datetime.fromisoformat(preview["expires_at"]) <= utcnow():
            raise AutonomousExecutionError("preview_expired_or_unapproved", "The preview is expired or not approved.", status="rejected")
        snapshot = self.execution.get_snapshot(preview["snapshot_id"])
        if not snapshot or datetime.fromisoformat(snapshot["expires_at"]) <= utcnow():
            raise AutonomousExecutionError("snapshot_expired", "The preview snapshot has expired.", status="rejected")
        fingerprint = hashlib.sha256(json.dumps({key: preview[key] for key in ("id", "account_id", "acc_num", "pair", "side", "order_type", "entry", "stop_loss", "take_profit", "lot_size")}, sort_keys=True).encode()).hexdigest()
        submission_id = f"submission_{uuid4().hex}"
        claimed, existing = self.execution.claim_submission(submission_id, preview_id, idempotency_key, fingerprint)
        key_hash = hashlib.sha256(idempotency_key.encode()).hexdigest()[:16]
        if not claimed:
            if existing.get("request_fingerprint") != fingerprint:
                raise AutonomousExecutionError("idempotency_conflict", "The idempotency key belongs to another request.", status="rejected")
            return self._submission_result(existing)
        logger.info(
            "autonomous_demo submission_started user_id=%s connection_id=%s account_id=%s acc_num=%s environment=demo mode=%s preview_id=%s idempotency_key_hash=%s instrument=%s side=%s quantity=%s kill_switch=%s",
            user_sub, context.connection_id, context.account_id, context.acc_num,
            context.execution_mode.value, preview_id, key_hash, preview["pair"],
            preview["side"], preview["lot_size"], settings.kill_switch_enabled,
        )
        # Forced fresh status and broker state are retrieved after the durable claim.
        dispatched = False
        try:
            account = await self.account_status_service.retrieve(user_sub)
            if settings.kill_switch_enabled:
                raise AutonomousExecutionError("kill_switch_enabled", "The kill switch blocks order submission.", status="rejected")
            providers, blackouts, _ = await self._provider_state()
            if not providers["finnhub"]["available"] or providers["finnhub"]["stale"] or blackouts:
                raise AutonomousExecutionError("news_validation_unavailable", "Required news-blackout validation failed closed.", status="rejected")
            if account.positions_count >= context.risk["maximum_open_positions"] or account.pending_orders_count >= context.risk["maximum_pending_orders"]:
                raise AutonomousExecutionError("position_or_order_limit", "The account position or pending-order limit was reached.", status="rejected")
            total_loss = account.today.net + account.open_net_pnl
            if account.balance <= 0 or total_loss <= -(account.balance * context.risk["daily_loss_limit_percent"] / 100):
                raise AutonomousExecutionError("daily_loss_limit", "The account daily loss limit was reached.", status="rejected")
            high_watermark = self.execution.observe_equity(
                user_sub, context.connection_id, context.account_id, context.acc_num,
                account.projected_balance,
            )
            drawdown = max(0.0, (high_watermark - account.projected_balance) / high_watermark * 100) if high_watermark > 0 else 100.0
            if drawdown >= context.risk["drawdown_cutoff_percent"]:
                raise AutonomousExecutionError("drawdown_cutoff", "The account drawdown cutoff was reached.", status="rejected")
            client = self._client(context.connection)
            try:
                quote = await client.get_quote(preview["pair"])
                bid, ask = self._quote(quote)
                current = ask if preview["side"] == "long" else bid
                metadata = InstrumentMetadata(**preview["broker_metadata"])
                if (ask - bid) / metadata.pip_size > settings.autonomous_max_spread_pips:
                    raise AutonomousExecutionError("spread_too_wide", "The current spread exceeds the configured maximum.", status="rejected")
                account_currency = (context.currency or account.account.currency or "").upper()
                conversion = await self._fresh_conversion_rate(client, metadata.quote_currency, account_currency)
                current_risk_per_lot = ((abs(preview["entry"] - preview["stop_loss"]) + (ask - bid)) * metadata.contract_size * conversion + metadata.commission_per_lot)
                if current_risk_per_lot * preview["lot_size"] > account.balance * context.risk["risk_per_trade_percent"] / 100:
                    raise AutonomousExecutionError("risk_limit_changed", "Fresh market state would exceed the account risk limit.", status="rejected")
                if abs(current - preview["entry"]) / preview["entry"] * 100 > settings.autonomous_price_tolerance_percent:
                    raise AutonomousExecutionError("price_moved", "The current price moved beyond the configured tolerance.", status="rejected")
                config = await client.get_config()
                before_positions, before_orders = await client.get_open_positions(), await client.get_orders()
                mapped_positions = map_configured_rows(config_response=config, data_response=before_positions, config_key="positionsConfig", data_key="positions")
                mapped_orders = map_configured_rows(config_response=config, data_response=before_orders, config_key="ordersConfig", data_key="orders")
                if any(str(_find_value(row, ("tradableInstrumentId", "instrumentId"))) == preview["instrument_id"] for row in mapped_positions + mapped_orders):
                    raise AutonomousExecutionError("equivalent_order_exists", "An equivalent position or order already exists.", status="rejected")
                if settings.kill_switch_enabled:
                    raise AutonomousExecutionError("kill_switch_enabled", "The kill switch blocks order submission.", status="rejected")
                order_payload = {
                    "qty": preview["lot_size"], "routeId": preview["route_id"],
                    "side": "buy" if preview["side"] == "long" else "sell",
                    "validity": "IOC" if preview["order_type"] == "market" else "GTC",
                    "type": preview["order_type"], "tradableInstrumentId": preview["instrument_id"],
                    "price": 0 if preview["order_type"] == "market" else preview["entry"],
                    "stopLoss": preview["stop_loss"], "stopLossType": "absolute",
                    "takeProfit": preview["take_profit"], "takeProfitType": "absolute",
                    "strategyId": f"afd-{preview_id[-20:]}",
                }
                response = await client.place_order(order_payload)
                dispatched = True
                after_orders = await client.get_orders()
                history = await client.get_orders_history()
                after_positions = await client.get_open_positions()
                reconciliation = self._reconcile(config, after_orders, history, after_positions, preview, response)
            finally:
                await client.aclose()
            broker_order_id = str(_find_value(response, ("orderId", "id")) or reconciliation.get("broker_order_id") or "") or None
            state = "verified" if reconciliation["verified"] else "unknown"
            self.execution.update_submission(
                submission_id, submission_state=state, broker_order_id=broker_order_id,
                broker_position_id=reconciliation.get("broker_position_id"),
                broker_response_sanitized_json={"order_id": broker_order_id, "accepted": True},
                reconciliation_json=reconciliation, submitted_at=utcnow().isoformat(),
                verified_at=utcnow().isoformat() if reconciliation["verified"] else None,
            )
            self.execution.mark_preview_submitted(preview_id)
            result = self.execution.get_submission(preview_id=preview_id) or {}
            self._record_run(context, preview, state, broker_order_id, self._submission_result(result))
            logger.info(
                "autonomous_demo submission_completed user_id=%s connection_id=%s account_id=%s acc_num=%s preview_id=%s idempotency_key_hash=%s broker_order_id=%s broker_position_id=%s reconciliation_verified=%s result=%s",
                user_sub, context.connection_id, context.account_id, context.acc_num,
                preview_id, key_hash, broker_order_id, reconciliation.get("broker_position_id"),
                reconciliation["verified"], state,
            )
            return self._submission_result(result)
        except AutonomousExecutionError as exc:
            self.execution.update_submission(submission_id, submission_state="rejected", reconciliation_json=exc.as_dict())
            logger.warning(
                "autonomous_demo submission_blocked user_id=%s connection_id=%s account_id=%s acc_num=%s preview_id=%s idempotency_key_hash=%s failure_category=%s kill_switch=%s",
                user_sub, context.connection_id, context.account_id, context.acc_num,
                preview_id, key_hash, exc.code, settings.kill_switch_enabled,
            )
            raise
        except (AccountStatusUnavailable, TradeLockerError, TradeLockerMappingError) as exc:
            # A timeout/request failure after dispatch is deliberately unknown and never retried blindly.
            operation = getattr(exc, "operation", "mapping")
            code = getattr(exc, "code", "mapping_unavailable")
            state = "unknown" if dispatched or (operation == "place_order" and code in {"timeout", "request_failed"}) else "rejected"
            self.execution.update_submission(submission_id, submission_state=state, reconciliation_json={"error": code, "manual_review_required": state == "unknown"})
            logger.warning(
                "autonomous_demo submission_failed user_id=%s connection_id=%s account_id=%s acc_num=%s preview_id=%s idempotency_key_hash=%s failure_category=%s result=%s",
                user_sub, context.connection_id, context.account_id, context.acc_num,
                preview_id, key_hash, code, state,
            )
            if state == "unknown":
                return {"schema_version": "1.0", "status": "unknown", "error": "broker_result_unverified", "message": "TradeLocker accepted or may have accepted the order, but the resulting broker state could not be verified.", "manual_review_required": True}
            raise AutonomousExecutionError("broker_rejected", "TradeLocker rejected the demo order.", status="rejected") from None

    @staticmethod
    def _reconcile(config: Any, orders: Any, history: Any, positions: Any, preview: dict[str, Any], response: Any) -> dict[str, Any]:
        mapped_orders: list[dict[str, Any]] = []
        mapped_history: list[dict[str, Any]] = []
        mapped_positions: list[dict[str, Any]] = []
        try:
            if isinstance(config, dict) and isinstance(orders, dict):
                mapped_orders = map_configured_rows(config_response=config, data_response=orders, config_key="ordersConfig", data_key="orders")
            if isinstance(config, dict) and isinstance(history, dict):
                mapped_history = map_configured_rows(config_response=config, data_response=history, config_key="ordersHistoryConfig", data_key="ordersHistory")
            if isinstance(config, dict) and isinstance(positions, dict):
                mapped_positions = map_configured_rows(config_response=config, data_response=positions, config_key="positionsConfig", data_key="positions")
        except TradeLockerMappingError:
            return {"verified": False, "order_found": False, "position_found": False, "mapping_verified": False}
        order_id = _find_value(response, ("orderId", "id"))
        candidates = mapped_orders + mapped_history
        order = next((row for row in candidates if order_id is not None and str(_find_value(row, ("orderId", "id"))) == str(order_id)), None)
        if order is None:
            order = next((row for row in candidates if str(_find_value(row, ("tradableInstrumentId", "instrumentId"))) == preview["instrument_id"]), None)
        position_id = _find_value(order, ("positionId",)) if order else None
        position = next((row for row in mapped_positions if position_id is not None and str(_find_value(row, ("positionId", "id"))) == str(position_id)), None)
        quantity = _find_value(order or position, ("qty", "quantity"))
        side = str(_find_value(order or position, ("side",)) or "").lower()
        stop = _find_value(order or position, ("stopLoss",))
        target = _find_value(order or position, ("takeProfit",))
        expected_side = "buy" if preview["side"] == "long" else "sell"
        checks = {
            "quantity_matches": quantity is not None and math.isclose(float(quantity), preview["lot_size"], rel_tol=1e-6),
            "side_matches": side == expected_side,
            "stop_loss_matches": stop is not None and math.isclose(float(stop), preview["stop_loss"], rel_tol=1e-6),
            "take_profit_matches": target is not None and math.isclose(float(target), preview["take_profit"], rel_tol=1e-6),
        }
        return {"verified": bool(order) and all(checks.values()), "mapping_verified": True, "order_found": bool(order), "position_found": bool(position), "broker_order_id": str(order_id) if order_id is not None else None, "broker_position_id": str(position_id) if position_id is not None else None, **checks}

    @staticmethod
    def _submission_result(record: dict[str, Any]) -> dict[str, Any]:
        state = record.get("submission_state", "unknown")
        return {"schema_version": "1.0", "status": "submitted" if state == "verified" else state, "broker_order_id": record.get("broker_order_id"), "broker_position_id": record.get("broker_position_id"), "reconciliation": record.get("reconciliation", {}), "manual_review_required": state == "unknown"}

    def _record_run(self, context: VerifiedDemoContext, preview: dict[str, Any], state: str, broker_order_id: str | None, result: dict[str, Any]) -> str:
        now, run_id = utcnow(), f"run_{uuid4().hex}"
        self.execution.insert_run({"id": run_id, "user_sub": context.user_sub, "connection_id": context.connection_id, "account_id": context.account_id, "acc_num": context.acc_num, "snapshot_id": preview["snapshot_id"], "preview_id": preview["id"], "strategy_name": context.risk["strategy_name"], "strategy_version": context.risk["strategy_version"], "decision": "submit", "selected_pair": preview["pair"], "selected_side": preview["side"], "result_status": state, "broker_order_id": broker_order_id, "result_json": result, "started_at": now.isoformat(), "completed_at": now.isoformat(), "created_at": now.isoformat()})
        return run_id

    async def record_no_trade(self, user_sub: str, snapshot_id: str, reason_codes: list[str], pairs: list[str]) -> dict[str, Any]:
        context = await self.context(user_sub, require_mode=False)
        snapshot = self.execution.get_snapshot(snapshot_id)
        if not snapshot or snapshot["user_sub"] != user_sub or snapshot["account_id"] != context.account_id:
            raise AutonomousExecutionError("snapshot_not_found", "The snapshot is unavailable.", status="rejected")
        if datetime.fromisoformat(snapshot["expires_at"]) <= utcnow():
            raise AutonomousExecutionError("snapshot_expired", "The snapshot has expired.", status="rejected")
        normalized_pairs = [normalize_pair(pair) for pair in pairs]
        if any(pair not in ALLOWED_PAIRS for pair in normalized_pairs):
            raise AutonomousExecutionError("pair_not_allowed", "A no-trade pair is outside the allowed watchlist.", status="rejected")
        now, run_id = utcnow(), f"run_{uuid4().hex}"
        self.execution.insert_run({"id": run_id, "user_sub": user_sub, "connection_id": context.connection_id, "account_id": context.account_id, "acc_num": context.acc_num, "snapshot_id": snapshot_id, "preview_id": None, "strategy_name": context.risk["strategy_name"], "strategy_version": context.risk["strategy_version"], "decision": "no_trade", "selected_pair": None, "selected_side": None, "no_trade_reason_codes_json": reason_codes, "result_status": "no_trade", "result_json": {"pairs_evaluated": normalized_pairs}, "started_at": now.isoformat(), "completed_at": now.isoformat(), "created_at": now.isoformat()})
        return {"schema_version": "1.0", "status": "no_trade", "run_id": run_id, "reason_codes": reason_codes, "pairs_evaluated": normalized_pairs}

    def run_result(self, user_sub: str, run_id: str | None = None) -> dict[str, Any]:
        record = self.execution.get_run(user_sub, run_id)
        if not record:
            raise AutonomousExecutionError("run_not_found", "No autonomous run result was found.", status="not_found")
        return {"schema_version": "1.0", "status": record["result_status"], "run_id": record["id"], "preview_id": record.get("preview_id"), "broker_order_id": record.get("broker_order_id"), "decision": record["decision"], "result": record["result"]}
