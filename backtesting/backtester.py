"""
Backtester: runs strategies against historical/simulated data to evaluate performance.
"""

import asyncio
from typing import Optional
from utils.logger import get_logger
from utils.models import MarketState, PortfolioState, TradeProposal, TradeResult
from utils.helpers import timestamp_iso
from agents.strategy.arbitrage_strategy import ArbitrageStrategy
from agents.risk.risk_agent import RiskAgent
from execution.pancake_client import PancakeClient
from portfolio.pnl_tracker import PnLTracker
from portfolio.metrics import PerformanceMetrics
from config.settings import Settings, load_settings
from data.collectors.subgraph_collector import SubgraphCollector
from data.processors.pool_analyzer import PoolAnalyzer

logger = get_logger(__name__)


class Backtester:
    """
    Simulates the full trading pipeline on historical or generated data.
    Runs: Data -> Strategy -> Risk -> Simulated Execution -> Portfolio
    """

    def __init__(self, settings: Settings = None):
        self.settings = settings or load_settings()
        self.settings.execution.dry_run = True  # Always dry run in backtesting

        self.strategy = ArbitrageStrategy(self.settings.strategy)
        self.risk_agent = RiskAgent(self.settings.risk)
        self.client = PancakeClient(self.settings.execution)
        self.pnl = PnLTracker()
        self.collector = SubgraphCollector()

        self.capital = self.settings.initial_capital_usd
        self.results: list[TradeResult] = []

    async def run(self, num_cycles: int = 100) -> dict:
        """
        Run a backtest over `num_cycles` simulated market cycles.
        
        Returns:
            Performance metrics dict
        """
        logger.info(f"Starting backtest: {num_cycles} cycles, capital=${self.capital:.2f}")

        portfolio = PortfolioState(
            capital_usd=self.capital,
            peak_capital_usd=self.capital,
        )

        for cycle in range(1, num_cycles + 1):
            # Generate market data
            pools = await self.collector.fetch_pools()
            gas_price = await self.collector.fetch_gas_price()

            market_state = MarketState(
                pools=pools,
                gas_price_gwei=gas_price,
                timestamp=timestamp_iso(),
            )

            # Generate proposals
            proposals = self.strategy.generate_proposals(market_state)

            for proposal in proposals:
                # Risk check
                approved, reason = self.risk_agent.validate(proposal, portfolio)
                if not approved:
                    continue

                # Simulate execution
                result = await self.client.execute_swap(proposal)
                self.results.append(result)

                if result.success:
                    pnl = self.pnl.record(result)
                    portfolio.capital_usd += pnl
                    portfolio.total_pnl_usd += pnl
                    portfolio.total_trades += 1

                    if pnl > 0:
                        portfolio.winning_trades += 1
                        portfolio.consecutive_losses = 0
                        self.risk_agent.record_trade_result(True)
                    else:
                        portfolio.losing_trades += 1
                        portfolio.consecutive_losses += 1
                        self.risk_agent.record_trade_result(False)

                    if portfolio.capital_usd > portfolio.peak_capital_usd:
                        portfolio.peak_capital_usd = portfolio.capital_usd

            if cycle % 20 == 0:
                logger.info(
                    f"Backtest cycle {cycle}/{num_cycles}: "
                    f"capital=${portfolio.capital_usd:.2f}, "
                    f"trades={portfolio.total_trades}"
                )

        # Compute final metrics
        metrics = PerformanceMetrics.compute(
            self.pnl.trade_pnls, self.settings.initial_capital_usd
        )
        metrics["final_capital"] = round(portfolio.capital_usd, 2)
        metrics["cycles_run"] = num_cycles

        logger.info("Backtest complete!")
        self._print_report(metrics)

        return metrics

    def _print_report(self, metrics: dict) -> None:
        """Print backtest results."""
        print("\n" + "=" * 60)
        print("BACKTEST RESULTS")
        print("=" * 60)
        print(f"  Cycles:          {metrics['cycles_run']}")
        print(f"  Final Capital:   ${metrics['final_capital']:.2f}")
        print(f"  Total P&L:       ${metrics['total_pnl']:+.2f}")
        print(f"  Total Return:    {metrics['total_return_pct']:.2%}")
        print(f"  Total Trades:    {metrics['total_trades']}")
        print(f"  Win Rate:        {metrics['win_rate']:.0%}")
        print(f"  Sharpe Ratio:    {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:    {metrics['max_drawdown_pct']:.2%}")
        print(f"  Profit Factor:   {metrics['profit_factor']:.2f}")
        print("=" * 60 + "\n")
