"""
Multi-Symbol, Multi-Timeframe Pipeline
Loads CSV candle data → computes technical indicators → stores in QuestDB → caches in Redis
"""
import sys
import os
import pandas as pd

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
data_service_path = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, project_root)
sys.path.insert(0, data_service_path)

from shared.python.questdb_client import QuestDBClient
from shared.python.redis_client import RedisClient
from processors.indicators import TechnicalIndicators

# --- High-performance settings ---
symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']  # Expand as needed
timeframes = ['M1', 'M5', 'H1']                       # Expand as needed

indicators = TechnicalIndicators()

# --- Orchestrate batch jobs for all symbol/timeframe combos ---
for symbol in symbols:
    for tf in timeframes:
        # --- 1. Load Data ---
        csv_path = os.path.join(project_root, f"{symbol}_{tf}_candles.csv")
        if not os.path.exists(csv_path):
            print(f"❌ Missing {csv_path} for {symbol} {tf}, skipping...")
            continue
        df = pd.read_csv(csv_path)
        df["time"] = pd.to_datetime(df["time"])

        # Rename 'time' to 'timestamp' for indicators compatibility
        df = df.rename(columns={"time": "timestamp"})

        # Ensure 'volume' column exists (use tick_volume as fallback)
        if "volume" not in df.columns and "tick_volume" in df.columns:
            df["volume"] = df["tick_volume"]

        # --- 2. Feature Engineering (class-based API) ---
        df = indicators.compute_all_features(df, symbol)

        # --- 3. Store enriched data in QuestDB ---
        qdb = QuestDBClient()
        qdb.insert_enriched_data(df)
        qdb.close()
        print(f"✅ Stored {symbol}-{tf} candles/features in QuestDB")

        # --- 4. Cache latest features in Redis ---
        rc = RedisClient()
        last_row = df.iloc[-1]
        latest_features = {
            'rsi_14': float(last_row.get('rsi_14', 0)),
            'macd': float(last_row.get('macd', 0)),
            'atr_14': float(last_row.get('atr_14', 0)),
            'adx_14': float(last_row.get('adx_14', 0)),
            'close': float(last_row.get('close', 0)),
        }
        rc.cache_latest_features(symbol, latest_features)
        rc.close()
        print(f"✅ Cached latest features for {symbol} in Redis")

print("🔁 Multi-symbol, multi-timeframe pipeline run complete.")
