"""
소셜 로그인 사용자 모델 + 보호 대상 상한 테스트.

- (auth_provider, provider_user_id) 쌍으로 사용자 식별 (이메일 미수집)
- 계정당 보호 대상 상한(person_limit, 기본 3) — 남용 방지의 실질 방어선
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import crud
from app.database import Base
from app.models.enums import AgeGroup


@pytest.fixture()
def db():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()


# --- 소셜 사용자 get-or-create ------------------------------------------------

def test_social_user_created_and_reused(db):
    user = crud.get_or_create_social_user(db, "google", "sub-123", "형인")
    again = crud.get_or_create_social_user(db, "google", "sub-123", "형인")
    assert user.id == again.id
    assert user.email is None  # 이메일은 수집하지 않는다


def test_same_provider_id_on_other_provider_is_different_user(db):
    # 회원번호는 프로바이더 안에서만 유일 — 쌍이 달라지면 다른 계정
    google = crud.get_or_create_social_user(db, "google", "1000")
    kakao = crud.get_or_create_social_user(db, "kakao", "1000")
    assert google.id != kakao.id


def test_nickname_refreshed_on_relogin(db):
    crud.get_or_create_social_user(db, "kakao", "42", "옛닉네임")
    user = crud.get_or_create_social_user(db, "kakao", "42", "새닉네임")
    assert user.nickname == "새닉네임"


# --- 보호 대상 상한 -----------------------------------------------------------

def _add_person(db, user, label):
    return crud.create_person(db, user, label, AgeGroup.SENIOR, [])


def test_person_limit_default_three(db):
    user = crud.get_or_create_social_user(db, "google", "limit-user")
    for i in range(3):
        _add_person(db, user, f"보호대상{i}")

    with pytest.raises(crud.PersonLimitExceeded):
        _add_person(db, user, "네번째")

    assert len(crud.list_persons(db, user)) == 3


def test_person_limit_raised_by_coupon(db):
    # 추후 유료 쿠폰이 person_limit 을 올리는 시나리오 — 값만 바꾸면 상한이 따라간다
    user = crud.get_or_create_social_user(db, "google", "coupon-user")
    user.person_limit = 5
    db.commit()

    for i in range(5):
        _add_person(db, user, f"보호대상{i}")
    with pytest.raises(crud.PersonLimitExceeded):
        _add_person(db, user, "여섯번째")


def test_person_limit_is_per_user(db):
    a = crud.get_or_create_social_user(db, "google", "user-a")
    b = crud.get_or_create_social_user(db, "kakao", "user-b")
    for i in range(3):
        _add_person(db, a, f"a{i}")
    # a 가 꽉 차도 b 는 영향 없음
    _add_person(db, b, "b0")
    assert len(crud.list_persons(db, b)) == 1
