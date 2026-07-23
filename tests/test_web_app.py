"""
웹 PWA 서빙 라우트 테스트.

conftest 가 FCM_WEB_* 환경변수를 비우므로 기본 상태는 "웹푸시 미설정".
설정된 상태는 monkeypatch 로 환경변수를 채우고 get_settings 캐시를 비워 재현한다.
"""
import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

client = TestClient(app)

_WEB_ENV = {
    "FCM_PROJECT_ID": "test-proj",
    "FCM_WEB_API_KEY": "AIzaFake",
    "FCM_WEB_APP_ID": "1:123:web:abc",
    "FCM_WEB_MESSAGING_SENDER_ID": "123",
    "FCM_VAPID_KEY": "BFakeVapid",
}


@pytest.fixture()
def fcm_web_configured(monkeypatch):
    """Firebase 웹 설정이 채워진 상태를 흉내낸다. 끝나면 캐시를 비워 원상복구."""
    for key, value in _WEB_ENV.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_app_page_served():
    response = client.get("/app")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "명예소방관" in response.text


def test_login_page_served():
    response = client.get("/login")
    assert response.status_code == 200
    assert "카카오로 시작하기" in response.text
    assert "구글로 시작하기" in response.text


def test_static_files_served():
    assert client.get("/static/manifest.json").status_code == 200
    assert client.get("/static/app.js").status_code == 200


def test_firebase_config_disabled_by_default():
    response = client.get("/firebase-config")
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_firebase_config_enabled(fcm_web_configured):
    data = client.get("/firebase-config").json()
    assert data["enabled"] is True
    assert data["config"]["projectId"] == "test-proj"
    assert data["config"]["apiKey"] == "AIzaFake"
    assert data["vapidKey"] == "BFakeVapid"


def test_messaging_sw_404_when_disabled():
    assert client.get("/firebase-messaging-sw.js").status_code == 404


def test_messaging_sw_contains_config(fcm_web_configured):
    response = client.get("/firebase-messaging-sw.js")
    assert response.status_code == 200
    assert "javascript" in response.headers["content-type"]
    assert '"projectId": "test-proj"' in response.text
    assert "onBackgroundMessage" in response.text
