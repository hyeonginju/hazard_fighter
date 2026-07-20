"""
Layer 2 — LLM 위험도 보조 판단 테스트.

시나리오: 한파특보 + 특이 태그 없는 '성인' — Layer 1 규칙 매트릭스에 없는 케이스.
LLM 판단 → ai_risk_logs 기록 → MEDIUM/HIGH 면 알림(risk_source=ai) 생성까지 검증.
실제 LLM 호출은 없다 (llm 모듈 httpx monkeypatch).
"""
from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.config import get_settings
from app.database import Base
from app.models import AIRiskLog, Event, Notification
from app.models.enums import AgeGroup, EventSource, EventType, Severity
from app.services import llm as llm_mod
from app.services import risk_ai
from app.services.ingest import _notify_subscription_for_event


@pytest.fixture(autouse=True)
def clear_state(monkeypatch):
    """LLM 쿨다운·판단 캐시 격리 + 가짜 키 설정 (Layer2 는 LLM 필수)."""
    llm_mod._cooldowns.clear()
    risk_ai._decision_cache.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    get_settings.cache_clear()
    yield
    llm_mod._cooldowns.clear()
    risk_ai._decision_cache.clear()
    monkeypatch.setenv("OPENAI_API_KEY", "")
    get_settings.cache_clear()


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _setup_unmatched_case(db, email="layer2@example.com", label="아버지"):
    """Layer1 규칙에 안 걸리는 조합: 한파특보 + 성인 + 태그 없음."""
    user = crud.get_or_create_user(db, email)
    person = crud.create_person(db, user, label, AgeGroup.ADULT, [])
    region = crud.get_or_create_region(db, "강원특별자치도", "평창", None)
    subscription = crud.create_subscription(db, user, person.id, region.id)
    event = Event(
        source=EventSource.KMA_WARNING,
        event_type=EventType.COLD_WAVE,
        region_id=region.id,
        severity=Severity.WARNING,
        raw_payload={},
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, subscription, person


def _llm_response(url: str, text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": text}}]},
        request=httpx.Request("POST", url),
    )


def test_layer2_creates_ai_notification_and_log(db, monkeypatch):
    event, subscription, person = _setup_unmatched_case(db)
    monkeypatch.setattr(
        llm_mod.httpx, "post",
        lambda url, **kw: _llm_response(url, "MEDIUM\n한파경보 시 성인도 장시간 야외 노출은 주의가 필요합니다."),
    )

    created = _notify_subscription_for_event(db, event, subscription)
    db.commit()

    assert created is True
    notification = db.scalar(select(Notification))
    assert notification.risk_level == "MEDIUM"
    assert notification.risk_source == "ai"  # matrix 가 아니라 Layer2 판단

    log = db.scalar(select(AIRiskLog))
    assert log.risk_level == "MEDIUM"
    assert "야외 노출" in log.rationale
    assert log.event_id == event.id and log.subscription_id == subscription.id


def test_layer2_low_logs_but_no_notification(db, monkeypatch):
    event, subscription, person = _setup_unmatched_case(db)
    monkeypatch.setattr(
        llm_mod.httpx, "post",
        lambda url, **kw: _llm_response(url, "LOW\n건강한 성인에게 특별한 위험은 없습니다."),
    )

    created = _notify_subscription_for_event(db, event, subscription)
    db.commit()

    assert created is False
    assert db.scalar(select(Notification)) is None  # 알림은 없고
    assert db.scalar(select(AIRiskLog)) is not None  # 판단 기록은 남는다 (감사용)


def test_layer2_llm_failure_holds_judgement(db, monkeypatch):
    event, subscription, person = _setup_unmatched_case(db)

    def fail(url, **kw):
        raise RuntimeError("llm down")

    monkeypatch.setattr(llm_mod.httpx, "post", fail)

    created = _notify_subscription_for_event(db, event, subscription)
    db.commit()

    assert created is False
    assert db.scalar(select(Notification)) is None
    assert db.scalar(select(AIRiskLog)) is None  # 판단 자체를 보류 — 임의 판정 금지


def test_layer2_decision_cache_saves_llm_calls(db, monkeypatch):
    """같은 (이벤트유형·등급·나이대·태그) 조합이면 두 번째 인물부턴 LLM 호출 없이 캐시 사용."""
    event, sub1, _ = _setup_unmatched_case(db, email="cache1@example.com", label="아버지")
    # 같은 프로필 조합의 두 번째 구독자 (다른 사용자·인물)
    user2 = crud.get_or_create_user(db, "cache2@example.com")
    person2 = crud.create_person(db, user2, "삼촌", AgeGroup.ADULT, [])
    sub2 = crud.create_subscription(db, user2, person2.id, event.region_id)

    calls = []

    def fake_post(url, **kw):
        calls.append(url)
        return _llm_response(url, "MEDIUM\n주의 필요.")

    monkeypatch.setattr(llm_mod.httpx, "post", fake_post)

    _notify_subscription_for_event(db, event, sub1)
    _notify_subscription_for_event(db, event, sub2)
    db.commit()

    # 위험도 판단 LLM 호출은 1번만 (문구 생성 호출은 별개로 2번)
    risk_calls = [u for u in calls]
    assert len(risk_calls) == 3  # 판단 1 + 문구 2
    logs = list(db.scalars(select(AIRiskLog)))
    assert len(logs) == 2  # 캐시를 써도 기록은 구독별로 남는다


def test_layer2_malformed_response_holds_judgement(db, monkeypatch):
    event, subscription, person = _setup_unmatched_case(db)
    monkeypatch.setattr(
        llm_mod.httpx, "post",
        lambda url, **kw: _llm_response(url, "위험도는 보통입니다"),  # HIGH/MEDIUM/LOW 없음
    )

    created = _notify_subscription_for_event(db, event, subscription)
    db.commit()

    assert created is False
    assert db.scalar(select(AIRiskLog)) is None
