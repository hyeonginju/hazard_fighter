"""
FCM 웹푸시 발송 + dispatch 단계 테스트.
실제 FCM/네트워크 없이 검증한다:
- 미설정(mock) 모드는 자격증명이 없으니 자동으로 no-op.
- 실발송 경로는 _access_token 과 httpx.post 를 monkeypatch 로 가짜 응답으로 바꿔 검증.
- dispatch 는 클라이언트를 주입받아 발송 결과를 시나리오별로 흉내낸다.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.models import DeviceToken, Event, Notification
from app.models.enums import (
    AgeGroup,
    DevicePlatform,
    EventSource,
    EventType,
    NotificationChannel,
    RiskLevel,
    RiskSource,
    Severity,
)
from app.services.dispatch import dispatch_unsent_notifications
from app.services.push import FcmClient, PushResult


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


def _make_notification(db, user_email="test@example.com") -> Notification:
    """구독 1개 + 이벤트 1개 + 미발송 알림 1개를 만들어 반환."""
    user = crud.get_or_create_user(db, user_email)
    person = crud.create_person(db, user, "어머니", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "충청북도", "청주시 흥덕구", None)
    subscription = crud.create_subscription(db, user, person.id, region.id)
    event = Event(
        source=EventSource.KMA_WARNING,
        event_type=EventType.HEAVY_RAIN,
        region_id=region.id,
        severity=Severity.WARNING,
        raw_payload={},
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    notif = Notification(
        subscription_id=subscription.id,
        event_id=event.id,
        risk_level=RiskLevel.HIGH,
        risk_source=RiskSource.MATRIX,
        message="호우경보 발효 — 저지대 주차 피하세요.",
        channel=NotificationChannel.WEB_PUSH,
    )
    db.add(notif)
    db.commit()
    db.refresh(notif)
    return notif


# --- FcmClient: 자격증명 유무에 따른 분기 ------------------------------------

def test_fcm_client_mock_when_not_configured():
    client = FcmClient(project_id=None, credentials_file=None)
    assert client.enabled is False
    result = client.send("some-token", "제목", "본문")
    assert result.ok is True
    assert result.status == "mock"


class _FakeResp:
    def __init__(self, status_code, text=""):
        self.status_code = status_code
        self.text = text


def test_fcm_client_send_success(monkeypatch):
    client = FcmClient(project_id="proj", credentials_file="/x/sa.json")
    assert client.enabled is True
    monkeypatch.setattr(client, "_access_token", lambda: "ya29.fake")
    captured = {}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return _FakeResp(200)

    monkeypatch.setattr("app.services.push.httpx.post", fake_post)

    result = client.send("dev-token", "제목", "본문")
    assert result.ok is True and result.status == "sent"
    assert "projects/proj/messages:send" in captured["url"]
    assert captured["headers"]["Authorization"] == "Bearer ya29.fake"
    assert captured["json"]["message"]["token"] == "dev-token"


def test_fcm_client_invalid_token_on_404(monkeypatch):
    client = FcmClient(project_id="proj", credentials_file="/x/sa.json")
    monkeypatch.setattr(client, "_access_token", lambda: "tok")
    monkeypatch.setattr("app.services.push.httpx.post",
                        lambda *a, **k: _FakeResp(404, '{"error":{"status":"NOT_FOUND"}}'))
    result = client.send("dead-token", "t", "b")
    assert result.ok is False and result.status == "invalid_token"


def test_fcm_client_transient_error_on_500(monkeypatch):
    client = FcmClient(project_id="proj", credentials_file="/x/sa.json")
    monkeypatch.setattr(client, "_access_token", lambda: "tok")
    monkeypatch.setattr("app.services.push.httpx.post", lambda *a, **k: _FakeResp(503, "unavailable"))
    result = client.send("token", "t", "b")
    assert result.ok is False and result.status == "error"


# --- 디바이스 토큰 등록: 멱등 ------------------------------------------------

def test_register_device_token_is_idempotent(db):
    user = crud.get_or_create_user(db, "a@example.com")
    t1 = crud.register_device_token(db, user, "fcm-abc", DevicePlatform.WEB)
    t2 = crud.register_device_token(db, user, "fcm-abc", DevicePlatform.ANDROID)
    # 같은 토큰 재등록 → 새 행이 아니라 기존 행 갱신
    assert t1.id == t2.id
    assert t2.platform == DevicePlatform.ANDROID
    all_tokens = list(db.scalars(select(DeviceToken)))
    assert len(all_tokens) == 1


# --- dispatch: 발송/미발송/멱등/죽은 토큰 정리 --------------------------------

class _StubClient:
    """dispatch 테스트용. 토큰별 반환 상태를 지정할 수 있는 가짜 FcmClient."""

    def __init__(self, enabled=True, result=None):
        self.enabled = enabled
        self._result = result or PushResult(ok=True, status="sent")
        self.sent_calls = []

    def send(self, fcm_token, title, body):
        self.sent_calls.append((fcm_token, title, body))
        return self._result


def test_dispatch_sends_and_marks_sent_at(db):
    notif = _make_notification(db)
    user = crud.get_or_create_user(db, "test@example.com")
    crud.register_device_token(db, user, "fcm-abc", DevicePlatform.WEB)

    client = _StubClient()
    result = dispatch_unsent_notifications(db, client=client)

    assert result["sent"] == 1
    assert len(client.sent_calls) == 1
    # 제목에 위험도가 들어가고 본문은 문구 전체
    assert client.sent_calls[0][1] == "[HIGH] 명예소방관 안전 알림"
    db.refresh(notif)
    assert notif.sent_at is not None


def test_dispatch_skips_when_no_device_token(db):
    notif = _make_notification(db)  # 토큰 등록 안 함
    result = dispatch_unsent_notifications(db, client=_StubClient())
    assert result["sent"] == 0
    assert result["no_target"] == 1
    db.refresh(notif)
    assert notif.sent_at is None  # 다음 사이클 재시도 대상으로 남음


def test_dispatch_is_idempotent(db):
    _make_notification(db)
    user = crud.get_or_create_user(db, "test@example.com")
    crud.register_device_token(db, user, "fcm-abc", DevicePlatform.WEB)

    first = dispatch_unsent_notifications(db, client=_StubClient())
    second = dispatch_unsent_notifications(db, client=_StubClient())

    assert first["sent"] == 1
    assert second["sent"] == 0  # 이미 sent_at 찍힘 — 재발송 안 함
    assert second["unsent_seen"] == 0


def test_dispatch_removes_invalid_token(db):
    notif = _make_notification(db)
    user = crud.get_or_create_user(db, "test@example.com")
    crud.register_device_token(db, user, "dead-token", DevicePlatform.WEB)

    client = _StubClient(result=PushResult(ok=False, status="invalid_token"))
    result = dispatch_unsent_notifications(db, client=client)

    assert result["tokens_removed"] == 1
    assert result["failed"] == 1  # 유효 토큰 없어 발송 실패
    assert list(db.scalars(select(DeviceToken))) == []  # 죽은 토큰 정리됨
    db.refresh(notif)
    assert notif.sent_at is None  # 재시도 대상


def test_dispatch_mock_mode_still_delivers(db):
    """FCM 미설정(mock)이어도 토큰이 있으면 '발송했다 치고' sent_at 을 찍는다."""
    notif = _make_notification(db)
    user = crud.get_or_create_user(db, "test@example.com")
    crud.register_device_token(db, user, "fcm-abc", DevicePlatform.WEB)

    result = dispatch_unsent_notifications(db, client=FcmClient(None, None))

    assert result["mock"] is True
    assert result["sent"] == 1
    db.refresh(notif)
    assert notif.sent_at is not None


def test_run_ingestion_cycle_dispatches_to_registered_token(db):
    """end-to-end: hrfco mock(충청북도 청주시 흥덕구 홍수경보) → 같은 지역 구독자 +
    등록된 기기가 있으면, 한 사이클 안에서 알림 생성 후 발송(sent_at)까지 이뤄진다."""
    from app.services.ingest import run_ingestion_cycle

    user = crud.get_or_create_user(db, "flood@example.com")
    person = crud.create_person(db, user, "아버지", AgeGroup.SENIOR, [])
    region = crud.get_or_create_region(db, "충청북도", "청주시 흥덕구", None)
    crud.create_subscription(db, user, person.id, region.id)
    crud.register_device_token(db, user, "fcm-flood", DevicePlatform.WEB)

    result = run_ingestion_cycle(db)

    assert result["notifications_created"] >= 1
    assert result["notifications_sent"] >= 1
    # 발송된 알림은 sent_at 이 찍혀 있어야 한다
    sent = [n for n in db.scalars(select(Notification)) if n.sent_at is not None]
    assert len(sent) >= 1
