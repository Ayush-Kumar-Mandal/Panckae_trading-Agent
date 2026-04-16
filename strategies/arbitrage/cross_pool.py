"""
Cross-pool arbitrage detection.
Wraps the PoolAnalyzer and provides a clean interface for the strategy agent.
"""

from utils.logger import get_logger
from utils.models import PoolData, ArbitrageOpportunity
from data.processors.pool_analyzer import PoolAnalyzer
from config.settings import StrategyConfig

logger = get_logger(__name__)


class CrossPoolArbitrage:
    """
    Detects arbitrage opportunities across multiple pools for the same token pair.
    
    Strategy: Buy from the pool with the lower price, sell to the pool
    with the higher price, pocket the difference minus fees.
    """

    def __init__(self, strategy_config: StrategyConfig):
        self.config = strategy_config
        self.analyzer = PoolAnalyzer(strategy_config)

    def detect(self, pools: list[PoolData]) -> list[ArbitrageOpportunity]:
        """
        Scan all pools and return viable arbitrage opportunities.
        Filters by minimum gap percentage from config.
        """
        opportunities = self.analyzer.find_opportunities(pools)

        # Additional filtering: ensure price diff covers at least 2x the fee
        viable = []
        for opp in opportunities:
            total_fee = opp.pool_a.fee_tier + opp.pool_b.fee_tier  # Two swaps
            if opp.price_diff_pct > total_fee:
                viable.append(opp)
            else:
                logger.debug(
                    f"Filtered out {opp.token_pair}: price diff {opp.price_diff_pct:.2%} "
                    f"< total fees {total_fee:.2%}"
                )

        logger.info(
            f"Cross-pool scan: {len(viable)} viable opportunities from {len(pools)} pools"
        )
        return viable
