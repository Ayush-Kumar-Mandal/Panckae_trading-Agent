"""
Transaction Manager: handles the lifecycle of blockchain transactions.
Build → Sign → Send → Confirm with retry logic.
"""

import time
from utils.logger import get_logger
from config.settings import ExecutionConfig

logger = get_logger(__name__)


class TransactionManager:
    """
    Manages the full transaction lifecycle on BSC.
    In dry-run mode, all operations are simulated.
    """

    def __init__(self, execution_config: ExecutionConfig):
        self.config = execution_config
        self.nonce_tracker: int = 0
        self.pending_txs: list[str] = []

    async def build_transaction(self, tx_params: dict) -> dict:
        """Build a transaction with proper gas and nonce."""
        tx = {
            "gas": self.config.gas_limit,
            "nonce": self.nonce_tracker,
            **tx_params,
        }
        self.nonce_tracker += 1
        logger.debug(f"Built tx with nonce {tx['nonce']}, gas {tx['gas']}")
        return tx

    async def send_transaction(self, signed_tx: dict) -> str:
        """
        Send a signed transaction.
        Returns tx hash. In dry-run, returns a simulated hash.
        """
        if self.config.dry_run:
            import random
            tx_hash = f"0x{'%064x' % random.randint(0, 2**256 - 1)}"
            logger.info(f"[DRY RUN] Simulated tx: {tx_hash[:18]}...")
            return tx_hash

        # Real sending would go here
        raise NotImplementedError("Live transaction sending not yet implemented")

    async def wait_for_receipt(self, tx_hash: str, timeout: float = 60.0) -> dict:
        """Wait for transaction confirmation."""
        if self.config.dry_run:
            return {
                "transactionHash": tx_hash,
                "status": 1,
                "gasUsed": 200_000,
                "blockNumber": 99999999,
            }

        raise NotImplementedError("Live receipt waiting not yet implemented")

    async def execute_with_retry(self, tx_params: dict) -> dict:
        """Build, send, and confirm a transaction with retries."""
        last_error = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                tx = await self.build_transaction(tx_params)
                tx_hash = await self.send_transaction(tx)
                receipt = await self.wait_for_receipt(
                    tx_hash, self.config.transaction_timeout_seconds
                )
                if receipt["status"] == 1:
                    return receipt
                else:
                    last_error = "Transaction reverted"
            except Exception as e:
                last_error = str(e)
                logger.warning(f"Tx attempt {attempt}/{self.config.max_retries} failed: {e}")
                if attempt < self.config.max_retries:
                    import asyncio
                    await asyncio.sleep(self.config.retry_delay_seconds)

        raise RuntimeError(f"Transaction failed after {self.config.max_retries} retries: {last_error}")
