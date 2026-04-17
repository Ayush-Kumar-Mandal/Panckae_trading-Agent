"""
RPC Collector: fetches real-time blockchain data via BSC RPC endpoint.
Provides gas price, block number, and on-chain pair reserves.
"""
from __future__ import annotations

import asyncio
from typing import Optional

from utils.logger import get_logger
from config.settings import NetworkConfig

logger = get_logger(__name__)


class RPCCollector:
    """
    Collects on-chain data from BSC via JSON-RPC.
    Currently provides mock data; replace internals with real web3 calls
    when connecting to a live node.
    """

    def __init__(self, network_config: NetworkConfig):
        self.rpc_url = network_config.rpc_url
        self._w3 = None  # Lazy-initialized web3 instance

    def _get_web3(self):
        """Lazy-initialize web3 connection."""
        if self._w3 is None:
            try:
                from web3 import Web3
                self._w3 = Web3(Web3.HTTPProvider(self.rpc_url))
                if self._w3.is_connected():
                    logger.info(f"Connected to RPC: {self.rpc_url}")
                else:
                    logger.warning(f"Failed to connect to RPC: {self.rpc_url}")
                    self._w3 = None
            except ImportError:
                logger.warning("web3 not installed — using mock RPC data")
            except Exception as e:
                logger.warning(f"RPC connection failed: {e}")
        return self._w3

    async def get_gas_price_gwei(self) -> float:
        """Get current gas price in gwei."""
        w3 = self._get_web3()
        if w3 and w3.is_connected():
            try:
                gas_wei = w3.eth.gas_price
                return float(w3.from_wei(gas_wei, "gwei"))
            except Exception as e:
                logger.error(f"Error fetching gas price: {e}")
        # Fallback mock value
        import random
        return round(random.uniform(3.0, 8.0), 1)

    async def get_block_number(self) -> int:
        """Get the latest block number."""
        w3 = self._get_web3()
        if w3 and w3.is_connected():
            try:
                return w3.eth.block_number
            except Exception as e:
                logger.error(f"Error fetching block number: {e}")
        return 0

    async def get_bnb_balance(self, address: str) -> float:
        """Get BNB balance for an address (in BNB, not wei)."""
        w3 = self._get_web3()
        if w3 and w3.is_connected():
            try:
                balance_wei = w3.eth.get_balance(address)
                return float(w3.from_wei(balance_wei, "ether"))
            except Exception as e:
                logger.error(f"Error fetching balance: {e}")
        return 0.0
