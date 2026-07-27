"""
모든 모델을 여기서 import 해야 Base.metadata 에 전부 등록되고,
Alembic autogenerate가 테이블을 빠짐없이 인식한다.
"""
from app.models.device_token import DeviceToken
from app.models.event import Event
from app.models.ingest_run import IngestRun
from app.models.notification import Notification
from app.models.person import Person, PersonTag
from app.models.region import Region
from app.models.risk import AIRiskLog, RiskMatrixRule
from app.models.river_gauge import GaugeRegionMap, RiverGauge
from app.models.subscription import Subscription
from app.models.user import User

__all__ = [
    "User",
    "Person",
    "PersonTag",
    "Region",
    "Subscription",
    "DeviceToken",
    "RiskMatrixRule",
    "AIRiskLog",
    "Event",
    "IngestRun",
    "Notification",
    "RiverGauge",
    "GaugeRegionMap",
]
