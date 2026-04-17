"""
Market view component for the dashboard.
Displays live pool data, opportunity scanner, and price comparison charts.
"""
from __future__ import annotations

import plotly.graph_objects as go
import pandas as pd
import streamlit as st


def render_pool_overview(pools, opportunities):
    """Render a complete market overview with pools and opportunities."""
    col_stats = st.columns(4)
    
    with col_stats[0]:
        st.metric("Total Pools", len(pools))
    with col_stats[1]:
        st.metric("Opportunities", len(opportunities))
    with col_stats[2]:
        total_liq = sum(p.liquidity_usd for p in pools)
        st.metric("Total Liquidity", f"${total_liq:,.0f}")
    with col_stats[3]:
        if opportunities:
            best = max(o.price_diff_pct for o in opportunities)
            st.metric("Best Gap", f"{best:.2%}")
        else:
            st.metric("Best Gap", "0.00%")


def render_price_bars(pools, height: int = 220):
    """Render price comparison bar charts grouped by token pair."""
    pair_pools = {}
    for p in pools:
        key = f"{p.token0_symbol}/{p.token1_symbol}"
        pair_pools.setdefault(key, []).append(p)

    for pair_name, pool_list in pair_pools.items():
        if len(pool_list) < 2:
            continue

        prices = [p.price_token0_in_token1 for p in pool_list]
        labels = [f"Pool {i+1}" for i in range(len(pool_list))]
        colors = ['#667eea', '#e040fb', '#00e676', '#ffd740'][:len(pool_list)]

        fig = go.Figure(go.Bar(
            x=labels, y=prices,
            marker_color=colors,
            text=[f"${p:.4f}" for p in prices],
            textposition="outside",
            textfont=dict(color="white", size=11),
        ))
        fig.update_layout(
            title=dict(text=pair_name, font=dict(color="white", size=14)),
            template="plotly_dark",
            paper_bgcolor="rgba(0,0,0,0)",
            plot_bgcolor="rgba(0,0,0,0)",
            margin=dict(l=20, r=20, t=40, b=20),
            height=height,
            showlegend=False,
            font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
            xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
            yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="Price (USD)"),
        )
        st.plotly_chart(fig, use_container_width=True)


def render_opportunity_table(opportunities):
    """Render arbitrage opportunities as a styled table."""
    if not opportunities:
        st.info("No arbitrage opportunities detected right now.")
        return

    data = []
    for opp in opportunities:
        spread = opp.sell_price - opp.buy_price
        data.append({
            "Pair": opp.token_pair,
            "Gap": f"{opp.price_diff_pct:.2%}",
            "Buy @": f"${opp.buy_price:.4f}",
            "Sell @": f"${opp.sell_price:.4f}",
            "Spread": f"${spread:.4f}",
            "Direction": opp.direction.replace("_", " ").title(),
        })

    df = pd.DataFrame(data)
    st.dataframe(df, use_container_width=True, hide_index=True)
