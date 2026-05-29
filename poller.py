"""Subreddit polling loop.

Runs as a daemon thread started by main.py.
Polls hot + new posts from each configured subreddit every
SUBREDDIT_POLL_INTERVAL seconds, extracts ticker mentions, and
writes them to SQLite.
"""

import logging
import random
import time
from typing import Dict, Tuple

import praw.models

from config import (
    BACKFILL_LIMIT,
    POSTS_PER_POLL,
    SUBREDDIT_POLL_INTERVAL,
    SUBREDDITS,
)
from db import insert_mention
from reddit_client import (
    create_reddit,
    get_hot_posts,
    get_new_posts,
    get_top_posts,
    jitter_sleep,
)
from ticker_loader import extract_tickers

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Post processing
# ---------------------------------------------------------------------------

def _process_submission(
    submission: praw.models.Submission,
    subreddit: str,
    known_tickers: Dict[str, Tuple[str, str]],
) -> int:
    """Extract tickers from a submission and persist mentions. Returns count inserted."""
    combined_text = f"{submission.title} {getattr(submission, 'selftext', '') or ''}"
    tickers = extract_tickers(combined_text, known_tickers, subreddit)
    if not tickers:
        return 0

    author = str(submission.author) if submission.author else "[deleted]"
    ts = int(submission.created_utc)
    body_snippet = (getattr(submission, "selftext", "") or "")[:280]

    inserted = 0
    for ticker in tickers:
        if insert_mention(
            ticker=ticker,
            subreddit=subreddit,
            post_id=submission.id,
            comment_id="",
            author=author,
            title=submission.title[:280],
            body_snippet=body_snippet,
            score=submission.score,
            timestamp=ts,
            is_live_thread=False,
        ):
            inserted += 1
    return inserted


# ---------------------------------------------------------------------------
# Per-subreddit poll
# ---------------------------------------------------------------------------

def poll_subreddit(
    reddit,
    subreddit: str,
    known_tickers: Dict[str, Tuple[str, str]],
    limit: int = POSTS_PER_POLL,
) -> int:
    logger.info("Polling r/%s (limit=%d)", subreddit, limit)
    total = 0
    seen: set = set()

    for fetch in (get_hot_posts, get_new_posts):
        for post in fetch(reddit, subreddit, limit=limit):
            if post.id in seen:
                continue
            seen.add(post.id)
            total += _process_submission(post, subreddit, known_tickers)
        jitter_sleep(1.0, 0.5)

    logger.info("r/%s: %d new mentions stored", subreddit, total)
    return total


# ---------------------------------------------------------------------------
# Backfill (run once on startup)
# ---------------------------------------------------------------------------

def _backfill(reddit, known_tickers: Dict[str, Tuple[str, str]]) -> None:
    logger.info("Starting 24h backfill (limit=%d per subreddit)…", BACKFILL_LIMIT)
    for subreddit in SUBREDDITS:
        total = 0
        seen: set = set()
        for fetch in (
            lambda r, s: get_hot_posts(r, s, BACKFILL_LIMIT),
            lambda r, s: get_new_posts(r, s, BACKFILL_LIMIT),
            lambda r, s: get_top_posts(r, s, time_filter="day", limit=BACKFILL_LIMIT),
        ):
            for post in fetch(reddit, subreddit):
                if post.id in seen:
                    continue
                seen.add(post.id)
                total += _process_submission(post, subreddit, known_tickers)
            jitter_sleep(1.5, 0.5)
        logger.info("Backfill r/%s: %d mentions", subreddit, total)
        time.sleep(random.uniform(2, 4))
    logger.info("Backfill complete")


# ---------------------------------------------------------------------------
# Main poller loop
# ---------------------------------------------------------------------------

def run_subreddit_poller(known_tickers: Dict[str, Tuple[str, str]]) -> None:
    """Entry point for the subreddit polling daemon thread."""
    reddit = create_reddit()
    logger.info("Subreddit poller thread started")

    _backfill(reddit, known_tickers)

    while True:
        cycle_start = time.monotonic()
        for subreddit in SUBREDDITS:
            poll_subreddit(reddit, subreddit, known_tickers)
            jitter_sleep(1.5, 0.8)

        elapsed = time.monotonic() - cycle_start
        sleep_secs = max(0, SUBREDDIT_POLL_INTERVAL - elapsed) + random.uniform(0, 15)
        logger.info("Poll cycle done in %.1fs, sleeping %.0fs", elapsed, sleep_secs)
        time.sleep(sleep_secs)
