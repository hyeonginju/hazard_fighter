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


def test_app_page_has_loading_placeholders():
    """콜드 스타트로 응답이 늦을 때 빈 화면 대신 로딩 문구가 보여야 한다."""
    html = client.get("/app").text
    assert html.count("불러오는 중") >= 3  # 사용자 바 + 구독 목록 + 알림 목록


def test_app_page_shows_device_push_status():
    """이 기기가 알림을 받는 상태인지 화면에 보여야 한다.

    2026-07-29: FCM 이 토큰을 무효화해 알림이 끊겼는데 화면엔 아무 표시가 없어서
    사용자가 알 방법이 없었다. app.js 의 syncPushToken 이 이 자리를 채운다.
    """
    html = client.get("/app").text
    assert 'id="push-status"' in html


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


# --- API 문서 노출 게이팅 (2026-08-28) ----------------------------------------

def test_docs_open_by_default():
    """로컬 개발 기본값은 켜짐 — README 의 실행 안내가 /docs 를 가리킨다."""
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def test_docs_closed_when_disabled(monkeypatch):
    """DOCS_ENABLED=0 이면 /docs 와 스키마가 함께 사라진다.

    스키마(/openapi.json)를 같이 끄는 게 핵심이다 — /docs 만 404 로 만들면
    사람이 보는 화면만 가려지고 기계가 읽는 목록은 그대로 열려 있어서,
    "인증 없이 DB 를 건드리는 엔드포인트가 어디인가"를 스캐너에게 계속 알려준다.

    설정은 앱 객체를 만들 때 한 번 읽히므로 모듈을 다시 불러와야 재현된다.
    """
    import importlib

    import app.main

    monkeypatch.setenv("DOCS_ENABLED", "0")
    get_settings.cache_clear()
    try:
        closed = TestClient(importlib.reload(app.main).app)
        assert closed.get("/docs").status_code == 404
        assert closed.get("/redoc").status_code == 404
        assert closed.get("/openapi.json").status_code == 404
        # 문서만 닫힌 것이지 서비스가 닫힌 게 아니다
        assert closed.get("/health").status_code == 200
    finally:
        monkeypatch.delenv("DOCS_ENABLED", raising=False)
        get_settings.cache_clear()
        importlib.reload(app.main)  # 다른 테스트를 위해 원상복구
