"""
Unit Tests for Strategy Layer:
  - CrossPoolArbitrage detection
  - ProfitEstimator accuracy
  - ArbitrageStrategy proposal generation
  - AMM math utilities
"""
from __future__ import annotations

import sys
import os
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.models import PoolData, ArbitrageOpportunity, MarketState
from config.settings import StrategyConfig
from strategies.arbitrage.cross_pool import CrossPoolArbitrage
from strategies.arbitrage.profit_estimator import ProfitEstimator
from strategies.arbitrage.price_diff import calculate_price_diff
from strategies.utils import amm_price, price_impact
from agents.strategy.arbitrage_strategy import ArbitrageStrategy


def make_pool(
    token0="WBNB", token1="USDT", price=300.0, reserve0=5000.0, reserve1=None,
    liquidity_usd=3_000_000.0, address="0xabc", source="mock"
) -> PoolData:
    """Helper: create a PoolData with sensible defaults."""
    if reserve1 is None:
        reserve1 = reserve0 * price
    return PoolData(
        pool_address=address,
        token0_symbol=token0,
        token1_symbol=token1,
        token0_address="0xt0",
        token1_address="0xt1",
        reserve0=reserve0,
        reserve1=reserve1,
        price_token0_in_token1=price,
        price_token1_in_token0=1.0 / price if price > 0 else 0,
        liquidity_usd=liquidity_usd,
        volume_24h_usd=100_000.0,
        fee_tier=0.0025,
        source=source,
    )


# ══════════════════════════════════════════════════════════════════
# Test: AMM Math Utilities
# ══════════════════════════════════════════════════════════════════
class TestAMMMath(unittest.TestCase):
    """Test constant-product math functions."""

    def test_amm_price(self):
        # reserve_out / reserve_in = 1500000 / 5000 = 300
        result = amm_price(5000.0, 1_500_000.0)
        self.assertAlmostEqual(result, 300.0, places=2)

    def test_amm_price_zero_reserve(self):
        result = amm_price(0, 1000.0)
        self.assertEqual(result, 0.0)

    def test_price_impact(self):
        # Buying 100 from a pool with 5000 reserve
        impact = price_impact(100.0, 5000.0)
        # 100 / (5000 + 100) ~ 0.02 -> small impact
        self.assertGreater(impact, 0)
        self.assertLess(impact, 0.05)

    def test_price_impact_large_trade(self):
        # Large trade should have high impact
        impact = price_impact(5000.0, 5000.0)
        # 5000 / (5000 + 5000) = 0.5 -> 50% impact
        self.assertAlmostEqual(impact, 0.5, places=2)


# ══════════════════════════════════════════════════════════════════
# Test: Price Diff Calculator
# ══════════════════════════════════════════════════════════════════
class TestPriceDiff(unittest.TestCase):
    """Test price comparison between pools."""

    def test_price_diff_same_price(self):
        pool_a = make_pool(price=300.0, address="0xa")
        pool_b = make_pool(price=300.0, address="0xb")
        result = calculate_price_diff(pool_a, pool_b)
        self.assertAlmostEqual(result["diff_pct"], 0.0, places=4)

    def test_price_diff_3_percent(self):
        pool_a = make_pool(price=300.0, address="0xa")
        pool_b = make_pool(price=309.0, address="0xb")
        result = calculate_price_diff(pool_a, pool_b)
        self.assertAlmostEqual(result["diff_pct"], 9.0 / 304.5, places=3)
        self.assertEqual(result["cheaper_pool"], "A")

    def test_price_diff_zero_price(self):
        pool_a = make_pool(price=0.0, address="0xa")
        pool_b = make_pool(price=0.0, address="0xb")
        result = calculate_price_diff(pool_a, pool_b)
        self.assertEqual(result["diff_pct"], 0)


# ══════════════════════════════════════════════════════════════════
# Test: Cross-Pool Arbitrage Detection
# ══════════════════════════════════════════════════════════════════
class TestCrossPoolArbitrage(unittest.TestCase):
    """Test cross-pool opportunity detection."""

    def setUp(self):
        self.config = StrategyConfig(arbitrage_gap_pct=0.01, min_liquidity_usd=500.0)
        self.detector = CrossPoolArbitrage(self.config)

    def test_detects_opportunity(self):
        """Two pools for same pair with >1% price diff should be detected."""
        pools = [
            make_pool(price=300.0, address="0xa"),
            make_pool(price=310.0, address="0xb"),
        ]
        opportunities = self.detector.detect(pools)
        self.assertGreater(len(opportunities), 0)
        self.assertEqual(opportunities[0].token_pair, "WBNB/USDT")

    def test_no_opportunity_small_diff(self):
        """Pools with <1% price diff should not generate opportunities."""
        pools = [
            make_pool(price=300.0, address="0xa"),
            make_pool(price=300.5, address="0xb"),
        ]
        opportunities = self.detector.detect(pools)
        self.assertEqual(len(opportunities), 0)

    def test_no_opportunity_single_pool(self):
        """Single pool cannot have arbitrage."""
        pools = [make_pool(price=300.0)]
        opportunities = self.detector.detect(pools)
        self.assertEqual(len(opportunities), 0)

    def test_multiple_pairs(self):
        """Pools for different pairs should be analyzed independently."""
        pools = [
            make_pool(token0="WBNB", token1="USDT", price=300.0, address="0xa"),
            make_pool(token0="WBNB", token1="USDT", price=312.0, address="0xb"),
            make_pool(token0="CAKE", token1="USDT", price=2.50, address="0xc"),
            make_pool(token0="CAKE", token1="USDT", price=2.60, address="0xd"),
        ]
        opportunities = self.detector.detect(pools)
        pairs = set(o.token_pair for o in opportunities)
        self.assertIn("WBNB/USDT", pairs)
        self.assertIn("CAKE/USDT", pairs)

    def test_low_liquidity_filtered(self):
        """Pools with liquidity below min should be skipped."""
        pools = [
            make_pool(price=300.0, liquidity_usd=100.0, address="0xa"),  # Too low
            make_pool(price=310.0, liquidity_usd=100.0, address="0xb"),  # Too low
        ]
        opportunities = self.detector.detect(pools)
        self.assertEqual(len(opportunities), 0)


# ══════════════════════════════════════════════════════════════════
# Test: Profit Estimator
# ══════════════════════════════════════════════════════════════════
class TestProfitEstimator(unittest.TestCase):
    """Test profit estimation including gas and slippage."""

    def setUp(self):
        self.estimator = ProfitEstimator(slippage_pct=0.005)

    def test_profitable_trade(self):
        opp = ArbitrageOpportunity(
            pool_a=make_pool(price=300.0, address="0xa"),
            pool_b=make_pool(price=312.0, address="0xb"),
            token_pair="WBNB/USDT",
            buy_pool="0xa",
            sell_pool="0xb",
            price_diff_pct=0.04,
            buy_price=300.0,
            sell_price=312.0,
            direction="buy_A_sell_B",
        )
        result = self.estimator.estimate(opp, trade_size_usd=100.0)
        self.assertTrue(result["is_profitable"])
        self.assertGreater(result["net_profit_usd"], 0)

    def test_unprofitable_tiny_gap(self):
        opp = ArbitrageOpportunity(
            pool_a=make_pool(price=300.0, address="0xa"),
            pool_b=make_pool(price=300.5, address="0xb"),
            token_pair="WBNB/USDT",
            buy_pool="0xa",
            sell_pool="0xb",
            price_diff_pct=0.001,
            buy_price=300.0,
            sell_price=300.5,
            direction="buy_A_sell_B",
        )
        result = self.estimator.estimate(opp, trade_size_usd=10.0)
        # Tiny gap with $10 trade should not be profitable after gas
        self.assertFalse(result["is_profitable"])

    def test_estimate_includes_gas(self):
        opp = ArbitrageOpportunity(
            pool_a=make_pool(price=300.0, address="0xa"),
            pool_b=make_pool(price=310.0, address="0xb"),
            token_pair="WBNB/USDT",
            buy_pool="0xa", sell_pool="0xb",
            price_diff_pct=0.033, buy_price=300.0, sell_price=310.0,
            direction="buy_A_sell_B",
        )
        result = self.estimator.estimate(opp, trade_size_usd=100.0)
        self.assertGreater(result["gas_cost_usd"], 0)
        self.assertGreater(result["slippage_cost_usd"], 0)


# ══════════════════════════════════════════════════════════════════
# Test: ArbitrageStrategy (end-to-end proposals)
# ══════════════════════════════════════════════════════════════════
class TestArbitrageStrategy(unittest.TestCase):
    """Test the full strategy pipeline: pools -> proposals."""

    def setUp(self):
        self.config = StrategyConfig(
            min_profit_threshold_usd=0.50,
            slippage_tolerance=0.005,
            arbitrage_gap_pct=0.01,
            max_trade_size_usd=100.0,
            min_liquidity_usd=1000.0,
        )
        self.strategy = ArbitrageStrategy(self.config)

    def test_generates_proposals_from_market(self):
        """Full pipeline: market state with price gaps -> proposals."""
        pools = [
            make_pool(price=300.0, address="0xa"),
            make_pool(price=312.0, address="0xb"),
        ]
        market = MarketState(pools=pools, gas_price_gwei=5.0)
        proposals = self.strategy.generate_proposals(market)
        self.assertGreater(len(proposals), 0)
        self.assertIsNotNone(proposals[0].opportunity)
        self.assertGreater(proposals[0].expected_profit_usd, 0)
        self.assertGreater(proposals[0].amount_in_usd, 0)

    def test_no_proposals_no_gap(self):
        """No price gap -> no proposals."""
        pools = [
            make_pool(price=300.0, address="0xa"),
            make_pool(price=300.1, address="0xb"),
        ]
        market = MarketState(pools=pools, gas_price_gwei=5.0)
        proposals = self.strategy.generate_proposals(market)
        self.assertEqual(len(proposals), 0)

    def test_trade_size_capped(self):
        """Trade size should not exceed max_trade_size_usd."""
        pools = [
            make_pool(price=300.0, liquidity_usd=50_000_000, address="0xa"),
            make_pool(price=315.0, liquidity_usd=50_000_000, address="0xb"),
        ]
        market = MarketState(pools=pools, gas_price_gwei=5.0)
        proposals = self.strategy.generate_proposals(market)
        if proposals:
            self.assertLessEqual(proposals[0].amount_in_usd, self.config.max_trade_size_usd)

    def test_empty_pool_list(self):
        """Empty pools -> no proposals."""
        market = MarketState(pools=[], gas_price_gwei=5.0)
        proposals = self.strategy.generate_proposals(market)
        self.assertEqual(len(proposals), 0)


if __name__ == "__main__":
    unittest.main()
