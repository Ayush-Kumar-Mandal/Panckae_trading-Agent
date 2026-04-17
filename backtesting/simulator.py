"""
Simulator: models AMM execution conditions — slippage, price impact, gas.
"""
from __future__ import annotations

import random
from utils.logger import get_logger

logger = get_logger(__name__)


class ExecutionSimulator:
    """Simulates realistic execution conditions for backtesting."""

    def __init__(self, base_gas_gwei: float = 5.0, bnb_price_usd: float = 300.0):
        self.base_gas_gwei = base_gas_gwei
        self.bnb_price_usd = bnb_price_usd

    def simulate_slippage(
        self, trade_size_usd: float, pool_liquidity_usd: float
    ) -> float:
        """
        Simulate realistic slippage based on trade size vs pool liquidity.
        Returns slippage as a fraction (e.g., 0.003 = 0.3%).
        """
        if pool_liquidity_usd == 0:
            return 0.10  # 10% slippage for empty pool

        impact_ratio = trade_size_usd / pool_liquidity_usd
        base_slippage = impact_ratio * 0.5  # Constant-product model
        noise = random.uniform(-0.001, 0.001)
        return max(0, base_slippage + noise)

    def simulate_gas_cost(self, num_swaps: int = 1) -> float:
        """Simulate gas cost in USD with some variance."""
        gas_per_swap = random.randint(150_000, 280_000)
        total_gas = gas_per_swap * num_swaps
        gas_cost_bnb = (total_gas * self.base_gas_gwei) / 1e9
        return round(gas_cost_bnb * self.bnb_price_usd, 4)

    def simulate_execution_delay(self) -> float:
        """Return simulated block confirmation time in seconds."""
        return random.uniform(1.0, 6.0)  # BSC ~3s blocks

    def simulate_success_rate(self, slippage_pct: float) -> bool:
        """
        Determine if a simulated trade succeeds.
        Higher slippage tolerance = higher success rate.
        """
        # Base 90% success, reduced by high slippage scenarios
        base_rate = 0.90
        if slippage_pct > 0.02:
            base_rate -= 0.15
        return random.random() < base_rate
