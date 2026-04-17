"""
run_backtest.py — Run the backtesting engine on simulated market data.

Usage:
    python scripts/run_backtest.py                # Default: 100 cycles
    python scripts/run_backtest.py --cycles 500   # 500 cycles
"""
from __future__ import annotations

import asyncio
import argparse
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backtesting.backtester import Backtester
from config.settings import load_settings
from utils.logger import get_logger

logger = get_logger("run_backtest")


def parse_args():
    parser = argparse.ArgumentParser(description="PancakeSwap Backtest Runner")
    parser.add_argument(
        "--cycles", type=int, default=100,
        help="Number of backtest cycles (default: 100)",
    )
    parser.add_argument(
        "--capital", type=float, default=None,
        help="Override initial capital",
    )
    return parser.parse_args()


async def main():
    args = parse_args()

    settings = load_settings()
    settings.execution.dry_run = True

    if args.capital:
        settings.initial_capital_usd = args.capital

    backtester = Backtester(settings=settings)
    metrics = await backtester.run(num_cycles=args.cycles)

    print(f"\nBacktest completed with {metrics['total_trades']} trades.")
    print(f"Final return: {metrics['total_return_pct']:.2%}")


if __name__ == "__main__":
    asyncio.run(main())
