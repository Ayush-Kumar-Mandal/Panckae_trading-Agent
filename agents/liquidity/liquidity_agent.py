"""
Liquidity & Pool Analysis Agent: Deep analysis of PancakeSwap pools.

Responsibilities:
  - Map all active pools and classify by risk tier (blue-chip, mid-cap, degen)
  - Identify pools with high fee generation relative to liquidity
  - Detect imbalanced reserves (arbitrage signals)
  - Estimate impermanent loss for LP strategies
  - Publish pool analysis updates to event bus
"""

import math
from utils.logger import get_logger
from utils.models import PoolData, PoolRiskTier, MarketState
from utils.constants import Events
from data.processors.feature_engineering import FeatureEngineering

logger = get_logger(__name__)

# Liquidity thresholds for risk tiers (USD)
BLUE_CHIP_MIN = 1_000_000    # >= $1M liquidity
MID_CAP_MIN = 100_000        # >= $100K liquidity
# Below $100K = degen


class LiquidityAgent:
    """
    Dedicated agent for deep pool and liquidity analysis.

    Subscribes to: market.opportunity_detected (receives pool data)
    Publishes:     liquidity.pool_analysis_updated

    Provides:
      - Risk-tiered pool classifications
      - Fee efficiency rankings
      - Reserve imbalance detection
      - Impermanent loss estimates
    """

    def __init__(self, event_bus=None):
        self.event_bus = event_bus
        self._analysis_count = 0
        self._pool_tiers: list[PoolRiskTier] = []
        self._v2_pools_seen = 0
        self._v3_pools_seen = 0

    async def on_market_opportunity(self, data: dict) -> None:
        """
        Event handler: receives market state, performs deep pool analysis,
        and publishes risk-tiered results.
        """
        market_state: MarketState = data["market_state"]
        self._pool_tiers = self.analyze_pools(market_state.pools)
        market_state.pool_risk_tiers = self._pool_tiers
        self._analysis_count += 1

        # Count pool types
        self._v2_pools_seen = sum(1 for p in market_state.pools if p.pool_type == "v2")
        self._v3_pools_seen = sum(1 for p in market_state.pools if p.pool_type == "v3")

        # Log top pools
        top_pools = sorted(self._pool_tiers, key=lambda t: t.score, reverse=True)[:3]
        if top_pools:
            logger.info(
                f"[LIQUIDITY] Analysis #{self._analysis_count}: "
                f"{len(self._pool_tiers)} pools | "
                f"Top: {', '.join(f'{p.token_pair}({p.risk_tier})' for p in top_pools)}"
            )

        if self.event_bus:
            await self.event_bus.publish(
                Events.POOL_ANALYSIS_UPDATED,
                {"pool_tiers": self._pool_tiers, "market_state": market_state},
            )

    def analyze_pools(self, pools: list[PoolData]) -> list[PoolRiskTier]:
        """
        Perform full analysis on all pools:
          1. Classify risk tier
          2. Compute fee/liquidity ratio
          3. Detect reserve imbalance
          4. Estimate impermanent loss
          5. Score overall attractiveness
        """
        tiers: list[PoolRiskTier] = []

        for pool in pools:
            pair = f"{pool.token0_symbol}/{pool.token1_symbol}"

            # 1. Risk tier classification
            risk_tier = self._classify_risk_tier(pool)

            # 2. Fee to liquidity ratio
            fee_to_liq = FeatureEngineering.compute_fee_to_liquidity(pool)

            # 3. Reserve imbalance
            imbalance = FeatureEngineering.compute_reserve_imbalance(pool)

            # 4. Impermanent loss estimates
            il_1pct = FeatureEngineering.compute_impermanent_loss(0.01)
            il_5pct = FeatureEngineering.compute_impermanent_loss(0.05)

            # 5. Composite attractiveness score (0-100)
            score = self._compute_pool_score(pool, fee_to_liq, imbalance, risk_tier)

            tiers.append(PoolRiskTier(
                pool_address=pool.pool_address,
                token_pair=pair,
                risk_tier=risk_tier,
                liquidity_usd=pool.liquidity_usd,
                fee_to_liquidity_ratio=round(fee_to_liq, 6),
                reserve_imbalance=round(imbalance, 4),
                impermanent_loss_1pct=round(il_1pct, 6),
                impermanent_loss_5pct=round(il_5pct, 6),
                score=round(score, 2),
            ))

        return sorted(tiers, key=lambda t: t.score, reverse=True)

    @staticmethod
    def _classify_risk_tier(pool: PoolData) -> str:
        """Classify pool into risk tiers based on liquidity and token type."""
        BLUE_CHIP_TOKENS = {"WBNB", "BNB", "USDT", "USDC", "BUSD", "ETH", "BTCB", "CAKE"}

        is_blue_chip_pair = (
            pool.token0_symbol in BLUE_CHIP_TOKENS
            and pool.token1_symbol in BLUE_CHIP_TOKENS
        )

        if pool.liquidity_usd >= BLUE_CHIP_MIN and is_blue_chip_pair:
            return "blue_chip"
        elif pool.liquidity_usd >= MID_CAP_MIN:
            return "mid_cap"
        else:
            return "degen"

    @staticmethod
    def _compute_pool_score(
        pool: PoolData,
        fee_to_liq: float,
        imbalance: float,
        risk_tier: str,
    ) -> float:
        """
        Score a pool's attractiveness (0-100):
          - High fee/liquidity = good (capital efficient)
          - Moderate imbalance = good for arb, but too high = risky
          - Higher liquidity = safer
          - Blue-chip = bonus
        """
        score = 0.0

        # Fee efficiency (0-30 pts)
        # fee_to_liq of 0.001 (0.1% daily) is good
        fee_score = min(fee_to_liq * 10000, 30)
        score += fee_score

        # Liquidity depth (0-25 pts)
        if pool.liquidity_usd >= 10_000_000:
            score += 25
        elif pool.liquidity_usd >= 1_000_000:
            score += 20
        elif pool.liquidity_usd >= 100_000:
            score += 12
        elif pool.liquidity_usd >= 10_000:
            score += 5

        # Volume activity (0-20 pts)
        vol_ratio = pool.volume_24h_usd / pool.liquidity_usd if pool.liquidity_usd > 0 else 0
        score += min(vol_ratio * 100, 20)

        # Imbalance opportunity (0-15 pts) — moderate imbalance is good for arb
        if 0.05 < imbalance < 0.3:
            score += imbalance * 50  # 2.5 to 15 pts
        elif imbalance >= 0.3:
            score += 5  # Too imbalanced = risky, lower score

        # Risk tier bonus (0-10 pts)
        tier_bonus = {"blue_chip": 10, "mid_cap": 5, "degen": 0}
        score += tier_bonus.get(risk_tier, 0)

        return min(score, 100)

    def get_pools_by_tier(self, tier: str) -> list[PoolRiskTier]:
        """Get all pools in a specific risk tier."""
        return [p for p in self._pool_tiers if p.risk_tier == tier]

    def get_top_fee_pools(self, n: int = 5) -> list[PoolRiskTier]:
        """Get the top N pools by fee-to-liquidity ratio."""
        return sorted(self._pool_tiers, key=lambda t: t.fee_to_liquidity_ratio, reverse=True)[:n]

    def get_imbalanced_pools(self, min_imbalance: float = 0.1) -> list[PoolRiskTier]:
        """Get pools with reserve imbalance above threshold."""
        return [p for p in self._pool_tiers if p.reserve_imbalance >= min_imbalance]

    @property
    def stats(self) -> dict:
        tier_counts = {}
        for t in self._pool_tiers:
            tier_counts[t.risk_tier] = tier_counts.get(t.risk_tier, 0) + 1
        return {
            "analysis_count": self._analysis_count,
            "total_pools": len(self._pool_tiers),
            "v2_pools": self._v2_pools_seen,
            "v3_pools": self._v3_pools_seen,
            "tier_distribution": tier_counts,
            "avg_score": round(
                sum(t.score for t in self._pool_tiers) / len(self._pool_tiers), 2
            ) if self._pool_tiers else 0,
        }
