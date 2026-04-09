"""
Odyssey v2 - Sentiment Analysis Microservice
Scrapes financial news → Scores with FinBERT → Aggregates per-pair → Publishes to Kafka/Redis
"""

import os
import sys
import time
import threading
from datetime import datetime
from typing import Dict
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

load_dotenv()

# Import paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")

sys.path.insert(0, SHARED_PYTHON)
sys.path.insert(0, CURRENT_DIR)

from redis_client import RedisClient
from kafka_utils import KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger
from metrics import metrics

from scrapers.news_scraper import NewsScraper
from models.finbert_scorer import FinBERTScorer
from aggregators.sentiment_aggregator import SentimentAggregator

logger = OdysseyLogger('sentiment-service')


class SentimentService:
    """
    Real-time sentiment analysis service.
    Runs a periodic loop: scrape → score → aggregate → publish.
    """

    def __init__(self, scrape_interval: int = 120):
        """
        Args:
            scrape_interval: seconds between scrape cycles (default: 2 min)
        """
        self.scrape_interval = scrape_interval
        self.redis = RedisClient()
        self.kafka_producer = KafkaProducerClient()

        metrics.start_server(8006)

        # Core components
        self.scraper = NewsScraper(max_age_hours=4, max_headlines=50)
        self.scorer = FinBERTScorer()
        self.aggregator = SentimentAggregator(ewma_alpha=0.3, decay_hours=4.0)

        self._running = False
        self._cycle_count = 0

        logger.info("Sentiment Service initialized")

    def _load_model(self):
        """Load FinBERT model (first-time download may take a few minutes)."""
        logger.info("Loading FinBERT model (first run downloads ~400MB)...")
        self.redis.set_cache("sentiment:status", "LOADING", ttl=3600)
        
        if self.scorer.load():
            logger.info("FinBERT model loaded successfully")
            self.redis.set_cache("sentiment:status", "LIVE", ttl=3600)
        else:
            logger.warning("FinBERT failed to load — using neutral fallback scores")
            self.redis.set_cache("sentiment:status", "FALLBACK", ttl=3600)

    def _run_cycle(self):
        """Execute one scrape→score→aggregate→publish cycle."""
        self._cycle_count += 1
        cycle_start = time.time()

        # 1. Scrape headlines
        headlines = self.scraper.scrape_all()
        if not headlines:
            logger.info(f"Cycle {self._cycle_count}: no new headlines")
            return

        logger.info(f"Cycle {self._cycle_count}: scraped {len(headlines)} new headlines")

        # 2. Score with FinBERT
        headline_texts = [h.title for h in headlines]
        scores = self.scorer.score_batch(headline_texts)

        # 3. Aggregate per currency
        for item, score in zip(headlines, scores):
            self.aggregator.update(
                headline=item.title,
                net_score=score['net_score'],
                label=score['label'],
            )

            # Log significant sentiment
            if abs(score['net_score']) > 0.5:
                emoji = '🟢' if score['net_score'] > 0 else '🔴'
                logger.info(f"{emoji} [{score['label']}] {item.title[:80]}... (score={score['net_score']:.3f})")
                
                # Send alert for major sentiment shifts
                self.kafka_producer.send(
                    KafkaTopics.ALERTS,
                    {
                        "type": "SENTIMENT_SHIFT",
                        "score": score['net_score'],
                        "asset": score['label'],
                        "details": item.title
                    },
                    key="SENTIMENT"
                )

        # 4. Get pair sentiments and publish
        summary = self.aggregator.get_summary()
        pair_sentiments = summary['pairs']

        # Cache in Redis for ML engine
        for pair, score in pair_sentiments.items():
            self.redis.set_cache(f"sentiment:{pair}", {
                'score': score,
                'timestamp': datetime.utcnow().isoformat(),
            }, ttl=600)

        # Cache full summary
        self.redis.set_cache("sentiment:summary", summary, ttl=600)

        # Publish to Kafka
        self.kafka_producer.send(
            KafkaTopics.SENTIMENT_SCORES,
            {
                'type': 'sentiment_update',
                'pairs': pair_sentiments,
                'currencies': summary['currencies'],
                'headlines_processed': len(headlines),
                'timestamp': datetime.utcnow().isoformat(),
            },
            key='SENTIMENT',
        )

        elapsed = time.time() - cycle_start
        logger.info(
            f"Cycle {self._cycle_count} complete in {elapsed:.1f}s — "
            f"{len(headlines)} headlines scored, "
            f"sentiments: {', '.join(f'{p}={s:+.3f}' for p, s in pair_sentiments.items() if abs(s) > 0.01)}"
        )
        metrics.events_processed.labels(service_name='sentiment-service', event_type='scrape_cycle').inc()

    def start(self):
        """Start the periodic scrape-score-publish loop."""
        logger.info("ODYSSEY SENTIMENT ENGINE — REAL-TIME NEWS ANALYSIS STARTED")
        logger.info(f"  Scrape interval: {self.scrape_interval}s")
        logger.info(f"  Feeds: {len(self.scraper.feeds)}")
        logger.info(f"  Model: {self.scorer.MODEL_NAME}")

        self._load_model()
        self._running = True

        while self._running:
            try:
                self._run_cycle()
                time.sleep(self.scrape_interval)
            except KeyboardInterrupt:
                logger.info("Sentiment service stopped by user")
                break
            except Exception as e:
                logger.error(f"Cycle error: {e}")
                time.sleep(30)

    def stop(self):
        """Stop the service."""
        self._running = False


# MAIN EXECUTION
if __name__ == "__main__":
    service = SentimentService(scrape_interval=120)
    service.start()
