"""
Database client for persistent storage using SQLite.
Stores trade history, portfolio snapshots, and historical pool data.

Uses Python's built-in sqlite3 (no aiosqlite dependency needed).
Async wrappers run sync operations in a thread executor for non-blocking I/O.
"""
from __future__ import annotations

import json
import os
import sqlite3
import asyncio
from datetime import datetime, timezone
from typing import Optional
from utils.logger import get_logger
from utils.helpers import timestamp_iso

logger = get_logger(__name__)

DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "trading_data.db",
)


class DBClient:
    """
    SQLite database client for persistent trade/performance data.
    Uses Python's built-in sqlite3 — no external dependencies required.
    """

    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._initialized = False

    def _get_conn(self) -> sqlite3.Connection:
        """Create a new connection (sqlite3 is not thread-safe for sharing)."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")  # Better concurrent performance
        return conn

    async def initialize(self) -> None:
        """Create tables if they don't exist."""
        await asyncio.get_event_loop().run_in_executor(None, self._initialize_sync)

    def _initialize_sync(self) -> None:
        """Synchronous table creation."""
        conn = self._get_conn()
        try:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    token_pair TEXT NOT NULL,
                    direction TEXT DEFAULT '',
                    amount_usd REAL DEFAULT 0,
                    expected_profit_usd REAL DEFAULT 0,
                    actual_profit_usd REAL DEFAULT 0,
                    gas_cost_usd REAL DEFAULT 0,
                    success INTEGER DEFAULT 0,
                    tx_hash TEXT DEFAULT '',
                    dry_run INTEGER DEFAULT 1,
                    error TEXT DEFAULT '',
                    details TEXT DEFAULT '{}'
                );

                CREATE TABLE IF NOT EXISTS portfolio_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cycle_number INTEGER DEFAULT 0,
                    capital_usd REAL DEFAULT 0,
                    total_pnl_usd REAL DEFAULT 0,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    drawdown_pct REAL DEFAULT 0,
                    sharpe_ratio REAL DEFAULT 0,
                    peak_capital_usd REAL DEFAULT 0
                );

                CREATE TABLE IF NOT EXISTS pool_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    pool_address TEXT NOT NULL,
                    token_pair TEXT NOT NULL,
                    reserve0 REAL DEFAULT 0,
                    reserve1 REAL DEFAULT 0,
                    price REAL DEFAULT 0,
                    liquidity_usd REAL DEFAULT 0,
                    volume_24h_usd REAL DEFAULT 0,
                    source TEXT DEFAULT 'mock'
                );

                CREATE TABLE IF NOT EXISTS feedback_adjustments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    adjustment_type TEXT NOT NULL,
                    old_value REAL,
                    new_value REAL,
                    reason TEXT DEFAULT ''
                );

                CREATE INDEX IF NOT EXISTS idx_trades_timestamp ON trades(timestamp);
                CREATE INDEX IF NOT EXISTS idx_trades_pair ON trades(token_pair);
                CREATE INDEX IF NOT EXISTS idx_snapshots_timestamp ON portfolio_snapshots(timestamp);
                CREATE INDEX IF NOT EXISTS idx_pools_address ON pool_snapshots(pool_address);
            """)
            conn.commit()
            self._initialized = True
            logger.info(f"Database initialized at {self.db_path}")
        except Exception as e:
            logger.error(f"Database initialization failed: {e}")
        finally:
            conn.close()

    # ── Trade Operations ──────────────────────────────────────────
    async def save_trade(self, trade: dict) -> Optional[int]:
        """Save a trade record. Returns the row ID."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._save_trade_sync, trade
        )

    def _save_trade_sync(self, trade: dict) -> Optional[int]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                """INSERT INTO trades 
                   (timestamp, token_pair, direction, amount_usd, expected_profit_usd,
                    actual_profit_usd, gas_cost_usd, success, tx_hash, dry_run, error, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    trade.get("timestamp", timestamp_iso()),
                    trade.get("token_pair", ""),
                    trade.get("direction", ""),
                    trade.get("amount_usd", 0),
                    trade.get("expected_profit_usd", 0),
                    trade.get("actual_profit_usd", 0),
                    trade.get("gas_cost_usd", 0),
                    1 if trade.get("success") else 0,
                    trade.get("tx_hash", ""),
                    1 if trade.get("dry_run", True) else 0,
                    trade.get("error", ""),
                    json.dumps(trade, default=str),
                ),
            )
            conn.commit()
            return cursor.lastrowid
        except Exception as e:
            logger.error(f"Failed to save trade: {e}")
            return None
        finally:
            conn.close()

    async def get_recent_trades(self, n: int = 50) -> list[dict]:
        """Retrieve the most recent N trades."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_recent_trades_sync, n
        )

    def _get_recent_trades_sync(self, n: int) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM trades ORDER BY id DESC LIMIT ?", (n,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"Failed to get trades: {e}")
            return []
        finally:
            conn.close()

    async def get_trades_by_pair(self, token_pair: str, n: int = 50) -> list[dict]:
        """Get trades filtered by token pair."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_trades_by_pair_sync, token_pair, n
        )

    def _get_trades_by_pair_sync(self, token_pair: str, n: int) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM trades WHERE token_pair = ? ORDER BY id DESC LIMIT ?",
                (token_pair, n),
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    async def get_trade_stats(self) -> dict:
        """Get aggregate trade statistics."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_trade_stats_sync
        )

    def _get_trade_stats_sync(self) -> dict:
        conn = self._get_conn()
        try:
            row = conn.execute("""
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN success = 0 THEN 1 ELSE 0 END) as losses,
                    SUM(actual_profit_usd) as total_pnl,
                    SUM(gas_cost_usd) as total_gas,
                    AVG(CASE WHEN actual_profit_usd > 0 THEN actual_profit_usd ELSE NULL END) as avg_win,
                    AVG(CASE WHEN actual_profit_usd <= 0 THEN actual_profit_usd ELSE NULL END) as avg_loss,
                    MAX(actual_profit_usd) as best_trade,
                    MIN(actual_profit_usd) as worst_trade
                FROM trades
            """).fetchone()
            return dict(row) if row else {}
        except Exception:
            return {}
        finally:
            conn.close()

    # ── Portfolio Snapshot Operations ──────────────────────────────
    async def save_portfolio_snapshot(
        self, portfolio_state, cycle_number: int = 0, metrics: dict = None
    ) -> None:
        """Save a portfolio snapshot for historical tracking."""
        await asyncio.get_event_loop().run_in_executor(
            None,
            self._save_snapshot_sync,
            portfolio_state,
            cycle_number,
            metrics or {},
        )

    def _save_snapshot_sync(self, portfolio, cycle_number: int, metrics: dict) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO portfolio_snapshots 
                   (timestamp, cycle_number, capital_usd, total_pnl_usd, total_trades,
                    winning_trades, losing_trades, win_rate, drawdown_pct, sharpe_ratio,
                    peak_capital_usd)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    timestamp_iso(),
                    cycle_number,
                    portfolio.capital_usd,
                    portfolio.total_pnl_usd,
                    portfolio.total_trades,
                    portfolio.winning_trades,
                    portfolio.losing_trades,
                    portfolio.win_rate,
                    portfolio.current_drawdown_pct,
                    metrics.get("sharpe_ratio", 0),
                    portfolio.peak_capital_usd,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save snapshot: {e}")
        finally:
            conn.close()

    async def get_portfolio_history(self, n: int = 100) -> list[dict]:
        """Get portfolio history for charting."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_portfolio_history_sync, n
        )

    def _get_portfolio_history_sync(self, n: int) -> list[dict]:
        conn = self._get_conn()
        try:
            cursor = conn.execute(
                "SELECT * FROM portfolio_snapshots ORDER BY id DESC LIMIT ?", (n,)
            )
            return [dict(row) for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()

    # ── Pool Snapshot Operations ──────────────────────────────────
    async def save_pool_snapshot(self, pool) -> None:
        """Save a pool state snapshot."""
        await asyncio.get_event_loop().run_in_executor(
            None, self._save_pool_sync, pool
        )

    def _save_pool_sync(self, pool) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO pool_snapshots 
                   (timestamp, pool_address, token_pair, reserve0, reserve1,
                    price, liquidity_usd, volume_24h_usd, source)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    timestamp_iso(),
                    pool.pool_address,
                    f"{pool.token0_symbol}/{pool.token1_symbol}",
                    pool.reserve0,
                    pool.reserve1,
                    pool.price_token0_in_token1,
                    pool.liquidity_usd,
                    pool.volume_24h_usd,
                    pool.source,
                ),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to save pool snapshot: {e}")
        finally:
            conn.close()

    # ── Feedback Adjustment Logging ───────────────────────────────
    async def save_feedback_adjustment(
        self, adj_type: str, old_val: float, new_val: float, reason: str = ""
    ) -> None:
        """Log a feedback agent parameter adjustment."""
        await asyncio.get_event_loop().run_in_executor(
            None, self._save_feedback_sync, adj_type, old_val, new_val, reason
        )

    def _save_feedback_sync(
        self, adj_type: str, old_val: float, new_val: float, reason: str
    ) -> None:
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO feedback_adjustments
                   (timestamp, adjustment_type, old_value, new_value, reason)
                   VALUES (?, ?, ?, ?, ?)""",
                (timestamp_iso(), adj_type, old_val, new_val, reason),
            )
            conn.commit()
        except Exception as e:
            logger.error(f"Failed to log adjustment: {e}")
        finally:
            conn.close()

    # ── Utilities ─────────────────────────────────────────────────
    async def get_table_counts(self) -> dict:
        """Return row counts for all tables."""
        return await asyncio.get_event_loop().run_in_executor(
            None, self._get_table_counts_sync
        )

    def _get_table_counts_sync(self) -> dict:
        conn = self._get_conn()
        try:
            counts = {}
            for table in ["trades", "portfolio_snapshots", "pool_snapshots", "feedback_adjustments"]:
                row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
                counts[table] = row["cnt"] if row else 0
            return counts
        except Exception:
            return {}
        finally:
            conn.close()

    async def clear_all(self) -> None:
        """Clear all data (for testing). """
        def _clear():
            conn = self._get_conn()
            try:
                for table in ["trades", "portfolio_snapshots", "pool_snapshots", "feedback_adjustments"]:
                    conn.execute(f"DELETE FROM {table}")
                conn.commit()
                logger.info("All database tables cleared")
            finally:
                conn.close()
        await asyncio.get_event_loop().run_in_executor(None, _clear)
