"""
MVP — 홍수특보 지역 단위 알림 (project-spec.md 6-1절, 9절, Phase 1~2)
river_gauges: id, station_code, name, lat, lng, source(hrfco)
gauge_region_map: id, river_gauge_id, region_id  # 관측소 -> 관할 시군 매핑

Phase 5의 지하차도/교량 정밀 매칭(infra_points, infra_gauge_map)은
2-1a·6-1절 확장 유스케이스이며 MVP에는 포함하지 않는다.
"""
import uuid

from sqlalchemy import ForeignKey, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RiverGauge(Base):
    __tablename__ = "river_gauges"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    station_code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)  # hrfco 관측소 코드
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 예: "미호천교"
    lat: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    lng: Mapped[float] = mapped_column(Numeric(9, 6), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False, default="hrfco")

    region_maps: Mapped[list["GaugeRegionMap"]] = relationship(back_populates="river_gauge")


class GaugeRegionMap(Base):
    __tablename__ = "gauge_region_map"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    river_gauge_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("river_gauges.id", ondelete="CASCADE"), nullable=False)
    region_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("regions.id", ondelete="CASCADE"), nullable=False)

    river_gauge: Mapped["RiverGauge"] = relationship(back_populates="region_maps")
    region: Mapped["Region"] = relationship(back_populates="gauge_maps")
