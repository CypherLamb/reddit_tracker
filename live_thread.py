"""WSB Daily Discussion Thread live comment streamer.

Runs as a daemon thread started by main.py.
- Auto-detects the current day's Daily Thread in r/wallstreetbets.
- Polls for new comments every LIVE_THREAD_POLL_INTERVAL seconds.
- Writes each new comment to `live_comments` (for the feed display) and
  each ticker mention to `mentions` (for leaderboard / timeline stats).
"""

import logging
import random
import re
import time
from datetime import date
from typing import Dict, List, Optional, Tuple

import praw.models

from config import LIVE_THREAD_POLL_INTERVAL
from db import insert_live_comment, insert_mention
from reddit_client import create_reddit, get_thread_comments_new, jitter_sleep
from ticker_loader import extract_tickers

logger = logging.getLogger(__name__)

_DAILY_PATTERNS = [
    re.compile(r"daily discussion", re.IGNORECASE),
    re.compile(r"daily thread", re.IGNORECASE),
    re.compile(r"what are your moves", re.IGNORECASE),
    re.compile(r"weekend discussion", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Thread detection
# ---------------------------------------------------------------------------

def _matches_today(title: str) -> bool:
    today = date.today()
    candidates = [
        today.strftime("%B %d, %Y"),    # "May 28, 2026"
        today.strftime("%B %-d, %Y"),   # "May 8, 2026"  (Linux)
        today.strftime("%Y-%m-%d"),     # "2026-05-28"
        today.strftime("%m/%d/%Y"),     # "05/28/2026"
        today.strftime("%b %d"),        # "May 28"
        today.strftime("%b %-d"),       # "May 8"        (Linux)
        str(today.day),                 # Fallback: just the day number
    ]
    # Windows doesn't support %-d; strip leading zeros manually
    candidates.append(
        today.strftime("%B %d, %Y").replace(" 0", " ")
    )
    return any(c in title for c in candidates)


def find_daily_thread(
    reddit,
    subreddit: str = "wallstreetbets",
) -> Optional[praw.models.Submission]:
    try:
        sub = reddit.subreddit(subreddit)
        # Scan the first 10 hot posts (pinned are always first)
        posts = list(sub.hot(limit=10))
        jitter_sleep(0.5, 0.3)

        best: Optional[praw.models.Submission] = None
        for post in posts:
            if any(p.search(post.title) for p in _DAILY_PATTERNS):
                if _matches_today(post.title):
                    logger.info("Found today's daily thread: %s", post.title)
                    return post
                if best is None:
                    best = post  # fallback: most recent daily thread

        if best is not None:
            logger.info("Falling back to: %s", best.title)
        else:
            logger.warning("No daily thread found in r/%s top 10 hot posts", subreddit)
        return best
    except Exception as exc:
        logger.error("find_daily_thread error: %s", exc)
        return None


# ---------------------------------------------------------------------------
# Comment processing
# ---------------------------------------------------------------------------

def _process_comments(
    comments: List[praw.models.Comment],
    thread: praw.models.Submission,
    known_tickers: Dict[str, Tuple[str, str]],
    last_ts: int,
) -> Tuple[int, int]:
    """Process comments newer than last_ts. Returns (new_max_ts, inserted_count)."""
    new_max_ts = last_ts
    inserted = 0

    for comment in comments:
        if not hasattr(comment, "created_utc"):
            continue
        comment_ts = int(comment.created_utc)
        if comment_ts <= last_ts:
            continue

        body = (comment.body or "")[:500]
        author = str(comment.author) if comment.author else "[deleted]"
        tickers = extract_tickers(body, known_tickers, "wallstreetbets")

        # Always store in live_comments for feed display
        insert_live_comment(
            comment_id=comment.id,
            post_id=thread.id,
            author=author,
            body=body,
            score=comment.score,
            timestamp=comment_ts,
            tickers=tickers,
        )

        # Store per-ticker mention rows
        for ticker in tickers:
            insert_mention(
                ticker=ticker,
                subreddit="wallstreetbets",
                post_id=thread.id,
                comment_id=comment.id,
                author=author,
                title=thread.title[:280],
                body_snippet=body[:280],
                score=comment.score,
                timestamp=comment_ts,
                is_live_thread=True,
            )
            inserted += 1

        if comment_ts > new_max_ts:
            new_max_ts = comment_ts

    return new_max_ts, inserted


# ---------------------------------------------------------------------------
# Main live-thread poller loop
# ---------------------------------------------------------------------------

def run_live_thread_poller(
    known_tickers: Dict[str, Tuple[str, str]],
    subreddit: str = "wallstreetbets",
) -> None:
    """Entry point for the live-thread polling daemon thread."""
    reddit = create_reddit()
    logger.info("Live-thread poller started (r/%s)", subreddit)

    current_thread: Optional[praw.models.Submission] = None
    last_ts: int = 0
    refresh_ticks: int = 0  # re-detect thread every ~10 min

    while True:
        # Re-detect daily thread every 20 cycles (~10 min) or when absent
        if current_thread is None or refresh_ticks >= 20:
            current_thread = find_daily_thread(reddit, subreddit)
            refresh_ticks = 0
            last_ts = 0  # reset so we don't skip old comments on first load
            if current_thread is None:
                logger.warning("No daily thread; retrying in 60s")
                time.sleep(60)
                continue

        try:
            comments = get_thread_comments_new(reddit, current_thread.id)
            last_ts, count = _process_comments(
                comments, current_thread, known_tickers, last_ts
            )
            if count:
                logger.info("Live thread: %d ticker mentions stored", count)
        except Exception as exc:
            logger.error("Live thread poll error: %s", exc)
            current_thread = None  # force re-detection

        refresh_ticks += 1
        sleep_secs = LIVE_THREAD_POLL_INTERVAL + random.uniform(-5, 8)
        time.sleep(max(15, sleep_secs))
