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


class ChatRequest(BaseModel):
    question: str


@router.post("/chat")
def post_chat(body: ChatRequest, request: Request):
    answer, views = request.app.state.chat_router.answer(body.question)
    return {"answer": answer, "views": views}
