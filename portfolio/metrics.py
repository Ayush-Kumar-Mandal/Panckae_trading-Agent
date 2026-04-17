"""
Performance metrics: computes trading system KPIs from trade history.
"""
from __future__ import annotations

import math
from utils.logger import get_logger

logger = get_logger(__name__)


class PerformanceMetrics:
    """Compute and report key performance indicators."""

    @staticmethod
    def compute(trade_pnls: list[float], initial_capital: float) -> dict:
        """
        Compute performance metrics from a list of trade P&Ls.
        
        Returns dict with: win_rate, total_return_pct, sharpe_ratio,
        max_drawdown, profit_factor, avg_win, avg_loss
        """
        if not trade_pnls:
            return {
                "win_rate": 0.0,
                "total_return_pct": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown_pct": 0.0,
                "profit_factor": 0.0,
                "total_trades": 0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
            }

        wins = [p for p in trade_pnls if p > 0]
        losses = [p for p in trade_pnls if p <= 0]

        total_pnl = sum(trade_pnls)
        win_rate = len(wins) / len(trade_pnls) if trade_pnls else 0

        # Total return
        total_return_pct = total_pnl / initial_capital if initial_capital > 0 else 0

        # Sharpe ratio (annualized, assuming ~365 trades/year)
        if len(trade_pnls) > 1:
            mean_return = sum(trade_pnls) / len(trade_pnls)
            std_return = math.sqrt(
                sum((p - mean_return) ** 2 for p in trade_pnls) / (len(trade_pnls) - 1)
            )
            sharpe = (mean_return / std_return * math.sqrt(365)) if std_return > 0 else 0
        else:
            sharpe = 0

        # Max drawdown
        cumulative = 0
        peak = 0
        max_dd = 0
        for pnl in trade_pnls:
            cumulative += pnl
            if cumulative > peak:
                peak = cumulative
            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
        max_drawdown_pct = max_dd / initial_capital if initial_capital > 0 else 0

        # Profit factor
        total_wins = sum(wins) if wins else 0
        total_losses = abs(sum(losses)) if losses else 0
        profit_factor = total_wins / total_losses if total_losses > 0 else float('inf')

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0

        metrics = {
            "win_rate": round(win_rate, 4),
            "total_return_pct": round(total_return_pct, 4),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_pct": round(max_drawdown_pct, 4),
            "profit_factor": round(profit_factor, 4) if profit_factor != float('inf') else 999.0,
            "total_trades": len(trade_pnls),
            "total_pnl": round(total_pnl, 4),
            "avg_win": round(avg_win, 4),
            "avg_loss": round(avg_loss, 4),
        }

        logger.info(
            f"📊 Performance: Win rate={metrics['win_rate']:.1%} | "
            f"Return={metrics['total_return_pct']:.2%} | "
            f"Sharpe={metrics['sharpe_ratio']:.2f} | "
            f"Max DD={metrics['max_drawdown_pct']:.2%}"
        )

        return metrics
