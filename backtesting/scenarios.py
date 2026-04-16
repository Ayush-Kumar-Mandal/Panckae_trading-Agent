"""
Scenarios: predefined stress-test conditions for backtesting.
"""

from dataclasses import dataclass
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class Scenario:
    """A stress-test scenario with specific market conditions."""
    name: str
    description: str
    gas_multiplier: float = 1.0      # Multiply gas costs
    liquidity_multiplier: float = 1.0  # Multiply pool liquidity
    volatility_multiplier: float = 1.0 # Multiply price differences
    success_rate: float = 0.85       # Trade success probability


# ── Predefined Scenarios ──────────────────────────────────────────

NORMAL_MARKET = Scenario(
    name="Normal Market",
    description="Standard market conditions with average gas and liquidity.",
    gas_multiplier=1.0,
    liquidity_multiplier=1.0,
    volatility_multiplier=1.0,
    success_rate=0.85,
)

HIGH_GAS = Scenario(
    name="High Gas",
    description="Gas prices spike 5x — tests profitability under high costs.",
    gas_multiplier=5.0,
    liquidity_multiplier=1.0,
    volatility_multiplier=1.0,
    success_rate=0.80,
)

LOW_LIQUIDITY = Scenario(
    name="Low Liquidity",
    description="Liquidity drops 80% — tests slippage handling.",
    gas_multiplier=1.0,
    liquidity_multiplier=0.2,
    volatility_multiplier=1.5,
    success_rate=0.70,
)

FLASH_CRASH = Scenario(
    name="Flash Crash",
    description="Extreme volatility with high gas and low success rate.",
    gas_multiplier=3.0,
    liquidity_multiplier=0.5,
    volatility_multiplier=3.0,
    success_rate=0.50,
)

CONGESTED_NETWORK = Scenario(
    name="Congested Network",
    description="Network congestion — high gas, many failed transactions.",
    gas_multiplier=4.0,
    liquidity_multiplier=0.8,
    volatility_multiplier=0.8,
    success_rate=0.60,
)

ALL_SCENARIOS = [NORMAL_MARKET, HIGH_GAS, LOW_LIQUIDITY, FLASH_CRASH, CONGESTED_NETWORK]


def get_scenario(name: str) -> Scenario:
    """Look up a scenario by name."""
    for s in ALL_SCENARIOS:
        if s.name.lower() == name.lower():
            return s
    logger.warning(f"Scenario '{name}' not found — using Normal Market")
    return NORMAL_MARKET
