# fivetran_mcp/client.py
"""Unified async interface over the Fivetran MCP server.

USE_MOCK_MCP=true (default) routes every call through an in-process mock
backend backed by JSON fixtures. USE_MOCK_MCP=false routes through the
real fivetran-mcp server via the `mcp` SDK. Agent code calls this client
identically either way — only this module knows which backend is active.
"""
import asyncio
import json
import os
import random
import time
import uuid
from typing import Any, Literal

from fivetran_mcp.logging import log_call

TriggeredBy = Literal["webhook", "user", "agent"]

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


class MCPError(Exception):
    def __init__(self, message: str, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _load_fixture(name: str) -> Any:
    with open(os.path.join(FIXTURES_DIR, f"{name}.json")) as f:
        return json.load(f)


class _MockBackend:
    """In-process mock of the Fivetran MCP tool surface, fixture-backed."""

    def __init__(self):
        self._connections = {c["id"]: dict(c) for c in _load_fixture("connections")["connections"]}
        self._details = {k: dict(v) for k, v in _load_fixture("connection_details").items()}
        self._sync_template = _load_fixture("sync_result")

    async def _latency(self):
        await asyncio.sleep(random.uniform(0.2, 0.9))

    async def list_connections(self) -> list[dict]:
        await self._latency()
        return list(self._connections.values())

    async def get_connection_details(self, connection_id: str) -> dict:
        await self._latency()
        if connection_id not in self._details:
            raise MCPError(f"Unknown connection: {connection_id}")
        return self._details[connection_id]

    async def get_connection_state(self, connection_id: str) -> dict:
        await self._latency()
        details = self._details.get(connection_id)
        if details is None:
            raise MCPError(f"Unknown connection: {connection_id}")
        return {"connection_id": connection_id, "state": details["status"]}

    async def get_connection_schema_config(self, connection_id: str) -> dict:
        await self._latency()
        details = self._details.get(connection_id)
        if details is None:
            raise MCPError(f"Unknown connection: {connection_id}")
        return {"connection_id": connection_id, "schema": details["schema"]}

    async def list_transformation_projects(self) -> list[dict]:
        await self._latency()
        return [{"id": "tp_dbt_001", "name": "supply_chain_transforms", "status": "ready"}]

    async def sync_connection(self, connection_id: str) -> dict:
        await self._latency()
        if connection_id not in self._connections:
            raise MCPError(f"Unknown connection: {connection_id}")
        return {
            "status": self._sync_template["status"],
            "job_id": f"{self._sync_template['job_id_prefix']}{uuid.uuid4().hex[:8]}",
            "connection_id": connection_id,
        }

    async def modify_connection(self, connection_id: str, frequency_minutes: int) -> dict:
        await self._latency()
        conn = self._connections.get(connection_id)
        if conn is None:
            raise MCPError(f"Unknown connection: {connection_id}")
        conn["frequency_minutes"] = frequency_minutes
        return {"connection_id": connection_id, "frequency_minutes": frequency_minutes, "status": "updated"}

    async def create_connection(self, config: dict) -> dict:
        await self._latency()
        new_id = f"conn_{config.get('name', 'new')}_{uuid.uuid4().hex[:6]}"
        record = {"id": new_id, "name": config.get("name", "new_connection"),
                  "service": config.get("service", "rest_api"), "status": "connected",
                  "frequency_minutes": config.get("frequency_minutes", 360)}
        self._connections[new_id] = record
        return record

    async def create_account_webhook(self, url: str, secret: str) -> dict:
        await self._latency()
        return {"id": f"webhook_{uuid.uuid4().hex[:8]}", "url": url, "events": ["sync_end"], "active": True}

    async def run_transformation(self, project_id: str) -> dict:
        await self._latency()
        return {"project_id": project_id, "status": "started", "run_id": f"run_{uuid.uuid4().hex[:8]}"}


class FivetranMCPClient:
    """Single interface for all Fivetran MCP calls, with logging."""

    def __init__(self, log_path: str = "logs/tool_calls.jsonl"):
        self._log_path = log_path
        use_mock = os.environ.get("USE_MOCK_MCP", "true").lower() == "true"
        if not use_mock:
            raise NotImplementedError(
                "Real Fivetran MCP backend not wired up yet — set USE_MOCK_MCP=true"
            )
        self._backend = _MockBackend()

    async def _call(self, tool: str, triggered_by: TriggeredBy, params: dict, coro):
        start = time.monotonic()
        try:
            result = await coro
        except MCPError as e:
            log_call(self._log_path, tool=tool, params=params,
                     result={"status": "error", "message": str(e), "retryable": e.retryable},
                     duration_ms=int((time.monotonic() - start) * 1000), triggered_by=triggered_by)
            raise
        log_call(self._log_path, tool=tool, params=params, result=result,
                 duration_ms=int((time.monotonic() - start) * 1000), triggered_by=triggered_by)
        return result

    async def list_connections(self, *, triggered_by: TriggeredBy) -> list[dict]:
        return await self._call("list_connections", triggered_by, {}, self._backend.list_connections())

    async def get_connection_details(self, connection_id: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("get_connection_details", triggered_by, {"connection_id": connection_id},
                                 self._backend.get_connection_details(connection_id))

    async def get_connection_state(self, connection_id: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("get_connection_state", triggered_by, {"connection_id": connection_id},
                                 self._backend.get_connection_state(connection_id))

    async def get_connection_schema_config(self, connection_id: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("get_connection_schema_config", triggered_by, {"connection_id": connection_id},
                                 self._backend.get_connection_schema_config(connection_id))

    async def list_transformation_projects(self, *, triggered_by: TriggeredBy) -> list[dict]:
        return await self._call("list_transformation_projects", triggered_by, {},
                                 self._backend.list_transformation_projects())

    async def sync_connection(self, connection_id: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("sync_connection", triggered_by, {"connection_id": connection_id},
                                 self._backend.sync_connection(connection_id))

    async def modify_connection(self, connection_id: str, frequency_minutes: int, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("modify_connection", triggered_by,
                                 {"connection_id": connection_id, "frequency_minutes": frequency_minutes},
                                 self._backend.modify_connection(connection_id, frequency_minutes))

    async def create_connection(self, config: dict, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("create_connection", triggered_by, {"config": config},
                                 self._backend.create_connection(config))

    async def create_account_webhook(self, url: str, secret: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("create_account_webhook", triggered_by, {"url": url},
                                 self._backend.create_account_webhook(url, secret))

    async def run_transformation(self, project_id: str, *, triggered_by: TriggeredBy) -> dict:
        return await self._call("run_transformation", triggered_by, {"project_id": project_id},
                                 self._backend.run_transformation(project_id))
