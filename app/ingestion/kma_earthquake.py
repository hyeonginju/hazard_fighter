"""
지진정보 조회서비스 (기상청, data.go.kr 15000420)
project-spec.md 6절 참고. 자동승인이라 키 발급이 빠르다.
"""
from datetime import datetime, timedelta, timezone

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

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
        # 2026-07-17 실 호출로 확인된 제약 (debug_responses/kma_earthquake.json):
        # - fromTmFc/toTmFc(조회기간, yyyyMMdd) 필수 → 없으면 resultCode=11
        # - 최대 조회 기간은 "오늘 기준 3일 전까지" → 초과하면 resultCode=99
        today = datetime.now(KST)
        params = {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 50,
            "dataType": "JSON",
            "fromTmFc": (today - timedelta(days=3)).strftime("%Y%m%d"),
            "toTmFc": today.strftime("%Y%m%d"),
        }
        response = httpx.get(BASE_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        header = data.get("response", {}).get("header", {})
        if header.get("resultCode") not in ("00", None):
            # 파라미터 오류 등 API 레벨 에러 — 예외로 올려서 ingest 가 소스별 에러로 기록
            raise RuntimeError(f"KMA earthquake API error: {header.get('resultCode')} {header.get('resultMsg')}")

        body = data.get("response", {}).get("body", {})
        items_container = body.get("items") or {}
        # 데이터 없으면 items 가 "" 로 오는 경우 방어 (data.go.kr 공통)
        items = items_container.get("item", []) if isinstance(items_container, dict) else []

        events: list[NormalizedEvent] = []
        for item in items:
            # 실제 필드 (2026-07-17 debug_responses/kma_earthquake.json 로 확인):
            #   mt=규모, loc=위치 문자열, tmEqk=발생시각(yyyyMMddHHmmss),
            #   lat/lon/dep=좌표·깊이, rem=비고("국내영향없음..." 등), fcTp=통보 유형
            # TODO: 국외 지진(loc이 해외)도 일단 저장됨 — region 미매칭이라 알림은 안 나가지만,
            #       fcTp/loc 기준 국내외 구분 필터는 추후 검토.
            magnitude = item.get("mt")
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=EventType.EARTHQUAKE,
                    magnitude=float(magnitude) if magnitude not in (None, "") else None,
                    region_sigungu=item.get("loc"),
                    occurred_at=_parse_tm_eqk(item.get("tmEqk")),
                    raw_payload=item,
                )
            )
        return events


def _parse_tm_eqk(tm_eqk) -> datetime:
    """tmEqk(예: 20260715004941, KST)를 timezone-aware datetime 으로. 실패 시 현재 시각."""
    try:
        return datetime.strptime(str(tm_eqk), "%Y%m%d%H%M%S").replace(tzinfo=KST)
    except (ValueError, TypeError):
        return datetime.now(UTC)
