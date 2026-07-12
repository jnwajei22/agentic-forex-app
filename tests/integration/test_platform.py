import sqlite3
from unittest.mock import AsyncMock
import pytest
from fastapi.testclient import TestClient

from app.api.routes import platform
from app.auth.identity import reset_current_claims, set_current_claims
from app.brokers.tradelocker import adapter
from app.brokers.tradelocker.client import TradeLockerError
from app.config.settings import settings
from app.main import app
from app.mcp import tools
from app.storage.brokers import BrokerRepository


@pytest.fixture
def platform_storage(tmp_path, monkeypatch):
    db_path = tmp_path / "app.db"
    monkeypatch.setattr(settings, "sqlite_path", str(db_path))
    monkeypatch.setattr(settings, "broker_secret_key", "unit-test-broker-secret")
    monkeypatch.setattr(settings, "allow_env_broker_fallback", False)
    return BrokerRepository()


@pytest.fixture(autouse=True)
def clear_dependency_overrides():
    yield
    app.dependency_overrides.clear()


def _claims(subject: str) -> dict:
    return {"sub": subject, "email": f"{subject.replace('|', '-')}@example.test"}


def _client_for(subject: str) -> TestClient:
    app.dependency_overrides[platform.current_claims] = lambda: _claims(subject)
    return TestClient(app)


def test_user_cannot_access_another_users_broker_connection(platform_storage):
    platform_storage.save_connection(
        "auth0|user-b",
        base_url="https://demo.example/backend-api",
        username="user-b",
        password="password-b",
        server="DEMO",
    )

    with _client_for("auth0|user-a") as client:
        response = client.get("/api/broker/status")

    assert response.json()["status"] == "not_connected"
    assert response.json()["connected"] is False
    assert response.json()["selected_account"] is None
    assert platform_storage.get_connection("auth0|user-a") is None


def test_me_is_tied_to_auth0_subject(platform_storage):
    with _client_for("auth0|user-a") as client:
        response = client.get("/api/me")

    assert response.status_code == 200
    assert response.json()["sub"] == "auth0|user-a"
    with sqlite3.connect(platform_storage.db_path) as connection:
        stored = connection.execute("SELECT auth0_sub FROM users").fetchall()
    assert stored == [("auth0|user-a",)]


def test_password_is_encrypted_at_rest(platform_storage):
    password = "plain-text-password"
    platform_storage.save_connection(
        "auth0|user-a",
        base_url="https://demo.example/backend-api",
        username="user-a",
        password=password,
        server="DEMO",
    )

    with sqlite3.connect(platform_storage.db_path) as connection:
        encrypted = connection.execute(
            "SELECT password_encrypted FROM broker_connections"
        ).fetchone()[0]

    assert password.encode() not in encrypted
    assert platform_storage.get_connection("auth0|user-a").password == password


def test_saved_credentials_discover_accounts_without_returning_secrets(
    platform_storage, monkeypatch
):
    password = "private-password"
    token = "private-jwt-token"
    captured = {}

    class FakeClient:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_accounts(self):
            return {"accounts": [{"accountId": 12345, "accNum": 2}]}

    monkeypatch.setattr(platform, "TradeLockerClient", FakeClient)
    with _client_for("auth0|user-a") as client:
        saved = client.post(
            "/api/broker/tradelocker/save-credentials",
            json={
                "base_url": "https://demo.example/backend-api",
                "username": "user-a",
                "password": password,
                "server": "DEMO",
            },
        )
        discovered = client.post("/api/broker/tradelocker/discover-accounts")

    assert saved.json()["status"] == "connected_no_account"
    assert discovered.json() == {"accounts": [{"accountId": 12345, "accNum": 2}]}
    assert captured["password"] == password
    output = saved.text + discovered.text
    assert password not in output
    assert token not in output
    assert "password_encrypted" not in output


def test_invalid_tradelocker_credentials_are_rejected_before_storage(platform_storage, monkeypatch):
    class RejectedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_accounts(self):
            raise TradeLockerError("login", "Rejected", code="http_error", status_code=400)

    monkeypatch.setattr(platform, "TradeLockerClient", RejectedClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/tradelocker/save-credentials", json={
            "base_url": "https://live.tradelocker.com/backend-api",
            "username": "user-a@example.test", "password": "wrong",
            "server": "DEMO",
        })
    assert response.status_code == 401
    assert response.json()["error"] == "tradelocker_credentials_rejected"
    assert "rejected the credentials or server selection" in response.json()["message"]
    assert response.json()["request_id"]
    assert platform_storage.get_connection("auth0|user-a") is None
    assert "wrong" not in response.text


def test_tradelocker_upstream_failure_has_structured_service_error(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.tradelocker.com/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )

    class FailedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_accounts(self):
            raise TradeLockerError("get_accounts", "Timeout", code="timeout")

    monkeypatch.setattr(platform, "TradeLockerClient", FailedClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/tradelocker/discover-accounts")
    assert response.status_code == 502
    assert response.json()["error"] == "tradelocker_account_discovery_failed"
    assert response.json()["message"] == "Unable to retrieve TradeLocker accounts."


def test_tradelocker_account_parsing_error_is_structured(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.tradelocker.com/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )

    class MalformedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_accounts(self):
            raise TradeLockerError(
                "get_accounts", "Unusable accounts response", code="invalid_response"
            )

    monkeypatch.setattr(platform, "TradeLockerClient", MalformedClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/tradelocker/discover-accounts")
    assert response.status_code == 502
    assert response.json()["error"] == "tradelocker_account_discovery_failed"
    assert "http_error" not in response.text


def test_missing_application_session_is_not_a_tradelocker_rejection(platform_storage):
    with TestClient(app) as client:
        response = client.post("/api/broker/tradelocker/discover-accounts")
    assert response.status_code == 401
    assert response.json()["detail"] == "OAuth access token is required."


def test_selected_account_is_stored_per_user(platform_storage):
    platform_storage.save_connection(
        "auth0|user-a",
        base_url="https://demo.example/backend-api",
        username="user-a",
        password="password-a",
        server="DEMO",
    )
    with _client_for("auth0|user-a") as client:
        response = client.post(
            "/api/broker/tradelocker/select-account",
            json={"account_id": "12345", "account_number": "2"},
        )

    stored = platform_storage.get_connection("auth0|user-a")
    assert response.json()["status"] == "ready"
    assert stored.account_id == "12345"
    assert stored.account_number == "2"


def test_onboarding_status_requires_valid_discovered_selected_account(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.example/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )
    platform_storage.select_account("auth0|user-a", "12345", "2")

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_accounts(self):
            return {"accounts": [{"accountId": 12345, "accNum": 2}]}

    monkeypatch.setattr(platform, "TradeLockerClient", FakeClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/onboarding-status")

    assert response.json()["status"] == "ready"
    assert "password" not in response.text.lower()


def test_onboarding_status_rejects_revoked_tradelocker_credentials(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.example/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )
    platform_storage.select_account("auth0|user-a", "12345", "2")

    class RevokedClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get_accounts(self):
            raise TradeLockerError("get_accounts", "Unauthorized", code="unauthorized")

    monkeypatch.setattr(platform, "TradeLockerClient", RevokedClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/onboarding-status")

    assert response.json()["status"] == "invalid_credentials"
    assert "Unauthorized" not in response.text


@pytest.mark.parametrize(
    ("error", "expected_status", "retryable"),
    [
        (TradeLockerError("get_accounts", "Expired", code="token_expired"), "expired", False),
        (TradeLockerError("get_accounts", "Timeout", code="timeout"), "unavailable", True),
    ],
)
def test_onboarding_status_classifies_expired_and_unavailable_connections(
    platform_storage, monkeypatch, error, expected_status, retryable
):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.example/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )

    class FailedClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_accounts(self): raise error

    monkeypatch.setattr(platform, "TradeLockerClient", FailedClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/onboarding-status")
    assert response.status_code == 200
    assert response.json()["status"] == expected_status
    assert response.json()["connected"] is False
    assert response.json()["selected_account"] is None
    assert response.json()["retryable"] is retryable


def test_onboarding_status_connected_without_account(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.example/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )

    class ValidClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): return None
        async def get_accounts(self): return {"accounts": [{"accountId": 123, "accNum": 1}]}

    monkeypatch.setattr(platform, "TradeLockerClient", ValidClient)
    with _client_for("auth0|user-a") as client:
        response = client.post("/api/broker/onboarding-status")
    assert response.json() == {
        "status": "connected_no_account", "connected": True,
        "selected_account": None, "message": None, "retryable": False,
    }


@pytest.mark.asyncio
async def test_mcp_tool_uses_current_users_saved_connection(platform_storage, monkeypatch):
    platform_storage.save_connection(
        "auth0|user-a",
        base_url="https://demo.example/backend-api",
        username="user-a",
        password="password-a",
        server="DEMO-A",
    )
    platform_storage.save_connection(
        "auth0|user-b",
        base_url="https://demo.example/backend-api",
        username="user-b",
        password="password-b",
        server="DEMO-B",
    )

    class FakeClient:
        def __init__(self, **kwargs):
            self.username = kwargs["username"]

        async def get_accounts(self):
            return {"accounts": [{"name": self.username}]}

    monkeypatch.setattr(adapter, "TradeLockerClient", FakeClient)
    identity_token = set_current_claims(_claims("auth0|user-a"))
    try:
        result = await tools.get_tradelocker_accounts()
    finally:
        reset_current_claims(identity_token)

    assert result == {"accounts": [{"name": "user-a"}]}
    assert "user-b" not in str(result)
    assert "password-a" not in str(result)


def test_cors_allows_configured_frontend_origin():
    with TestClient(app) as client:
        response = client.options(
            "/api/me",
            headers={
                "Origin": settings.frontend_origin,
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == settings.frontend_origin


@pytest.mark.asyncio
async def test_mcp_missing_connection_returns_safe_setup_url(platform_storage, monkeypatch):
    monkeypatch.setattr(settings, "frontend_origin", "https://setup.example.test/")
    monkeypatch.setattr(settings, "chatgpt_return_url", "https://chatgpt.com")
    identity_token = set_current_claims(_claims("auth0|not-connected"))
    try:
        result = await tools.get_my_tradelocker_symbols()
        status = tools.get_tradelocker_connection_status()
    finally:
        reset_current_claims(identity_token)

    expected_url = (
        "https://setup.example.test/connect-tradelocker?source=chatgpt"
        "&returnTo=https%3A%2F%2Fchatgpt.com"
    )
    assert result == {
        "status": "setup_required",
        "message": "TradeLocker setup required.",
        "setup_url": expected_url,
        "instruction": (
            "Open the setup URL, connect TradeLocker using the same login account, "
            "then return to ChatGPT and run this again."
        ),
    }
    assert status["setup_url"] == expected_url
    assert status["connected"] is False
    assert status["selected_account"] is False
    serialized = str(result).lower()
    assert "password" not in serialized
    assert "token" not in serialized
    assert "username" not in serialized


@pytest.mark.asyncio
async def test_authorized_user_with_revoked_tradelocker_gets_setup_recovery(
    platform_storage, monkeypatch
):
    platform_storage.save_connection(
        "auth0|user-a", base_url="https://demo.example/backend-api",
        username="user-a", password="password-a", server="DEMO",
    )
    client = type("Client", (), {
        "get_symbols": AsyncMock(
            side_effect=TradeLockerError(
                "get_symbols", "Unauthorized", code="http_error", status_code=401
            )
        )
    })()
    monkeypatch.setattr(tools, "get_tradelocker_adapter", lambda: type("Adapter", (), {"client": client})())
    identity_token = set_current_claims(_claims("auth0|user-a"))
    try:
        result = await tools.get_my_tradelocker_symbols()
    finally:
        reset_current_claims(identity_token)
    assert result["status"] == "setup_required"
    assert "setup_url" in result
