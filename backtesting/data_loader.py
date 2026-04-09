"""
Odyssey v2 - Historical Data Loader for Backtesting
====================================================
Multi-source data loader for backtesting.
Supports: Cache -> AlphaVantage -> yfinance (fallback).

Supported symbols:
  - Forex:   EURUSD, GBPUSD, etc.
  - Indian:  NIFTY50, SENSEX, RELIANCE, INFY, etc.
  - Global:  SPX500, DAX40
"""

import os
import time
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'historical')
API_KEY = os.getenv('ALPHAVANTAGE_API_KEY')

# Symbol Mapping for yfinance
YF_SYMBOL_MAP = {
    'EURUSD': 'EURUSD=X',
    'GBPUSD': 'GBPUSD=X',
    'USDJPY': 'USDJPY=X',
    'XAUUSD': 'GC=F',
    'USDINR': 'USDINR=X',
    'NIFTY50': '^NSEI',
    'SENSEX': '^BSESN',
    'BANKNIFTY': '^NSEBANK',
    'RELIANCE': 'RELIANCE.NS',
    'INFY': 'INFY.NS',
    'SBIN': 'SBIN.NS',
    'TCS': 'TCS.NS',
    'HDFC': 'HDFCBANK.NS',
    'SPX500': '^GSPC',
    'DAX40': '^GDAXI',
}

# AlphaVantage Ticker Format
AV_EQUITY_MAP = {
    'RELIANCE': 'NSE:RELIANCE',
    'INFY': 'NSE:INFY',
    'TCS': 'NSE:TCS',
    'SBIN': 'NSE:SBIN',
    'HDFC': 'NSE:HDFCBANK',
}

INTERVAL_MAP = {
    'M1': '1min',
    'M5': '5min',
    'M15': '15min',
    'M30': '30min',
    'H1': '60min',
    'D1': 'daily',
}


class HistoricalDataLoader:
    def __init__(self, cache_dir: str = DATA_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.api_key = API_KEY

    def load(self, symbol: str, timeframe: str = 'D1',
             period_days: int = 365, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        Master load method with fallback logic:
        1. Cache
        2. AlphaVantage (premium-like quality)
        3. yfinance (as final fallback)
        """
        cache_path = os.path.join(self.cache_dir, f'{symbol}_{timeframe}.csv')

        # 1. Local Cache Check
        if use_cache and os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if (datetime.now() - mtime).days < 1:
                try:
                    df = pd.read_csv(cache_path, parse_dates=['time'])
                    df.set_index('time', inplace=True)
                    print(f"[DataLoader] {symbol} {timeframe} loaded from cache.")
                    return df
                except Exception:
                    pass

        # 2. AlphaVantage (AlphaVantage provides official/stable data)
        if self.api_key and self.api_key != "your_alphavantage_key_here":
            print(f"[DataLoader] Attempting {symbol} via AlphaVantage...")
            df_av = self._load_from_alphavantage(symbol, timeframe)
            if df_av is not None:
                df_av.to_csv(cache_path)
                return df_av

        # 3. yfinance Fallback
        return self._load_from_yfinance(symbol, timeframe, period_days)

    def _load_from_alphavantage(self, symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
        """Fetches data from AlphaVantage API."""
        if not self.api_key:
            return None

        # Determine function type: FX vs Equity
        is_forex = len(symbol) == 6 and any(cur in symbol for cur in ['EUR', 'USD', 'GBP', 'JPY', 'INR'])
        
        url = "https://www.alphavantage.co/query?"
        params = {"apikey": self.api_key}

        if is_forex:
            from_cur, to_cur = symbol[:3], symbol[3:]
            params["function"] = "FX_DAILY" if timeframe == 'D1' else "FX_INTRADAY"
            params["from_symbol"] = from_cur
            params["to_symbol"] = to_cur
            if timeframe != 'D1':
                params["interval"] = INTERVAL_MAP.get(timeframe, '60min')
        else:
            ticker = AV_EQUITY_MAP.get(symbol.upper(), symbol.upper())
            params["function"] = "TIME_SERIES_DAILY_ADJUSTED" if timeframe == 'D1' else "TIME_SERIES_INTRADAY"
            params["symbol"] = ticker
            if timeframe != 'D1':
                params["interval"] = INTERVAL_MAP.get(timeframe, '60min')

        try:
            r = requests.get(url, params=params, timeout=10)
            data = r.json()

            # Handle rate limiting
            if "Note" in data:
                print(f"[DataLoader] AlphaVantage Rate Limit: {data['Note']}")
                return None
            
            # Find the time series key
            ts_key = None
            for key in data.keys():
                if "Time Series" in key:
                    ts_key = key
                    break
            
            if not ts_key:
                print(f"[DataLoader] AlphaVantage error: {data.get('Error Message', 'Unknown format')}")
                return None

            df = pd.DataFrame.from_dict(data[ts_key], orient='index')
            df.index = pd.to_datetime(df.index)
            df.index.name = 'time'

            # Standardize column names
            df.columns = [c.split('. ')[1].lower() for c in df.columns]
            df = df.rename(columns={'adjusted close': 'close'})
            
            # Convert to float and take core columns
            cols_to_use = ['open', 'high', 'low', 'close', 'volume']
            df = df[cols_to_use].astype(float)
            df = df.sort_index()

            print(f"[DataLoader] Successfully fetched {symbol} from AlphaVantage.")
            return df
        except Exception as e:
            print(f"[DataLoader] AlphaVantage failed: {e}")
            return None

    def _load_from_yfinance(self, symbol: str, timeframe: str, period_days: int) -> Optional[pd.DataFrame]:
        """Original yfinance fallback method."""
        if not YFINANCE_AVAILABLE:
            return None

        ticker_sym = YF_SYMBOL_MAP.get(symbol.upper(), symbol.upper())
        yf_tf = {
            'M1': '1m', 'M5': '5m', 'M15': '15m', 'M30': '30m', 'H1': '1h', 'D1': '1d'
        }.get(timeframe, '1d')

        period = '5d' if yf_tf in ('1m', '5m') else '60d' if yf_tf in ('15m', '30m') else f'{period_days}d'

        try:
            ticker = yf.Ticker(ticker_sym)
            df = ticker.history(period=period, interval=yf_tf)
            if df is None or len(df) == 0:
                return None
            
            df.index.name = 'time'
            df = df.rename(columns={'Open': 'open', 'High': 'high', 'Low': 'low', 'Close': 'close', 'Volume': 'volume'})
            df = df[['open', 'high', 'low', 'close', 'volume']]
            df = df.dropna()
            
            # Cache the fallback result
            cache_path = os.path.join(self.cache_dir, f'{symbol}_{timeframe}.csv')
            df.to_csv(cache_path)
            
            print(f"[DataLoader] {symbol} loaded via yfinance fallback.")
            return df
        except Exception as e:
            print(f"[DataLoader] yfinance failed: {e}")
            return None

    def get_benchmark_returns(self, days: int = 365) -> Optional[np.ndarray]:
        """Fetch S&P 500 returns for Sharpe/IR benchmark."""
        df = self.load('SPX500', 'D1', period_days=days)
        if df is not None:
            return np.log(df['close'] / df['close'].shift(1)).dropna().values
        return None


if __name__ == '__main__':
    loader = HistoricalDataLoader()
    # Test fetch
    print(loader.load('EURUSD', 'D1'))

import os
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional

try:
    import yfinance as yf
    YFINANCE_AVAILABLE = True
except ImportError:
    YFINANCE_AVAILABLE = False

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data', 'historical')

SYMBOL_MAP = {
    # Forex (yfinance uses =X suffix)
    'EURUSD':    'EURUSD=X',
    'GBPUSD':    'GBPUSD=X',
    'USDJPY':    'USDJPY=X',
    'XAUUSD':    'GC=F',      # Gold Futures
    'USDINR':    'USDINR=X',

    # Indian Indices
    'NIFTY50':   '^NSEI',
    'SENSEX':    '^BSESN',
    'BANKNIFTY': '^NSEBANK',

    # Indian Large-caps
    'RELIANCE':  'RELIANCE.NS',
    'INFY':      'INFY.NS',
    'SBIN':      'SBIN.NS',
    'TCS':       'TCS.NS',
    'HDFC':      'HDFCBANK.NS',

    # Global Indices
    'SPX500':    '^GSPC',
    'DAX40':     '^GDAXI',
}

INTERVAL_MAP = {
    'M1':  '1m',
    'M5':  '5m',
    'M15': '15m',
    'M30': '30m',
    'H1':  '1h',
    'D1':  '1d',
}


class HistoricalDataLoader:
    """
    Downloads and caches OHLCV data for backtesting.
    Uses yfinance for all free data.
    """

    def __init__(self, cache_dir: str = DATA_DIR):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_symbol(self, odyssey_symbol: str) -> str:
        """Map Odyssey internal symbol to yfinance ticker."""
        return SYMBOL_MAP.get(odyssey_symbol.upper(), odyssey_symbol)

    def load(self, symbol: str, timeframe: str = 'D1',
             period_days: int = 365, use_cache: bool = True) -> Optional[pd.DataFrame]:
        """
        Load historical OHLCV data for a symbol.

        Args:
            symbol:      Odyssey symbol (e.g. 'EURUSD', 'NIFTY50')
            timeframe:   timeframe key (e.g. 'D1', 'H1', 'M15')
            period_days: how many days back to fetch
            use_cache:   if True, use locally cached CSV when fresh

        Returns:
            pd.DataFrame with columns: time, open, high, low, close, volume
        """
        cache_path = os.path.join(self.cache_dir, f'{symbol}_{timeframe}.csv')

        # Check cache freshness (< 1 day old)
        if use_cache and os.path.exists(cache_path):
            mtime = datetime.fromtimestamp(os.path.getmtime(cache_path))
            if (datetime.now() - mtime).days < 1:
                df = pd.read_csv(cache_path, parse_dates=['time'])
                df.set_index('time', inplace=True)
                print(f"[DataLoader] Loaded {symbol} {timeframe} from cache ({len(df)} rows)")
                return df

        if not YFINANCE_AVAILABLE:
            print("[DataLoader] yfinance not installed. Run: pip install yfinance")
            return None

        ticker_sym = self.get_symbol(symbol)
        interval = INTERVAL_MAP.get(timeframe, '1d')

        # yfinance period limits by interval
        if interval in ('1m', '5m'):
            period = '5d'
        elif interval in ('15m', '30m'):
            period = '60d'
        elif interval in ('1h',):
            period = '730d'
        else:
            period = f'{min(period_days, 3650)}d'

        try:
            ticker = yf.Ticker(ticker_sym)
            df = ticker.history(period=period, interval=interval, auto_adjust=True)

            if df is None or len(df) == 0:
                print(f"[DataLoader] No data returned for {symbol} ({ticker_sym})")
                return None

            df.index = pd.to_datetime(df.index)
            df.index.name = 'time'
            df = df.rename(columns={
                'Open': 'open', 'High': 'high',
                'Low': 'low', 'Close': 'close', 'Volume': 'volume'
            })[['open', 'high', 'low', 'close', 'volume']]

            df = df.dropna()
            df = df[df['close'] > 0]

            # Save to cache
            df.to_csv(cache_path)
            print(f"[DataLoader] Downloaded {symbol} {timeframe}: {len(df)} rows → {cache_path}")
            return df

        except Exception as e:
            print(f"[DataLoader] Error fetching {symbol}: {e}")
            return None

    def get_benchmark_returns(self, symbol: str = 'SPX500',
                               timeframe: str = 'D1',
                               period_days: int = 365) -> Optional[np.ndarray]:
        """
        Fetch daily log returns for a benchmark (default: S&P 500).
        Used for Information Ratio calculation.
        """
        df = self.load(symbol, timeframe, period_days)
        if df is None or 'close' not in df.columns:
            return None
        log_returns = np.log(df['close'] / df['close'].shift(1)).dropna().values
        return log_returns

    def list_cached(self):
        """List all locally cached datasets."""
        files = [f for f in os.listdir(self.cache_dir) if f.endswith('.csv')]
        print(f"[DataLoader] Cached files in {self.cache_dir}:")
        for f in files:
            fpath = os.path.join(self.cache_dir, f)
            size = os.path.getsize(fpath)
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime('%Y-%m-%d %H:%M')
            print(f"  {f} — {size//1024}KB — {mtime}")
        return files


if __name__ == '__main__':
    loader = HistoricalDataLoader()
    for sym in ['EURUSD', 'NIFTY50', 'XAUUSD']:
        df = loader.load(sym, 'D1', period_days=365)
        if df is not None:
            print(f"  {sym}: {len(df)} rows, {df.index[0]} → {df.index[-1]}")
