"""
알림 dedupe 테스트 — 예보구역 분할로 인한 중복 푸시 방지.

배경 (2026-07-22 실기기 검증에서 발견): 기상특보 통보문 하나가 예보구역 수만큼
이벤트로 쪼개져 들어온다 (경주 폭염 → 경주남부/서부/동부/중북부 = 4건).
분할 이벤트들은 같은 통보문에서 나와 (source, 종류, 등급, 발표시각)이 전부 같으므로,
같은 보호 대상에게는 이 시그니처당 알림 1건만 만든다.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.ingestion.base import NormalizedEvent
from app.models import Notification
from app.models.enums import AgeGroup, EventSource, EventType, Severity
from app.services.ingest import _evaluate_and_notify, _store_event, backfill_subscription

ISSUED_AT = datetime(2026, 7, 22, 2, 0, tzinfo=timezone.utc)  # 통보문 발표시각


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _warning_event(db, sigungu, occurred_at=ISSUED_AT):
    """폭염 경보 이벤트 저장. 폭염×고령은 Layer 1 매트릭스 조합이라 LLM 없이 HIGH."""
    event, created = _store_event(
        db,
        NormalizedEvent(
            source=EventSource.KMA_WARNING,
            event_type=EventType.HEATWAVE,
            region_sido="경상북도",
            region_sigungu=sigungu,
            severity=Severity.WARNING,
            raw_payload={},
            occurred_at=occurred_at,
        ),
    )
    assert created
    return event


def _subscribe(db, email, label, sido, sigungu):
    user = crud.get_or_create_user(db, email)
    person = crud.create_person(db, user, label, AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, sido, sigungu, None)
    return crud.create_subscription(db, user, person.id, region.id)


def _notification_count(db):
    return db.scalar(select(func.count()).select_from(Notification))


def test_split_zones_create_single_notification(db):
    # 경주시 구독 하나 — 같은 통보문의 분할 구역 4건이 들어와도 알림은 1건
    _subscribe(db, "dedupe@example.com", "어머니", "경상북도", "경주시")

    created = sum(
        _evaluate_and_notify(db, _warning_event(db, z))
        for z in ["경주남부", "경주서부", "경주동부", "경주중북부"]
    )

    assert created == 1
    assert _notification_count(db) == 1


def test_new_bulletin_creates_new_notification(db):
    # 발표시각이 다르면 새 통보문 — 다시 알림이 나가야 한다 (해제 후 재발효 등)
    _subscribe(db, "dedupe@example.com", "어머니", "경상북도", "경주시")

    assert _evaluate_and_notify(db, _warning_event(db, "경주남부")) == 1
    later = _warning_event(db, "경주남부", occurred_at=ISSUED_AT + timedelta(hours=6))
    assert _evaluate_and_notify(db, later) == 1
    assert _notification_count(db) == 2


def test_dedupe_is_per_person(db):
    # 보호 대상이 다르면 각자 1건씩 — dedupe 키는 (보호 대상, 통보문 시그니처)
    _subscribe(db, "a@example.com", "어머니", "경상북도", "경주시")
    _subscribe(db, "b@example.com", "아버지", "경상북도", "경주시")

    created = sum(
        _evaluate_and_notify(db, _warning_event(db, z)) for z in ["경주남부", "경주서부"]
    )

    assert created == 2
    assert _notification_count(db) == 2


def test_same_person_overlapping_subscriptions(db):
    # 한 보호 대상이 겹치는 구독 둘(경주시 + 경북 전체)을 가져도 이벤트 하나엔 알림 1건
    user = crud.get_or_create_user(db, "overlap@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    for sigungu in ["경주시", "전체"]:
        region = crud.get_or_create_region(db, "경상북도", sigungu, None)
        crud.create_subscription(db, user, person.id, region.id)

    assert _evaluate_and_notify(db, _warning_event(db, "경주남부")) == 1
    assert _notification_count(db) == 1


def test_disaster_message_not_deduped(db):
    # 재난문자는 같은 시각이라도 문자 내용이 제각각 — dedupe 미적용 (기상특보 한정)
    _subscribe(db, "dm@example.com", "어머니", "전라남도", "전체")

    for sigungu in ["순천", "여수"]:
        event, created = _store_event(
            db,
            NormalizedEvent(
                source=EventSource.DISASTER_MESSAGE,
                event_type=EventType.DISASTER_MESSAGE,
                region_sido="전라남도",
                region_sigungu=sigungu,
                severity=Severity.WARNING,
                raw_payload={"MSG_CN": f"{sigungu} 안전 안내"},
                occurred_at=ISSUED_AT,
            ),
        )
        assert created
        assert _evaluate_and_notify(db, event) == 1

    assert _notification_count(db) == 2


def test_backfill_dedupes_split_zones(db):
    # 소급 평가(backfill) 경로도 같은 로직을 타므로 분할 구역이 1건으로 합쳐져야 한다
    for z in ["경주남부", "경주서부", "경주동부"]:
        _warning_event(db, z)

    subscription = _subscribe(db, "backfill@example.com", "어머니", "경상북도", "경주시")
    assert backfill_subscription(db, subscription) == 1
    assert _notification_count(db) == 1
