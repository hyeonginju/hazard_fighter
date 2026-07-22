"""
지역 이름 기반 매칭(regions_match) 테스트.

배경: 사용자는 행정구역명(부산광역시 해운대구, 경주시)을 구독하지만 공공 API 는
예보구역명(부산 전체, 경주남부)으로 이벤트를 만든다. region_id 동일성 대신
시도 표준화 + '전체' + 접두어 비교로 매칭한다.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.crud import canonical_sido, regions_match
from app.database import Base
from app.models import Notification, Region
from app.models.enums import AgeGroup, EventSource, EventType, Severity


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _region(sido, sigungu):
    return Region(sido=sido, sigungu=sigungu)


# --- canonical_sido: 행정구역명 ↔ 기상청 표기 ---------------------------------

@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("부산광역시", "부산"),
        ("전북특별자치도", "전북자치도"),
        ("전라북도", "전북자치도"),
        ("제주특별자치도", "제주도"),
        ("세종특별자치시", "세종"),
        ("강원특별자치도", "강원도"),
        ("충청북도", "충청북도"),
    ],
)
def test_canonical_sido_equates_variants(a, b):
    assert canonical_sido(a) == canonical_sido(b)


def test_canonical_sido_distinguishes_different_sido():
    assert canonical_sido("충청북도") != canonical_sido("충청남도")
    assert canonical_sido("경상북도") != canonical_sido("전라북도")


# --- regions_match ------------------------------------------------------------

def test_match_suffix_variants():
    # 사용자 '광양시' ↔ 기상청 '광양'
    assert regions_match(_region("전라남도", "광양시"), _region("전라남도", "광양"))


def test_match_forecast_zone_split_by_prefix():
    # 사용자 '경주시' ↔ 기상청 분할 구역 '경주남부'
    assert regions_match(_region("경상북도", "경주시"), _region("경상북도", "경주남부"))


def test_match_sido_wide_warning():
    # 기상청 '부산 전체' 특보는 부산의 어느 구 구독에도 매칭
    assert regions_match(_region("부산광역시", "해운대구"), _region("부산", "전체"))


def test_match_whole_sido_subscription():
    # '전체' 구독은 그 시도의 모든 이벤트에 매칭
    assert regions_match(_region("경상남도", "전체"), _region("경상남도", "거창남부"))


def test_no_match_same_sigungu_name_in_other_sido():
    # 동명이지역: 경남 고성 vs 강원 고성 — 시도에서 걸러짐
    assert not regions_match(_region("경상남도", "고성군"), _region("강원특별자치도", "고성"))


def test_no_match_unrelated_sigungu():
    assert not regions_match(_region("경기도", "양주시"), _region("경기도", "남양주"))


# --- 파이프라인 통합: 행정구역명 구독이 예보구역명 이벤트와 매칭돼 알림 생성 ----

def test_pipeline_matches_admin_name_subscription(db):
    from app.services.ingest import _evaluate_and_notify, _store_event
    from app.ingestion.base import NormalizedEvent

    user = crud.get_or_create_user(db, "match@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    # 사용자는 행정구역명으로 구독
    region = crud.get_or_create_region(db, "경상북도", "경주시", None)
    crud.create_subscription(db, user, person.id, region.id)

    # 공공 API 는 예보구역명으로 이벤트를 만든다.
    # 폭염×고령은 Layer 1 매트릭스에 있는 조합이라 LLM 없이도 HIGH 알림이 나온다.
    event, created = _store_event(
        db,
        NormalizedEvent(
            source=EventSource.KMA_WARNING,
            event_type=EventType.HEATWAVE,
            region_sido="경상북도",
            region_sigungu="경주남부",
            severity=Severity.WARNING,
            raw_payload={},
            occurred_at=datetime.now(timezone.utc),
        ),
    )
    assert created
    assert _evaluate_and_notify(db, event) == 1
    assert db.scalar(select(Notification)) is not None
