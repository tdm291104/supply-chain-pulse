"""Fivetran webhook handler: verifies HMAC signature, then runs post-sync
analysis before responding so the full pipeline (webhook -> analysis ->
alert) completes within a single request.
"""
import hashlib
import hmac
import json

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


def _verify_signature(secret: str, raw_body: bytes, signature: str) -> bool:
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/webhook/fivetran")
async def fivetran_webhook(request: Request):
    deps = request.app.state
    raw_body = await request.body()
    signature = request.headers.get("X-Fivetran-Signature", "")

    if not _verify_signature(deps.webhook_secret, raw_body, signature):
        raise HTTPException(status_code=401, detail="invalid signature")

    payload = json.loads(raw_body)
    event_type = payload.get("event")
    data = payload.get("data", {})
    connection_id = data.get("connection_id")
    status = data.get("status")

    if event_type == "sync_end" and status == "successful" and connection_id:
        await deps.analyzer.run_post_sync_analysis(connection_id)

    return {"status": "received"}


@router.post("/actions/approve/{alert_id}")
async def approve_action(alert_id: str, request: Request):
    deps = request.app.state
    body = await request.json()
    approved_by = body.get("approved_by", "unknown")
    action = body.get("action")

    rows = deps.db.query(f"SELECT recommended_action, affected_skus FROM risk_alerts WHERE alert_id = '{alert_id}'")
    if len(rows) == 0:
        raise HTTPException(status_code=404, detail="alert not found")

    deps.db.execute(f"""
        UPDATE risk_alerts SET status = 'APPROVED', approved_by = '{approved_by.replace("'", "''")}'
        WHERE alert_id = '{alert_id}'
    """)

    if action == "switch_supplier":
        result = await deps.executor.switch_primary_supplier(
            alert_id=alert_id,
            new_supplier_config={"name": "vertex_fabrics_backup", "service": "rest_api"},
            approved_by=approved_by,
        )
    elif action == "increase_monitoring":
        result = await deps.executor.increase_monitoring_frequency(
            connection_ids=["conn_orders_001", "conn_inventory_001"],
            new_freq_minutes=15,
            alert_id=alert_id,
        )
    else:
        raise HTTPException(status_code=400, detail=f"unknown action: {action}")

    return {"success": result.success, "detail": result.detail}
