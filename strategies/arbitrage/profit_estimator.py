"""
Profit estimator: calculates expected net profit for an arbitrage opportunity
after accounting for gas costs, slippage, and trading fees.
"""

from utils.logger import get_logger
from utils.models import ArbitrageOpportunity
from utils.constants import DEFAULT_GAS_COST_USD

logger = get_logger(__name__)


class ProfitEstimator:
    """Estimates net profit for arbitrage trades."""

    def __init__(
        self,
        gas_cost_usd: float = DEFAULT_GAS_COST_USD,
        slippage_pct: float = 0.005,
    ):
        self.gas_cost_usd = gas_cost_usd
        self.slippage_pct = slippage_pct

    def estimate(
        self,
        opportunity: ArbitrageOpportunity,
        trade_size_usd: float,
    ) -> dict:
        """
        Estimate profit for a given opportunity and trade size.
        
        Returns dict with:
            gross_profit_usd, gas_cost_usd, slippage_cost_usd,
            fee_cost_usd, net_profit_usd, is_profitable
        """
        # Gross profit from price difference
        gross_profit_usd = trade_size_usd * opportunity.price_diff_pct

        # Slippage cost (applied to trade size)
        slippage_cost_usd = trade_size_usd * self.slippage_pct

        # Trading fees (both pools: buy + sell)
        total_fee_rate = opportunity.pool_a.fee_tier + opportunity.pool_b.fee_tier
        fee_cost_usd = trade_size_usd * total_fee_rate

        # Gas cost for 2 transactions (buy + sell)
        total_gas_cost = self.gas_cost_usd * 2

        # Net profit
        net_profit_usd = gross_profit_usd - slippage_cost_usd - fee_cost_usd - total_gas_cost

        result = {
            "gross_profit_usd": round(gross_profit_usd, 4),
            "gas_cost_usd": round(total_gas_cost, 4),
            "slippage_cost_usd": round(slippage_cost_usd, 4),
            "fee_cost_usd": round(fee_cost_usd, 4),
            "net_profit_usd": round(net_profit_usd, 4),
            "is_profitable": net_profit_usd > 0,
            "profit_margin_pct": round(
                net_profit_usd / trade_size_usd if trade_size_usd > 0 else 0, 6
            ),
        }

        logger.debug(
            f"Profit estimate for {opportunity.token_pair}: "
            f"gross=${result['gross_profit_usd']:.2f}, "
            f"net=${result['net_profit_usd']:.2f}, "
            f"profitable={result['is_profitable']}"
        )

        return result
