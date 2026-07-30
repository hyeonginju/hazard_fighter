"""
알림 발송(dispatch) 단계 — 생성과 발송을 분리한다.
project-spec.md 7절·9절 참고.

왜 분리하나: 알림은 ingest 파이프라인이 DB 에 sent_at=NULL 로 쌓아둔다. 이 단계가 아직
안 보낸 알림만 모아 FCM 으로 발송하고 sent_at 을 찍는다. 이렇게 하면
- **멱등·중복발송 방지**: sent_at 이 곧 가드라, 발송에 성공한 알림은 다음 사이클에 다시 안 보낸다.
  스케줄러 중복 가드·LLM 쿨다운·이벤트 dedupe 와 같은 "상태를 기억해 낭비 호출을 막는" 패턴.
- **재시도**: 발송 실패(네트워크·5xx)면 sent_at 을 안 찍어 다음 사이클에 자동 재시도된다.
- **관심사 분리**: 위험도 판단/문구 생성과 전송이 서로를 안 붙든다.

미설정(mock) 시엔 FcmClient 가 실제 발송 없이 성공(mock)을 돌려주므로, 토큰만 등록돼 있으면
파이프라인 전체가 로컬에서도 끝까지 돈다.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeviceToken, Notification, Subscription
from app.services.push import FcmClient, get_fcm_client

UTC = timezone.utc
logger = logging.getLogger(__name__)


def dispatch_unsent_notifications(db: Session, client: FcmClient | None = None) -> dict:
    """아직 안 보낸 알림을 사용자 기기로 발송하고 sent_at 을 기록한다.

    client 를 주입하면 테스트에서 실제 FCM 없이 검증할 수 있다(기본은 설정 기반 클라이언트).
    """
    client = client or get_fcm_client()

    unsent = list(
        db.scalars(select(Notification).where(Notification.sent_at.is_(None)).order_by(Notification.id))
    )

    sent = 0
    no_target = 0
    failed = 0
    tokens_removed = 0

    for notif in unsent:
        tokens = _device_tokens_for_notification(db, notif)
        if not tokens:
            no_target += 1  # 아직 등록된 기기가 없음 — sent_at 을 안 찍어 다음 사이클에 재시도
            continue

        title, body = _title_body(notif)
        delivered = False
        for token in tokens:
            result = client.send(token.fcm_token, title, body)
            if result.status == "invalid_token":
                db.delete(token)  # 죽은 토큰(앱 삭제·구독 해제) 정리
                tokens_removed += 1
            elif result.ok:
                delivered = True

        if delivered:
            notif.sent_at = datetime.now(UTC)
            sent += 1
        else:
            failed += 1  # 유효 토큰이 있었는데 전부 실패 — 재시도 대상

    db.commit()

    # 발송은 파이프라인의 마지막 단계라, 여기서 조용히 실패하면 "수집은 잘 되는데
    # 알림만 안 오는" 상태가 된다. 2026-07-29 프로덕션에서 실제로 그랬다 — 기기 토큰이
    # 죽어 사라졌는데 로그가 없어 이틀 동안 아무도 몰랐다. 그래서 사람이 알아야 하는
    # 상황(토큰 정리·보낼 기기 없음·전송 실패)은 WARNING 으로 남긴다.
    if tokens_removed:
        logger.warning(
            "죽은 기기 토큰 %d개 삭제 (FCM UNREGISTERED) — 해당 기기는 /app 을 다시 열어야 재등록된다",
            tokens_removed,
        )
    if no_target:
        logger.warning("보낼 기기가 없어 대기 중인 알림 %d건 (등록된 기기 토큰 없음)", no_target)
    if failed:
        logger.warning("발송 실패로 다음 사이클에 재시도할 알림 %d건", failed)

    return {
        "unsent_seen": len(unsent),
        "sent": sent,
        "no_target": no_target,
        "failed": failed,
        "tokens_removed": tokens_removed,
        "mock": not client.enabled,
    }


def _device_tokens_for_notification(db: Session, notif: Notification) -> list[DeviceToken]:
    """알림 → 구독 → 사용자 → 그 사용자의 모든 기기 토큰."""
    subscription = db.get(Subscription, notif.subscription_id)
    if subscription is None:
        return []
    return list(db.scalars(select(DeviceToken).where(DeviceToken.user_id == subscription.user_id)))


def _title_body(notif: Notification) -> tuple[str, str]:
    """푸시 제목/본문. 제목엔 위험도를 넣어 잠금화면에서 바로 분류되게 하고, 본문은 문구 전체."""
    return f"[{notif.risk_level}] 명예소방관 안전 알림", notif.message
