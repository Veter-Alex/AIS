import sys
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "vessel_api"))
import app as vessel_app


class _FakeCursor:
    def __init__(self):
        self._rows = []
        self._single = None

    def execute(self, query, params=None):
        if "FROM source_priority" in query:
            self._rows = [
                {
                    "source_name": "marinetraffic.org",
                    "priority": 1,
                    "description": "main",
                    "is_active": True,
                },
                {
                    "source_name": "orphan-source",
                    "priority": 99,
                    "description": None,
                    "is_active": True,
                },
            ]
            return
        if "FROM scraper_state" in query:
            self._rows = [
                {
                    "scraper_name": "marinetraffic.org",
                    "mode": "full",
                    "last_page": 12,
                    "vessels_count": 120,
                    "last_run_at": datetime(2026, 1, 1, 0, 0, 0),
                },
                {
                    "scraper_name": "unknown_scraper",
                    "mode": "delta",
                    "last_page": 3,
                    "vessels_count": 5,
                    "last_run_at": datetime(2099, 1, 1, 0, 0, 0),
                },
            ]
            return
        if "GROUP BY info_source" in query:
            self._rows = [
                {
                    "info_source": "marinetraffic.org",
                    "last_data_at": datetime(2026, 1, 2, 12, 0, 0),
                }
            ]
            return
        if "COUNT(*) as total" in query:
            self._single = {"total": 1}
            return
        if "COUNT(*) AS total FROM vessels" in query:
            self._single = {"total": 1}
            return
        if "FROM vessels" in query and "LIMIT" in query:
            self._rows = [
                {
                    "id": 1,
                    "name": "TEST VESSEL",
                    "imo": "1234567",
                    "mmsi": "123456789",
                    "call_sign": "TEST1",
                    "general_type": "Cargo",
                    "detailed_type": "Container Ship",
                    "flag": "Panama",
                    "year_built": 2010,
                    "length": 300,
                    "width": 45,
                    "dwt": 120000,
                    "gt": 90000,
                    "home_port": "Panama",
                    "photo_path": None,
                    "description": None,
                    "info_source": "test",
                    "updated_at": None,
                }
            ]
        if query.strip().startswith("SELECT 1"):
            self._single = (1,)
            return

    def fetchone(self):
        return self._single

    def fetchall(self):
        return self._rows


@contextmanager
def _fake_db_cursor(**_kwargs):
    yield _FakeCursor()


def test_get_vessels_smoke(monkeypatch):
    monkeypatch.setattr(vessel_app, "get_db_cursor", _fake_db_cursor)
    client = TestClient(vessel_app.app)
    resp = client.get("/vessels/")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total"] == 1
    assert payload["vessels"][0]["mmsi"] == "123456789"


def test_health_ok():
    client = TestClient(vessel_app.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_ready_ok(monkeypatch):
    monkeypatch.setattr(vessel_app, "get_db_cursor", _fake_db_cursor)
    client = TestClient(vessel_app.app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_ready_503_when_db_unavailable(monkeypatch):
    @contextmanager
    def _broken(**_kwargs):
        raise RuntimeError("db down")
        yield  # pragma: no cover

    monkeypatch.setattr(vessel_app, "get_db_cursor", _broken)
    client = TestClient(vessel_app.app)
    resp = client.get("/ready")
    assert resp.status_code == 503


def test_monitor_scrapers(monkeypatch):
    monkeypatch.setattr(vessel_app, "get_db_cursor", _fake_db_cursor)
    client = TestClient(vessel_app.app)
    resp = client.get("/monitor/scrapers")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["total_scrapers"] == 2
    names = {s["scraper_name"] for s in payload["states"]}
    assert names == {"marinetraffic.org", "unknown_scraper"}


def test_stats_ingestion(monkeypatch):
    monkeypatch.setattr(vessel_app, "get_db_cursor", _fake_db_cursor)
    client = TestClient(vessel_app.app)
    resp = client.get("/stats/ingestion")
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["database"]["ok"] is True
    assert payload["total_vessels"] == 1
    assert len(payload["sources"]) == 2
    mt = next(s for s in payload["sources"] if s["source_name"] == "marinetraffic.org")
    assert len(mt["scrapers"]) == 1
    assert mt["scrapers"][0]["mode"] == "full"
    assert mt["scrapers"][0]["last_data_at"] == "2026-01-02T12:00:00"
    assert len(payload["orphan_scrapers"]) == 1
    assert payload["orphan_scrapers"][0]["scraper_name"] == "unknown_scraper"


def test_metrics_endpoint(monkeypatch):
    monkeypatch.setattr(vessel_app, "get_db_cursor", _fake_db_cursor)
    client = TestClient(vessel_app.app)
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert "ais_vessels_total" in resp.text
