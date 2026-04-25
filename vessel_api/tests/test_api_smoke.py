from contextlib import contextmanager
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as vessel_app


class _FakeCursor:
    def __init__(self):
        self._rows = []
        self._single = None

    def execute(self, query, params=None):
        if "COUNT(*) as total" in query:
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
