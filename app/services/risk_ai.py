"""
Layer 2 — LLM 위험도 보조 판단 (spec 4절).

Layer 1 규칙 매트릭스(app/risk/matrix.py)가 매칭하지 못한(None) 케이스만 여기로 온다.
예: 한파특보 + 특이 태그 없는 성인 — 규칙엔 없지만 상황에 따라 주의가 필요할 수 있다.

설계 원칙:
- 판단 결과는 반드시 ai_risk_logs 에 남긴다 (감사 가능성 — 왜 알림을 보냈/안 보냈는지 추적).
- MEDIUM/HIGH 만 알림 생성으로 이어진다. LOW 는 "판단은 했고 알림은 불필요" 기록만.
- LLM 실패 시 판단 보류(None) — 규칙에 없는 케이스를 임의로 HIGH 처리하지 않는다(오탐 방지).
- 호출 절약: 같은 (이벤트 유형, 등급, 나이대, 태그) 조합은 인물이 달라도 같은 판단이므로
  프로세스 메모리에 캐시한다. 전국 특보 × 다수 구독자 상황에서 LLM 호출이 폭증하는 것 방지.
"""
import logging
import re
from typing import TYPE_CHECKING

from app.models import AIRiskLog
from app.models.enums import RiskLevel
from app.services import llm

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from app.models import Event, Person, Subscription

logger = logging.getLogger("hazard_fighter.risk_ai")

_SYSTEM_PROMPT = (
    "너는 재난 안전 서비스의 위험도 평가자다. 재난 상황과 대상 인물의 특성을 보고 "
    "그 사람에게 얼마나 위험한지 평가한다. 응답 형식(반드시 지킬 것): "
    "첫 줄에 HIGH, MEDIUM, LOW 중 정확히 하나만. "
    "둘째 줄에 판단 근거를 한 문장으로. "
    "기준: HIGH=즉시 행동 필요한 직접 위험, MEDIUM=주의하면 관리 가능, LOW=특별 조치 불필요. "
    "과잉 경보는 알림 피로를 만드니, 애매하면 낮은 쪽을 택한다."
)

_LEVEL_RE = re.compile(r"\b(HIGH|MEDIUM|LOW)\b")

# (event_type, severity, age_group, tags) -> (risk_level, rationale, model)
# 같은 조합은 인물이 달라도 같은 판단 — LLM 호출 절약용 프로세스 메모리 캐시
_decision_cache: dict[tuple, tuple[str, str, str]] = {}


def evaluate_and_log(
    db: "Session",
    event: "Event",
    subscription: "Subscription",
    person: "Person",
    tags: set[str],
) -> str | None:
    """LLM 으로 위험도를 판단하고 ai_risk_logs 에 기록. 커밋은 호출자 책임.

    반환: RiskLevel 값(판단 성공) 또는 None(LLM 실패 → 판단 보류).
    """
    cache_key = (event.event_type, event.severity, person.age_group, frozenset(tags))
    cached = _decision_cache.get(cache_key)

    if cached is not None:
        risk_level, rationale, model_name = cached
    else:
        decision = _ask_llm(event, person, tags)
        if decision is None:
            return None  # 체인 전체 실패 — 판단 보류 (다음 사이클에 재시도됨)
        risk_level, rationale, model_name = decision
        _decision_cache[cache_key] = decision

    db.add(
        AIRiskLog(
            event_id=event.id,
            subscription_id=subscription.id,
            risk_level=risk_level,
            rationale=rationale,
            model=model_name,
        )
    )
    return risk_level


def _ask_llm(event: "Event", person: "Person", tags: set[str]) -> tuple[str, str, str] | None:
    region_name = (
        f"{event.region.sido} {event.region.sigungu}" if event.region else "알 수 없는 지역"
    )
    user_prompt = (
        f"재난: {event.event_type}"
        f"{f' ({event.severity})' if event.severity else ''}\n"
        f"지역: {region_name}\n"
        f"대상 인물 나이대: {person.age_group}\n"
        f"특성 태그: {', '.join(sorted(tags)) if tags else '없음'}\n"
        "이 인물에게 이 상황의 위험도를 평가해줘."
    )

    result = llm.chat(_SYSTEM_PROMPT, user_prompt, max_tokens=150)
    if result is None:
        return None
    content, model_name = result

    match = _LEVEL_RE.search(content.upper())
    if match is None:
        logger.warning("Layer2 응답에서 위험도를 못 찾음: %r", content[:100])
        return None  # 형식 위반 응답 — 판단 보류
    risk_level = {
        "HIGH": RiskLevel.HIGH,
        "MEDIUM": RiskLevel.MEDIUM,
        "LOW": RiskLevel.LOW,
    }[match.group(1)]

    # 첫 줄(레벨) 제외한 나머지를 근거로. 없으면 원문 전체 보존
    lines = [line.strip() for line in content.strip().splitlines() if line.strip()]
    rationale = " ".join(lines[1:]) if len(lines) > 1 else content.strip()

    return risk_level, rationale, model_name
