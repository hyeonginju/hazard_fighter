"""
특보 통보문 t6 파서 + 이벤트 중복 방지 테스트.
t6 샘플은 2026-07-17 실제 응답(debug_responses/kma_warnings_msg.json)에서 가져온 것.
"""
from datetime import datetime, timezone

from app.ingestion.kma_warnings import _parse_active_warnings, _split_top_level
from app.models.enums import Severity

# 실제 응답에서 나온 까다로운 케이스들을 전부 포함
REAL_T6 = (
    "o 호우주의보 : 충청남도(보령(도서제외), 보령도서)\r\n"
    "o 폭염주의보 : 전라남도(광양, 순천), 제주도(제주도산지, 추자도 제외)\r\n"
    "o 폭풍해일경보 : 경기도(시흥, 김포), 인천\r\n"
    "o 열대야주의보 : 제주도(제주시북부, 제주시동부)"
)


def test_split_top_level_respects_parens():
    assert _split_top_level("전라남도(광양, 순천), 인천") == ["전라남도(광양, 순천)", "인천"]
    assert _split_top_level("충청남도(보령(도서제외), 보령도서)") == ["충청남도(보령(도서제외), 보령도서)"]


def test_parse_real_t6_snapshot():
    parsed = _parse_active_warnings(REAL_T6)

    # 호우주의보: 중첩 괄호 한정어 '보령(도서제외)' → '보령' 으로 정규화
    assert ("호우", Severity.ADVISORY, "충청남도", "보령") in parsed
    assert ("호우", Severity.ADVISORY, "충청남도", "보령도서") in parsed

    # 폭염주의보: '추자도 제외' 는 발효 지역이 아니므로 빠져야 함
    assert ("폭염", Severity.ADVISORY, "전라남도", "광양") in parsed
    assert ("폭염", Severity.ADVISORY, "제주도", "제주도산지") in parsed
    assert not any(sig == "추자도 제외" for _, _, _, sig in parsed)

    # 폭풍해일경보: 등급이 '경보'로, 시도 단위 '인천' 은 sigungu='전체'
    assert ("폭풍해일", Severity.WARNING, "경기도", "시흥") in parsed
    assert ("폭풍해일", Severity.WARNING, "인천", "전체") in parsed

    # 열대야도 파서 레벨에서는 나온다 (MVP 범위 필터는 클라이언트 몫)
    assert ("열대야", Severity.ADVISORY, "제주도", "제주시북부") in parsed


def test_store_event_dedupes_identical_events(tmp_path):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import sessionmaker

    from app.database import Base
    from app.ingestion.base import NormalizedEvent
    from app.models import Event
    from app.models.enums import EventSource, EventType
    from app.services.ingest import _store_event

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine)()

    normalized = NormalizedEvent(
        source=EventSource.KMA_WARNING,
        event_type=EventType.HEATWAVE,
        severity=Severity.ADVISORY,
        region_sido="전라남도",
        region_sigungu="광양",
        occurred_at=datetime(2026, 7, 17, 16, 0, tzinfo=timezone.utc),
        raw_payload={"t": 1},
    )

    _, created_first = _store_event(db, normalized)
    _, created_second = _store_event(db, normalized)

    assert created_first is True
    assert created_second is False
    assert len(list(db.scalars(select(Event)))) == 1
