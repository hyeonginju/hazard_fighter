import uuid
from datetime import datetime

from sqlalchemy import DateTime, Integer, String, UniqueConstraint, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"
    # 소셜 로그인 사용자는 (auth_provider, provider_user_id)로 식별한다.
    # 프로바이더 회원번호는 프로바이더 안에서만 유일하므로 반드시 쌍으로 유니크.
    __table_args__ = (
        UniqueConstraint("auth_provider", "provider_user_id", name="uq_users_provider_identity"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # 소셜 로그인 전환(2026-07-23)으로 nullable — 카카오는 이메일 수집에 비즈 앱이 필요해
    # 이메일을 아예 받지 않는다. 기존 user_email 방식 사용자만 값이 있다.
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    auth_provider: Mapped[str | None] = mapped_column(String(20), nullable=True)  # "google" | "kakao"
    provider_user_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    nickname: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # 계정당 보호 대상 상한 (남용 방지의 실질 방어선). 기본 3명 — 추후 유료 쿠폰이 이 값을 올린다.
    person_limit: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    persons: Mapped[list["Person"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    device_tokens: Mapped[list["DeviceToken"]] = relationship(back_populates="user", cascade="all, delete-orphan")
