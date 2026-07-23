"""
MVP 스캐폴딩용 최소 CRUD 헬퍼.
인증(JWT)은 아직 없음 — 11절 기술 스택에 있지만 Phase 2+ 항목으로 미룸.
지금은 person 생성 시 user_email로 사용자를 get-or-create 하는 방식으로 단순화.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DeviceToken, Person, PersonTag, Region, Subscription, User


class PersonLimitExceeded(Exception):
    """계정당 보호 대상 상한(users.person_limit) 초과. 라우트에서 409로 변환."""

    def __init__(self, limit: int):
        self.limit = limit
        super().__init__(f"보호 대상은 최대 {limit}명까지 등록할 수 있어요.")


def get_or_create_user(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def get_or_create_social_user(
    db: Session, provider: str, provider_user_id: str, nickname: str | None = None
) -> User:
    """소셜 로그인 사용자 get-or-create. 식별자는 (provider, 프로바이더 회원번호) 쌍.

    이메일은 받지 않는다 — 카카오는 이메일 수집에 비즈 앱 전환이 필요하고,
    구글·카카오를 같이 쓰는 이상 이메일로 계정을 자동 통합하는 건 탈취 벡터라 하지 않는다.
    닉네임은 화면 표시용으로만 저장하고, 재로그인 시 최신 값으로 갱신한다.
    """
    user = db.scalar(
        select(User).where(User.auth_provider == provider, User.provider_user_id == provider_user_id)
    )
    if user is None:
        user = User(auth_provider=provider, provider_user_id=provider_user_id, nickname=nickname)
        db.add(user)
        db.commit()
        db.refresh(user)
    elif nickname and user.nickname != nickname:
        user.nickname = nickname
        db.commit()
    return user


def create_person(db: Session, user: User, label: str, age_group: str, tags: list[str]) -> Person:
    # 계정당 상한 검사 — 무분별한 구독 남용의 실질 방어선 (알림 1건마다 LLM 호출이 따라오므로)
    count = len(list_persons(db, user))
    if count >= user.person_limit:
        raise PersonLimitExceeded(user.person_limit)

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


# 시도명 표준화: 행정구역 공식명(부산광역시)과 기상청 통보문 표기(부산)를 같은 키로.
# 접두어 매칭이라 '전북특별자치도'/'전북자치도'/'전라북도' 가 모두 '전북'으로 모인다.
_SIDO_PREFIX_TO_KEY = (
    ("서울", "서울"), ("부산", "부산"), ("대구", "대구"), ("인천", "인천"),
    ("광주", "광주"), ("대전", "대전"), ("울산", "울산"), ("세종", "세종"),
    ("경기", "경기"), ("강원", "강원"),
    ("충청북", "충북"), ("충북", "충북"), ("충청남", "충남"), ("충남", "충남"),
    ("전라북", "전북"), ("전북", "전북"), ("전라남", "전남"), ("전남", "전남"),
    ("경상북", "경북"), ("경북", "경북"), ("경상남", "경남"), ("경남", "경남"),
    ("제주", "제주"),
)


def canonical_sido(sido: str) -> str:
    cleaned = sido.strip()
    for prefix, key in _SIDO_PREFIX_TO_KEY:
        if cleaned.startswith(prefix):
            return key
    return cleaned


def regions_match(sub_region: Region, event_region: Region) -> bool:
    """구독 지역(사용자가 고른 행정구역명)과 이벤트 지역(공공 API의 예보구역명)이
    같은 곳을 가리키는지 판정한다.

    이름이 글자까지 같아야 하는 region_id 동일성 대신 3단계 규칙:
    ① 시도를 표준화해 비교 (부산광역시 ↔ 부산, 전북특별자치도 ↔ 전북자치도)
    ② 어느 한쪽이 '전체'(시도 단위 특보)면 시도만 맞으면 매칭
    ③ 시군구는 접두어 비교 — '경주(시)' 구독이 기상청 분할 구역 '경주남부'·'경주서부'에 매칭.
       같은 시도 안에서만 비교하므로 다른 도의 동명(경남 고성 vs 강원 고성)은 ①에서 걸러진다.
    한계: '제주도산지'처럼 행정구역과 무관한 예보구역은 접두어로도 못 잡는다 (region_code TODO).
    """
    if canonical_sido(sub_region.sido) != canonical_sido(event_region.sido):
        return False
    if sub_region.sigungu == "전체" or event_region.sigungu == "전체":
        return True
    a = normalize_sigungu(sub_region.sigungu)
    b = normalize_sigungu(event_region.sigungu)
    return a.startswith(b) or b.startswith(a)


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
