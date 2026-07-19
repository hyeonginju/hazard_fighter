"""
구독 소급 평가(backfill) + 지역명 정규화 테스트.
2026-07-17 실사용에서 발견한 "구독을 먼저 만들어야 알림이 생기는" 순서 문제의 해결 검증.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.models import Event, Notification
from app.models.enums import AgeGroup, EventSource, EventType, Severity
from app.services.ingest import backfill_subscription


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_event(db, region, event_type, severity, occurred_at):
    event = Event(
        source=EventSource.KMA_WARNING,
        event_type=event_type,
        region_id=region.id,
        severity=severity,
        raw_payload={},
        occurred_at=occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def test_backfill_creates_notification_for_existing_event(db):
    # 이벤트가 "먼저" 있고 구독을 "나중에" 만들어도 알림이 소급 생성돼야 한다
    user = crud.get_or_create_user(db, "backfill@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "전라남도", "광양", None)
    _make_event(db, region, EventType.HEATWAVE, Severity.ADVISORY, datetime.now(timezone.utc))

    subscription = crud.create_subscription(db, user, person.id, region.id)
    created = backfill_subscription(db, subscription)

    assert created == 1
    notifications = list(db.scalars(select(Notification)))
    assert len(notifications) == 1
    assert notifications[0].risk_level == "HIGH"  # 폭염 + 고령


def test_backfill_skips_old_events_and_does_not_duplicate(db):
    user = crud.get_or_create_user(db, "backfill2@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "전라남도", "순천", None)
    # 오래된 이벤트(창 밖) + 최근 이벤트(창 안)
    _make_event(db, region, EventType.HEATWAVE, Severity.ADVISORY,
                datetime.now(timezone.utc) - timedelta(days=10))
    _make_event(db, region, EventType.HEATWAVE, Severity.ADVISORY, datetime.now(timezone.utc))

    subscription = crud.create_subscription(db, user, person.id, region.id)
    first = backfill_subscription(db, subscription)
    second = backfill_subscription(db, subscription)  # 두 번 불러도 중복 알림 없어야 함

    assert first == 1  # 최근 이벤트만
    assert second == 0
    assert len(list(db.scalars(select(Notification)))) == 1


def test_region_name_normalization(db):
    # '광양시'로 만들어도 통보문의 '광양'과 같은 region 이어야 한다
    r1 = crud.get_or_create_region(db, "전라남도", "광양시", None)
    r2 = crud.get_or_create_region(db, "전라남도", "광양", None)
    assert r1.id == r2.id
    assert r1.sigungu == "광양"

    # 복합 표기는 건드리지 않는다
    r3 = crud.get_or_create_region(db, "충청북도", "청주시 흥덕구", None)
    assert r3.sigungu == "청주시 흥덕구"

    # 시도 단위 '전체' 도 그대로
    r4 = crud.get_or_create_region(db, "인천", "전체", None)
    assert r4.sigungu == "전체"


def test_create_subscription_is_idempotent(db):
    # 같은 (person, region) 구독을 두 번 만들어도 500 이 아니라 기존 구독 반환
    user = crud.get_or_create_user(db, "idem@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "전라남도", "광양", None)

    s1 = crud.create_subscription(db, user, person.id, region.id)
    s2 = crud.create_subscription(db, user, person.id, region.id)

    assert s1.id == s2.id
