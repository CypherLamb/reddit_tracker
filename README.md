# Reddit Stock Mention Tracker

A Python application that monitors multiple subreddits for stock ticker mentions
and visualises trends in a live-updating web dashboard.

## Features

| Panel | What it shows |
|-------|--------------|
| **Leaderboard** | Top N tickers by mention count — bar chart + sortable table |
| **Timeline** | Multi-ticker mention frequency over time (line chart) |
| **Live Feed** | WSB Daily Thread comments with ticker highlights, auto-refreshed every 30 s |
| **Recent Posts** | Latest posts across all tracked subreddits with extracted ticker tags |
| **Breakdown** | Subreddit share pie chart + per-ticker drill-down |

Global sidebar filters: subreddit multi-select, time window (1 h / 6 h / 24 h / 7 d).

## Monitored subreddits

- r/wallstreetbets (+ live Daily Discussion Thread stream)
- r/ValueInvesting
- r/stocks
- r/Stock_Picks
- r/mauerstrassenwetten (with German company name → ticker mapping)

---

## Setup

### 1. Prerequisites

- Python 3.10 or newer
- A Reddit account

### 2. Create a Reddit API app

1. Go to <https://www.reddit.com/prefs/apps> (log in first).
2. Click **"create another app…"** at the bottom.
3. Choose **"script"** (not "web app").
4. Fill in any name, redirect URI `http://localhost:8080`.
5. Copy the **client ID** (shown under the app name) and **client secret**.

### 3. Clone / download the project

```bash
cd c:\DEV
# Already there if you're reading this from the repo
```

### 4. Create a virtual environment and install dependencies

```bash
cd reddit_tracker
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

### 5. Configure credentials

```bash
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
```

Edit `.env`:

```dotenv
REDDIT_CLIENT_ID=abc123xyz          # the short id under your app name
REDDIT_CLIENT_SECRET=secret_value
REDDIT_USER_AGENT=StockTracker/1.0 by /u/YourRedditUsername
```

---

## Running

```bash
python main.py
```

Open your browser at **http://localhost:8501**.

Optional flags:

```bash
python main.py --port 8888      # use a different port
python main.py --no-browser     # don't try to open browser automatically
```

What happens on startup:

1. Database (`stock_mentions.db`) is created / migrated.
2. S&P 500 ticker list is fetched from GitHub and cached to `tickers_cache.csv`.
3. A **24-hour backfill** runs (up to 100 posts per subreddit).
4. The **5-minute subreddit poller** loop starts.
5. The **30-second live-thread poller** starts (detects today's WSB Daily Thread).
6. The Streamlit dashboard launches.

---

## Screenshots

> _Add screenshots here after first run._

---

## Architecture

```
main.py
 ├── Thread: subreddit_poller  (every 5 min)
 │     ├── reddit_client.get_hot_posts / get_new_posts
 │     ├── ticker_loader.extract_tickers
 │     └── db.insert_mention
 ├── Thread: live_thread_poller  (every 30 s)
 │     ├── live_thread.find_daily_thread
 │     ├── ticker_loader.extract_tickers
 │     ├── db.insert_live_comment
 │     └── db.insert_mention
 └── Subprocess: streamlit run dashboard.py
       └── Reads from SQLite (WAL mode, concurrent-safe)
```

### SQLite schema

| Table | Purpose |
|-------|---------|
| `mentions` | All ticker mentions (posts + live thread) |
| `tickers` | Symbol lookup table (S&P 500 + extras) |
| `live_comments` | All WSB Daily Thread comments for the live feed |

---

## Reddit API rate limits

Reddit's API allows ~60 requests per minute for script apps. This tracker:

- Adds **random jitter** (±0.4 s) between every API call.
- Polls subreddits every **5 minutes** (well within limits).
- Polls the live thread every **30 seconds** (1 call/30 s = 2 req/min).
- Uses **PRAW's built-in rate-limit backoff** on 429 responses.
- Performs a **read-only OAuth flow** (no login required).

Even polling all 5 subreddits continuously, peak load is ≈ 6 API calls/minute —
roughly 10% of the allowed quota.

---

## Ticker extraction

- `$TICKER` format: always extracted if in the known list.
- Bare `UPPERCASE` 2–5 letter words: cross-referenced against the ticker list.
- Exclusion list of ~150 false positives (I, AI, DD, YOLO, ETF, CEO, etc.).
- r/mauerstrassenwetten: German company names mapped to tickers (e.g. "Biontech" → BNTX).

The ticker list is the **S&P 500** plus a curated set of popular meme / small-cap
stocks (GME, AMC, NIO, PLTR, COIN, …). It refreshes from GitHub once per day.
