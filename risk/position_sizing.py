"""
Position sizing: determines how large a trade should be based on
available capital and risk parameters.
"""

from utils.logger import get_logger
from config.settings import RiskConfig

logger = get_logger(__name__)


class PositionSizer:
    """Calculate safe trade sizes based on capital and risk limits."""

    def __init__(self, risk_config: RiskConfig):
        self.max_risk_pct = risk_config.max_risk_per_trade_pct

    def calculate(self, capital_usd: float, proposed_size_usd: float) -> float:
        """
        Return the allowed trade size, capped at the maximum risk per trade.
        
        Args:
            capital_usd: Current available capital
            proposed_size_usd: Strategy's requested trade size
            
        Returns:
            Allowed trade size in USD (may be smaller than proposed)
        """
        max_allowed = capital_usd * self.max_risk_pct
        final_size = min(proposed_size_usd, max_allowed)

        if final_size < proposed_size_usd:
            logger.info(
                f"Position sized down: ${proposed_size_usd:.2f} → ${final_size:.2f} "
                f"(max {self.max_risk_pct:.0%} of ${capital_usd:.2f} capital)"
            )

        return round(final_size, 2)
