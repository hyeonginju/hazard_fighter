"""
Layer 2 (LLM 위험도 보조 판단) 실데이터 데모 — 로컬 서버(localhost:8000) 대상.

하는 일:
1. 발효 중인 이벤트에서 "호우특보" 지역을 찾는다 (매트릭스에 '성인+태그없음' 규칙이 없는 케이스)
2. 태그 없는 성인 인물을 만들고 그 지역을 구독 → 소급 평가에서 Layer 2 가 발동
3. ai_risk_logs 와 알림 결과를 출력

사용법 (서버가 떠 있는 상태에서):
    python scripts/demo_layer2.py
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

BASE = "http://localhost:8000"
EMAIL = "layer2demo@example.com"


def main() -> None:
    # 1. 호우특보 이벤트 찾기
    events = httpx.get(f"{BASE}/events", params={"limit": 100}, timeout=10).json()
    rain = [e for e in events if e["event_type"] == "호우특보" and e["region_id"]]
    if not rain:
        print("지금 발효 중인 호우특보(지역 매칭된)가 없습니다. 다른 특보 상황에서 다시 시도하세요.")
        print("현재 이벤트 유형:", sorted({e['event_type'] for e in events}))
        return
    region_id = rain[0]["region_id"]

    regions = {r["id"]: r for r in httpx.get(f"{BASE}/regions", timeout=10).json()}
    region = regions.get(region_id, {})
    print(f"호우특보 지역 발견: {region.get('sido')} {region.get('sigungu')} ({region_id})")

    # 2. 태그 없는 성인 인물 + 구독 생성 (소급 평가에서 Layer 2 발동 지점)
    person = httpx.post(
        f"{BASE}/persons",
        json={"user_email": EMAIL, "label": "데모성인", "age_group": "성인", "tags": []},
        timeout=10,
    ).json()
    print(f"인물 생성: {person['label']} ({person['age_group']}, 태그 없음)")

    print("구독 생성 → 소급 평가 실행 중 (LLM 호출 포함, 수 초 걸릴 수 있음)...")
    httpx.post(
        f"{BASE}/subscriptions",
        json={"user_email": EMAIL, "person_id": person["id"], "region_id": region_id},
        timeout=60,
    ).raise_for_status()

    # 3. 결과 확인 — ai_risk_logs 는 API 가 없어 DB 직접 조회
    from sqlalchemy import select

    from app.database import SessionLocal
    from app.models import AIRiskLog

    db = SessionLocal()
    try:
        logs = list(db.scalars(select(AIRiskLog).order_by(AIRiskLog.created_at.desc()).limit(5)))
    finally:
        db.close()

    print()
    if not logs:
        print("ai_risk_logs 가 비어 있음 — Layer 2 가 발동하지 않았습니다 (LLM 실패로 판단 보류였을 수도).")
    else:
        print("=== Layer 2 판단 기록 (최신순) ===")
        for log in logs:
            print(f"[{log.risk_level}] model={log.model}")
            print(f"  근거: {log.rationale}")

    notifications = httpx.get(
        f"{BASE}/notifications", params={"user_email": EMAIL}, timeout=10
    ).json()
    print()
    print(f"=== 이 데모 사용자의 알림 ({len(notifications)}건) ===")
    for n in notifications:
        print(f"[{n['risk_level']}/{n['risk_source']}] {n['message']}")
    if not notifications:
        print("(알림 없음 — Layer 2 가 LOW 로 판단했다면 정상: 기록만 남기고 알림은 안 보냄)")


if __name__ == "__main__":
    main()
