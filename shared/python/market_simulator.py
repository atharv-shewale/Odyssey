import time
import random
import math
import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta

class PriceProvider(ABC):
    """Abstract base class for all simulated market data sources."""
    
    @abstractmethod
    def get_next_tick(self, symbol: str) -> Dict[str, Any]:
        """Fetch the next price event for the given symbol."""
        pass

    @abstractmethod
    def reset(self):
        """Reset the simulation state."""
        pass

class StochasticEngine(PriceProvider):
    """
    Implements Geometric Brownian Motion (GBM) for realistic price paths.
    Formula: S(t) = S(0) * exp((mu - 0.5*sigma^2)*t + sigma*W(t))
    """
    
    def __init__(self, 
                 base_prices: Dict[str, float] = None, 
                 volatility: float = 0.02, 
                 drift: float = 0.0001,
                 dt: float = 1.0): # 1 second steps
        self.prices = base_prices or {"GOLD": 2000.0, "EURUSD": 1.0850}
        self.volatility = volatility # Annualized or step-wise sigma
        self.drift = drift # Annualized or step-wise mu
        self.dt = dt
        self.initial_prices = self.prices.copy()
        
    def get_next_tick(self, symbol: str) -> Dict[str, Any]:
        if symbol not in self.prices:
            self.prices[symbol] = 100.0 # Default starting price
            
        current_price = self.prices[symbol]
        
        # Weiner process (Standard Normal)
        z = np.random.standard_normal()
        
        # GBM Discretized Step
        # S_new = S_old * exp((drift - 0.5 * vol^2) * dt + vol * sqrt(dt) * z)
        exponent = (self.drift - 0.5 * self.volatility**2) * self.dt + self.volatility * math.sqrt(self.dt) * z
        new_price = current_price * math.exp(exponent)
        
        self.prices[symbol] = new_price
        
        return {
            "symbol": symbol,
            "price": round(new_price, 5),
            "timestamp": datetime.now().isoformat(),
            "source": "stochastic_gbm"
        }

    def reset(self):
        self.prices = self.initial_prices.copy()

class HistoricalReplayEngine(PriceProvider):
    """
    Replays historical bars/ticks from a file or QuestDB.
    """
    
    def __init__(self, data_file: str = None, df: Any = None):
        self.data_file = data_file
        self.df = df
        self.cursor = 0
        
    def load_from_csv(self, file_path: str):
        import pandas as pd
        self.df = pd.read_csv(file_path)
        self.reset()
        
    def get_next_tick(self, symbol: str) -> Dict[str, Any]:
        if self.df is None or self.cursor >= len(self.df):
            return {}
            
        row = self.df.iloc[self.cursor]
        self.cursor += 1
        
        # Map common OHLC columns to a single price tick
        price = row.get('close', row.get('price', 0))
        ts = row.get('timestamp', row.get('time', datetime.now().isoformat()))
        
        return {
            "symbol": symbol,
            "price": float(price),
            "timestamp": str(ts),
            "source": "historical_replay"
        }

    def reset(self):
        self.cursor = 0

class HybridSimulator(PriceProvider):
    """
    Wraps a PriceProvider and injects real-world noise (spread, spikes, slippage).
    """
    
    def __init__(self, provider: PriceProvider, spread_pct: float = 0.0001):
        self.provider = provider
        self.spread_pct = spread_pct # 0.01% default spread
        
    def get_next_tick(self, symbol: str) -> Dict[str, Any]:
        tick = self.provider.get_next_tick(symbol)
        if not tick: return {}
        
        mid = tick['price']
        spread = mid * self.spread_pct
        
        # Inject occasional random spikes (0.5% chance)
        if random.random() < 0.005:
            spike_factor = random.uniform(0.005, 0.02) # 0.5% to 2% spike
            if random.random() > 0.5:
                mid *= (1 + spike_factor)
            else:
                mid *= (1 - spike_factor)
        
        return {
            **tick,
            "bid": round(mid - spread/2, 5),
            "ask": round(mid + spread/2, 5),
            "mid": round(mid, 5),
            "price": round(mid, 5) # Ensure price key is updated if mid changed
        }

    def reset(self):
        self.provider.reset()
