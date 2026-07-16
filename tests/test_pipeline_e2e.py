"""
전체 파이프라인 통합 스모크 테스트 — DB 서버 없이 in-memory SQLite로 돈다.
project-spec.md 8절(아키텍처) 흐름을 실제 DB 왕복으로 검증:
  사용자/인물/지역/구독 생성 → ingest 사이클(mock 데이터) → events 저장 → Layer1 위험도 평가 → notifications 생성

운영은 PostgreSQL이지만, 모델이 다이얼렉트 호환 타입(app/models/types.py)이라 SQLite에서도 동일 로직이 돈다.
"""
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import Event, Notification, PersonTag
from app.models.enums import AgeGroup, ConsiderationTag, EventType
from app.services.ingest import run_ingestion_cycle


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()


def _setup_subscription(db, sido, sigungu, age_group, tags):
    from app import crud

    user = crud.get_or_create_user(db, "test@example.com")
    person = crud.create_person(db, user, "부모님", age_group, tags)
    region = crud.get_or_create_region(db, sido, sigungu, None)
    crud.create_subscription(db, user, person.id, region.id)
    return user, person, region


def test_all_tables_created_on_sqlite(db):
    # 12개 테이블이 다이얼렉트 호환 타입으로 SQLite에도 문제없이 생성되는지
    assert len(Base.metadata.tables) == 12


def test_full_ingest_cycle_creates_events(db):
    # 구독이 없어도 ingest는 이벤트를 저장해야 한다 (mock 소스 3개)
    result = run_ingestion_cycle(db)
    assert result["events_ingested"] >= 3
    events = list(db.scalars(select(Event)))
    assert len(events) >= 3


def test_flood_warning_matched_region_creates_high_risk_notification(db):
    # hrfco mock은 "충청북도 청주시 흥덕구"에 홍수경보(WARNING)를 발생시킨다.
    # 같은 지역을 구독한 인물이 있으면 Layer1 규칙상 전원 HIGH → 알림 생성돼야 한다.
    _setup_subscription(db, "충청북도", "청주시 흥덕구", AgeGroup.ADULT, [])

    run_ingestion_cycle(db)

    notifications = list(db.scalars(select(Notification)))
    flood_notifs = [
        n for n in notifications
        if db.get(Event, n.event_id).event_type == EventType.FLOOD_WARNING
    ]
    assert len(flood_notifs) >= 1
    assert flood_notifs[0].risk_level == "HIGH"
    assert flood_notifs[0].risk_source == "matrix"


def test_heatwave_senior_gets_notification(db):
    # kma_warning mock은 "대전광역시 유성구"에 폭염경보를 발생시킨다.
    # 고령 인물 구독 시 HIGH 알림이 생성돼야 한다.
    _setup_subscription(db, "대전광역시", "유성구", AgeGroup.SENIOR, [])

    run_ingestion_cycle(db)

    notifications = list(db.scalars(select(Notification)))
    heat_notifs = [
        n for n in notifications
        if db.get(Event, n.event_id).event_type == EventType.HEATWAVE
    ]
    assert len(heat_notifs) >= 1
    assert heat_notifs[0].risk_level == "HIGH"


def test_person_tags_persist_and_roundtrip(db):
    # 태그가 실제로 DB에 저장되고 다시 읽히는지 (JSON/ARRAY variant 포함 왕복 확인)
    _setup_subscription(
        db, "서울특별시", "강남구", AgeGroup.ADULT, [ConsiderationTag.DRIVER, ConsiderationTag.OUTDOOR_COMMUTE]
    )
    tags = list(db.scalars(select(PersonTag)))
    stored = {t.tag for t in tags}
    assert ConsiderationTag.DRIVER in stored
    assert ConsiderationTag.OUTDOOR_COMMUTE in stored
