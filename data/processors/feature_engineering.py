"""
Feature Engineering: compute derived metrics from raw pool data.
Includes: volatility, regime detection, whale detection, anomaly detection.
"""

import math
import time
from collections import defaultdict
from typing import Optional
from utils.logger import get_logger
from utils.models import PoolData, MarketRegime, WhaleAlert, AnomalyAlert

logger = get_logger(__name__)


class FeatureEngineering:
    """Computes derived features from raw pool data for strategy consumption."""

    def __init__(self):
        # Price history per pair for volatility/regime analysis
        self._price_history: dict[str, list[float]] = defaultdict(list)
        self._volume_history: dict[str, list[float]] = defaultdict(list)
        self._liquidity_history: dict[str, list[float]] = defaultdict(list)
        self._max_history = 100  # Keep last 100 data points

    # ── Basic Pool Metrics ────────────────────────────────────────

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
    def compute_fee_to_liquidity(pool: PoolData) -> float:
        """Fee income relative to pool liquidity — measures capital efficiency."""
        if pool.liquidity_usd == 0:
            return 0.0
        # Estimate daily fee: volume * fee_tier
        estimated_fee = pool.volume_24h_usd * pool.fee_tier
        return estimated_fee / pool.liquidity_usd

    @staticmethod
    def compute_reserve_imbalance(pool: PoolData) -> float:
        """
        Measures how far the pool is from 50/50 balance.
        0.0 = perfectly balanced, 1.0 = completely imbalanced.
        """
        if pool.liquidity_usd == 0:
            return 0.0
        # Convert reserves to USD value
        val0 = pool.reserve0 * pool.price_token0_in_token1 if pool.price_token0_in_token1 else 0
        val1 = pool.reserve1
        total = val0 + val1
        if total == 0:
            return 0.0
        ratio = val0 / total  # Should be ~0.5 for balanced pool
        return abs(ratio - 0.5) * 2  # Scale to 0-1

    @staticmethod
    def compute_impermanent_loss(price_change_pct: float) -> float:
        """
        Calculate impermanent loss for a given price change.
        IL = 2 * sqrt(price_ratio) / (1 + price_ratio) - 1
        """
        price_ratio = 1 + price_change_pct
        if price_ratio <= 0:
            return -1.0
        il = 2 * math.sqrt(price_ratio) / (1 + price_ratio) - 1
        return il

    # ── Volatility & Regime Detection ─────────────────────────────

    @staticmethod
    def compute_price_volatility(price_history: list[float]) -> float:
        """Rolling standard deviation of prices."""
        if len(price_history) < 2:
            return 0.0
        mean = sum(price_history) / len(price_history)
        variance = sum((p - mean) ** 2 for p in price_history) / (len(price_history) - 1)
        return math.sqrt(variance)

    @staticmethod
    def compute_returns(prices: list[float]) -> list[float]:
        """Compute log returns from price series."""
        returns = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                returns.append(math.log(prices[i] / prices[i - 1]))
        return returns

    def update_history(self, pools: list[PoolData]) -> None:
        """Record current pool data into rolling history."""
        for pool in pools:
            pair = f"{pool.token0_symbol}/{pool.token1_symbol}"
            self._price_history[pair].append(pool.price_token0_in_token1)
            self._volume_history[pair].append(pool.volume_24h_usd)
            self._liquidity_history[pair].append(pool.liquidity_usd)
            # Trim to max history
            for hist in (self._price_history, self._volume_history, self._liquidity_history):
                if len(hist[pair]) > self._max_history:
                    hist[pair] = hist[pair][-self._max_history:]

    def detect_regime(self, pair: str = None) -> MarketRegime:
        """
        Classify the current market regime based on price history.
        Uses: volatility, trend direction, mean-reversion tendency.
        """
        # Aggregate across all pairs if no specific pair given
        if pair and pair in self._price_history:
            prices = self._price_history[pair]
        else:
            # Use the pair with most history
            if not self._price_history:
                return MarketRegime(regime="unknown", confidence=0.0)
            pair = max(self._price_history, key=lambda k: len(self._price_history[k]))
            prices = self._price_history[pair]

        if len(prices) < 5:
            return MarketRegime(regime="unknown", confidence=0.0)

        # 1) Volatility
        returns = self.compute_returns(prices)
        if not returns:
            return MarketRegime(regime="unknown", confidence=0.0)

        volatility = self.compute_price_volatility(returns)

        # Volatility percentile (relative to history)
        if len(returns) >= 10:
            rolling_vols = []
            for i in range(5, len(returns)):
                window = returns[max(0, i - 5):i]
                rolling_vols.append(self.compute_price_volatility(window))
            vol_percentile = sum(1 for v in rolling_vols if v <= volatility) / len(rolling_vols) if rolling_vols else 0.5
        else:
            vol_percentile = 0.5

        # 2) Trend strength (simple: sign of recent returns)
        recent = returns[-min(10, len(returns)):]
        avg_return = sum(recent) / len(recent) if recent else 0
        positive_count = sum(1 for r in recent if r > 0)
        trend_strength = (positive_count / len(recent) - 0.5) * 2 if recent else 0  # -1 to +1

        # 3) Mean-reversion score (autocorrelation of returns)
        if len(returns) >= 4:
            mean_ret = sum(returns) / len(returns)
            autocorr_sum = sum(
                (returns[i] - mean_ret) * (returns[i - 1] - mean_ret)
                for i in range(1, len(returns))
            )
            var_sum = sum((r - mean_ret) ** 2 for r in returns)
            autocorrelation = autocorr_sum / var_sum if var_sum > 0 else 0
            # Negative autocorrelation = mean-reverting
            mean_reversion_score = max(0, -autocorrelation)
        else:
            mean_reversion_score = 0.0
            autocorrelation = 0.0

        # 4) Classify regime
        if vol_percentile > 0.8:
            regime = "high_volatility"
            confidence = vol_percentile
        elif vol_percentile < 0.2:
            regime = "low_volatility"
            confidence = 1.0 - vol_percentile
        elif trend_strength > 0.3:
            regime = "trending_up"
            confidence = min(abs(trend_strength), 1.0)
        elif trend_strength < -0.3:
            regime = "trending_down"
            confidence = min(abs(trend_strength), 1.0)
        elif mean_reversion_score > 0.3:
            regime = "mean_reverting"
            confidence = min(mean_reversion_score, 1.0)
        else:
            regime = "neutral"
            confidence = 0.5

        return MarketRegime(
            regime=regime,
            volatility=volatility,
            volatility_percentile=round(vol_percentile, 3),
            trend_strength=round(trend_strength, 3),
            mean_reversion_score=round(mean_reversion_score, 3),
            confidence=round(confidence, 3),
        )

    # ── Whale & Large Swap Detection ──────────────────────────────

    def detect_whale_activity(self, pools: list[PoolData]) -> list[WhaleAlert]:
        """
        Detect whale-like activity by comparing current volume to historical.
        If volume spikes >3x average, flag as potential whale.
        """
        alerts: list[WhaleAlert] = []

        for pool in pools:
            pair = f"{pool.token0_symbol}/{pool.token1_symbol}"
            vol_history = self._volume_history.get(pair, [])

            if len(vol_history) < 3:
                continue

            avg_vol = sum(vol_history[:-1]) / (len(vol_history) - 1)
            current_vol = pool.volume_24h_usd

            if avg_vol > 0 and current_vol > avg_vol * 3:
                impact = min((current_vol / avg_vol - 1) / 10, 1.0)  # Scale 0-1
                alerts.append(WhaleAlert(
                    event_type="volume_spike",
                    token_pair=pair,
                    amount_usd=current_vol,
                    pool_address=pool.pool_address,
                    impact_score=round(impact, 3),
                ))
                logger.warning(
                    f"WHALE ALERT: {pair} volume spike {current_vol/avg_vol:.1f}x "
                    f"(${current_vol:,.0f} vs avg ${avg_vol:,.0f})"
                )

            # Check for liquidity drain
            liq_history = self._liquidity_history.get(pair, [])
            if len(liq_history) >= 3:
                avg_liq = sum(liq_history[:-1]) / (len(liq_history) - 1)
                if avg_liq > 0 and pool.liquidity_usd < avg_liq * 0.5:
                    alerts.append(WhaleAlert(
                        event_type="liquidity_remove",
                        token_pair=pair,
                        amount_usd=avg_liq - pool.liquidity_usd,
                        pool_address=pool.pool_address,
                        impact_score=0.8,
                    ))
                    logger.warning(
                        f"LIQUIDITY DRAIN: {pair} lost {(1 - pool.liquidity_usd/avg_liq)*100:.0f}% liquidity"
                    )

        return alerts

    # ── Anomaly Detection ─────────────────────────────────────────

    def detect_anomalies(self, pools: list[PoolData]) -> list[AnomalyAlert]:
        """
        Detect market anomalies that require defensive action:
        - Flash crash (>10% price drop in 1 cycle)
        - Depeg (stablecoin deviating >2% from $1)
        - Liquidity drain (>50% liquidity removed)
        - Extreme volume spike (>10x normal)
        """
        anomalies: list[AnomalyAlert] = []
        STABLECOINS = {"USDT", "USDC", "BUSD", "DAI", "TUSD"}

        for pool in pools:
            pair = f"{pool.token0_symbol}/{pool.token1_symbol}"
            prices = self._price_history.get(pair, [])

            # Flash crash detection: >10% price drop
            if len(prices) >= 2:
                prev_price = prices[-2]
                curr_price = prices[-1]
                if prev_price > 0:
                    change_pct = (curr_price - prev_price) / prev_price
                    if change_pct < -0.10:
                        anomalies.append(AnomalyAlert(
                            anomaly_type="flash_crash",
                            severity="critical" if change_pct < -0.20 else "high",
                            token_pair=pair,
                            description=f"Price dropped {change_pct*100:.1f}% in one cycle",
                            recommended_action="pause",
                        ))
                    elif change_pct > 0.15:
                        anomalies.append(AnomalyAlert(
                            anomaly_type="flash_crash",
                            severity="high",
                            token_pair=pair,
                            description=f"Price surged {change_pct*100:.1f}% — possible manipulation",
                            recommended_action="reduce_exposure",
                        ))

            # Stablecoin depeg detection
            for symbol in (pool.token0_symbol, pool.token1_symbol):
                if symbol in STABLECOINS:
                    # If this is token0, check its USD price
                    if symbol == pool.token0_symbol and pool.token1_symbol in STABLECOINS:
                        price_vs_stable = pool.price_token0_in_token1
                        if abs(price_vs_stable - 1.0) > 0.02:  # >2% depeg
                            anomalies.append(AnomalyAlert(
                                anomaly_type="depeg",
                                severity="critical" if abs(price_vs_stable - 1.0) > 0.05 else "high",
                                token_pair=pair,
                                description=f"{symbol} at ${price_vs_stable:.4f} — depegged by {abs(price_vs_stable-1)*100:.1f}%",
                                recommended_action="exit_all",
                            ))

            # Extreme volume spike (>10x normal)
            vol_history = self._volume_history.get(pair, [])
            if len(vol_history) >= 5:
                avg_vol = sum(vol_history[:-1]) / (len(vol_history) - 1)
                if avg_vol > 0 and pool.volume_24h_usd > avg_vol * 10:
                    anomalies.append(AnomalyAlert(
                        anomaly_type="volume_spike",
                        severity="medium",
                        token_pair=pair,
                        description=f"Volume {pool.volume_24h_usd/avg_vol:.0f}x above normal",
                        recommended_action="reduce_exposure",
                    ))

        return anomalies

    # ── Aggregated Compute ────────────────────────────────────────

    @staticmethod
    def compute_all(pool: PoolData) -> dict:
        """Compute all features for a pool."""
        return {
            "liquidity_ratio": FeatureEngineering.compute_liquidity_ratio(pool),
            "volume_to_liquidity": FeatureEngineering.compute_volume_to_liquidity(pool),
            "fee_to_liquidity": FeatureEngineering.compute_fee_to_liquidity(pool),
            "reserve_imbalance": FeatureEngineering.compute_reserve_imbalance(pool),
            "impermanent_loss_1pct": FeatureEngineering.compute_impermanent_loss(0.01),
            "impermanent_loss_5pct": FeatureEngineering.compute_impermanent_loss(0.05),
            "price_token0": pool.price_token0_in_token1,
            "price_token1": pool.price_token1_in_token0,
            "liquidity_usd": pool.liquidity_usd,
            "volume_24h_usd": pool.volume_24h_usd,
        }
