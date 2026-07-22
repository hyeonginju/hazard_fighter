"""
긴급재난문자 클라이언트 테스트.
샘플은 2026-07-22 실 응답(프로브)에서 가져온 까다로운 케이스들.
실제 API 는 호출하지 않고 httpx.get 을 monkeypatch 로 가짜 응답으로 바꿔 검증한다.
"""
from datetime import timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.ingestion.safety_disaster import (
    SafetyDisasterMessageClient,
    _parse_crt_dt,
    _parse_regions,
)
from app.models import Event, Notification
from app.models.enums import AgeGroup, EventType
from app.services.ingest import run_ingestion_cycle


# --- 지역 파싱 (RCPTN_RGN_NM) -------------------------------------------------

def test_parse_regions_single_sigungu():
    assert _parse_regions("서울특별시 노원구 ") == [("서울특별시", "노원구")]


def test_parse_regions_sido_only_becomes_jeonche():
    # 시도만 온 경우 → sigungu='전체' (특보 소스와 동일 규칙)
    assert _parse_regions("울산광역시") == [("울산광역시", "전체")]


def test_parse_regions_keeps_si_gu_compound():
    # '고양시 덕양구' 처럼 시+구 복합은 통째로 유지해야 시군구 매칭이 맞는다
    assert _parse_regions("경기도 고양시 덕양구 ") == [("경기도", "고양시 덕양구")]


def test_parse_regions_drops_dong_level():
    # '강남구 역삼동' → 동 단위는 버리고 '강남구'로 (구독은 시군구 단위)
    assert _parse_regions("서울특별시 강남구 역삼동") == [("서울특별시", "강남구")]


def test_parse_regions_splits_multiple_and_dedupes():
    parsed = _parse_regions("경기도 고양시 덕양구 ,경기도 고양시 일산동구 ")
    assert ("경기도", "고양시 덕양구") in parsed
    assert ("경기도", "고양시 일산동구") in parsed
    # 쉼표 중복은 1건으로
    assert _parse_regions("경기도 임진강 ,경기도 임진강") == [("경기도", "임진강")]


def test_parse_crt_dt():
    dt = _parse_crt_dt("2026/07/22 11:00:14")
    assert dt.year == 2026 and dt.hour == 11 and dt.minute == 0
    assert dt.utcoffset() is not None  # timezone-aware (KST)


# --- live fetch: 필터링 + 최신 페이지 + 지역 확장 -----------------------------

class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def _fake_get_factory(rows):
    """numOfRows<=1 이면 총건수만, 아니면 rows 를 반환하는 가짜 httpx.get."""
    def fake_get(url, params=None, timeout=None, follow_redirects=None):
        params = params or {}
        body = [] if int(params.get("numOfRows", 0)) <= 1 else rows
        return _FakeResp({"header": {"resultCode": "00"}, "totalCount": len(rows), "body": body})
    return fake_get


_ROWS = [
    {"SN": 1, "MSG_CN": "(폭염) 폭염주의보 발효 중. 온열질환 유의.",
     "RCPTN_RGN_NM": "울산광역시", "CRT_DT": "2026/07/22 11:00:14",
     "DST_SE_NM": "폭염", "EMRG_STEP_NM": "안전안내"},
    {"SN": 2, "MSG_CN": "[서울경찰청] 노원구에서 실종된 OOO씨를 찾습니다",
     "RCPTN_RGN_NM": "서울특별시 노원구 ", "CRT_DT": "2026/07/22 11:01:00",
     "DST_SE_NM": "기타", "EMRG_STEP_NM": "안전안내"},
    {"SN": 3, "MSG_CN": "고양시 하천 급증. 저지대 대피.",
     "RCPTN_RGN_NM": "경기도 고양시 덕양구 ,경기도 고양시 일산동구 ",
     "CRT_DT": "2026/07/22 11:02:00", "DST_SE_NM": "호우", "EMRG_STEP_NM": "안전안내"},
]


def test_live_fetch_filters_non_hazard_and_expands_regions(monkeypatch):
    monkeypatch.setattr("app.ingestion.safety_disaster.httpx.get", _fake_get_factory(_ROWS))

    client = SafetyDisasterMessageClient(api_key="TEST")
    events = client.fetch()

    # '기타'(실종자)는 제외, 폭염 1지역 + 호우 2지역 = 3건
    assert len(events) == 3
    assert all(e.raw_payload.get("DST_SE_NM") != "기타" for e in events)
    assert all(e.event_type == EventType.DISASTER_MESSAGE for e in events)

    regions = {(e.region_sido, e.region_sigungu) for e in events}
    assert ("울산광역시", "전체") in regions
    assert ("경기도", "고양시 덕양구") in regions
    assert ("경기도", "고양시 일산동구") in regions


def test_live_fetch_empty_day_returns_nothing(monkeypatch):
    monkeypatch.setattr("app.ingestion.safety_disaster.httpx.get", _fake_get_factory([]))
    client = SafetyDisasterMessageClient(api_key="TEST")
    assert client.fetch() == []


# --- 파이프라인 통합: 재난문자 → broadcast/MEDIUM 알림 -------------------------

@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def test_disaster_message_creates_broadcast_notification(db):
    # mock 재난문자는 '충청북도 청주시 흥덕구'에 호우 재난문자를 발생시킨다.
    # 같은 지역 구독자가 있으면 위험엔진 재판정 없이 broadcast/MEDIUM 알림이 나와야 한다.
    user = crud.get_or_create_user(db, "test@example.com")
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "충청북도", "청주시 흥덕구", None)
    crud.create_subscription(db, user, person.id, region.id)

    run_ingestion_cycle(db)

    notifs = list(db.scalars(select(Notification)))
    disaster = [
        n for n in notifs
        if db.get(Event, n.event_id).event_type == EventType.DISASTER_MESSAGE
    ]
    assert len(disaster) == 1
    assert disaster[0].risk_level == "MEDIUM"
    assert disaster[0].risk_source == "broadcast"
    # LLM 키가 없으니 템플릿 fallback — 당국 원문(MSG_CN)이 문구에 그대로 들어간다
    assert "긴급재난문자" in disaster[0].message
    assert "호우경보" in disaster[0].message
