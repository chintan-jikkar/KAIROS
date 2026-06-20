"""Recent headlines for a symbol — via yfinance, no separate API key needed."""
from datetime import datetime

import streamlit as st
import yfinance as yf


@st.cache_data(ttl=600)
def fetch_news(ticker: str, limit: int = 5) -> list[dict]:
    try:
        items = yf.Ticker(ticker).news or []
    except Exception:
        return []

    parsed = []
    for raw in items[:limit]:
        content = raw.get("content", {})
        pub = content.get("pubDate")
        try:
            pub_dt = datetime.strptime(pub, "%Y-%m-%dT%H:%M:%SZ") if pub else None
        except ValueError:
            pub_dt = None
        parsed.append({
            "title": content.get("title", ""),
            "summary": content.get("summary", ""),
            "provider": (content.get("provider") or {}).get("displayName", ""),
            "url": (content.get("canonicalUrl") or {}).get("url", ""),
            "published": pub_dt.strftime("%b %d, %H:%M") if pub_dt else "",
        })
    return parsed


def render_news_list(ticker: str, limit: int = 5):
    items = fetch_news(ticker, limit)
    if not items:
        st.caption("No recent headlines found.")
        return

    for item in items:
        st.markdown(
            f"""
            <div style="padding:9px 0;border-bottom:0.5px solid var(--border-glass);">
                <a href="{item['url']}" target="_blank" style="color:var(--text-primary);
                   font-size:12.5px;font-weight:500;text-decoration:none;">{item['title']}</a>
                <p style="font-size:10.5px;color:var(--text-muted);margin:3px 0 0;">
                    {item['provider']} &middot; {item['published']}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
