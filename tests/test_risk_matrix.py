"""
project-spec.md 4절 Layer 1 표를 코드로 옮긴 evaluate_risk()가 표대로 동작하는지 확인.
"""
from app.models.enums import AgeGroup, ConsiderationTag, EventType, RiskLevel, Severity
from app.risk.matrix import evaluate_risk


def test_heatwave_senior_is_high():
    assert evaluate_risk(EventType.HEATWAVE, AgeGroup.SENIOR, set()) == RiskLevel.HIGH


def test_heatwave_adult_no_tags_is_medium():
    assert evaluate_risk(EventType.HEATWAVE, AgeGroup.ADULT, set()) == RiskLevel.MEDIUM


def test_heatwave_adult_with_low_mobility_tag_is_high():
    # age_group 규칙(MEDIUM)과 tag 규칙(HIGH)이 동시에 매칭되면 더 높은 쪽을 따라야 한다.
    result = evaluate_risk(EventType.HEATWAVE, AgeGroup.ADULT, {ConsiderationTag.LOW_MOBILITY})
    assert result == RiskLevel.HIGH


def test_heavy_rain_driver_is_high():
    result = evaluate_risk(EventType.HEAVY_RAIN, AgeGroup.ADULT, {ConsiderationTag.DRIVER})
    assert result == RiskLevel.HIGH


def test_flood_warning_everyone_is_high():
    result = evaluate_risk(
        EventType.FLOOD_WARNING, AgeGroup.ADULT, set(), severity=Severity.WARNING
    )
    assert result == RiskLevel.HIGH


def test_flood_advisory_without_relevant_tag_is_none():
    result = evaluate_risk(
        EventType.FLOOD_WARNING, AgeGroup.ADULT, set(), severity=Severity.ADVISORY
    )
    assert result is None  # Layer 2(LLM)로 넘어가야 하는 케이스


def test_earthquake_high_magnitude_is_high_for_everyone():
    result = evaluate_risk(EventType.EARTHQUAKE, AgeGroup.ADULT, set(), magnitude=4.5)
    assert result == RiskLevel.HIGH


def test_earthquake_medium_magnitude_with_vulnerable_tag_escalates_to_high():
    result = evaluate_risk(
        EventType.EARTHQUAKE, AgeGroup.ADULT, {ConsiderationTag.NEEDS_MOBILITY_AID}, magnitude=3.5
    )
    assert result == RiskLevel.HIGH


def test_earthquake_medium_magnitude_without_tag_is_medium():
    result = evaluate_risk(EventType.EARTHQUAKE, AgeGroup.ADULT, set(), magnitude=3.5)
    assert result == RiskLevel.MEDIUM


def test_earthquake_low_magnitude_is_low():
    result = evaluate_risk(EventType.EARTHQUAKE, AgeGroup.ADULT, set(), magnitude=1.5)
    assert result == RiskLevel.LOW
