"""
MVP 스캐폴딩용 최소 CRUD 헬퍼.
인증(JWT)은 아직 없음 — 11절 기술 스택에 있지만 Phase 2+ 항목으로 미룸.
지금은 person 생성 시 user_email로 사용자를 get-or-create 하는 방식으로 단순화.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeviceToken, Person, PersonTag, Region, Subscription, User


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


def normalize_sigungu(sigungu: str) -> str:
    """지역명 매칭용 최소 정규화.

    기상청 통보문은 '광양', 사용자는 '광양시'처럼 다르게 쓸 수 있어 매칭이 깨진다.
    단일 단어 + 3글자 이상 + '시'/'군'으로 끝나면 접미사를 떼서 저장한다
    ('광양시'→'광양', '보령시'→'보령'). '청주시 흥덕구' 같은 복합 표기는 그대로 둔다.
    TODO: 근본 해결은 표준 행정구역 코드(region_code) 기반 매칭 (spec 12절).
    """
    cleaned = sigungu.strip()
    parts = cleaned.split()
    if len(parts) == 1 and len(parts[0]) >= 3 and parts[0].endswith(("시", "군")):
        return parts[0][:-1]
    return cleaned


def get_or_create_region(db: Session, sido: str, sigungu: str, region_code: str | None) -> Region:
    sigungu = normalize_sigungu(sigungu)
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
    """(person, region) 조합은 유니크 — 이미 있으면 기존 구독을 반환한다 (멱등).

    중복 요청을 500(IntegrityError)으로 터뜨리는 대신 get-or-create 로 처리.
    덕분에 같은 구독을 다시 만들어도 안전하고, 소급 평가만 다시 돈다.
    """
    existing = db.scalar(
        select(Subscription).where(
            Subscription.person_id == person_id,
            Subscription.region_id == region_id,
        )
    )
    if existing is not None:
        return existing

    subscription = Subscription(user_id=user.id, person_id=person_id, region_id=region_id)
    db.add(subscription)
    db.commit()
    db.refresh(subscription)
    return subscription


def list_subscriptions(db: Session, user: User) -> list[Subscription]:
    return list(db.scalars(select(Subscription).where(Subscription.user_id == user.id)))


def register_device_token(db: Session, user: User, fcm_token: str, platform: str) -> DeviceToken:
    """푸시 발송 대상 기기 토큰을 등록한다. fcm_token 은 유니크 (멱등).

    같은 토큰을 다시 등록하면(브라우저 재방문·토큰 로테이션) 500 으로 터뜨리지 않고
    소유 사용자·플랫폼만 갱신한다. FCM 토큰은 기기/브라우저마다 유일하므로
    이 토큰이 다른 계정에 붙어 있었다면 현재 사용자로 옮긴다.
    """
    existing = db.scalar(select(DeviceToken).where(DeviceToken.fcm_token == fcm_token))
    if existing is not None:
        existing.user_id = user.id
        existing.platform = platform
        db.commit()
        db.refresh(existing)
        return existing

    token = DeviceToken(user_id=user.id, fcm_token=fcm_token, platform=platform)
    db.add(token)
    db.commit()
    db.refresh(token)
    return token


def list_device_tokens(db: Session, user: User) -> list[DeviceToken]:
    return list(db.scalars(select(DeviceToken).where(DeviceToken.user_id == user.id)))
