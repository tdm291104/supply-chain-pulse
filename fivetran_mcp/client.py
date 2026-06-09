# fivetran_mcp/client.py
"""Unified async interface over the Fivetran MCP server.

USE_MOCK_MCP=true (default) routes every call through an in-process mock
backend backed by JSON fixtures. USE_MOCK_MCP=false connects to the real
fivetran-mcp server (github.com/fivetran/fivetran-mcp) via stdio JSON-RPC,
using live Fivetran API credentials from FIVETRAN_API_KEY / FIVETRAN_API_SECRET.
Agent code calls this client identically either way.
"""
import asyncio
import glob
import json
import os
import random
import subprocess
import threading
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


class _RealBackend:
    """Connects to the real fivetran-mcp server via stdio JSON-RPC subprocess.

    Requires the server to be installable via uvx:
        uvx --from git+https://github.com/fivetran/fivetran-mcp fivetran-mcp
    and FIVETRAN_API_KEY / FIVETRAN_API_SECRET in the environment.
    """

    _MCP_CMD = [
        "uvx", "--from",
        "git+https://github.com/fivetran/fivetran-mcp",
        "fivetran-mcp",
    ]
    _SCHEMAS = {
        "list_connections":             "open-api-definitions/connections/list_connections.json",
        "get_connection_details":       "open-api-definitions/connections/connection_details.json",
        "get_connection_state":         "open-api-definitions/connections/connection_state.json",
        "get_connection_schema_config": "open-api-definitions/connections/connection_schema_config.json",
        "sync_connection":              "open-api-definitions/connections/sync_connection.json",
        "modify_connection":            "open-api-definitions/connections/modify_connection.json",
        "create_connection":            "open-api-definitions/connections/create_connection.json",
        "list_transformation_projects": "open-api-definitions/transformation-projects/list_all_transformation_projects.json",
        "create_account_webhook":       "open-api-definitions/webhooks/create_account_webhook.json",
        "run_transformation":           "open-api-definitions/transformations/run_transformation.json",
    }

    def __init__(self):
        self._cwd = self._find_cwd()
        self._lock = threading.Lock()
        self._proc = None
        self._req_id = 0

    @staticmethod
    def _find_cwd() -> str:
        matches = glob.glob(
            os.path.expanduser(
                "~/.cache/uv/**/open-api-definitions/connections/list_connections.json"
            ),
            recursive=True,
        )
        for m in sorted(matches):
            if "site-packages" in m:
                return m.replace("/open-api-definitions/connections/list_connections.json", "")
        # Fall back to any match
        if matches:
            return matches[0].replace("/open-api-definitions/connections/list_connections.json", "")
        raise RuntimeError(
            "fivetran-mcp schema files not found — run once:\n"
            "  uvx --from git+https://github.com/fivetran/fivetran-mcp fivetran-mcp"
        )

    def _ensure_proc(self):
        if self._proc and self._proc.poll() is None:
            return
        self._proc = subprocess.Popen(
            self._MCP_CMD,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            env=os.environ.copy(),
            cwd=self._cwd,
        )
        self._req_id = 0
        # MCP handshake
        self._rpc(0, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "supply-chain-pulse", "version": "1.0"},
        })

    def _rpc(self, req_id: int, method: str, params: dict) -> dict:
        msg = {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params}
        self._proc.stdin.write((json.dumps(msg) + "\n").encode())
        self._proc.stdin.flush()
        while True:
            line = self._proc.stdout.readline().decode()
            if not line:
                raise MCPError("MCP server closed connection")
            resp = json.loads(line)
            if resp.get("id") == req_id:
                return resp

    def _call_sync(self, tool: str, args: dict) -> dict:
        with self._lock:
            self._ensure_proc()
            self._req_id += 1
            resp = self._rpc(
                self._req_id, "tools/call",
                {"name": tool, "arguments": {"schema_file": self._SCHEMAS[tool], **args}},
            )
            text = resp["result"]["content"][0]["text"]
            if not text.strip():
                return {}
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return {"message": text}

    async def _call(self, tool: str, args: dict | None = None) -> dict:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self._call_sync, tool, args or {})

    # ── Public interface (same signatures as _MockBackend) ────────────────────

    async def list_connections(self) -> list[dict]:
        data = (await self._call("list_connections")).get("data", {})
        result = []
        for item in data.get("items", []):
            st = item.get("status", {})
            setup = st.get("setup_state", "incomplete")
            mapped = "connected" if setup == "connected" else "warning"
            result.append({
                "id": item["id"],
                "name": item.get("schema") or item.get("service", item["id"]),
                "status": mapped,
                "frequency_minutes": item.get("sync_frequency", 360),
            })
        return result

    async def get_connection_details(self, connection_id: str) -> dict:
        return (await self._call("get_connection_details", {"connection_id": connection_id})).get("data", {})

    async def get_connection_state(self, connection_id: str) -> dict:
        d = (await self._call("get_connection_state", {"connection_id": connection_id})).get("data", {})
        return {"connection_id": connection_id, "state": d.get("sync_state", "unknown")}

    async def get_connection_schema_config(self, connection_id: str) -> dict:
        d = await self._call("get_connection_schema_config", {"connection_id": connection_id})
        return {"connection_id": connection_id, "schema": d.get("data", {})}

    async def list_transformation_projects(self) -> list[dict]:
        data = (await self._call("list_transformation_projects")).get("data", {})
        return [
            {"id": item["id"], "name": item.get("name", item["id"]), "status": "ready"}
            for item in data.get("items", [])
        ]

    async def sync_connection(self, connection_id: str) -> dict:
        await self._call("sync_connection", {"connection_id": connection_id})
        return {
            "status": "success",
            "job_id": f"job_{uuid.uuid4().hex[:10]}",
            "connection_id": connection_id,
        }

    async def modify_connection(self, connection_id: str, frequency_minutes: int) -> dict:
        body = json.dumps({"sync_frequency": frequency_minutes})
        await self._call("modify_connection", {"connection_id": connection_id, "request_body": body})
        return {"connection_id": connection_id, "frequency_minutes": frequency_minutes, "status": "updated"}

    async def create_connection(self, config: dict) -> dict:
        data = (await self._call("create_connection", {"request_body": json.dumps(config)})).get("data", {})
        return {
            "id": data.get("id", str(uuid.uuid4())),
            "name": config.get("name", "new_connection"),
            "status": "connected",
        }

    async def create_account_webhook(self, url: str, secret: str) -> dict:
        body = json.dumps({"url": url, "events": ["sync_end"], "active": True, "secret": secret})
        data = (await self._call("create_account_webhook", {"request_body": body})).get("data", {})
        return {"id": data.get("id", f"webhook_{uuid.uuid4().hex[:8]}"), "url": url, "active": True}

    async def run_transformation(self, project_id: str) -> dict:
        await self._call("run_transformation", {"transformation_id": project_id})
        return {"project_id": project_id, "status": "started", "run_id": f"run_{uuid.uuid4().hex[:8]}"}


class FivetranMCPClient:
    """Single interface for all Fivetran MCP calls, with logging."""

    def __init__(self, log_path: str = "logs/tool_calls.jsonl"):
        self._log_path = log_path
        use_mock = os.environ.get("USE_MOCK_MCP", "true").lower() == "true"
        self._backend = _MockBackend() if use_mock else _RealBackend()

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
