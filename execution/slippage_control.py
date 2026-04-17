"""
Slippage Control: calculates minimum output amounts and dynamic slippage.
"""
from __future__ import annotations

from utils.logger import get_logger

logger = get_logger(__name__)


class SlippageController:
    """
    Manages slippage tolerance for trades.
    Can adjust dynamically based on trade size relative to pool liquidity.
    """

    def __init__(self, default_slippage_pct: float = 0.005):
        self.default_slippage_pct = default_slippage_pct

    def calculate_min_output(
        self, expected_output: float, slippage_pct: float = None
    ) -> float:
        """
        Calculate the minimum acceptable output given slippage tolerance.
        
        Args:
            expected_output: The expected output from the swap
            slippage_pct: Override slippage (None = use default)
            
        Returns:
            Minimum acceptable output amount
        """
        slippage = slippage_pct if slippage_pct is not None else self.default_slippage_pct
        min_output = expected_output * (1 - slippage)
        return min_output

    def dynamic_slippage(
        self, trade_size_usd: float, pool_liquidity_usd: float
    ) -> float:
        """
        Calculate dynamic slippage based on trade size vs pool liquidity.
        Larger trades relative to pool size need more slippage tolerance.
        """
        if pool_liquidity_usd == 0:
            return self.default_slippage_pct * 3  # Max slippage for empty pool

        size_ratio = trade_size_usd / pool_liquidity_usd

        if size_ratio < 0.001:  # < 0.1% of pool
            return self.default_slippage_pct
        elif size_ratio < 0.01:  # < 1% of pool
            return self.default_slippage_pct * 1.5
        elif size_ratio < 0.05:  # < 5% of pool
            return self.default_slippage_pct * 2.0
        else:
            return self.default_slippage_pct * 3.0  # High impact trade
