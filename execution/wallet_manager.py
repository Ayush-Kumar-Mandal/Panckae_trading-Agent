"""
Wallet Manager: handles wallet loading, balance checking, and signing.
"""
from __future__ import annotations

from utils.logger import get_logger
from utils.helpers import format_address
from config.settings import NetworkConfig

logger = get_logger(__name__)


class WalletManager:
    """
    Manages wallet operations: loading from private key, balance queries.
    """

    def __init__(self, network_config: NetworkConfig):
        self.config = network_config
        self.address = network_config.wallet_address
        self._account = None

    def is_configured(self) -> bool:
        """Check if wallet credentials are properly configured."""
        return bool(
            self.config.private_key
            and self.config.private_key != "your_testnet_private_key_here"
            and self.config.wallet_address
            and self.config.wallet_address != "your_wallet_address_here"
        )

    async def get_bnb_balance(self) -> float:
        """Get BNB balance for the configured wallet."""
        if not self.is_configured():
            logger.warning("Wallet not configured — returning 0 balance")
            return 0.0

        try:
            from web3 import Web3
            w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            balance_wei = w3.eth.get_balance(self.address)
            return float(w3.from_wei(balance_wei, "ether"))
        except Exception as e:
            logger.error(f"Failed to get BNB balance: {e}")
            return 0.0

    async def get_token_balance(self, token_address: str, decimals: int = 18) -> float:
        """Get ERC-20 token balance for the configured wallet."""
        if not self.is_configured():
            return 0.0

        try:
            from web3 import Web3
            from utils.constants import ERC20_ABI

            w3 = Web3(Web3.HTTPProvider(self.config.rpc_url))
            contract = w3.eth.contract(
                address=Web3.to_checksum_address(token_address),
                abi=ERC20_ABI,
            )
            balance = contract.functions.balanceOf(self.address).call()
            return balance / (10 ** decimals)
        except Exception as e:
            logger.error(f"Failed to get token balance: {e}")
            return 0.0

    def summary(self) -> dict:
        return {
            "address": format_address(self.address) if self.address else "not configured",
            "configured": self.is_configured(),
            "network": self.config.network,
        }
