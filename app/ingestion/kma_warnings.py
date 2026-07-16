"""
기상특보 조회서비스 (기상청, data.go.kr 15000415)
project-spec.md 6절 참고. 폭염/한파/호우/태풍/대설 등 12종 특보, 178개 시군 단위.
회원가입 + 활용신청 승인 필요.
"""
from datetime import datetime, timezone

UTC = timezone.utc

import httpx

from app.ingestion.base import BaseIngestionClient, NormalizedEvent
from app.models.enums import EventSource, EventType, Severity

BASE_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList"


class KmaWarningClient(BaseIngestionClient):
    source = EventSource.KMA_WARNING

    def _fetch_mock(self) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source=self.source,
                event_type=EventType.HEATWAVE,
                severity=Severity.WARNING,
                region_sido="대전광역시",
                region_sigungu="유성구",
                occurred_at=datetime.now(UTC),
                raw_payload={
                    "mock": True,
                    "특보종류": "폭염경보",
                    "특보구역": "대전 유성구",
                    "발표시각": datetime.now(UTC).isoformat(),
                },
            )
        ]

    def _fetch_live(self) -> list[NormalizedEvent]:
        # TODO: 실제 파라미터명/응답 필드는 활용가이드 문서 기준으로 검증 필요.
        # data.go.kr 공통 컨벤션(serviceKey, pageNo, numOfRows, dataType) 기준으로 우선 작성.
        params = {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
        }
        response = httpx.get(BASE_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        events: list[NormalizedEvent] = []
        items = data.get("response", {}).get("body", {}).get("items", [])
        for item in items:
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=_map_warning_type(item.get("warnVar", "")),
                    severity=_map_severity(item.get("warnStress", "")),
                    region_sigungu=item.get("areaName"),
                    occurred_at=datetime.now(UTC),  # TODO: 실제 발표시각 필드로 교체
                    raw_payload=item,
                )
            )
        return events


def _map_warning_type(raw: str) -> str:
    # TODO: 실제 코드값 확인 후 매핑 완성
    mapping = {
        "폭염": EventType.HEATWAVE,
        "한파": EventType.COLD_WAVE,
        "호우": EventType.HEAVY_RAIN,
        "태풍": EventType.TYPHOON,
        "대설": EventType.HEAVY_SNOW,
    }
    return mapping.get(raw, raw)


def _map_severity(raw: str) -> str:
    if "경보" in raw:
        return Severity.WARNING
    if "주의보" in raw:
        return Severity.ADVISORY
    return raw
