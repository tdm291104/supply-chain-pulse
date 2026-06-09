"""FastAPI app factory. Wires the shared db/analyzer/executor into app
state so api/webhook.py handlers can reach them via request.app.state."""
import os

from fastapi import FastAPI

from agent.actions import ActionExecutor
from agent.analysis import SupplyChainAnalyzer
from agent.chat import ChatRouter
from agent.gemini_client import GeminiClient
from api.read_routes import router as read_router
from api.webhook import router
from db.database import Database
from fivetran_mcp.client import FivetranMCPClient


def create_app(*, db=None, analyzer=None, executor=None, webhook_secret=None) -> FastAPI:
    app = FastAPI(title="Supply Chain Pulse API")

    if db is None:
        db = Database(os.environ.get("DUCKDB_PATH", "./data/supply_chain.duckdb"))

    gemini = None
    if analyzer is None or executor is None:
        mcp = FivetranMCPClient()
        if analyzer is None:
            gemini = GeminiClient(
                api_key=os.environ["GEMINI_API_KEY"],
                model_name=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
            )
            analyzer = SupplyChainAnalyzer(db=db, mcp=mcp, gemini=gemini)
        if executor is None:
            executor = ActionExecutor(db=db, mcp=mcp)
    if webhook_secret is None:
        webhook_secret = os.environ.get("WEBHOOK_SECRET", "")

    if gemini is None:
        gemini = getattr(analyzer, "_gemini", None)

    app.state.db = db
    app.state.analyzer = analyzer
    app.state.executor = executor
    app.state.webhook_secret = webhook_secret
    app.state.chat_router = ChatRouter(db=db, gemini=gemini)

    app.include_router(router)
    app.include_router(read_router)
    return app


app = create_app()
