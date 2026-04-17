"""
Trade table component for the dashboard.
Renders trade history as a styled, filterable table.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st


def render_trade_table(trade_history: list[dict], max_rows: int = 50):
    """
    Render a filterable trade history table.
    
    Args:
        trade_history: List of trade dicts from the portfolio agent
        max_rows: Maximum rows to display
    """
    if not trade_history:
        st.info("No trades executed yet. Use the sidebar to run trading cycles.")
        return

    # Build dataframe
    recent = list(reversed(trade_history[-max_rows:]))
    rows = []
    for i, t in enumerate(recent):
        rows.append({
            "#": len(trade_history) - i,
            "Time": t.get("time", ""),
            "Pair": t.get("pair", ""),
            "Size": t.get("size", "$0"),
            "P&L": f"${t['pnl']:+.2f}" if t.get("success") else "FAILED",
            "Gas": f"${t['gas']:.2f}" if t.get("gas") else "-",
            "Status": _status_emoji(t),
        })

    df = pd.DataFrame(rows)

    # Filter controls
    col_filter, col_status = st.columns([2, 1])
    with col_filter:
        pair_filter = st.selectbox(
            "Filter by pair",
            ["All"] + list(set(t.get("pair", "") for t in trade_history)),
            key="trade_pair_filter",
        )
    with col_status:
        status_filter = st.selectbox(
            "Filter by status",
            ["All", "WIN", "LOSS", "FAIL"],
            key="trade_status_filter",
        )

    # Apply filters
    if pair_filter != "All":
        df = df[df["Pair"] == pair_filter]
    if status_filter != "All":
        if status_filter == "WIN":
            df = df[df["Status"].str.contains("WIN")]
        elif status_filter == "LOSS":
            df = df[df["Status"].str.contains("LOSS")]
        elif status_filter == "FAIL":
            df = df[df["Status"].str.contains("FAIL")]

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(len(df) * 38 + 40, 600),
    )

    # Summary row
    if trade_history:
        total_pnl = sum(t["pnl"] for t in trade_history if t.get("success"))
        total_gas = sum(t.get("gas", 0) for t in trade_history if t.get("gas"))
        st.caption(
            f"Showing {len(df)} of {len(trade_history)} trades | "
            f"Total P&L: ${total_pnl:+.2f} | Total Gas: ${total_gas:.2f}"
        )


def _status_emoji(trade: dict) -> str:
    """Return a status string with emoji."""
    if not trade.get("success"):
        return "❌ FAIL"
    if trade.get("pnl", 0) > 0:
        return "✅ WIN"
    return "🔻 LOSS"
