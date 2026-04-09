"""
Odyssey v2 - Comprehensive Technical Indicators Module
Multi-symbol, multi-timeframe with scaling/normalization
Supports: XAUUSD, EURUSD + extensible
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

class TechnicalIndicators:
    def __init__(self):
        self.symbols = ['XAUUSD', 'EURUSD']  # Multi-symbol support
        
    def scale_features(self, df: pd.DataFrame, feature_cols: List[str]) -> pd.DataFrame:
        """Min-Max scaling for ML compatibility [0,1] range"""
        df_scaled = df.copy()
        for col in feature_cols:
            if col in df.columns:
                min_val = df[col].min()
                max_val = df[col].max()
                if max_val > min_val:
                    df_scaled[col] = (df[col] - min_val) / (max_val - min_val)
                else:
                    df_scaled[col] = 0.5  # Neutral value
        return df_scaled
    
    # === MOMENTUM INDICATORS ===
    def rsi(self, df: pd.DataFrame, period: int = 14, price_col: str = 'close') -> pd.Series:
        """Relative Strength Index"""
        delta = df[price_col].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    def stoch_rsi(self, df: pd.DataFrame, rsi_period: int = 14, stoch_period: int = 14, k_period: int = 3) -> Tuple[pd.Series, pd.Series]:
        """Stochastic RSI (K%, D%)"""
        rsi_values = self.rsi(df, rsi_period)
        rsi_low = rsi_values.rolling(window=stoch_period).min()
        rsi_high = rsi_values.rolling(window=stoch_period).max()
        k_percent = 100 * ((rsi_values - rsi_low) / (rsi_high - rsi_low))
        d_percent = k_percent.rolling(window=k_period).mean()
        return k_percent, d_percent
    
    # === TREND INDICATORS ===
    def ema(self, df: pd.DataFrame, period: int, price_col: str = 'close') -> pd.Series:
        """Exponential Moving Average"""
        return df[price_col].ewm(span=period, adjust=False).mean()
    
    def macd(self, df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9, price_col: str = 'close') -> Tuple[pd.Series, pd.Series, pd.Series]:
        """MACD Line, Signal Line, Histogram"""
        ema_fast = self.ema(df, fast, price_col)
        ema_slow = self.ema(df, slow, price_col)
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    def adx(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average Directional Index"""
        high_diff = df['high'].diff()
        low_diff = df['low'].diff()
        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)
        tr = pd.concat([
            df['high'] - df['low'],
            np.abs(df['high'] - df['close'].shift()),
            np.abs(df['low'] - df['close'].shift())
        ], axis=1).max(axis=1)
        
        plus_di = 100 * (pd.Series(plus_dm).ewm(span=period).mean() / tr.ewm(span=period).mean())
        minus_di = 100 * (pd.Series(minus_dm).ewm(span=period).mean() / tr.ewm(span=period).mean())
        dx = 100 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
        return dx.ewm(span=period).mean()
    
    # === VOLATILITY INDICATORS ===
    def bollinger_bands(self, df: pd.DataFrame, period: int = 20, std_dev: float = 2, price_col: str = 'close') -> Tuple[pd.Series, pd.Series, pd.Series]:
        """Bollinger Bands (Middle, Upper, Lower)"""
        sma = df[price_col].rolling(window=period).mean()
        std = df[price_col].rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        return sma, upper, lower
    
    def atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Average True Range"""
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        tr = np.maximum(high_low, np.maximum(high_close, low_close))
        return tr.rolling(window=period).mean()
    
    def cci(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Commodity Channel Index"""
        tp = (df['high'] + df['low'] + df['close']) / 3
        sma_tp = tp.rolling(window=period).mean()
        mad = tp.rolling(window=period).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
        return (tp - sma_tp) / (0.015 * mad)
    
    # === VOLUME INDICATORS ===
    def obv(self, df: pd.DataFrame) -> pd.Series:
        """On Balance Volume"""
        obv = (np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()
        return obv
    
    def vol_sma(self, df: pd.DataFrame, period: int = 20) -> pd.Series:
        """Volume Simple Moving Average"""
        return df['volume'].rolling(window=period).mean()
        
    # === INSTITUTIONAL QUANT FEATURES ===
    def realized_volatility(self, df: pd.DataFrame, period: int = 20, price_col: str = 'close') -> pd.Series:
        """Rolling Realized Volatility"""
        returns = np.log(df[price_col] / df[price_col].shift(1))
        return returns.rolling(window=period).std() * np.sqrt(period)

    def bid_ask_spread_proxy(self, df: pd.DataFrame) -> pd.Series:
        """Proxy for bid-ask spread using High-Low / Close or true spread if available"""
        if 'ask' in df.columns and 'bid' in df.columns:
            return (df['ask'] - df['bid']) / df['close']
        return (df['high'] - df['low']) / df['close']

    def volume_imbalance(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Volume delta/imbalance proxy"""
        delta = df['close'].diff()
        buy_vol = df['volume'].where(delta > 0, 0)
        sell_vol = df['volume'].where(delta < 0, 0)
        smooth_buy = buy_vol.rolling(window=period).mean()
        smooth_sell = sell_vol.rolling(window=period).mean()
        imbalance = (smooth_buy - smooth_sell) / (smooth_buy + smooth_sell).replace(0, 1e-9)
        return imbalance

    def log_returns(self, df: pd.DataFrame, price_col: str = 'close') -> pd.Series:
        """Logarithmic returns"""
        return np.log(df[price_col] / df[price_col].shift(1))
    
    # === COMPREHENSIVE FEATURE ENGINEERING ===
    def compute_all_features(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Compute ALL indicators + scaling for single symbol"""
        print(f"🧮 Computing features for {symbol}...")
        
        # Copy and prepare
        df_features = df.copy()
        df_features['symbol'] = symbol
        
        # Momentum
        df_features['rsi_14'] = self.rsi(df_features)
        df_features['stoch_k'], df_features['stoch_d'] = self.stoch_rsi(df_features)
        
        # Trend
        df_features['ema_9'] = self.ema(df_features, 9)
        df_features['ema_21'] = self.ema(df_features, 21)
        df_features['macd'], df_features['macd_signal'], df_features['macd_hist'] = self.macd(df_features)
        df_features['adx_14'] = self.adx(df_features)
        
        # Volatility
        df_features['bb_middle'], df_features['bb_upper'], df_features['bb_lower'] = self.bollinger_bands(df_features)
        df_features['atr_14'] = self.atr(df_features)
        
        # Momentum (continued)
        df_features['cci_14'] = self.cci(df_features)
        
        # Volume
        df_features['obv'] = self.obv(df_features)
        df_features['vol_sma'] = self.vol_sma(df_features)
        
        # Price-based features
        df_features['price_change_pct'] = df_features['close'].pct_change()
        df_features['high_low_ratio'] = df_features['high'] / df_features['low']
        df_features['close_position'] = (df_features['close'] - df_features['low']) / (df_features['high'] - df_features['low']).replace(0, 1e-9)
        
        # Institutional Quant Features
        df_features['log_returns'] = self.log_returns(df_features)
        df_features['realized_vol_20'] = self.realized_volatility(df_features, 20)
        df_features['spread_proxy'] = self.bid_ask_spread_proxy(df_features)
        df_features['vol_imbalance'] = self.volume_imbalance(df_features, 14)
        
        # Scaling ALL feature columns
        feature_cols = [
            'rsi_14', 'stoch_k', 'stoch_d', 'ema_9', 'ema_21', 'macd', 'macd_signal', 
            'macd_hist', 'adx_14', 'cci_14', 'bb_upper', 'bb_lower', 'atr_14', 'obv', 
            'vol_sma', 'price_change_pct', 'high_low_ratio', 'close_position',
            'log_returns', 'realized_vol_20', 'spread_proxy', 'vol_imbalance'
        ]
        
        df_features = self.scale_features(df_features, feature_cols)
        
        print(f"✅ {symbol}: {len(feature_cols)} features computed and scaled")
        return df_features
    
    def process_multi_symbol(self, data_dict: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
        """Process multiple symbols in parallel"""
        results = {}
        for symbol, df in data_dict.items():
            if symbol in self.symbols:
                results[symbol] = self.compute_all_features(df, symbol)
            else:
                print(f"⚠️  Skipping unsupported symbol: {symbol}")
        return results

# === TEST SCRIPT ===
if __name__ == "__main__":
    indicators = TechnicalIndicators()
    
    # Sample data for testing (replace with your real OHLCV)
    sample_data = {
        'XAUUSD': pd.DataFrame({
            'timestamp': pd.date_range('2025-11-01', periods=100, freq='1T'),
            'open': np.random.uniform(2500, 2600, 100),
            'high': np.random.uniform(2505, 2605, 100),
            'low': np.random.uniform(2495, 2595, 100),
            'close': np.random.uniform(2500, 2600, 100),
            'volume': np.random.uniform(1000, 5000, 100)
        }),
        'EURUSD': pd.DataFrame({
            'timestamp': pd.date_range('2025-11-01', periods=100, freq='1T'),
            'open': np.random.uniform(1.05, 1.08, 100),
            'high': np.random.uniform(1.051, 1.081, 100),
            'low': np.random.uniform(1.049, 1.079, 100),
            'close': np.random.uniform(1.05, 1.08, 100),
            'volume': np.random.uniform(5000, 20000, 100)
        })
    }
    
    # Test multi-symbol processing
    features = indicators.process_multi_symbol(sample_data)
    
    # Verify output
    for symbol, df in features.items():
        print(f"\n📊 {symbol} Features Sample:")
        print(df[['timestamp', 'rsi_14', 'macd', 'atr_14', 'adx_14']].tail())
        print(f"Features shape: {df.shape}")
