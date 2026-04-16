"""
Portfolio Agent: tracks capital, records trades, computes performance metrics.
"""

from utils.logger import get_logger
from utils.models import TradeResult, PortfolioState
from utils.constants import Events
from portfolio.pnl_tracker import PnLTracker
from portfolio.trade_logger import TradeLogger
from portfolio.metrics import PerformanceMetrics

logger = get_logger(__name__)


class PortfolioAgent:
    """
    Manages portfolio state: capital, P&L, trade history, and metrics.
    Subscribes to trade completion/failure events.
    """

    def __init__(self, initial_capital: float, event_bus=None):
        self.event_bus = event_bus
        self.initial_capital = initial_capital

        self.state = PortfolioState(
            capital_usd=initial_capital,
            peak_capital_usd=initial_capital,
        )

        self.pnl = PnLTracker()
        self.trade_log = TradeLogger()

    async def on_trade_completed(self, data: dict) -> None:
        """Handle a successful trade execution."""
        result: TradeResult = data["result"]

        # Record P&L
        trade_pnl = self.pnl.record(result)

        # Update capital
        self.state.capital_usd += trade_pnl
        self.state.total_pnl_usd += trade_pnl
        self.state.total_trades += 1

        if trade_pnl > 0:
            self.state.winning_trades += 1
            self.state.consecutive_losses = 0
        else:
            self.state.losing_trades += 1
            self.state.consecutive_losses += 1

        # Update peak
        if self.state.capital_usd > self.state.peak_capital_usd:
            self.state.peak_capital_usd = self.state.capital_usd

        # Calculate drawdown
        if self.state.peak_capital_usd > 0:
            self.state.current_drawdown_pct = (
                (self.state.peak_capital_usd - self.state.capital_usd)
                / self.state.peak_capital_usd
            )

        # Log trade
        self.trade_log.log_trade(result)

        logger.info(
            f"💰 Portfolio updated: Capital=${self.state.capital_usd:.2f} | "
            f"P&L=${self.state.total_pnl_usd:+.2f} | "
            f"Trades={self.state.total_trades} | "
            f"Win rate={self.state.win_rate:.0%}"
        )

        # Publish portfolio update
        if self.event_bus:
            await self.event_bus.publish(
                Events.PORTFOLIO_UPDATED,
                {"portfolio": self.state, "latest_result": result},
            )

    async def on_trade_failed(self, data: dict) -> None:
        """Handle a failed trade execution."""
        result: TradeResult = data["result"]

        self.state.total_trades += 1
        self.state.losing_trades += 1
        self.state.consecutive_losses += 1

        self.trade_log.log_trade(result)

        logger.warning(
            f"💔 Trade failed: {result.proposal.opportunity.token_pair} | "
            f"Error: {result.error}"
        )

        if self.event_bus:
            await self.event_bus.publish(
                Events.PORTFOLIO_UPDATED,
                {"portfolio": self.state, "latest_result": result},
            )

    def get_metrics(self) -> dict:
        """Compute and return current performance metrics."""
        return PerformanceMetrics.compute(
            self.pnl.trade_pnls, self.initial_capital
        )

    def get_state(self) -> PortfolioState:
        """Return current portfolio state."""
        return self.state

    def print_summary(self) -> None:
        """Print a formatted portfolio summary."""
        metrics = self.get_metrics()
        summary = self.trade_log.get_summary()

        print("\n" + "=" * 60)
        print("📊 PORTFOLIO SUMMARY")
        print("=" * 60)
        print(f"  Initial Capital:    ${self.initial_capital:.2f}")
        print(f"  Current Capital:    ${self.state.capital_usd:.2f}")
        print(f"  Total P&L:          ${self.state.total_pnl_usd:+.2f}")
        print(f"  Total Return:       {metrics['total_return_pct']:.2%}")
        print(f"  Total Trades:       {self.state.total_trades}")
        print(f"  Win Rate:           {metrics['win_rate']:.0%}")
        print(f"  Profit Factor:      {metrics['profit_factor']:.2f}")
        print(f"  Sharpe Ratio:       {metrics['sharpe_ratio']:.2f}")
        print(f"  Max Drawdown:       {metrics['max_drawdown_pct']:.2%}")
        print(f"  Avg Win:            ${metrics['avg_win']:+.2f}")
        print(f"  Avg Loss:           ${metrics['avg_loss']:+.2f}")
        print(f"  Total Gas Spent:    ${self.pnl.total_gas_spent:.2f}")
        print("=" * 60 + "\n")
