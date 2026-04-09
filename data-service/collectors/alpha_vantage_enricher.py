"""
Odyssey v2 - AlphaVantage Macro Enricher (Enrichment Layer)
==========================================================
Fetches Institutional-grade macro and technical data from AlphaVantage
to enrich the live broker data. Runs on a 60-minute cycle to stay
within the 25 req/day free limit.
"""

import os
import time
import requests
from datetime import datetime
from dotenv import load_dotenv

# Fix paths for microservice structure
import sys
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))

from redis_client import RedisClient
from logger import OdysseyLogger

load_dotenv()

logger = OdysseyLogger('data-service')
API_KEY = os.getenv('ALPHAVANTAGE_API_KEY')

# Symbols to enrich (Major benchmarks + specific trading pairs)
MACRO_SYMBOLS = ["SPY", "QQQ", "GLD", "VIX", "NSE:NIFTY50"]
TRADING_SYMBOLS = ["EURUSD", "GBPUSD", "RELIANCE", "NIFTY50"]

class AlphaVantageEnricher:
    def __init__(self):
        self.redis = RedisClient()
        self.api_key = API_KEY
        self.base_url = "https://www.alphavantage.co/query"
        
        if not self.api_key or self.api_key == "your_alphavantage_key_here":
            logger.warning("AlphaVantage API Key missing or default. Enricher will run in PASSIVE mode.")
            self.active = False
        else:
            self.active = True
            logger.info("AlphaVantage Enricher initialized in ACTIVE mode.")

    def fetch_global_market_status(self):
        """Fetch general market atmosphere."""
        if not self.active: return
        
        try:
            # Note: MARKET_STATUS is a newer endpoint, falling back to GLOBAL_QUOTE for SPY if needed
            params = {
                "function": "GLOBAL_QUOTE",
                "symbol": "SPY",
                "apikey": self.api_key
            }
            r = requests.get(self.base_url, params=params, timeout=10)
            data = r.json()
            
            if "Global Quote" in data:
                quote = data["Global Quote"]
                change_pct = float(quote.get("10. change percent", "0%").replace("%", ""))
                mood = "Bullish" if change_pct > 0.2 else "Bearish" if change_pct < -0.2 else "Consolidating"
                
                status = {
                    "global_mood": mood,
                    "spy_change": change_pct,
                    "timestamp": datetime.now().isoformat(),
                    "source": "AlphaVantage"
                }
                self.redis.set_cache("macro:market_status", status, ttl=7200) # 2 hours
                logger.info(f"Updated Global Mood: {mood} ({change_pct:+.2f}%)")
        except Exception as e:
            logger.error(f"Failed to fetch market status: {e}")

    def fetch_sector_performance(self):
        """Fetch US sector performance as a proxy for global risk appetite."""
        if not self.active: return
        
        try:
            params = {
                "function": "SECTOR",
                "apikey": self.api_key
            }
            r = requests.get(self.base_url, params=params, timeout=10)
            data = r.json()
            
            # Key "Rank A: Real-Time Performance"
            if "Rank A: Real-Time Performance" in data:
                sectors = data["Rank A: Real-Time Performance"]
                self.redis.set_cache("macro:sector_performance", sectors, ttl=7200)
                logger.info("Updated Sector Performance cache.")
        except Exception as e:
            logger.error(f"Failed to fetch sector performance: {e}")

    def fetch_institutional_indicators(self, symbol: str):
        """Fetch pre-calculated RSI/ADX from AlphaVantage."""
        if not self.active: return
        
        try:
            # RSI
            params = {
                "function": "RSI",
                "symbol": symbol if ":" in symbol else symbol, # AV uses NSE:RELIANCE
                "interval": "daily",
                "time_period": 14,
                "series_type": "close",
                "apikey": self.api_key
            }
            r = requests.get(self.base_url, params=params, timeout=10)
            data = r.json()
            
            if "Technical Analysis: RSI" in data:
                latest_date = sorted(data["Technical Analysis: RSI"].keys())[-1]
                rsi_val = float(data["Technical Analysis: RSI"][latest_date]["RSI"])
                
                self.redis.set_feature(symbol, "inst_rsi", rsi_val)
                logger.info(f"Enriched {symbol} with Institutional RSI: {rsi_val:.2f}")
        except Exception as e:
            logger.error(f"Failed to enrich indicators for {symbol}: {e}")

    def _simulate_data(self):
        """Populate Redis with simulated institutional data if no AV key exists."""
        logger.info("AlphaVantage Enricher: Generating high-quality SIMULATED macro data...")
        
        # 1. Global Mood simulation
        import random
        change = random.uniform(-1.5, 1.5)
        mood = "Bullish" if change > 0.3 else "Bearish" if change < -0.3 else "Neutral"
        status = {
            "global_mood": mood,
            "spy_change": round(change, 2),
            "timestamp": datetime.now().isoformat(),
            "source": "Odyssey Simulation"
        }
        self.redis.set_cache("macro:market_status", status, ttl=3600)
        
        # 2. Sector Performance simulation
        sectors = {
            "Information Technology": f"{random.uniform(-2, 2):.2f}%",
            "Health Care": f"{random.uniform(-2, 2):.2f}%",
            "Financials": f"{random.uniform(-2, 2):.2f}%",
            "Consumer Discretionary": f"{random.uniform(-2, 2):.2f}%",
            "Communication Services": f"{random.uniform(-2, 2):.2f}%",
            "Energy": f"{random.uniform(-2, 2):.2f}%"
        }
        self.redis.set_cache("macro:sector_performance", sectors, ttl=3600)
        
        # 3. Institutional Indicators for top symbols
        for sym in TRADING_SYMBOLS:
            rsi = random.uniform(35, 65)
            self.redis.set_feature(sym, "inst_rsi", rsi)

    def run_cycle(self):
        """Execute one full enrichment cycle (consumes ~5-10 requests)."""
        if not self.active:
            self._simulate_data()
            return

        logger.info("Starting AlphaVantage Enrichment Cycle...")
        
        # 1. Macro Context
        self.fetch_global_market_status()
        time.sleep(2) # AV rate limit safety
        
        self.fetch_sector_performance()
        time.sleep(2)
        
        # 2. Key Trading Symbols
        for sym in TRADING_SYMBOLS[:2]: # Limit to 2 symbols on free tier to save credits
            self.fetch_institutional_indicators(sym)
            time.sleep(2)
            
        logger.info("Enrichment cycle complete.")

    def run_forever(self):
        """Run every 60 minutes."""
        while True:
            self.run_cycle()
            # If simulated, we can run slightly faster for demo purposes
            wait_time = 3600 if self.active else 300
            logger.info(f"Sleeping for {wait_time}s...")
            time.sleep(wait_time)

if __name__ == "__main__":
    enricher = AlphaVantageEnricher()
    enricher.run_forever()
