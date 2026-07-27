"""
수집 엔드포인트 보호 테스트 (POST /events/ingest).

배경 (2026-07-27): 이 엔드포인트는 무인증이었다. 로컬에서는 "내가 연타하는 것"만
문제라 시간 가드로 충분했지만, 공개 배포되면 주소를 아는 누구나 우리 공공 API 쿼터와
LLM 비용을 태울 수 있다. 배포 후엔 외부 스케줄러만 이 문을 통과해야 한다.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings
from app.database import Base, get_db
from app.main import app

TOKEN = "test-ingest-token"  # conftest 가 INGEST_TOKEN 으로 넣는 값


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    app.dependency_overrides[get_db] = lambda: session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        session.close()


def test_ingest_without_token_is_rejected(client):
    response = client.post("/events/ingest")
    assert response.status_code == 401


def test_ingest_with_wrong_token_is_rejected(client):
    response = client.post("/events/ingest", headers={"X-Ingest-Token": "wrong-token"})
    assert response.status_code == 401


def test_ingest_with_non_ascii_token_is_rejected(client):
    """비ASCII 바이트가 와도 401 이어야 한다 (500 이 아니라).

    HTTP 헤더는 latin-1 로 디코드되므로 이런 값이 실제로 도착할 수 있고,
    secrets.compare_digest 에 str 로 넘기면 TypeError → 500 이 된다. bytes 로 비교해 막았다.
    """
    response = client.post("/events/ingest", headers={"X-Ingest-Token": "틀린토큰".encode("utf-8")})
    assert response.status_code == 401


def test_ingest_with_correct_token_runs(client):
    response = client.post("/events/ingest", headers={"X-Ingest-Token": TOKEN})
    assert response.status_code == 200
    body = response.json()
    assert body["skipped"] is False
    assert body["events_ingested"] >= 3  # mock 소스들


def test_ingest_closed_when_token_not_configured(client, monkeypatch):
    """fail-closed: 토큰을 설정하지 않았으면 열어두지 않고 503.

    "설정을 잊으면 열려 있는" 보호는 없는 것보다 위험하다는 판단.
    """
    monkeypatch.setenv("INGEST_TOKEN", "")
    get_settings.cache_clear()
    try:
        response = client.post("/events/ingest", headers={"X-Ingest-Token": TOKEN})
        assert response.status_code == 503
    finally:
        get_settings.cache_clear()
