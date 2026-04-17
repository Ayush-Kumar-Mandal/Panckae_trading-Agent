"""
Feedback Agent: the adaptive learning loop.

Analyzes recent trading performance and adjusts system parameters:
  - Strategy thresholds (min profit, trade size)
  - Risk parameters (max risk per trade)
  - Trading frequency (scan interval)

This creates a self-improving system that reacts to changing market conditions.
"""
from __future__ import annotations

import time
from utils.logger import get_logger
from utils.models import PortfolioState, TradeResult
from utils.constants import Events
from config.settings import Settings

logger = get_logger(__name__)


class FeedbackAgent:
    """
    Closes the adaptive loop: Portfolio performance -> parameter adjustments.
    
    Subscribes to: portfolio.updated
    Publishes:     feedback.params_updated
    
    Adjustment rules:
    - High win rate + good profit   -> increase trade size, lower profit threshold
    - Low win rate or losses        -> decrease trade size, raise profit threshold
    - High drawdown                 -> reduce risk, widen scan interval
    - Consecutive wins              -> slightly relax risk limits
    """

    def __init__(self, settings: Settings, event_bus=None):
        self.settings = settings
        self.event_bus = event_bus

        # Track the original values to enforce bounds
        self._original_min_profit = settings.strategy.min_profit_threshold_usd
        self._original_max_trade_size = settings.strategy.max_trade_size_usd
        self._original_risk_per_trade = settings.risk.max_risk_per_trade_pct
        self._original_scan_interval = settings.strategy.scan_interval_seconds

        # Adjustment history
        self._adjustment_count = 0
        self._last_adjustment_time = 0.0
        self._cooldown_seconds = 30.0  # Don't adjust more often than every 30s

        # Rolling performance window
        self._recent_pnls: list[float] = []
        self._window_size = 20  # Look at last 20 trades

    async def on_portfolio_updated(self, data: dict) -> None:
        """
        Event handler: analyzes portfolio state and adjusts parameters.
        Called after every trade completes.
        """
        portfolio: PortfolioState = data["portfolio"]
        latest_result: TradeResult = data.get("latest_result")

        # Track recent P&Ls
        if latest_result and latest_result.success:
            self._recent_pnls.append(latest_result.actual_profit_usd)
            if len(self._recent_pnls) > self._window_size:
                self._recent_pnls = self._recent_pnls[-self._window_size:]

        # Cooldown check: don't adjust too frequently
        now = time.time()
        if now - self._last_adjustment_time < self._cooldown_seconds:
            return

        # Need minimum trades before adjusting
        if len(self._recent_pnls) < 5:
            return

        # Analyze and adjust
        adjustments = self._analyze_and_adjust(portfolio)

        if adjustments:
            self._adjustment_count += 1
            self._last_adjustment_time = now

            logger.info(
                f"[FEEDBACK] Adjustment #{self._adjustment_count}: "
                + " | ".join(f"{k}={v}" for k, v in adjustments.items())
            )

            if self.event_bus:
                await self.event_bus.publish(
                    Events.FEEDBACK_PARAMS_UPDATED,
                    {"adjustments": adjustments, "portfolio": portfolio},
                )

    def _analyze_and_adjust(self, portfolio: PortfolioState) -> dict:
        """
        Core feedback logic: analyze recent performance and return adjustments.
        """
        adjustments = {}

        # Calculate recent metrics
        recent_wins = sum(1 for p in self._recent_pnls if p > 0)
        recent_losses = sum(1 for p in self._recent_pnls if p <= 0)
        recent_count = len(self._recent_pnls)
        recent_win_rate = recent_wins / recent_count if recent_count > 0 else 0
        recent_avg_pnl = sum(self._recent_pnls) / recent_count if recent_count > 0 else 0

        strategy = self.settings.strategy
        risk = self.settings.risk

        # ── Rule 1: Adjust min profit threshold ────────────────────
        if recent_win_rate > 0.75 and recent_avg_pnl > 0:
            # Performing well -> lower the bar slightly to catch more opportunities
            new_threshold = max(
                self._original_min_profit * 0.5,  # Never go below 50% of original
                strategy.min_profit_threshold_usd * 0.9,
            )
            if new_threshold != strategy.min_profit_threshold_usd:
                strategy.min_profit_threshold_usd = round(new_threshold, 2)
                adjustments["min_profit_usd"] = strategy.min_profit_threshold_usd

        elif recent_win_rate < 0.45:
            # Struggling -> raise the bar to be more selective
            new_threshold = min(
                self._original_min_profit * 2.0,  # Never go above 2x original
                strategy.min_profit_threshold_usd * 1.15,
            )
            if new_threshold != strategy.min_profit_threshold_usd:
                strategy.min_profit_threshold_usd = round(new_threshold, 2)
                adjustments["min_profit_usd"] = strategy.min_profit_threshold_usd

        # ── Rule 2: Adjust max trade size ──────────────────────────
        if recent_win_rate > 0.70 and portfolio.consecutive_losses == 0:
            # Confident -> allow larger trades (up to 150% of original)
            new_size = min(
                self._original_max_trade_size * 1.5,
                strategy.max_trade_size_usd * 1.1,
            )
            if new_size != strategy.max_trade_size_usd:
                strategy.max_trade_size_usd = round(new_size, 2)
                adjustments["max_trade_size"] = strategy.max_trade_size_usd

        elif recent_win_rate < 0.40 or portfolio.consecutive_losses >= 3:
            # Losing -> shrink trade size
            new_size = max(
                self._original_max_trade_size * 0.3,  # Floor at 30% of original
                strategy.max_trade_size_usd * 0.8,
            )
            if new_size != strategy.max_trade_size_usd:
                strategy.max_trade_size_usd = round(new_size, 2)
                adjustments["max_trade_size"] = strategy.max_trade_size_usd

        # ── Rule 3: Adjust risk per trade ──────────────────────────
        if portfolio.current_drawdown_pct > 0.05:
            # In drawdown -> reduce risk
            new_risk = max(
                self._original_risk_per_trade * 0.5,
                risk.max_risk_per_trade_pct * 0.85,
            )
            if new_risk != risk.max_risk_per_trade_pct:
                risk.max_risk_per_trade_pct = round(new_risk, 4)
                adjustments["max_risk_pct"] = risk.max_risk_per_trade_pct

        elif portfolio.current_drawdown_pct < 0.01 and recent_win_rate > 0.65:
            # Healthy + winning -> restore risk toward original
            new_risk = min(
                self._original_risk_per_trade,
                risk.max_risk_per_trade_pct * 1.05,
            )
            if new_risk != risk.max_risk_per_trade_pct:
                risk.max_risk_per_trade_pct = round(new_risk, 4)
                adjustments["max_risk_pct"] = risk.max_risk_per_trade_pct

        # ── Rule 4: Adjust scan interval ───────────────────────────
        if recent_win_rate > 0.60 and recent_avg_pnl > self._original_min_profit:
            # Market is active and profitable -> scan faster
            new_interval = max(
                self._original_scan_interval * 0.5,  # Min 50% of original
                strategy.scan_interval_seconds * 0.9,
            )
            if new_interval != strategy.scan_interval_seconds:
                strategy.scan_interval_seconds = round(new_interval, 1)
                adjustments["scan_interval_sec"] = strategy.scan_interval_seconds

        elif recent_win_rate < 0.35:
            # Market is tough -> slow down to save gas
            new_interval = min(
                self._original_scan_interval * 3.0,  # Cap at 3x original
                strategy.scan_interval_seconds * 1.2,
            )
            if new_interval != strategy.scan_interval_seconds:
                strategy.scan_interval_seconds = round(new_interval, 1)
                adjustments["scan_interval_sec"] = strategy.scan_interval_seconds

        return adjustments

    @property
    def stats(self) -> dict:
        recent_count = len(self._recent_pnls)
        recent_wins = sum(1 for p in self._recent_pnls if p > 0)
        return {
            "total_adjustments": self._adjustment_count,
            "recent_window_size": recent_count,
            "recent_win_rate": round(recent_wins / recent_count, 2) if recent_count > 0 else 0,
            "current_min_profit": self.settings.strategy.min_profit_threshold_usd,
            "current_max_trade_size": self.settings.strategy.max_trade_size_usd,
            "current_risk_per_trade": self.settings.risk.max_risk_per_trade_pct,
            "current_scan_interval": self.settings.strategy.scan_interval_seconds,
        }
