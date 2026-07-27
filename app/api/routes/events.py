from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_ingest_token
from app.database import get_db
from app.models import Event
from app.schemas.event import EventRead
from app.services.ingest import run_ingestion_cycle_guarded

router = APIRouter(prefix="/events", tags=["events"])


@router.post("/ingest", dependencies=[Depends(require_ingest_token)])
def ingest_events(db: Session = Depends(get_db)) -> dict:
    """
    기상특보/지진/홍수특보 소스를 한 번 폴링해서 저장하고, 매칭되는 구독에
    대해 위험도를 평가한다 (project-spec.md 8절 파이프라인 참고).
    API 키가 없는 소스는 자동으로 mock 데이터를 쓴다.

    `X-Ingest-Token` 헤더 필수 (.env 의 INGEST_TOKEN) — 배포 후엔 외부 스케줄러
    (Cloud Scheduler)가 10분마다 이 엔드포인트를 호출하는 게 정상 경로이고,
    아무나 호출하면 공공 API 쿼터·LLM 비용이 낭비되기 때문.

    중복 실행 가드가 있어 최근 수집(기본 3분) 직후 재호출은 스킵된다
    ("skipped": true 응답) — 가드 상태는 ingest_runs 테이블(다중 인스턴스 대응).
    """
    return run_ingestion_cycle_guarded(db)


@router.get("", response_model=list[EventRead])
def list_events(limit: int = 50, db: Session = Depends(get_db)):
    stmt = select(Event).order_by(Event.occurred_at.desc()).limit(limit)
    return list(db.scalars(stmt))
