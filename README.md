# PancakeSwap Multi-Agent Trading System

An autonomous, multi-agent AI trading system for PancakeSwap that identifies and executes cross-pool arbitrage opportunities while managing risk in real-time.

## Architecture

```
Data Ingestion → Market Intelligence → Strategy → Risk → Execution → Portfolio → Feedback → Repeat
```

### Agents

| Agent | Role |
|-------|------|a
| **Market Intelligence** | Scans pools, detects price discrepancies |
| **Strategy (Signal Generator)** | Converts opportunities into trade proposals |
| **Risk Management** | Validates every trade — position sizing, exposure limits, circuit breakers |
| **Execution** | Executes trades (dry-run simulation or live via PancakeSwap Router V2) |
| **Portfolio** | Tracks capital, P&L, win rate, Sharpe ratio, drawdown |

### Event-Driven Pipeline

All agents communicate through an in-memory async event bus:

```
market.opportunity_detected → strategy.trade_signal → risk.trade_approved → execution.trade_completed → portfolio.updated
```

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Initialize pipeline (validate config)
python scripts/init_pipeline.py

# 3. Run live trading (DRY RUN mode — no real transactions)
python scripts/run_live.py --cycles 10

# 4. Run backtest
python scripts/run_backtest.py --cycles 100
```

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Network, wallet, trading mode (DRY_RUN=true) |
| `config/strategy_config.yaml` | Min profit threshold, slippage, arbitrage gap |
| `config/risk_config.yaml` | Max drawdown, exposure limits, circuit breakers |
| `config/execution_config.yaml` | Gas limits, retries, slippage tolerance |

## Project Structure

```
trading-agent/
├── agents/                    # Multi-agent system
│   ├── market_intelligence/   # Market scanning & opportunity detection
│   ├── strategy/              # Signal generation & arbitrage strategy
│   ├── risk/                  # Risk validation gate
│   ├── execution/             # Trade execution, routing, gas optimization
│   └── portfolio/             # Portfolio tracking & metrics
├── config/                    # Configuration (YAML + settings.py)
├── data/                      # Data ingestion & storage
│   ├── collectors/            # Subgraph, RPC, price data
│   ├── processors/            # Pool analysis, feature engineering
│   └── storage/               # Cache, Redis, SQLite
├── execution/                 # Blockchain interaction layer
├── risk/                      # Position sizing, drawdown, exposure
├── portfolio/                 # P&L tracking, trade logging, metrics
├── strategies/                # Reusable strategy logic
│   └── arbitrage/             # Cross-pool arbitrage
├── orchestration/             # Event bus, orchestrator, scheduler
├── backtesting/               # Simulation engine
├── scripts/                   # Entry points (run_live, run_backtest)
└── utils/                     # Logger, helpers, constants, models
```

## Safety Features

- **DRY_RUN=true** by default — no real blockchain transactions
- Every trade must pass through the **Risk Agent** before execution
- **Circuit breakers**: halt trading after consecutive losses or max drawdown
- **Position sizing**: limits each trade to a % of available capital
- **Exposure limits**: prevents over-concentration in any single token

## CLI Options

```bash
# Live trading
python scripts/run_live.py --cycles 50 --interval 2 --capital 5000

# Backtesting
python scripts/run_backtest.py --cycles 500 --capital 10000
```
