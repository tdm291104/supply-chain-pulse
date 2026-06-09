"""Streamlit dashboard — Alerts / Pipeline / Chat tabs.

All data reads go through the FastAPI REST API so the UI process never
opens the DuckDB file directly (DuckDB allows only one read-write
connection at a time across OS processes). Writes (approve actions,
webhook triggers) also go through the API.
"""
import html
import json

import httpx
import pandas as pd
import streamlit as st

from ui.components.alert_card import format_alert_summary, severity_color, source_icon
from ui.state import API_BASE_URL, LOG_PATH, get_mcp

st.set_page_config(page_title="Supply Chain Pulse", layout="wide")


def _open_alerts() -> list[dict]:
    try:
        resp = httpx.get(f"{API_BASE_URL}/alerts", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def render_alerts_tab():
    alerts = _open_alerts()
    if len(alerts) == 0:
        st.info("No open alerts. The agent will create one after the next risky sync.")
        return

    for alert in alerts:
        color = severity_color(alert["severity"])
        sources = [s for s in (alert["risk_type"] or "").split(",") if s]
        icons = " ".join(source_icon(s) for s in sources)
        with st.container(border=True):
            st.markdown(
                f'<div style="border-left: 6px solid {color}; padding-left: 12px;">'
                f'<h4>{icons} {alert["severity"]} RISK — {html.escape(", ".join(alert["affected_skus"]))}</h4>'
                f"</div>",
                unsafe_allow_html=True,
            )
            st.write(format_alert_summary(
                severity=alert["severity"],
                affected_skus=list(alert["affected_skus"]),
                description=alert["description"],
                recommended_action=alert["recommended_action"],
            ))

            with st.expander("Show underlying data and query"):
                st.code("SELECT * FROM v_supply_risk_summary ORDER BY risk_score DESC LIMIT 5", language="sql")
                try:
                    r = httpx.get(f"{API_BASE_URL}/risk-summary", timeout=5)
                    r.raise_for_status()
                    st.dataframe(pd.DataFrame(r.json()))
                except Exception as e:
                    st.warning(f"Could not load risk summary: {e}")

            action_choice = st.radio(
                "Choose a recommended action",
                ["switch_supplier", "increase_monitoring"],
                format_func=lambda v: {
                    "switch_supplier": "Switch to backup supplier (Vertex Fabrics)",
                    "increase_monitoring": "Increase monitoring frequency to 15 min",
                }[v],
                key=f"action_{alert['alert_id']}",
                index=None,
            )
            approve_disabled = action_choice is None
            if st.button("Approve", key=f"approve_{alert['alert_id']}", disabled=approve_disabled):
                resp = httpx.post(
                    f"{API_BASE_URL}/actions/approve/{alert['alert_id']}",
                    json={"approved_by": "demo_user", "action": action_choice},
                    timeout=30,
                )
                resp.raise_for_status()
                st.success(f"Action executed: {resp.json()['detail']}")
                st.markdown("**Live tool call log:**")
                with open(LOG_PATH) as f:
                    lines = [json.loads(l) for l in f if l.strip()][-5:]
                st.json(lines)
                st.rerun()


def render_pipeline_tab():
    import asyncio
    mcp = get_mcp()
    connections = asyncio.run(mcp.list_connections(triggered_by="user"))

    for conn in connections:
        with st.container(border=True):
            cols = st.columns([3, 2, 2, 2])
            cols[0].markdown(f"**{conn['name']}**  \n`{conn['id']}`")
            badge = {"connected": "🟢 healthy", "warning": "🟡 warning"}.get(conn["status"], "🔴 error")
            cols[1].write(badge)
            cols[2].write(f"Every {conn['frequency_minutes']} min")
            if cols[3].button("Sync now", key=f"sync_{conn['id']}"):
                result = asyncio.run(mcp.sync_connection(conn["id"], triggered_by="user"))
                st.success(f"Sync triggered: job {result['job_id']}")
                st.rerun()


def render_chat_tab():
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    st.caption("Try: " + " · ".join(f"_{p}_" for p in [
        "What's my highest-risk SKU?",
        "Compare SUP-001 vs SUP-002 reliability",
        "Show me stockout forecast for next 30 days",
    ]))

    for role, text, views in st.session_state.chat_history:
        with st.chat_message(role):
            st.write(text)
            if views:
                st.caption(f"Queried: {', '.join(views)}")

    question = st.chat_input("Ask about your supply chain...")
    if question:
        st.session_state.chat_history.append(("user", question, []))
        try:
            resp = httpx.post(f"{API_BASE_URL}/chat", json={"question": question}, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            answer, views = data["answer"], data["views"]
        except Exception as e:
            answer, views = f"Chat unavailable: {e}", []
        st.session_state.chat_history.append(("assistant", answer, views))
        st.rerun()


alerts_tab, pipeline_tab, chat_tab = st.tabs(["Alerts", "Pipeline", "Chat"])
with alerts_tab:
    render_alerts_tab()
with pipeline_tab:
    render_pipeline_tab()
with chat_tab:
    render_chat_tab()
