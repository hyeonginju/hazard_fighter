"""
Layer 1 — 결정론적 위험도 매트릭스.
project-spec.md 4절 표를 그대로 코드화한 것.

설계 노트: MVP는 이 표를 코드에 명시적으로 하드코딩해서 정확성/테스트 용이성을 보장한다.
`seed_risk_matrix()`가 같은 규칙을 risk_matrix 테이블에도 미러링해두는데, 이건 감사(audit)와
향후 "규칙을 관리자 화면에서 조정" 같은 확장을 위한 것 — 지금 당장 이 테이블을 evaluate_risk()가
읽지는 않는다 (12절 Open Question #1, #4와 연결).

지진 규모 임계치는 project-spec.md 4절에 있는 3.0/4.0 구간을 그대로 썼는데, 이건 시작점이고
기상청 실제 발표 기준과 대조해서 다듬어야 한다 (12절 Open Question #1).
"""
from app.models.enums import AgeGroup, ConsiderationTag, EventType, RiskLevel, Severity

# (event_type, severity_or_none, trigger_type, trigger_value, risk_level)
# severity_or_none 이 None이면 해당 특보 등급 전체에 적용.
RISK_MATRIX: list[dict] = [
    # 폭염특보
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "age_group", "trigger_value": AgeGroup.SENIOR, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "age_group", "trigger_value": AgeGroup.INFANT_CHILD, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.LOW_MOBILITY, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.LOW_JUDGEMENT, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEATWAVE, "severity": None, "trigger_type": "age_group", "trigger_value": AgeGroup.ADULT, "risk_level": RiskLevel.MEDIUM},  # "그 외 성인"
    # 한파특보
    {"event_type": EventType.COLD_WAVE, "severity": None, "trigger_type": "age_group", "trigger_value": AgeGroup.SENIOR, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.COLD_WAVE, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.NEEDS_MOBILITY_AID, "risk_level": RiskLevel.HIGH},
    # 호우/태풍특보 (동일 규칙 적용)
    {"event_type": EventType.HEAVY_RAIN, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.DRIVER, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEAVY_RAIN, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.OUTDOOR_COMMUTE, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.TYPHOON, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.DRIVER, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.TYPHOON, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.OUTDOOR_COMMUTE, "risk_level": RiskLevel.HIGH},
    # 대설특보
    {"event_type": EventType.HEAVY_SNOW, "severity": None, "trigger_type": "age_group", "trigger_value": AgeGroup.SENIOR, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEAVY_SNOW, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.NEEDS_MOBILITY_AID, "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.HEAVY_SNOW, "severity": None, "trigger_type": "tag", "trigger_value": ConsiderationTag.DRIVER, "risk_level": RiskLevel.HIGH},
    # 홍수특보 — MVP는 관측소 관할 지역 단위로 적용 (2-3절, 6-1절)
    {"event_type": EventType.FLOOD_WARNING, "severity": Severity.WARNING, "trigger_type": "everyone", "trigger_value": "*", "risk_level": RiskLevel.HIGH},
    {"event_type": EventType.FLOOD_WARNING, "severity": Severity.ADVISORY, "trigger_type": "tag", "trigger_value": ConsiderationTag.DRIVER, "risk_level": RiskLevel.MEDIUM},
    {"event_type": EventType.FLOOD_WARNING, "severity": Severity.ADVISORY, "trigger_type": "tag", "trigger_value": ConsiderationTag.NEEDS_MOBILITY_AID, "risk_level": RiskLevel.MEDIUM},
]

# 지진은 규모(magnitude)가 기준이라 severity 문자열이 아니라 숫자 임계치로 별도 처리한다.
EARTHQUAKE_HIGH_MAGNITUDE = 4.0
EARTHQUAKE_MEDIUM_MAGNITUDE = 3.0
EARTHQUAKE_HIGH_RISK_TAGS = {ConsiderationTag.NEEDS_MOBILITY_AID, ConsiderationTag.LOW_JUDGEMENT}

_RISK_RANK = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}


def _higher(a: str, b: str) -> str:
    return a if _RISK_RANK.get(a, 0) >= _RISK_RANK.get(b, 0) else b


def evaluate_earthquake_risk(magnitude: float, tags: set[str]) -> str:
    if magnitude >= EARTHQUAKE_HIGH_MAGNITUDE:
        return RiskLevel.HIGH
    if magnitude >= EARTHQUAKE_MEDIUM_MAGNITUDE:
        if tags & EARTHQUAKE_HIGH_RISK_TAGS:
            return RiskLevel.HIGH
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def evaluate_risk(
    event_type: str,
    age_group: str,
    tags: set[str],
    severity: str | None = None,
    magnitude: float | None = None,
) -> str | None:
    """
    Layer 1 규칙 매트릭스로 위험도를 계산한다.
    매칭되는 규칙이 여러 개면 가장 높은 위험도를 반환한다.
    매칭되는 규칙이 하나도 없으면 None을 반환 — 이 경우 호출부(추후 Phase 2)가
    Layer 2 LLM 보조 판단으로 넘겨야 한다 (4절 참고).
    """
    if event_type == EventType.EARTHQUAKE:
        if magnitude is None:
            return None
        return evaluate_earthquake_risk(magnitude, tags)

    matched: str | None = None
    for rule in RISK_MATRIX:
        if rule["event_type"] != event_type:
            continue
        if rule["severity"] is not None and rule["severity"] != severity:
            continue

        trigger_type = rule["trigger_type"]
        if trigger_type == "everyone":
            hit = True
        elif trigger_type == "age_group":
            hit = age_group == rule["trigger_value"]
        elif trigger_type == "tag":
            hit = rule["trigger_value"] in tags
        else:
            hit = False

        if hit:
            matched = rule["risk_level"] if matched is None else _higher(matched, rule["risk_level"])

    return matched
