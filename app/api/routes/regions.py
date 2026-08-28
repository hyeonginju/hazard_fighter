from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.region import RegionCreate, RegionRead

router = APIRouter(prefix="/regions", tags=["regions"])


@router.post("", response_model=RegionRead)
def create_region(
    payload: RegionCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """행정구역 get-or-create. 구독 폼이 지역을 고를 때 호출한다.

    인증을 붙인 이유 (2026-08-28, 저장소 공개 점검 중 발견):
    이 엔드포인트는 무인증 쓰기였다 — 주소를 아는 누구나 우리 DB 에 행을 만들 수 있었다.
    /docs 가 열려 있어 이미 발견 가능한 상태였고, Neon 무료 한도(100 CU-시간)를
    23일 만에 80% 쓴 상황이라 낙서 트래픽 한 번이 실제로 아프다.
    프런트는 api() 헬퍼가 항상 JWT 를 실어 보내므로 화면 동작에는 변화가 없다.

    GET 은 열어둔다 — 표준 행정구역 조회표라 공개돼도 잃을 게 없고,
    scripts/demo_layer2.py 가 토큰 없이 읽는다. 막을 이유가 없는 문은 막지 않는다.
    """
    return crud.get_or_create_region(db, payload.sido, payload.sigungu, payload.region_code)


@router.get("", response_model=list[RegionRead])
def list_regions(db: Session = Depends(get_db)):
    return crud.list_regions(db)
