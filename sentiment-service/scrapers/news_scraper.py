"""
Odyssey v2 - Financial News RSS Scraper
Scrapes headlines from multiple financial RSS feeds with deduplication.
"""

import hashlib
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field

try:
    import feedparser
except ImportError:
    feedparser = None


@dataclass
class NewsItem:
    """Represents a single news headline."""
    title: str
    source: str
    url: str
    published: str
    hash_id: str = ""
    timestamp: float = 0.0

    def __post_init__(self):
        if not self.hash_id:
            self.hash_id = hashlib.md5(self.title.encode()).hexdigest()[:12]
        if not self.timestamp:
            self.timestamp = time.time()


class NewsScraper:
    """
    Multi-source RSS feed scraper for financial news.
    Supports deduplication and configurable staleness filtering.
    """

    # Public RSS feeds for financial/forex news
    DEFAULT_FEEDS = {
        # GLOBAL FOREX
        'investing_forex': 'https://www.investing.com/rss/news_14.rss',
        'fxstreet': 'https://www.fxstreet.com/rss',
        'dailyfx': 'https://www.dailyfx.com/feeds/market-news',
        'forexlive': 'https://www.forexlive.com/feed',
        
        # INDIAN MARKETS
        'et_markets': 'https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms',
        'livemint_markets': 'https://www.livemint.com/rss/markets',
        'ndtv_profit': 'https://www.ndtv.com/business/latest/rss',
        'equitymaster': 'https://www.equitymaster.com/rss/',
        
        # SOCIAL / RETAIL SENTIMENT (REDDIT & SIMULATED STOCKTWITS)
        'reddit_forex': 'https://www.reddit.com/r/forex/.rss',
        'reddit_streetbets': 'https://www.reddit.com/r/wallstreetbets/.rss',
        'reddit_streetbets_in': 'https://www.reddit.com/r/IndianStreetBets/.rss',
        'social_sentiment_global': 'https://news.google.com/rss/search?q=stocktwits+sentiment&hl=en',
    }

    def __init__(self,
                 feeds: Dict[str, str] = None,
                 max_age_hours: int = 4,
                 max_headlines: int = 100):
        """
        Args:
            feeds: {name: rss_url} mapping of feeds to scrape
            max_age_hours: ignore headlines older than this
            max_headlines: max headlines to return per scrape cycle
        """
        if feedparser is None:
            raise ImportError("feedparser required: pip install feedparser")

        self.feeds = feeds or self.DEFAULT_FEEDS
        self.max_age_hours = max_age_hours
        self.max_headlines = max_headlines
        self._seen_hashes: Set[str] = set()
        self._max_seen = 5000  # cap dedup cache

    def scrape_feed(self, feed_name: str, feed_url: str) -> List[NewsItem]:
        """Scrape a single RSS feed and return new headlines."""
        items = []
        try:
            feed = feedparser.parse(feed_url)

            if feed.bozo and not feed.entries:
                return items

            for entry in feed.entries:
                title = entry.get('title', '').strip()
                if not title or len(title) < 10:
                    continue

                link = entry.get('link', '')

                # Parse published date
                published = ''
                if hasattr(entry, 'published_parsed') and entry.published_parsed:
                    try:
                        pub_dt = datetime(*entry.published_parsed[:6])
                        age = datetime.utcnow() - pub_dt
                        if age > timedelta(hours=self.max_age_hours):
                            continue
                        published = pub_dt.isoformat()
                    except Exception:
                        published = datetime.utcnow().isoformat()
                else:
                    published = datetime.utcnow().isoformat()

                item = NewsItem(
                    title=title,
                    source=feed_name,
                    url=link,
                    published=published,
                )

                # Deduplicate
                if item.hash_id not in self._seen_hashes:
                    self._seen_hashes.add(item.hash_id)
                    items.append(item)

        except Exception:
            pass

        return items

    def scrape_all(self) -> List[NewsItem]:
        """Scrape all configured feeds and return deduplicated headlines."""
        all_items = []

        for name, url in self.feeds.items():
            items = self.scrape_feed(name, url)
            all_items.extend(items)

        # Trim dedup cache if too large
        if len(self._seen_hashes) > self._max_seen:
            self._seen_hashes = set(list(self._seen_hashes)[-self._max_seen // 2:])

        # Sort by timestamp (newest first) and cap
        all_items.sort(key=lambda x: x.timestamp, reverse=True)
        return all_items[:self.max_headlines]

    def get_stats(self) -> Dict:
        """Return scraper statistics."""
        return {
            'feeds_configured': len(self.feeds),
            'unique_headlines_seen': len(self._seen_hashes),
            'max_age_hours': self.max_age_hours,
        }
