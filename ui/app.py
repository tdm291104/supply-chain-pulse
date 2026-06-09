"""Streamlit dashboard — Alerts / Pipeline / Chat tabs.

All data reads go through the FastAPI REST API so the UI process never
opens the DuckDB file directly (DuckDB allows only one read-write
connection at a time across OS processes). Writes go through the API.
"""
import html
import json

import httpx
import pandas as pd
import streamlit as st

from ui.components.alert_card import severity_color, source_icon
from ui.state import API_BASE_URL, LOG_PATH, get_mcp

st.set_page_config(page_title="Supply Chain Pulse", page_icon="📦", layout="wide")

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""<style>
/* App header */
.scp-header {
    display:flex; align-items:center; gap:14px;
    padding-bottom:16px; margin-bottom:6px;
    border-bottom:1px solid rgba(255,255,255,0.08);
}
.scp-title   { font-size:20px; font-weight:700; margin:0; letter-spacing:-0.3px; }
.scp-tagline { font-size:11px; color:#888; margin:0; letter-spacing:0.6px; }

/* KPI banner */
.kpi-row { display:flex; gap:14px; margin:0 0 22px 0; }
.kpi-card {
    flex:1; border-radius:10px; padding:16px 20px;
    text-align:center; border:1px solid rgba(255,255,255,0.06);
}
.kpi-card.danger  { background:rgba(226,75,74,0.13);  border-color:rgba(226,75,74,0.38); }
.kpi-card.warning { background:rgba(239,159,39,0.11); border-color:rgba(239,159,39,0.38); }
.kpi-card.ok      { background:rgba(82,196,26,0.09);  border-color:rgba(82,196,26,0.32); }
.kpi-label { font-size:10px; text-transform:uppercase; letter-spacing:1.2px; color:#999; margin-bottom:4px; }
.kpi-value { font-size:32px; font-weight:700; line-height:1.1; }
.kpi-card.danger  .kpi-value { color:#ff6b6b; }
.kpi-card.warning .kpi-value { color:#ffa940; }
.kpi-card.ok      .kpi-value { color:#73d13d; }
.kpi-sub { font-size:11px; color:#999; margin-top:3px; }

/* Alert card pulse */
@keyframes pulse-glow {
    0%   { box-shadow: 0 0 0 0   rgba(226,75,74,0.55); }
    65%  { box-shadow: 0 0 0 10px rgba(226,75,74,0);   }
    100% { box-shadow: 0 0 0 0   rgba(226,75,74,0);   }
}
.alert-card {
    border-radius:10px; padding:18px 22px 14px 22px; margin-bottom:6px;
}
.alert-card.HIGH {
    border-left:5px solid #e24b4a;
    background:linear-gradient(135deg, rgba(226,75,74,0.11), rgba(226,75,74,0.04));
    animation:pulse-glow 2.4s ease-out infinite;
}
.alert-card.MEDIUM {
    border-left:5px solid #ef9f27;
    background:rgba(239,159,39,0.07);
}
.sev-badge {
    display:inline-block; padding:2px 10px; border-radius:20px;
    font-size:11px; font-weight:700; letter-spacing:0.8px;
    text-transform:uppercase; margin-right:8px;
}
.sev-badge.HIGH   { background:#e24b4a; color:#fff; }
.sev-badge.MEDIUM { background:#ef9f27; color:#fff; }
.sev-badge.LOW    { background:#639922; color:#fff; }
.alert-skus  { font-size:17px; font-weight:700; }
.alert-desc  { font-size:13.5px; line-height:1.65; margin:10px 0; color:#c8cbd4; }
.alert-rec   {
    font-size:13px; padding:9px 14px; border-radius:6px;
    background:rgba(239,159,39,0.10); border-left:3px solid #ef9f27; margin-top:10px;
}

/* Pipeline status dot */
@keyframes blink-dot {
    0%, 100% { opacity:1; }
    50%       { opacity:0.3; }
}
.sdot { width:8px; height:8px; border-radius:50%; display:inline-block; margin-right:7px; }
.sdot.healthy { background:#52c41a; animation:blink-dot 2.5s ease-in-out infinite; }
.sdot.warning { background:#faad14; }
.sdot.error   { background:#ff4d4f; }
</style>""", unsafe_allow_html=True)

# ── Branded header ────────────────────────────────────────────────────────────
st.markdown("""
<div class="scp-header">
  <span style="font-size:26px">📦</span>
  <div>
    <p class="scp-title">Supply Chain Pulse</p>
    <p class="scp-tagline">AI-POWERED RISK MONITORING &amp; AUTOMATED RESPONSE</p>
  </div>
</div>
""", unsafe_allow_html=True)


# ── Data helpers ──────────────────────────────────────────────────────────────

def _open_alerts() -> list[dict]:
    try:
        resp = httpx.get(f"{API_BASE_URL}/alerts", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return []


def _fetch_metrics() -> dict:
    try:
        resp = httpx.get(f"{API_BASE_URL}/metrics", timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return {}


def _style_risk_df(df: pd.DataFrame):
    def _row(row):
        if row.get("risk_score", 0) > 0:
            return ["background-color: rgba(226,75,74,0.20)"] * len(row)
        return [""] * len(row)
    return df.style.apply(_row, axis=1).format(precision=2, na_rep="—")


# ── KPI banner ────────────────────────────────────────────────────────────────

def _render_kpi_banner(m: dict):
    n_alerts = m.get("open_alerts", "—")
    days = m.get("min_stockout_days")
    sku = m.get("critical_sku") or ""
    rate = m.get("worst_supplier_rate")
    sup = m.get("worst_supplier_id") or ""

    days_str = str(days) if days is not None else "—"
    days_cls = "danger" if days is not None and days <= 2 else ("warning" if days is not None and days <= 7 else "ok")

    rate_str = f"{int(rate * 100)}%" if rate is not None else "—"
    rate_cls = "danger" if rate is not None and rate < 0.65 else ("warning" if rate is not None and rate < 0.85 else "ok")

    alerts_cls = "danger" if n_alerts and int(n_alerts) > 0 else "ok"
    alerts_sub = "HIGH severity active" if n_alerts and int(n_alerts) > 0 else "All clear"

    st.markdown(f"""
    <div class="kpi-row">
      <div class="kpi-card {alerts_cls}">
        <div class="kpi-label">Open Alerts</div>
        <div class="kpi-value">{n_alerts}</div>
        <div class="kpi-sub">{alerts_sub}</div>
      </div>
      <div class="kpi-card {days_cls}">
        <div class="kpi-label">Days to Stockout</div>
        <div class="kpi-value">{days_str}</div>
        <div class="kpi-sub">{html.escape(sku)} — critical</div>
      </div>
      <div class="kpi-card {rate_cls}">
        <div class="kpi-label">Supplier On-Time</div>
        <div class="kpi-value">{rate_str}</div>
        <div class="kpi-sub">{html.escape(sup)} — degraded</div>
      </div>
    </div>
    """, unsafe_allow_html=True)


# ── Tab renderers ─────────────────────────────────────────────────────────────

def render_alerts_tab():
    _render_kpi_banner(_fetch_metrics())

    alerts = _open_alerts()
    if not alerts:
        st.info("No open alerts. The agent will create one after the next risky sync.")
        return

    for alert in alerts:
        sev = alert["severity"]
        icons = " ".join(source_icon(s) for s in (alert["risk_type"] or "").split(",") if s)
        skus = ", ".join(alert["affected_skus"])

        st.markdown(f"""
        <div class="alert-card {sev}">
          <div>
            <span class="sev-badge {sev}">{sev}</span>
            <span style="font-size:15px">{icons}</span>
            <span class="alert-skus">{html.escape(skus)}</span>
          </div>
          <p class="alert-desc">{html.escape(alert["description"])}</p>
          <div class="alert-rec">
            <strong>Recommended:</strong> {html.escape(alert["recommended_action"])}
          </div>
        </div>
        """, unsafe_allow_html=True)

        with st.expander("Show underlying data and query"):
            st.code("SELECT * FROM v_supply_risk_summary ORDER BY risk_score DESC LIMIT 5", language="sql")
            try:
                r = httpx.get(f"{API_BASE_URL}/risk-summary", timeout=5)
                r.raise_for_status()
                st.dataframe(_style_risk_df(pd.DataFrame(r.json())), use_container_width=True)
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
        if st.button("Approve", key=f"approve_{alert['alert_id']}",
                     disabled=(action_choice is None), type="primary"):
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
            import time as _time; _time.sleep(4)
            st.rerun()


def render_pipeline_tab():
    import asyncio
    mcp = get_mcp()
    connections = asyncio.run(mcp.list_connections(triggered_by="user"))

    st.markdown(
        f"**{len(connections)} active connections** — real-time data ingestion via Fivetran MCP",
        unsafe_allow_html=False,
    )
    st.write("")

    for conn in connections:
        dot_cls = {"connected": "healthy", "warning": "warning"}.get(conn["status"], "error")
        status_text = {"connected": "Healthy", "warning": "Warning"}.get(conn["status"], "Error")
        status_color = {"healthy": "#52c41a", "warning": "#faad14"}.get(dot_cls, "#ff4d4f")

        with st.container(border=True):
            cols = st.columns([4, 2, 2, 2])
            with cols[0]:
                st.markdown(
                    f'<span class="sdot {dot_cls}"></span>'
                    f'<strong>{conn["name"]}</strong> &nbsp;'
                    f'<span style="font-size:11px;color:#666;font-family:monospace">{conn["id"]}</span>',
                    unsafe_allow_html=True,
                )
            cols[1].markdown(
                f'<span style="color:{status_color};font-weight:600">{status_text}</span>',
                unsafe_allow_html=True,
            )
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
