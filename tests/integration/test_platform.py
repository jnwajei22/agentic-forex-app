import sqlite3
import pytest
from fastapi.testclient import TestClient

from app.api.routes import platform
from app.auth.identity import reset_current_claims, set_current_claims
from app.brokers.tradelocker import adapter
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

    assert response.json() == {"status": "setup_required", "provider": "tradelocker"}
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

    assert saved.json() == {"status": "saved", "provider": "tradelocker"}
    assert discovered.json() == {"accounts": [{"accountId": 12345, "accNum": 2}]}
    assert captured["password"] == password
    output = saved.text + discovered.text
    assert password not in output
    assert token not in output
    assert "password_encrypted" not in output


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
    assert response.json()["status"] == "connected"
    assert stored.account_id == "12345"
    assert stored.account_number == "2"


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
                "Origin": "https://app.agenticforexdesk.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "authorization",
            },
        )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "https://app.agenticforexdesk.com"
    )
