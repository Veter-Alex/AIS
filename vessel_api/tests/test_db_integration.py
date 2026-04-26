"""Интеграция с PostgreSQL: по умолчанию пропускается.

Запуск локально / в CI с сервисом Postgres:
  RUN_DB_INTEGRATION_TESTS=1 pytest vessel_api/tests/test_db_integration.py -q

Переменные POSTGRES_* должны указывать на доступную БД с применёнными
миграциями (alembic upgrade head).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))
sys.path.insert(0, str(_REPO_ROOT / "vessel_api"))

pytestmark = pytest.mark.skipif(
    not os.environ.get("RUN_DB_INTEGRATION_TESTS"),
    reason="RUN_DB_INTEGRATION_TESTS не задан",
)


def test_ready_with_real_database():
    import app as vessel_app

    client = TestClient(vessel_app.app)
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"
