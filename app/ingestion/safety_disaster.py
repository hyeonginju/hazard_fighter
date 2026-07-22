"""
긴급재난문자 조회 (행정안전부, 재난안전데이터공유플랫폼 safetydata.go.kr, DSSP-IF-00247).
project-spec.md 6절 참고. 일일 호출 한도 1,000건 — 호출량 예산이 가장 빡빡한 소스라
폴링 주기를 10분 이상으로 유지해야 한다 (docs/dev-learning-notes.md 2026-07-20 항목).

2026-07-22 실 응답으로 확인된 것 (debug_responses/safetydata_disaster_msg.json + 프로브):
- 응답 구조가 data.go.kr 과 다르다: header/body 가 최상위(response. 하위 아님),
  body 가 리스트 그 자체({"item":[...]} 래핑 없음).
- 날짜 필터 파라미터 = crtDt(YYYYMMDD). 지정한 그 날짜의 문자만 반환된다.
- 정렬은 SN(일련번호) 오름차순 = 오래된 순. 따라서 "최신"을 얻으려면 마지막 페이지를 봐야 한다.
- 필드: MSG_CN(내용), RCPTN_RGN_NM(수신지역, 공백구분·쉼표로 다지역), CRT_DT(발송시각),
  DST_SE_NM(재난구분), EMRG_STEP_NM(긴급단계), SN(일련번호 = dedupe 키).
- EMRG_STEP_NM 은 폭염·호우·댐방류까지 거의 전부 "안전안내"라 필터 기준으로 무용지물.
  실제 판별자는 DST_SE_NM(재난구분)이다.

위험도 처리(Option A — "공식 방송으로 취급"): 재난문자는 당국이 이미 그 지역에 방송하기로
판정한 완성 경보다. 규칙/LLM 위험엔진으로 재판정하지 않고, 필터를 통과하면 관련 있음으로 보고
기본 위험도를 매긴다(app/services/ingest.py). 개인화는 알림 문구(MSG_CN 기반)에서 한다.
"""
from datetime import datetime, timedelta, timezone

import httpx

from app.ingestion.base import BaseIngestionClient, NormalizedEvent
from app.models.enums import EventSource, EventType

UTC = timezone.utc
KST = timezone(timedelta(hours=9))

BASE_URL = "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247"
PAGE_SIZE = 100  # 최신 페이지에서 가져올 최대 건수 (10분 주기 × 하루 볼륨이면 충분)

# 재난이 아닌(안내성) 재난구분 — 이것만 걸러낸다.
# 화이트리스트가 아니라 denylist 인 이유: 재해 구분은 열려 있어(신규 재난 유형이 계속 생김)
# 화이트리스트는 목록에 없는 신규 재난을 조용히 놓치는 false negative 위험이 있다.
# 안전 서비스에선 "알려진 비재해만 제외"가 신규 위험을 놓치지 않아 더 안전하다.
# 실측 예: DST_SE_NM="기타" = 실종자 찾기·물놀이 안내, "교통통제" = 도로 통제.
_NON_HAZARD_DST_SE = {"기타", "교통통제"}


class SafetyDisasterMessageClient(BaseIngestionClient):
    source = EventSource.DISASTER_MESSAGE

    def _fetch_mock(self) -> list[NormalizedEvent]:
        return [
            NormalizedEvent(
                source=self.source,
                event_type=EventType.DISASTER_MESSAGE,
                severity=None,
                region_sido="충청북도",
                region_sigungu="청주시 흥덕구",
                occurred_at=datetime.now(UTC),
                raw_payload={
                    "mock": True,
                    "SN": 999999,
                    "MSG_CN": "[청주시] 호우경보 발효 중. 하천변·저지대 접근을 자제하고 안전한 곳으로 대피하세요.",
                    "DST_SE_NM": "호우",
                    "EMRG_STEP_NM": "안전안내",
                    "RCPTN_RGN_NM": "충청북도 청주시 흥덕구 ",
                    "CRT_DT": datetime.now(KST).strftime("%Y/%m/%d %H:%M:%S"),
                },
            )
        ]

    def _fetch_live(self) -> list[NormalizedEvent]:
        today = datetime.now(KST).strftime("%Y%m%d")
        base = {"serviceKey": self.api_key, "returnType": "json", "crtDt": today}

        # 오늘치 총건수 확인 → 오름차순이라 최신은 마지막 페이지에 있다.
        _, total = self._call({**base, "pageNo": 1, "numOfRows": 1})
        if total <= 0:
            return []
        last_page = (total + PAGE_SIZE - 1) // PAGE_SIZE
        rows, _ = self._call({**base, "pageNo": last_page, "numOfRows": PAGE_SIZE})

        events: list[NormalizedEvent] = []
        for row in rows:
            dst_se = (row.get("DST_SE_NM") or "").strip()
            if dst_se in _NON_HAZARD_DST_SE:
                continue  # 실종자·교통통제 등 안내성 메시지는 스킵 (알림 피로 방지)

            occurred_at = _parse_crt_dt(row.get("CRT_DT"))
            payload = {
                "SN": row.get("SN"),
                "MSG_CN": row.get("MSG_CN"),
                "DST_SE_NM": row.get("DST_SE_NM"),
                "EMRG_STEP_NM": row.get("EMRG_STEP_NM"),
                "RCPTN_RGN_NM": row.get("RCPTN_RGN_NM"),
                "CRT_DT": row.get("CRT_DT"),
            }
            # 한 문자가 여러 지역을 수신처로 가지면 지역별 이벤트로 분리한다(특보 소스와 동일 패턴).
            for sido, sigungu in _parse_regions(str(row.get("RCPTN_RGN_NM", ""))):
                events.append(
                    NormalizedEvent(
                        source=self.source,
                        event_type=EventType.DISASTER_MESSAGE,
                        severity=None,
                        region_sido=sido,
                        region_sigungu=sigungu,
                        occurred_at=occurred_at,
                        raw_payload=payload,
                    )
                )
        return events

    def _call(self, params: dict) -> tuple[list[dict], int]:
        response = httpx.get(BASE_URL, params=params, timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        data = response.json()

        header = data.get("header", {})
        if header.get("resultCode") not in ("00", None):
            raise RuntimeError(
                f"safetydata disaster API error: {header.get('resultCode')} {header.get('resultMsg')}"
            )

        body = data.get("body")
        rows = body if isinstance(body, list) else []
        total = int(data.get("totalCount") or 0)
        return rows, total


def _parse_regions(rcptn_rgn_nm: str) -> list[tuple[str, str]]:
    """RCPTN_RGN_NM("시도 시군구 [읍면동]", 쉼표로 다지역)을 (시도, 시군구) 목록으로.

    실측 케이스 (2026-07-22):
    - "서울특별시 노원구 "            → ("서울특별시", "노원구")
    - "울산광역시"                    → ("울산광역시", "전체")  # 시도만 온 경우
    - "경기도 고양시 덕양구 ,경기도 고양시 일산동구 " → 시+구 복합은 유지, 지역별 분리
    - "서울특별시 강남구 역삼동"      → ("서울특별시", "강남구")  # 동 단위는 버림(구독은 시군구 단위)
    - "경기도 임진강 ,경기도 임진강"  → ("경기도", "임진강") 1건  # 쉼표 중복 제거
    """
    results: list[tuple[str, str]] = []
    for chunk in rcptn_rgn_nm.split(","):
        tokens = chunk.split()
        if not tokens:
            continue
        sido = tokens[0]
        rest = tokens[1:]
        if not rest:
            sigungu = "전체"
        elif len(rest) >= 2 and rest[0].endswith("시") and rest[1].endswith("구"):
            sigungu = f"{rest[0]} {rest[1]}"  # '고양시 덕양구' 처럼 시+구 복합은 통째로 유지
        else:
            sigungu = rest[0]  # '노원구'/'김포시'; 뒤따르는 동·읍·면은 버린다
        pair = (sido, sigungu)
        if pair not in results:  # 한 문자 내 쉼표 중복 제거
            results.append(pair)
    return results


def _parse_crt_dt(crt_dt) -> datetime:
    """CRT_DT(예: '2026/07/22 11:00:14', KST)를 timezone-aware datetime 으로. 실패 시 현재 시각."""
    try:
        return datetime.strptime(str(crt_dt).strip(), "%Y/%m/%d %H:%M:%S").replace(tzinfo=KST)
    except (ValueError, TypeError):
        return datetime.now(UTC)
