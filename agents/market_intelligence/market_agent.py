"""
Market Intelligence Agent: builds a real-time market view,
detects opportunities, monitors regime changes, whale activity,
and anomalies. Publishes all findings to the event bus.
"""

from utils.logger import get_logger
from utils.models import MarketState, PoolData, ArbitrageOpportunity
from utils.constants import Events
from utils.helpers import timestamp_iso
from data.collectors.subgraph_collector import SubgraphCollector
from data.processors.pool_analyzer import PoolAnalyzer
from data.processors.feature_engineering import FeatureEngineering
from config.settings import StrategyConfig

logger = get_logger(__name__)


class MarketAgent:
    """
    The 'awareness layer' — continuously ingests data, builds market state,
    detects regime changes, whale activity, and anomalies,
    and publishes to the event bus for downstream agents.
    """

    def __init__(self, strategy_config: StrategyConfig, event_bus=None):
        self.config = strategy_config
        self.event_bus = event_bus
        self.collector = SubgraphCollector()
        self.analyzer = PoolAnalyzer(strategy_config)
        self.feature_eng = FeatureEngineering()
        self.scan_count: int = 0
        self.total_opportunities_found: int = 0
        self._last_regime = "unknown"
        self._whale_alert_count = 0
        self._anomaly_count = 0

    async def scan(self) -> MarketState:
        """
        Perform one full market scan cycle:
        1. Fetch pool data (V2 + V3 attempted)
        2. Update price/volume history for analysis
        3. Detect regime changes
        4. Detect whale activity
        5. Detect anomalies
        6. Analyze for arbitrage opportunities
        7. Build MarketState and publish
        """
        self.scan_count += 1

        # 1. Fetch pool data
        pools = await self.collector.fetch_pools()
        gas_price = await self.collector.fetch_gas_price()

        # 2. Update rolling history for regime/whale/anomaly detection
        self.feature_eng.update_history(pools)

        # 3. Regime detection
        regime = self.feature_eng.detect_regime()
        if regime.regime != self._last_regime and regime.regime != "unknown":
            logger.info(
                f"[REGIME] Change: {self._last_regime} -> {regime.regime} "
                f"(vol={regime.volatility:.4f}, trend={regime.trend_strength:+.2f}, "
                f"confidence={regime.confidence:.0%})"
            )
            self._last_regime = regime.regime
            if self.event_bus:
                await self.event_bus.publish(
                    Events.REGIME_CHANGE, {"regime": regime}
                )

        # 4. Whale activity detection
        whale_alerts = self.feature_eng.detect_whale_activity(pools)
        self._whale_alert_count += len(whale_alerts)
        for alert in whale_alerts:
            if self.event_bus:
                await self.event_bus.publish(
                    Events.WHALE_ALERT, {"alert": alert}
                )

        # 5. Anomaly detection
        anomalies = self.feature_eng.detect_anomalies(pools)
        self._anomaly_count += len(anomalies)
        for anomaly in anomalies:
            logger.warning(
                f"[ANOMALY] {anomaly.severity.upper()}: {anomaly.anomaly_type} "
                f"on {anomaly.token_pair} — {anomaly.description}"
            )
            if self.event_bus:
                await self.event_bus.publish(
                    Events.ANOMALY_DETECTED, {"anomaly": anomaly}
                )

        # 6. Detect arbitrage opportunities
        opportunities = self.analyzer.find_opportunities(pools)
        self.total_opportunities_found += len(opportunities)

        # 7. Build market state
        market_state = MarketState(
            pools=pools,
            opportunities=opportunities,
            gas_price_gwei=gas_price,
            timestamp=timestamp_iso(),
            regime=regime,
            whale_alerts=whale_alerts,
            anomalies=anomalies,
        )

        logger.info(
            f"Market scan #{self.scan_count}: "
            f"{len(pools)} pools | "
            f"{len(opportunities)} opps | "
            f"regime={regime.regime} | "
            f"gas={gas_price:.1f} gwei"
            + (f" | {len(whale_alerts)} whale alerts" if whale_alerts else "")
            + (f" | {len(anomalies)} ANOMALIES" if anomalies else "")
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
            "current_regime": self._last_regime,
            "whale_alerts": self._whale_alert_count,
            "anomalies_detected": self._anomaly_count,
        }
