# tests/test_mcp_logging.py
import json
import os
import tempfile

from fivetran_mcp.logging import log_call


def test_log_call_appends_jsonl_line():
    with tempfile.TemporaryDirectory() as tmp:
        log_path = os.path.join(tmp, "tool_calls.jsonl")
        log_call(
            log_path,
            tool="sync_connection",
            params={"connection_id": "conn_orders_001"},
            result={"status": "success", "job_id": "job_abc123"},
            duration_ms=847,
            triggered_by="user",
        )
        log_call(
            log_path,
            tool="list_connections",
            params={},
            result={"count": 4},
            duration_ms=120,
            triggered_by="agent",
        )

        with open(log_path) as f:
            lines = [json.loads(line) for line in f if line.strip()]

        assert len(lines) == 2
        assert lines[0]["tool"] == "sync_connection"
        assert lines[0]["triggered_by"] == "user"
        assert lines[0]["params"]["connection_id"] == "conn_orders_001"
        assert "timestamp" in lines[0]
        assert lines[1]["tool"] == "list_connections"
