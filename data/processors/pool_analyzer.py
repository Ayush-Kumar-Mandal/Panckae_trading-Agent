"""
Pool analyzer: processes raw pool data to detect arbitrage opportunities.
Groups pools by token pair, compares prices, and identifies profitable gaps.
"""
from __future__ import annotations

from typing import Optional
from utils.logger import get_logger
from utils.models import PoolData, ArbitrageOpportunity
from config.settings import StrategyConfig

logger = get_logger(__name__)


class PoolAnalyzer:
    """Analyzes pool data to find cross-pool arbitrage opportunities."""

    def __init__(self, strategy_config: StrategyConfig):
        self.min_gap_pct = strategy_config.arbitrage_gap_pct
        self.min_liquidity = strategy_config.min_liquidity_usd

    def find_opportunities(
        self, pools: list[PoolData]
    ) -> list[ArbitrageOpportunity]:
        """
        Group pools by token pair, compare prices across pools for the same
        pair, and return opportunities where the price gap exceeds the threshold.
        """
        # Group pools by normalized token pair key
        pair_groups: dict[str, list[PoolData]] = {}
        for pool in pools:
            key = self._pair_key(pool.token0_symbol, pool.token1_symbol)
            pair_groups.setdefault(key, []).append(pool)

        opportunities: list[ArbitrageOpportunity] = []

        for pair_key, group in pair_groups.items():
            if len(group) < 2:
                continue  # Need at least 2 pools for cross-pool arb

            # Filter out pools with insufficient liquidity
            valid_pools = [
                p for p in group if p.liquidity_usd >= self.min_liquidity
            ]
            if len(valid_pools) < 2:
                continue

            # Compare every pair of pools
            for i in range(len(valid_pools)):
                for j in range(i + 1, len(valid_pools)):
                    opp = self._compare_pools(valid_pools[i], valid_pools[j])
                    if opp is not None:
                        opportunities.append(opp)

        # Sort by highest price difference first
        opportunities.sort(key=lambda o: o.price_diff_pct, reverse=True)

        if opportunities:
            logger.info(
                f"Found {len(opportunities)} arbitrage opportunities "
                f"(best: {opportunities[0].price_diff_pct:.2%} on {opportunities[0].token_pair})"
            )
        else:
            logger.debug("No arbitrage opportunities found this cycle")

        return opportunities

    def _compare_pools(
        self, pool_a: PoolData, pool_b: PoolData
    ) -> Optional[ArbitrageOpportunity]:
        """Compare two pools and return an opportunity if gap exceeds threshold."""
        price_a = pool_a.price_token0_in_token1
        price_b = pool_b.price_token0_in_token1

        if price_a == 0 or price_b == 0:
            return None

        # Calculate percentage difference
        avg_price = (price_a + price_b) / 2
        diff_pct = abs(price_a - price_b) / avg_price

        if diff_pct < self.min_gap_pct:
            return None

        # Determine direction: buy from cheaper pool, sell to more expensive
        if price_a < price_b:
            buy_pool, sell_pool = pool_a, pool_b
            buy_price, sell_price = price_a, price_b
            direction = "buy_A_sell_B"
        else:
            buy_pool, sell_pool = pool_b, pool_a
            buy_price, sell_price = price_b, price_a
            direction = "buy_B_sell_A"

        token_pair = f"{pool_a.token0_symbol}/{pool_a.token1_symbol}"

        return ArbitrageOpportunity(
            pool_a=pool_a,
            pool_b=pool_b,
            token_pair=token_pair,
            buy_pool=buy_pool.pool_address,
            sell_pool=sell_pool.pool_address,
            price_diff_pct=diff_pct,
            buy_price=buy_price,
            sell_price=sell_price,
            direction=direction,
        )

    @staticmethod
    def _pair_key(symbol_a: str, symbol_b: str) -> str:
        """Normalize pair key so WBNB/USDT and USDT/WBNB map to the same key."""
        return "/".join(sorted([symbol_a, symbol_b]))
