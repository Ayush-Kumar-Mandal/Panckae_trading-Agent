"""
PancakeSwap Trading Dashboard — Streamlit Application

A real-time monitoring dashboard for the multi-agent trading system.
Displays portfolio metrics, trade history, performance charts, and market state.

Run:  streamlit run dashboard/app.py
"""

import sys
import os
import time
import asyncio
import random
from datetime import datetime, timezone, timedelta

# Add project root for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from plotly.subplots import make_subplots

from config.settings import load_settings
from data.collectors.subgraph_collector import SubgraphCollector
from data.processors.pool_analyzer import PoolAnalyzer
from agents.strategy.arbitrage_strategy import ArbitrageStrategy
from agents.risk.risk_agent import RiskAgent
from execution.pancake_client import PancakeClient
from portfolio.pnl_tracker import PnLTracker
from portfolio.metrics import PerformanceMetrics

# ── Page Config ───────────────────────────────────────────────────
st.set_page_config(
    page_title="PancakeSwap Trading Dashboard",
    page_icon="🥞",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }

    .stApp {
        background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
    }

    /* Main header */
    .main-header {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1.5rem 2rem;
        border-radius: 16px;
        margin-bottom: 1.5rem;
        text-align: center;
        box-shadow: 0 8px 32px rgba(102, 126, 234, 0.3);
    }
    .main-header h1 {
        color: #ffffff;
        font-size: 2rem;
        font-weight: 800;
        margin: 0;
        letter-spacing: -0.5px;
    }
    .main-header p {
        color: rgba(255,255,255,0.8);
        margin: 0.3rem 0 0 0;
        font-size: 0.95rem;
    }

    /* Metric cards */
    .metric-card {
        background: rgba(255, 255, 255, 0.05);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 1.2rem 1.5rem;
        text-align: center;
        transition: transform 0.2s ease, box-shadow 0.2s ease;
    }
    .metric-card:hover {
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(0,0,0,0.3);
    }
    .metric-label {
        color: rgba(255,255,255,0.6);
        font-size: 0.75rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 1px;
        margin-bottom: 0.3rem;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: 800;
        margin: 0;
    }
    .metric-green { color: #00e676; }
    .metric-red { color: #ff5252; }
    .metric-blue { color: #448aff; }
    .metric-gold { color: #ffd740; }
    .metric-purple { color: #e040fb; }
    .metric-white { color: #ffffff; }

    /* Section headers */
    .section-header {
        color: #ffffff;
        font-size: 1.2rem;
        font-weight: 700;
        margin: 1.5rem 0 0.8rem 0;
        padding-bottom: 0.4rem;
        border-bottom: 2px solid rgba(102, 126, 234, 0.5);
    }

    /* Glass panels */
    .glass-panel {
        background: rgba(255, 255, 255, 0.03);
        backdrop-filter: blur(10px);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 16px;
        padding: 1.2rem;
        margin-bottom: 1rem;
    }

    /* Status badge */
    .status-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 20px;
        font-size: 0.75rem;
        font-weight: 600;
    }
    .status-active {
        background: rgba(0, 230, 118, 0.2);
        color: #00e676;
        border: 1px solid rgba(0, 230, 118, 0.3);
    }
    .status-dry {
        background: rgba(255, 215, 64, 0.2);
        color: #ffd740;
        border: 1px solid rgba(255, 215, 64, 0.3);
    }

    /* Trade history table */
    .trade-row {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0.6rem 0;
        border-bottom: 1px solid rgba(255,255,255,0.05);
        font-size: 0.85rem;
    }

    /* Sidebar styling */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1a1a2e 0%, #16213e 100%);
    }
    [data-testid="stSidebar"] .stMarkdown {
        color: rgba(255,255,255,0.85);
    }

    /* Override streamlit tab styling */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background: rgba(255,255,255,0.05);
        border-radius: 8px;
        padding: 8px 16px;
        color: rgba(255,255,255,0.7);
    }
    .stTabs [aria-selected="true"] {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%) !important;
        color: white !important;
    }

    /* Dataframe styling */
    .stDataFrame {
        border-radius: 12px;
        overflow: hidden;
    }
</style>
""", unsafe_allow_html=True)


# ── Session State Initialization ──────────────────────────────────
def init_session():
    """Initialize session state with trading system components."""
    if "initialized" not in st.session_state:
        settings = load_settings()
        st.session_state.settings = settings
        st.session_state.collector = SubgraphCollector()
        st.session_state.analyzer = PoolAnalyzer(settings.strategy)
        st.session_state.strategy = ArbitrageStrategy(settings.strategy)
        st.session_state.risk_agent = RiskAgent(settings.risk)
        st.session_state.client = PancakeClient(settings.execution)
        st.session_state.pnl = PnLTracker()
        st.session_state.trade_history = []
        st.session_state.capital = settings.initial_capital_usd
        st.session_state.initial_capital = settings.initial_capital_usd
        st.session_state.capital_history = [settings.initial_capital_usd]
        st.session_state.cycle_count = 0
        st.session_state.total_opportunities = 0
        st.session_state.approved_trades = 0
        st.session_state.rejected_trades = 0
        st.session_state.initialized = True


def run_one_cycle():
    """Run one trading cycle synchronously for the dashboard."""
    settings = st.session_state.settings
    collector = st.session_state.collector
    strategy = st.session_state.strategy
    risk_agent = st.session_state.risk_agent
    client = st.session_state.client
    pnl_tracker = st.session_state.pnl

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        # Fetch pools
        pools = loop.run_until_complete(collector.fetch_pools())
        gas_price = loop.run_until_complete(collector.fetch_gas_price())

        from utils.models import MarketState, PortfolioState
        from utils.helpers import timestamp_iso

        market_state = MarketState(
            pools=pools,
            gas_price_gwei=gas_price,
            timestamp=timestamp_iso(),
        )

        # Get opportunities
        opportunities = st.session_state.analyzer.find_opportunities(pools)
        st.session_state.total_opportunities += len(opportunities)

        # Generate proposals
        proposals = strategy.generate_proposals(market_state)

        portfolio = PortfolioState(
            capital_usd=st.session_state.capital,
            peak_capital_usd=max(st.session_state.capital_history),
        )

        for proposal in proposals:
            approved, reason = risk_agent.validate(proposal, portfolio)

            if approved:
                st.session_state.approved_trades += 1
                result = loop.run_until_complete(client.execute_swap(proposal))

                if result.success:
                    trade_pnl = pnl_tracker.record(result)
                    st.session_state.capital += trade_pnl
                    risk_agent.record_trade_result(trade_pnl > 0)
                else:
                    trade_pnl = 0.0
                    risk_agent.record_trade_result(False)

                st.session_state.trade_history.append({
                    "time": datetime.now(timezone.utc).strftime("%H:%M:%S"),
                    "pair": proposal.opportunity.token_pair,
                    "size": f"${proposal.amount_in_usd:.2f}",
                    "pnl": trade_pnl,
                    "gas": result.gas_cost_usd,
                    "status": "WIN" if result.success and trade_pnl > 0 else ("LOSS" if result.success else "FAIL"),
                    "success": result.success,
                })
            else:
                st.session_state.rejected_trades += 1

        st.session_state.capital_history.append(st.session_state.capital)
        st.session_state.cycle_count += 1

        return pools, opportunities, proposals

    finally:
        loop.close()


# ── Component: Metric Card ────────────────────────────────────────
def metric_card(label: str, value: str, color: str = "white"):
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-label">{label}</div>
        <div class="metric-value metric-{color}">{value}</div>
    </div>
    """, unsafe_allow_html=True)


# ── Component: P&L Chart ─────────────────────────────────────────
def render_pnl_chart(capital_history: list[float]):
    """Render an interactive equity curve with Plotly."""
    if len(capital_history) < 2:
        st.info("Run a few cycles to see the equity curve.")
        return

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        y=capital_history,
        mode='lines',
        fill='tozeroy',
        line=dict(color='#667eea', width=3),
        fillcolor='rgba(102, 126, 234, 0.15)',
        name='Capital',
        hovertemplate='Cycle %{x}<br>Capital: $%{y:.2f}<extra></extra>',
    ))

    # Add starting capital reference line
    fig.add_hline(
        y=capital_history[0],
        line_dash="dash",
        line_color="rgba(255,255,255,0.3)",
        annotation_text=f"Start: ${capital_history[0]:.0f}",
        annotation_font_color="rgba(255,255,255,0.5)",
    )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=30, b=20),
        height=300,
        xaxis=dict(
            title="Cycle",
            gridcolor="rgba(255,255,255,0.05)",
            showgrid=True,
        ),
        yaxis=dict(
            title="Capital (USD)",
            gridcolor="rgba(255,255,255,0.05)",
            showgrid=True,
        ),
        showlegend=False,
        font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Component: Trade Distribution Chart ───────────────────────────
def render_trade_distribution(trade_history: list[dict]):
    """Render trade P&L distribution as a bar chart."""
    if not trade_history:
        st.info("No trades yet.")
        return

    pnls = [t["pnl"] for t in trade_history if t["success"]]
    if not pnls:
        return

    colors = ['#00e676' if p > 0 else '#ff5252' for p in pnls]

    fig = go.Figure(go.Bar(
        y=pnls,
        marker_color=colors,
        hovertemplate='Trade #%{x}<br>P&L: $%{y:.2f}<extra></extra>',
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=20, r=20, t=10, b=20),
        height=250,
        xaxis=dict(title="Trade #", gridcolor="rgba(255,255,255,0.05)"),
        yaxis=dict(title="P&L (USD)", gridcolor="rgba(255,255,255,0.05)"),
        showlegend=False,
        font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
    )

    fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)", line_width=1)
    st.plotly_chart(fig, use_container_width=True)


# ── Component: Win/Loss Donut Chart ──────────────────────────────
def render_winloss_donut(trade_history: list[dict]):
    """Render win/loss ratio as a donut chart."""
    if not trade_history:
        return

    wins = sum(1 for t in trade_history if t["success"] and t["pnl"] > 0)
    losses = sum(1 for t in trade_history if t["success"] and t["pnl"] <= 0)
    fails = sum(1 for t in trade_history if not t["success"])

    fig = go.Figure(go.Pie(
        values=[wins, losses, fails],
        labels=["Wins", "Losses", "Failed"],
        marker_colors=["#00e676", "#ff5252", "#ff9100"],
        hole=0.65,
        textinfo="label+value",
        textfont=dict(size=12, color="white"),
        hovertemplate="%{label}: %{value} (%{percent})<extra></extra>",
    ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=10, r=10, t=10, b=10),
        height=250,
        showlegend=False,
        font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
        annotations=[dict(
            text=f"{wins + losses + fails}<br>trades",
            x=0.5, y=0.5, font_size=16, font_color="rgba(255,255,255,0.8)",
            showarrow=False,
        )],
    )
    st.plotly_chart(fig, use_container_width=True)


# ── Component: Market Pools Table ─────────────────────────────────
def render_pool_table(pools):
    """Render pool data as a styled table."""
    if not pools:
        st.info("No pool data available.")
        return

    data = []
    for p in pools[:12]:  # Cap at 12 for display
        data.append({
            "Pair": f"{p.token0_symbol}/{p.token1_symbol}",
            "Price": f"${p.price_token0_in_token1:.4f}",
            "Liquidity": f"${p.liquidity_usd:,.0f}",
            "Volume 24h": f"${p.volume_24h_usd:,.0f}",
            "Reserve0": f"{p.reserve0:,.1f}",
            "Reserve1": f"{p.reserve1:,.1f}",
            "Source": p.source,
        })

    df = pd.DataFrame(data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        height=min(len(data) * 38 + 40, 500),
    )


# ── Component: Trade History Table ────────────────────────────────
def render_trade_table(trade_history: list[dict]):
    """Render recent trades as a styled dataframe."""
    if not trade_history:
        st.info("No trades executed yet. Run a cycle to generate trades.")
        return

    # Show newest first
    recent = list(reversed(trade_history[-20:]))
    data = []
    for t in recent:
        pnl_display = f"${t['pnl']:+.2f}" if t["success"] else "FAILED"
        data.append({
            "Time": t["time"],
            "Pair": t["pair"],
            "Size": t["size"],
            "P&L": pnl_display,
            "Gas": f"${t['gas']:.2f}" if t["gas"] else "-",
            "Status": t["status"],
        })

    df = pd.DataFrame(data)
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Status": st.column_config.TextColumn(
                "Status",
                help="WIN = profitable, LOSS = unprofitable, FAIL = tx failed",
            ),
        },
        height=min(len(data) * 38 + 40, 500),
    )


# ══════════════════════════════════════════════════════════════════
# MAIN APP
# ══════════════════════════════════════════════════════════════════

init_session()

# ── Header ────────────────────────────────────────────────────────
st.markdown("""
<div class="main-header">
    <h1>🥞 PancakeSwap Trading Dashboard</h1>
    <p>Multi-Agent Arbitrage System &nbsp;|&nbsp;
    <span class="status-badge status-dry">DRY RUN MODE</span></p>
</div>
""", unsafe_allow_html=True)

# ── Sidebar ───────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("### ⚙️ Controls")

    if st.button("▶️  Run 1 Cycle", use_container_width=True, type="primary"):
        pools, opps, proposals = run_one_cycle()
        st.success(f"Cycle #{st.session_state.cycle_count}: {len(opps)} opportunities, {len(proposals)} proposals")

    if st.button("⏩ Run 5 Cycles", use_container_width=True):
        for _ in range(5):
            run_one_cycle()
        st.success(f"Ran 5 cycles (total: {st.session_state.cycle_count})")

    if st.button("🚀 Run 20 Cycles", use_container_width=True):
        for _ in range(20):
            run_one_cycle()
        st.success(f"Ran 20 cycles (total: {st.session_state.cycle_count})")

    st.divider()

    st.markdown("### 📊 System Info")
    settings = st.session_state.settings
    st.markdown(f"""
    - **Network:** {settings.network.network}
    - **Mode:** {'DRY RUN 🔒' if settings.execution.dry_run else 'LIVE ⚠️'}
    - **Min Profit:** ${settings.strategy.min_profit_threshold_usd:.2f}
    - **Max Risk/Trade:** {settings.risk.max_risk_per_trade_pct:.0%}
    - **Max Drawdown:** {settings.risk.max_drawdown_pct:.0%}
    - **Slippage Tol:** {settings.strategy.slippage_tolerance:.1%}
    """)

    st.divider()

    st.markdown("### 🔄 Risk Agent Status")
    risk = st.session_state.risk_agent
    st.markdown(f"""
    - **Approved:** {st.session_state.approved_trades}
    - **Rejected:** {st.session_state.rejected_trades}
    - **Consec. Losses:** {risk.consecutive_losses}
    - **Circuit Breaker:** {'🔴 ACTIVE' if risk.drawdown_ctrl.is_halted else '🟢 Normal'}
    """)

    if st.button("🔄 Reset System", use_container_width=True):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()


# ── Top Metrics Row ───────────────────────────────────────────────
capital = st.session_state.capital
initial = st.session_state.initial_capital
total_pnl = capital - initial
total_return = (total_pnl / initial * 100) if initial > 0 else 0
trade_count = len(st.session_state.trade_history)
wins = sum(1 for t in st.session_state.trade_history if t["success"] and t["pnl"] > 0)
win_rate = (wins / trade_count * 100) if trade_count > 0 else 0

col1, col2, col3, col4, col5, col6 = st.columns(6)
with col1:
    metric_card("Capital", f"${capital:,.2f}", "white")
with col2:
    pnl_color = "green" if total_pnl >= 0 else "red"
    metric_card("Total P&L", f"${total_pnl:+,.2f}", pnl_color)
with col3:
    ret_color = "green" if total_return >= 0 else "red"
    metric_card("Return", f"{total_return:+.2f}%", ret_color)
with col4:
    metric_card("Trades", str(trade_count), "blue")
with col5:
    wr_color = "green" if win_rate >= 50 else "gold"
    metric_card("Win Rate", f"{win_rate:.0f}%", wr_color)
with col6:
    metric_card("Cycles", str(st.session_state.cycle_count), "purple")


# ── Tabs ──────────────────────────────────────────────────────────
tab_overview, tab_trades, tab_performance, tab_market = st.tabs([
    "📈 Overview", "📋 Trade History", "🏆 Performance", "🌐 Market"
])

# ── Tab: Overview ─────────────────────────────────────────────────
with tab_overview:
    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown('<div class="section-header">Equity Curve</div>', unsafe_allow_html=True)
        render_pnl_chart(st.session_state.capital_history)

        st.markdown('<div class="section-header">Trade P&L Distribution</div>', unsafe_allow_html=True)
        render_trade_distribution(st.session_state.trade_history)

    with col_right:
        st.markdown('<div class="section-header">Win / Loss Ratio</div>', unsafe_allow_html=True)
        render_winloss_donut(st.session_state.trade_history)

        st.markdown('<div class="section-header">Quick Stats</div>', unsafe_allow_html=True)

        pnl_tracker = st.session_state.pnl
        if pnl_tracker.trade_pnls:
            metrics = PerformanceMetrics.compute(pnl_tracker.trade_pnls, initial)

            stats_data = {
                "Metric": [
                    "Sharpe Ratio", "Profit Factor", "Max Drawdown",
                    "Avg Win", "Avg Loss", "Best Trade",
                    "Worst Trade", "Total Gas Spent"
                ],
                "Value": [
                    f"{metrics['sharpe_ratio']:.2f}",
                    f"{metrics['profit_factor']:.2f}",
                    f"{metrics['max_drawdown_pct']:.2%}",
                    f"${metrics['avg_win']:+.2f}",
                    f"${metrics['avg_loss']:+.2f}",
                    f"${pnl_tracker.best_trade:+.2f}",
                    f"${pnl_tracker.worst_trade:+.2f}",
                    f"${pnl_tracker.total_gas_spent:.2f}",
                ],
            }
            st.dataframe(
                pd.DataFrame(stats_data),
                use_container_width=True,
                hide_index=True,
                height=330,
            )
        else:
            st.info("Run some cycles to see stats.")

# ── Tab: Trade History ────────────────────────────────────────────
with tab_trades:
    st.markdown('<div class="section-header">Recent Trades</div>', unsafe_allow_html=True)
    render_trade_table(st.session_state.trade_history)

    if st.session_state.trade_history:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown('<div class="section-header">Cumulative P&L</div>', unsafe_allow_html=True)
            pnls = [t["pnl"] for t in st.session_state.trade_history if t["success"]]
            if pnls:
                cumulative = []
                running = 0
                for p in pnls:
                    running += p
                    cumulative.append(running)

                fig = go.Figure(go.Scatter(
                    y=cumulative, mode='lines+markers',
                    line=dict(color='#00e676', width=2),
                    marker=dict(size=4, color='#00e676'),
                    hovertemplate='Trade #%{x}<br>Cumulative: $%{y:.2f}<extra></extra>',
                ))
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=20, r=20, t=10, b=20),
                    height=250,
                    showlegend=False,
                    font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="Cumulative P&L ($)"),
                )
                st.plotly_chart(fig, use_container_width=True)

        with col_b:
            st.markdown('<div class="section-header">P&L by Token Pair</div>', unsafe_allow_html=True)
            pair_pnl = {}
            for t in st.session_state.trade_history:
                if t["success"]:
                    pair_pnl[t["pair"]] = pair_pnl.get(t["pair"], 0) + t["pnl"]

            if pair_pnl:
                pairs = list(pair_pnl.keys())
                values = list(pair_pnl.values())
                colors = ['#00e676' if v > 0 else '#ff5252' for v in values]

                fig = go.Figure(go.Bar(
                    x=pairs, y=values,
                    marker_color=colors,
                    hovertemplate='%{x}<br>P&L: $%{y:.2f}<extra></extra>',
                ))
                fig.update_layout(
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=20, r=20, t=10, b=20),
                    height=250,
                    showlegend=False,
                    font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)"),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="Total P&L ($)"),
                )
                fig.add_hline(y=0, line_color="rgba(255,255,255,0.2)")
                st.plotly_chart(fig, use_container_width=True)

# ── Tab: Performance ──────────────────────────────────────────────
with tab_performance:
    pnl_tracker = st.session_state.pnl

    if pnl_tracker.trade_pnls:
        metrics = PerformanceMetrics.compute(pnl_tracker.trade_pnls, initial)

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            metric_card("Sharpe Ratio", f"{metrics['sharpe_ratio']:.2f}", "gold")
        with col2:
            metric_card("Profit Factor", f"{metrics['profit_factor']:.2f}", "green")
        with col3:
            metric_card("Max Drawdown", f"{metrics['max_drawdown_pct']:.2%}", "red")
        with col4:
            metric_card("Total Gas", f"${pnl_tracker.total_gas_spent:.2f}", "purple")

        st.markdown("")  # Spacer

        col_left, col_right = st.columns(2)
        with col_left:
            st.markdown('<div class="section-header">Drawdown Over Time</div>', unsafe_allow_html=True)

            # Calculate drawdown series
            cap = st.session_state.capital_history
            peak = cap[0]
            drawdowns = []
            for c in cap:
                if c > peak:
                    peak = c
                dd = (peak - c) / peak if peak > 0 else 0
                drawdowns.append(-dd * 100)  # Negative for display

            fig = go.Figure(go.Scatter(
                y=drawdowns, mode='lines', fill='tozeroy',
                line=dict(color='#ff5252', width=2),
                fillcolor='rgba(255, 82, 82, 0.2)',
                hovertemplate='Cycle %{x}<br>Drawdown: %{y:.2f}%<extra></extra>',
            ))
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=10, b=20),
                height=260,
                showlegend=False,
                font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
                xaxis=dict(title="Cycle", gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Drawdown (%)", gridcolor="rgba(255,255,255,0.05)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        with col_right:
            st.markdown('<div class="section-header">Returns Histogram</div>', unsafe_allow_html=True)

            fig = go.Figure(go.Histogram(
                x=pnl_tracker.trade_pnls,
                nbinsx=20,
                marker_color='#667eea',
                hovertemplate='P&L range: $%{x}<br>Count: %{y}<extra></extra>',
            ))
            fig.add_vline(x=0, line_color="rgba(255,255,255,0.5)", line_dash="dash")
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                margin=dict(l=20, r=20, t=10, b=20),
                height=260,
                showlegend=False,
                font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
                xaxis=dict(title="P&L ($)", gridcolor="rgba(255,255,255,0.05)"),
                yaxis=dict(title="Frequency", gridcolor="rgba(255,255,255,0.05)"),
            )
            st.plotly_chart(fig, use_container_width=True)

        # Summary table
        st.markdown('<div class="section-header">Performance Summary</div>', unsafe_allow_html=True)
        summary_data = {
            "Metric": [
                "Initial Capital", "Final Capital", "Net P&L", "Total Return",
                "Total Trades", "Winning Trades", "Losing Trades", "Win Rate",
                "Average Win", "Average Loss", "Best Trade", "Worst Trade",
                "Sharpe Ratio", "Profit Factor", "Max Drawdown", "Total Gas Fees",
            ],
            "Value": [
                f"${initial:,.2f}",
                f"${st.session_state.capital:,.2f}",
                f"${total_pnl:+,.2f}",
                f"{total_return:+.2f}%",
                str(metrics["total_trades"]),
                str(sum(1 for p in pnl_tracker.trade_pnls if p > 0)),
                str(sum(1 for p in pnl_tracker.trade_pnls if p <= 0)),
                f"{metrics['win_rate']:.0%}",
                f"${metrics['avg_win']:+.2f}",
                f"${metrics['avg_loss']:+.2f}",
                f"${pnl_tracker.best_trade:+.2f}",
                f"${pnl_tracker.worst_trade:+.2f}",
                f"{metrics['sharpe_ratio']:.2f}",
                f"{metrics['profit_factor']:.2f}",
                f"{metrics['max_drawdown_pct']:.2%}",
                f"${pnl_tracker.total_gas_spent:.2f}",
            ]
        }
        st.dataframe(pd.DataFrame(summary_data), use_container_width=True, hide_index=True)

    else:
        st.info("Run some trading cycles to see performance metrics. Use the sidebar buttons.")

# ── Tab: Market ───────────────────────────────────────────────────
with tab_market:
    st.markdown('<div class="section-header">Live Pool Data</div>', unsafe_allow_html=True)
    st.caption("Click 'Run 1 Cycle' in the sidebar to refresh market data.")

    # Fetch and display current pools
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        pools = loop.run_until_complete(st.session_state.collector.fetch_pools())
        opportunities = st.session_state.analyzer.find_opportunities(pools)
    finally:
        loop.close()

    col_pools, col_opps = st.columns([3, 2])

    with col_pools:
        st.markdown(f"**{len(pools)} pools detected**")
        render_pool_table(pools)

    with col_opps:
        st.markdown(f"**{len(opportunities)} arbitrage opportunities**")
        if opportunities:
            opp_data = []
            for opp in opportunities:
                opp_data.append({
                    "Pair": opp.token_pair,
                    "Price Diff": f"{opp.price_diff_pct:.2%}",
                    "Buy Price": f"${opp.buy_price:.4f}",
                    "Sell Price": f"${opp.sell_price:.4f}",
                    "Direction": opp.direction,
                })
            st.dataframe(
                pd.DataFrame(opp_data),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("No arbitrage opportunities at this moment.")

    # Price comparison visualization
    if pools:
        st.markdown('<div class="section-header">Price Comparison Across Pools</div>', unsafe_allow_html=True)

        # Group by pair
        pair_pools = {}
        for p in pools:
            key = f"{p.token0_symbol}/{p.token1_symbol}"
            pair_pools.setdefault(key, []).append(p)

        for pair_name, pair_pool_list in pair_pools.items():
            if len(pair_pool_list) >= 2:
                prices = [p.price_token0_in_token1 for p in pair_pool_list]
                addresses = [p.pool_address[:10] + "..." for p in pair_pool_list]

                fig = go.Figure(go.Bar(
                    x=addresses,
                    y=prices,
                    marker_color=['#667eea', '#e040fb', '#00e676', '#ffd740'][:len(prices)],
                    text=[f"${p:.4f}" for p in prices],
                    textposition="outside",
                    textfont=dict(color="white", size=11),
                    hovertemplate='Pool: %{x}<br>Price: $%{y:.4f}<extra></extra>',
                ))
                fig.update_layout(
                    title=dict(text=pair_name, font=dict(color="white", size=14)),
                    template="plotly_dark",
                    paper_bgcolor="rgba(0,0,0,0)",
                    plot_bgcolor="rgba(0,0,0,0)",
                    margin=dict(l=20, r=20, t=40, b=20),
                    height=220,
                    showlegend=False,
                    font=dict(family="Inter", color="rgba(255,255,255,0.8)"),
                    xaxis=dict(gridcolor="rgba(255,255,255,0.05)", title=""),
                    yaxis=dict(gridcolor="rgba(255,255,255,0.05)", title="Price (USD)"),
                )
                st.plotly_chart(fig, use_container_width=True)

# ── Footer ────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    "<div style='text-align:center; color:rgba(255,255,255,0.3); font-size:0.8rem;'>"
    "PancakeSwap Multi-Agent Trading System &nbsp;|&nbsp; DRY RUN MODE &nbsp;|&nbsp; "
    "Built with Streamlit + Plotly"
    "</div>",
    unsafe_allow_html=True,
)
