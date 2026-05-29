"""SQLite schema definition and query helpers.

Each thread gets its own connection (thread-local storage) so WAL mode
can serve concurrent readers (dashboard) and writers (pollers) safely.
"""

import sqlite3
import threading
import time
import logging
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from config import DB_PATH

logger = logging.getLogger(__name__)
_local = threading.local()


# ---------------------------------------------------------------------------
# Connection management
# ---------------------------------------------------------------------------

def _get_conn() -> sqlite3.Connection:
    if not hasattr(_local, "conn") or _local.conn is None:
        conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return _local.conn


@contextmanager
def _cursor():
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


# ---------------------------------------------------------------------------
# Schema initialisation
# ---------------------------------------------------------------------------

def init_db() -> None:
    with _cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS mentions (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                ticker       TEXT    NOT NULL,
                subreddit    TEXT    NOT NULL,
                post_id      TEXT    NOT NULL,
                comment_id   TEXT    NOT NULL DEFAULT '',
                author       TEXT    DEFAULT '',
                title        TEXT    DEFAULT '',
                body_snippet TEXT    DEFAULT '',
                score        INTEGER DEFAULT 0,
                timestamp    INTEGER NOT NULL,
                is_live_thread INTEGER DEFAULT 0,
                created_at   INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        cur.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_mentions_dedup
            ON mentions(post_id, comment_id, ticker)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mentions_ticker_ts
            ON mentions(ticker, timestamp)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mentions_sub_ts
            ON mentions(subreddit, timestamp)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_mentions_live
            ON mentions(is_live_thread, timestamp)
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS tickers (
                symbol TEXT PRIMARY KEY,
                name   TEXT DEFAULT '',
                sector TEXT DEFAULT ''
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS live_comments (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                comment_id TEXT    UNIQUE NOT NULL,
                post_id    TEXT    NOT NULL,
                author     TEXT    DEFAULT '',
                body       TEXT    DEFAULT '',
                score      INTEGER DEFAULT 0,
                timestamp  INTEGER NOT NULL,
                tickers    TEXT    DEFAULT '',
                created_at INTEGER DEFAULT (strftime('%s','now'))
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_lc_timestamp
            ON live_comments(timestamp)
        """)
    logger.info("Database initialised at %s", DB_PATH)


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_ticker(symbol: str, name: str = "", sector: str = "") -> None:
    with _cursor() as cur:
        cur.execute(
            "INSERT OR IGNORE INTO tickers (symbol, name, sector) VALUES (?,?,?)",
            (symbol, name, sector),
        )


def insert_mention(
    ticker: str,
    subreddit: str,
    post_id: str,
    comment_id: str = "",
    author: str = "",
    title: str = "",
    body_snippet: str = "",
    score: int = 0,
    timestamp: int = 0,
    is_live_thread: bool = False,
) -> bool:
    """Insert a ticker mention; silently ignores duplicates. Returns True if inserted."""
    if timestamp == 0:
        timestamp = int(time.time())
    try:
        with _cursor() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO mentions
                  (ticker, subreddit, post_id, comment_id, author,
                   title, body_snippet, score, timestamp, is_live_thread)
                VALUES (?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    ticker, subreddit, post_id, comment_id or "",
                    author or "", title or "", body_snippet or "",
                    score, timestamp, 1 if is_live_thread else 0,
                ),
            )
            return True
    except sqlite3.IntegrityError:
        return False


def insert_live_comment(
    comment_id: str,
    post_id: str,
    author: str,
    body: str,
    score: int,
    timestamp: int,
    tickers: List[str],
) -> bool:
    """Store a live-thread comment for the live feed display."""
    tickers_str = ",".join(sorted(set(tickers)))
    try:
        with _cursor() as cur:
            cur.execute(
                """
                INSERT OR IGNORE INTO live_comments
                  (comment_id, post_id, author, body, score, timestamp, tickers)
                VALUES (?,?,?,?,?,?,?)
                """,
                (comment_id, post_id, author or "", body or "",
                 score, timestamp, tickers_str),
            )
            return True
    except sqlite3.IntegrityError:
        return False


# ---------------------------------------------------------------------------
# Read helpers (called by the dashboard; use a fresh read-only connection
# each call so dashboard process never blocks on a write-side commit)
# ---------------------------------------------------------------------------

def _read_conn() -> sqlite3.Connection:
    """Return a lightweight per-call read connection for the dashboard."""
    conn = sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True,
                           check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def get_top_tickers(
    subreddits: Optional[List[str]] = None,
    since_ts: int = 0,
    limit: int = 50,
) -> List[Dict]:
    sql = """
        SELECT ticker,
               COUNT(*) AS mention_count,
               MAX(timestamp) AS last_seen,
               GROUP_CONCAT(DISTINCT subreddit) AS subreddits
        FROM mentions
        WHERE timestamp >= ?
          AND ticker != ''
    """
    params: List[Any] = [since_ts]
    if subreddits:
        sql += f" AND subreddit IN ({','.join('?'*len(subreddits))})"
        params += subreddits
    sql += " GROUP BY ticker ORDER BY mention_count DESC LIMIT ?"
    params.append(limit)

    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_mention_timeline(
    tickers: List[str],
    since_ts: int = 0,
    bucket_seconds: int = 3600,
) -> List[Dict]:
    if not tickers:
        return []
    placeholders = ",".join("?" * len(tickers))
    sql = f"""
        SELECT ticker,
               (timestamp / ?) * ? AS bucket,
               COUNT(*) AS count
        FROM mentions
        WHERE ticker IN ({placeholders})
          AND timestamp >= ?
          AND ticker != ''
        GROUP BY ticker, bucket
        ORDER BY bucket ASC
    """
    params = [bucket_seconds, bucket_seconds] + list(tickers) + [since_ts]
    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_live_comments(limit: int = 100) -> List[Dict]:
    sql = """
        SELECT * FROM live_comments
        ORDER BY timestamp DESC
        LIMIT ?
    """
    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (limit,)).fetchall()]


def get_recent_posts(
    subreddits: Optional[List[str]] = None,
    limit: int = 60,
) -> List[Dict]:
    sql = """
        SELECT post_id, subreddit, author, title, body_snippet,
               MAX(score) AS score, timestamp,
               GROUP_CONCAT(DISTINCT ticker) AS tickers
        FROM mentions
        WHERE comment_id = ''
          AND ticker != ''
    """
    params: List[Any] = []
    if subreddits:
        sql += f" AND subreddit IN ({','.join('?'*len(subreddits))})"
        params += subreddits
    sql += " GROUP BY post_id ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)

    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]


def get_subreddit_breakdown(since_ts: int = 0) -> List[Dict]:
    sql = """
        SELECT subreddit, COUNT(*) AS mention_count
        FROM mentions
        WHERE timestamp >= ?
          AND ticker != ''
        GROUP BY subreddit
        ORDER BY mention_count DESC
    """
    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (since_ts,)).fetchall()]


def get_ticker_subreddit_breakdown(ticker: str, since_ts: int = 0) -> List[Dict]:
    sql = """
        SELECT subreddit, COUNT(*) AS mention_count
        FROM mentions
        WHERE ticker = ?
          AND timestamp >= ?
        GROUP BY subreddit
        ORDER BY mention_count DESC
    """
    with _read_conn() as conn:
        return [dict(r) for r in conn.execute(sql, (ticker, since_ts)).fetchall()]


def get_all_tracked_tickers() -> List[str]:
    with _read_conn() as conn:
        rows = conn.execute(
            "SELECT DISTINCT ticker FROM mentions WHERE ticker != '' "
            "ORDER BY ticker"
        ).fetchall()
    return [r["ticker"] for r in rows]
