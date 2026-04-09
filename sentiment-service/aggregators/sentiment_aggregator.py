"""
Odyssey v2 - Sentiment Aggregator
Maps headlines to currencies and computes per-pair EWMA sentiment scores.
"""

import re
import time
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Tuple


class SentimentAggregator:
    """
    Aggregates headline sentiment scores into per-currency and per-pair
    exponentially-weighted moving averages.
    """

    # Keyword → Currency mapping for headline classification
    CURRENCY_KEYWORDS = {
        'USD': [
            'dollar', 'usd', 'fed', 'federal reserve', 'fomc', 'powell',
            'us economy', 'nonfarm', 'payroll', 'cpi', 'ppi', 'gdp',
            'treasury', 'wall street', 'american', 'us inflation',
        ],
        'EUR': ['euro', 'eur', 'ecb', 'lagarde', 'eurozone', 'european central'],
        'GBP': ['pound', 'gbp', 'boe', 'bank of england', 'bailey', 'uk economy'],
        'JPY': ['yen', 'jpy', 'boj', 'bank of japan', 'ueda', 'japan'],
        'XAU': ['gold', 'xau', 'bullion', 'precious metal', 'safe haven'],
        
        # INDIAN MARKET
        'INR': [
            'rupee', 'inr', 'rbi', 'shaktikanta das', 'indian economy',
            'nifty', 'sensex', 'bse', 'nse', 'adani', 'reliance',
            'tata', 'infosys', 'hdfc', 'modi government', 'fii', 'dii',
            'dalal street', 'indian markets',
        ],
    }

    # Trading pairs to compute sentiment for
    PAIRS = [
        'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD',
        # INDIAN PAIRS / INDICES
        'USDINR', 'NIFTY50', 'SENSEX', 'BANKNIFTY'
    ]

    def __init__(self, ewma_alpha: float = 0.3, decay_hours: float = 4.0):
        """
        Args:
            ewma_alpha: smoothing factor for EWMA (0-1, higher = more reactive)
            decay_hours: how quickly old sentiment fades
        """
        self.ewma_alpha = ewma_alpha
        self.decay_hours = decay_hours

        # Per-currency sentiment: {currency: {'score': float, 'count': int, 'last_update': float}}
        self._currency_sentiment: Dict[str, Dict] = {}

        # Raw headline scores buffer for analysis
        self._recent_scores: List[Dict] = []
        self._max_recent = 200

    def detect_currencies(self, headline: str) -> List[str]:
        """Detect which currencies a headline is about."""
        headline_lower = headline.lower()
        detected = []

        for currency, keywords in self.CURRENCY_KEYWORDS.items():
            for kw in keywords:
                if kw in headline_lower:
                    detected.append(currency)
                    break

        return detected

    def update(self, headline: str, net_score: float, label: str):
        """
        Update sentiment with a new scored headline.

        Args:
            headline: the news headline text
            net_score: FinBERT net score (positive - negative), range [-1, 1]
            label: 'BULLISH', 'BEARISH', or 'NEUTRAL'
        """
        currencies = self.detect_currencies(headline)

        if not currencies:
            return

        now = time.time()

        for currency in currencies:
            if currency not in self._currency_sentiment:
                self._currency_sentiment[currency] = {
                    'score': 0.0,
                    'count': 0,
                    'last_update': now,
                }

            state = self._currency_sentiment[currency]

            # Apply time decay to existing score
            hours_elapsed = (now - state['last_update']) / 3600.0
            decay = max(0.01, 1.0 - hours_elapsed / self.decay_hours)
            state['score'] *= decay

            # EWMA update
            state['score'] = self.ewma_alpha * net_score + (1 - self.ewma_alpha) * state['score']
            state['count'] += 1
            state['last_update'] = now

        # Buffer for analysis
        self._recent_scores.append({
            'headline': headline,
            'score': net_score,
            'label': label,
            'currencies': currencies,
            'timestamp': now,
        })
        if len(self._recent_scores) > self._max_recent:
            self._recent_scores = self._recent_scores[-self._max_recent // 2:]

    def get_currency_sentiment(self, currency: str) -> float:
        """Get current EWMA sentiment for a currency (range: -1 to +1)."""
        if currency not in self._currency_sentiment:
            return 0.0

        state = self._currency_sentiment[currency]
        # Apply time decay
        hours_elapsed = (time.time() - state['last_update']) / 3600.0
        decay = max(0.01, 1.0 - hours_elapsed / self.decay_hours)
        return state['score'] * decay

    def get_pair_sentiment(self, pair: str) -> float:
        """
        Get sentiment for a trading pair.
        For EURUSD: sentiment = EUR_sentiment - USD_sentiment
        For XAUUSD: sentiment = XAU_sentiment - USD_sentiment

        Returns: float in range [-1, +1]
            Positive = bullish for the pair (buy signal)
            Negative = bearish for the pair (sell signal)
        """
        # Parse pair into base/quote
        if pair in ('XAUUSD',):
            base, quote = pair[:3], pair[3:]
        elif len(pair) == 6:
            base, quote = pair[:3], pair[3:]
        else:
            return 0.0

        base_sent = self.get_currency_sentiment(base)
        quote_sent = self.get_currency_sentiment(quote)

        return base_sent - quote_sent

    def get_all_pair_sentiments(self) -> Dict[str, float]:
        """Get sentiment scores for all configured trading pairs."""
        return {pair: self.get_pair_sentiment(pair) for pair in self.PAIRS}

    def get_summary(self) -> Dict:
        """Get full sentiment summary for dashboard/logging."""
        currencies = {}
        for ccy in self.CURRENCY_KEYWORDS:
            score = self.get_currency_sentiment(ccy)
            state = self._currency_sentiment.get(ccy, {})
            currencies[ccy] = {
                'score': round(score, 4),
                'count': state.get('count', 0),
                'label': 'BULLISH' if score > 0.1 else ('BEARISH' if score < -0.1 else 'NEUTRAL'),
            }

        pairs = self.get_all_pair_sentiments()
        
        # Include last 10 headlines with their scores for the UI
        recent = []
        for s in self._recent_scores[-10:]:
            recent.append({
                'headline': s['headline'],
                'score': round(s['score'], 3),
                'label': s['label'],
                'timestamp': datetime.fromtimestamp(s['timestamp']).isoformat()
            })

        return {
            'timestamp': datetime.utcnow().isoformat(),
            'currencies': currencies,
            'pairs': {k: round(v, 4) for k, v in pairs.items()},
            'headlines_processed': sum(s.get('count', 0) for s in self._currency_sentiment.values()),
            'recent_headlines': recent[::-1] # Newest first
        }
