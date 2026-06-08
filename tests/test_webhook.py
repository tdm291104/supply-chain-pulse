import hashlib
import hmac
import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from data.seed_db import seed
from db.database import Database

WEBHOOK_SECRET = "test_secret_32_characters_long!!"


def _signed_payload(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    signature = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, signature


@pytest.fixture
def app_and_mocks(monkeypatch, tmp_path):
    monkeypatch.setenv("WEBHOOK_SECRET", WEBHOOK_SECRET)
    db_path = str(tmp_path / "test.duckdb")
    db = Database(db_path)
    seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))

    analyzer = MagicMock()
    analyzer.run_post_sync_analysis = AsyncMock(return_value=None)

    executor = MagicMock()
    executor.switch_primary_supplier = AsyncMock()
    executor.increase_monitoring_frequency = AsyncMock()

    app = create_app(db=db, analyzer=analyzer, executor=executor, webhook_secret=WEBHOOK_SECRET)
    return app, analyzer, executor, db


def test_webhook_rejects_bad_signature(app_and_mocks):
    app, analyzer, _, _ = app_and_mocks
    client = TestClient(app)
    body, _ = _signed_payload({"event": "sync_end", "data": {"connection_id": "conn_orders_001", "status": "successful"}})
    resp = client.post("/webhook/fivetran", content=body, headers={"X-Fivetran-Signature": "wrong"})
    assert resp.status_code == 401
    analyzer.run_post_sync_analysis.assert_not_awaited()


def test_webhook_schedules_analysis_on_successful_sync(app_and_mocks):
    app, analyzer, _, _ = app_and_mocks
    client = TestClient(app)
    body, signature = _signed_payload({"event": "sync_end", "data": {"connection_id": "conn_orders_001", "status": "successful", "sync_id": "sync_123"}})
    resp = client.post("/webhook/fivetran", content=body, headers={"X-Fivetran-Signature": signature})
    assert resp.status_code == 200
    assert resp.json() == {"status": "received"}
    analyzer.run_post_sync_analysis.assert_awaited_once_with("conn_orders_001")


def test_webhook_ignores_non_sync_end_events(app_and_mocks):
    app, analyzer, _, _ = app_and_mocks
    client = TestClient(app)
    body, signature = _signed_payload({"event": "sync_start", "data": {"connection_id": "conn_orders_001", "status": "running"}})
    resp = client.post("/webhook/fivetran", content=body, headers={"X-Fivetran-Signature": signature})
    assert resp.status_code == 200
    analyzer.run_post_sync_analysis.assert_not_awaited()


def test_approve_route_invokes_executor(app_and_mocks):
    app, _, executor, db = app_and_mocks
    db.execute("""
        INSERT INTO risk_alerts VALUES
        ('alert_test02', current_timestamp, 'HIGH', ['SKU-C01'], 'inventory',
         'desc', 'Switch to SUP-002 + increase monitoring', 'OPEN', NULL, NULL)
    """)
    executor.switch_primary_supplier.return_value = MagicMock(success=True, detail="done")
    client = TestClient(app)

    resp = client.post("/actions/approve/alert_test02", json={"approved_by": "demo_user", "action": "switch_supplier"})

    assert resp.status_code == 200
    assert resp.json()["success"] is True
    rows = db.query("SELECT status FROM risk_alerts WHERE alert_id = 'alert_test02'")
    assert rows["status"][0] == "APPROVED"
    executor.switch_primary_supplier.assert_awaited_once()
