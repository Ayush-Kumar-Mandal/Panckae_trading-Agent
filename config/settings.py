"""
Centralized configuration loaded from environment variables and YAML files.
Uses pydantic for validation. Falls back to sensible defaults.
"""

import os
import yaml
from dataclasses import dataclass, field
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")


def _load_yaml(filename: str) -> dict:
    """Load a YAML config file from the config/ directory."""
    path = _PROJECT_ROOT / "config" / filename
    if path.exists():
        with open(path, "r") as f:
            data = yaml.safe_load(f)
            return data if data else {}
    return {}


@dataclass
class NetworkConfig:
    network: str = "testnet"  # "testnet" or "mainnet"
    bsc_testnet_rpc: str = "https://data-seed-prebsc-1-s1.binance.org:8545/"
    bsc_mainnet_rpc: str = "https://bsc-dataseed.binance.org/"
    private_key: str = ""
    wallet_address: str = ""

    @property
    def rpc_url(self) -> str:
        if self.network == "mainnet":
            return self.bsc_mainnet_rpc
        return self.bsc_testnet_rpc


@dataclass
class StrategyConfig:
    min_profit_threshold_usd: float = 0.50
    slippage_tolerance: float = 0.005
    arbitrage_gap_pct: float = 0.01       # 1% minimum price difference
    max_trade_size_usd: float = 100.0
    min_liquidity_usd: float = 1000.0
    scan_interval_seconds: float = 5.0


@dataclass
class RiskConfig:
    max_risk_per_trade_pct: float = 0.02      # 2% of capital
    max_drawdown_pct: float = 0.10            # 10% max drawdown
    max_exposure_per_token_pct: float = 0.25  # 25% max per token
    min_profit_threshold_usd: float = 0.50
    max_consecutive_losses: int = 5
    circuit_breaker_cooldown_sec: float = 300.0  # 5 minutes


@dataclass
class ExecutionConfig:
    gas_limit: int = 300_000
    gas_price_multiplier: float = 1.1
    max_retries: int = 3
    retry_delay_seconds: float = 2.0
    slippage_tolerance: float = 0.005
    transaction_timeout_seconds: float = 60.0
    dry_run: bool = True  # CRITICAL: defaults to True for safety


@dataclass
class Settings:
    """Master settings container — single source of truth for the system."""
    network: NetworkConfig = field(default_factory=NetworkConfig)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    execution: ExecutionConfig = field(default_factory=ExecutionConfig)
    initial_capital_usd: float = 1000.0
    log_level: str = "INFO"


def load_settings() -> Settings:
    """
    Build Settings from environment variables + YAML config files.
    Environment variables override YAML values.
    """
    strategy_yaml = _load_yaml("strategy_config.yaml")
    risk_yaml = _load_yaml("risk_config.yaml")
    execution_yaml = _load_yaml("execution_config.yaml")

    network = NetworkConfig(
        network=os.getenv("NETWORK", "testnet"),
        bsc_testnet_rpc=os.getenv(
            "BNB_TESTNET_RPC",
            "https://data-seed-prebsc-1-s1.binance.org:8545/",
        ),
        bsc_mainnet_rpc=os.getenv(
            "BNB_MAINNET_RPC", "https://bsc-dataseed.binance.org/"
        ),
        private_key=os.getenv("PRIVATE_KEY", ""),
        wallet_address=os.getenv("WALLET_ADDRESS", ""),
    )

    strategy = StrategyConfig(
        min_profit_threshold_usd=float(
            os.getenv(
                "MIN_PROFIT_USD",
                strategy_yaml.get("min_profit_threshold_usd", 0.50),
            )
        ),
        slippage_tolerance=float(
            os.getenv(
                "SLIPPAGE_TOLERANCE",
                strategy_yaml.get("slippage_tolerance", 0.005),
            )
        ),
        arbitrage_gap_pct=float(
            strategy_yaml.get("arbitrage_gap_pct", 0.01)
        ),
        max_trade_size_usd=float(
            strategy_yaml.get("max_trade_size_usd", 100.0)
        ),
        min_liquidity_usd=float(
            strategy_yaml.get("min_liquidity_usd", 1000.0)
        ),
        scan_interval_seconds=float(
            strategy_yaml.get("scan_interval_seconds", 5.0)
        ),
    )

    risk = RiskConfig(
        max_risk_per_trade_pct=float(
            risk_yaml.get("max_risk_per_trade_pct", 0.02)
        ),
        max_drawdown_pct=float(
            os.getenv("MAX_DRAWDOWN_PCT", risk_yaml.get("max_drawdown_pct", 0.10))
        ),
        max_exposure_per_token_pct=float(
            risk_yaml.get("max_exposure_per_token_pct", 0.25)
        ),
        min_profit_threshold_usd=float(
            risk_yaml.get("min_profit_threshold_usd", 0.50)
        ),
        max_consecutive_losses=int(
            risk_yaml.get("max_consecutive_losses", 5)
        ),
        circuit_breaker_cooldown_sec=float(
            risk_yaml.get("circuit_breaker_cooldown_sec", 300.0)
        ),
    )

    execution = ExecutionConfig(
        gas_limit=int(execution_yaml.get("gas_limit", 300_000)),
        gas_price_multiplier=float(
            execution_yaml.get("gas_price_multiplier", 1.1)
        ),
        max_retries=int(execution_yaml.get("max_retries", 3)),
        retry_delay_seconds=float(
            execution_yaml.get("retry_delay_seconds", 2.0)
        ),
        slippage_tolerance=float(
            execution_yaml.get("slippage_tolerance", 0.005)
        ),
        transaction_timeout_seconds=float(
            execution_yaml.get("transaction_timeout_seconds", 60.0)
        ),
        dry_run=os.getenv("DRY_RUN", "true").lower() in ("true", "1", "yes"),
    )

    return Settings(
        network=network,
        strategy=strategy,
        risk=risk,
        execution=execution,
        initial_capital_usd=float(os.getenv("INITIAL_CAPITAL_USD", "1000.0")),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
