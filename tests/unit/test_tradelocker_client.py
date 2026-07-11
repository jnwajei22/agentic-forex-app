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


def _client(handler) -> TradeLockerClient:
    return TradeLockerClient(
        base_url="https://demo.tradelocker.test/backend-api",
        username="user@example.test",
        password="never-log-this",
        server="DEMO",
        account_id="12345",
        account_number="2",
        transport=httpx.MockTransport(handler),
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
        assert await client.get_account_status() == {"balance": 1000.0}
        assert await client.get_open_positions() == {"d": [[1, "EURUSD"]]}
        assert await client.get_orders() == {"d": []}

    assert calls["login"] == 1


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
        assert "accounts" in await client.get_accounts()
        assert await client.get_symbols() == {"instruments": []}


@pytest.mark.asyncio
async def test_quote_and_candles_resolve_documented_info_route():
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
                200, json={"t": [1], "o": [1.0], "h": [1.1], "l": [0.9], "c": [1.05]}
            )
        raise AssertionError(f"Unexpected request: {request.url.path}")

    async with _client(handler) as client:
        assert (await client.get_quote("EUR/USD"))["ask"] == 1.101
        assert (await client.get_candles("EUR/USD", "1h", 100))["c"] == [1.05]


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
