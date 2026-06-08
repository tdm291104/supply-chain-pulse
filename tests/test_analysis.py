import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.analysis import SupplyChainAnalyzer
from data.seed_db import seed
from db.database import Database


@pytest.fixture
def seeded_db():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))
        yield db
        db.close()


@pytest.fixture
def fake_gemini_high_severity():
    gemini = MagicMock()
    gemini.generate_json.return_value = {
        "severity": "HIGH",
        "affected_skus": ["SKU-C01"],
        "risk_sources": ["weather", "supplier_delay", "inventory"],
        "summary": "Three converging signals threaten SKU-C01 supply.",
        "recommended_actions": [
            {"action": "Emergency order from Vertex Fabrics (SUP-002)",
             "impact": "Risk reduction: HIGH -> LOW", "cost_delta": "+3.8%"}
        ],
        "requires_approval": True,
    }
    return gemini


@pytest.mark.asyncio
async def test_run_post_sync_analysis_creates_alert_for_high_severity(seeded_db, fake_gemini_high_severity):
    mcp = MagicMock()
    mcp.get_connection_details = AsyncMock(return_value={"id": "conn_orders_001", "status": "connected"})

    analyzer = SupplyChainAnalyzer(db=seeded_db, mcp=mcp, gemini=fake_gemini_high_severity)
    report = await analyzer.run_post_sync_analysis("conn_orders_001")

    assert report is not None
    assert report.severity == "HIGH"
    assert "SKU-C01" in report.affected_skus

    alerts = seeded_db.query("SELECT * FROM risk_alerts WHERE severity = 'HIGH'")
    assert len(alerts) == 1
    assert alerts["status"][0] == "OPEN"
    mcp.get_connection_details.assert_awaited_once_with("conn_orders_001", triggered_by="webhook")


@pytest.mark.asyncio
async def test_run_post_sync_analysis_skips_alert_for_low_severity(seeded_db):
    mcp = MagicMock()
    mcp.get_connection_details = AsyncMock(return_value={"id": "conn_orders_001", "status": "connected"})
    gemini = MagicMock()
    gemini.generate_json.return_value = {
        "severity": "LOW",
        "affected_skus": [],
        "risk_sources": [],
        "summary": "No significant risk detected.",
        "recommended_actions": [],
        "requires_approval": False,
    }

    analyzer = SupplyChainAnalyzer(db=seeded_db, mcp=mcp, gemini=gemini)
    report = await analyzer.run_post_sync_analysis("conn_orders_001")

    assert report.severity == "LOW"
    alerts = seeded_db.query("SELECT * FROM risk_alerts")
    assert len(alerts) == 0
