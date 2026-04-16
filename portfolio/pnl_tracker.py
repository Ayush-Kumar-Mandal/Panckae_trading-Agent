"""
P&L Tracker: tracks all realized profit/loss from trades.
"""

from utils.logger import get_logger
from utils.models import TradeResult

logger = get_logger(__name__)


class PnLTracker:
    """Track cumulative profit and loss across all trades."""

    def __init__(self):
        self.total_pnl: float = 0.0
        self.total_gas_spent: float = 0.0
        self.trade_pnls: list[float] = []

    def record(self, result: TradeResult) -> float:
        """
        Record a completed trade's P&L.
        
        Returns the P&L for this individual trade.
        """
        pnl = result.actual_profit_usd
        self.total_pnl += pnl
        self.total_gas_spent += result.gas_cost_usd
        self.trade_pnls.append(pnl)

        logger.info(
            f"📈 P&L recorded: ${pnl:+.2f} | "
            f"Total P&L: ${self.total_pnl:+.2f} | "
            f"Total gas: ${self.total_gas_spent:.2f}"
        )
        return pnl

    @property
    def average_pnl(self) -> float:
        if not self.trade_pnls:
            return 0.0
        return sum(self.trade_pnls) / len(self.trade_pnls)

    @property
    def best_trade(self) -> float:
        return max(self.trade_pnls) if self.trade_pnls else 0.0

    @property
    def worst_trade(self) -> float:
        return min(self.trade_pnls) if self.trade_pnls else 0.0

    def summary(self) -> dict:
        wins = [p for p in self.trade_pnls if p > 0]
        losses = [p for p in self.trade_pnls if p <= 0]
        return {
            "total_pnl": round(self.total_pnl, 4),
            "total_gas_spent": round(self.total_gas_spent, 4),
            "total_trades": len(self.trade_pnls),
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "avg_pnl": round(self.average_pnl, 4),
            "best_trade": round(self.best_trade, 4),
            "worst_trade": round(self.worst_trade, 4),
        }
