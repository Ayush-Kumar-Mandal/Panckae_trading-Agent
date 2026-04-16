"""
Performance chart components for the dashboard.
Renders equity curves, drawdown charts, return histograms, and metric gauges.
"""

import plotly.graph_objects as go
import streamlit as st

# ── Shared layout template ────────────────────────────────────────
_DARK_LAYOUT = dict(
    template="plotly_dark",
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(0,0,0,0)",
    font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
    showlegend=False,
    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
    yaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
)


def equity_curve(capital_history: list[float], height: int = 300):
    """Render equity curve with gradient fill."""
    if len(capital_history) < 2:
        st.info("Not enough data for equity curve.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=capital_history,
        mode='lines',
        fill='tozeroy',
        line=dict(color='#667eea', width=3),
        fillcolor='rgba(102, 126, 234, 0.12)',
        hovertemplate='Cycle %{x}<br>Capital: $%{y:,.2f}<extra></extra>',
    ))
    fig.add_hline(
        y=capital_history[0], line_dash="dash",
        line_color="rgba(255,255,255,0.2)",
        annotation_text=f"Start: ${capital_history[0]:,.0f}",
        annotation_font_color="rgba(255,255,255,0.4)",
    )
    fig.update_layout(
        **_DARK_LAYOUT,
        margin=dict(l=20, r=20, t=20, b=20),
        height=height,
        yaxis_title="Capital (USD)",
        xaxis_title="Cycle",
    )
    st.plotly_chart(fig, use_container_width=True)


def drawdown_chart(capital_history: list[float], height: int = 250):
    """Render drawdown chart."""
    if len(capital_history) < 2:
        return

    peak = capital_history[0]
    drawdowns = []
    for c in capital_history:
        if c > peak:
            peak = c
        dd = (peak - c) / peak if peak > 0 else 0
        drawdowns.append(-dd * 100)

    fig = go.Figure(go.Scatter(
        y=drawdowns, mode='lines', fill='tozeroy',
        line=dict(color='#ff5252', width=2),
        fillcolor='rgba(255, 82, 82, 0.15)',
        hovertemplate='Cycle %{x}<br>Drawdown: %{y:.2f}%<extra></extra>',
    ))
    fig.update_layout(
        **_DARK_LAYOUT,
        margin=dict(l=20, r=20, t=10, b=20),
        height=height,
        yaxis_title="Drawdown (%)",
        xaxis_title="Cycle",
    )
    st.plotly_chart(fig, use_container_width=True)


def pnl_histogram(trade_pnls: list[float], height: int = 250):
    """Render P&L distribution histogram."""
    if not trade_pnls:
        return

    fig = go.Figure(go.Histogram(
        x=trade_pnls, nbinsx=25,
        marker_color='#667eea',
        hovertemplate='P&L: $%{x:.2f}<br>Count: %{y}<extra></extra>',
    ))
    fig.add_vline(x=0, line_color="rgba(255,255,255,0.4)", line_dash="dash")
    fig.update_layout(
        **_DARK_LAYOUT,
        margin=dict(l=20, r=20, t=10, b=20),
        height=height,
        xaxis_title="P&L ($)",
        yaxis_title="Frequency",
    )
    st.plotly_chart(fig, use_container_width=True)


def win_rate_gauge(win_rate: float, height: int = 200):
    """Render a gauge chart for win rate."""
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=win_rate * 100,
        number=dict(suffix="%", font=dict(color="white", size=32)),
        gauge=dict(
            axis=dict(range=[0, 100], tickcolor="rgba(255,255,255,0.3)"),
            bar=dict(color="#00e676"),
            bgcolor="rgba(255,255,255,0.05)",
            bordercolor="rgba(255,255,255,0.1)",
            steps=[
                dict(range=[0, 40], color="rgba(255,82,82,0.2)"),
                dict(range=[40, 60], color="rgba(255,215,64,0.2)"),
                dict(range=[60, 100], color="rgba(0,230,118,0.2)"),
            ],
        ),
    ))
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
        margin=dict(l=30, r=30, t=30, b=10),
        height=height,
    )
    st.plotly_chart(fig, use_container_width=True)
