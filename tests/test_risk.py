"""
Unit Tests for Risk Management Layer:
  - PositionSizer constraints
  - DrawdownController circuit breaker
  - ExposureManager limits
  - RiskAgent full validation pipeline
"""

import sys
import os
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.models import PoolData, ArbitrageOpportunity, TradeProposal, PortfolioState
from config.settings import RiskConfig
from risk.position_sizing import PositionSizer
from risk.drawdown_control import DrawdownController
from risk.exposure_manager import ExposureManager
from agents.risk.risk_agent import RiskAgent


def make_pool(price=300.0, address="0xabc") -> PoolData:
    return PoolData(
        pool_address=address, token0_symbol="WBNB", token1_symbol="USDT",
        token0_address="0xt0", token1_address="0xt1",
        reserve0=5000.0, reserve1=5000.0 * price,
        price_token0_in_token1=price, price_token1_in_token0=1.0 / price,
        liquidity_usd=3_000_000.0,
    )


def make_proposal(profit=2.0, size=100.0, token_out_symbol="WBNB") -> TradeProposal:
    opp = ArbitrageOpportunity(
        pool_a=make_pool(300, "0xa"), pool_b=make_pool(310, "0xb"),
        token_pair="WBNB/USDT", buy_pool="0xa", sell_pool="0xb",
        price_diff_pct=0.033, buy_price=300.0, sell_price=310.0,
        direction="buy_A_sell_B",
    )
    return TradeProposal(
        opportunity=opp, token_in="0xt1", token_out="0xt0",
        token_in_symbol="USDT", token_out_symbol=token_out_symbol,
        amount_in_usd=size, expected_amount_out=size / 300,
        expected_profit_usd=profit, gas_cost_usd=0.30,
        slippage_cost_usd=0.10,
    )


def make_portfolio(capital=1000.0, peak=1000.0) -> PortfolioState:
    return PortfolioState(capital_usd=capital, peak_capital_usd=peak)


# ══════════════════════════════════════════════════════════════════
# Test: Position Sizing
# ══════════════════════════════════════════════════════════════════
class TestPositionSizer(unittest.TestCase):
    """Test position sizing logic."""

    def setUp(self):
        self.config = RiskConfig(max_risk_per_trade_pct=0.02)
        self.sizer = PositionSizer(self.config)

    def test_size_capped_to_risk_percent(self):
        # 2% of $1000 = $20
        result = self.sizer.calculate(1000.0, 100.0)
        self.assertAlmostEqual(result, 20.0, places=2)

    def test_small_trade_not_capped(self):
        # $10 trade when max is $20 -> should remain $10
        result = self.sizer.calculate(1000.0, 10.0)
        self.assertAlmostEqual(result, 10.0, places=2)

    def test_zero_capital(self):
        result = self.sizer.calculate(0.0, 100.0)
        self.assertEqual(result, 0.0)

    def test_negative_capital(self):
        result = self.sizer.calculate(-500.0, 100.0)
        self.assertLessEqual(result, 0.0)


# ══════════════════════════════════════════════════════════════════
# Test: Drawdown Controller
# ══════════════════════════════════════════════════════════════════
class TestDrawdownController(unittest.TestCase):
    """Test drawdown-based circuit breaker."""

    def setUp(self):
        self.ctrl = DrawdownController(max_drawdown_pct=0.10)  # 10%

    def test_normal_operation(self):
        self.assertTrue(self.ctrl.update(1000.0))  # Set initial
        self.assertTrue(self.ctrl.update(1050.0))  # New peak
        self.assertTrue(self.ctrl.update(1000.0))  # 4.7% drawdown — OK

    def test_halt_on_max_drawdown(self):
        self.ctrl.update(1000.0)  # Set initial peak
        result = self.ctrl.update(890.0)  # 11% drawdown — should halt
        self.assertFalse(result)
        self.assertTrue(self.ctrl.is_halted)

    def test_peak_tracking(self):
        self.ctrl.update(1000.0)
        self.ctrl.update(1200.0)  # New peak
        result = self.ctrl.update(1100.0)  # 8.3% from peak of 1200 — OK
        self.assertTrue(result)

    def test_exact_threshold(self):
        self.ctrl.update(1000.0)
        result = self.ctrl.update(900.0)  # Exactly 10%
        # Should halt at or beyond threshold
        self.assertFalse(result)


# ══════════════════════════════════════════════════════════════════
# Test: Exposure Manager
# ══════════════════════════════════════════════════════════════════
class TestExposureManager(unittest.TestCase):
    """Test per-token exposure limits."""

    def setUp(self):
        self.mgr = ExposureManager(max_exposure_pct=0.25)  # 25% max per token

    def test_allows_small_exposure(self):
        result = self.mgr.can_add_exposure("WBNB", 100.0, 1000.0)
        self.assertTrue(result)

    def test_blocks_over_exposure(self):
        # Add 20% exposure
        self.mgr.can_add_exposure("WBNB", 200.0, 1000.0)
        self.mgr.add_exposure("WBNB", 200.0)
        # Adding another 10% (total 30%) should fail
        result = self.mgr.can_add_exposure("WBNB", 100.0, 1000.0)
        self.assertFalse(result)

    def test_different_tokens_independent(self):
        self.mgr.add_exposure("WBNB", 240.0)
        # Different token should still be allowed
        result = self.mgr.can_add_exposure("CAKE", 200.0, 1000.0)
        self.assertTrue(result)


# ══════════════════════════════════════════════════════════════════
# Test: Risk Agent (full validation pipeline)
# ══════════════════════════════════════════════════════════════════
class TestRiskAgent(unittest.TestCase):
    """Test the full 6-check risk validation pipeline."""

    def setUp(self):
        self.config = RiskConfig(
            max_risk_per_trade_pct=0.02,
            max_drawdown_pct=0.10,
            max_exposure_per_token_pct=0.25,
            min_profit_threshold_usd=0.50,
            max_consecutive_losses=3,
            circuit_breaker_cooldown_sec=5.0,
        )
        self.agent = RiskAgent(self.config)

    def test_approve_valid_trade(self):
        proposal = make_proposal(profit=2.0, size=100.0)
        portfolio = make_portfolio(capital=1000.0)
        approved, reason = self.agent.validate(proposal, portfolio)
        self.assertTrue(approved)

    def test_reject_low_profit(self):
        proposal = make_proposal(profit=0.10, size=50.0)  # Below threshold
        portfolio = make_portfolio()
        approved, reason = self.agent.validate(proposal, portfolio)
        self.assertFalse(approved)
        self.assertIn("Profit", reason)

    def test_reject_high_drawdown(self):
        """Should reject if portfolio is in max drawdown."""
        proposal = make_proposal(profit=5.0, size=50.0)
        # Peak was 1000, now 850 = 15% drawdown > 10% max
        portfolio = make_portfolio(capital=850.0, peak=1000.0)
        # Need to set up drawdown controller
        self.agent.drawdown_ctrl.update(1000.0)  # Set peak
        self.agent.drawdown_ctrl.update(850.0)   # Trigger drawdown
        approved, reason = self.agent.validate(proposal, portfolio)
        self.assertFalse(approved)

    def test_consecutive_loss_circuit_breaker(self):
        """After max consecutive losses, circuit breaker activates."""
        self.agent.consecutive_losses = 3  # = max_consecutive_losses
        proposal = make_proposal(profit=5.0)
        portfolio = make_portfolio()
        approved, reason = self.agent.validate(proposal, portfolio)
        self.assertFalse(approved)
        self.assertIn("circuit breaker", reason.lower())

    def test_record_win_resets_losses(self):
        self.agent.consecutive_losses = 2
        self.agent.record_trade_result(True)
        self.assertEqual(self.agent.consecutive_losses, 0)

    def test_record_loss_increments(self):
        self.agent.consecutive_losses = 1
        self.agent.record_trade_result(False)
        self.assertEqual(self.agent.consecutive_losses, 2)

    def test_position_size_shrunk(self):
        """Risk agent should reduce proposal size based on position sizing."""
        proposal = make_proposal(profit=5.0, size=500.0)
        portfolio = make_portfolio(capital=1000.0)
        approved, reason = self.agent.validate(proposal, portfolio)
        self.assertTrue(approved)
        # Size should be capped to 2% of $1000 = $20
        self.assertLessEqual(proposal.amount_in_usd, 20.0)

    def test_stats_tracking(self):
        proposal = make_proposal(profit=2.0)
        portfolio = make_portfolio()
        self.agent.validate(proposal, portfolio)
        stats = self.agent.stats
        self.assertIn("total_approved", stats)
        self.assertIn("consecutive_losses", stats)


if __name__ == "__main__":
    unittest.main()
