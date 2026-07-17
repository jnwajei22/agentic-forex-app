from concurrent.futures import ThreadPoolExecutor

import pytest

from app.config.settings import settings
from app.models.autonomous import ExecutionMode
from app.services.autonomous.execution import (
    AutonomousDemoService,
    AutonomousExecutionError,
    InstrumentMetadata,
    calculate_broker_position_size,
    normalize_pair,
    parse_instrument_metadata,
)
from app.storage.execution import ExecutionRepository
from app.storage.brokers import BrokerRepository


def metadata(**overrides):
    values = {
        "instrument_id": "101", "route_id": "trade-route", "contract_size": 100_000,
        "pip_size": 0.0001, "lot_step": 0.01, "min_lots": 0.01,
        "max_lots": 100.0, "quote_currency": "USD", "minimum_stop_distance": 0.0001,
        "commission_per_lot": 0.0,
        "leverage": 100.0,
    }
    values.update(overrides)
    return InstrumentMetadata(**values)


@pytest.mark.parametrize("raw", ["EUR/USD", "EURUSD", "eurusd", "eur_usd"])
def test_pair_normalization(raw):
    assert normalize_pair(raw) == "EURUSD"


def test_usd_quoted_position_sizing_uses_contract_and_increment():
    result = calculate_broker_position_size(
        balance=10_000, available_funds=10_000, risk_percent=1,
        entry=1.1000, stop_loss=1.0990, metadata=metadata(), quote_to_account_rate=1,
    )
    assert result["lot_size"] == pytest.approx(1.0)
    assert result["quantity"] == pytest.approx(100_000)
    assert result["estimated_risk"] == pytest.approx(100)
    assert result["estimated_margin"] == pytest.approx(1100)


def test_sizing_rejects_unverifiable_or_insufficient_margin():
    with pytest.raises(AutonomousExecutionError,match="leverage"):
        calculate_broker_position_size(balance=10_000,available_funds=10_000,risk_percent=.25,
            entry=1.1,stop_loss=1.099,metadata=metadata(leverage=None),quote_to_account_rate=1)
    with pytest.raises(AutonomousExecutionError) as error:
        calculate_broker_position_size(balance=10_000,available_funds=10,risk_percent=.25,
            entry=1.1,stop_loss=1.099,metadata=metadata(),quote_to_account_rate=1)
    assert error.value.code=="insufficient_margin"


def test_usd_base_position_sizing_converts_quote_currency():
    result = calculate_broker_position_size(
        balance=10_000, available_funds=10_000, risk_percent=1,
        entry=1.25, stop_loss=1.249, metadata=metadata(quote_currency="CAD"),
        quote_to_account_rate=0.8,
    )
    assert result["lot_size"] == pytest.approx(1.25)
    assert result["estimated_risk"] == pytest.approx(100)


def test_position_sizing_rounds_down_and_never_up():
    result = calculate_broker_position_size(
        balance=1_000, available_funds=1_000, risk_percent=1,
        entry=1.1, stop_loss=1.0987, metadata=metadata(lot_step=0.01),
        quote_to_account_rate=1,
    )
    assert result["lot_size"] == 0.07
    assert result["estimated_risk"] <= 10


@pytest.mark.parametrize("balance,funds", [(0, 1000), (1000, 0), (-1, 1000)])
def test_position_sizing_rejects_nonpositive_funds(balance, funds):
    with pytest.raises(AutonomousExecutionError) as error:
        calculate_broker_position_size(
            balance=balance, available_funds=funds, risk_percent=1,
            entry=1.1, stop_loss=1.099, metadata=metadata(), quote_to_account_rate=1,
        )
    assert error.value.code == "insufficient_account_funds"


def test_position_sizing_fails_closed_without_conversion():
    with pytest.raises(AutonomousExecutionError) as error:
        calculate_broker_position_size(
            balance=1000, available_funds=1000, risk_percent=1,
            entry=1.1, stop_loss=1.099, metadata=metadata(), quote_to_account_rate=0,
        )
    assert error.value.code == "position_size_unverifiable"


def test_instrument_metadata_requires_verified_broker_values():
    payload = {
        "instrument_id": 42,
        "listing": {"routes": [{"type": "TRADE", "id": "r1"}]},
        "details": {"d": {"contractSize": 100000, "pipSize": 0.0001,
                           "lotStep": 0.01, "minOrderQty": 0.01,
                           "maxOrderQty": 20, "quoteCurrency": "USD",
                           "minStopLossDistance": 0.0002, "commissionPerLot": 7}},
    }
    result = parse_instrument_metadata(payload, "EURUSD")
    assert result.instrument_id == "42"
    assert result.route_id == "r1"
    assert result.minimum_stop_distance == pytest.approx(0.0002)
    assert result.commission_per_lot == pytest.approx(7)


def test_instrument_metadata_fails_closed_when_contract_missing():
    with pytest.raises(AutonomousExecutionError) as error:
        parse_instrument_metadata({"instrument_id": 1, "listing": {}, "details": {}}, "EURUSD")
    assert error.value.code == "position_size_unverifiable"


def test_official_quote_abbreviations_are_supported():
    assert AutonomousDemoService._quote({"d": {"bp": 1.1, "ap": 1.1002}}) == (1.1, 1.1002)


def test_cross_currency_conversion_uses_direct_or_inverse_snapshot_quote():
    market = {"EURUSD": {"quote": {"d": {"bp": 1.0998, "ap": 1.1002}}}}
    assert AutonomousDemoService._conversion_rate("EUR", "USD", market) == pytest.approx(1.1)
    assert AutonomousDemoService._conversion_rate("USD", "EUR", market) == pytest.approx(1 / 1.1)


def test_execution_mode_is_account_scoped_and_defaults_read_only(tmp_path):
    repository = ExecutionRepository(tmp_path / "execution.db")
    first = repository.get_or_create_settings("user", "conn", "account-1", "100")
    second = repository.get_or_create_settings("user", "conn", "account-2", "200")
    assert first["execution_mode"] == second["execution_mode"] == "read_only"
    repository.set_mode("user", "conn", "account-1", "100", ExecutionMode.DEMO_AUTONOMOUS)
    assert repository.get_or_create_settings("user", "conn", "account-1", "100")["execution_mode"] == "demo_autonomous"
    assert repository.get_or_create_settings("user", "conn", "account-2", "200")["execution_mode"] == "read_only"


def test_equity_high_watermark_never_moves_down(tmp_path):
    repository = ExecutionRepository(tmp_path / "execution.db")
    repository.get_or_create_settings("user", "conn", "account", "100")
    assert repository.observe_equity("user", "conn", "account", "100", 1000) == 1000
    assert repository.observe_equity("user", "conn", "account", "100", 900) == 1000
    assert repository.observe_equity("user", "conn", "account", "100", 1100) == 1100


def test_submission_claim_is_durable_for_preview_and_key(tmp_path):
    repository = ExecutionRepository(tmp_path / "execution.db")
    # Foreign keys require the immutable snapshot and preview records to exist.
    now = "2099-01-01T00:00:00+00:00"
    repository.insert_snapshot({"id": "snap", "user_sub": "u", "connection_id": "c", "account_id": "a", "acc_num": "n", "environment": "demo", "strategy_name": "s", "strategy_version": "1", "normalized_snapshot_json": "{}", "retrieved_at": now, "expires_at": now, "created_at": now})
    repository.insert_preview({"id": "p1", "snapshot_id": "snap", "user_sub": "u", "connection_id": "c", "account_id": "a", "acc_num": "n", "environment": "demo", "pair": "EURUSD", "instrument_id": "1", "route_id": "r", "side": "long", "order_type": "market", "entry": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "quantity": 1000, "lot_size": .01, "estimated_risk": 10, "risk_percent": 1, "estimated_reward": 20, "reward_risk": 2, "broker_metadata_json": "{}", "status": "approved", "violations_json": "[]", "expires_at": now, "created_at": now})
    claimed, _ = repository.claim_submission("s1", "p1", "key-12345", "fingerprint")
    duplicate, existing = repository.claim_submission("s2", "p1", "other-key", "fingerprint")
    assert claimed is True
    assert duplicate is False
    assert existing["id"] == "s1"


def test_concurrent_submission_claims_have_one_winner(tmp_path):
    repository = ExecutionRepository(tmp_path / "execution.db")
    now = "2099-01-01T00:00:00+00:00"
    repository.insert_snapshot({"id": "snap", "user_sub": "u", "connection_id": "c", "account_id": "a", "acc_num": "n", "environment": "demo", "strategy_name": "s", "strategy_version": "1", "normalized_snapshot_json": "{}", "retrieved_at": now, "expires_at": now, "created_at": now})
    repository.insert_preview({"id": "p1", "snapshot_id": "snap", "user_sub": "u", "connection_id": "c", "account_id": "a", "acc_num": "n", "environment": "demo", "pair": "EURUSD", "instrument_id": "1", "route_id": "r", "side": "long", "order_type": "market", "entry": 1.1, "stop_loss": 1.09, "take_profit": 1.12, "quantity": 1000, "lot_size": .01, "estimated_risk": 10, "risk_percent": 1, "estimated_reward": 20, "reward_risk": 2, "broker_metadata_json": "{}", "status": "approved", "violations_json": "[]", "expires_at": now, "created_at": now})

    def claim(index):
        return repository.claim_submission(f"submission-{index}", "p1", "same-key", "same-fingerprint")[0]

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, (1, 2)))
    assert results.count(True) == 1
    assert results.count(False) == 1


def test_database_constraints_reject_duplicate_idempotency_key(tmp_path):
    repository = ExecutionRepository(tmp_path / "execution.db")
    with repository._connect() as db:
        indexes = db.execute("PRAGMA index_list(broker_submissions)").fetchall()
    assert sum(bool(row["unique"]) for row in indexes) >= 3


class DiscoveryClient:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    async def get_accounts(self):
        return {"accounts": [{"accountId": "a1", "accNum": "7", "name": "Anything", "currency": "USD"}]}

    async def aclose(self):
        pass


def configured_service(tmp_path, monkeypatch, *, base_url="https://demo.tradelocker.test/backend-api", environment="demo"):
    monkeypatch.setattr(settings, "tradelocker_demo_base_url", "https://demo.tradelocker.test/backend-api")
    brokers = BrokerRepository(tmp_path / "broker.db", secret="test-secret")
    brokers.save_connection("user", base_url=base_url, username="u", password="p", server="s", environment=environment)
    brokers.select_account("user", "a1", "7")
    account = brokers.list_accounts("user")[0]
    profile = brokers.create_profile("user", name="Demo profile", account_ref=account["public_id"])
    execution = ExecutionRepository(tmp_path / "broker.db")
    service = AutonomousDemoService(
        broker_repository=brokers, execution_repository=execution, client_factory=DiscoveryClient,
    )
    service.test_profile_ref = profile["public_id"]
    return service, execution


@pytest.mark.asyncio
async def test_verified_demo_context_defaults_to_read_only(tmp_path, monkeypatch):
    service, _ = configured_service(tmp_path, monkeypatch)
    with pytest.raises(AutonomousExecutionError) as error:
        await service.context("user", service.test_profile_ref)
    assert error.value.code == "execution_mode_read_only"


@pytest.mark.asyncio
async def test_demo_mode_can_be_enabled_only_for_scoped_account(tmp_path, monkeypatch):
    service, execution = configured_service(tmp_path, monkeypatch)
    service.brokers.update_profile("user", service.test_profile_ref, execution_mode="demo_manual")
    context = await service.context("user", service.test_profile_ref)
    assert context.execution_mode == ExecutionMode.DEMO_MANUAL
    assert context.account_id == "a1" and context.acc_num == "7"


@pytest.mark.asyncio
async def test_required_macro_policy_is_loaded_from_bound_strategy(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "tradelocker_demo_base_url", "https://demo.tradelocker.test/backend-api")
    brokers = BrokerRepository(tmp_path / "broker.db", secret="test-secret")
    connection = brokers.save_connection("user", base_url=settings.tradelocker_demo_base_url,
        username="u", password="p", server="s", environment="demo")
    brokers.sync_accounts("user", connection.connection_ref,
        {"accounts": [{"accountId": "a1", "accNum": "7", "currency": "USD"}]})
    account = brokers.list_accounts("user")[0]
    profile = brokers.create_profile("user", name="AI demo", account_ref=account["public_id"],
        strategy_template_id="strategy_ai_forex_confluence_v1", execution_mode="demo_manual")
    service = AutonomousDemoService(broker_repository=brokers,
        execution_repository=ExecutionRepository(tmp_path / "broker.db"), client_factory=DiscoveryClient)

    context = await service.context("user", profile["public_id"])

    assert context.risk["strategy_config"]["required_macro_series"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "base_url,environment",
    [
        ("https://live.tradelocker.test/backend-api", "demo"),
        ("https://demo.tradelocker.test/backend-api", "live"),
        ("https://live.tradelocker.test/backend-api", "live"),
    ],
)
async def test_environment_conflicts_fail_closed(tmp_path, monkeypatch, base_url, environment):
    service, _ = configured_service(tmp_path, monkeypatch, base_url=base_url, environment=environment)
    with pytest.raises(AutonomousExecutionError) as error:
        await service.context("user", service.test_profile_ref, require_mode=False)
    assert error.value.code == "demo_environment_verification_failed"


def reconciliation_payloads(*, quantity=0.01, side="buy", stop=1.09, target=1.12):
    config = {"d": {
        "ordersConfig": {"columns": [{"id": "id"}]},
        "ordersHistoryConfig": {"columns": [{"id": key} for key in (
            "id", "tradableInstrumentId", "qty", "side", "positionId", "stopLoss", "takeProfit"
        )]},
        "positionsConfig": {"columns": [{"id": "id"}, {"id": "tradableInstrumentId"}]},
    }}
    orders = {"d": {"orders": []}}
    history = {"d": {"ordersHistory": [["o1", "42", quantity, side, "pos1", stop, target]]}}
    positions = {"d": {"positions": [["pos1", "42"]]}}
    preview = {"instrument_id": "42", "lot_size": 0.01, "side": "long", "stop_loss": 1.09, "take_profit": 1.12}
    return config, orders, history, positions, preview


def test_reconciliation_maps_positional_order_and_position_fields():
    config, orders, history, positions, preview = reconciliation_payloads()
    result = AutonomousDemoService._reconcile(
        config, orders, history, positions, preview, {"d": {"orderId": "o1"}}
    )
    assert result["verified"] is True
    assert result["order_found"] is True and result["position_found"] is True
    assert result["broker_position_id"] == "pos1"


@pytest.mark.parametrize(
    "overrides,failed_check",
    [({"quantity": 0.02}, "quantity_matches"), ({"side": "sell"}, "side_matches"),
     ({"stop": 1.08}, "stop_loss_matches"), ({"target": 1.13}, "take_profit_matches")],
)
def test_reconciliation_reports_protection_and_order_mismatches(overrides, failed_check):
    config, orders, history, positions, preview = reconciliation_payloads(**overrides)
    result = AutonomousDemoService._reconcile(
        config, orders, history, positions, preview, {"d": {"orderId": "o1"}}
    )
    assert result["verified"] is False
    assert result[failed_check] is False
