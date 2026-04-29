"""Integration tests for vessel notes sync API."""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "vessel_api"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_SYNC_INTEGRATION_TESTS"),
    reason="RUN_SYNC_INTEGRATION_TESTS не задан",
)


def _create_test_vessel(client: TestClient, suffix: str) -> tuple[str, str]:
    imo = f"9{suffix[:6]}"
    mmsi = f"7{suffix[:8]}"
    payload = {
        "name": f"SYNC TEST {suffix}",
        "imo": imo,
        "mmsi": mmsi,
        "call_sign": f"SC{suffix[:4]}",
        "general_type": "Cargo",
        "detailed_type": "Test Vessel",
        "flag": "Panama",
        "year_built": 2020,
        "length": 100,
        "width": 20,
        "dwt": 10000,
        "gt": 8000,
        "home_port": "Test Port",
        "photo_path": None,
        "description": "integration test",
        "info_source": "integration",
        "updated_at": None,
    }
    resp = client.post("/vessels/", json=payload)
    assert resp.status_code == 200
    return imo, mmsi


def test_notes_pull_push_roundtrip():
    import app as vessel_app

    client = TestClient(vessel_app.app)
    suffix = uuid.uuid4().hex
    imo, _ = _create_test_vessel(client, suffix)

    created = client.post(
        f"/vessels/{imo}/notes",
        json={"body": "Initial note", "author": "offline-user"},
    )
    assert created.status_code == 200
    note = created.json()
    note_uuid = note["note_uuid"]

    pulled = client.post(
        "/sync/notes/pull", json={"since": None, "limit": 100}
    )
    assert pulled.status_code == 200
    pulled_notes = pulled.json()["notes"]
    matched = [n for n in pulled_notes if n["note_uuid"] == note_uuid]
    assert matched

    pushed = client.post(
        "/sync/notes/push",
        json={
            "source_node": "offline-node",
            "notes": [
                {
                    "note_uuid": note_uuid,
                    "vessel_imo_or_mmsi": imo,
                    "body": "Updated from offline node",
                    "author": "offline-user",
                    "source_node": "offline-node",
                    "sync_version": note["sync_version"] + 1,
                    "created_at": note["created_at"],
                    "updated_at": note["updated_at"],
                    "deleted_at": None,
                }
            ],
        },
    )
    assert pushed.status_code == 200
    assert pushed.json()["upserted"] >= 1

    after = client.get(f"/vessels/{imo}/notes")
    assert after.status_code == 200
    notes = after.json()
    assert any(n["body"] == "Updated from offline node" for n in notes)
