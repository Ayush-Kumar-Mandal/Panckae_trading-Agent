"""
Drawdown controller: monitors portfolio drawdown and triggers circuit breaker
when losses exceed the configured threshold.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class DrawdownController:
    """Track portfolio peak and current drawdown. Halt trading if threshold exceeded."""

    def __init__(self, max_drawdown_pct: float = 0.10):
        self.max_drawdown_pct = max_drawdown_pct
        self.peak_value: float = 0.0
        self.is_halted: bool = False

    def update(self, current_value: float) -> bool:
        """
        Update with current portfolio value.
        
        Returns:
            True if trading should continue, False if circuit breaker triggered.
        """
        # Track peak
        if current_value > self.peak_value:
            self.peak_value = current_value

        # Calculate drawdown
        if self.peak_value > 0:
            drawdown = (self.peak_value - current_value) / self.peak_value
        else:
            drawdown = 0.0

        if drawdown >= self.max_drawdown_pct:
            if not self.is_halted:
                logger.warning(
                    f"🛑 CIRCUIT BREAKER: Drawdown {drawdown:.2%} exceeds max {self.max_drawdown_pct:.2%}. "
                    f"Peak=${self.peak_value:.2f}, Current=${current_value:.2f}. "
                    f"Trading HALTED."
                )
                self.is_halted = True
            return False

        if self.is_halted and drawdown < self.max_drawdown_pct * 0.5:
            logger.info(
                f"✅ Circuit breaker reset: drawdown recovered to {drawdown:.2%}"
            )
            self.is_halted = False

        return True

    @property
    def current_drawdown(self) -> float:
        if self.peak_value == 0:
            return 0.0
        return max(0, (self.peak_value - self.peak_value) / self.peak_value)

    def reset(self, new_peak: float) -> None:
        """Reset the controller with a new peak value."""
        self.peak_value = new_peak
        self.is_halted = False
