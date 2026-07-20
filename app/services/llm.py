"""
LLM 프로바이더 폴백 체인 — 범용 호출 모듈.

원래 알림 문구 생성(message.py) 안에 있던 체인을, Layer 2 위험도 판단(risk_ai.py)도
쓸 수 있게 분리했다 (2026-07-20). 체인 구조와 쿨다운 동작은 그대로:

    1순위: 유료 (OpenAI)  →  2순위: 무료 폴백 (.env LLM_FALLBACK_*)  →  실패 시 None

- 401/402/429(키 문제·quota 소진) 프로바이더는 15분 쿨다운으로 격리.
- 쿨다운 상태는 프로세스 메모리 (다중 인스턴스 배포 시 Redis 등으로 이전 필요).
- 호출자는 None 을 받으면 각자의 폴백(템플릿 문구, 판단 보류 등)을 실행한다.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

from app.config import get_settings

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


def chat(system_prompt: str, user_prompt: str, max_tokens: int = 200) -> tuple[str, str] | None:
    """체인을 순서대로 시도해 (응답 텍스트, 사용된 모델명)을 반환. 전부 실패하면 None."""
    now = datetime.now(timezone.utc)
    for provider in _build_provider_chain():
        cooldown_until = _cooldowns.get(provider.name)
        if cooldown_until is not None and now < cooldown_until:
            continue  # quota 소진 등으로 쿨다운 중 — 다음 프로바이더로
        try:
            content = _call_provider(provider, system_prompt, user_prompt, max_tokens)
            return content, provider.model
        except httpx.HTTPStatusError as e:
            if e.response.status_code in (401, 402, 429):
                # 키 문제/quota 소진 — 당분간 이 프로바이더는 시도 자체를 스킵
                _cooldowns[provider.name] = now + _QUOTA_COOLDOWN
            continue  # 다음 프로바이더로
        except Exception:  # noqa: BLE001 — 네트워크 등 일시 오류도 다음 프로바이더로
            continue
    return None


def _call_provider(provider: LlmProvider, system_prompt: str, user_prompt: str, max_tokens: int) -> str:
    response = httpx.post(
        provider.base_url.rstrip("/") + "/chat/completions",
        headers={"Authorization": f"Bearer {provider.api_key}"},
        json={
            "model": provider.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_tokens": max_tokens,
            "temperature": 0.7,
        },
        timeout=15.0,
    )
    response.raise_for_status()
    content = response.json()["choices"][0]["message"]["content"].strip()
    if not content:
        raise ValueError("empty LLM response")
    return content
