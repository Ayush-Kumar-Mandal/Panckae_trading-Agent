"""
Feature Engineering: compute derived metrics from raw pool data.
"""

import math
from typing import Optional
from utils.logger import get_logger
from utils.models import PoolData

logger = get_logger(__name__)


class FeatureEngineering:
    """Computes derived features from raw pool data for strategy consumption."""

    @staticmethod
    def compute_liquidity_ratio(pool: PoolData) -> float:
        """Ratio of reserve0 to reserve1 — indicates pool balance."""
        if pool.reserve1 == 0:
            return float("inf")
        return pool.reserve0 / pool.reserve1

    @staticmethod
    def compute_volume_to_liquidity(pool: PoolData) -> float:
        """Volume/liquidity ratio — high = active trading."""
        if pool.liquidity_usd == 0:
            return 0.0
        return pool.volume_24h_usd / pool.liquidity_usd

    @staticmethod
    def compute_price_volatility(price_history: list[float]) -> float:
        """Rolling standard deviation of prices."""
        if len(price_history) < 2:
            return 0.0
        mean = sum(price_history) / len(price_history)
        variance = sum((p - mean) ** 2 for p in price_history) / (len(price_history) - 1)
        return math.sqrt(variance)

    @staticmethod
    def compute_all(pool: PoolData) -> dict:
        """Compute all features for a pool."""
        return {
            "liquidity_ratio": FeatureEngineering.compute_liquidity_ratio(pool),
            "volume_to_liquidity": FeatureEngineering.compute_volume_to_liquidity(pool),
            "price_token0": pool.price_token0_in_token1,
            "price_token1": pool.price_token1_in_token0,
            "liquidity_usd": pool.liquidity_usd,
            "volume_24h_usd": pool.volume_24h_usd,
        }
