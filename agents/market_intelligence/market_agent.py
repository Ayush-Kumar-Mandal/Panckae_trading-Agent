"""
Market Intelligence Agent: builds a real-time market view,
detects opportunities, and publishes them to the event bus.
"""

from utils.logger import get_logger
from utils.models import MarketState, PoolData, ArbitrageOpportunity
from utils.constants import Events
from utils.helpers import timestamp_iso
from data.collectors.subgraph_collector import SubgraphCollector
from data.processors.pool_analyzer import PoolAnalyzer
from config.settings import StrategyConfig

logger = get_logger(__name__)


class MarketAgent:
    """
    The 'awareness layer' — continuously ingests data, builds market state,
    and publishes detected opportunities for the strategy agent.
    """

    def __init__(self, strategy_config: StrategyConfig, event_bus=None):
        self.config = strategy_config
        self.event_bus = event_bus
        self.collector = SubgraphCollector()
        self.analyzer = PoolAnalyzer(strategy_config)
        self.scan_count: int = 0
        self.total_opportunities_found: int = 0

    async def scan(self) -> MarketState:
        """
        Perform one market scan cycle:
        1. Fetch pool data
        2. Analyze for opportunities
        3. Build MarketState
        4. Publish to event bus
        """
        self.scan_count += 1

        # Fetch pool data
        pools = await self.collector.fetch_pools()
        gas_price = await self.collector.fetch_gas_price()

        # Detect opportunities
        opportunities = self.analyzer.find_opportunities(pools)
        self.total_opportunities_found += len(opportunities)

        # Build market state
        market_state = MarketState(
            pools=pools,
            opportunities=opportunities,
            gas_price_gwei=gas_price,
            timestamp=timestamp_iso(),
        )

        logger.info(
            f"🔍 Market scan #{self.scan_count}: "
            f"{len(pools)} pools | "
            f"{len(opportunities)} opportunities | "
            f"gas={gas_price:.1f} gwei"
        )

        # Publish to event bus
        if self.event_bus and opportunities:
            await self.event_bus.publish(
                Events.MARKET_OPPORTUNITY,
                {"market_state": market_state},
            )

        return market_state

    @property
    def stats(self) -> dict:
        return {
            "scan_count": self.scan_count,
            "total_opportunities_found": self.total_opportunities_found,
        }
