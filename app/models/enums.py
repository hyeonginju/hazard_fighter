"""
프로젝트 전역에서 쓰는 고정 태그/enum 값들.
project-spec.md 3절(인물 프로필 태그 체계), 4절(위험도 판단 로직) 기준.
DB에는 문자열로 저장하고, 애플리케이션 레벨에서 이 Enum으로 검증한다.
"""
from enum import Enum


class StrEnum(str, Enum):
    """Python 3.10 이하 호환용 (3.11+ 표준 StrEnum과 동일하게 동작)."""

    def __str__(self) -> str:
        return str(self.value)


class AgeGroup(StrEnum):
    INFANT_CHILD = "영유아/아동"
    TEEN = "청소년"
    ADULT = "성인"
    SENIOR = "고령"


class ConsiderationTag(StrEnum):
    DRIVER = "운전자"
    NEEDS_MOBILITY_AID = "보행보조필요"
    LOW_ATTENTION = "주의력낮음"
    LOW_JUDGEMENT = "판단력저하"
    LOW_MOBILITY = "운동능력낮음"
    PREGNANT = "임신부"
    RESPIRATORY_CARDIAC = "호흡기·심혈관질환"
    OUTDOOR_COMMUTE = "실외근무/통학통근 중"


class EventType(StrEnum):
    HEATWAVE = "폭염특보"
    COLD_WAVE = "한파특보"
    HEAVY_RAIN = "호우특보"
    TYPHOON = "태풍특보"
    HEAVY_SNOW = "대설특보"
    EARTHQUAKE = "지진"
    FLOOD_WARNING = "홍수특보"
    DISASTER_MESSAGE = "긴급재난문자"


class Severity(StrEnum):
    ADVISORY = "주의보"
    WARNING = "경보"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class RiskSource(StrEnum):
    MATRIX = "matrix"  # Layer 1 결정론적 규칙
    AI = "ai"  # Layer 2 LLM 보조 판단


class DevicePlatform(StrEnum):
    WEB = "web"
    ANDROID = "android"
    IOS = "ios"


class NotificationChannel(StrEnum):
    WEB_PUSH = "web_push"
    APP_PUSH = "app_push"


class EventSource(StrEnum):
    KMA_WARNING = "kma_warning"  # 기상특보 (data.go.kr 15000415)
    KMA_EARTHQUAKE = "kma_earthquake"  # 지진정보 (data.go.kr 15000420)
    HRFCO_FLOOD = "hrfco_flood"  # 홍수통제소 수문DB (data.go.kr 3040409)
    DISASTER_MESSAGE = "disaster_message"  # 긴급재난문자 (safetydata.go.kr)
