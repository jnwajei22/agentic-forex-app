from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.execution_profile_v2 import ExecutionProfileV2, deep_merge, migrate_legacy_profile
from app.storage.brokers import BrokerRepository
from app.services.trading_policy import (
    classify_orders, count_open_positions, deterministic_size, market_is_open,
    normalize_instrument, resolve_universe, screen_candidates, validate_exit_prices,
)


def instruments():
    rows = [
        {"tradableInstrumentId":"1","name":"EURUSD","assetClass":"forex","tradable":True,"marketState":"open","tickSize":.00001},
        {"tradableInstrumentId":"2","name":"XAUUSD","assetClass":"metals","tradable":True,"marketState":"open","tickSize":.01},
        {"tradableInstrumentId":"3","name":"BTCUSD","assetClass":"crypto","tradable":True,"marketState":"open","tickSize":.1},
    ]
    return [normalize_instrument(row) for row in rows]


def test_legacy_profile_projects_without_losing_limits():
    profile=migrate_legacy_profile({"strategy_name":"hourly_forex","allowed_instruments":["EURUSD"],
        "risk":{"risk_per_trade_percent":.4,"maximum_open_positions":3,"maximum_pending_orders":2,
                "minimum_reward_risk":1.75},"minimum_confidence":.8,"enabled":True})
    assert profile.trading_policy.preset_id == "hourly_forex"
    assert profile.market_universe.included_instrument_ids == ["EURUSD"]
    assert profile.risk_policy.fixed_risk_pct == .4
    assert profile.risk_policy.maximum_open_positions == 3
    assert profile.risk_policy.maximum_pending_entry_orders == 2
    assert profile.exit_policy.take_profit.minimum_reward_to_risk == 1.75


def test_partial_patch_deep_merges_and_validates_fields():
    data=deep_merge(ExecutionProfileV2().model_dump(),{"risk_policy":{"maximum_open_positions":7}})
    assert ExecutionProfileV2.model_validate(data).risk_policy.maximum_open_positions == 7
    with pytest.raises(ValidationError):
        ExecutionProfileV2.model_validate(deep_merge(data,{"risk_policy":{"maximum_open_positions":0}}))


def test_repository_migrates_on_patch_and_latest_limits_are_immediate(tmp_path):
    repo=BrokerRepository(tmp_path/"v2.db","secret")
    connection=repo.save_connection("owner",base_url="https://demo.tradelocker.test",username="u",password="p",server="s",environment="demo")
    repo.sync_accounts("owner",connection.connection_ref,{"accounts":[{"accountId":"a","accNum":"1"}]})
    account=repo.list_accounts("owner")[0]
    legacy=repo.create_profile("owner",name="profile",account_ref=account["public_id"],
        risk={"maximum_open_positions":3})
    assert legacy["migration_state"] == "legacy_projected"
    updated=repo.update_profile_v2("owner",legacy["public_id"],{"risk_policy":{"maximum_open_positions":7}})
    assert updated["migration_state"] == "native_v2"
    assert updated["profile_v2"]["risk_policy"]["maximum_open_positions"] == 7
    assert updated["risk"]["maximum_open_positions"] == 7
    assert repo.get_profile("other-user",legacy["public_id"]) is None
    assert repo.account_connection_context("other-user",account["account_alias"]) is None


def test_universe_modes_are_stable_id_based():
    catalog=instruments()
    assert {i["instrument_id"] for i in resolve_universe(catalog,{"mode":"all_available"})} == {"1","2","3"}
    assert [i["instrument_id"] for i in resolve_universe(catalog,{"mode":"groups","groups":["metals"]})] == ["2"]
    assert [i["instrument_id"] for i in resolve_universe(catalog,{"mode":"custom","included_instrument_ids":["3"]})] == ["3"]


def test_protective_orders_do_not_consume_pending_entry_limit():
    positions=[{"positionId":"p1","qty":1000,"stopLossId":"sl1","takeProfitId":"tp1"}]
    orders=[{"orderId":"sl1","positionId":"p1","type":"stop","status":"open"},
            {"orderId":"tp1","positionId":"p1","type":"limit","status":"open"},
            {"orderId":"entry2","type":"limit","status":"working"}]
    result=classify_orders(positions,orders)["counts"]
    assert result["protective_stop_loss"] == 1
    assert result["protective_take_profit"] == 1
    assert result["pending_entry"] == 1
    assert count_open_positions(positions) == 1
    assert count_open_positions([positions[0],dict(positions[0]),{"positionId":"zero","qty":0}]) == 1


def test_fixed_sizing_is_deterministic_and_respects_increment():
    result=deterministic_size(equity=10_000,entry=100,stop=99,loss_per_price_unit=1,
        minimum_quantity=1,maximum_quantity=1000,quantity_increment=3,
        risk_policy={"mode":"fixed","fixed_risk_pct":.25,"base_risk_pct":.25,"maximum_total_open_risk_pct":1})
    assert result.approved and result.risk_amount == 25
    assert result.quantity_before_rounding == 25
    assert result.quantity == 24


def test_adaptive_sizing_clamps_model_and_keeps_margin_separate():
    result=deterministic_size(equity=10_000,entry=100,stop=99,loss_per_price_unit=1,
        minimum_quantity=1,maximum_quantity=10000,quantity_increment=1,proposed_multiplier=100,
        risk_policy={"mode":"adaptive","base_risk_pct":.25,"minimum_risk_pct":.1,"maximum_risk_pct":.5,
                     "maximum_total_open_risk_pct":1,"maximum_margin_utilization_pct":10},
        estimated_margin_per_unit=50,available_margin=10_000)
    assert result.final_risk_pct == .5
    assert result.risk_amount == 50
    assert "maximum_margin_utilization_reached" in result.rejection_reasons


@pytest.mark.parametrize(("side","stop","target","approved"),[("long",99,102,True),("long",101,102,False),("short",101,98,True),("short",99,98,False)])
def test_exit_side_and_reward_validation(side,stop,target,approved):
    result=validate_exit_prices(side=side,entry=100,current_price=100,stop=stop,take_profit=target,
        tick_size=.1,minimum_reward_to_risk=1.5)
    assert result["approved"] is approved


def test_market_hours_are_asset_aware_and_screening_is_bounded():
    saturday=datetime(2026,7,18,12,tzinfo=timezone.utc);catalog=instruments()
    # Force fallback classification because explicit broker-open metadata takes precedence.
    forex={**catalog[0],"classification_source":"symbol_fallback","market_state":"unknown"}
    crypto={**catalog[2],"classification_source":"symbol_fallback","market_state":"unknown"}
    assert not market_is_open(forex,saturday)
    assert market_is_open(crypto,saturday)
    screened=screen_candidates(catalog*10,maximum_screened=8,maximum_deeply_analyzed=2)
    assert screened["candidates_screened"] == 8
    assert screened["candidates_deeply_analyzed"] == 2
