"""Shared, cached access to the db/analyzer/executor/mcp for the
Streamlit process — separate from api/main.py's instances since
Streamlit and FastAPI run as separate processes."""
import os

import streamlit as st

from agent.actions import ActionExecutor
from agent.analysis import SupplyChainAnalyzer
from agent.chat import ChatRouter
from agent.gemini_client import GeminiClient
from db.database import Database
from fivetran_mcp.client import FivetranMCPClient

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
LOG_PATH = "logs/tool_calls.jsonl"


@st.cache_resource
def get_db() -> Database:
    return Database(os.environ.get("DUCKDB_PATH", "./data/supply_chain.duckdb"), read_only=True)


@st.cache_resource
def get_mcp() -> FivetranMCPClient:
    return FivetranMCPClient(log_path=LOG_PATH)


@st.cache_resource
def get_gemini() -> GeminiClient:
    return GeminiClient(
        api_key=os.environ["GEMINI_API_KEY"],
        model_name=os.environ.get("GEMINI_MODEL", "gemini-2.0-flash"),
    )


@st.cache_resource
def get_analyzer() -> SupplyChainAnalyzer:
    return SupplyChainAnalyzer(db=get_db(), mcp=get_mcp(), gemini=get_gemini())


@st.cache_resource
def get_executor() -> ActionExecutor:
    return ActionExecutor(db=get_db(), mcp=get_mcp())


@st.cache_resource
def get_chat_router() -> ChatRouter:
    return ChatRouter(db=get_db(), gemini=get_gemini())
