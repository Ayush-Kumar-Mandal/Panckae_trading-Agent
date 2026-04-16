"""
PancakeSwap client: wrapper for interacting with the PancakeSwap Router V2.
In DRY_RUN mode, simulates all operations without blockchain interaction.
"""

import random
from utils.logger import get_logger
from utils.models import TradeProposal, TradeResult
from utils.helpers import timestamp_iso
from config.settings import ExecutionConfig

logger = get_logger(__name__)


class PancakeClient:
    """
    Client for PancakeSwap interactions.
    In dry-run mode (default), simulates trades with realistic parameters.
    """

    def __init__(self, execution_config: ExecutionConfig):
        self.config = execution_config
        self.dry_run = execution_config.dry_run
        self._trade_count = 0

    async def execute_swap(self, proposal: TradeProposal) -> TradeResult:
        """
        Execute a swap on PancakeSwap (or simulate in dry-run mode).
        
        Returns a TradeResult with execution details.
        """
        self._trade_count += 1

        if self.dry_run:
            return await self._simulate_swap(proposal)

        # Real execution would go here
        # For now, always fall through to simulation
        logger.warning("Real execution not implemented — falling back to dry run")
        return await self._simulate_swap(proposal)

    async def _simulate_swap(self, proposal: TradeProposal) -> TradeResult:
        """
        Simulate a swap with realistic variance.
        ~80% of simulated trades succeed with slight slippage.
        """
        # Simulate success with realistic outcomes
        success_roll = random.random()
        success = success_roll < 0.85  # 85% success rate in simulation

        if success:
            # Simulate actual profit with some variance (-20% to +10% of expected)
            profit_variance = random.uniform(-0.20, 0.10)
            actual_profit = proposal.expected_profit_usd * (1 + profit_variance)
            actual_amount_out = proposal.expected_amount_out * (1 + profit_variance * 0.5)

            # Simulate gas cost
            gas_used = random.randint(150_000, 280_000)
            gas_cost = proposal.gas_cost_usd * random.uniform(0.8, 1.3)

            # Final profit after actual gas
            actual_profit = actual_profit - (gas_cost - proposal.gas_cost_usd)

            result = TradeResult(
                proposal=proposal,
                success=True,
                tx_hash=f"0x{'%064x' % random.randint(0, 2**256 - 1)}",
                actual_amount_out=round(actual_amount_out, 6),
                actual_profit_usd=round(actual_profit, 4),
                gas_used=gas_used,
                gas_cost_usd=round(gas_cost, 4),
                timestamp=timestamp_iso(),
                dry_run=True,
            )

            logger.info(
                f"🔄 [DRY RUN] Trade #{self._trade_count} EXECUTED: "
                f"{proposal.opportunity.token_pair} | "
                f"profit=${result.actual_profit_usd:.2f} | "
                f"gas=${result.gas_cost_usd:.2f}"
            )
        else:
            result = TradeResult(
                proposal=proposal,
                success=False,
                error="Simulated failure: transaction reverted (slippage too high)",
                timestamp=timestamp_iso(),
                dry_run=True,
            )
            logger.warning(
                f"🔄 [DRY RUN] Trade #{self._trade_count} FAILED: "
                f"{proposal.opportunity.token_pair} | {result.error}"
            )

        return result
