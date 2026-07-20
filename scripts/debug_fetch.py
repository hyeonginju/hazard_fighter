"""
실제 공공 API 응답을 그대로 파일로 저장하는 디버그 스크립트.
_fetch_live()의 필드 매핑을 실제 응답 구조에 맞게 고치기 위한 1회성 도구.

사용법 (가상환경 활성화된 상태에서, 프로젝트 루트에서):
    python scripts/debug_fetch.py

결과: debug_responses/ 폴더에 소스별 응답 저장
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import get_settings  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "debug_responses"
OUT_DIR.mkdir(exist_ok=True)

settings = get_settings()

KST = timezone(timedelta(hours=9))
_today = datetime.now(KST)

TARGETS = [
    {
        "name": "kma_warnings",
        "url": "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnList",
        "params": {
            "serviceKey": settings.kma_warning_api_key,
            "pageNo": 1,
            "numOfRows": 20,
            "dataType": "JSON",
        },
    },
    {
        # 특보 "통보문 상세" — 지역(시군구) 정보가 여기 있을 것으로 추정.
        # 1차 시도(파라미터 없음) → resultCode=11. stnId + 기간을 넣어 재시도.
        "name": "kma_warnings_msg",
        "url": "http://apis.data.go.kr/1360000/WthrWrnInfoService/getWthrWrnMsg",
        "params": {
            "serviceKey": settings.kma_warning_api_key,
            "pageNo": 1,
            "numOfRows": 5,
            "dataType": "JSON",
            "stnId": "108",
            "fromTmFc": (_today - timedelta(days=2)).strftime("%Y%m%d"),
            "toTmFc": _today.strftime("%Y%m%d"),
        },
    },
    {
        # 2026-07-17 확인: fromTmFc/toTmFc 필수 + 최대 조회기간 3일 (resultCode=99)
        "name": "kma_earthquake",
        "url": "http://apis.data.go.kr/1360000/EqkInfoService/getEqkMsg",
        "params": {
            "serviceKey": settings.kma_earthquake_api_key,
            "pageNo": 1,
            "numOfRows": 20,
            "dataType": "JSON",
            "fromTmFc": (_today - timedelta(days=3)).strftime("%Y%m%d"),
            "toTmFc": _today.strftime("%Y%m%d"),
        },
    },
    {
        # 2026-07-17 확인 성공: 전국 1,417개 수위관측소 목록 + 주의/경보 수위 임계치.
        # (4대강 통합 제공 확인 — spec Open Question #6 해결)
        "name": "hrfco_flood_info",
        "url": f"https://api.hrfco.go.kr/{settings.hrfco_api_key}/waterlevel/info.json",
        "params": {},
    },
    {
        # 다음 확인 대상: 특정 관측소의 "실제 수위 데이터" 조회.
        # 표준수문DB 패턴 후보: /{키}/waterlevel/list/{시간단위}/{관측소코드}/{시작}/{종료}.json
        # 관측소 1004616 = 청주시(청석굴교), 최근 3시간, 10분 단위
        "name": "hrfco_waterlevel_list",
        "url": (
            f"https://api.hrfco.go.kr/{settings.hrfco_api_key}/waterlevel/list/10M/1004616/"
            f"{(_today - timedelta(hours=3)).strftime('%Y%m%d%H%M')}/{_today.strftime('%Y%m%d%H%M')}.json"
        ),
        "params": {},
    },
    {
        # 긴급재난문자 (safetydata.go.kr, 키 발급 2026-07-19) — 엔드포인트/파라미터는 추정.
        # safetydata 공통 패턴: /V2/api/{서비스ID}?serviceKey=...&returnType=json
        # DSSP-IF-00247 = 재난문자방송 발령현황(추정) — 에러가 나면 응답 메시지로 스펙 역추적.
        "name": "safetydata_disaster_msg",
        "url": "https://www.safetydata.go.kr/V2/api/DSSP-IF-00247",
        "params": {
            "serviceKey": settings.safetydata_api_key,
            "returnType": "json",
            "pageNo": 1,
            "numOfRows": 10,
        },
    },
]


def main() -> None:
    for t in TARGETS:
        name = t["name"]
        print(f"\n=== {name} ===")
        if not any(t["params"].get(k) for k in t["params"] if "Key" in k or k == "serviceKey"):
            pass  # serviceKey 비었어도 일단 호출해서 에러 응답이라도 저장
        try:
            r = httpx.get(t["url"], params=t["params"], timeout=15.0, follow_redirects=True)
            print(f"HTTP {r.status_code}  content-type: {r.headers.get('content-type')}")
            body = r.text
            # JSON이면 예쁘게, 아니면 원문 그대로 저장
            try:
                parsed = r.json()
                out = OUT_DIR / f"{name}.json"
                out.write_text(json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                out = OUT_DIR / f"{name}.txt"
                out.write_text(body, encoding="utf-8")
            print(f"저장됨: {out}")
            print("응답 앞부분:", body[:300].replace("\n", " "))
        except Exception as e:
            err_file = OUT_DIR / f"{name}.error.txt"
            err_file.write_text(f"{type(e).__name__}: {e}", encoding="utf-8")
            print(f"호출 실패: {type(e).__name__}: {e} (저장: {err_file})")

    print("\n완료. debug_responses/ 폴더 내용을 확인하세요.")


if __name__ == "__main__":
    main()
