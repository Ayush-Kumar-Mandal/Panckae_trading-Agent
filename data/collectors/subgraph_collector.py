"""
Data collector that fetches pool data from PancakeSwap subgraph (REAL + MOCK fallback).

Queries PancakeSwap V2 subgraph for:
- Top pools by liquidity
- Pool reserves, token info, volume
- Token prices via stablecoin pairs

Falls back to mock data if the subgraph is unreachable.
"""
from __future__ import annotations

import random
import asyncio
import json
from typing import Optional

from utils.logger import get_logger
from utils.models import PoolData
from utils.helpers import timestamp_iso

logger = get_logger(__name__)

# ── PancakeSwap V2 Subgraph Endpoints ────────────────────────────
SUBGRAPH_URLS = {
    "v2_bsc": "https://proxy-worker-api.pancakeswap.com/bsc-exchange",
    "v2_streaming": "https://bsc.streamingfast.io/subgraphs/name/pancakeswap/exchange-v2",
    "v2_nodereal": "https://open-platform-ap.nodereal.io/69e256dc38dc4b3dbeae87826d42adac/pancakeswap-free/graphql",
}

# Ordered list of endpoints to try
SUBGRAPH_FALLBACK_ORDER = [
    SUBGRAPH_URLS["v2_streaming"],       # StreamingFast (official partner)
    SUBGRAPH_URLS["v2_bsc"],             # PancakeSwap proxy
    SUBGRAPH_URLS["v2_nodereal"],         # NodeReal free tier
]

# ── GraphQL Queries ───────────────────────────────────────────────
QUERY_TOP_POOLS = """
{
  pairs(first: 30, orderBy: reserveUSD, orderDirection: desc, where: {reserveUSD_gt: "10000"}) {
    id
    token0 {
      id
      symbol
      name
      decimals
    }
    token1 {
      id
      symbol
      name
      decimals
    }
    reserve0
    reserve1
    reserveUSD
    volumeUSD
    token0Price
    token1Price
  }
}
"""

QUERY_SPECIFIC_PAIRS = """
query GetPairs($token0: String!, $token1: String!) {
  pairs(where: {token0: $token0, token1: $token1}, first: 5, orderBy: reserveUSD, orderDirection: desc) {
    id
    token0 { id symbol decimals }
    token1 { id symbol decimals }
    reserve0
    reserve1
    reserveUSD
    volumeUSD
    token0Price
    token1Price
  }
}
"""

# ── Mock pool templates (fallback) ────────────────────────────────
_POOL_TEMPLATES = [
    {
        "token0_symbol": "WBNB",
        "token1_symbol": "USDT",
        "token0_address": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
        "token1_address": "0x55d398326f99059fF775485246999027B3197955",
        "base_reserve0": 5000.0,
        "base_reserve1": 1_500_000.0,
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
        "base_reserve1": 500_000.0,
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
    Collects pool data from PancakeSwap V2 subgraph.
    Falls back to mock data if the subgraph query fails.
    
    Usage:
        collector = SubgraphCollector(use_real=True)
        pools = await collector.fetch_pools()
    """

    def __init__(self, use_real: bool = True, subgraph_url: str = None):
        self._call_count = 0
        self._use_real = use_real
        self._subgraph_url = subgraph_url  # If set, only use this URL
        self._last_real_data: list[PoolData] = []
        self._working_url: str = None  # Cache the last URL that worked

    async def fetch_pools(self) -> list[PoolData]:
        """
        Fetch current pool states.
        Tries multiple subgraph endpoints, falls back to mock on total failure.
        """
        self._call_count += 1

        if self._use_real:
            # If user specified a specific URL, only try that
            if self._subgraph_url:
                urls_to_try = [self._subgraph_url]
            elif self._working_url:
                # Try the last working URL first, then others
                urls_to_try = [self._working_url] + [
                    u for u in SUBGRAPH_FALLBACK_ORDER if u != self._working_url
                ]
            else:
                urls_to_try = list(SUBGRAPH_FALLBACK_ORDER)

            for url in urls_to_try:
                try:
                    pools = await self._fetch_from_subgraph(url)
                    if pools:
                        self._last_real_data = pools
                        self._working_url = url
                        logger.info(
                            f"[LIVE] Fetched {len(pools)} real pools from PancakeSwap subgraph"
                        )
                        return pools
                except Exception as e:
                    logger.debug(f"Subgraph {url[:40]}... failed: {e}")

            # Try DexScreener API as fallback (free, no API key)
            try:
                pools = await self._fetch_from_dexscreener()
                if pools:
                    self._last_real_data = pools
                    logger.info(
                        f"[LIVE] Fetched {len(pools)} real pools from DexScreener API"
                    )
                    return pools
            except Exception as e:
                logger.warning(f"DexScreener query failed: {e}")

            logger.warning("All live data sources failed — falling back to mock data")

        # Fallback to mock data
        return await self._fetch_mock_pools()

    async def _fetch_from_subgraph(self, url: str = None) -> list[PoolData]:
        """Query the PancakeSwap V2 subgraph via HTTP POST."""
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed — cannot query subgraph")
            return []

        subgraph_url = url or SUBGRAPH_URLS["v2_streaming"]
        payload = {"query": QUERY_TOP_POOLS}
        headers = {"Content-Type": "application/json"}

        async with aiohttp.ClientSession() as session:
            async with session.post(
                subgraph_url,
                json=payload,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as response:
                if response.status != 200:
                    text = await response.text()
                    logger.error(f"Subgraph HTTP {response.status}: {text[:200]}")
                    return []

                data = await response.json()

        if "errors" in data:
            logger.error(f"Subgraph errors: {data['errors']}")
            return []

        pairs = data.get("data", {}).get("pairs", [])
        if not pairs:
            logger.warning("Subgraph returned no pairs")
            return []

        pools: list[PoolData] = []
        for pair in pairs:
            try:
                reserve0 = float(pair["reserve0"])
                reserve1 = float(pair["reserve1"])
                reserve_usd = float(pair["reserveUSD"])
                token0_price = float(pair["token0Price"])
                token1_price = float(pair["token1Price"])
                volume_usd = float(pair["volumeUSD"])

                # Skip tiny or broken pools
                if reserve_usd < 1000 or reserve0 == 0 or reserve1 == 0:
                    continue

                pool = PoolData(
                    pool_address=pair["id"],
                    token0_symbol=pair["token0"]["symbol"],
                    token1_symbol=pair["token1"]["symbol"],
                    token0_address=pair["token0"]["id"],
                    token1_address=pair["token1"]["id"],
                    reserve0=reserve0,
                    reserve1=reserve1,
                    price_token0_in_token1=token0_price if token0_price > 0 else (reserve1 / reserve0 if reserve0 > 0 else 0),
                    price_token1_in_token0=token1_price if token1_price > 0 else (reserve0 / reserve1 if reserve1 > 0 else 0),
                    liquidity_usd=reserve_usd,
                    volume_24h_usd=volume_usd,
                    fee_tier=0.0025,
                    source="subgraph",
                )
                pools.append(pool)

            except (KeyError, ValueError, TypeError) as e:
                logger.debug(f"Skipping malformed pair: {e}")
                continue

        return pools

    # ── DexScreener API (fallback live data) ──────────────────────
    DEXSCREENER_TOKEN_ADDRS = [
        "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
        "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82",  # CAKE
    ]

    async def _fetch_from_dexscreener(self) -> list[PoolData]:
        """
        Fetch real-time PancakeSwap pool data from DexScreener API.
        Free, no API key required. Uses token search endpoint.
        """
        try:
            import aiohttp
        except ImportError:
            logger.warning("aiohttp not installed")
            return []

        pools: list[PoolData] = []
        seen_pairs = set()  # Avoid duplicate pool addresses

        async with aiohttp.ClientSession() as session:
            for token_addr in self.DEXSCREENER_TOKEN_ADDRS:
                url = f"https://api.dexscreener.com/latest/dex/tokens/{token_addr}"
                try:
                    async with session.get(
                        url, timeout=aiohttp.ClientTimeout(total=10)
                    ) as response:
                        if response.status != 200:
                            continue
                        data = await response.json()
                except Exception:
                    continue

                pairs = data.get("pairs", [])
                # Filter: PancakeSwap on BSC only, with sufficient liquidity
                for pair in pairs:
                    if pair.get("dexId") != "pancakeswap":
                        continue
                    if pair.get("chainId") != "bsc":
                        continue

                    pair_addr = pair.get("pairAddress", "")
                    if pair_addr in seen_pairs:
                        continue
                    seen_pairs.add(pair_addr)

                    try:
                        base = pair["baseToken"]
                        quote = pair["quoteToken"]
                        liq = pair.get("liquidity", {})
                        liq_usd = float(liq.get("usd", 0)) if isinstance(liq, dict) else 0
                        vol = pair.get("volume", {})
                        vol_24h = float(vol.get("h24", 0)) if isinstance(vol, dict) else 0
                        price_usd = float(pair.get("priceUsd", 0))
                        price_native = float(pair.get("priceNative", 0))

                        if liq_usd < 10000 or price_usd <= 0:
                            continue

                        # Estimate reserves from liquidity
                        reserve_base = (liq_usd / 2) / price_usd if price_usd > 0 else 0
                        reserve_quote = liq_usd / 2

                        # price_token0_in_token1 = how many quote tokens per 1 base
                        price_t0_in_t1 = price_native if price_native > 0 else (reserve_quote / reserve_base if reserve_base > 0 else 0)

                        pool = PoolData(
                            pool_address=pair_addr,
                            token0_symbol=base.get("symbol", "?"),
                            token1_symbol=quote.get("symbol", "?"),
                            token0_address=base.get("address", ""),
                            token1_address=quote.get("address", ""),
                            reserve0=round(reserve_base, 4),
                            reserve1=round(reserve_quote, 4),
                            price_token0_in_token1=round(price_t0_in_t1, 6),
                            price_token1_in_token0=round(1 / price_t0_in_t1, 6) if price_t0_in_t1 > 0 else 0,
                            liquidity_usd=round(liq_usd, 2),
                            volume_24h_usd=round(vol_24h, 2),
                            fee_tier=0.0025,
                            source="dexscreener",
                        )
                        pools.append(pool)
                    except (KeyError, ValueError, TypeError, ZeroDivisionError):
                        continue

        return pools

    async def fetch_gas_price(self) -> float:
        """
        Get current BSC gas price in gwei.
        Tries real RPC, falls back to estimate.
        """
        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "jsonrpc": "2.0",
                    "method": "eth_gasPrice",
                    "params": [],
                    "id": 1,
                }
                async with session.post(
                    "https://bsc-dataseed.binance.org/",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    data = await resp.json()
                    gas_wei = int(data["result"], 16)
                    return round(gas_wei / 1e9, 1)  # Convert to gwei
        except Exception:
            return round(random.uniform(3.0, 8.0), 1)

    async def fetch_specific_pairs(
        self, token0_address: str, token1_address: str
    ) -> list[PoolData]:
        """Fetch all pools for a specific token pair."""
        try:
            import aiohttp
        except ImportError:
            return []

        # Normalize addresses to lowercase for subgraph
        t0 = token0_address.lower()
        t1 = token1_address.lower()

        payload = {
            "query": QUERY_SPECIFIC_PAIRS,
            "variables": {"token0": t0, "token1": t1},
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._subgraph_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as response:
                    data = await response.json()

            pairs = data.get("data", {}).get("pairs", [])
            pools = []
            for pair in pairs:
                reserve0 = float(pair["reserve0"])
                reserve1 = float(pair["reserve1"])
                if reserve0 == 0 or reserve1 == 0:
                    continue

                pool = PoolData(
                    pool_address=pair["id"],
                    token0_symbol=pair["token0"]["symbol"],
                    token1_symbol=pair["token1"]["symbol"],
                    token0_address=pair["token0"]["id"],
                    token1_address=pair["token1"]["id"],
                    reserve0=reserve0,
                    reserve1=reserve1,
                    price_token0_in_token1=reserve1 / reserve0,
                    price_token1_in_token0=reserve0 / reserve1,
                    liquidity_usd=float(pair.get("reserveUSD", 0)),
                    volume_24h_usd=float(pair.get("volumeUSD", 0)),
                    fee_tier=0.0025,
                    source="subgraph",
                )
                pools.append(pool)
            return pools
        except Exception as e:
            logger.error(f"Failed to fetch specific pairs: {e}")
            return []

    # ── Mock fallback ─────────────────────────────────────────────
    async def _fetch_mock_pools(self) -> list[PoolData]:
        """Generate mock pool data with realistic price variations."""
        pools: list[PoolData] = []

        for i, template in enumerate(_POOL_TEMPLATES):
            num_pools = random.randint(2, 3)
            for j in range(num_pools):
                price_variation = random.uniform(-0.03, 0.03)
                reserve_variation = random.uniform(0.8, 1.2)

                base_price = template["base_price"]
                price = base_price * (1 + price_variation)
                reserve0 = template["base_reserve0"] * reserve_variation
                reserve1 = reserve0 * price

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
            f"[MOCK] Fetched {len(pools)} pools across {len(_POOL_TEMPLATES)} token pairs"
        )
        return pools

    @property
    def stats(self) -> dict:
        return {
            "total_queries": self._call_count,
            "mode": "real" if self._use_real else "mock",
            "last_pool_count": len(self._last_real_data),
        }
