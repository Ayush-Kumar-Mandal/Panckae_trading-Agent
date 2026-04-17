"""
Arbitrage Strategy Agent: converts market opportunities into trade proposals.
"""
from __future__ import annotations

from utils.logger import get_logger
from utils.models import ArbitrageOpportunity, TradeProposal, MarketState
from strategies.arbitrage.cross_pool import CrossPoolArbitrage
from strategies.arbitrage.profit_estimator import ProfitEstimator
from config.settings import StrategyConfig

logger = get_logger(__name__)


class ArbitrageStrategy:
    """
    Generates TradeProposals from detected ArbitrageOpportunities.
    Sizes positions, estimates profit, and outputs structured proposals.
    """

    def __init__(self, strategy_config: StrategyConfig):
        self.config = strategy_config
        self.detector = CrossPoolArbitrage(strategy_config)
        self.estimator = ProfitEstimator(
            slippage_pct=strategy_config.slippage_tolerance,
        )

    def generate_proposals(
        self, market_state: MarketState
    ) -> list[TradeProposal]:
        """
        Analyze market state and return trade proposals for profitable
        arbitrage opportunities.
        """
        # Step 1: Detect arbitrage opportunities from pool data
        opportunities = self.detector.detect(market_state.pools)

        if not opportunities:
            logger.debug("No arbitrage opportunities to evaluate")
            return []

        proposals: list[TradeProposal] = []

        for opp in opportunities:
            # Step 2: Determine trade size (capped by config)
            trade_size_usd = min(
                self.config.max_trade_size_usd,
                opp.pool_a.liquidity_usd * 0.01,  # Max 1% of pool liquidity
                opp.pool_b.liquidity_usd * 0.01,
            )

            if trade_size_usd < 1.0:
                continue  # Too small to bother

            # Step 3: Estimate profit
            estimate = self.estimator.estimate(opp, trade_size_usd)

            if not estimate["is_profitable"]:
                logger.debug(
                    f"Skipping {opp.token_pair}: not profitable "
                    f"(net=${estimate['net_profit_usd']:.2f})"
                )
                continue

            if estimate["net_profit_usd"] < self.config.min_profit_threshold_usd:
                logger.debug(
                    f"Skipping {opp.token_pair}: profit ${estimate['net_profit_usd']:.2f} "
                    f"< threshold ${self.config.min_profit_threshold_usd:.2f}"
                )
                continue

            # Step 4: Build trade proposal
            proposal = TradeProposal(
                opportunity=opp,
                token_in=opp.pool_a.token1_address,   # Pay with stablecoin
                token_out=opp.pool_a.token0_address,   # Buy the volatile token
                token_in_symbol=opp.pool_a.token1_symbol,
                token_out_symbol=opp.pool_a.token0_symbol,
                amount_in_usd=trade_size_usd,
                expected_amount_out=trade_size_usd / opp.buy_price if opp.buy_price > 0 else 0,
                expected_profit_usd=estimate["net_profit_usd"],
                gas_cost_usd=estimate["gas_cost_usd"],
                slippage_cost_usd=estimate["slippage_cost_usd"],
                confidence=min(opp.price_diff_pct / 0.05, 1.0),  # Scale to 0-1
            )
            proposals.append(proposal)

            logger.info(
                f"📊 Trade proposal: {opp.token_pair} | "
                f"size=${trade_size_usd:.2f} | "
                f"expected profit=${estimate['net_profit_usd']:.2f} | "
                f"price diff={opp.price_diff_pct:.2%}"
            )

        logger.info(f"Generated {len(proposals)} trade proposals from {len(opportunities)} opportunities")
        return proposals
