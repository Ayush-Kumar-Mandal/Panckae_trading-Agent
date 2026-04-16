"""
Database client for persistent storage using SQLite.
Stores trade history, portfolio snapshots, and historical data.
"""

import json
import os
from typing import Optional
from utils.logger import get_logger

logger = get_logger(__name__)

DB_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "trading_data.db")


class DBClient:
    """SQLite database client for persistent trade/performance data."""

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._conn = None

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS trades (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        token_pair TEXT NOT NULL,
                        direction TEXT,
                        amount_usd REAL,
                        profit_usd REAL,
                        gas_cost_usd REAL,
                        success INTEGER,
                        tx_hash TEXT,
                        dry_run INTEGER,
                        details TEXT
                    )
                """)
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        capital_usd REAL,
                        total_pnl REAL,
                        total_trades INTEGER,
                        win_rate REAL,
                        drawdown_pct REAL
                    )
                """)
                await db.commit()
                logger.info(f"Database initialized at {self.db_path}")
        except ImportError:
            logger.warning("aiosqlite not installed — database features disabled")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")

    async def save_trade(self, trade: dict) -> None:
        """Save a trade record."""
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """INSERT INTO trades 
                       (timestamp, token_pair, direction, amount_usd, profit_usd, 
                        gas_cost_usd, success, tx_hash, dry_run, details)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        trade.get("timestamp", ""),
                        trade.get("token_pair", ""),
                        trade.get("direction", ""),
                        trade.get("amount_usd", 0),
                        trade.get("profit_usd", 0),
                        trade.get("gas_cost_usd", 0),
                        1 if trade.get("success") else 0,
                        trade.get("tx_hash", ""),
                        1 if trade.get("dry_run") else 0,
                        json.dumps(trade),
                    ),
                )
                await db.commit()
        except ImportError:
            pass
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")

    async def get_recent_trades(self, n: int = 50) -> list[dict]:
        """Retrieve the most recent N trades."""
        try:
            import aiosqlite
            async with aiosqlite.connect(self.db_path) as db:
                db.row_factory = aiosqlite.Row
                cursor = await db.execute(
                    "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (n,)
                )
                rows = await cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception:
            return []
