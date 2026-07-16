"""
project-spec.md 3절(인물 프로필 태그 체계), 9절(데이터 모델) 참고.
persons: id, user_id, label, age_group, created_at
person_tags: id, person_id, tag
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Person(Base):
    __tablename__ = "persons"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(50), nullable=False)  # 예: "부모님", "본인", "자녀"
    age_group: Mapped[str] = mapped_column(String(20), nullable=False)  # enums.AgeGroup 값
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship(back_populates="persons")
    tags: Mapped[list["PersonTag"]] = relationship(back_populates="person", cascade="all, delete-orphan")
    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="person", cascade="all, delete-orphan")


class PersonTag(Base):
    __tablename__ = "person_tags"
    __table_args__ = (UniqueConstraint("person_id", "tag", name="uq_person_tag"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("persons.id", ondelete="CASCADE"), nullable=False)
    tag: Mapped[str] = mapped_column(String(30), nullable=False)  # enums.ConsiderationTag 값

    person: Mapped["Person"] = relationship(back_populates="tags")
