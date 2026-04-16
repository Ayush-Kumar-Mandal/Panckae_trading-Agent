"""
Order Router: determines the best swap path (direct vs multi-hop).
"""

from utils.logger import get_logger
from utils.constants import WBNB

logger = get_logger(__name__)


class OrderRouter:
    """
    Determines the optimal swap route for a trade.
    Supports direct swaps and multi-hop through intermediate tokens (e.g., WBNB).
    """

    # Common intermediate tokens for multi-hop routing
    INTERMEDIATES = [WBNB]

    def find_best_route(
        self, token_in: str, token_out: str, available_pairs: set[tuple[str, str]]
    ) -> list[str]:
        """
        Find the best route from token_in to token_out.
        
        Args:
            token_in: Input token address
            token_out: Output token address
            available_pairs: Set of (tokenA, tokenB) pairs with liquidity
            
        Returns:
            Path as list of token addresses [token_in, ..., token_out]
        """
        # Check direct path
        pair = (min(token_in, token_out), max(token_in, token_out))
        if pair in available_pairs:
            logger.debug(f"Direct route: {token_in[:8]}... -> {token_out[:8]}...")
            return [token_in, token_out]

        # Try multi-hop through intermediates
        for intermediate in self.INTERMEDIATES:
            if intermediate == token_in or intermediate == token_out:
                continue

            pair1 = (min(token_in, intermediate), max(token_in, intermediate))
            pair2 = (min(intermediate, token_out), max(intermediate, token_out))

            if pair1 in available_pairs and pair2 in available_pairs:
                logger.debug(
                    f"Multi-hop route: {token_in[:8]}... -> "
                    f"{intermediate[:8]}... -> {token_out[:8]}..."
                )
                return [token_in, intermediate, token_out]

        # No route found
        logger.warning(f"No route found: {token_in[:8]}... -> {token_out[:8]}...")
        return []

    @staticmethod
    def estimate_hops(path: list[str]) -> int:
        """Return the number of swaps in a path."""
        return max(0, len(path) - 1)
