from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as ai_app


def test_ingest_requires_api_key_when_configured(monkeypatch):
    monkeypatch.setattr(ai_app, "ADMIN_API_KEY", "secret-token")
    monkeypatch.setattr(ai_app, "run_ingestion", lambda **_kwargs: {})
    client = TestClient(ai_app.app)

    resp = client.post("/ingest/run", json={})
    assert resp.status_code == 401


def test_ingest_allows_valid_api_key(monkeypatch):
    monkeypatch.setattr(ai_app, "ADMIN_API_KEY", "secret-token")
    monkeypatch.setattr(
        ai_app,
        "run_ingestion",
        lambda **_kwargs: {
            "job_id": 1,
            "vessels_processed": 0,
            "documents_upserted": 0,
            "chunks_upserted": 0,
        },
    )
    client = TestClient(ai_app.app)

    resp = client.post("/ingest/run", json={}, headers={"x-api-key": "secret-token"})
    assert resp.status_code == 200
    assert resp.json()["job_id"] == 1
