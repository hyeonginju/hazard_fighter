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

    GET 도 뒤이어 막았다 (같은 날, 과금 표면 점검) — 아래 list_regions 주석 참고.
    """
    return crud.get_or_create_region(db, payload.sido, payload.sigungu, payload.region_code)


@router.get("", response_model=list[RegionRead])
def list_regions(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """읽기에도 인증이 필요하다.

    처음엔 열어뒀다 — 표준 행정구역 목록이라 읽혀서 잃을 게 없다고 봤다. 그 판단은
    "데이터가 민감한가"만 본 것이었고, 축을 하나 놓쳤다: **이 요청은 DB 를 깨운다.**
    Neon 은 요청이 끊기면 5분 뒤 컴퓨트를 재우므로, 누가 4분마다 한 번만 찔러도
    DB 가 24시간 깨어 있고 그대로 CU-시간이 된다(2026-08-23 에 우리 크론이 같은
    방식으로 무료 한도 80% 를 태웠다 — 범인만 남으로 바뀐 것).

    데이터는 여전히 비밀이 아니다. 막는 건 내용이 아니라 **계량기를 돌리는 레버**다.
    """
    return crud.list_regions(db)
