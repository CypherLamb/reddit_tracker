"""Ticker list management and text extraction.

On first run (or when cache is stale) we pull the S&P 500 constituent CSV
from GitHub and merge it with a hand-curated meme/small-cap list.
Subsequent runs read from the local CSV cache.

extract_tickers() is the shared extraction function used by both
poller.py (subreddit posts) and live_thread.py (daily thread comments).
"""

import csv
import logging
import os
import re
import time
from typing import Dict, List, Tuple

import requests

from config import (
    EXCLUSION_LIST,
    EXTRA_TICKERS,
    GERMAN_TICKER_MAP,
    SP500_CSV_URL,
    TICKER_CACHE_MAX_AGE,
    TICKER_CACHE_PATH,
)

logger = logging.getLogger(__name__)

# Pre-compiled patterns for speed
_DOLLAR_RE = re.compile(r"\$([A-Z]{1,5})\b")
_BARE_RE = re.compile(r"\b([A-Z]{2,5})\b")


# ---------------------------------------------------------------------------
# Ticker loading
# ---------------------------------------------------------------------------

def load_tickers() -> Dict[str, Tuple[str, str]]:
    """Return {symbol: (name, sector)} merged from cache/GitHub + extras."""
    tickers: Dict[str, Tuple[str, str]] = {}

    if os.path.exists(TICKER_CACHE_PATH):
        age = time.time() - os.path.getmtime(TICKER_CACHE_PATH)
        if age < TICKER_CACHE_MAX_AGE:
            tickers = _load_csv(TICKER_CACHE_PATH)
            if tickers:
                logger.info("Loaded %d tickers from cache", len(tickers))

    if not tickers:
        tickers = _fetch_sp500()
        if tickers:
            _save_csv(tickers, TICKER_CACHE_PATH)
            logger.info("Fetched %d S&P 500 tickers from GitHub", len(tickers))
        else:
            logger.warning("GitHub fetch failed; proceeding with extras only")

    # Merge extra meme/small-cap tickers (don't overwrite S&P 500 entries)
    for symbol, name in EXTRA_TICKERS.items():
        if symbol not in tickers:
            tickers[symbol] = (name, "")

    logger.info("Total tickers available: %d", len(tickers))
    return tickers


def _fetch_sp500() -> Dict[str, Tuple[str, str]]:
    try:
        resp = requests.get(SP500_CSV_URL, timeout=15)
        resp.raise_for_status()
        reader = csv.DictReader(resp.text.splitlines())
        result = {}
        for row in reader:
            sym = row.get("Symbol", "").strip().upper()
            name = row.get("Name", "").strip()
            sector = row.get("Sector", "").strip()
            if sym:
                result[sym] = (name, sector)
        return result
    except Exception as exc:
        logger.warning("S&P 500 fetch error: %s", exc)
        return {}


def _load_csv(path: str) -> Dict[str, Tuple[str, str]]:
    try:
        result = {}
        with open(path, newline="", encoding="utf-8") as fh:
            for row in csv.DictReader(fh):
                sym = row.get("symbol", "").strip().upper()
                if sym:
                    result[sym] = (
                        row.get("name", "").strip(),
                        row.get("sector", "").strip(),
                    )
        return result
    except Exception as exc:
        logger.warning("Cache load error: %s", exc)
        return {}


def _save_csv(tickers: Dict[str, Tuple[str, str]], path: str) -> None:
    try:
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=["symbol", "name", "sector"])
            writer.writeheader()
            for sym, (name, sector) in sorted(tickers.items()):
                writer.writerow({"symbol": sym, "name": name, "sector": sector})
    except Exception as exc:
        logger.warning("Cache save error: %s", exc)


# ---------------------------------------------------------------------------
# Ticker extraction
# ---------------------------------------------------------------------------

def extract_tickers(
    text: str,
    known_tickers: Dict[str, Tuple[str, str]],
    subreddit: str = "",
) -> List[str]:
    """Extract ticker symbols from *text* using two strategies:

    1. ``$TICKER`` — high-confidence, extract from known list.
    2. Bare ALL-CAPS 2-5 letter words — cross-reference known list only.

    For r/mauerstrassenwetten, additionally scan for German company names
    and map them to their ticker symbols.
    """
    if not text:
        return []

    found: set = set()

    # Strategy 1: explicit $TICKER prefix
    for m in _DOLLAR_RE.finditer(text):
        sym = m.group(1)
        if sym in known_tickers and sym not in EXCLUSION_LIST:
            found.add(sym)

    # Strategy 2: bare uppercase word cross-referenced against ticker list
    for m in _BARE_RE.finditer(text):
        sym = m.group(1)
        if sym in known_tickers and sym not in EXCLUSION_LIST:
            found.add(sym)

    # Strategy 3: German company names (r/mauerstrassenwetten only)
    if subreddit == "mauerstrassenwetten":
        text_lower = text.lower()
        for german_name, ticker_sym in GERMAN_TICKER_MAP.items():
            if german_name in text_lower:
                if ticker_sym in known_tickers or ticker_sym in EXTRA_TICKERS:
                    found.add(ticker_sym)

    return list(found)
