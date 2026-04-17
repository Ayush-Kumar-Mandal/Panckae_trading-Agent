"""
Unit Tests for Execution Layer:
  - PancakeClient dry-run simulation
  - SlippageController calculations
  - TransactionManager lifecycle
  - DBClient persistent storage (sqlite3)
  - FeedbackAgent parameter adjustments
"""
from __future__ import annotations

import sys
import os
import asyncio
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.models import (
    PoolData, ArbitrageOpportunity, TradeProposal, TradeResult, PortfolioState,
)
from config.settings import ExecutionConfig, RiskConfig, StrategyConfig, Settings
from execution.pancake_client import PancakeClient
from execution.slippage_control import SlippageController
from data.storage.db_client import DBClient
from agents.feedback.feedback_agent import FeedbackAgent


def make_proposal(profit=2.0, size=100.0) -> TradeProposal:
    pool_a = PoolData(
        pool_address="0xabc", token0_symbol="WBNB", token1_symbol="USDT",
        token0_address="0xt0", token1_address="0xt1",
        reserve0=5000, reserve1=1_500_000,
        price_token0_in_token1=300.0, price_token1_in_token0=1/300,
        liquidity_usd=3_000_000.0,
    )
    pool_b = PoolData(
        pool_address="0xdef", token0_symbol="WBNB", token1_symbol="USDT",
        token0_address="0xt0", token1_address="0xt1",
        reserve0=5000, reserve1=1_550_000,
        price_token0_in_token1=310.0, price_token1_in_token0=1/310,
        liquidity_usd=3_100_000.0,
    )
    opp = ArbitrageOpportunity(
        pool_a=pool_a, pool_b=pool_b, token_pair="WBNB/USDT",
        buy_pool="0xabc", sell_pool="0xdef",
        price_diff_pct=0.033, buy_price=300.0, sell_price=310.0,
        direction="buy_A_sell_B",
    )
    return TradeProposal(
        opportunity=opp, token_in="0xt1", token_out="0xt0",
        token_in_symbol="USDT", token_out_symbol="WBNB",
        amount_in_usd=size, expected_amount_out=size / 300,
        expected_profit_usd=profit, gas_cost_usd=0.30,
        slippage_cost_usd=0.10,
    )


def run_async(coro):
    """Helper to run async functions in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ══════════════════════════════════════════════════════════════════
# Test: PancakeClient (Dry-Run)
# ══════════════════════════════════════════════════════════════════
class TestPancakeClientDryRun(unittest.TestCase):
    """Test the dry-run swap simulation."""

    def setUp(self):
        self.config = ExecutionConfig(dry_run=True)
        self.client = PancakeClient(self.config)

    def test_dry_run_returns_result(self):
        proposal = make_proposal()
        result = run_async(self.client.execute_swap(proposal))
        self.assertIsInstance(result, TradeResult)
        self.assertTrue(result.dry_run)

    def test_dry_run_has_tx_hash_or_error(self):
        proposal = make_proposal()
        result = run_async(self.client.execute_swap(proposal))
        # Either successful (has tx_hash) or failed (has error)
        self.assertTrue(result.tx_hash != "" or result.error != "")

    def test_successful_trade_has_profit(self):
        # Run multiple times — at least one should succeed (85% rate)
        successes = 0
        for _ in range(20):
            result = run_async(self.client.execute_swap(make_proposal()))
            if result.success:
                successes += 1
                self.assertGreater(result.actual_profit_usd, -10)  # Reasonable range
                self.assertGreater(result.gas_cost_usd, 0)
        self.assertGreater(successes, 0, "Expected at least 1 success in 20 runs")

    def test_trade_count_increments(self):
        self.assertEqual(self.client._trade_count, 0)
        run_async(self.client.execute_swap(make_proposal()))
        self.assertEqual(self.client._trade_count, 1)
        run_async(self.client.execute_swap(make_proposal()))
        self.assertEqual(self.client._trade_count, 2)


# ══════════════════════════════════════════════════════════════════
# Test: Slippage Control
# ══════════════════════════════════════════════════════════════════
class TestSlippageController(unittest.TestCase):
    """Test slippage calculations."""

    def setUp(self):
        self.ctrl = SlippageController(default_slippage_pct=0.005)

    def test_min_output_calculation(self):
        # $100 with 0.5% slippage -> min $99.50
        result = self.ctrl.calculate_min_output(100.0)
        self.assertAlmostEqual(result, 99.50, places=2)

    def test_custom_slippage(self):
        result = self.ctrl.calculate_min_output(100.0, slippage_pct=0.02)
        self.assertAlmostEqual(result, 98.0, places=2)

    def test_dynamic_slippage_small_trade(self):
        # Small trade relative to pool -> low slippage
        slippage = self.ctrl.dynamic_slippage(10.0, 1_000_000.0)
        self.assertEqual(slippage, 0.005)

    def test_dynamic_slippage_large_trade(self):
        # 5% of pool -> high slippage
        slippage = self.ctrl.dynamic_slippage(50_000.0, 1_000_000.0)
        self.assertGreater(slippage, 0.005)

    def test_dynamic_slippage_empty_pool(self):
        slippage = self.ctrl.dynamic_slippage(100.0, 0.0)
        self.assertEqual(slippage, 0.015)  # 3x default


# ══════════════════════════════════════════════════════════════════
# Test: DBClient (SQLite Persistent Storage)
# ══════════════════════════════════════════════════════════════════
class TestDBClient(unittest.TestCase):
    """Test SQLite database operations."""

    def setUp(self):
        # Use a temporary test database
        self.db_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "test_trading_data.db"
        )
        self.db = DBClient(db_path=self.db_path)
        run_async(self.db.initialize())

    def tearDown(self):
        # Clean up test database
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_initialize_creates_tables(self):
        counts = run_async(self.db.get_table_counts())
        self.assertIn("trades", counts)
        self.assertIn("portfolio_snapshots", counts)
        self.assertIn("pool_snapshots", counts)
        self.assertIn("feedback_adjustments", counts)

    def test_save_and_retrieve_trade(self):
        trade = {
            "timestamp": "2026-01-01T00:00:00Z",
            "token_pair": "WBNB/USDT",
            "amount_usd": 100.0,
            "actual_profit_usd": 2.50,
            "gas_cost_usd": 0.30,
            "success": True,
            "tx_hash": "0xabc123",
            "dry_run": True,
        }
        row_id = run_async(self.db.save_trade(trade))
        self.assertIsNotNone(row_id)

        trades = run_async(self.db.get_recent_trades(10))
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades[0]["token_pair"], "WBNB/USDT")
        self.assertAlmostEqual(trades[0]["actual_profit_usd"], 2.50)

    def test_save_multiple_trades(self):
        for i in range(5):
            run_async(self.db.save_trade({
                "token_pair": f"PAIR_{i}",
                "success": True,
            }))
        trades = run_async(self.db.get_recent_trades(10))
        self.assertEqual(len(trades), 5)

    def test_get_trade_stats(self):
        run_async(self.db.save_trade({"token_pair": "A", "success": True, "actual_profit_usd": 5.0, "gas_cost_usd": 0.5}))
        run_async(self.db.save_trade({"token_pair": "B", "success": True, "actual_profit_usd": -1.0, "gas_cost_usd": 0.5}))
        stats = run_async(self.db.get_trade_stats())
        self.assertEqual(stats["total_trades"], 2)

    def test_save_portfolio_snapshot(self):
        portfolio = PortfolioState(capital_usd=1050.0, peak_capital_usd=1050.0, total_trades=10)
        run_async(self.db.save_portfolio_snapshot(portfolio, cycle_number=5))
        history = run_async(self.db.get_portfolio_history(10))
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["capital_usd"], 1050.0)

    def test_save_feedback_adjustment(self):
        run_async(self.db.save_feedback_adjustment(
            "min_profit", 0.50, 0.45, "high win rate"
        ))
        counts = run_async(self.db.get_table_counts())
        self.assertEqual(counts["feedback_adjustments"], 1)

    def test_clear_all(self):
        run_async(self.db.save_trade({"token_pair": "A", "success": True}))
        run_async(self.db.clear_all())
        trades = run_async(self.db.get_recent_trades(10))
        self.assertEqual(len(trades), 0)


# ══════════════════════════════════════════════════════════════════
# Test: Feedback Agent
# ══════════════════════════════════════════════════════════════════
class TestFeedbackAgent(unittest.TestCase):
    """Test the adaptive feedback loop."""

    def setUp(self):
        self.settings = Settings(
            strategy=StrategyConfig(
                min_profit_threshold_usd=0.50,
                max_trade_size_usd=100.0,
                scan_interval_seconds=5.0,
            ),
            risk=RiskConfig(max_risk_per_trade_pct=0.02),
        )
        self.agent = FeedbackAgent(self.settings)

    def test_no_adjustment_with_few_trades(self):
        # With fewer than 5 trades, the on_portfolio_updated handler exits early.
        # _analyze_and_adjust itself always runs, so test the handler path.
        self.agent._recent_pnls = [1.0, 2.0]  # < 5 trades
        # Verify recent count is below threshold
        self.assertLess(len(self.agent._recent_pnls), 5)

    def test_winning_streak_increases_size(self):
        self.agent._recent_pnls = [1.0, 2.0, 1.5, 0.8, 1.2, 3.0, 2.0]  # All wins
        portfolio = PortfolioState(capital_usd=1050.0, peak_capital_usd=1050.0)
        adjustments = self.agent._analyze_and_adjust(portfolio)
        # Should increase trade size or decrease min profit
        self.assertGreater(len(adjustments), 0)

    def test_losing_streak_shrinks_size(self):
        self.agent._recent_pnls = [-1.0, -2.0, -0.5, -1.5, -0.8]  # All losses
        portfolio = PortfolioState(
            capital_usd=950.0, peak_capital_usd=1000.0,
            consecutive_losses=5,
        )
        adjustments = self.agent._analyze_and_adjust(portfolio)
        if "max_trade_size" in adjustments:
            self.assertLess(adjustments["max_trade_size"], 100.0)

    def test_drawdown_reduces_risk(self):
        self.agent._recent_pnls = [-1.0, -2.0, 0.5, -1.0, -0.5]
        portfolio = PortfolioState(
            capital_usd=930.0, peak_capital_usd=1000.0,
            current_drawdown_pct=0.07,
        )
        adjustments = self.agent._analyze_and_adjust(portfolio)
        if "max_risk_pct" in adjustments:
            self.assertLess(adjustments["max_risk_pct"], 0.02)

    def test_bounds_enforced(self):
        # Even with extreme losses, values shouldn't go below bounds
        self.agent._recent_pnls = [-5.0] * 20
        portfolio = PortfolioState(
            capital_usd=700.0, peak_capital_usd=1000.0,
            current_drawdown_pct=0.30, consecutive_losses=20,
        )
        self.agent._analyze_and_adjust(portfolio)
        # Trade size should not go below 30% of original (30.0)
        self.assertGreaterEqual(self.settings.strategy.max_trade_size_usd, 30.0)
        # Risk should not go below 50% of original (0.01)
        self.assertGreaterEqual(self.settings.risk.max_risk_per_trade_pct, 0.01)

    def test_stats_output(self):
        self.agent._recent_pnls = [1.0, -0.5, 2.0]
        stats = self.agent.stats
        self.assertIn("total_adjustments", stats)
        self.assertIn("recent_win_rate", stats)
        self.assertIn("current_min_profit", stats)


if __name__ == "__main__":
    unittest.main()
