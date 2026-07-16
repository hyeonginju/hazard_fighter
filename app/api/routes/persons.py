from fastapi import APIRouter, Depends
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session

from app import crud
from app.database import get_db
from app.schemas.person import PersonCreate, PersonRead

router = APIRouter(prefix="/persons", tags=["persons"])


class PersonCreateRequest(PersonCreate):
    # TODO: JWT 인증이 붙으면 user_email 대신 인증된 사용자에서 가져온다 (Phase 2+).
    user_email: EmailStr


def _to_read(person) -> PersonRead:
    return PersonRead(
        id=person.id,
        label=person.label,
        age_group=person.age_group,
        created_at=person.created_at,
        tags=[t.tag for t in person.tags],
    )


@router.post("", response_model=PersonRead)
def create_person(payload: PersonCreateRequest, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, payload.user_email)
    person = crud.create_person(db, user, payload.label, payload.age_group, payload.tags)
    return _to_read(person)


@router.get("", response_model=list[PersonRead])
def list_persons(user_email: EmailStr, db: Session = Depends(get_db)):
    user = crud.get_or_create_user(db, user_email)
    return [_to_read(p) for p in crud.list_persons(db, user)]
