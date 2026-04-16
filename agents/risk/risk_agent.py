"""
Risk Management Agent: validates every trade proposal before execution.
This is the CRITICAL safety gate — no trade bypasses this agent.
"""

import time
from utils.logger import get_logger
from utils.models import TradeProposal, PortfolioState
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
    1. Minimum profit threshold
    2. Position size limits  
    3. Token exposure limits
    4. Drawdown circuit breaker
    5. Consecutive loss circuit breaker
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
                f"✅ APPROVED: {proposal.opportunity.token_pair} | "
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
                f"❌ REJECTED: {proposal.opportunity.token_pair} | "
                f"reason: {reason}"
            )
            if self.event_bus:
                await self.event_bus.publish(
                    Events.TRADE_REJECTED,
                    {"proposal": proposal, "reason": reason},
                )

    def validate(
        self, proposal: TradeProposal, portfolio: PortfolioState
    ) -> tuple[bool, str]:
        """
        Run all risk checks on a trade proposal.
        
        Returns:
            (approved: bool, reason: str)
        """
        # Check 1: Circuit breaker cooldown
        if time.time() < self.circuit_breaker_until:
            remaining = int(self.circuit_breaker_until - time.time())
            return False, f"Circuit breaker active ({remaining}s remaining)"

        # Check 2: Consecutive loss circuit breaker
        if self.consecutive_losses >= self.config.max_consecutive_losses:
            self.circuit_breaker_until = time.time() + self.config.circuit_breaker_cooldown_sec
            self.consecutive_losses = 0  # Reset after triggering
            return False, (
                f"Consecutive losses ({self.config.max_consecutive_losses}) triggered "
                f"circuit breaker for {self.config.circuit_breaker_cooldown_sec}s"
            )

        # Check 3: Drawdown check
        can_trade = self.drawdown_ctrl.update(portfolio.capital_usd)
        if not can_trade:
            return False, f"Drawdown exceeds max {self.config.max_drawdown_pct:.1%}"

        # Check 4: Minimum profit threshold
        if proposal.expected_profit_usd < self.config.min_profit_threshold_usd:
            return False, (
                f"Profit ${proposal.expected_profit_usd:.2f} "
                f"< threshold ${self.config.min_profit_threshold_usd:.2f}"
            )

        # Check 5: Position sizing
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

        # Check 6: Exposure limits
        if not self.exposure_mgr.can_add_exposure(
            proposal.token_out_symbol,
            proposal.amount_in_usd,
            portfolio.capital_usd,
        ):
            return False, (
                f"Exposure limit exceeded for {proposal.token_out_symbol}"
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
        }
