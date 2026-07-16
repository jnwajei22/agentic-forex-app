from datetime import datetime, timedelta, timezone

import httpx
import jwt
import pytest

from app.brokers.tradelocker.adapter import TradeLockerAdapter
from app.brokers.tradelocker.client import TradeLockerClient, TradeLockerError


def _token() -> str:
    return jwt.encode(
        {"exp": datetime.now(timezone.utc) + timedelta(minutes=10)},
        "test-only-key-that-is-at-least-32-bytes-long",
        algorithm="HS256",
    )


def _client(handler, **overrides) -> TradeLockerClient:
    config = {
        "base_url": "https://demo.tradelocker.test/backend-api",
        "username": "user@example.test",
        "password": "never-log-this",
        "server": "DEMO",
        "account_id": "12345",
        "account_number": "2",
        "transport": httpx.MockTransport(handler),
    }
    config.update(overrides)
    return TradeLockerClient(
        **config,
    )


@pytest.mark.asyncio
async def test_login_is_cached_and_account_reads_are_authenticated():
    calls = {"login": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            calls["login"] += 1
            return httpx.Response(201, json={"accessToken": _token()})
        assert request.headers["authorization"].startswith("Bearer ")
        assert request.headers["accnum"] == "2"
        if request.url.path.endswith("/state"):
            return httpx.Response(200, json={"balance": 1000.0})
        if request.url.path.endswith("/positions"):
            return httpx.Response(200, json={"d": [[1, "EURUSD"]]})
        if request.url.path.endswith("/orders"):
            return httpx.Response(200, json={"d": []})
        raise AssertionError(f"Unexpected request: {request.url.path}")

    async with _client(handler) as client:
        assert await client.get_account_state_payload() == {"balance": 1000.0}
        assert await client.get_open_positions() == {"d": [[1, "EURUSD"]]}
        assert await client.get_orders() == {"d": []}

    assert calls["login"] == 1


@pytest.mark.asyncio
async def test_unauthorized_account_read_refreshes_token_once_without_changing_account():
    calls = {"login": 0, "state": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            calls["login"] += 1
            return httpx.Response(201, json={"accessToken": _token()})
        if request.url.path.endswith("/state"):
            calls["state"] += 1
            if calls["state"] == 1:
                return httpx.Response(401, json={"error": "expired"})
            assert request.headers["accnum"] == "2"
            return httpx.Response(200, json={"d": {"accountDetailsData": []}})
        raise AssertionError(f"Unexpected request: {request.url.path}")

    async with _client(handler) as client:
        assert await client.get_account_state_payload() == {"d": {"accountDetailsData": []}}
        assert client.account_id == "12345" and client.account_number == "2"
        assert client.token_refresh_count == 1
    assert calls == {"login": 2, "state": 2}


@pytest.mark.asyncio
async def test_config_accounts_and_symbols_use_documented_read_routes():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": _token()})
        if request.url.path.endswith("/trade/config"):
            return httpx.Response(200, json={"positionsConfig": []})
        if request.url.path.endswith("/auth/jwt/all-accounts"):
            return httpx.Response(200, json={"accounts": [{"id": 12345, "accNum": 2}]})
        if request.url.path.endswith("/instruments"):
            return httpx.Response(200, json={"instruments": []})
        raise AssertionError(f"Unexpected request: {request.url.path}")

    async with _client(handler) as client:
        assert "positionsConfig" in await client.get_config()
        assert await client.get_accounts() == {
            "accounts": [{"accountId": 12345, "accNum": 2}]
        }
        assert await client.get_symbols() == {"instruments": []}


@pytest.mark.asyncio
async def test_place_order_uses_account_route_header_and_atomic_protections():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": _token()})
        captured["path"] = request.url.path
        captured["headers"] = dict(request.headers)
        captured["body"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"orderId": "order-1"})

    order = {
        "qty": 0.01, "routeId": "trade-route", "side": "buy", "validity": "IOC",
        "type": "market", "tradableInstrumentId": 42, "price": 0,
        "stopLoss": 1.09, "stopLossType": "absolute",
        "takeProfit": 1.12, "takeProfitType": "absolute", "strategyId": "afd-test",
    }
    async with _client(handler) as client:
        assert await client.place_order(order) == {"orderId": "order-1"}
    assert captured["path"].endswith("/trade/accounts/12345/orders")
    assert captured["headers"]["accnum"] == "2"
    assert captured["body"]["stopLossType"] == "absolute"
    assert captured["body"]["takeProfitType"] == "absolute"


@pytest.mark.asyncio
async def test_place_order_rejects_caller_account_override_before_network():
    client = _client(lambda request: (_ for _ in ()).throw(AssertionError("network called")))
    with pytest.raises(TradeLockerError) as error:
        await client.place_order({"accountId": "other"})
    await client.aclose()
    assert error.value.code == "invalid_order"


@pytest.mark.asyncio
async def test_account_discovery_does_not_require_account_selection():
    secret_token = _token()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": secret_token})
        assert request.url.path.endswith("/auth/jwt/all-accounts")
        assert "accnum" not in request.headers
        return httpx.Response(
            200,
            json={
                "accounts": [{
                    "id": 45678,
                    "accNum": 3,
                    "name": "Demo account",
                    "currency": "USD",
                    "accessToken": secret_token,
                    "password": "must-not-escape",
                }]
            },
        )

    async with _client(handler, account_id=None, account_number=None) as client:
        result = await client.get_accounts()

    assert result == {
        "accounts": [{
            "accountId": 45678,
            "accNum": 3,
            "name": "Demo account",
            "currency": "USD",
        }]
    }
    assert secret_token not in str(result)
    assert "must-not-escape" not in str(result)


@pytest.mark.asyncio
async def test_account_specific_config_requires_discovered_account_number():
    client = _client(lambda request: httpx.Response(500), account_number=None)

    with pytest.raises(TradeLockerError) as caught:
        await client.get_config()
    await client.aclose()

    assert caught.value.code == "not_configured"
    assert str(caught.value) == (
        "Account number is required for account-specific config. "
        "Run get_tradelocker_accounts first."
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["password", "server"])
async def test_discovery_rejects_incomplete_login_config(missing):
    client = _client(lambda request: httpx.Response(500), **{missing: None}, account_number=None)

    with pytest.raises(TradeLockerError) as caught:
        await client.get_accounts()
    await client.aclose()

    expected_name = f"TRADELOCKER_{missing.upper()}"
    assert caught.value.code == "not_configured"
    assert expected_name in str(caught.value)
    assert "never-log-this" not in str(caught.value)


@pytest.mark.asyncio
async def test_discovery_does_not_log_password_or_token(caplog):
    secret_token = _token()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": secret_token})
        return httpx.Response(500, json={"accessToken": secret_token})

    async with _client(handler, account_id=None, account_number=None) as client:
        with pytest.raises(TradeLockerError):
            await client.get_accounts()

    assert "never-log-this" not in caplog.text
    assert secret_token not in caplog.text


@pytest.mark.asyncio
async def test_quote_and_candles_resolve_documented_info_route():
    candle_timestamp = int((datetime.now(timezone.utc) - timedelta(minutes=1)).timestamp() * 1000)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": _token()})
        if request.url.path.endswith("/instruments"):
            return httpx.Response(
                200,
                json={
                    "d": {"instruments": [{
                        "name": "EURUSD",
                        "tradableInstrumentId": 77,
                        "routes": [{"type": "INFO", "id": 9}],
                    }]}
                },
            )
        assert request.url.params["tradableInstrumentId"] == "77"
        assert request.url.params["routeId"] == "9"
        if request.url.path.endswith("/quotes"):
            return httpx.Response(200, json={"ask": 1.101, "bid": 1.1})
        if request.url.path.endswith("/history"):
            assert request.url.params["resolution"] == "1H"
            return httpx.Response(
                200, json={"t": [candle_timestamp], "o": [1.0], "h": [1.1], "l": [0.9], "c": [1.05]}
            )
        raise AssertionError(f"Unexpected request: {request.url.path}")

    async with _client(handler) as client:
        assert (await client.get_quote("EUR/USD"))["ask"] == 1.101
        result = await client.get_candles("EUR/USD", "1h", 100)
        assert result.candles[0].close == 1.05
        assert result.batches_requested == 2


@pytest.mark.asyncio
async def test_unavailable_optional_endpoint_returns_not_implemented():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/auth/jwt/token"):
            return httpx.Response(201, json={"accessToken": _token()})
        return httpx.Response(404, json={"message": "missing"})

    async with _client(handler) as client:
        result = await client.get_orders()

    assert result["status"] == "not_implemented"
    assert result["operation"] == "get_orders"


@pytest.mark.asyncio
async def test_errors_are_sanitized_and_structured():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"message": "bad credentials"})

    async with _client(handler) as client:
        with pytest.raises(TradeLockerError) as caught:
            await client.login()

    error = caught.value.as_dict()
    assert error["status_code"] == 401
    assert "user@example.test" not in str(error)
    assert "never-log-this" not in str(error)


@pytest.mark.asyncio
async def test_submit_order_remains_unimplemented():
    adapter = TradeLockerAdapter(client=_client(lambda request: httpx.Response(500)))
    with pytest.raises(NotImplementedError, match="intentionally disabled"):
        await adapter.submit_order(None)
    await adapter.client.aclose()
