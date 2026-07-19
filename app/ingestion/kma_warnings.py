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

BASE_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList"  # 발표 이력 목록 (지역정보 없음)
MSG_URL = "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnMsg"  # 통보문 상세 (t6 에 지역 스냅샷)


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
        # 통보문 상세(getWthrWrnMsg) 기반. 2026-07-17 실 응답으로 확인
        # (debug_responses/kma_warnings_msg.json):
        # - stnId=108(본청) + fromTmFc/toTmFc 필수
        # - 각 통보문의 t6 = "그 시점 기준 발효 중인 특보 전체 + 지역" 스냅샷:
        #     o 폭염주의보 : 전라남도(광양, 순천), 제주도(제주도산지, 추자도 제외)
        #     o 호우주의보 : 충청남도(보령(도서제외), 보령도서)
        # → 최신 통보문의 t6 만 파싱하면 현재 발효 특보 + 지역을 전부 얻는다.
        # (getWthrWrnList 는 관서 단위 목록만 있어 지역 매칭 불가 — msg 로 대체함)
        today = datetime.now(KST)
        params = {
            "serviceKey": self.api_key,
            "pageNo": 1,
            "numOfRows": 10,
            "dataType": "JSON",
            "stnId": "108",  # 기상청 본청 — t6 에 전국 스냅샷이 담긴다
            "fromTmFc": (today - timedelta(days=2)).strftime("%Y%m%d"),
            "toTmFc": today.strftime("%Y%m%d"),
        }
        response = httpx.get(MSG_URL, params=params, timeout=10.0)
        response.raise_for_status()
        data = response.json()

        header = data.get("response", {}).get("header", {})
        if header.get("resultCode") not in ("00", None):
            raise RuntimeError(f"KMA warning msg API error: {header.get('resultCode')} {header.get('resultMsg')}")

        body = data.get("response", {}).get("body", {})
        items_container = body.get("items") or {}
        items = items_container.get("item", []) if isinstance(items_container, dict) else []
        if not items:
            return []  # 발효 중 특보 없음 (또는 조회 기간 내 통보문 없음)

        latest = max(items, key=lambda it: it.get("tmFc", 0))
        occurred_at = _parse_tm_fc(latest.get("tmFc"))

        events: list[NormalizedEvent] = []
        for kind, severity, sido, sigungu in _parse_active_warnings(str(latest.get("t6", ""))):
            event_type = _WARNING_TYPE_MAP.get(kind)
            if event_type is None:
                continue  # MVP 범위 밖 특보(열대야·폭풍해일 등)는 스킵 — spec 6절
            events.append(
                NormalizedEvent(
                    source=self.source,
                    event_type=event_type,
                    severity=severity,
                    region_sido=sido,
                    region_sigungu=sigungu,
                    occurred_at=occurred_at,
                    raw_payload={
                        "stnId": latest.get("stnId"),
                        "tmFc": latest.get("tmFc"),
                        "tmSeq": latest.get("tmSeq"),
                        "kind": kind,
                        "severity": str(severity),
                        "sido": sido,
                        "sigungu": sigungu,
                        "t6": latest.get("t6"),
                    },
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

_HEAD_RE = re.compile(r"([가-힣]+?)(주의보|경보)$")
_NESTED_PAREN_RE = re.compile(r"\([^()]*\)")

KST = timezone(timedelta(hours=9))


def _split_top_level(text: str) -> list[str]:
    """괄호 깊이를 추적하며 최상위 쉼표로만 분리.
    '전라남도(광양, 순천), 인천' → ['전라남도(광양, 순천)', '인천']
    """
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _parse_active_warnings(t6: str) -> list[tuple[str, str, str, str]]:
    """통보문 t6(발효 중 특보 스냅샷)를 (종류, 등급, 시도, 시군구) 목록으로.

    실제 형식 (2026-07-17 debug_responses/kma_warnings_msg.json):
        o 폭염주의보 : 전라남도(광양, 순천), 제주도(제주도산지, 추자도 제외)
        o 호우주의보 : 충청남도(보령(도서제외), 보령도서)
        o 폭풍해일주의보 : 경기도(시흥, 김포), 인천
    처리 규칙:
    - '추자도 제외' 처럼 '제외'로 끝나는 항목은 발효 지역이 아니므로 스킵
    - '보령(도서제외)' 의 중첩 괄호 한정어는 떼고 '보령'으로 정규화
    - '인천' 처럼 하위구역 없이 시도만 오면 sigungu='전체'
    """
    results: list[tuple[str, str, str, str]] = []
    for line in t6.splitlines():
        line = line.strip()
        if not line.startswith("o "):
            continue
        head, sep, regions_text = line[2:].partition(" : ")
        if not sep:
            continue
        m = _HEAD_RE.fullmatch(head.strip())
        if m is None:
            continue
        kind = m.group(1)
        severity = Severity.WARNING if m.group(2) == "경보" else Severity.ADVISORY

        for token in _split_top_level(regions_text):
            if "(" in token and token.endswith(")"):
                sido = token[: token.index("(")].strip()
                inner = token[token.index("(") + 1 : -1]
                for area in _split_top_level(inner):
                    clean = _NESTED_PAREN_RE.sub("", area).strip()
                    if not clean or clean.endswith("제외"):
                        continue
                    results.append((kind, severity, sido, clean))
            else:
                results.append((kind, severity, token, "전체"))
    return results


def _parse_tm_fc(tm_fc) -> datetime:
    """tmFc(예: 202607171000, KST 기준)를 timezone-aware datetime 으로. 실패 시 현재 시각."""
    try:
        return datetime.strptime(str(tm_fc), "%Y%m%d%H%M").replace(tzinfo=KST)
    except (ValueError, TypeError):
        return datetime.now(UTC)
