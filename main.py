"""Entry point: initialises the database, loads tickers, starts the two
polling daemon threads, then launches the Streamlit dashboard in-process.

Usage:
    python main.py [--port 8501] [--no-browser]
"""

import argparse
import logging
import os
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv

# Load .env before importing any module that reads env vars
load_dotenv()

# Set up logging early
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def _validate_env() -> None:
    missing = [
        k for k in ("REDDIT_CLIENT_ID", "REDDIT_CLIENT_SECRET")
        if not os.environ.get(k)
    ]
    if missing:
        logger.error(
            "Missing env vars: %s\n"
            "Copy .env.example → .env and fill in your Reddit credentials.",
            ", ".join(missing),
        )
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Reddit Stock Mention Tracker")
    parser.add_argument("--port", type=int, default=8501, help="Streamlit port")
    parser.add_argument(
        "--no-browser", action="store_true", help="Don't open browser on start"
    )
    args = parser.parse_args()

    _validate_env()

    # Late imports so dotenv has already populated os.environ
    from db import init_db, upsert_ticker
    from ticker_loader import load_tickers
    from poller import run_subreddit_poller
    from live_thread import run_live_thread_poller

    logger.info("Initialising database…")
    init_db()

    logger.info("Loading ticker list…")
    known_tickers = load_tickers()
    for symbol, (name, sector) in known_tickers.items():
        upsert_ticker(symbol, name, sector)
    logger.info("Ticker DB populated (%d symbols)", len(known_tickers))

    logger.info("Starting subreddit poller thread…")
    t_poller = threading.Thread(
        target=run_subreddit_poller,
        args=(known_tickers,),
        daemon=True,
        name="subreddit-poller",
    )
    t_poller.start()

    # Give the poller a moment to begin its first backfill before streaming starts
    time.sleep(2)

    logger.info("Starting live-thread poller thread…")
    t_live = threading.Thread(
        target=run_live_thread_poller,
        args=(known_tickers,),
        daemon=True,
        name="live-thread-poller",
    )
    t_live.start()

    logger.info("Launching Streamlit dashboard on port %d…", args.port)
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.py")
    streamlit_cmd = [
        sys.executable, "-m", "streamlit", "run", dashboard_path,
        f"--server.port={args.port}",
        "--server.headless=true",
        f"--browser.serverAddress=localhost",
    ]
    if args.no_browser:
        streamlit_cmd.append("--server.headless=true")

    logger.info("Dashboard URL: http://localhost:%d", args.port)
    logger.info("Press Ctrl+C to stop")

    try:
        subprocess.run(
            streamlit_cmd,
            cwd=os.path.dirname(__file__),
            check=False,
        )
    except KeyboardInterrupt:
        logger.info("Shutting down…")


if __name__ == "__main__":
    main()
