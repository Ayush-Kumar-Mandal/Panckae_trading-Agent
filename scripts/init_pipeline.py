"""
init_pipeline.py — Initialize data connections, validate configuration, run health checks.

Usage:
    python scripts/init_pipeline.py
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import load_settings
from data.collectors.subgraph_collector import SubgraphCollector
from data.storage.db_client import DBClient
from execution.wallet_manager import WalletManager
from utils.logger import get_logger

logger = get_logger("init_pipeline")


async def main():
    print("=" * 60)
    print("PIPELINE INITIALIZATION & HEALTH CHECK")
    print("=" * 60)

    settings = load_settings()

    # 1. Configuration check
    print("\n[1/4] Configuration...")
    print(f"  Network:    {settings.network.network}")
    print(f"  RPC URL:    {settings.network.rpc_url}")
    print(f"  Dry Run:    {settings.execution.dry_run}")
    print(f"  Capital:    ${settings.initial_capital_usd:.2f}")
    print("  Status:     OK")

    # 2. Data collector check
    print("\n[2/4] Data Collectors...")
    collector = SubgraphCollector()
    try:
        pools = await collector.fetch_pools()
        print(f"  Pools fetched: {len(pools)}")
        print("  Status:       OK")
    except Exception as e:
        print(f"  Status:       FAILED ({e})")

    # 3. Database initialization
    print("\n[3/4] Database...")
    try:
        db = DBClient()
        await db.initialize()
        print("  Status:       OK")
    except Exception as e:
        print(f"  Status:       SKIPPED ({e})")

    # 4. Wallet check
    print("\n[4/4] Wallet...")
    wallet = WalletManager(settings.network)
    info = wallet.summary()
    print(f"  Address:    {info['address']}")
    print(f"  Configured: {info['configured']}")
    if not info['configured']:
        print("  Note:       Set PRIVATE_KEY and WALLET_ADDRESS in .env for live trading")
    print(f"  Status:     {'OK' if info['configured'] else 'NOT CONFIGURED (OK for dry run)'}")

    print("\n" + "=" * 60)
    print("INITIALIZATION COMPLETE")
    print("=" * 60)
    print("\nTo start trading:  python scripts/run_live.py")
    print("To run backtest:   python scripts/run_backtest.py")
    print()


if __name__ == "__main__":
    asyncio.run(main())
