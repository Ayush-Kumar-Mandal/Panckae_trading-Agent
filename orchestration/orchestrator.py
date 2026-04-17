"""
Trading Orchestrator: the main engine that initializes all agents,
wires them to the event bus, and runs the continuous trading loop.

Pipeline: Market -> Strategy -> Risk -> Execution -> Portfolio -> Feedback -> Repeat
          Market -> Liquidity (parallel deep pool analysis)
          Market -> Risk (anomaly detection -> defensive actions)
"""
from __future__ import annotations

import asyncio
import signal
import sys

from utils.logger import get_logger
from utils.constants import Events
from config.settings import Settings, load_settings
from orchestration.event_bus import EventBus
from agents.market_intelligence.market_agent import MarketAgent
from agents.strategy.signal_generator import SignalGenerator
from agents.risk.risk_agent import RiskAgent
from agents.execution.execution_agent import ExecutionAgent
from agents.portfolio.portfolio_agent import PortfolioAgent
from agents.feedback.feedback_agent import FeedbackAgent
from agents.liquidity.liquidity_agent import LiquidityAgent
from data.storage.db_client import DBClient

logger = get_logger(__name__)


class TradingOrchestrator:
    """
    Central controller for the multi-agent trading system.

    Initializes 7 agents, wires the event bus, and runs the
    continuous scan -> propose -> validate -> execute -> track -> adapt loop.
    """

    def __init__(self, settings: Settings = None):
        self.settings = settings or load_settings()
        self.event_bus = EventBus()
        self._running = False
        self._cycle_count = 0

        # Persistent Storage
        self.db = DBClient()

        # Initialize ALL 7 Agents
        self.portfolio_agent = PortfolioAgent(
            initial_capital=self.settings.initial_capital_usd,
            event_bus=self.event_bus,
        )

        self.market_agent = MarketAgent(
            strategy_config=self.settings.strategy,
            event_bus=self.event_bus,
        )

        self.signal_generator = SignalGenerator(
            strategy_config=self.settings.strategy,
            event_bus=self.event_bus,
            portfolio_agent=self.portfolio_agent,
        )

        self.risk_agent = RiskAgent(
            risk_config=self.settings.risk,
            event_bus=self.event_bus,
        )

        self.execution_agent = ExecutionAgent(
            execution_config=self.settings.execution,
            event_bus=self.event_bus,
        )

        self.feedback_agent = FeedbackAgent(
            settings=self.settings,
            event_bus=self.event_bus,
        )

        self.liquidity_agent = LiquidityAgent(
            event_bus=self.event_bus,
        )

        # Wire Event Bus (7 agents, 8 subscriptions)
        # Main pipeline: Market -> Strategy -> Risk -> Execution -> Portfolio -> Feedback
        self.event_bus.subscribe(
            Events.MARKET_OPPORTUNITY, self.signal_generator.on_market_opportunity
        )
        self.event_bus.subscribe(
            Events.TRADE_SIGNAL, self.risk_agent.on_trade_signal
        )
        self.event_bus.subscribe(
            Events.TRADE_APPROVED, self.execution_agent.on_trade_approved
        )
        self.event_bus.subscribe(
            Events.TRADE_COMPLETED, self.portfolio_agent.on_trade_completed
        )
        self.event_bus.subscribe(
            Events.TRADE_FAILED, self.portfolio_agent.on_trade_failed
        )
        # Feedback loop: portfolio updates -> feedback agent adapts parameters
        self.event_bus.subscribe(
            Events.PORTFOLIO_UPDATED, self.feedback_agent.on_portfolio_updated
        )
        # Liquidity agent: parallel deep pool analysis
        self.event_bus.subscribe(
            Events.MARKET_OPPORTUNITY, self.liquidity_agent.on_market_opportunity
        )
        # Anomaly detection -> Risk agent defensive actions
        self.event_bus.subscribe(
            Events.ANOMALY_DETECTED, self.risk_agent.on_anomaly_detected
        )

        logger.info("Orchestrator initialized - 7 agents wired (including liquidity + feedback)")
        logger.info(f"   Mode: {'DRY RUN' if self.settings.execution.dry_run else 'LIVE'}")
        logger.info(f"   Network: {self.settings.network.network}")
        logger.info(f"   Capital: ${self.settings.initial_capital_usd:.2f}")
        logger.info(f"   Strategies: Arbitrage + Trend Following + Mean Reversion")
        logger.info(f"   Scan interval: {self.settings.strategy.scan_interval_seconds}s")

    async def run(self, max_cycles: int = 0) -> None:
        """
        Run the trading loop.

        Args:
            max_cycles: Max number of scan cycles (0 = infinite)
        """
        self._running = True
        scan_interval = self.settings.strategy.scan_interval_seconds

        # Initialize persistent DB
        await self.db.initialize()

        print("\n" + "=" * 60)
        print("PANCAKESWAP MULTI-AGENT TRADING SYSTEM")
        print("=" * 60)
        print(f"  Mode:       {'DRY RUN (no real trades)' if self.settings.execution.dry_run else 'LIVE TRADING'}")
        print(f"  Network:    {self.settings.network.network}")
        print(f"  Capital:    ${self.settings.initial_capital_usd:.2f}")
        print(f"  Strategies: Arbitrage + Trend Following + Mean Reversion")
        print(f"  Agents:     7 (Market, Strategy, Risk, Execution, Portfolio, Feedback, Liquidity)")
        print(f"  Interval:   {scan_interval}s")
        print(f"  MEV:        Protection ENABLED")
        print(f"  Anomaly:    Detection ENABLED")
        print("=" * 60 + "\n")

        try:
            while self._running:
                self._cycle_count += 1

                if max_cycles > 0 and self._cycle_count > max_cycles:
                    logger.info(f"Reached max cycles ({max_cycles}). Stopping.")
                    break

                logger.info(f"=== Cycle #{self._cycle_count} =====================================")

                # Run one scan cycle - the event bus propagates through all agents
                await self.market_agent.scan()

                # Report feedback on losses to risk agent
                if self.portfolio_agent.state.total_trades > 0:
                    last_trade_pnl = (
                        self.portfolio_agent.pnl.trade_pnls[-1]
                        if self.portfolio_agent.pnl.trade_pnls
                        else 0
                    )
                    self.risk_agent.record_trade_result(last_trade_pnl > 0)

                # Save portfolio snapshot to DB every cycle
                await self.db.save_portfolio_snapshot(
                    self.portfolio_agent.state,
                    cycle_number=self._cycle_count,
                    metrics=self.portfolio_agent.get_metrics() if self.portfolio_agent.state.total_trades > 0 else {},
                )

                # Brief status
                state = self.portfolio_agent.state
                regime = self.market_agent._last_regime
                logger.info(
                    f"Capital=${state.capital_usd:.2f} | "
                    f"P&L=${state.total_pnl_usd:+.2f} | "
                    f"Trades={state.total_trades} | "
                    f"Wins={state.winning_trades} | "
                    f"Regime={regime}"
                )

                # Wait before next cycle
                await asyncio.sleep(self.settings.strategy.scan_interval_seconds)

        except asyncio.CancelledError:
            logger.info("Trading loop cancelled")
        finally:
            self._running = False
            await self._print_final_report()

    def stop(self) -> None:
        """Signal the trading loop to stop."""
        logger.info("Stop signal received - shutting down after current cycle")
        self._running = False

    async def _print_final_report(self) -> None:
        """Print the final performance report."""
        print("\n")
        self.portfolio_agent.print_summary()

        print("Agent Statistics:")
        print(f"  Market Agent:     {self.market_agent.stats}")
        print(f"  Signal Generator: {self.signal_generator.stats}")
        print(f"  Risk Agent:       {self.risk_agent.stats}")
        print(f"  Execution Agent:  {self.execution_agent.stats}")
        print(f"  Portfolio Agent:  cycles={self._cycle_count}")
        print(f"  Feedback Agent:   {self.feedback_agent.stats}")
        print(f"  Liquidity Agent:  {self.liquidity_agent.stats}")
        print(f"  Event Bus:        {self.event_bus.stats}")
        print()

        # DB stats
        db_counts = await self.db.get_table_counts()
        if any(db_counts.values()):
            print("Database:")
            for table, count in db_counts.items():
                print(f"  {table}: {count} rows")
            print()

        # Print recent trades
        recent = self.portfolio_agent.trade_log.get_recent(5)
        if recent:
            print("Recent Trades:")
            print("-" * 70)
            for t in recent:
                status = "WIN" if t["success"] else "FAIL"
                print(
                    f"  [{status}] {t['token_pair']:12s} | "
                    f"P&L: ${t['actual_profit_usd']:+.2f} | "
                    f"Gas: ${t['gas_cost_usd']:.2f} | "
                    f"{'DRY' if t['dry_run'] else 'LIVE'}"
                )
            print("-" * 70)
