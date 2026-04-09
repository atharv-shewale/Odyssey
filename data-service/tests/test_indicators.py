"""
Test suite for TechnicalIndicators class
Uses the class-based API from processors/indicators.py
"""
import os
import sys
import pandas as pd
import numpy as np

# Fix import path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from processors.indicators import TechnicalIndicators


def create_sample_data(n=200):
    """Generate realistic OHLCV test data"""
    np.random.seed(42)
    close = 1.0850 + np.cumsum(np.random.normal(0, 0.001, n))
    return pd.DataFrame({
        'timestamp': pd.date_range('2025-01-01', periods=n, freq='1min'),
        'open': close + np.random.normal(0, 0.0005, n),
        'high': close + np.abs(np.random.normal(0.001, 0.0005, n)),
        'low': close - np.abs(np.random.normal(0.001, 0.0005, n)),
        'close': close,
        'volume': np.random.uniform(1000, 10000, n),
    })


def test_rsi():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    rsi = indicators.rsi(df)
    assert len(rsi) == len(df), "RSI length mismatch"
    # After warmup, RSI should be bounded 0-100
    valid_rsi = rsi.dropna()
    assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all(), "RSI out of bounds"
    print("✅ test_rsi passed")


def test_ema():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    ema_14 = indicators.ema(df, period=14)
    assert len(ema_14) == len(df), "EMA length mismatch"
    assert not ema_14.isna().all(), "EMA is all NaN"
    print("✅ test_ema passed")


def test_macd():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    macd_line, signal_line, histogram = indicators.macd(df)
    assert len(macd_line) == len(df), "MACD length mismatch"
    assert len(signal_line) == len(df), "Signal length mismatch"
    assert len(histogram) == len(df), "Histogram length mismatch"
    print("✅ test_macd passed")


def test_bollinger_bands():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    middle, upper, lower = indicators.bollinger_bands(df)
    valid = middle.dropna()
    assert len(valid) > 0, "Bollinger Bands all NaN"
    # Upper should be above lower
    valid_idx = upper.dropna().index.intersection(lower.dropna().index)
    assert (upper[valid_idx] >= lower[valid_idx]).all(), "Upper BB < Lower BB"
    print("✅ test_bollinger_bands passed")


def test_atr():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    atr = indicators.atr(df)
    valid_atr = atr.dropna()
    assert (valid_atr >= 0).all(), "ATR has negative values"
    print("✅ test_atr passed")


def test_stoch_rsi():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    k, d = indicators.stoch_rsi(df)
    assert len(k) == len(df), "Stoch K length mismatch"
    assert len(d) == len(df), "Stoch D length mismatch"
    print("✅ test_stoch_rsi passed")


def test_obv():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    obv = indicators.obv(df)
    assert len(obv) == len(df), "OBV length mismatch"
    print("✅ test_obv passed")


def test_compute_all_features():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    result = indicators.compute_all_features(df, 'EURUSD')
    expected_cols = ['rsi_14', 'macd', 'atr_14', 'adx_14', 'bb_upper', 'bb_lower', 'obv']
    for col in expected_cols:
        assert col in result.columns, f"Missing feature column: {col}"
    assert result.shape[0] == df.shape[0], "Row count changed after feature computation"
    print("✅ test_compute_all_features passed")


def test_scale_features():
    indicators = TechnicalIndicators()
    df = create_sample_data()
    df['test_feature'] = np.random.uniform(0, 100, len(df))
    scaled = indicators.scale_features(df, ['test_feature'])
    valid = scaled['test_feature'].dropna()
    assert (valid >= 0).all() and (valid <= 1).all(), "Scaled features out of [0,1] range"
    print("✅ test_scale_features passed")


if __name__ == "__main__":
    test_rsi()
    test_ema()
    test_macd()
    test_bollinger_bands()
    test_atr()
    test_stoch_rsi()
    test_obv()
    test_compute_all_features()
    test_scale_features()
    print("\n🎉 All indicator tests passed!")
