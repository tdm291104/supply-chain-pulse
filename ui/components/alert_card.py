"""Pure rendering/formatting helpers for alert cards — kept free of
Streamlit calls so they're trivially unit-testable; ui/app.py composes
these with st.* calls."""

_SEVERITY_COLORS = {"HIGH": "#E24B4A", "MEDIUM": "#EF9F27", "LOW": "#639922"}

_SOURCE_ICONS = {"weather": "⛈️", "supplier_delay": "🚚", "inventory": "📦"}


def severity_color(severity: str) -> str:
    return _SEVERITY_COLORS.get(severity, _SEVERITY_COLORS["LOW"])


def source_icon(source: str) -> str:
    return _SOURCE_ICONS.get(source, "ℹ️")


def format_alert_summary(*, severity: str, affected_skus: list[str], description: str, recommended_action: str) -> str:
    skus = ", ".join(affected_skus) if affected_skus else "no specific SKUs"
    return (
        f"**{severity} RISK** — {skus}\n\n"
        f"{description}\n\n"
        f"**Recommended:** {recommended_action}"
    )
