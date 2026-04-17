"""
Risk Management Agent: validates every trade proposal before execution.
This is the CRITICAL safety gate — no trade bypasses this agent.

Includes: anomaly-triggered defensive actions, per-trade stop-loss enforcement.
"""

import time
from utils.logger import get_logger
from utils.models import TradeProposal, PortfolioState, AnomalyAlert
from utils.constants import Events
from risk.position_sizing import PositionSizer
from risk.drawdown_control import DrawdownController
from risk.exposure_manager import ExposureManager
from config.settings import RiskConfig

logger = get_logger(__name__)


class RiskAgent:
    """
    Validates trades against risk rules. Can approve or reject.

    Checks:
    1. Anomaly-based halt (flash crash, depeg, oracle failure)
    2. Circuit breaker cooldown
    3. Consecutive loss circuit breaker
    4. Drawdown circuit breaker
    5. Minimum profit threshold
    6. Position size limits
    7. Token exposure limits
    8. Per-trade stop-loss validation
    """

    def __init__(self, risk_config: RiskConfig, event_bus=None):
        self.config = risk_config
        self.event_bus = event_bus
        self.position_sizer = PositionSizer(risk_config)
        self.drawdown_ctrl = DrawdownController(risk_config.max_drawdown_pct)
        self.exposure_mgr = ExposureManager(risk_config.max_exposure_per_token_pct)

        self.consecutive_losses: int = 0
        self.circuit_breaker_until: float = 0.0  # Unix timestamp
        self.total_approved: int = 0
        self.total_rejected: int = 0

        # Anomaly tracking
        self._anomaly_halt = False
        self._anomaly_halt_until: float = 0.0
        self._active_anomalies: list[AnomalyAlert] = []
        self._anomaly_triggered_count = 0

    async def on_trade_signal(self, data: dict) -> None:
        """
        Event handler: receives trade signals from the strategy agent.
        Validates and publishes approved/rejected events.
        """
        proposal: TradeProposal = data["proposal"]
        portfolio: PortfolioState = data["portfolio"]

        approved, reason = self.validate(proposal, portfolio)

        if approved:
            self.total_approved += 1
            logger.info(
                f"APPROVED: {proposal.opportunity.token_pair} | "
                f"{proposal.strategy_type} | "
                f"size=${proposal.amount_in_usd:.2f} | "
                f"expected profit=${proposal.expected_profit_usd:.2f}"
            )
            if self.event_bus:
                await self.event_bus.publish(
                    Events.TRADE_APPROVED,
                    {"proposal": proposal, "portfolio": portfolio},
                )
        else:
            self.total_rejected += 1
            logger.warning(
                f"REJECTED: {proposal.opportunity.token_pair} | "
                f"{proposal.strategy_type} | reason: {reason}"
            )
            if self.event_bus:
                await self.event_bus.publish(
                    Events.TRADE_REJECTED,
                    {"proposal": proposal, "reason": reason},
                )

    async def on_anomaly_detected(self, data: dict) -> None:
        """
        Event handler: receives anomaly alerts from the Market Agent.
        Takes defensive action based on severity.
        """
        anomaly: AnomalyAlert = data["anomaly"]
        self._active_anomalies.append(anomaly)
        self._anomaly_triggered_count += 1

        if anomaly.severity in ("critical", "high"):
            # Halt trading for 60 seconds on critical anomalies
            halt_duration = 120 if anomaly.severity == "critical" else 60
            self._anomaly_halt = True
            self._anomaly_halt_until = time.time() + halt_duration
            logger.warning(
                f"ANOMALY HALT: {anomaly.anomaly_type} ({anomaly.severity}) "
                f"on {anomaly.token_pair} — trading paused for {halt_duration}s | "
                f"{anomaly.description}"
            )
            if self.event_bus:
                await self.event_bus.publish(
                    Events.CIRCUIT_BREAKER_TRIGGERED,
                    {"reason": f"anomaly:{anomaly.anomaly_type}", "duration": halt_duration},
                )

    def validate(
        self, proposal: TradeProposal, portfolio: PortfolioState
    ) -> tuple[bool, str]:
        """
        Run all risk checks on a trade proposal.

        Returns:
            (approved: bool, reason: str)
        """
        # Check 1: Anomaly-based halt
        if self._anomaly_halt:
            if time.time() < self._anomaly_halt_until:
                remaining = int(self._anomaly_halt_until - time.time())
                return False, f"Anomaly halt active ({remaining}s remaining)"
            else:
                self._anomaly_halt = False
                self._active_anomalies.clear()
                logger.info("Anomaly halt lifted — resuming trading")

        # Check 2: Circuit breaker cooldown
        if time.time() < self.circuit_breaker_until:
            remaining = int(self.circuit_breaker_until - time.time())
            return False, f"Circuit breaker active ({remaining}s remaining)"

        # Check 3: Consecutive loss circuit breaker
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self.circuit_breaker_until = time.time() + self.config.circuit_breaker_cooldown_sec
            self.consecutive_losses = 0  # Reset after triggering
            return False, (
                f"Consecutive losses ({self.config.max_consecutive_losses}) triggered "
                f"circuit breaker for {self.config.circuit_breaker_cooldown_sec}s"
            )

        # Check 4: Drawdown check
        can_trade = self.drawdown_ctrl.update(portfolio.capital_usd)
        if not can_trade:
            return False, f"Drawdown exceeds max {self.config.max_drawdown_pct:.1%}"

        # Check 5: Minimum profit threshold
        if proposal.expected_profit_usd < self.config.min_profit_threshold_usd:
            return False, (
                f"Profit ${proposal.expected_profit_usd:.2f} "
                f"< threshold ${self.config.min_profit_threshold_usd:.2f}"
            )

        # Check 6: Position sizing
        max_size = self.position_sizer.calculate(
            portfolio.capital_usd, proposal.amount_in_usd
        )
        if max_size < 1.0:
            return False, f"Position size too small after risk adjustment (${max_size:.2f})"

        # Update proposal size if it was reduced
        if max_size < proposal.amount_in_usd:
            proposal.amount_in_usd = max_size
            # Recalculate expected profit proportionally
            ratio = max_size / proposal.amount_in_usd if proposal.amount_in_usd > 0 else 0
            proposal.expected_profit_usd *= ratio

        # Check 7: Exposure limits
        if not self.exposure_mgr.can_add_exposure(
            proposal.token_out_symbol,
            proposal.amount_in_usd,
            portfolio.capital_usd,
        ):
            return False, (
                f"Exposure limit exceeded for {proposal.token_out_symbol}"
            )

        # Check 8: Per-trade stop-loss validation
        max_loss = proposal.amount_in_usd * proposal.stop_loss_pct
        if max_loss > portfolio.capital_usd * 0.05:
            return False, (
                f"Stop-loss risk ${max_loss:.2f} exceeds 5% of capital"
            )

        # All checks passed
        return True, "All risk checks passed"

    def record_trade_result(self, is_win: bool) -> None:
        """Update consecutive loss counter after a trade completes."""
        if is_win:
            self.consecutive_losses = 0
        else:
            self.consecutive_losses += 1
            logger.info(
                f"Consecutive losses: {self.consecutive_losses}/"
                f"{self.config.max_consecutive_losses}"
            )

    @property
    def stats(self) -> dict:
        return {
            "total_approved": self.total_approved,
            "total_rejected": self.total_rejected,
            "consecutive_losses": self.consecutive_losses,
            "circuit_breaker_active": time.time() < self.circuit_breaker_until,
            "drawdown_halted": self.drawdown_ctrl.is_halted,
            "anomaly_halt_active": self._anomaly_halt and time.time() < self._anomaly_halt_until,
            "anomalies_triggered": self._anomaly_triggered_count,
        }
