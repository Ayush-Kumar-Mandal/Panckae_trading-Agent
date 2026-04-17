"""
Price Fetcher: normalizes token prices from various data sources.
"""
from __future__ import annotations

from typing import Optional
from utils.logger import get_logger
from utils.models import PoolData

logger = get_logger(__name__)


class PriceFetcher:
    """
    Normalizes and caches token prices from pool data.
    Calculates USD prices using stable pairs (WBNB/USDT, WBNB/BUSD).
    """

    def __init__(self):
        self._price_cache: dict[str, float] = {}
        # Stablecoins pegged to $1
        self._stablecoins = {"USDT", "BUSD", "USDC", "DAI"}

    def update_from_pools(self, pools: list[PoolData]) -> None:
        """Extract token prices from pool data and cache them."""
        for pool in pools:
            # If one side is a stablecoin, the other side's price = the pool price
            if pool.token1_symbol in self._stablecoins:
                self._price_cache[pool.token0_symbol] = pool.price_token0_in_token1
            elif pool.token0_symbol in self._stablecoins:
                self._price_cache[pool.token1_symbol] = pool.price_token1_in_token0

        # Stablecoins are always $1
        for stable in self._stablecoins:
            self._price_cache[stable] = 1.0

    def get_price(self, token_symbol: str) -> Optional[float]:
        """Get the USD price for a token symbol."""
        return self._price_cache.get(token_symbol)

    def get_all_prices(self) -> dict[str, float]:
        """Return all cached prices."""
        return dict(self._price_cache)
