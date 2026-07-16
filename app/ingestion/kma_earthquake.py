"""
지진정보 조회서비스 (기상청, data.go.kr 15000420)
project-spec.md 6절 참고. 자동승인이라 키 발급이 빠르다.
"""
from datetime import datetime, timezone

UTC = timezone.utc

import httpx

from app.ingestion.base import BaseIngestionClient, NormalizedEvent
from app.models.enums import EventSource, EventType

BASE_URL = "http://apis.data.go.kr/1360000/EqkInfoService/getEqkMsg"


class KmaEarthquakeClient(BaseIngestionClient):
    source = EventSource.KMA_EARTHQUAKE

    def _fetch_mock(self) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source=self.source,
                event_type=EventType.EARTHQUAKE,
                magnitude=3.2,
                region_sido="충청북도",
                region_sigungu="청주시",
                occurred_at=datetime.now(UTC),
                raw_payload={
                    "mock": True,
                    "규모": 3.2,
                    "위치": "충북 청주시 서쪽 5km",
                },
            )
        ]

    def _fetch_live(self) -> list[NormalizedEvent]:
        # TODO: 실제 파라미터명/응답 필드는 활용가이드 문서 기준으로 검증 필요.
        params = {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 50,
            "dataType": "JSON",
        }
        response = httpx.get(BASE_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        events: list[NormalizedEvent] = []
        items = data.get("response", {}).get("body", {}).get("items", [])
        for item in items:
            magnitude = item.get("mt")  # TODO: 실제 필드명 확인
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=EventType.EARTHQUAKE,
                    magnitude=float(magnitude) if magnitude is not None else None,
                    region_sigungu=item.get("loc"),
                    occurred_at=datetime.now(UTC),  # TODO: 실제 발생시각 필드로 교체
                    raw_payload=item,
                )
            )
        return events
