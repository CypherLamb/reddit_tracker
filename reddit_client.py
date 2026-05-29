"""Thin PRAW wrapper with jitter-based rate-limit protection.

Credentials are read from environment variables (loaded by python-dotenv
in main.py before any other module is imported).
"""

import logging
import os
import random
import time
from typing import List

import praw
import praw.models

logger = logging.getLogger(__name__)


def create_reddit() -> praw.Reddit:
    """Create and return a read-only PRAW Reddit instance."""
    reddit = praw.Reddit(
        client_id=os.environ["REDDIT_CLIENT_ID"],
        client_secret=os.environ["REDDIT_CLIENT_SECRET"],
        user_agent=os.environ.get(
            "REDDIT_USER_AGENT", "StockMentionTracker/1.0"
        ),
    )
    reddit.read_only = True
    return reddit


def jitter_sleep(base: float = 1.0, spread: float = 0.8) -> None:
    """Sleep for base ± spread seconds to avoid request bursts."""
    time.sleep(max(0.1, base + random.uniform(-spread / 2, spread / 2)))


def get_hot_posts(
    reddit: praw.Reddit,
    subreddit: str,
    limit: int = 25,
) -> List[praw.models.Submission]:
    try:
        jitter_sleep(0.6, 0.4)
        posts = list(reddit.subreddit(subreddit).hot(limit=limit))
        logger.debug("r/%s hot: %d posts", subreddit, len(posts))
        return posts
    except Exception as exc:
        logger.error("hot r/%s: %s", subreddit, exc)
        return []


def get_new_posts(
    reddit: praw.Reddit,
    subreddit: str,
    limit: int = 25,
) -> List[praw.models.Submission]:
    try:
        jitter_sleep(0.6, 0.4)
        posts = list(reddit.subreddit(subreddit).new(limit=limit))
        logger.debug("r/%s new: %d posts", subreddit, len(posts))
        return posts
    except Exception as exc:
        logger.error("new r/%s: %s", subreddit, exc)
        return []


def get_top_posts(
    reddit: praw.Reddit,
    subreddit: str,
    time_filter: str = "day",
    limit: int = 25,
) -> List[praw.models.Submission]:
    try:
        jitter_sleep(0.8, 0.4)
        posts = list(
            reddit.subreddit(subreddit).top(time_filter=time_filter, limit=limit)
        )
        logger.debug("r/%s top(%s): %d posts", subreddit, time_filter, len(posts))
        return posts
    except Exception as exc:
        logger.error("top r/%s: %s", subreddit, exc)
        return []


def get_thread_comments_new(
    reddit: praw.Reddit,
    post_id: str,
) -> List[praw.models.Comment]:
    """Fetch top-level comments for a submission sorted by new."""
    try:
        jitter_sleep(0.6, 0.4)
        submission = reddit.submission(id=post_id)
        submission.comment_sort = "new"
        submission.comments.replace_more(limit=0)
        comments = list(submission.comments)
        logger.debug("post %s: %d comments", post_id, len(comments))
        return comments
    except Exception as exc:
        logger.error("comments %s: %s", post_id, exc)
        return []
