"""
MVP 스캐폴딩용 최소 CRUD 헬퍼.
인증(JWT)은 아직 없음 — 11절 기술 스택에 있지만 Phase 2+ 항목으로 미룸.
지금은 person 생성 시 user_email로 사용자를 get-or-create 하는 방식으로 단순화.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Person, PersonTag, Region, Subscription, User


def get_or_create_user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def create_person(db: Session, user: User, label: str, age_group: str, tags: list[str]) -> Person:
    person = Person(user_id=user.id, label=label, age_group=age_group)
    db.add(person)
    db.flush()  # person.id 확보
    for tag in tags:
        db.add(PersonTag(person_id=person.id, tag=tag))
    db.commit()
    db.refresh(person)
    return person


def list_persons(db: Session, user: User) -> list[Person]:
    return list(db.scalars(select(Person).where(Person.user_id == user.id)))


def get_or_create_region(db: Session, sido: str, sigungu: str, region_code: str | None) -> Region:
    region = db.scalar(select(Region).where(Region.sido == sido, Region.sigungu == sigungu))
    if region is None:
        region = Region(sido=sido, sigungu=sigungu, region_code=region_code)
        db.add(region)
        db.commit()
        db.refresh(region)
    return region


def list_regions(db: Session) -> list[Region]:
    return list(db.scalars(select(Region)))


def create_subscription(db: Session, user: User, person_id: uuid.UUID, region_id: uuid.UUID) -> Subscription:
    subscription = Subscription(user_id=user.id, person_id=person_id, region_id=region_id)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def list_subscriptions(db: Session, user: User) -> list[Subscription]:
    return list(db.scalars(select(Subscription).where(Subscription.user_id == user.id)))
