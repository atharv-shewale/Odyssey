"""
Odyssey v2 - Free Market Data Collector (yfinance)
Fetches Indian Market Indices and Large-caps using the free YFinance API.
"""

import time
import json
import yfinance as yf
from datetime import datetime
from typing import List, Dict
from logger import OdysseyLogger

logger = OdysseyLogger('yfinance-collector')

class YFinanceCollector:
    """
    Scrapes free real-time-ish data for Indian Markets.
    Symbols: ^NSEI (Nifty 50), ^BSESN (Sensex), RELIANCE.NS, etc.
    """

    INDIAN_SYMBOLS = [
        '^NSEI', '^BSESN', '^NSEBANK', 
        'RELIANCE.NS', 'TCS.NS', 'HDFCBANK.NS', 
        'INFY.NS', 'ICICIBANK.NS', 'SBIN.NS', 'BHARTIARTL.NS',
        'ITC.NS', 'LTIM.NS', 'KOTAKBANK.NS'
    ]

    def __init__(self, redis_client):
        self.redis = redis_client
        self.running = True

    def fetch_latest(self):
        """Fetch and cache latest prices for Indian markets."""
        while self.running:
            try:
                for symbol in self.INDIAN_SYMBOLS:
                    ticker = yf.Ticker(symbol)
                    # Get fast_info or history(period='1d')
                    data = ticker.history(period='1d', interval='1m').iloc[-1]
                    
                    price_data = {
                        'symbol': symbol.replace('^', '').replace('.NS', ''),
                        'price': float(data['Close']),
                        'high': float(data['High']),
                        'low': float(data['Low']),
                        'open': float(data['Open']),
                        'volume': int(data['Volume']),
                        'timestamp': datetime.utcnow().isoformat()
                    }
                    
                    # Cache for Gateway/ML
                    self.redis.set_cache(f"market:{price_data['symbol']}:latest", price_data)
                    logger.info(f"Updated {price_data['symbol']}: {price_data['price']}")

                time.sleep(60) # Free API - poll every minute to avoid rate limits
            except Exception as e:
                logger.error(f"YFinance Error: {e}")
                time.sleep(10)

    def stop(self):
        self.running = False

if __name__ == "__main__":
    from redis_client import RedisClient
    r = RedisClient()
    collector = YFinanceCollector(r)
    collector.fetch_latest()
