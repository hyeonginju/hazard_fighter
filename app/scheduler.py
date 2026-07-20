"""
주기 수집 스케줄러 — FastAPI lifespan 에서 asyncio 백그라운드 태스크로 돈다.

설계 (호출량 예산 분석 기준 — docs/dev-learning-notes.md 2026-07-20 항목):
- 기본 10분 주기 = 하루 144사이클. 가장 한도가 빡빡한 긴급재난문자(1,000/일)도 14.4% 수준.
- run_ingestion_cycle_guarded 를 쓰므로 수동 /events/ingest 와 겹쳐도 중복 호출 안 됨.
- 사이클 전체가 실패해도(DB 다운 등) 루프는 죽지 않고 다음 주기에 자연 재시도.
  주기가 10분이라 이 자체가 완만한 백오프 역할을 한다. 소스별 실패는
  run_ingestion_cycle 내부에서 이미 격리돼 응답 errors 로 기록된다.
- 별도 라이브러리(APScheduler 등) 없이 asyncio 만 사용 — 단일 프로세스 MVP 에선
  의존성 하나 줄이는 쪽을 택했다. 다중 인스턴스 배포 시엔 외부 스케줄러
  (Cloud Scheduler → POST /events/ingest)로 전환하고 이 루프는 끄면 된다
  (SCHEDULER_ENABLED=0).

주의: ingestion 클라이언트가 동기(sync) 코드라, 이벤트 루프를 막지 않도록
asyncio.to_thread 로 스레드에서 실행한다.
"""
import asyncio
import logging

from app.config import get_settings
from app.database import SessionLocal
from app.services.ingest import run_ingestion_cycle_guarded

logger = logging.getLogger("hazard_fighter.scheduler")


def _run_cycle_sync() -> dict:
    db = SessionLocal()
    try:
        return run_ingestion_cycle_guarded(db)
    finally:
        db.close()


async def ingest_loop() -> None:
    """서버가 떠 있는 동안 ingest_interval_minutes 마다 수집을 실행한다."""
    settings = get_settings()
    interval_seconds = settings.ingest_interval_minutes * 60
    logger.info("수집 스케줄러 시작 (주기: %d분)", settings.ingest_interval_minutes)

    while True:
        try:
            result = await asyncio.to_thread(_run_cycle_sync)
            if result.get("skipped"):
                logger.info("수집 스킵: %s", result.get("reason"))
            else:
                logger.info(
                    "수집 완료: events=%s dup=%s notifications=%s errors=%s",
                    result.get("events_ingested"),
                    result.get("duplicates_skipped"),
                    result.get("notifications_created"),
                    result.get("errors") or "없음",
                )
        except Exception:  # noqa: BLE001 — 루프는 어떤 실패에도 살아남아야 한다
            logger.exception("수집 사이클 실패 — 다음 주기에 재시도")

        await asyncio.sleep(interval_seconds)
