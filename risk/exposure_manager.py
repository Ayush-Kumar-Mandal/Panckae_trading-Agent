"""
Exposure manager: prevents over-concentration in any single token.
"""
from __future__ import annotations

from collections import defaultdict
from utils.logger import get_logger

logger = get_logger(__name__)


class ExposureManager:
    """Track and limit exposure per token as a percentage of portfolio."""

    def __init__(self, max_exposure_pct: float = 0.25):
        self.max_exposure_pct = max_exposure_pct
        self._exposure: dict[str, float] = defaultdict(float)  # token -> USD amount

    def can_add_exposure(
        self, token_symbol: str, amount_usd: float, portfolio_value_usd: float
    ) -> bool:
        """Check if adding this exposure would exceed the per-token limit."""
        if portfolio_value_usd <= 0:
            return False

        current = self._exposure.get(token_symbol, 0.0)
        new_total = current + amount_usd
        exposure_pct = new_total / portfolio_value_usd

        if exposure_pct > self.max_exposure_pct:
            logger.warning(
                f"Exposure limit: {token_symbol} would be {exposure_pct:.1%} "
                f"(max {self.max_exposure_pct:.1%}). Current=${current:.2f}, "
                f"Adding=${amount_usd:.2f}"
            )
            return False
        return True

    def add_exposure(self, token_symbol: str, amount_usd: float) -> None:
        """Record new exposure for a token."""
        self._exposure[token_symbol] += amount_usd

    def remove_exposure(self, token_symbol: str, amount_usd: float) -> None:
        """Reduce exposure for a token (after closing a position)."""
        self._exposure[token_symbol] = max(0, self._exposure[token_symbol] - amount_usd)

    def get_exposure(self, token_symbol: str) -> float:
        """Return current USD exposure for a token."""
        return self._exposure.get(token_symbol, 0.0)

    def reset(self) -> None:
        """Clear all exposure tracking."""
        self._exposure.clear()
