"""Executes approved actions via the Fivetran MCP client.

Approval is enforced here — not just in the UI — by re-checking the
alert's status in the database before any write call is made.
"""
from dataclasses import dataclass
from datetime import datetime, timezone


class NotApprovedError(Exception):
    pass


@dataclass
class ActionResult:
    success: bool
    detail: str


class ActionExecutor:
    def __init__(self, db, mcp):
        self._db = db
        self._mcp = mcp

    def _require_approval(self, alert_id: str) -> None:
        rows = self._db.query(f"SELECT status FROM risk_alerts WHERE alert_id = '{alert_id}'")
        if len(rows) == 0 or rows["status"][0] != "APPROVED":
            raise NotApprovedError(f"Alert {alert_id} is not in APPROVED status")

    def _resolve_alert(self, alert_id: str) -> None:
        self._db.execute(f"""
            UPDATE risk_alerts
            SET status = 'RESOLVED', resolved_at = current_timestamp
            WHERE alert_id = '{alert_id}'
        """)

    async def switch_primary_supplier(self, *, alert_id: str, new_supplier_config: dict, approved_by: str) -> ActionResult:
        self._require_approval(alert_id)
        connection = await self._mcp.create_connection(new_supplier_config, triggered_by="agent")
        self._db.execute(f"""
            UPDATE risk_alerts SET approved_by = '{approved_by.replace("'", "''")}'
            WHERE alert_id = '{alert_id}'
        """)
        self._resolve_alert(alert_id)
        return ActionResult(success=True, detail=f"Created backup connection {connection['id']}")

    async def increase_monitoring_frequency(self, *, connection_ids: list[str], new_freq_minutes: int, alert_id: str) -> ActionResult:
        self._require_approval(alert_id)
        for connection_id in connection_ids:
            await self._mcp.modify_connection(connection_id, frequency_minutes=new_freq_minutes, triggered_by="agent")
        self._resolve_alert(alert_id)
        return ActionResult(success=True, detail=f"Increased frequency to {new_freq_minutes}min for {len(connection_ids)} connection(s)")

    async def trigger_emergency_sync(self, *, connection_ids: list[str]) -> ActionResult:
        for connection_id in connection_ids:
            await self._mcp.sync_connection(connection_id, triggered_by="agent")
        return ActionResult(success=True, detail=f"Triggered sync for {len(connection_ids)} connection(s)")
