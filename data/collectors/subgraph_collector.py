"""
Data collector that fetches pool data from PancakeSwap.
For initial development, generates realistic mock data to avoid subgraph
API complexity. Structured so real data sources can be swapped in later.
"""

import random
import math
from typing import Optional

from utils.logger import get_logger
from utils.models import PoolData
from utils.helpers import timestamp_iso

logger = get_logger(__name__)

# ── Mock pool templates ───────────────────────────────────────────
# Simulates multiple pools for the same token pairs at slightly different prices,
# which creates arbitrage opportunities.
_POOL_TEMPLATES = [
    {
        "token0_symbol": "WBNB",
        "token1_symbol": "USDT",
        "token0_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "token1_address": "0x55d398326f99059fF775485246999027B3197955",
        "base_reserve0": 5000.0,     # 5000 WBNB
        "base_reserve1": 1_500_000.0, # ~$300 per BNB
        "base_price": 300.0,
        "liquidity_usd": 3_000_000.0,
        "volume_24h_usd": 500_000.0,
    },
    {
        "token0_symbol": "CAKE",
        "token1_symbol": "USDT",
        "token0_address": "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",
        "token1_address": "0x55d398326f99059fF775485246999027B3197955",
        "base_reserve0": 200_000.0,
        "base_reserve1": 500_000.0,   # ~$2.50 per CAKE
        "base_price": 2.50,
        "liquidity_usd": 1_000_000.0,
        "volume_24h_usd": 150_000.0,
    },
    {
        "token0_symbol": "WBNB",
        "token1_symbol": "BUSD",
        "token0_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "token1_address": "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56",
        "base_reserve0": 3000.0,
        "base_reserve1": 900_000.0,
        "base_price": 300.0,
        "liquidity_usd": 1_800_000.0,
        "volume_24h_usd": 300_000.0,
    },
]


def _generate_pool_address(seed: int) -> str:
    """Generate a deterministic fake pool address."""
    return f"0x{'%040x' % (seed * 7919 + 123456789)}"


class SubgraphCollector:
    """
    Collects pool data. Currently uses mock data for development.
    Replace `fetch_pools()` internals with real subgraph queries later.
    """

    def __init__(self):
        self._call_count = 0

    async def fetch_pools(self) -> list[PoolData]:
        """
        Fetch current pool states. Returns multiple pools per token pair
        with slightly varying prices to simulate arbitrage opportunities.
        """
        self._call_count += 1
        pools: list[PoolData] = []

        for i, template in enumerate(_POOL_TEMPLATES):
            # Create 2-3 pools per token pair with different reserves/prices
            num_pools = random.randint(2, 3)
            for j in range(num_pools):
                # Add random price variation between pools (0-3%)
                price_variation = random.uniform(-0.03, 0.03)
                reserve_variation = random.uniform(0.8, 1.2)

                base_price = template["base_price"]
                price = base_price * (1 + price_variation)

                reserve0 = template["base_reserve0"] * reserve_variation
                reserve1 = reserve0 * price  # reserve1 = reserve0 * price

                pool = PoolData(
                    pool_address=_generate_pool_address(i * 100 + j + self._call_count),
                    token0_symbol=template["token0_symbol"],
                    token1_symbol=template["token1_symbol"],
                    token0_address=template["token0_address"],
                    token1_address=template["token1_address"],
                    reserve0=reserve0,
                    reserve1=reserve1,
                    price_token0_in_token1=price,
                    price_token1_in_token0=1.0 / price if price > 0 else 0,
                    liquidity_usd=template["liquidity_usd"] * reserve_variation,
                    volume_24h_usd=template["volume_24h_usd"] * random.uniform(0.5, 1.5),
                    fee_tier=0.0025,
                    source="mock",
                )
                pools.append(pool)

        logger.info(
            f"Fetched {len(pools)} pools across {len(_POOL_TEMPLATES)} token pairs"
        )
        return pools

    async def fetch_gas_price(self) -> float:
        """Return current gas price in gwei (mock)."""
        return round(random.uniform(3.0, 8.0), 1)
