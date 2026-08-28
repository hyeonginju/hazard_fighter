"""
JWT 인증 테스트 — 토큰 발급/검증, 보호된 라우트, 구글 콜백 흐름.

API 라우트 테스트는 dependency_overrides 로 get_db 를 in-memory SQLite 세션으로
갈아끼운다 (운영 Postgres 없이 라우트→DB 왕복까지 검증하는 기존 패턴의 API 판).
구글 토큰 엔드포인트는 monkeypatch 로 흉내 — 테스트는 네트워크를 타지 않는다.
"""
import uuid
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import crud
from app.config import get_settings
from app.database import Base, get_db
from app.main import app
from app.services.auth import InvalidTokenError, decode_token, issue_token


@pytest.fixture()
def db():
    # StaticPool: TestClient 요청마다 새 커넥션을 열어도 같은 in-memory DB 를 보게 한다
    engine = create_engine(
        "sqlite+pysqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client(db):
    app.dependency_overrides[get_db] = lambda: db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


def _social_user(db, provider="google", pid="sub-1", nickname="형인"):
    return crud.get_or_create_social_user(db, provider, pid, nickname)


# --- 토큰 발급/검증 -----------------------------------------------------------

def test_token_roundtrip(db):
    user = _social_user(db)
    token = issue_token(user)
    assert decode_token(token) == user.id


def test_tampered_token_rejected(db):
    token = issue_token(_social_user(db))
    with pytest.raises(InvalidTokenError):
        decode_token(token[:-2] + "xx")  # 서명 훼손


def test_expired_token_rejected(db):
    user = _social_user(db)
    expired = pyjwt.encode(
        {"sub": str(user.id), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
        get_settings().jwt_secret,
        algorithm="HS256",
    )
    with pytest.raises(InvalidTokenError):
        decode_token(expired)


# --- 보호된 라우트 ------------------------------------------------------------

def test_protected_route_requires_token(client):
    assert client.get("/persons").status_code == 401
    assert client.get("/notifications").status_code == 401
    assert client.get("/subscriptions").status_code == 401
    assert client.get("/device-tokens").status_code == 401


def test_region_write_requires_token_but_read_is_open(client, db):
    """POST /regions 는 401, GET /regions 는 열어둔다 (2026-08-28).

    저장소를 공개하기 전 점검에서 POST /regions 가 무인증 쓰기인 걸 발견했다.
    /docs 로 이미 노출돼 있었으니 공개가 만든 위험은 아니지만, Neon 무료 한도를
    쓰고 있는 지금은 아무나 DB 에 행을 넣을 수 있다는 게 실제 비용이다.
    읽기는 표준 행정구역 조회표라 막지 않는다 — 그 비대칭을 여기에 고정해 둔다.
    """
    denied = client.post("/regions", json={"sido": "경기도", "sigungu": "안양시"})
    assert denied.status_code == 401

    headers = {"Authorization": f"Bearer {issue_token(_social_user(db))}"}
    created = client.post("/regions", json={"sido": "경기도", "sigungu": "안양시"}, headers=headers)
    assert created.status_code == 200

    # 읽기는 토큰 없이도 통과해야 한다 (scripts/demo_layer2.py 가 그렇게 쓴다)
    listed = client.get("/regions")
    assert listed.status_code == 200
    assert [r["id"] for r in listed.json()] == [created.json()["id"]]


def test_protected_route_with_valid_token(client, db):
    user = _social_user(db)
    headers = {"Authorization": f"Bearer {issue_token(user)}"}

    created = client.post(
        "/persons",
        json={"label": "어머니", "age_group": "고령", "tags": []},
        headers=headers,
    )
    assert created.status_code == 200

    listed = client.get("/persons", headers=headers)
    assert [p["label"] for p in listed.json()] == ["어머니"]


def test_person_limit_returns_409(client, db):
    user = _social_user(db)
    headers = {"Authorization": f"Bearer {issue_token(user)}"}
    for i in range(3):
        assert (
            client.post(
                "/persons",
                json={"label": f"보호대상{i}", "age_group": "성인", "tags": []},
                headers=headers,
            ).status_code
            == 200
        )
    over = client.post(
        "/persons", json={"label": "네번째", "age_group": "성인", "tags": []}, headers=headers
    )
    assert over.status_code == 409
    assert "3명" in over.json()["detail"]


def test_token_of_other_user_sees_own_data_only(client, db):
    a = _social_user(db, pid="user-a")
    b = _social_user(db, "kakao", pid="user-b")
    client.post(
        "/persons",
        json={"label": "a의 어머니", "age_group": "고령", "tags": []},
        headers={"Authorization": f"Bearer {issue_token(a)}"},
    )
    listed_by_b = client.get("/persons", headers={"Authorization": f"Bearer {issue_token(b)}"})
    assert listed_by_b.json() == []


# --- 구글 로그인 흐름 ---------------------------------------------------------

def test_google_login_disabled_without_config(client):
    # conftest 가 GOOGLE_CLIENT_* 를 비우므로 기본은 503 안내
    assert client.get("/auth/google/login", follow_redirects=False).status_code == 503


@pytest.fixture()
def google_configured(monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "test-client-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_google_login_redirects_with_state(client, google_configured):
    response = client.get("/auth/google/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://accounts.google.com")
    assert "client_id=test-client-id" in response.headers["location"]
    assert "oauth_state" in response.headers["set-cookie"]


def test_google_callback_issues_token(client, db, google_configured, monkeypatch):
    # 구글 토큰 엔드포인트 흉내: 서명 없는 id_token 반환 (aud/iss 는 검증 대상이라 맞춰줌)
    id_token = pyjwt.encode(
        {"sub": "google-sub-999", "name": "테스터", "aud": "test-client-id", "iss": "https://accounts.google.com"},
        "unused",
        algorithm="HS256",
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id_token": id_token}

    monkeypatch.setattr("app.api.routes.auth.httpx.post", lambda *a, **kw: FakeResponse())

    client.cookies.set("oauth_state", "state-123")
    response = client.get(
        "/auth/google/callback", params={"code": "code-1", "state": "state-123"}, follow_redirects=False
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("/app#token=")

    # 발급된 토큰으로 실제 사용자 조회까지 되는지
    token = location.split("token=")[1].split("&")[0]
    user_id = decode_token(token)
    assert crud.get_or_create_social_user(db, "google", "google-sub-999").id == user_id


def test_google_callback_rejects_wrong_state(client, google_configured):
    client.cookies.set("oauth_state", "state-abc")
    response = client.get(
        "/auth/google/callback", params={"code": "code-1", "state": "wrong"}, follow_redirects=False
    )
    assert response.status_code == 400


# --- 카카오 로그인 흐름 -------------------------------------------------------

@pytest.fixture()
def kakao_configured(monkeypatch):
    monkeypatch.setenv("KAKAO_REST_API_KEY", "test-kakao-key")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_kakao_login_redirects_with_state(client, kakao_configured):
    response = client.get("/auth/kakao/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://kauth.kakao.com")
    assert "client_id=test-kakao-key" in response.headers["location"]
    assert "oauth_state" in response.headers["set-cookie"]


def test_kakao_callback_issues_token(client, db, kakao_configured, monkeypatch):
    # 토큰 교환 → 사용자 조회 두 단계를 모두 흉내
    class FakeTokenResponse:
        status_code = 200

        def json(self):
            return {"access_token": "kakao-access"}

    class FakeMeResponse:
        status_code = 200

        def json(self):
            return {"id": 123456789, "properties": {"nickname": "형인"}}

    monkeypatch.setattr("app.api.routes.auth.httpx.post", lambda *a, **kw: FakeTokenResponse())
    monkeypatch.setattr("app.api.routes.auth.httpx.get", lambda *a, **kw: FakeMeResponse())

    client.cookies.set("oauth_state", "state-k")
    response = client.get(
        "/auth/kakao/callback", params={"code": "c", "state": "state-k"}, follow_redirects=False
    )
    assert response.status_code == 307
    location = response.headers["location"]
    assert location.startswith("/app#token=")
    assert "provider=kakao" in location

    token = location.split("token=")[1].split("&")[0]
    user_id = decode_token(token)
    user = crud.get_or_create_social_user(db, "kakao", "123456789")
    assert user.id == user_id
    assert user.nickname == "형인"


def test_kakao_login_disabled_without_config(client):
    assert client.get("/auth/kakao/login", follow_redirects=False).status_code == 503


def test_google_callback_rejects_wrong_audience(client, db, google_configured, monkeypatch):
    # aud 가 다른 클라이언트의 id_token — 채널만 믿고 클레임 검증을 안 하면 뚫리는 지점
    id_token = pyjwt.encode(
        {"sub": "x", "aud": "other-client", "iss": "https://accounts.google.com"}, "unused", algorithm="HS256"
    )

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"id_token": id_token}

    monkeypatch.setattr("app.api.routes.auth.httpx.post", lambda *a, **kw: FakeResponse())
    client.cookies.set("oauth_state", "s")
    response = client.get(
        "/auth/google/callback", params={"code": "c", "state": "s"}, follow_redirects=False
    )
    assert response.status_code == 502
