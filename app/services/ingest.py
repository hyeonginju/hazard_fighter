"""
Phase 1 파이프라인 전체를 한 번 돌리는 오케스트레이션.
project-spec.md 8절(시스템 아키텍처) 흐름을 그대로 코드로 옮긴 것:
  ingestion -> events 저장 -> (지역 매칭된) 구독 조회 -> Layer1 위험도 평가 -> notifications 생성

Layer2(LLM 보조 판단·알림 문구 생성)와 실제 FCM 발송은 Phase 2 항목이라
지금은 risk_level이 안 잡히면 스킵하고, 메시지는 템플릿 문자열로 대신한다 (TODO 표시).
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.crud import get_or_create_region
from app.ingestion.base import NormalizedEvent
from app.ingestion.hrfco_flood import HrfcoFloodClient
from app.ingestion.kma_earthquake import KmaEarthquakeClient
from app.ingestion.kma_warnings import KmaWarningClient
from app.models import Event, Notification, Person, PersonTag, Subscription
from app.models.enums import NotificationChannel, RiskSource
from app.risk.matrix import evaluate_risk


def run_ingestion_cycle(db: Session) -> dict:
    """모든 소스에서 이벤트를 가져와 저장하고, 매칭되는 구독에 대해 위험도를 평가한다."""
    settings = get_settings()

    clients = [
        KmaWarningClient(settings.kma_warning_api_key),
        KmaEarthquakeClient(settings.kma_earthquake_api_key),
        HrfcoFloodClient(settings.hrfco_api_key),
    ]

    stored_events: list[Event] = []
    duplicates_skipped = 0
    errors: dict[str, str] = {}
    for client in clients:
        # 한 소스가 실패해도(API 형식 변경, 네트워크 등) 나머지 소스는 계속 처리한다.
        # 실패 내용은 응답의 errors 에 소스별로 담아 호출자가 바로 볼 수 있게 한다.
        try:
            for normalized in client.fetch():
                event, created = _store_event(db, normalized)
                if created:
                    stored_events.append(event)
                else:
                    duplicates_skipped += 1
        except Exception as e:  # noqa: BLE001 — 소스별 격리가 목적
            errors[str(client.source)] = f"{type(e).__name__}: {e}"

    notifications_created = 0
    for event in stored_events:  # 신규 이벤트만 평가 — 중복 알림 방지
        notifications_created += _evaluate_and_notify(db, event)

    return {
        "events_ingested": len(stored_events),
        "duplicates_skipped": duplicates_skipped,
        "notifications_created": notifications_created,
        "errors": errors,
    }


def _store_event(db: Session, normalized: NormalizedEvent) -> tuple[Event, bool]:
    """이벤트 저장. 이미 같은 이벤트가 있으면 재사용하고 created=False 반환.

    특보 통보문의 t6 는 "발효 중 특보 스냅샷"이라 같은 특보가 매 ingest 사이클 반복된다.
    (source, event_type, severity, region, occurred_at=발표시각) 이 모두 같으면 동일 이벤트로
    간주해 중복 저장·중복 알림을 막는다. 새 통보문이 나오면 occurred_at 이 바뀌므로 새 이벤트가 된다.
    """
    region = None
    if normalized.region_sido and normalized.region_sigungu:
        region = get_or_create_region(db, normalized.region_sido, normalized.region_sigungu, None)
    region_id = region.id if region else None

    existing = db.scalar(
        select(Event).where(
            Event.source == normalized.source,
            Event.event_type == normalized.event_type,
            Event.severity == normalized.severity,
            Event.region_id == region_id,
            Event.occurred_at == normalized.occurred_at,
        )
    )
    if existing is not None:
        return existing, False

    event = Event(
        source=normalized.source,
        event_type=normalized.event_type,
        region_id=region_id,
        severity=normalized.severity,
        raw_payload=normalized.raw_payload,
        occurred_at=normalized.occurred_at,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return event, True


def _evaluate_and_notify(db: Session, event: Event) -> int:
    if event.region_id is None:
        return 0  # TODO: 지진처럼 region 매칭이 약한 소스는 Phase 2에서 별도 처리

    subscriptions = list(db.scalars(select(Subscription).where(Subscription.region_id == event.region_id)))

    created = 0
    for subscription in subscriptions:
        person = db.get(Person, subscription.person_id)
        if person is None:
            continue
        tags = {t.tag for t in db.scalars(select(PersonTag).where(PersonTag.person_id == person.id))}

        risk_level = evaluate_risk(
            event_type=event.event_type,
            age_group=person.age_group,
            tags=tags,
            severity=event.severity,
        )
        if risk_level is None:
            continue  # Layer1이 못 잡음 -> Phase 2에서 Layer2(LLM)로 넘길 케이스

        message = _template_message(event, person)  # TODO: Phase 2에서 LLM 생성으로 교체

        db.add(
            Notification(
                subscription_id=subscription.id,
                event_id=event.id,
                risk_level=risk_level,
                risk_source=RiskSource.MATRIX,
                message=message,
                channel=NotificationChannel.WEB_PUSH,  # TODO: Phase 2에서 device_tokens 기반으로 실제 발송
            )
        )
        created += 1

    db.commit()
    return created


def _template_message(event: Event, person: Person) -> str:
    region_name = f"{event.region.sido} {event.region.sigungu}" if event.region else "알 수 없는 지역"
    return f"[{event.event_type}] {region_name}에 이상상황이 감지됐어요. {person.label}님 관련 주의가 필요해요 (severity={event.severity or 'N/A'})."
