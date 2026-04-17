"""
Gas Optimizer: estimates and optimizes gas costs for transactions.
"""
from __future__ import annotations

from utils.logger import get_logger
from utils.constants import DEFAULT_GAS_COST_USD

logger = get_logger(__name__)


class GasOptimizer:
    """
    Optimizes gas usage and estimates transaction costs.
    Rejects trades where gas cost exceeds profit margin.
    """

    # Average gas costs per operation on BSC (in gas units)
    GAS_ESTIMATES = {
        "approve": 50_000,
        "swap_exact_tokens": 200_000,
        "swap_multi_hop": 350_000,
    }

    def __init__(self, gas_price_gwei: float = 5.0, bnb_price_usd: float = 300.0):
        self.gas_price_gwei = gas_price_gwei
        self.bnb_price_usd = bnb_price_usd

    def estimate_cost_usd(self, operation: str = "swap_exact_tokens") -> float:
        """Estimate gas cost in USD for a given operation."""
        gas_units = self.GAS_ESTIMATES.get(operation, 200_000)
        gas_cost_bnb = (gas_units * self.gas_price_gwei) / 1e9
        cost_usd = gas_cost_bnb * self.bnb_price_usd
        return round(cost_usd, 4)

    def is_profitable_after_gas(
        self, expected_profit_usd: float, operation: str = "swap_exact_tokens"
    ) -> tuple[bool, float]:
        """
        Check if a trade is still profitable after gas costs.
        
        Returns:
            (is_profitable, net_profit_after_gas)
        """
        gas_cost = self.estimate_cost_usd(operation)
        net = expected_profit_usd - gas_cost
        return net > 0, round(net, 4)

    def suggest_gas_price(self, urgency: str = "normal") -> float:
        """Suggest a gas price based on urgency level."""
        multipliers = {
            "low": 0.8,
            "normal": 1.0,
            "high": 1.3,
            "urgent": 1.8,
        }
        multiplier = multipliers.get(urgency, 1.0)
        return round(self.gas_price_gwei * multiplier, 1)

    def update_gas_price(self, new_price_gwei: float) -> None:
        """Update the current gas price estimate."""
        self.gas_price_gwei = new_price_gwei

    def update_bnb_price(self, new_price_usd: float) -> None:
        """Update the BNB/USD price for gas cost calculation."""
        self.bnb_price_usd = new_price_usd
