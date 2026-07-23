from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import crud
from app.api.deps import get_current_user
from app.database import get_db
from app.models import User
from app.schemas.person import PersonCreate, PersonRead

router = APIRouter(prefix="/persons", tags=["persons"])


def _to_read(person) -> PersonRead:
    return PersonRead(
        id=person.id,
        label=person.label,
        age_group=person.age_group,
        created_at=person.created_at,
        tags=[t.tag for t in person.tags],
    )


@router.post("", response_model=PersonRead)
def create_person(
    payload: PersonCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    try:
        person = crud.create_person(db, user, payload.label, payload.age_group, payload.tags)
    except crud.PersonLimitExceeded as e:
        raise HTTPException(status_code=409, detail=str(e))
    return _to_read(person)


@router.get("", response_model=list[PersonRead])
def list_persons(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return [_to_read(p) for p in crud.list_persons(db, user)]
