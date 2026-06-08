"""Full offline flow: seed perfect-storm data -> webhook -> analysis ->
alert -> approval -> action, asserted against the real mock MCP backend
and a real (temp) DuckDB so the whole wiring is exercised together."""
import hashlib
import hmac
import json
import os
import tempfile
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from agent.actions import ActionExecutor
from agent.analysis import SupplyChainAnalyzer
from api.main import create_app
from data.seed_db import seed
from db.database import Database
from fivetran_mcp.client import FivetranMCPClient

WEBHOOK_SECRET = "e2e_test_secret_32_characters!!!"


def _signed(body: dict) -> tuple[bytes, str]:
    raw = json.dumps(body).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()
    return raw, sig


@pytest.fixture
def perfect_storm_app(monkeypatch, tmp_path):
    monkeypatch.setenv("USE_MOCK_MCP", "true")
    log_path = str(tmp_path / "tool_calls.jsonl")
    db_path = str(tmp_path / "test.duckdb")

    db = Database(db_path)
    seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))

    mcp = FivetranMCPClient(log_path=log_path)

    fake_gemini = MagicMock()
    fake_gemini.generate_json.return_value = {
        "severity": "HIGH",
        "affected_skus": ["SKU-C01"],
        "risk_sources": ["weather", "supplier_delay", "inventory"],
        "summary": "9 days of stock, a 4.2-day average Apex delay, and an "
                   "approaching hurricane converge on SKU-C01.",
        "recommended_actions": [
            {"action": "Switch to Vertex Fabrics (SUP-002) and increase monitoring to 15 min",
             "impact": "Risk reduction: HIGH -> LOW", "cost_delta": "+3.8%"}
        ],
        "requires_approval": True,
    }

    analyzer = SupplyChainAnalyzer(db=db, mcp=mcp, gemini=fake_gemini)
    executor = ActionExecutor(db=db, mcp=mcp)
    app = create_app(db=db, analyzer=analyzer, executor=executor, webhook_secret=WEBHOOK_SECRET)
    return app, db, log_path


def test_perfect_storm_workflow(perfect_storm_app):
    app, db, log_path = perfect_storm_app
    client = TestClient(app)

    body, sig = _signed({"event": "sync_end", "data": {
        "connection_id": "conn_orders_001", "status": "successful", "sync_id": "sync_e2e_001"
    }})
    resp = client.post("/webhook/fivetran", content=body, headers={"X-Fivetran-Signature": sig})
    assert resp.status_code == 200

    alerts = db.query("SELECT * FROM risk_alerts WHERE status = 'OPEN'")
    assert len(alerts) == 1
    assert alerts["severity"][0] == "HIGH"
    assert "SKU-C01" in list(alerts["affected_skus"][0])
    assert "SUP-002" in alerts["recommended_action"][0]
    alert_id = alerts["alert_id"][0]

    approve_resp = client.post(
        f"/actions/approve/{alert_id}",
        json={"approved_by": "demo_user", "action": "increase_monitoring"},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["success"] is True

    with open(log_path) as f:
        tools_called = [json.loads(line)["tool"] for line in f if line.strip()]
    assert "modify_connection" in tools_called

    resolved = db.query(f"SELECT status FROM risk_alerts WHERE alert_id = '{alert_id}'")
    assert resolved["status"][0] == "RESOLVED"
