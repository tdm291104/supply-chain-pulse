import json

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

router = APIRouter()


def _df_to_json(df):
    return json.loads(df.to_json(orient="records"))


@router.get("/alerts")
def get_alerts(request: Request):
    rows = request.app.state.db.query(
        "SELECT * FROM risk_alerts WHERE status = 'OPEN' ORDER BY created_at DESC"
    )
    return JSONResponse(content=_df_to_json(rows))


@router.get("/risk-summary")
def get_risk_summary(request: Request):
    rows = request.app.state.db.query(
        "SELECT * FROM v_supply_risk_summary ORDER BY risk_score DESC LIMIT 5"
    )
    return JSONResponse(content=_df_to_json(rows))


@router.get("/metrics")
def get_metrics(request: Request):
    alerts_df = request.app.state.db.query(
        "SELECT COUNT(*) AS open_alerts FROM risk_alerts WHERE status = 'OPEN'"
    )
    stockout_df = request.app.state.db.query(
        "SELECT sku, days_until_stockout FROM v_stockout_forecast ORDER BY days_until_stockout ASC LIMIT 1"
    )
    supplier_df = request.app.state.db.query(
        "SELECT supplier_id, last_30d_on_time_rate FROM supplier_performance ORDER BY last_30d_on_time_rate ASC LIMIT 1"
    )
    open_alerts = int(alerts_df.iloc[0]["open_alerts"])
    min_days = int(stockout_df.iloc[0]["days_until_stockout"]) if not stockout_df.empty else None
    critical_sku = stockout_df.iloc[0]["sku"] if not stockout_df.empty else None
    worst_rate = float(supplier_df.iloc[0]["last_30d_on_time_rate"]) if not supplier_df.empty else None
    worst_supplier = supplier_df.iloc[0]["supplier_id"] if not supplier_df.empty else None
    return {
        "open_alerts": open_alerts,
        "min_stockout_days": min_days,
        "critical_sku": critical_sku,
        "worst_supplier_rate": worst_rate,
        "worst_supplier_id": worst_supplier,
    }


class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
def post_chat(body: ChatRequest, request: Request):
    answer, views = request.app.state.chat_router.answer(body.question)
    return {"answer": answer, "views": views}
