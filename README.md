# 🥞 PancakeSwap Multi-Agent Trading System

An autonomous, event-driven, multi-agent AI trading system for PancakeSwap (BSC). Features **7 specialized agents**, **3 trading strategies** (arbitrage, trend-following, mean-reversion), **regime-aware strategy selection**, **whale/anomaly detection**, **MEV protection**, and **adaptive feedback loops** — all orchestrated through an async event bus.

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)
![BSC](https://img.shields.io/badge/Chain-BSC-F0B90B?logo=binance&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Production%20Ready-00e676)
![Agents](https://img.shields.io/badge/Agents-7-667eea)
![Strategies](https://img.shields.io/badge/Strategies-3-e040fb)
![Tests](https://img.shields.io/badge/Tests-60%20passing-00e676)

---

## Architecture

```
                          ┌───────────────────────────────────────────────────────────────────────────────┐
                          │                           ASYNC EVENT BUS                                     │
                          └───┬────────┬────────┬───────┬────────┬────────┬────────┬────────┬────────────┘
                              │        │        │       │        │        │        │        │
                          ┌───▼──┐ ┌───▼──┐ ┌───▼──┐ ┌─▼────┐ ┌─▼────┐ ┌─▼────┐ ┌─▼──────┐│
                          │Market│ │Liqui-│ │Strat-│ │ Risk │ │Execu-│ │Port- │ │Feed-  ││
                          │Intel │ │dity  │ │egy   │ │Agent │ │tion  │ │folio │ │back   ││
                          │Agent │ │Agent │ │Agent │ │      │ │Agent │ │Agent │ │Agent  ││
                          └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬───┘ └──┬────┘│
                             │        │        │        │        │        │        │      │
  ┌─────────────────────────────────────────────────────────────────────────────────────────┘
  │                                    FEEDBACK LOOP
  ▼
  Market Scan → Regime Detection → Whale/Anomaly Detection → Multi-Strategy Proposals
       → Risk Validation (8 checks) → MEV-Protected Execution → Portfolio Update → Adapt Parameters
```

### 🤖 7-Agent Pipeline

| # | Agent | Subscribes To | Publishes | Key Capabilities |
|---|-------|--------------|-----------|----|
| 1 | **Market Intelligence** | *(orchestrator-triggered)* | `market.opportunity_detected`, `market.regime_change`, `market.whale_alert`, `risk.anomaly_detected` | Fetches pools, **detects regime** (5 states), **whale activity**, **anomalies** (flash crash, depeg) |
| 2 | **Liquidity & Pool Analysis** | `market.opportunity_detected` | `liquidity.pool_analysis_updated` | **Risk-tier classification** (blue-chip/mid-cap/degen), fee efficiency, reserve imbalance, **impermanent loss estimation** |
| 3 | **Strategy (Multi-Strategy)** | `market.opportunity_detected` | `strategy.trade_signal` | **3 strategies**: arbitrage, trend-following, mean-reversion. Regime-aware selection. |
| 4 | **Risk Management** | `strategy.trade_signal`, `risk.anomaly_detected` | `risk.trade_approved` / `risk.trade_rejected` | **8 checks**: anomaly halt, circuit breaker, drawdown, profit, position size, exposure, stop-loss, consecutive losses |
| 5 | **Execution** | `risk.trade_approved` | `execution.trade_completed` / `execution.trade_failed` | **MEV protection** (trade splitting, tight slippage), dry-run or live Router V2 swaps |
| 6 | **Portfolio** | `execution.trade_completed` | `portfolio.updated` | Capital tracking, P&L, Sharpe ratio, win rate, drawdown monitoring |
| 7 | **Feedback** | `portfolio.updated` | `feedback.params_updated` | Adaptive tuning: min profit, trade size, risk limits, scan interval — bounded ±50-200% |

---

## Key Features

### 🎯 Multi-Strategy Engine (Regime-Aware)

| Strategy | Active When | Signal |
|----------|-------------|--------|
| **Cross-Pool Arbitrage** | Always | Price diff > 1% between same-pair pools |
| **Trend Following** | `trending_up` / `trending_down` regimes | Momentum in dominant trend direction |
| **Mean Reversion** | `mean_reverting` / `low_volatility` regimes | Reserve imbalance + high reversion probability |

### 📊 Market Regime Detection

5 market regimes detected using volatility, trend strength, and autocorrelation:

| Regime | Icon | Characteristics |
|--------|------|-----------------|
| Trending Up | 📈 | Positive momentum, >30% trend strength |
| Trending Down | 📉 | Negative momentum, <-30% trend strength |
| Mean Reverting | 🔄 | Negative autocorrelation, prices revert to mean |
| High Volatility | ⚡ | Volatility in 80th+ percentile |
| Low Volatility | 😴 | Volatility in 20th or lower percentile |

### 🐋 Whale & Anomaly Detection

| Detection | Trigger | Action |
|-----------|---------|--------|
| Volume spike | 3x+ above average | ⚠️ Whale alert published |
| Liquidity drain | >50% pool TVL removed | ⚠️ Whale alert published |
| Flash crash | >10% price drop in 1 cycle | 🛑 Trading halted 60-120s |
| Stablecoin depeg | >2% deviation from $1 | 🛑 Trading halted, exit recommendation |
| Extreme volume | >10x normal | ⚠️ Reduce exposure recommendation |

### 🛡️ MEV Protection

| Technique | How It Works |
|-----------|-------------|
| Tight slippage | Enforced max 0.5% slippage bounds |
| Trade splitting | Large orders split into smaller chunks ($500 max per piece) |
| Short deadlines | 30-second transaction validity windows |

### 🔍 Liquidity Agent — Pool Risk Tiers

| Tier | Criteria | Score Bonus |
|------|----------|-------------|
| 🟢 **Blue Chip** | ≥$1M TVL + both tokens are major (WBNB, USDT, CAKE, ETH, BTCB) | +10 pts |
| 🟡 **Mid Cap** | ≥$100K TVL | +5 pts |
| 🔴 **Degen** | <$100K TVL | +0 pts |

Pool scoring (0-100) factors: fee efficiency, liquidity depth, volume activity, reserve imbalance, risk tier.

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

The Streamlit dashboard provides real-time monitoring with **6 interactive tabs**:

| Tab | Features |
|-----|----------|
| **📈 Overview** | Equity curve, win/loss donut, P&L distribution, Sharpe/profit factor stats |
| **📋 Trade History** | Filterable trade table with strategy type column, cumulative P&L chart |
| **🏆 Performance** | Drawdown chart, returns histogram, full performance summary |
| **🌐 Market** | Live pool data, arbitrage opportunities, cross-pool price comparison |
| **🔍 Pools** | Risk tier table, fee efficiency, impermanent loss, tier distribution pie chart, pool score ranking |
| **💾 Database** | SQLite table counts, all-time trade stats, recent DB records |

**Sidebar** displays:
- 📊 System info with **live regime indicator** (📈📉🔄⚡😴)
- 🎯 **Multi-Strategy breakdown** (arbitrage / trend / MR signal counts)
- 🛡️ Risk Agent status with **anomaly halt** indicator
- ⚠️ Active **anomaly alerts** and 🐋 **whale alerts**
- 🧠 Feedback Agent live parameter values
- 🔍 Liquidity Agent pool tier distribution

---

## Project Structure

```
trading-agent/
├── agents/                         # 🤖 7-Agent System
│   ├── market_intelligence/
│   │   └── market_agent.py         #    Scans markets + regime + whale + anomaly detection
│   ├── liquidity/
│   │   └── liquidity_agent.py      #    Pool risk tiers, fee efficiency, IL estimation
│   ├── strategy/
│   │   ├── signal_generator.py     #    Routes to multi-strategy engine
│   │   └── arbitrage_strategy.py   #    Legacy single-strategy (kept for compat)
│   ├── risk/
│   │   └── risk_agent.py           #    8-check validation gate + anomaly defense
│   ├── execution/
│   │   ├── execution_agent.py      #    MEV-protected trade execution
│   │   ├── order_router.py         #    Direct vs multi-hop path finding
│   │   └── gas_optimizer.py        #    Gas cost estimation & optimization
│   ├── portfolio/
│   │   └── portfolio_agent.py      #    Capital & performance tracking
│   └── feedback/
│       └── feedback_agent.py       #    Adaptive parameter tuning
│
├── strategies/                     # 📐 Strategy Engines
│   ├── multi_strategy.py           #    Regime-aware: arb + trend + mean-reversion
│   ├── arbitrage/
│   │   ├── cross_pool.py           #    Cross-pool opportunity detection
│   │   ├── price_diff.py           #    Precise price comparison
│   │   └── profit_estimator.py     #    Net profit after gas + slippage
│   └── utils.py                    #    AMM math (constant-product formulas)
│
├── config/                         # ⚙️ Configuration
│   ├── settings.py                 #    Centralized settings (env + YAML)
│   ├── strategy_config.yaml        #    Arbitrage thresholds, slippage
│   ├── risk_config.yaml            #    Drawdown limits, circuit breakers
│   └── execution_config.yaml       #    Gas, retries, dry_run flag
│
├── data/                           # 📊 Data Ingestion & Storage
│   ├── collectors/
│   │   ├── subgraph_collector.py   #    Real PancakeSwap V2 subgraph + mock fallback
│   │   ├── rpc_collector.py        #    On-chain data via Web3 RPC
│   │   └── price_fetcher.py        #    Token USD price normalization
│   ├── processors/
│   │   ├── pool_analyzer.py        #    Groups pools, detects arb gaps
│   │   └── feature_engineering.py  #    Regime detection, whale/anomaly detection, volatility
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
├── orchestration/                  # 🎛️ System Coordination
│   ├── event_bus.py                #    Async publish/subscribe (asyncio)
│   ├── orchestrator.py             #    Main engine — wires all 7 agents + DB
│   └── scheduler.py                #    Interval-based task runner
│
├── backtesting/                    # 🧪 Simulation Engine
│   ├── backtester.py               #    Runs strategy on simulated data
│   ├── simulator.py                #    Models slippage, gas, delays
│   └── scenarios.py                #    Stress tests (high gas, flash crash)
│
├── dashboard/                      # 📈 Monitoring Dashboard
│   ├── app.py                      #    Streamlit dashboard (6 tabs)
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
├── runtime.txt                     # Python 3.11 (Streamlit Cloud)
├── requirements.txt                # Python dependencies
├── .env                            # Environment variables
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
INITIAL_CAPITAL_USD=1000.0       # Starting capital
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
| **Anomaly halt** | Auto | **Flash crash / depeg auto-halts trading** for 60-120s |
| **Per-trade stop-loss** | 2% | Each trade has an enforced stop-loss limit |
| Min profit threshold | $0.50 | Rejects trades below expected profit floor |
| **MEV protection** | On | Trade splitting + tight slippage prevents sandwich attacks |
| Feedback bounds | ±50-200% | Feedback agent won't push parameters beyond safe limits |

---

## Risk Agent — 8 Validation Checks

Every trade must pass all 8 checks before execution:

1. **🚨 Anomaly halt** — is there an active flash crash / depeg / anomaly?
2. **⏸️ Circuit breaker cooldown** — is the system currently halted?
3. **📉 Consecutive losses** — stop after N losses in a row
4. **📊 Drawdown** — halt if portfolio drops > max % from peak
5. **💰 Profit threshold** — reject if expected profit < minimum
6. **📏 Position sizing** — cap at max % of capital per trade
7. **🔒 Exposure limits** — prevent over-concentration in one token
8. **🛑 Per-trade stop-loss** — reject if potential loss exceeds 5% of capital

---

## Feedback Agent — Adaptive Parameter Tuning

The feedback agent automatically adjusts system parameters based on a rolling 20-trade performance window:

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
| `trades` | Full trade history (pair, strategy, P&L, gas, tx hash, dry_run flag) |
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
| `test_risk.py` | 15 | Position sizing, drawdown circuit breaker, exposure limits, 8-check validation |
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
5. Install `web3`: `pip install web3`
6. Start with small capital and monitor the dashboard

> ⚠️ **WARNING**: Live trading involves real financial risk. Always start small, monitor closely, and never trade with funds you cannot afford to lose.

---

## Tech Stack

| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ (async/await) |
| Framework | asyncio event-driven, 7-agent architecture |
| Blockchain | Web3.py + PancakeSwap Router V2 |
| Data | PancakeSwap V2 Subgraph (GraphQL) |
| Strategies | Arbitrage + Trend Following + Mean Reversion |
| ML/Analysis | Regime detection, volatility analysis, autocorrelation |
| Storage | SQLite (built-in, no dependencies) |
| Dashboard | Streamlit + Plotly (6 tabs) |
| Config | python-dotenv + PyYAML |
| Testing | unittest (60 tests) |
| Safety | MEV protection, anomaly halt, 8-check risk gate |
