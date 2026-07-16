"""
regions: id, sido, sigungu, region_code(기상청 특보 코드 매핑용)
project-spec.md 9절 참고.
"""
import uuid

from sqlalchemy import String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Region(Base):
    __tablename__ = "regions"
    __table_args__ = (UniqueConstraint("sido", "sigungu", name="uq_region_sido_sigungu"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    sido: Mapped[str] = mapped_column(String(20), nullable=False)  # 예: "대전광역시"
    sigungu: Mapped[str] = mapped_column(String(30), nullable=False)  # 예: "유성구"
    region_code: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)  # 기상청 특보 코드

    subscriptions: Mapped[list["Subscription"]] = relationship(back_populates="region")
    events: Mapped[list["Event"]] = relationship(back_populates="region")
    gauge_maps: Mapped[list["GaugeRegionMap"]] = relationship(back_populates="region")
