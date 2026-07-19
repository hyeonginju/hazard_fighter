"""
알림 문구 생성 — Phase 2 (spec 7절).

전략: LLM(OpenAI)으로 인물 특성에 맞춘 문구를 생성하되,
키가 없거나 호출이 실패하면 즉시 템플릿 문구로 fallback 한다.
알림은 안전 기능이므로 "LLM 장애 = 알림 불발"이 되면 안 된다.

비용/지연 노트: 알림 1건당 LLM 1회 호출. MVP 트래픽(개인 사용)에선 무시 가능한 수준.
대량 발송 단계가 되면 배치 생성·캐싱(같은 이벤트×비슷한 프로필 재사용)을 검토한다.
"""
from typing import TYPE_CHECKING

import httpx

from app.config import get_settings

if TYPE_CHECKING:
    from app.models import Event, Person

OPENAI_URL = "https://api.openai.com/v1/chat/completions"

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
    """LLM 으로 맞춤 문구 생성. 실패하면 템플릿 fallback."""
    settings = get_settings()
    if not settings.openai_api_key:
        return template_message(event, person)
    try:
        return _generate_with_openai(event, person, risk_level, tags or set())
    except Exception:  # noqa: BLE001 — 어떤 실패든 알림 자체는 나가야 한다
        return template_message(event, person)


def _generate_with_openai(
    event: "Event", person: "Person", risk_level: str, tags: set[str]
) -> str:
    settings = get_settings()
    region_name = (
        f"{event.region.sido} {event.region.sigungu}" if event.region else "구독 지역"
    )
    user_prompt = (
        f"이벤트: {event.event_type}"
        f"{f' ({event.severity})' if event.severity else ''}\n"
        f"지역: {region_name}\n"
        f"위험도: {risk_level}\n"
        f"대상 인물 label: {person.label}\n"
        f"나이대: {person.age_group}\n"
        f"특성 태그: {', '.join(sorted(tags)) if tags else '없음'}\n"
        "위 상황에 대한 푸시 알림 문구를 작성해줘."
    )

    response = httpx.post(
        OPENAI_URL,
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.openai_model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": 200,
            "temperature": 0.7,
        },
        timeout=15.0,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    if not content:
        raise ValueError("empty LLM response")
    return content


def template_message(event: "Event", person: "Person") -> str:
    """LLM 없이도 항상 동작하는 기본 문구 (Phase 1 방식)."""
    region_name = (
        f"{event.region.sido} {event.region.sigungu}" if event.region else "알 수 없는 지역"
    )
    return (
        f"[{event.event_type}] {region_name}에 이상상황이 감지됐어요. "
        f"{person.label}님 관련 주의가 필요해요 (severity={event.severity or 'N/A'})."
    )
