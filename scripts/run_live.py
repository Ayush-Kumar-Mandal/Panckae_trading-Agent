"""
run_live.py — Main entry point for the PancakeSwap multi-agent trading system.

Usage:
    python scripts/run_live.py                  # Default: 10 cycles, dry run
    python scripts/run_live.py --cycles 50     # Run 50 cycles
    python scripts/run_live.py --cycles 0      # Infinite loop (Ctrl+C to stop)
"""
from __future__ import annotations

import asyncio
import argparse
import sys
import os

# Add project root to path so imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestration.orchestrator import TradingOrchestrator
from config.settings import load_settings
from utils.logger import get_logger

logger = get_logger("run_live")


def parse_args():
    parser = argparse.ArgumentParser(
        description="PancakeSwap Multi-Agent Trading System"
    )
    parser.add_argument(
        "--cycles",
        type=int,
        default=10,
        help="Number of trading cycles to run (0 = infinite, default: 10)",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=None,
        help="Override scan interval in seconds",
    )
    parser.add_argument(
        "--capital",
        type=float,
        default=None,
        help="Override initial capital in USD",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    # Load settings
    settings = load_settings()

    # Apply CLI overrides
    if args.interval is not None:
        settings.strategy.scan_interval_seconds = args.interval
    if args.capital is not None:
        settings.initial_capital_usd = args.capital

    # Create and run the orchestrator
    orchestrator = TradingOrchestrator(settings=settings)

    # Handle Ctrl+C gracefully
    loop = asyncio.get_event_loop()

    def handle_shutdown():
        logger.info("Received shutdown signal...")
        orchestrator.stop()

    # Windows-compatible signal handling
    try:
        loop.add_signal_handler(signal_module.SIGINT, handle_shutdown)
        loop.add_signal_handler(signal_module.SIGTERM, handle_shutdown)
    except (NotImplementedError, AttributeError):
        # Signal handlers not supported on Windows in some cases
        pass

    try:
        await orchestrator.run(max_cycles=args.cycles)
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt — shutting down...")
        orchestrator.stop()


if __name__ == "__main__":
    import signal as signal_module
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Trading system stopped by user.")
