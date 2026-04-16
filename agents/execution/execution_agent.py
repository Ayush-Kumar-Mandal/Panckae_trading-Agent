"""
Execution Agent: receives approved trades and executes them via PancakeClient.
"""

from utils.logger import get_logger
from utils.models import TradeProposal, TradeResult, PortfolioState
from utils.constants import Events
from execution.pancake_client import PancakeClient
from config.settings import ExecutionConfig

logger = get_logger(__name__)


class ExecutionAgent:
    """
    Executes trades that have been approved by the Risk Agent.
    Publishes trade results (completed or failed) back to the event bus.
    """

    def __init__(self, execution_config: ExecutionConfig, event_bus=None):
        self.config = execution_config
        self.event_bus = event_bus
        self.client = PancakeClient(execution_config)
        self.total_executed: int = 0
        self.total_failed: int = 0

    async def on_trade_approved(self, data: dict) -> None:
        """
        Event handler: receives approved trades from the Risk Agent.
        Executes and publishes results.
        """
        proposal: TradeProposal = data["proposal"]
        portfolio: PortfolioState = data["portfolio"]

        logger.info(
            f"⚡ Executing trade: {proposal.opportunity.token_pair} | "
            f"size=${proposal.amount_in_usd:.2f}"
        )

        # Execute the trade
        result: TradeResult = await self.client.execute_swap(proposal)

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
        }
