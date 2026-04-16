# 🥞 PancakeSwap Multi-Agent Trading System

An autonomous, event-driven, multi-agent AI trading system for PancakeSwap (BSC) that identifies and executes cross-pool arbitrage opportunities while managing risk and adapting to market conditions in real time.

![Python](https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white)
![BSC](https://img.shields.io/badge/Chain-BSC-F0B90B?logo=binance&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Fully%20Functional-00e676)

---

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   Market     │───▶│   Strategy   │───▶│     Risk     │───▶│  Execution   │───▶│  Portfolio   │───▶│   Feedback   │
│   Agent      │    │   Agent      │    │    Agent     │    │   Agent      │    │   Agent      │    │    Agent     │
│              │    │              │    │              │    │              │    │              │    │              │
│ Scans pools  │    │ Generates    │    │ Validates    │    │ Executes or  │    │ Tracks P&L   │    │ Adapts       │
│ Detects opps │    │ proposals    │    │ every trade  │    │ simulates    │    │ Win rate     │    │ parameters   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
       ▲                                                                                                  │
       └──────────────────────────────── Feedback Loop ◀──────────────────────────────────────────────────┘
```

### 🤖 Agent Pipeline

| # | Agent | Subscribes To | Publishes | Key Logic |
|---|-------|--------------|-----------|-----------|
| 1 | **Market Intelligence** | *(triggered by orchestrator)* | `market.opportunity_detected` | Fetches pools from PancakeSwap subgraph, runs pool analyzer, finds price gaps |
| 2 | **Signal Generator** | `market.opportunity_detected` | `strategy.trade_signal` | Sizes positions, estimates profit, builds TradeProposals |
| 3 | **Risk Management** | `strategy.trade_signal` | `risk.trade_approved` / `risk.trade_rejected` | 6 checks: profit threshold, position size, exposure, drawdown, circuit breaker, gas |
| 4 | **Execution** | `risk.trade_approved` | `execution.trade_completed` / `execution.trade_failed` | Real swaps via Router V2 (live) or simulated (dry-run) |
| 5 | **Portfolio** | `execution.trade_completed` | `portfolio.updated` | Updates capital, P&L, win/loss, computes Sharpe, profit factor |
| 6 | **Feedback** | `portfolio.updated` | `feedback.params_updated` | Adjusts min profit, trade size, risk limits, scan interval based on performance |

### Event-Driven Communication

All agents are decoupled and communicate through an **async event bus**:

```
market.opportunity_detected → strategy.trade_signal → risk.trade_approved → execution.trade_completed → portfolio.updated → feedback.params_updated
```

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure environment
cp .env.example .env   # Edit with your settings (or use defaults for dry-run)

# 3. Initialize pipeline (health check)
python scripts/init_pipeline.py

# 4. Run live trading (DRY RUN mode — no real transactions)
python scripts/run_live.py --cycles 10 --interval 2

# 5. Run backtest
python scripts/run_backtest.py --cycles 100

# 6. Launch monitoring dashboard
streamlit run dashboard/app.py
```

---

## Dashboard

The Streamlit dashboard provides real-time monitoring with **5 interactive tabs**:

| Tab | Features |
|-----|----------|
| **📈 Overview** | Equity curve, win/loss donut, P&L distribution, Sharpe/profit factor stats |
| **📋 Trade History** | Filterable trade table, cumulative P&L chart, P&L by token pair |
| **🏆 Performance** | Drawdown chart, returns histogram, full performance summary |
| **🌐 Market** | Live pool data, arbitrage opportunities, cross-pool price comparison |
| **💾 Database** | SQLite table counts, all-time trade stats, recent DB records |

**Sidebar** displays: System info, Data Source (Live/Mock), Risk Agent status, and **Feedback Agent** live parameter values.

---

## Project Structure

```
trading-agent/
├── agents/                         # 🤖 Multi-Agent System
│   ├── market_intelligence/
│   │   └── market_agent.py         #    Scans markets, publishes opportunities
│   ├── strategy/
│   │   ├── signal_generator.py     #    Routes opportunities → trade signals
│   │   └── arbitrage_strategy.py   #    Cross-pool arb strategy logic
│   ├── risk/
│   │   └── risk_agent.py           #    6-check validation gate
│   ├── execution/
│   │   ├── execution_agent.py      #    Coordinates trade execution
│   │   ├── order_router.py         #    Direct vs multi-hop path finding
│   │   └── gas_optimizer.py        #    Gas cost estimation & optimization
│   ├── portfolio/
│   │   └── portfolio_agent.py      #    Capital & performance tracking
│   └── feedback/
│       └── feedback_agent.py       #    Adaptive parameter tuning
│
├── config/                         # ⚙️ Configuration
│   ├── settings.py                 #    Centralized settings (env + YAML)
│   ├── strategy_config.yaml        #    Arbitrage thresholds, slippage
│   ├── risk_config.yaml            #    Drawdown limits, circuit breakers
│   └── execution_config.yaml       #    Gas, retries, dry_run flag
│
├── data/                           # 📊 Data Ingestion & Storage
│   ├── collectors/
│   │   ├── subgraph_collector.py   #    Real PancakeSwap V2 subgraph queries + mock fallback
│   │   ├── rpc_collector.py        #    On-chain data via Web3 RPC
│   │   └── price_fetcher.py        #    Token USD price normalization
│   ├── processors/
│   │   ├── pool_analyzer.py        #    Groups pools, detects arb gaps
│   │   └── feature_engineering.py  #    Derived metrics (vol/liq, volatility)
│   └── storage/
│       ├── cache.py                #    In-memory cache with TTL
│       ├── redis_client.py         #    Optional Redis (auto-fallback)
│       └── db_client.py            #    SQLite persistent storage (4 tables)
│
├── execution/                      # ⛓️ Blockchain Interaction
│   ├── pancake_client.py           #    PancakeSwap Router V2 (live + dry-run)
│   ├── transaction_manager.py      #    Build → Sign → Send → Confirm
│   ├── wallet_manager.py           #    Private key, balance queries
│   └── slippage_control.py         #    Dynamic slippage calculation
│
├── risk/                           # 🛡️ Risk Management Modules
│   ├── position_sizing.py          #    Caps trade size to % of capital
│   ├── drawdown_control.py         #    Circuit breaker on max drawdown
│   └── exposure_manager.py         #    Per-token concentration limits
│
├── portfolio/                      # 💰 Performance Tracking
│   ├── pnl_tracker.py              #    Realized P&L accounting
│   ├── trade_logger.py             #    Full trade history log
│   └── metrics.py                  #    Sharpe, win rate, drawdown, profit factor
│
├── strategies/                     # 📐 Reusable Strategy Logic
│   ├── arbitrage/
│   │   ├── cross_pool.py           #    Cross-pool opportunity detection
│   │   ├── price_diff.py           #    Precise price comparison
│   │   └── profit_estimator.py     #    Net profit after gas + slippage
│   └── utils.py                    #    AMM math (constant-product formulas)
│
├── orchestration/                  # 🎛️ System Coordination
│   ├── event_bus.py                #    Async publish/subscribe (asyncio)
│   ├── orchestrator.py             #    Main engine — wires all 6 agents + DB
│   └── scheduler.py                #    Interval-based task runner
│
├── backtesting/                    # 🧪 Simulation Engine
│   ├── backtester.py               #    Runs strategy on simulated data
│   ├── simulator.py                #    Models slippage, gas, delays
│   └── scenarios.py                #    Stress tests (high gas, flash crash)
│
├── dashboard/                      # 📈 Monitoring Dashboard
│   ├── app.py                      #    Streamlit dashboard (5 tabs)
│   └── components/
│       ├── trade_table.py          #    Filterable trade history table
│       ├── performance_charts.py   #    Equity curve, drawdown, histogram
│       └── market_view.py          #    Pool data, opportunity scanner
│
├── scripts/                        # 🚀 Entry Points
│   ├── run_live.py                 #    Live trading loop
│   ├── run_backtest.py             #    Backtest runner
│   └── init_pipeline.py            #    Health check & initialization
│
├── tests/                          # ✅ Unit Tests (60 tests)
│   ├── test_strategy.py            #    AMM math, arb detection, proposals
│   ├── test_risk.py                #    Position sizing, drawdown, exposure, validation
│   └── test_execution.py           #    Dry-run, slippage, DB, feedback agent
│
├── .env                            # Environment variables
├── .gitignore                      # Python gitignore
├── requirements.txt                # Python dependencies
└── README.md                       # This file
```

---

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Network, wallet, trading mode (`DRY_RUN=true`) |
| `config/strategy_config.yaml` | Min profit threshold, slippage, arbitrage gap, trade size |
| `config/risk_config.yaml` | Max drawdown, exposure limits, consecutive loss limit, circuit breaker |
| `config/execution_config.yaml` | Gas limits, retries, slippage tolerance, tx timeout |

### Key Environment Variables

```env
NETWORK=testnet                  # testnet or mainnet
DRY_RUN=true                     # true = simulated, false = real trades
INITIAL_CAPITAL_USD=1000.0        # Starting capital
PRIVATE_KEY=                     # Required for live trading only
WALLET_ADDRESS=                  # Required for live trading only
```

---

## Safety Features

| Feature | Default | Description |
|---------|---------|-------------|
| `DRY_RUN` | `true` | No real blockchain transactions |
| Max risk/trade | 2% | Limits each trade to 2% of capital |
| Max drawdown | 10% | Halts all trading if portfolio drops 10% from peak |
| Max exposure/token | 25% | Prevents concentration in one asset |
| Circuit breaker | 5 losses | Pauses 5 minutes after 5 consecutive losses |
| Min profit threshold | $0.50 | Rejects trades below expected profit floor |
| Feedback bounds | ±50-200% | Feedback agent won't push parameters beyond safe limits |

---

## Risk Agent — 6 Validation Checks

Every trade must pass all 6 checks before execution:

1. **Circuit breaker cooldown** — is the system currently halted?
2. **Consecutive losses** — stop after N losses in a row
3. **Drawdown** — halt if portfolio drops > max % from peak
4. **Profit threshold** — reject if expected profit < minimum
5. **Position sizing** — cap at max % of capital per trade
6. **Exposure limits** — prevent over-concentration in one token

---

## Feedback Agent — Adaptive Parameter Tuning

The feedback agent automatically adjusts system parameters based on recent performance:

| Condition | Action |
|-----------|--------|
| High win rate (>75%) + profitable | Lower min profit threshold, increase trade size |
| Low win rate (<45%) | Raise min profit threshold, shrink trade size |
| Portfolio in drawdown (>5%) | Reduce risk per trade |
| Healthy + winning | Restore risk toward original values |
| Active market + profitable | Scan faster (reduce interval) |
| Tough market | Slow down to save gas |

All adjustments are bounded — parameters never go below 50% or above 200% of their original values.

---

## Data Sources

| Source | Status | Description |
|--------|--------|-------------|
| **PancakeSwap V2 Subgraph** | ✅ Implemented | GraphQL queries for top pools by liquidity |
| **BSC RPC** | ✅ Implemented | Real gas price via `eth_gasPrice` |
| **Mock Data** | ✅ Auto-fallback | Realistic simulated pools if subgraph is unreachable |

---

## Persistent Storage (SQLite)

All data is automatically persisted to `data/trading_data.db`:

| Table | Data |
|-------|------|
| `trades` | Full trade history (pair, P&L, gas, tx hash, dry_run flag) |
| `portfolio_snapshots` | Capital, drawdown, Sharpe at each cycle |
| `pool_snapshots` | Historical pool states |
| `feedback_adjustments` | Parameter change log |

---

## Testing

```bash
# Run all 60 tests
python -m unittest discover -s tests -v

# Run individual test files
python -m unittest tests.test_strategy -v
python -m unittest tests.test_risk -v
python -m unittest tests.test_execution -v
```

### Test Coverage

| File | Tests | Covers |
|------|-------|--------|
| `test_strategy.py` | 17 | AMM math, price diff, cross-pool detection, profit estimation, proposal pipeline |
| `test_risk.py` | 15 | Position sizing, drawdown circuit breaker, exposure limits, 6-check validation |
| `test_execution.py` | 28 | PancakeClient dry-run, slippage control, SQLite CRUD, feedback agent adaptation |

---

## CLI Options

```bash
# Live trading
python scripts/run_live.py --cycles 50 --interval 2 --capital 5000

# Backtesting
python scripts/run_backtest.py --cycles 500 --capital 10000

# Dashboard
streamlit run dashboard/app.py
```

---

## Going Live

To transition from dry-run to real trading:

1. Set `DRY_RUN=false` in `.env`
2. Set `NETWORK=mainnet` in `.env`
3. Add your `PRIVATE_KEY` and `WALLET_ADDRESS` to `.env`
4. Fund your wallet with BNB (for gas) and trading tokens
5. Install `web3` and `aiohttp`: `pip install web3 aiohttp`
6. Start with small capital and monitor the dashboard

> ⚠️ **WARNING**: Live trading involves real financial risk. Always start small, monitor closely, and never trade with funds you cannot afford to lose.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.10+ (async/await) |
| Framework | asyncio event-driven |
| Blockchain | Web3.py + PancakeSwap Router V2 |
| Data | PancakeSwap V2 Subgraph (GraphQL) |
| Storage | SQLite (built-in, no dependencies) |
| Dashboard | Streamlit + Plotly |
| Config | python-dotenv + PyYAML |
| Testing | unittest (60 tests) |
