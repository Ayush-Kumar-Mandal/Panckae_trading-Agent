"""
Multi-Strategy Engine: supports arbitrage, trend-following, and mean-reversion.
Selects strategies based on the current market regime.
"""
from __future__ import annotations

from utils.logger import get_logger
from utils.models import MarketState, TradeProposal, MarketRegime, PoolData, ArbitrageOpportunity
from strategies.arbitrage.cross_pool import CrossPoolArbitrage
from strategies.arbitrage.profit_estimator import ProfitEstimator
from config.settings import StrategyConfig

logger = get_logger(__name__)


class MultiStrategyEngine:
    """
    Context-aware strategy engine that selects and weights strategies
    based on the detected market regime.

    Strategies:
      1. Cross-pool Arbitrage — always active
      2. Trend Following    — active in trending regimes
      3. Mean Reversion     — active in mean-reverting / low-volatility regimes
    """

    def __init__(self, strategy_config: StrategyConfig):
        self.config = strategy_config
        self.arb_detector = CrossPoolArbitrage(strategy_config)
        self.estimator = ProfitEstimator(
            slippage_pct=strategy_config.slippage_tolerance,
        )
        self._strategy_stats = {
            "arbitrage": {"signals": 0, "profit": 0.0},
            "trend_following": {"signals": 0, "profit": 0.0},
            "mean_reversion": {"signals": 0, "profit": 0.0},
        }

    def generate_proposals(self, market_state: MarketState) -> list[TradeProposal]:
        """
        Generate trade proposals from ALL active strategies,
        prioritized by the current regime.
        """
        proposals: list[TradeProposal] = []
        regime = market_state.regime

        # Strategy 1: Arbitrage — always active (regime-agnostic)
        arb_proposals = self._generate_arbitrage(market_state)
        proposals.extend(arb_proposals)

        # Strategy 2: Trend Following — active in trending regimes
        if regime.regime in ("trending_up", "trending_down", "neutral", "unknown"):
            trend_proposals = self._generate_trend_following(market_state)
            proposals.extend(trend_proposals)

        # Strategy 3: Mean Reversion — active in mean-reverting / low-vol regimes
        if regime.regime in ("mean_reverting", "low_volatility", "neutral", "unknown"):
            mr_proposals = self._generate_mean_reversion(market_state)
            proposals.extend(mr_proposals)

        # Sort by expected profit (descending)
        proposals.sort(key=lambda p: p.expected_profit_usd, reverse=True)

        # Log
        strat_breakdown = {}
        for p in proposals:
            strat_breakdown[p.strategy_type] = strat_breakdown.get(p.strategy_type, 0) + 1
        if proposals:
            logger.info(
                f"Multi-strategy: {len(proposals)} proposals | "
                f"regime={regime.regime} | "
                + " | ".join(f"{k}={v}" for k, v in strat_breakdown.items())
            )

        return proposals

    # ── Strategy 1: Arbitrage ─────────────────────────────────────

    def _generate_arbitrage(self, market_state: MarketState) -> list[TradeProposal]:
        """Cross-pool arbitrage: buy cheap, sell expensive."""
        opportunities = self.arb_detector.detect(market_state.pools)
        proposals: list[TradeProposal] = []

        for opp in opportunities:
            trade_size_usd = min(
                self.config.max_trade_size_usd,
                opp.pool_a.liquidity_usd * 0.01,
                opp.pool_b.liquidity_usd * 0.01,
            )
            if trade_size_usd < 1.0:
                continue

            estimate = self.estimator.estimate(opp, trade_size_usd)
            if not estimate["is_profitable"]:
                continue
            if estimate["net_profit_usd"] < self.config.min_profit_threshold_usd:
                continue

            proposal = TradeProposal(
                opportunity=opp,
                token_in=opp.pool_a.token1_address,
                token_out=opp.pool_a.token0_address,
                token_in_symbol=opp.pool_a.token1_symbol,
                token_out_symbol=opp.pool_a.token0_symbol,
                amount_in_usd=trade_size_usd,
                expected_amount_out=trade_size_usd / opp.buy_price if opp.buy_price > 0 else 0,
                expected_profit_usd=estimate["net_profit_usd"],
                gas_cost_usd=estimate["gas_cost_usd"],
                slippage_cost_usd=estimate["slippage_cost_usd"],
                confidence=min(opp.price_diff_pct / 0.05, 1.0),
                strategy_type="arbitrage",
            )
            proposals.append(proposal)
            self._strategy_stats["arbitrage"]["signals"] += 1

        return proposals

    # ── Strategy 2: Trend Following ───────────────────────────────

    def _generate_trend_following(self, market_state: MarketState) -> list[TradeProposal]:
        """
        Trend following: go long (buy) tokens with strong upward momentum.
        Uses regime trend_strength as the signal.
        """
        proposals: list[TradeProposal] = []
        regime = market_state.regime

        # Only act on strong trends with sufficient confidence
        if abs(regime.trend_strength) < 0.3 or regime.confidence < 0.4:
            return proposals

        # Find the most liquid pool for the trending pair
        if not market_state.pools:
            return proposals

        # Pick the most liquid pool
        best_pool = max(market_state.pools, key=lambda p: p.liquidity_usd)

        # Determine direction
        if regime.trend_strength > 0.3:
            # Uptrend — buy token0 (the volatile token)
            direction = "buy"
        elif regime.trend_strength < -0.3:
            # Downtrend — sell token0 / buy token1 (the stable)
            direction = "sell"
        else:
            return proposals

        trade_size = min(self.config.max_trade_size_usd, best_pool.liquidity_usd * 0.005)
        if trade_size < 1.0:
            return proposals

        # Expected profit: proportional to trend strength and confidence
        expected_profit = trade_size * abs(regime.trend_strength) * 0.02  # Conservative 2% of trend
        gas_cost = 0.30
        if expected_profit - gas_cost < self.config.min_profit_threshold_usd:
            return proposals

        # Create a synthetic opportunity for the proposal
        opp = ArbitrageOpportunity(
            pool_a=best_pool, pool_b=best_pool,
            token_pair=f"{best_pool.token0_symbol}/{best_pool.token1_symbol}",
            buy_pool=best_pool.pool_address, sell_pool=best_pool.pool_address,
            price_diff_pct=abs(regime.trend_strength) * 0.01,
            buy_price=best_pool.price_token0_in_token1,
            sell_price=best_pool.price_token0_in_token1,
            direction=f"trend_{direction}",
        )

        proposal = TradeProposal(
            opportunity=opp,
            token_in=best_pool.token1_address if direction == "buy" else best_pool.token0_address,
            token_out=best_pool.token0_address if direction == "buy" else best_pool.token1_address,
            token_in_symbol=best_pool.token1_symbol if direction == "buy" else best_pool.token0_symbol,
            token_out_symbol=best_pool.token0_symbol if direction == "buy" else best_pool.token1_symbol,
            amount_in_usd=trade_size,
            expected_amount_out=trade_size / best_pool.price_token0_in_token1 if best_pool.price_token0_in_token1 > 0 else 0,
            expected_profit_usd=round(expected_profit - gas_cost, 2),
            gas_cost_usd=gas_cost,
            slippage_cost_usd=trade_size * self.config.slippage_tolerance,
            confidence=round(regime.confidence * abs(regime.trend_strength), 3),
            strategy_type="trend_following",
            stop_loss_pct=0.03,  # Tighter stop for trend trades
        )
        proposals.append(proposal)
        self._strategy_stats["trend_following"]["signals"] += 1

        return proposals

    # ── Strategy 3: Mean Reversion ────────────────────────────────

    def _generate_mean_reversion(self, market_state: MarketState) -> list[TradeProposal]:
        """
        Mean reversion: trade against extreme moves, expecting price to revert.
        Active when market shows mean-reverting behavior.
        """
        proposals: list[TradeProposal] = []
        regime = market_state.regime

        if regime.mean_reversion_score < 0.2 or regime.confidence < 0.3:
            return proposals

        # Find pools where price has deviated significantly
        for pool in market_state.pools:
            if pool.liquidity_usd < self.config.min_liquidity_usd:
                continue

            # Check reserve imbalance — high imbalance = potential reversion opportunity
            imbalance = FeatureEngineering.compute_reserve_imbalance(pool)

            if imbalance < 0.05:  # Too balanced, no opportunity
                continue

            trade_size = min(self.config.max_trade_size_usd, pool.liquidity_usd * 0.005)
            if trade_size < 1.0:
                continue

            # Expected profit proportional to imbalance * reversion probability
            expected_profit = trade_size * imbalance * regime.mean_reversion_score * 0.5
            gas_cost = 0.30
            if expected_profit - gas_cost < self.config.min_profit_threshold_usd:
                continue

            opp = ArbitrageOpportunity(
                pool_a=pool, pool_b=pool,
                token_pair=f"{pool.token0_symbol}/{pool.token1_symbol}",
                buy_pool=pool.pool_address, sell_pool=pool.pool_address,
                price_diff_pct=imbalance,
                buy_price=pool.price_token0_in_token1,
                sell_price=pool.price_token0_in_token1,
                direction="mean_reversion",
            )

            proposal = TradeProposal(
                opportunity=opp,
                token_in=pool.token1_address,
                token_out=pool.token0_address,
                token_in_symbol=pool.token1_symbol,
                token_out_symbol=pool.token0_symbol,
                amount_in_usd=trade_size,
                expected_amount_out=trade_size / pool.price_token0_in_token1 if pool.price_token0_in_token1 > 0 else 0,
                expected_profit_usd=round(expected_profit - gas_cost, 2),
                gas_cost_usd=gas_cost,
                slippage_cost_usd=trade_size * self.config.slippage_tolerance,
                confidence=round(regime.mean_reversion_score * 0.8, 3),
                strategy_type="mean_reversion",
                stop_loss_pct=0.04,  # Wider stop for MR
                take_profit_pct=0.03,
            )
            proposals.append(proposal)
            self._strategy_stats["mean_reversion"]["signals"] += 1
            break  # Only one MR trade per cycle

        return proposals

    @property
    def strategy_stats(self) -> dict:
        return dict(self._strategy_stats)


# Import here to avoid circular at module level
from data.processors.feature_engineering import FeatureEngineering as FeatureEngineering
