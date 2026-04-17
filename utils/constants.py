"""
Static constants for the trading system — addresses, ABIs, event types.
"""
from __future__ import annotations

# ── PancakeSwap Contract Addresses (BSC Mainnet) ──────────────────
PANCAKE_ROUTER_V2 = "0x10ED43C718714eb63d5aA57B78B54704E256024E"
PANCAKE_FACTORY_V2 = "0xcA143Ce32Fe78f1f7019d7d551a6402fC5350c73"

# ── Common Token Addresses (BSC Mainnet) ──────────────────────────
WBNB = "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c"
USDT = "0x55d398326f99059fF775485246999027B3197955"
BUSD = "0xe9e7CEA3DedcA5984780Bafc599bD69ADd087D56"
CAKE = "0x0E09FaBB73Bd3Ade0a17ECC321fD13a19e81cE82"

# ── PancakeSwap Contract Addresses (BSC Testnet) ──────────────────
PANCAKE_ROUTER_V2_TESTNET = "0xD99D1c33F9fC3444f8101754aBC46c52416550d1"
WBNB_TESTNET = "0xae13d989daC2f0dEbFf460aC112a837C89BAa7cd"
USDT_TESTNET = "0x337610d27c682E347C9cD60BD4b3b107C9d34dDd"

# ── Minimal Router V2 ABI (only functions we need) ────────────────
ROUTER_V2_ABI = [
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
        ],
        "name": "getAmountsOut",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "uint256", "name": "amountIn", "type": "uint256"},
            {"internalType": "uint256", "name": "amountOutMin", "type": "uint256"},
            {"internalType": "address[]", "name": "path", "type": "address[]"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint256", "name": "deadline", "type": "uint256"},
        ],
        "name": "swapExactTokensForTokens",
        "outputs": [
            {"internalType": "uint256[]", "name": "amounts", "type": "uint256[]"}
        ],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

# ── Minimal ERC-20 ABI ────────────────────────────────────────────
ERC20_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "spender", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
        ],
        "name": "approve",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "account", "type": "address"}
        ],
        "name": "balanceOf",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "decimals",
        "outputs": [{"internalType": "uint8", "name": "", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]

# ── Event Types (used by the event bus) ───────────────────────────
class Events:
    DATA_UPDATED = "data.updated"
    MARKET_OPPORTUNITY = "market.opportunity_detected"
    TRADE_SIGNAL = "strategy.trade_signal"
    TRADE_APPROVED = "risk.trade_approved"
    TRADE_REJECTED = "risk.trade_rejected"
    TRADE_COMPLETED = "execution.trade_completed"
    TRADE_FAILED = "execution.trade_failed"
    PORTFOLIO_UPDATED = "portfolio.updated"
    FEEDBACK_PARAMS_UPDATED = "feedback.params_updated"
    # New events
    REGIME_CHANGE = "market.regime_change"
    WHALE_ALERT = "market.whale_alert"
    ANOMALY_DETECTED = "risk.anomaly_detected"
    POOL_ANALYSIS_UPDATED = "liquidity.pool_analysis_updated"
    CIRCUIT_BREAKER_TRIGGERED = "risk.circuit_breaker_triggered"

# ── Fixed Defaults ────────────────────────────────────────────────
DEFAULT_GAS_COST_USD = 0.30          # Approximate BSC tx cost in USD
DEFAULT_SLIPPAGE_PCT = 0.005         # 0.5%
DEFAULT_SCAN_INTERVAL_SEC = 5        # Seconds between market scans
