"""Streamlit dashboard for the Reddit Stock Mention Tracker.

Launch via:   streamlit run dashboard.py
Or indirectly via:  python main.py  (which starts pollers + this)

Auto-refreshes every 30 seconds using streamlit-autorefresh.
"""

import re
import sys
import time
from datetime import datetime, timezone
from typing import List

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

# Ensure imports from the same directory work when launched as subprocess
import os
sys.path.insert(0, os.path.dirname(__file__))

from config import SUBREDDITS
from db import (
    get_all_tracked_tickers,
    get_live_comments,
    get_mention_timeline,
    get_recent_posts,
    get_subreddit_breakdown,
    get_ticker_subreddit_breakdown,
    get_top_tickers,
)

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Reddit Stock Tracker",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Auto-refresh every 30 s
try:
    from streamlit_autorefresh import st_autorefresh
    st_autorefresh(interval=30_000, key="main_refresh")
except ImportError:
    st.warning(
        "Install `streamlit-autorefresh` for live updates: "
        "`pip install streamlit-autorefresh`"
    )

# ---------------------------------------------------------------------------
# Styles
# ---------------------------------------------------------------------------
st.markdown(
    """
    <style>
    .ticker-chip {
        display: inline-block;
        background: #1e3a5f;
        color: #4fc3f7;
        border: 1px solid #4fc3f7;
        border-radius: 12px;
        padding: 2px 10px;
        font-size: 0.78em;
        font-weight: 700;
        margin: 2px;
        letter-spacing: 0.05em;
    }
    .comment-card {
        border: 1px solid #333;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 10px;
        background: #0e1117;
    }
    .comment-meta {
        color: #888;
        font-size: 0.82em;
        margin-bottom: 6px;
    }
    .comment-body {
        line-height: 1.55;
        font-size: 0.92em;
        word-break: break-word;
    }
    .post-card {
        border: 1px solid #2a3a5c;
        border-radius: 8px;
        padding: 10px 14px;
        margin-bottom: 8px;
        background: #0e1117;
    }
    .post-title { font-weight: 600; font-size: 0.95em; }
    .post-meta { color: #888; font-size: 0.80em; margin-top: 4px; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts_to_str(ts: int) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%H:%M %b %d")


def _since_ts(window: str) -> int:
    windows = {"1h": 3600, "6h": 21_600, "24h": 86_400, "7d": 604_800}
    return int(time.time()) - windows.get(window, 86_400)


def _bucket_for_window(window: str) -> int:
    """Bucket size in seconds for the timeline chart."""
    return {"1h": 300, "6h": 1_800, "24h": 3_600, "7d": 86_400}.get(window, 3_600)


def _highlight_tickers_html(text: str, tickers: List[str]) -> str:
    """Wrap each ticker mention in a coloured <span>."""
    if not tickers:
        return text
    # Sort longest first so overlapping patterns don't partially match
    for t in sorted(tickers, key=len, reverse=True):
        pattern = re.compile(r"(\$?" + re.escape(t) + r")\b")
        text = pattern.sub(
            r'<span class="ticker-chip">\1</span>',
            text,
        )
    return text


def _ticker_chips_html(tickers_csv: str) -> str:
    if not tickers_csv:
        return ""
    chips = [
        f'<span class="ticker-chip">{t.strip()}</span>'
        for t in tickers_csv.split(",")
        if t.strip()
    ]
    return " ".join(chips)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
st.sidebar.title("📈 Filters")
selected_subs = st.sidebar.multiselect(
    "Subreddits",
    options=SUBREDDITS,
    default=SUBREDDITS,
    help="Filter all panels by subreddit",
)
if not selected_subs:
    selected_subs = SUBREDDITS  # fallback to all

time_window = st.sidebar.selectbox(
    "Time Window",
    options=["1h", "6h", "24h", "7d"],
    index=2,
)
top_n = st.sidebar.slider("Top N Tickers", min_value=5, max_value=50, value=20, step=5)

since_ts = _since_ts(time_window)

st.sidebar.divider()
st.sidebar.caption(
    f"Last refresh: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}"
)
st.sidebar.caption("Auto-refreshes every 30 s")

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("Reddit Stock Mention Tracker 📈")
col_a, col_b, col_c = st.columns(3)
with col_a:
    top_data = get_top_tickers(selected_subs, since_ts, limit=1)
    top_tick = top_data[0]["ticker"] if top_data else "—"
    st.metric("Top Ticker", top_tick,
              f"{top_data[0]['mention_count']} mentions" if top_data else "")
with col_b:
    all_top = get_top_tickers(selected_subs, since_ts, limit=200)
    st.metric("Unique Tickers Tracked", len(all_top))
with col_c:
    total_mentions = sum(r["mention_count"] for r in all_top)
    st.metric("Total Mentions", f"{total_mentions:,}")

st.divider()

# ---------------------------------------------------------------------------
# Tabs
# ---------------------------------------------------------------------------
tab_lead, tab_time, tab_live, tab_posts, tab_break = st.tabs(
    ["📊 Leaderboard", "📈 Timeline", "💬 Live Feed", "📰 Recent Posts", "🥧 Breakdown"]
)


# ── Tab 1: Leaderboard ─────────────────────────────────────────────────────
with tab_lead:
    st.subheader(f"Top {top_n} Tickers — {time_window}")
    leaderboard_data = get_top_tickers(selected_subs, since_ts, limit=top_n)

    if not leaderboard_data:
        st.info("No mentions recorded yet. Pollers will populate data shortly.")
    else:
        df_lead = pd.DataFrame(leaderboard_data)
        df_lead["last_seen"] = df_lead["last_seen"].apply(_ts_to_str)

        # Bar chart
        fig_bar = px.bar(
            df_lead,
            x="mention_count",
            y="ticker",
            orientation="h",
            color="mention_count",
            color_continuous_scale="Blues",
            labels={"mention_count": "Mentions", "ticker": "Ticker"},
            title=f"Top {top_n} by Mention Count ({time_window})",
        )
        fig_bar.update_layout(
            yaxis={"categoryorder": "total ascending"},
            showlegend=False,
            coloraxis_showscale=False,
            height=max(350, top_n * 22),
            margin=dict(l=60, r=20, t=50, b=40),
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
        )
        fig_bar.update_xaxes(showgrid=True, gridcolor="#222")
        st.plotly_chart(fig_bar, use_container_width=True)

        # Sortable table
        st.dataframe(
            df_lead.rename(columns={
                "ticker": "Ticker",
                "mention_count": "Mentions",
                "last_seen": "Last Seen",
                "subreddits": "Subreddits",
            }),
            use_container_width=True,
            hide_index=True,
        )


# ── Tab 2: Timeline ─────────────────────────────────────────────────────────
with tab_time:
    st.subheader("Mention Frequency Over Time")

    tracked = get_all_tracked_tickers()
    # Pre-select the top 5 by default
    top5 = [r["ticker"] for r in (all_top[:5] if all_top else [])]

    selected_tickers = st.multiselect(
        "Tickers to plot",
        options=tracked if tracked else top5,
        default=top5,
        key="timeline_tickers",
    )

    if not selected_tickers:
        st.info("Select at least one ticker above.")
    else:
        bucket = _bucket_for_window(time_window)
        timeline_rows = get_mention_timeline(selected_tickers, since_ts, bucket)

        if not timeline_rows:
            st.info("No timeline data for the selected tickers / window.")
        else:
            df_time = pd.DataFrame(timeline_rows)
            df_time["datetime"] = pd.to_datetime(df_time["bucket"], unit="s", utc=True)

            fig_line = px.line(
                df_time,
                x="datetime",
                y="count",
                color="ticker",
                markers=True,
                labels={"count": "Mentions", "datetime": "Time", "ticker": "Ticker"},
                title=f"Mention Frequency ({time_window})",
            )
            fig_line.update_layout(
                height=420,
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            )
            fig_line.update_xaxes(showgrid=True, gridcolor="#222")
            fig_line.update_yaxes(showgrid=True, gridcolor="#222")
            st.plotly_chart(fig_line, use_container_width=True)


# ── Tab 3: Live Feed ─────────────────────────────────────────────────────────
with tab_live:
    st.subheader("WSB Daily Thread — Live Comment Stream")
    st.caption("Showing latest 60 comments · auto-refreshes every 30 s")

    live_rows = get_live_comments(limit=60)

    if not live_rows:
        st.info(
            "No live comments yet.\n\n"
            "The live-thread poller auto-detects today's WSB Daily Discussion "
            "thread on startup. Check logs if data doesn't appear."
        )
    else:
        for row in live_rows:
            tickers_list = [t for t in row.get("tickers", "").split(",") if t]
            body_html = _highlight_tickers_html(row["body"], tickers_list)
            chips_html = _ticker_chips_html(row.get("tickers", ""))
            ts_str = _ts_to_str(row["timestamp"])
            score = row.get("score", 0)

            st.markdown(
                f"""
                <div class="comment-card">
                  <div class="comment-meta">
                    <b>u/{row['author']}</b> &nbsp;·&nbsp;
                    score: {score} &nbsp;·&nbsp;
                    {ts_str}
                  </div>
                  <div class="comment-body">{body_html}</div>
                  {"<div style='margin-top:8px'>" + chips_html + "</div>" if chips_html else ""}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── Tab 4: Recent Posts ──────────────────────────────────────────────────────
with tab_posts:
    st.subheader("Recent Posts Across Tracked Subreddits")

    posts_data = get_recent_posts(selected_subs, limit=60)

    if not posts_data:
        st.info("No posts recorded yet.")
    else:
        for post in posts_data:
            chips = _ticker_chips_html(post.get("tickers", ""))
            ts_str = _ts_to_str(post["timestamp"])
            sub = post["subreddit"]
            score = post.get("score", 0)
            snippet = (post.get("body_snippet") or "").strip()

            st.markdown(
                f"""
                <div class="post-card">
                  <div class="post-title">
                    <span style="color:#4fc3f7">r/{sub}</span> &nbsp;
                    {post['title']}
                  </div>
                  {"<div style='margin-top:4px;color:#aaa;font-size:0.87em'>" + snippet + "</div>" if snippet else ""}
                  <div class="post-meta">
                    u/{post['author']} &nbsp;·&nbsp;
                    score: {score} &nbsp;·&nbsp;
                    {ts_str}
                  </div>
                  {"<div style='margin-top:6px'>" + chips + "</div>" if chips else ""}
                </div>
                """,
                unsafe_allow_html=True,
            )


# ── Tab 5: Breakdown ─────────────────────────────────────────────────────────
with tab_break:
    st.subheader(f"Mention Share by Subreddit ({time_window})")

    col_pie, col_drill = st.columns([1, 1])

    with col_pie:
        breakdown = get_subreddit_breakdown(since_ts)
        if not breakdown:
            st.info("No data yet.")
        else:
            df_break = pd.DataFrame(breakdown)
            fig_pie = px.pie(
                df_break,
                values="mention_count",
                names="subreddit",
                title="All Tickers — Subreddit Share",
                hole=0.35,
            )
            fig_pie.update_layout(
                plot_bgcolor="rgba(0,0,0,0)",
                paper_bgcolor="rgba(0,0,0,0)",
                height=380,
            )
            fig_pie.update_traces(textposition="inside", textinfo="percent+label")
            st.plotly_chart(fig_pie, use_container_width=True)

    with col_drill:
        st.markdown("**Drill into a specific ticker:**")
        drill_ticker = st.text_input(
            "Ticker symbol (e.g. AAPL)",
            value="",
            key="drill_ticker",
        ).strip().upper()

        if drill_ticker:
            drill_data = get_ticker_subreddit_breakdown(drill_ticker, since_ts)
            if not drill_data:
                st.info(f"No mentions of **{drill_ticker}** in the selected window.")
            else:
                df_drill = pd.DataFrame(drill_data)
                fig_drill = px.bar(
                    df_drill,
                    x="subreddit",
                    y="mention_count",
                    color="subreddit",
                    title=f"{drill_ticker} — mentions per subreddit",
                    labels={"mention_count": "Mentions"},
                )
                fig_drill.update_layout(
                    showlegend=False,
                    plot_bgcolor="rgba(0,0,0,0)",
                    paper_bgcolor="rgba(0,0,0,0)",
                    height=320,
                )
                st.plotly_chart(fig_drill, use_container_width=True)

    # Stacked bar: top 10 tickers × subreddit
    st.divider()
    st.markdown("**Top 10 Tickers — Mention Breakdown by Subreddit**")

    top10_tickers = [r["ticker"] for r in all_top[:10]]
    stacked_rows = []
    for ticker in top10_tickers:
        for row in get_ticker_subreddit_breakdown(ticker, since_ts):
            stacked_rows.append(
                {"ticker": ticker, "subreddit": row["subreddit"],
                 "count": row["mention_count"]}
            )

    if stacked_rows:
        df_stack = pd.DataFrame(stacked_rows)
        fig_stack = px.bar(
            df_stack,
            x="ticker",
            y="count",
            color="subreddit",
            barmode="stack",
            title=f"Top 10 Tickers by Subreddit ({time_window})",
            labels={"count": "Mentions", "ticker": "Ticker"},
        )
        fig_stack.update_layout(
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=380,
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
        )
        st.plotly_chart(fig_stack, use_container_width=True)
    else:
        st.info("Not enough data yet for the stacked breakdown.")
