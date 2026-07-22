"""
홍수통제소 표준수문DB (기후에너지환경부, api.hrfco.go.kr)
project-spec.md 6절, 6-1절 참고.

실제 API (2026-07-17 debug_fetch.py 로 확인 — debug_responses/hrfco_*.json):
- 관측소 목록:  GET /{키}/waterlevel/info.json
    → content[]: wlobscd(관측소코드), obsnm, addr(주소), attwl(주의수위),
      wrnwl(경보수위), almwl, srswl, pfh 등. 전국 1,417개 — 4대강 통합 제공 확인
      (spec 12절 Open Question #6 해결).
- 수위 데이터:  GET /{키}/waterlevel/list/10M/{관측소코드}/{시작yyyyMMddHHmm}/{종료}.json
    → content[]: wlobscd, ymdhm(관측시각), wl(수위, 빈 값 " " 가능), fw(유량)

홍수 이벤트 판정: 최신 수위(wl) >= 경보수위(wrnwl) → 경보, >= 주의수위(attwl) → 주의보.
"경보/주의보"라는 공식 특보 발령 API가 아니라 수위 임계치 초과를 근거로 한 자체 판정이다
(spec 4절의 홍수특보 규칙과 동일한 기준).

키 발급: hrfco.go.kr 오픈API 페이지에서 별도 발급 (data.go.kr 계정과 무관).
"""
import time
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

import httpx

from app.ingestion.base import BaseIngestionClient, NormalizedEvent
from app.models.enums import EventSource, EventType, Severity

BASE_URL = "https://api.hrfco.go.kr"

# 분당 호출 상한. 홍수통제소 실제 한도는 분당 1,000건이고, 초과가 3회면 키가 차단된다
# (학습노트 2026-07-20 호출량 예산). 관측소를 여러 개 순회하면 순차 호출이라도
# 네트워크가 빠를 때 순간적으로 분당 1,000을 넘길 수 있어(예: N=1,417 × 콜당 50ms
# = 분당 1,200콜) 호출 속도 자체에 상한을 건다. 한도의 60%(콜당 최소 0.1초)로 여유.
DEFAULT_MAX_REQUESTS_PER_MINUTE = 600


class _RateLimiter:
    """연속 호출 사이 최소 간격을 강제해 분당 호출 수가 상한을 넘지 않게 하는 게이트.
    스케줄러 중복 가드·LLM 쿨다운과 같은 "상태를 기억해 낭비/위험 호출을 막는" 패턴.
    clock/sleep 을 주입받아 테스트에서 실제 대기 없이 검증할 수 있다."""

    def __init__(self, max_per_minute: int, *, monotonic=time.monotonic, sleep=time.sleep):
        if max_per_minute <= 0:
            raise ValueError("max_per_minute must be positive")
        self._min_interval = 60.0 / max_per_minute
        self._monotonic = monotonic
        self._sleep = sleep
        self._next_allowed: float | None = None  # 다음 호출이 허용되는 시각(monotonic)

    def wait(self) -> None:
        """다음 호출이 허용될 때까지 블록한다. 간격이 이미 충분하면 대기하지 않는다."""
        now = self._monotonic()
        if self._next_allowed is not None and now < self._next_allowed:
            self._sleep(self._next_allowed - now)
            now = self._next_allowed
        self._next_allowed = now + self._min_interval

# MVP 모니터링 대상 관측소 (spec 2-3절 청주 시나리오 기준).
# 전 관측소(1,417개)를 매 사이클 조회하면 호출이 과하므로, 구독 지역 기반으로
# 동적 선정하는 것은 Phase 2 TODO (river_gauges/gauge_region_maps 테이블 활용).
MONITORED_STATIONS = [
    "1004616",  # 청주시(청석굴교) — 충북 청주시 상당구, 주의 3.3 / 경보 5.6
    "3010605",  # 청주시(죽전교) — 충북 청주시 서원구, 주의 1.4 / 경보 2.1
]


class HrfcoFloodClient(BaseIngestionClient):
    source = EventSource.HRFCO_FLOOD

    def __init__(self, api_key: str | None, max_requests_per_minute: int = DEFAULT_MAX_REQUESTS_PER_MINUTE):
        super().__init__(api_key)
        self._limiter = _RateLimiter(max_requests_per_minute)

    def _fetch_mock(self) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source=self.source,
                event_type=EventType.FLOOD_WARNING,
                severity=Severity.WARNING,
                station_code="3008670",  # 미호천교 관측소 (예시)
                region_sido="충청북도",
                region_sigungu="청주시 흥덕구",
                occurred_at=datetime.now(UTC),
                raw_payload={
                    "mock": True,
                    "관측소명": "미호천교",
                    "홍수특보": "홍수경보",
                    "수위": 29.02,
                },
            )
        ]

    def _fetch_live(self) -> list[NormalizedEvent]:
        stations = self._fetch_station_info()

        events: list[NormalizedEvent] = []
        for code in MONITORED_STATIONS:
            info = stations.get(code)
            if info is None:
                continue
            att = _to_float(info.get("attwl"))
            wrn = _to_float(info.get("wrnwl"))
            if att is None and wrn is None:
                continue  # 임계치 미설정 관측소는 판정 불가 (예: 3011627 미호)

            latest = self._fetch_latest_level(code)
            if latest is None:
                continue
            level, observed_at = latest

            severity = None
            if wrn is not None and level >= wrn:
                severity = Severity.WARNING
            elif att is not None and level >= att:
                severity = Severity.ADVISORY
            if severity is None:
                continue  # 평시 수위 — 이벤트 아님

            sido, sigungu = _split_addr(str(info.get("addr", "")))
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=EventType.FLOOD_WARNING,
                    severity=severity,
                    station_code=code,
                    region_sido=sido,
                    region_sigungu=sigungu,
                    occurred_at=observed_at,
                    raw_payload={
                        "station": info,
                        "water_level": level,
                        "observed_at": observed_at.isoformat(),
                    },
                )
            )
        return events

    def _fetch_station_info(self) -> dict[str, dict]:
        """관측소 목록 + 주의/경보 수위 임계치. wlobscd 로 인덱싱해서 반환."""
        url = f"{BASE_URL}/{self.api_key}/waterlevel/info.json"
        self._limiter.wait()
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        content = response.json().get("content", [])
        return {str(item.get("wlobscd")): item for item in content}

    def _fetch_latest_level(self, station_code: str) -> tuple[float, datetime] | None:
        """최근 3시간 중 가장 최신의 유효한 수위(wl). 없으면 None."""
        now = datetime.now(KST)
        start = (now - timedelta(hours=3)).strftime("%Y%m%d%H%M")
        end = now.strftime("%Y%m%d%H%M")
        url = f"{BASE_URL}/{self.api_key}/waterlevel/list/10M/{station_code}/{start}/{end}.json"
        self._limiter.wait()
        response = httpx.get(url, timeout=15.0)
        response.raise_for_status()
        content = response.json().get("content", [])
        # 응답은 최신순. wl 이 빈 값(" ")인 행이 섞여 있어 첫 유효값을 찾는다.
        for row in content:
            level = _to_float(row.get("wl"))
            if level is not None:
                observed = _parse_ymdhm(row.get("ymdhm"))
                return level, observed
        return None


def _to_float(raw) -> float | None:
    try:
        value = str(raw).strip()
        return float(value) if value else None
    except (ValueError, TypeError):
        return None


def _parse_ymdhm(raw) -> datetime:
    """ymdhm(예: 202607171610, KST)를 datetime 으로. 실패 시 현재 시각."""
    try:
        return datetime.strptime(str(raw), "%Y%m%d%H%M").replace(tzinfo=KST)
    except (ValueError, TypeError):
        return datetime.now(UTC)


def _split_addr(addr: str) -> tuple[str | None, str | None]:
    """'충청북도 청주시 상당구 미원면' → ('충청북도', '청주시 상당구')."""
    parts = addr.split()
    if not parts:
        return None, None
    sido = parts[0]
    if len(parts) >= 3 and parts[2].endswith(("구", "군")):
        return sido, f"{parts[1]} {parts[2]}"
    if len(parts) >= 2:
        return sido, parts[1]
    return sido, None
