"""
수집 중복 실행 가드 + 스케줄러 설정 테스트.
배경: API 호출량 예산 분석(학습노트 2026-07-20) — 수동 ingest 연타나
스케줄러-수동 겹침이 공공 API 호출 낭비로 이어지지 않아야 한다.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.services import ingest as ingest_mod
from app.services.ingest import run_ingestion_cycle_guarded


@pytest.fixture(autouse=True)
def reset_guard():
    """가드 상태는 모듈 전역이라 테스트 간 격리 필요."""
    ingest_mod._last_cycle_at = None
    yield
    ingest_mod._last_cycle_at = None


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_first_run_executes(db):
    result = run_ingestion_cycle_guarded(db, min_gap_minutes=3)
    assert result["skipped"] is False
    assert result["events_ingested"] >= 3  # mock 소스 3개


def test_second_run_within_gap_is_skipped(db):
    first = run_ingestion_cycle_guarded(db, min_gap_minutes=3)
    second = run_ingestion_cycle_guarded(db, min_gap_minutes=3)

    assert first["skipped"] is False
    assert second["skipped"] is True
    assert "reason" in second and "last_cycle_at" in second


def test_run_after_gap_executes_again(db):
    run_ingestion_cycle_guarded(db, min_gap_minutes=3)
    # 마지막 실행 시각을 과거로 밀어서 "3분 경과" 상황을 흉내
    ingest_mod._last_cycle_at = datetime.now(timezone.utc) - timedelta(minutes=5)

    result = run_ingestion_cycle_guarded(db, min_gap_minutes=3)
    assert result["skipped"] is False


def test_scheduler_disabled_in_tests():
    """conftest 가 SCHEDULER_ENABLED=0 을 강제하는지 (테스트 중 백그라운드 폴링 방지)."""
    from app.config import get_settings

    assert get_settings().scheduler_enabled is False
