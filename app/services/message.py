"""
알림 문구 생성 — Phase 2 (spec 7절).

LLM 프로바이더 폴백 체인 (graceful degradation):

    1순위: 유료 (OpenAI gpt-4o-mini)
    2순위: 무료 폴백 (.env 의 LLM_FALLBACK_* — Gemini 무료 티어 등, OpenAI 호환 API)
    최종:  템플릿 문구 (LLM 전부 실패해도 알림은 반드시 나간다)

쿨다운(서킷 브레이커 단순판): quota 소진·인증 실패(401/402/429)가 감지된 프로바이더는
15분간 건너뛴다. 매 알림마다 죽은 프로바이더에 실패 호출을 반복하지 않기 위함.
(상태는 프로세스 메모리에만 있어 재시작하면 초기화 — MVP 에선 충분. 다중 인스턴스
배포 시엔 Redis 등 공유 저장소로 옮겨야 한다.)

비용/지연 노트: 알림 1건당 LLM 1회 호출. MVP 트래픽(개인 사용)에선 무시 가능한 수준.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import httpx

from app.config import get_settings

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

_QUOTA_COOLDOWN = timedelta(minutes=15)
# 프로바이더별 "이 시각까지 건너뜀" — quota/인증 오류 시 설정됨
_cooldowns: dict[str, datetime] = {}


@dataclass(frozen=True)
class LlmProvider:
    name: str
    base_url: str
    api_key: str
    model: str


def _build_provider_chain() -> list[LlmProvider]:
    """설정된 프로바이더를 우선순위 순으로. 키가 없는 항목은 체인에서 빠진다."""
    settings = get_settings()
    chain: list[LlmProvider] = []
    if settings.openai_api_key:
        chain.append(
            LlmProvider("primary", settings.openai_base_url, settings.openai_api_key, settings.openai_model)
        )
    if settings.llm_fallback_base_url and settings.llm_fallback_api_key and settings.llm_fallback_model:
        chain.append(
            LlmProvider(
                "fallback",
                settings.llm_fallback_base_url,
                settings.llm_fallback_api_key,
                settings.llm_fallback_model,
            )
        )
    return chain


def generate_notification_message(
    event: "Event",
    person: "Person",
    risk_level: str,
    tags: set[str] | None = None,
) -> str:
    """프로바이더 체인을 순서대로 시도. 전부 실패하면 템플릿."""
    now = datetime.now(timezone.utc)
    for provider in _build_provider_chain():
        cooldown_until = _cooldowns.get(provider.name)
        if cooldown_until is not None and now < cooldown_until:
            continue  # quota 소진 등으로 쿨다운 중 — 다음 프로바이더로
        try:
            return _call_provider(provider, event, person, risk_level, tags or set())
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 402, 429):
                # 키 문제/quota 소진 — 당분간 이 프로바이더는 시도 자체를 스킵
                _cooldowns[provider.name] = now + _QUOTA_COOLDOWN
            continue  # 다음 프로바이더로
        except Exception:  # noqa: BLE001 — 네트워크 등 일시 오류도 다음 프로바이더로
            continue
    return template_message(event, person)


def _call_provider(
    provider: LlmProvider,
    event: "Event",
    person: "Person",
    risk_level: str,
    tags: set[str],
) -> str:
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
        provider.base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json={
            "model": provider.model,
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
