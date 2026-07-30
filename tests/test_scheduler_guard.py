"""
수집 중복 실행 가드 + 스케줄러 설정 테스트.
배경: API 호출량 예산 분석(학습노트 2026-07-20) — 수동 ingest 연타나
스케줄러-수동 겹침이 공공 API 호출 낭비로 이어지지 않아야 한다.

2026-07-27: 가드 상태가 모듈 전역 → ingest_runs 테이블로 이동(다중 인스턴스 대응).
그래서 테스트 간 격리 fixture 도 필요 없어졌다 — DB fixture 가 매 테스트마다 새 DB 다.
"""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import IngestRun
from app.services.ingest import run_ingestion_cycle_guarded


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
    # 이력의 시작 시각을 과거로 밀어서 "3분 경과" 상황을 흉내
    run = db.scalars(select(IngestRun)).one()
    run.started_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    db.commit()

    result = run_ingestion_cycle_guarded(db, min_gap_minutes=3)
    assert result["skipped"] is False


def test_run_history_is_recorded(db):
    """이력이 남아야 로그 grep 없이 "언제 몇 건" 을 조회할 수 있다."""
    result = run_ingestion_cycle_guarded(db, min_gap_minutes=3)

    run = db.scalars(select(IngestRun)).one()
    assert run.finished_at is not None  # 정상 종료 (NULL 이면 도중에 죽은 사이클)
    assert run.events_ingested == result["events_ingested"]
    assert run.notifications_created == result["notifications_created"]


def test_guard_state_survives_new_session(db):
    """가드가 프로세스 메모리가 아니라 DB 에 있는지 — 다중 인스턴스 대응의 핵심.

    같은 DB 에 붙은 다른 세션(= 다른 인스턴스를 흉내)이 앞선 실행을 보고 스킵해야 한다.
    """
    assert run_ingestion_cycle_guarded(db, min_gap_minutes=3)["skipped"] is False

    other_session = sessionmaker(bind=db.get_bind())()
    try:
        assert run_ingestion_cycle_guarded(other_session, min_gap_minutes=3)["skipped"] is True
    finally:
        other_session.close()


def test_cycle_logs_summary(db, caplog):
    """사이클 결과가 로그로 남는지 — Cloud Scheduler 로 옮긴 뒤엔 응답 dict 를 아무도 안 본다.

    Scheduler 는 HTTP 응답을 버리므로, 프로덕션에서 "몇 건 수집했고 몇 건 보냈나" 를
    확인할 수 있는 유일한 창구가 이 로그 한 줄이다.
    """
    with caplog.at_level(logging.INFO, logger="app.services.ingest"):
        run_ingestion_cycle_guarded(db, min_gap_minutes=3)

    assert any("수집 사이클 완료" in r.getMessage() for r in caplog.records)


def test_skipped_cycle_logs_reason(db, caplog):
    run_ingestion_cycle_guarded(db, min_gap_minutes=3)

    with caplog.at_level(logging.INFO, logger="app.services.ingest"):
        run_ingestion_cycle_guarded(db, min_gap_minutes=3)

    assert any("수집 사이클 스킵" in r.getMessage() for r in caplog.records)


def test_scheduler_disabled_in_tests():
    """conftest 가 SCHEDULER_ENABLED=0 을 강제하는지 (테스트 중 백그라운드 폴링 방지)."""
    from app.config import get_settings

    assert get_settings().scheduler_enabled is False
