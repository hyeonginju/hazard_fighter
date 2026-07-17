"""
기상특보 조회서비스 (기상청, data.go.kr 15000415)
project-spec.md 6절 참고. 폭염/한파/호우/태풍/대설 등 12종 특보, 178개 시군 단위.
회원가입 + 활용신청 승인 필요.
"""
import re
from datetime import datetime, timedelta, timezone

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
        # 실제 응답 구조 (2026-07-17 debug_responses/kma_warnings.json 로 확인):
        #   response.body.items.item = [
        #     {"stnId": "156", "title": "[특보] 제07-62호 : 2026.07.17.10:00 / 폭염주의보 발표 (*)",
        #      "tmFc": 202607171000, "tmSeq": 62}, ...
        #   ]
        # - items 는 리스트가 아니라 {"item": [...]} 딕셔너리 (data.go.kr 공통 컨벤션)
        # - 특보 종류/등급/조치(발표·해제)는 title 문자열 안에 들어 있어 파싱 필요
        # - stnId 는 시군구가 아니라 발표 관서(지방기상청) 코드 → 지역 상세는
        #   getWthrWrnMsg(통보문 상세) 연동이 따로 필요 (TODO: Phase 2)
        params = {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 100,
            "dataType": "JSON",
        }
        response = httpx.get(BASE_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        body = data.get("response", {}).get("body", {})
        items_container = body.get("items") or {}
        # 데이터가 없으면 items 가 빈 문자열("")로 오는 경우가 있어 방어
        items = items_container.get("item", []) if isinstance(items_container, dict) else []

        events: list[NormalizedEvent] = []
        for item in items:
            parsed = _parse_title(str(item.get("title", "")))
            if parsed is None:
                continue  # 형식이 다른 공지 등은 스킵 (원문은 로그성 확인용)
            kind, severity, action = parsed
            if action == "해제":
                continue  # 해제 공지는 신규 위험 이벤트가 아님
            event_type = _WARNING_TYPE_MAP.get(kind)
            if event_type is None:
                continue  # MVP 범위 밖 특보(폭풍해일 등)는 스킵 — spec 6절 참고
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=event_type,
                    severity=severity,
                    # 지역 정보 없음: getWthrWrnList 는 관서 단위라 region 매칭 불가.
                    # region 은 None 으로 저장되고, 알림 매칭은 통보문 상세 연동 후 가능.
                    occurred_at=_parse_tm_fc(item.get("tmFc")),
                    raw_payload=item,
                )
            )
        return events


_WARNING_TYPE_MAP = {
    "폭염": EventType.HEATWAVE,
    "한파": EventType.COLD_WAVE,
    "호우": EventType.HEAVY_RAIN,
    "태풍": EventType.TYPHOON,
    "대설": EventType.HEAVY_SNOW,
}

_TITLE_RE = re.compile(r"/\s*([가-힣]+?)(주의보|경보)\s*([가-힣]+)")

KST = timezone(timedelta(hours=9))


def _parse_title(title: str) -> tuple[str, str, str] | None:
    """'... / 폭염주의보 발표 (*)' → ('폭염', Severity, '발표'). 매칭 실패 시 None."""
    m = _TITLE_RE.search(title)
    if m is None:
        return None
    kind, sev_word, action = m.group(1), m.group(2), m.group(3)
    severity = Severity.WARNING if sev_word == "경보" else Severity.ADVISORY
    return kind, severity, action


def _parse_tm_fc(tm_fc) -> datetime:
    """tmFc(예: 202607171000, KST 기준)를 timezone-aware datetime 으로. 실패 시 현재 시각."""
    try:
        return datetime.strptime(str(tm_fc), "%Y%m%d%H%M").replace(tzinfo=KST)
    except (ValueError, TypeError):
        return datetime.now(UTC)
