"""
Odyssey v2 - Unified Dual-Market Tick Receiver (Phase 7)
=========================================================
Subscribes to:
1. Fyers v3 DataSocket (Free Indian Market API)
2. Oanda v20 Pricing Stream (Fast Global Forex API)

Broadcasting ticks to Redis Streams for sub-millisecond chart updates.
"""

import os
import sys
import json
import time
import asyncio
import threading
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..', '..'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'shared', 'python'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'trading-executor', 'executor'))

from redis_client import RedisClient
from logger import OdysseyLogger
from broker_connector import FyersAPI, OandaAPI

logger = OdysseyLogger('tick-receiver')


class TickReceiverV2:
    def __init__(self):
        self.redis = RedisClient()
        self.fyers_api = FyersAPI()
        self.oanda_api = OandaAPI()
        
        # Mappings for Odyssey generic symbols
        self.INDIA_MAP = {
            'NSE:NIFTY50-INDEX': 'NIFTY50',
            'NSE:NIFTYBANK-INDEX': 'BANKNIFTY',
            'NSE:RELIANCE-EQ': 'RELIANCE',
            'NSE:INFY-EQ': 'INFY'
        }
        self.FOREX_MAP = {
            'XAU_USD': 'XAUUSD',
            'EUR_USD': 'EURUSD',
            'GBP_USD': 'GBPUSD',
            'USD_JPY': 'USDJPY'
        }
        
        self.active_universe = list(self.INDIA_MAP.keys()) + list(self.FOREX_MAP.keys())
        self._running = False

    # -------------------------------------------------------------------------
    # FYERS (INDIA) WEBSOCKET
    # -------------------------------------------------------------------------
    def _run_fyers_stream(self):
        """Streams Indian market data via Fyers v3 DataSocket."""
        try:
            from fyers_apiv3.FyersWebsocket import data_ws
            
            if not self.fyers_api.initialize():
                logger.warning("Fyers not reachable. Indian Ticker Offline.")
                return

            def on_message(message):
                # Fyers tick format mapping
                symbol = message.get('symbol')
                price = message.get('ltp')
                if symbol and price:
                    generic = self.INDIA_MAP.get(symbol, symbol)
                    self.redis.set_cache(f"ticks:{generic}", price, ttl=60)
                    # Pipeline to Stream for ML
                    self.redis.client.xadd(f"market:ticks:{generic}", {'price': str(price)}, maxlen=1000)

            def on_open():
                logger.info("Fyers DataSocket Connected. Subscribing to India Universe...")
                fyers_socket.subscribe(symbols=list(self.INDIA_MAP.keys()), data_type="SymbolData")

            access_token = f"{self.fyers_api.client_id}:{self.fyers_api.access_token}"
            fyers_socket = data_ws.FyersDataSocket(
                access_token=access_token,
                log_path="",
                litemode=False,
                reconnect=True,
                on_connect=on_open,
                on_message=on_message
            )
            fyers_socket.connect()
            
        except Exception as e:
            logger.error(f"Fyers Stream Error: {e}")

    # -------------------------------------------------------------------------
    # OANDA (FOREX) STREAMING
    # -------------------------------------------------------------------------
    def _run_oanda_stream(self):
        """Streams Global Forex via Oanda v20 REST-Streaming API."""
        import requests
        
        # Oanda Streaming Domain logic
        env = os.getenv("OANDA_ENVIRONMENT", "practice")
        stream_domain = "stream-fxtrade.oanda.com" if env == "live" else "stream-fxpractice.oanda.com"
        account_id = self.oanda_api.account_id
        
        if not self.oanda_api.initialize():
            logger.warning("Oanda not reachable. Forex Ticker Offline.")
            return

        instruments = ",".join(self.FOREX_MAP.keys())
        url = f"https://{stream_domain}/v3/accounts/{account_id}/pricing/stream?instruments={instruments}"
        headers = self.oanda_api.headers
        
        logger.info(f"Oanda Pricing Stream Initiated for: {instruments}")
        
        try:
            with requests.get(url, headers=headers, stream=True, timeout=None) as response:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode('utf-8'))
                        if data.get('type') == 'PRICE':
                            symbol = data.get('instrument')
                            price = float(data.get('closeoutBid')) # Use bid as representative price
                            generic = self.FOREX_MAP.get(symbol, symbol)
                            self.redis.set_cache(f"ticks:{generic}", price, ttl=60)
                            # Pipeline to Stream
                            self.redis.client.xadd(f"market:ticks:{generic}", {'price': str(price)}, maxlen=1000)
        except Exception as e:
            logger.error(f"Oanda Stream Error: {e}")

    # -------------------------------------------------------------------------
    # MOCK (SIMULATION) FALLBACK
    # -------------------------------------------------------------------------
    def _run_mock_stream(self):
        """Fallback simulation if no broker keys are provided."""
        logger.info("Initializing Professional GBM Simulator (Simulation Mode)...")
        import random
        # Initialize Forex prices
        prices = {
            'XAUUSD': 1950.0, 'EURUSD': 1.0850, 'GBPUSD': 1.2500,
            'USDJPY': 150.00, 'DAX40': 17000.0, 'SPX500': 5000.0
        }
        
        while self._running:
            for symbol, price in prices.items():
                vol = 0.0001 if symbol in ('EURUSD', 'GBPUSD') else 0.5
                change = price * random.gauss(0, vol)
                prices[symbol] += change
                self.redis.set_cache(f"ticks:{symbol}", prices[symbol], ttl=60)
            time.sleep(1)

    def start(self):
        """Launch dual-orchestration."""
        self._running = True
        logger.info("ODYSSEY v2 — TICK RECEIVER RE-LOADED [ACTIVE]")
        
        # Start India (Fyers) Thread
        if self.fyers_api.access_token:
            threading.Thread(target=self._run_fyers_stream, daemon=True).start()
        
        # Start Forex (Oanda) Thread 
        if self.oanda_api.access_token:
            threading.Thread(target=self._run_oanda_stream, daemon=True).start()
            
        # Passive Mock thread if universe is empty (Demo safety)
        if not self.fyers_api.access_token and not self.oanda_api.access_token:
            self._run_mock_stream()
        else:
            # Keep main thread alive
            while self._running:
                time.sleep(1)

if __name__ == "__main__":
    receiver = TickReceiverV2()
    try:
        receiver.start()
    except KeyboardInterrupt:
        logger.info("Tick Receiver Shutdown requested.")
