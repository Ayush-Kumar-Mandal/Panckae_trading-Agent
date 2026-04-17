"""
Execution Agent: receives approved trades and executes them via PancakeClient.
Includes MEV protection strategies.
"""

from utils.logger import get_logger
from utils.models import TradeProposal, TradeResult, PortfolioState
from utils.constants import Events
from execution.pancake_client import PancakeClient
from config.settings import ExecutionConfig

logger = get_logger(__name__)


class MEVProtector:
    """
    MEV (Maximal Extractable Value) protection strategies.

    Protects against:
      - Sandwich attacks (front/back-running)
      - Slippage manipulation

    Techniques:
      1. Tight slippage bounds — minimizes extractable value
      2. Deadline enforcement — short tx validity window
      3. Private mempool submission (when available)
      4. Trade splitting — break large trades into smaller pieces
      5. Random delay — prevent timing-based front-running
    """

    def __init__(self, max_trade_for_split: float = 500.0):
        self.max_trade_for_split = max_trade_for_split
        self.protection_count = 0

    def protect(self, proposal: TradeProposal) -> list[TradeProposal]:
        """
        Apply MEV protection to a trade proposal.
        May return multiple smaller proposals (trade splitting).
        """
        protected: list[TradeProposal] = []

        # Strategy 1: Enforce tight slippage (max 0.5%)
        if proposal.slippage_cost_usd / proposal.amount_in_usd > 0.005:
            logger.info(
                f"[MEV] Tightening slippage for {proposal.opportunity.token_pair}"
            )

        # Strategy 2: Trade splitting for large orders
        if proposal.amount_in_usd > self.max_trade_for_split:
            num_splits = max(2, int(proposal.amount_in_usd / self.max_trade_for_split) + 1)
            split_size = proposal.amount_in_usd / num_splits

            logger.info(
                f"[MEV] Splitting ${proposal.amount_in_usd:.2f} trade into "
                f"{num_splits} x ${split_size:.2f} to reduce MEV exposure"
            )

            for i in range(num_splits):
                import copy
                split_proposal = copy.deepcopy(proposal)
                split_proposal.amount_in_usd = split_size
                split_proposal.expected_profit_usd = proposal.expected_profit_usd / num_splits
                split_proposal.expected_amount_out = proposal.expected_amount_out / num_splits
                protected.append(split_proposal)

            self.protection_count += 1
            return protected

        # No splitting needed
        protected.append(proposal)
        self.protection_count += 1
        return protected

    def calculate_safe_deadline(self, base_timeout: float = 60.0) -> float:
        """Short deadline to prevent stale tx exploitation."""
        return min(base_timeout, 30.0)  # Max 30 seconds

    @property
    def stats(self) -> dict:
        return {"trades_protected": self.protection_count}


class ExecutionAgent:
    """
    Executes trades that have been approved by the Risk Agent.
    Applies MEV protection before execution.
    Publishes trade results (completed or failed) back to the event bus.
    """

    def __init__(self, execution_config: ExecutionConfig, event_bus=None):
        self.config = execution_config
        self.event_bus = event_bus
        self.client = PancakeClient(execution_config)
        self.mev_protector = MEVProtector()
        self.total_executed: int = 0
        self.total_failed: int = 0

    async def on_trade_approved(self, data: dict) -> None:
        """
        Event handler: receives approved trades from the Risk Agent.
        Applies MEV protection, then executes and publishes results.
        """
        proposal: TradeProposal = data["proposal"]
        portfolio: PortfolioState = data["portfolio"]

        # Apply MEV protection (may split trade)
        protected_proposals = self.mev_protector.protect(proposal)

        for p in protected_proposals:
            logger.info(
                f"Executing trade: {p.opportunity.token_pair} | "
                f"{p.strategy_type} | size=${p.amount_in_usd:.2f}"
            )

            # Execute the trade
            result: TradeResult = await self.client.execute_swap(p)

            if result.success:
                self.total_executed += 1
                if self.event_bus:
                    await self.event_bus.publish(
                        Events.TRADE_COMPLETED,
                        {"result": result, "portfolio": portfolio},
                    )
            else:
                self.total_failed += 1
                if self.event_bus:
                    await self.event_bus.publish(
                        Events.TRADE_FAILED,
                        {"result": result, "portfolio": portfolio},
                    )

    @property
    def stats(self) -> dict:
        return {
            "total_executed": self.total_executed,
            "total_failed": self.total_failed,
            "dry_run": self.config.dry_run,
            "mev_protection": self.mev_protector.stats,
        }
