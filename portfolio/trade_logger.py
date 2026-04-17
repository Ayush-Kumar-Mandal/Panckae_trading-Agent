"""
Trade logger: maintains a complete log of all trades with full details.
"""
from __future__ import annotations

from dataclasses import asdict
from utils.logger import get_logger
from utils.models import TradeResult

logger = get_logger(__name__)


class TradeLogger:
    """Log all trades with full context for analysis and debugging."""

    def __init__(self):
        self.trades: list[dict] = []

    def log_trade(self, result: TradeResult) -> None:
        """Record a trade result to the log."""
        entry = {
            "timestamp": result.timestamp,
            "token_pair": result.proposal.opportunity.token_pair,
            "direction": result.proposal.opportunity.direction,
            "token_in": result.proposal.token_in_symbol,
            "token_out": result.proposal.token_out_symbol,
            "amount_in_usd": result.proposal.amount_in_usd,
            "expected_profit_usd": result.proposal.expected_profit_usd,
            "actual_profit_usd": result.actual_profit_usd,
            "gas_cost_usd": result.gas_cost_usd,
            "success": result.success,
            "tx_hash": result.tx_hash[:16] + "..." if result.tx_hash else "",
            "dry_run": result.dry_run,
            "error": result.error,
        }
        self.trades.append(entry)

        status = "✅" if result.success else "❌"
        logger.info(
            f"{status} Trade logged: {entry['token_pair']} | "
            f"P&L: ${entry['actual_profit_usd']:+.2f} | "
            f"{'DRY RUN' if entry['dry_run'] else 'LIVE'}"
        )

    def get_recent(self, n: int = 10) -> list[dict]:
        """Return the most recent N trades."""
        return self.trades[-n:]

    def get_summary(self) -> dict:
        """Return a summary of all logged trades."""
        if not self.trades:
            return {"total": 0}

        successful = [t for t in self.trades if t["success"]]
        failed = [t for t in self.trades if not t["success"]]
        total_profit = sum(t["actual_profit_usd"] for t in successful)

        return {
            "total": len(self.trades),
            "successful": len(successful),
            "failed": len(failed),
            "total_profit_usd": round(total_profit, 4),
        }
