"""
API 키가 없을 때 mock 데이터로 정상 동작하는지 확인 (base.py의 fetch() 분기 로직).
"""
from app.ingestion.hrfco_flood import HrfcoFloodClient
from app.ingestion.kma_earthquake import KmaEarthquakeClient
from app.ingestion.kma_warnings import KmaWarningClient
from app.ingestion.safety_disaster import SafetyDisasterMessageClient


def test_kma_warning_client_falls_back_to_mock_without_key():
    client = KmaWarningClient(api_key=None)
    events = client.fetch()
    assert len(events) >= 1
    assert events[0].raw_payload.get("mock") is True


def test_kma_earthquake_client_falls_back_to_mock_without_key():
    client = KmaEarthquakeClient(api_key=None)
    events = client.fetch()
    assert len(events) >= 1
    assert events[0].magnitude is not None


def test_hrfco_flood_client_falls_back_to_mock_without_key():
    client = HrfcoFloodClient(api_key=None)
    events = client.fetch()
    assert len(events) >= 1
    assert events[0].station_code is not None


def test_safety_disaster_client_falls_back_to_mock_without_key():
    client = SafetyDisasterMessageClient(api_key=None)
    events = client.fetch()
    assert len(events) >= 1
    assert events[0].raw_payload.get("mock") is True
    assert events[0].raw_payload.get("MSG_CN")  # 문구 생성이 쓸 원문이 담겨 있어야 함
