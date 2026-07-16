"""
홍수통제소 표준수문DB (기후에너지환경부 한강홍수통제소, data.go.kr 3040409 / hrfco.go.kr)
project-spec.md 6절, 6-1절 참고.

주의: data.go.kr 목록엔 "API 유형: LINK"로 돼 있어서, 실제 키 발급은 hrfco.go.kr
오픈API 페이지에서 별도로 받아야 한다 (data.go.kr 계정과 무관).

12절 Open Question #6: hrfco.go.kr이 한강 수계 외 금강·낙동강·영산강 홍수통제소까지
통합 제공하는지 실제 연동 시 확인 필요 (미호강은 금강 수계).
"""
from datetime import datetime, timezone

UTC = timezone.utc

import httpx

from app.ingestion.base import BaseIngestionClient, NormalizedEvent
from app.models.enums import EventSource, EventType, Severity

BASE_URL = "http://www.hrfco.go.kr/web/openapifront/getWaterInfo.do"  # TODO: 실제 홍수특보 엔드포인트로 교체


class HrfcoFloodClient(BaseIngestionClient):
    source = EventSource.HRFCO_FLOOD

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
        # TODO: hrfco.go.kr 오픈API 가이드 기준으로 실제 엔드포인트/파라미터 확정 필요.
        params = {"serviceKey": self.api_key, "type": "json"}
        response = httpx.get(BASE_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        events: list[NormalizedEvent] = []
        for item in data.get("content", []):
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=EventType.FLOOD_WARNING,
                    severity=_map_flood_severity(item.get("fw_wl", "")),
                    station_code=item.get("wlobscd"),
                    occurred_at=datetime.now(UTC),  # TODO: 실제 관측시각 필드로 교체
                    raw_payload=item,
                )
            )
        return events


def _map_flood_severity(raw: str) -> str | None:
    if "경보" in raw:
        return Severity.WARNING
    if "주의보" in raw:
        return Severity.ADVISORY
    return None
