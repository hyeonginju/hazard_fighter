"""
알림 문구 생성 — Phase 2 (spec 7절).

전략: LLM 프로바이더 체인(app/services/llm.py)으로 인물 특성에 맞춘 문구를 생성하되,
체인 전체가 실패하면 즉시 템플릿 문구로 fallback 한다.
알림은 안전 기능이므로 "LLM 장애 = 알림 불발"이 되면 안 된다.

비용/지연 노트: 알림 1건당 LLM 1회 호출. MVP 트래픽(개인 사용)에선 무시 가능한 수준.
대량 발송 단계가 되면 배치 생성·캐싱(같은 이벤트×비슷한 프로필 재사용)을 검토한다.
"""
from typing import TYPE_CHECKING

from app.models.enums import EventSource
from app.services import llm

if TYPE_CHECKING:
    from app.models import Event, Person

_SYSTEM_PROMPT = (
    "너는 개인 맞춤 재난 안전 알림 서비스의 문구 작성자다. "
    "한국어 푸시 알림 문구를 작성한다. 규칙: "
    "(1) 2~3문장, 전체 120자 이내. "
    "(2) 첫 문장에 무슨 일이 어디서 났는지. "
    "(3) 이어서 이 사람의 특성에 맞는 구체적 행동 요령 1가지. "
    "(4) 과장·공포 조장 금지, 차분하고 명확하게. 이모지 금지. "
    "(5) 인물 호칭은 주어진 label 을 그대로 쓴다 (예: '어머니님')."
)


def generate_notification_message(
    event: "Event",
    person: "Person",
    risk_level: str,
    tags: set[str] | None = None,
) -> str:
    """LLM 체인으로 맞춤 문구 생성. 실패하면 템플릿 fallback."""
    region_name = (
        f"{event.region.sido} {event.region.sigungu}" if event.region else "구독 지역"
    )
    tag_set = tags or set()
    official = _official_message_text(event)
    if official:
        # 재난문자는 당국 원문(MSG_CN)을 사실 그대로 두고, 이 인물 특성에 맞춰 다듬기만 한다.
        user_prompt = (
            f"공식 긴급재난문자 원문: {official}\n"
            f"지역: {region_name}\n"
            f"대상 인물 label: {person.label}\n"
            f"나이대: {person.age_group}\n"
            f"특성 태그: {', '.join(sorted(tag_set)) if tag_set else '없음'}\n"
            "위 공식 재난문자의 사실은 바꾸지 말고, 이 인물의 특성에 맞는 행동 요령을 담아 다듬어줘."
        )
    else:
        user_prompt = (
            f"이벤트: {event.event_type}"
            f"{f' ({event.severity})' if event.severity else ''}\n"
            f"지역: {region_name}\n"
            f"위험도: {risk_level}\n"
            f"대상 인물 label: {person.label}\n"
            f"나이대: {person.age_group}\n"
            f"특성 태그: {', '.join(sorted(tag_set)) if tag_set else '없음'}\n"
            "위 상황에 대한 푸시 알림 문구를 작성해줘."
        )

    result = llm.chat(_SYSTEM_PROMPT, user_prompt, max_tokens=200)
    if result is None:
        return template_message(event, person)
    content, _model = result
    return content


def template_message(event: "Event", person: "Person") -> str:
    """LLM 없이도 항상 동작하는 기본 문구 (Phase 1 방식)."""
    region_name = (
        f"{event.region.sido} {event.region.sigungu}" if event.region else "알 수 없는 지역"
    )
    official = _official_message_text(event)
    if official:
        # 재난문자는 원문 자체가 이미 당국이 작성한 푸시 문구다 — 그대로 전달한다.
        return f"[긴급재난문자] {region_name}\n{official}"
    return (
        f"[{event.event_type}] {region_name}에 이상상황이 감지됐어요. "
        f"{person.label}님 관련 주의가 필요해요 (severity={event.severity or 'N/A'})."
    )


def _official_message_text(event: "Event") -> str | None:
    """긴급재난문자면 당국 원문(MSG_CN)을 돌려준다. 그 외 소스는 None."""
    if getattr(event, "source", None) != EventSource.DISASTER_MESSAGE:
        return None
    text = (event.raw_payload or {}).get("MSG_CN")
    return text.strip() if isinstance(text, str) and text.strip() else None
