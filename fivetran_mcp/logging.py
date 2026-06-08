# fivetran_mcp/logging.py
"""Appends one JSON line per Fivetran MCP tool call to a log file.

This file is the audit trail shown live in the demo and asserted
against by the end-to-end test.
"""
import json
import os
from datetime import datetime, timezone
from typing import Any, Literal

TriggeredBy = Literal["webhook", "user", "agent"]


def log_call(
    log_path: str,
    *,
    tool: str,
    params: dict[str, Any],
    result: dict[str, Any],
    duration_ms: int,
    triggered_by: TriggeredBy,
) -> None:
    os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "params": params,
        "result": result,
        "duration_ms": duration_ms,
        "triggered_by": triggered_by,
    }
    with open(log_path, "a") as f:
        f.write(json.dumps(entry) + "\n")
