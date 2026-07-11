import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import jwt


SUPPORTED_TIMEFRAMES = {"1m", "5m", "15m", "30m", "1H", "4H", "1D", "1W", "1M"}


class TradeLockerError(RuntimeError):
    """A sanitized, structured TradeLocker client failure."""

    def __init__(
        self,
        operation: str,
        message: str,
        *,
        code: str = "tradelocker_error",
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.operation = operation
        self.code = code
        self.status_code = status_code

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": "error",
            "error": self.code,
            "operation": self.operation,
            "status_code": self.status_code,
            "message": str(self),
        }


def _not_implemented(operation: str) -> dict[str, str]:
    return {
        "status": "not_implemented",
        "operation": operation,
        "message": "The configured TradeLocker API does not expose this read endpoint.",
    }


class TradeLockerClient:
    """Async client containing only documented TradeLocker read operations."""

    def __init__(
        self,
        *,
        base_url: str,
        username: str | None,
        password: str | None,
        server: str | None,
        account_id: str | None,
        account_number: str | None,
        timeout: float = 10.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.username = username
        self.password = password
        self.server = server
        self.account_id = account_id
        self.account_number = account_number
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
        )
        self._access_token: str | None = None
        self._token_expires_at = 0.0
        self._login_lock = asyncio.Lock()

    async def __aenter__(self) -> "TradeLockerClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        await self._http.aclose()

    def validate_login_config(self, operation: str = "login") -> None:
        missing = [
            name
            for name, value in (
                ("TRADELOCKER_BASE_URL", self.base_url),
                ("TRADELOCKER_USERNAME", self.username),
                ("TRADELOCKER_PASSWORD", self.password),
                ("TRADELOCKER_SERVER", self.server),
            )
            if not value
        ]
        if missing:
            raise TradeLockerError(
                operation,
                f"TradeLocker login configuration is incomplete: {', '.join(missing)}.",
                code="not_configured",
            )

    def validate_account_config(self, operation: str = "account") -> None:
        self.validate_login_config(operation)
        missing = [
            name
            for name, value in (
                ("TRADELOCKER_ACCOUNT_ID", self.account_id),
                ("TRADELOCKER_ACCOUNT_NUMBER", self.account_number),
            )
            if not value
        ]
        if missing:
            raise TradeLockerError(
                operation,
                f"TradeLocker account configuration is incomplete: {', '.join(missing)}.",
                code="not_configured",
            )

    def _credentials(self) -> dict[str, str]:
        self.validate_login_config()
        return {"email": self.username, "password": self.password, "server": self.server}

    async def login(self, *, force: bool = False) -> str:
        if not force and self._access_token and time.time() < self._token_expires_at - 30:
            return self._access_token
        async with self._login_lock:
            if not force and self._access_token and time.time() < self._token_expires_at - 30:
                return self._access_token
            payload = await self._request(
                "POST", "/auth/jwt/token", operation="login", auth=False, json=self._credentials()
            )
            token = payload.get("accessToken") if isinstance(payload, dict) else None
            if not isinstance(token, str) or not token:
                raise TradeLockerError(
                    "login", "TradeLocker did not return an access token.", code="invalid_response"
                )
            self._access_token = token
            self._token_expires_at = self._token_expiry(token, payload)
            return token

    @staticmethod
    def _token_expiry(token: str, payload: dict[str, Any]) -> float:
        for key in ("accessTokenExpiresAt", "accessTokenExpiration", "expiresAt"):
            value = payload.get(key)
            if isinstance(value, (int, float)):
                return float(value) / 1000 if value > 10_000_000_000 else float(value)
        try:
            exp = jwt.decode(token, options={"verify_signature": False}).get("exp")
            if isinstance(exp, (int, float)):
                return float(exp)
        except jwt.PyJWTError:
            pass
        return time.time() + 300

    def _account_headers(self, operation: str = "account") -> dict[str, str]:
        if not self.account_number:
            message = "TradeLocker account number is not configured."
            if operation == "get_config":
                message = (
                    "Account number is required for account-specific config. "
                    "Run get_tradelocker_accounts first."
                )
            raise TradeLockerError(
                operation, message, code="not_configured"
            )
        return {"accNum": self.account_number}

    def _account_path(self, suffix: str) -> str:
        if not self.account_id:
            raise TradeLockerError(
                "account", "TradeLocker account ID is not configured.", code="not_configured"
            )
        return f"/trade/accounts/{self.account_id}/{suffix.lstrip('/')}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        auth: bool = True,
        **kwargs: Any,
    ) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if auth:
            headers["Authorization"] = f"Bearer {await self.login()}"
        try:
            response = await self._http.request(method, path, headers=headers, **kwargs)
            response.raise_for_status()
            return response.json()
        except httpx.TimeoutException as exc:
            raise TradeLockerError(operation, "TradeLocker request timed out.", code="timeout") from exc
        except httpx.HTTPStatusError as exc:
            raise TradeLockerError(
                operation,
                "TradeLocker rejected the request.",
                code="http_error",
                status_code=exc.response.status_code,
            ) from exc
        except (httpx.RequestError, ValueError) as exc:
            raise TradeLockerError(
                operation, "TradeLocker returned an unusable response.", code="request_failed"
            ) from exc

    async def _optional_get(self, path: str, *, operation: str, **kwargs: Any) -> Any:
        try:
            return await self._request("GET", path, operation=operation, **kwargs)
        except TradeLockerError as exc:
            if exc.status_code in {404, 405, 501}:
                return _not_implemented(operation)
            raise

    async def get_config(self) -> Any:
        return await self._optional_get(
            "/trade/config",
            operation="get_config",
            headers=self._account_headers("get_config"),
        )

    async def get_accounts(self) -> Any:
        self.validate_login_config("get_accounts")
        payload = await self._optional_get(
            "/auth/jwt/all-accounts", operation="get_accounts"
        )
        if isinstance(payload, dict) and payload.get("status") == "not_implemented":
            return payload
        container = payload.get("d", payload) if isinstance(payload, dict) else {}
        records = container.get("accounts", []) if isinstance(container, dict) else []
        if not isinstance(records, list):
            raise TradeLockerError(
                "get_accounts",
                "TradeLocker returned an unusable accounts response.",
                code="invalid_response",
            )
        safe_records = []
        for record in records:
            if not isinstance(record, dict):
                continue
            safe_record = {}
            account_id = record.get("accountId", record.get("id"))
            if account_id is not None:
                safe_record["accountId"] = account_id
            for key in ("accNum", "name", "currency", "status"):
                if key in record:
                    safe_record[key] = record[key]
            safe_records.append(safe_record)
        return {"accounts": safe_records}

    async def get_account_status(self) -> Any:
        return await self._optional_get(
            self._account_path("state"),
            operation="get_account_status",
            headers=self._account_headers(),
        )

    async def get_open_positions(self) -> Any:
        return await self._optional_get(
            self._account_path("positions"),
            operation="get_open_positions",
            headers=self._account_headers(),
        )

    async def get_orders(self) -> Any:
        return await self._optional_get(
            self._account_path("orders"),
            operation="get_orders",
            headers=self._account_headers(),
        )

    async def get_symbols(self) -> Any:
        return await self._optional_get(
            self._account_path("instruments"),
            operation="get_symbols",
            headers=self._account_headers(),
        )

    @staticmethod
    def _instrument_rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return [row for row in payload if isinstance(row, dict)]
        if isinstance(payload, dict):
            for key in ("instruments", "data", "d"):
                nested = payload.get(key)
                rows = TradeLockerClient._instrument_rows(nested)
                if rows:
                    return rows
        return []

    async def _resolve_instrument(self, symbol: str) -> tuple[Any, Any]:
        payload = await self.get_symbols()
        if isinstance(payload, dict) and payload.get("status") == "not_implemented":
            raise TradeLockerError(
                "resolve_symbol", "TradeLocker instruments are unavailable.", code="not_implemented"
            )
        target = symbol.replace("/", "").upper()
        for row in self._instrument_rows(payload):
            name = str(row.get("name", row.get("symbol", ""))).replace("/", "").upper()
            if name != target:
                continue
            instrument_id = row.get("tradableInstrumentId", row.get("id"))
            routes = row.get("routes", [])
            info_route = next(
                (
                    route.get("id", route.get("routeId"))
                    for route in routes
                    if isinstance(route, dict) and str(route.get("type", "")).upper() == "INFO"
                ),
                row.get("routeId"),
            )
            if instrument_id is not None and info_route is not None:
                return instrument_id, info_route
        raise TradeLockerError(
            "resolve_symbol", "The requested TradeLocker symbol was not found.", code="symbol_not_found"
        )

    async def get_quote(self, symbol: str) -> Any:
        instrument_id, route_id = await self._resolve_instrument(symbol)
        return await self._optional_get(
            "/trade/quotes",
            operation="get_quote",
            headers=self._account_headers(),
            params={"tradableInstrumentId": instrument_id, "routeId": route_id},
        )

    async def get_candles(self, symbol: str, timeframe: str, lookback: int) -> Any:
        resolution = timeframe if timeframe in SUPPORTED_TIMEFRAMES else timeframe.upper()
        if resolution not in SUPPORTED_TIMEFRAMES:
            raise TradeLockerError(
                "get_candles", "Unsupported TradeLocker timeframe.", code="invalid_timeframe"
            )
        if lookback < 1 or lookback > 20_000:
            raise TradeLockerError(
                "get_candles", "Lookback must be between 1 and 20000.", code="invalid_lookback"
            )
        instrument_id, route_id = await self._resolve_instrument(symbol)
        minutes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1H": 60, "4H": 240,
                   "1D": 1440, "1W": 10080, "1M": 43200}[resolution]
        end = datetime.now(timezone.utc)
        start = end - timedelta(minutes=minutes * lookback)
        return await self._optional_get(
            "/trade/history",
            operation="get_candles",
            headers=self._account_headers(),
            params={
                "tradableInstrumentId": instrument_id,
                "routeId": route_id,
                "resolution": resolution,
                "from": int(start.timestamp() * 1000),
                "to": int(end.timestamp() * 1000),
            },
        )
