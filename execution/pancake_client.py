"""
PancakeSwap client: wrapper for interacting with PancakeSwap Router V2.

Supports two modes:
  - DRY_RUN (default): simulates trades with realistic parameters
  - LIVE: executes real on-chain swaps via Web3 + Router V2 contract

⚠️  LIVE mode requires: PRIVATE_KEY, WALLET_ADDRESS, and DRY_RUN=false in .env
"""

import time
import random
import asyncio
from typing import Optional

from utils.logger import get_logger
from utils.models import TradeProposal, TradeResult
from utils.helpers import timestamp_iso, to_wei, from_wei
from utils.constants import (
    PANCAKE_ROUTER_V2,
    PANCAKE_ROUTER_V2_TESTNET,
    ROUTER_V2_ABI,
    ERC20_ABI,
    WBNB,
    WBNB_TESTNET,
)
from config.settings import ExecutionConfig, NetworkConfig

logger = get_logger(__name__)


class PancakeClient:
    """
    Client for PancakeSwap interactions.
    
    DRY_RUN mode (default):  Simulates trades with realistic variance.
    LIVE mode:               Executes real swaps on PancakeSwap Router V2.
    """

    def __init__(
        self,
        execution_config: ExecutionConfig,
        network_config: NetworkConfig = None,
    ):
        self.config = execution_config
        self.network_config = network_config
        self.dry_run = execution_config.dry_run
        self._trade_count = 0
        self._w3 = None
        self._router = None
        self._account = None

        if not self.dry_run and network_config:
            self._init_web3(network_config)

    def _init_web3(self, network_config: NetworkConfig) -> None:
        """Initialize Web3 connection and router contract for live trading."""
        try:
            from web3 import Web3

            self._w3 = Web3(Web3.HTTPProvider(network_config.rpc_url))
            if not self._w3.is_connected():
                logger.error(f"Cannot connect to RPC: {network_config.rpc_url}")
                logger.warning("Falling back to DRY RUN mode")
                self.dry_run = True
                return

            # Select correct router address for network
            if network_config.network == "mainnet":
                router_addr = PANCAKE_ROUTER_V2
            else:
                router_addr = PANCAKE_ROUTER_V2_TESTNET

            self._router = self._w3.eth.contract(
                address=Web3.to_checksum_address(router_addr),
                abi=ROUTER_V2_ABI,
            )

            # Load account from private key
            if network_config.private_key and network_config.private_key != "your_testnet_private_key_here":
                self._account = self._w3.eth.account.from_key(network_config.private_key)
                logger.info(
                    f"[LIVE] Web3 connected to {network_config.network} | "
                    f"Router: {router_addr[:10]}... | "
                    f"Wallet: {self._account.address[:10]}..."
                )
            else:
                logger.error("No valid private key — cannot execute live trades")
                self.dry_run = True

        except ImportError:
            logger.error("web3 package not installed — cannot do live trading")
            self.dry_run = True
        except Exception as e:
            logger.error(f"Web3 initialization failed: {e} — falling back to DRY RUN")
            self.dry_run = True

    async def execute_swap(self, proposal: TradeProposal) -> TradeResult:
        """
        Execute a swap on PancakeSwap.
        Routes to simulation or real execution based on dry_run flag.
        """
        self._trade_count += 1

        if self.dry_run:
            return await self._simulate_swap(proposal)

        return await self._live_swap(proposal)

    # ── LIVE EXECUTION ────────────────────────────────────────────
    async def _live_swap(self, proposal: TradeProposal) -> TradeResult:
        """
        Execute a REAL swap on PancakeSwap Router V2.
        
        Flow:
        1. Check/approve token allowance
        2. Build swap transaction
        3. Sign and send
        4. Wait for receipt
        5. Parse result
        """
        from web3 import Web3

        try:
            token_in = Web3.to_checksum_address(proposal.token_in)
            token_out = Web3.to_checksum_address(proposal.token_out)
            wallet = self._account.address

            # Calculate amounts
            amount_in = to_wei(proposal.amount_in_usd / proposal.opportunity.buy_price)
            min_amount_out = int(
                proposal.expected_amount_out * (1 - self.config.slippage_tolerance) * 1e18
            )

            # Step 1: Approve token spending (if needed)
            await self._ensure_approval(token_in, amount_in)

            # Step 2: Build swap path
            path = [token_in, token_out]

            # Step 3: Build transaction
            deadline = int(time.time()) + int(self.config.transaction_timeout_seconds)

            swap_tx = self._router.functions.swapExactTokensForTokens(
                amount_in,
                min_amount_out,
                path,
                wallet,
                deadline,
            ).build_transaction({
                "from": wallet,
                "gas": self.config.gas_limit,
                "gasPrice": self._w3.eth.gas_price,
                "nonce": self._w3.eth.get_transaction_count(wallet),
            })

            # Multiply gas price for priority
            swap_tx["gasPrice"] = int(
                swap_tx["gasPrice"] * self.config.gas_price_multiplier
            )

            # Step 4: Sign and send
            signed = self._w3.eth.account.sign_transaction(swap_tx, self._account.key)
            tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)
            tx_hash_hex = tx_hash.hex()

            logger.info(
                f"[LIVE] Tx sent: {tx_hash_hex[:18]}... | "
                f"Waiting for confirmation..."
            )

            # Step 5: Wait for receipt (with retry)
            receipt = await self._wait_for_receipt(tx_hash_hex)

            if receipt and receipt["status"] == 1:
                gas_used = receipt["gasUsed"]
                gas_price_wei = swap_tx["gasPrice"]
                gas_cost_bnb = from_wei(gas_used * gas_price_wei)
                gas_cost_usd = gas_cost_bnb * 300  # Approximate BNB price

                # Estimate actual profit (would need to parse logs for exact)
                actual_profit = proposal.expected_profit_usd - (gas_cost_usd - proposal.gas_cost_usd)

                result = TradeResult(
                    proposal=proposal,
                    success=True,
                    tx_hash=tx_hash_hex,
                    actual_amount_out=proposal.expected_amount_out,
                    actual_profit_usd=round(actual_profit, 4),
                    gas_used=gas_used,
                    gas_cost_usd=round(gas_cost_usd, 4),
                    timestamp=timestamp_iso(),
                    dry_run=False,
                )
                logger.info(
                    f"[LIVE] Trade #{self._trade_count} CONFIRMED: "
                    f"{proposal.opportunity.token_pair} | "
                    f"tx={tx_hash_hex[:18]}... | "
                    f"gas={gas_used} ({gas_cost_usd:.2f} USD)"
                )
            else:
                result = TradeResult(
                    proposal=proposal,
                    success=False,
                    tx_hash=tx_hash_hex,
                    error="Transaction reverted on-chain",
                    timestamp=timestamp_iso(),
                    dry_run=False,
                )
                logger.error(
                    f"[LIVE] Trade #{self._trade_count} REVERTED: "
                    f"{tx_hash_hex[:18]}..."
                )

            return result

        except Exception as e:
            logger.error(f"[LIVE] Trade #{self._trade_count} FAILED: {e}")
            return TradeResult(
                proposal=proposal,
                success=False,
                error=str(e),
                timestamp=timestamp_iso(),
                dry_run=False,
            )

    async def _ensure_approval(self, token_address: str, amount: int) -> None:
        """Approve the Router to spend tokens if allowance is insufficient."""
        from web3 import Web3

        token_contract = self._w3.eth.contract(
            address=Web3.to_checksum_address(token_address),
            abi=ERC20_ABI,
        )

        router_addr = self._router.address
        wallet = self._account.address

        current_allowance = token_contract.functions.balanceOf(wallet).call()

        if current_allowance >= amount:
            return  # Already approved

        logger.info(f"Approving Router to spend token {token_address[:10]}...")

        max_approval = 2**256 - 1  # Max uint256
        approve_tx = token_contract.functions.approve(
            router_addr, max_approval
        ).build_transaction({
            "from": wallet,
            "gas": 100_000,
            "gasPrice": self._w3.eth.gas_price,
            "nonce": self._w3.eth.get_transaction_count(wallet),
        })

        signed = self._w3.eth.account.sign_transaction(approve_tx, self._account.key)
        tx_hash = self._w3.eth.send_raw_transaction(signed.raw_transaction)

        # Wait for approval confirmation
        self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=30)
        logger.info(f"Approval confirmed: {tx_hash.hex()[:18]}...")

    async def _wait_for_receipt(
        self, tx_hash: str, max_wait: float = None
    ) -> Optional[dict]:
        """Wait for a transaction receipt with timeout."""
        timeout = max_wait or self.config.transaction_timeout_seconds
        start = time.time()

        while time.time() - start < timeout:
            try:
                receipt = self._w3.eth.get_transaction_receipt(tx_hash)
                if receipt:
                    return dict(receipt)
            except Exception:
                pass
            await asyncio.sleep(2)

        logger.error(f"Tx receipt timeout after {timeout}s: {tx_hash[:18]}...")
        return None

    async def get_amounts_out(
        self, amount_in: int, path: list[str]
    ) -> Optional[list[int]]:
        """Call getAmountsOut on the router to estimate swap output."""
        if not self._router:
            return None
        try:
            from web3 import Web3
            checksum_path = [Web3.to_checksum_address(p) for p in path]
            amounts = self._router.functions.getAmountsOut(
                amount_in, checksum_path
            ).call()
            return amounts
        except Exception as e:
            logger.error(f"getAmountsOut failed: {e}")
            return None

    # ── DRY RUN SIMULATION ────────────────────────────────────────
    async def _simulate_swap(self, proposal: TradeProposal) -> TradeResult:
        """Simulate a swap with realistic variance."""
        success_roll = random.random()
        success = success_roll < 0.85

        if success:
            profit_variance = random.uniform(-0.20, 0.10)
            actual_profit = proposal.expected_profit_usd * (1 + profit_variance)
            actual_amount_out = proposal.expected_amount_out * (1 + profit_variance * 0.5)

            gas_used = random.randint(150_000, 280_000)
            gas_cost = proposal.gas_cost_usd * random.uniform(0.8, 1.3)
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
                f"[DRY RUN] Trade #{self._trade_count} EXECUTED: "
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
                f"[DRY RUN] Trade #{self._trade_count} FAILED: "
                f"{proposal.opportunity.token_pair} | {result.error}"
            )

        return result
