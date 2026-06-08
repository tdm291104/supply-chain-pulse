# tests/test_mcp_client.py
import json
import os
import tempfile

import pytest

from fivetran_mcp.client import FivetranMCPClient, MCPError


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("USE_MOCK_MCP", "true")
    log_path = str(tmp_path / "tool_calls.jsonl")
    return FivetranMCPClient(log_path=log_path), log_path


@pytest.mark.asyncio
async def test_list_connections_returns_four_and_logs(client):
    c, log_path = client
    connections = await c.list_connections(triggered_by="user")
    assert len(connections) == 4
    ids = {conn["id"] for conn in connections}
    assert "conn_orders_001" in ids

    with open(log_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert lines[-1]["tool"] == "list_connections"
    assert lines[-1]["triggered_by"] == "user"


@pytest.mark.asyncio
async def test_sync_connection_returns_job_id_and_logs(client):
    c, log_path = client
    result = await c.sync_connection("conn_orders_001", triggered_by="agent")
    assert result["status"] == "success"
    assert result["job_id"].startswith("job_")

    with open(log_path) as f:
        lines = [json.loads(line) for line in f if line.strip()]
    assert lines[-1]["tool"] == "sync_connection"
    assert lines[-1]["params"]["connection_id"] == "conn_orders_001"


@pytest.mark.asyncio
async def test_modify_connection_changes_frequency_and_logs(client):
    c, _ = client
    result = await c.modify_connection("conn_orders_001", frequency_minutes=15, triggered_by="agent")
    assert result["frequency_minutes"] == 15
    assert result["connection_id"] == "conn_orders_001"


@pytest.mark.asyncio
async def test_unknown_connection_raises_mcp_error(client):
    c, _ = client
    with pytest.raises(MCPError):
        await c.get_connection_details("conn_does_not_exist", triggered_by="agent")
