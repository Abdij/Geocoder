from __future__ import annotations

import html

import streamlit as st


LIGHT_COLORS = {
    "green": ("#107C10", "#E6F4EA"),
    "yellow": ("#986F0B", "#FFF4CE"),
    "red": ("#C50F1F", "#FDE7E9"),
    "blue": ("#0078D4", "#E5F1FB"),
    "gray": ("#605E5C", "#F3F2F1"),
}


def metric_card(title: str, value: object, subtitle: str = "", color: str = "blue") -> None:
    accent, background = LIGHT_COLORS.get(color, LIGHT_COLORS["blue"])
    st.markdown(
        f"""
        <div class="metric-card" style="border-left-color: {accent}; background: {background};">
            <div class="metric-title">{html.escape(str(title))}</div>
            <div class="metric-value">{html.escape(str(value))}</div>
            <div class="metric-subtitle">{html.escape(str(subtitle))}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def status_badge(label: str, status: str = "gray") -> str:
    accent, background = LIGHT_COLORS.get(status, LIGHT_COLORS["gray"])
    return (
        f'<span class="status-badge" style="color:{accent};background:{background};">'
        f"{html.escape(label)}</span>"
    )


def traffic_light_card(title: str, value: object, status: str, detail: str = "") -> None:
    metric_card(title, value, detail, color=status if status in LIGHT_COLORS else "gray")
