from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.region import RegionCreate, RegionRead

router = APIRouter(prefix="/regions", tags=["regions"])


@router.post("", response_model=RegionRead)
def create_region(payload: RegionCreate, db: Session = Depends(get_db)):
    return crud.get_or_create_region(db, payload.sido, payload.sigungu, payload.region_code)


@router.get("", response_model=list[RegionRead])
def list_regions(db: Session = Depends(get_db)):
    return crud.list_regions(db)
