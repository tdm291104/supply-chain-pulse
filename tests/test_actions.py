import os
import tempfile
from unittest.mock import AsyncMock, MagicMock

import pytest

from agent.actions import ActionExecutor, NotApprovedError
from data.seed_db import seed
from db.database import Database


@pytest.fixture
def db_with_open_alert():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test.duckdb")
        db = Database(db_path)
        seed(db, data_dir=os.path.join(os.path.dirname(__file__), "..", "data"))
        db.execute("""
            INSERT INTO risk_alerts VALUES
            ('alert_test01', current_timestamp, 'HIGH', ['SKU-C01'], 'weather,supplier_delay,inventory',
             'Three converging signals', 'Switch to SUP-002', 'OPEN', NULL, NULL)
        """)
        yield db
        db.close()


def _mock_mcp():
    mcp = MagicMock()
    mcp.create_connection = AsyncMock(return_value={"id": "conn_vertex_backup", "status": "connected"})
    mcp.modify_connection = AsyncMock(return_value={"connection_id": "conn_orders_001", "frequency_minutes": 15})
    mcp.sync_connection = AsyncMock(return_value={"status": "success", "job_id": "job_xyz"})
    return mcp


@pytest.mark.asyncio
async def test_switch_supplier_requires_approval(db_with_open_alert):
    mcp = _mock_mcp()
    executor = ActionExecutor(db=db_with_open_alert, mcp=mcp)
    with pytest.raises(NotApprovedError):
        await executor.switch_primary_supplier(
            alert_id="alert_test01",
            new_supplier_config={"name": "vertex_backup", "service": "rest_api"},
            approved_by="demo_user",
        )
    mcp.create_connection.assert_not_awaited()


@pytest.mark.asyncio
async def test_switch_supplier_executes_after_approval(db_with_open_alert):
    db_with_open_alert.execute("UPDATE risk_alerts SET status = 'APPROVED' WHERE alert_id = 'alert_test01'")
    mcp = _mock_mcp()
    executor = ActionExecutor(db=db_with_open_alert, mcp=mcp)

    result = await executor.switch_primary_supplier(
        alert_id="alert_test01",
        new_supplier_config={"name": "vertex_backup", "service": "rest_api"},
        approved_by="demo_user",
    )

    assert result.success is True
    mcp.create_connection.assert_awaited_once()
    alerts = db_with_open_alert.query("SELECT status FROM risk_alerts WHERE alert_id = 'alert_test01'")
    assert alerts["status"][0] == "RESOLVED"


@pytest.mark.asyncio
async def test_increase_monitoring_frequency_modifies_each_connection(db_with_open_alert):
    db_with_open_alert.execute("UPDATE risk_alerts SET status = 'APPROVED' WHERE alert_id = 'alert_test01'")
    mcp = _mock_mcp()
    executor = ActionExecutor(db=db_with_open_alert, mcp=mcp)

    result = await executor.increase_monitoring_frequency(
        connection_ids=["conn_orders_001", "conn_inventory_001"],
        new_freq_minutes=15,
        alert_id="alert_test01",
    )

    assert result.success is True
    assert mcp.modify_connection.await_count == 2


@pytest.mark.asyncio
async def test_trigger_emergency_sync_does_not_require_approval(db_with_open_alert):
    mcp = _mock_mcp()
    executor = ActionExecutor(db=db_with_open_alert, mcp=mcp)

    result = await executor.trigger_emergency_sync(connection_ids=["conn_orders_001"])

    assert result.success is True
    mcp.sync_connection.assert_awaited_once_with("conn_orders_001", triggered_by="agent")
