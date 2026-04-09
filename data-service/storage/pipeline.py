"""
Odyssey v2 - Enhanced Data Pipeline with Multi-Symbol Indicators
Full integration: OHLCV → 16+ Technical Features → QuestDB → Redis Cache
Supports: Live MT5 data, CSV files, or sample data
"""

import os
import sys
import argparse
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

load_dotenv()

# Fix imports for project structure
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # storage
DATASERVICE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
sys.path.insert(0, DATASERVICE_DIR)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
sys.path.insert(0, PROJECT_ROOT)

from processors.indicators import TechnicalIndicators
from questdb_client import QuestDBClient
from redis_client import RedisClient
from kafka_utils import KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger
from metrics import metrics

logger = OdysseyLogger('data-pipeline')


class OdysseyPipeline:
    def __init__(self, data_source='auto'):
        """
        Args:
            data_source: 'mt5' for live MT5, 'csv' for CSV files, 'sample' for random data,
                         'auto' tries MT5 first, then CSV, then sample.
        """
        self.indicators = TechnicalIndicators()
        self.qdb = QuestDBClient()
        self.redis = RedisClient()
        self.kafka = KafkaProducerClient()
        self.symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'USDINR', 'NIFTY50', 'SENSEX', 'RELIANCE', 'INFY']
        self.data_source = data_source
        self.project_root = PROJECT_ROOT
        
        metrics.start_server(8001)

    # ==========================================
    # DATA LOADERS
    # ==========================================

    def load_mt5_data(self, symbol: str, timeframe_str: str = 'M1', periods: int = 250) -> pd.DataFrame:
        """Load live data from MT5 terminal."""
        try:
            import MetaTrader5 as mt5

            mt5_login = int(os.getenv('MT5_LOGIN', '0'))
            mt5_password = os.getenv('MT5_PASSWORD', '')
            mt5_server = os.getenv('MT5_SERVER', 'MetaQuotes-Demo')

            if not mt5.initialize(login=mt5_login, password=mt5_password, server=mt5_server):
                logger.error(f"MT5 init failed: {mt5.last_error()}")
                return pd.DataFrame()

            tf_map = {
                'M1': mt5.TIMEFRAME_M1,
                'M5': mt5.TIMEFRAME_M5,
                'H1': mt5.TIMEFRAME_H1,
                'D1': mt5.TIMEFRAME_D1,
            }
            tf = tf_map.get(timeframe_str, mt5.TIMEFRAME_M1)

            rates = mt5.copy_rates_from_pos(symbol, tf, 0, periods)
            mt5.shutdown()

            if rates is None or len(rates) == 0:
                logger.warning(f"No MT5 data for {symbol} {timeframe_str}")
                return pd.DataFrame()

            df = pd.DataFrame(rates)
            df['timestamp'] = pd.to_datetime(df['time'], unit='s')
            df = df.drop(columns=['time'], errors='ignore')

            # Ensure volume column exists
            if 'volume' not in df.columns and 'tick_volume' in df.columns:
                df['volume'] = df['tick_volume']

            logger.info(f"Loaded {len(df)} bars from MT5 for {symbol} {timeframe_str}")
            return df

        except ImportError:
            logger.warning("MetaTrader5 package not installed - cannot load MT5 data")
            return pd.DataFrame()
        except Exception as e:
            logger.error(f"MT5 data load failed for {symbol}: {e}")
            return pd.DataFrame()

    def load_csv_data(self, symbol: str, timeframe_str: str = 'M1') -> pd.DataFrame:
        """Load data from existing CSV files."""
        csv_path = os.path.join(self.project_root, "data", "historical", f"{symbol}_{timeframe_str}_candles.csv")
        if not os.path.exists(csv_path):
            # Try without timeframe
            csv_path = os.path.join(self.project_root, "data", "historical", f"{symbol}_candles.csv")
            if not os.path.exists(csv_path):
                logger.warning(f"No CSV found for {symbol} {timeframe_str}")
                return pd.DataFrame()

        df = pd.read_csv(csv_path)

        # Normalize column names
        if 'time' in df.columns:
            df = df.rename(columns={'time': 'timestamp'})
        df['timestamp'] = pd.to_datetime(df['timestamp'])

        # Ensure volume column
        if 'volume' not in df.columns and 'tick_volume' in df.columns:
            df['volume'] = df['tick_volume']
        elif 'volume' not in df.columns:
            df['volume'] = 0

        logger.info(f"Loaded {len(df)} bars from CSV for {symbol} {timeframe_str}")
        return df

    def load_sample_data(self, symbol: str, periods: int = 100) -> pd.DataFrame:
        """Generate random sample data for testing only."""
        logger.warning(f"Using SAMPLE data for {symbol} (not real market data)")
        np.random.seed(42)

        timestamps = pd.date_range(
            start=datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            periods=periods,
            freq='1min'
        )

        if symbol == 'XAUUSD':
            base_price, volatility = 2550.0, 5.0
        else:
            base_price, volatility = 1.0850, 0.002

        data = {
            'timestamp': timestamps,
            'open': base_price + np.cumsum(np.random.normal(0, volatility, periods)),
            'high': base_price + np.abs(np.random.normal(0, volatility * 1.2, periods)),
            'low': base_price + np.random.normal(0, volatility * 1.2, periods),
            'close': base_price + np.cumsum(np.random.normal(0, volatility, periods)),
            'volume': np.random.uniform(1000, 10000, periods)
        }

        df = pd.DataFrame(data)
        df[['open', 'high', 'low', 'close']] = df[['open', 'high', 'low', 'close']].round(5)
        return df

    def load_data(self, symbol: str) -> pd.DataFrame:
        """Load data based on configured source (auto/mt5/csv/sample)."""
        if self.data_source == 'mt5':
            return self.load_mt5_data(symbol)
        elif self.data_source == 'csv':
            return self.load_csv_data(symbol)
        elif self.data_source == 'sample':
            return self.load_sample_data(symbol)
        else:  # auto
            df = self.load_mt5_data(symbol)
            if df.empty:
                df = self.load_csv_data(symbol)
            if df.empty:
                df = self.load_sample_data(symbol)
            return df

    # ==========================================
    # PIPELINE
    # ==========================================

    def process_symbol_pipeline(self, symbol: str) -> pd.DataFrame:
        """Complete pipeline for single symbol: load multi-TF → features → store → cache"""
        logger.info(f"Processing multi-timeframe pipeline for {symbol}...")

        # Timeframes to process
        timeframes = ['M1', 'M5', 'M15']
        all_features = {}
        
        for tf in timeframes:
            # 1. Load raw OHLCV data per timeframe (Mocking TF passing for now as kwargs if supported)
            # Future implement: self.load_data(symbol, timeframe=tf)
            df_raw = self.load_data(symbol)
            if df_raw.empty:
                logger.error(f"No {tf} data loaded for {symbol} - skipping")
                continue

            # 2. Compute all technical features for this TF
            df_feat = self.indicators.compute_all_features(df_raw, symbol)
            all_features[tf] = df_feat

        if not all_features or 'M1' not in all_features:
            return pd.DataFrame()

        # Base dataframe is M1
        df_features = all_features['M1']

        # 3. Store to QuestDB (ONLY LATEST ROW TO AVOID DUPLICATES IN LIVE MODE)
        latest_row = df_features.iloc[[-1]]
        last_ts = latest_row.iloc[0]['timestamp']
        
        # Check QuestDB state to avoid duplicates
        try:
            latest_qdb = self.qdb.get_latest_features(symbol)
            qdb_ts = latest_qdb.get('timestamp') if latest_qdb else None
            
            # Simple timestamp check - only insert if it's a new minute
            if qdb_ts is None or last_ts > qdb_ts:
                self.qdb.insert_enriched_data(latest_row)
                logger.debug(f"Inserted NEW row for {symbol} at {last_ts}")
            else:
                logger.debug(f"Row for {symbol} at {last_ts} already exists in QuestDB. Skipping.")
        except Exception as e:
            # Fallback to insert if check fails
            self.qdb.insert_enriched_data(latest_row)

        # 4. Cache latest features to Redis (incorporating nested TF data if needed)
        latest_features = df_features.iloc[-1][['rsi_14', 'macd', 'atr_14', 'adx_14', 'close']].to_dict()
        latest_features = {k: float(v) for k, v in latest_features.items()}
        
        # Add stub multi-TF context
        if 'M5' in all_features and not all_features['M5'].empty:
            latest_features['m5_rsi_14'] = float(all_features['M5'].iloc[-1]['rsi_14'])
        if 'M15' in all_features and not all_features['M15'].empty:
            latest_features['m15_rsi_14'] = float(all_features['M15'].iloc[-1]['rsi_14'])
            
        self.redis.cache_latest_features(symbol, latest_features)

        # 5. Publish to Kafka
        kafka_payload = {
            'symbol': symbol,
            'timestamp': df_features.iloc[-1]['timestamp'].isoformat(),
            'features': latest_features,
            'timeframes_processed': list(all_features.keys())
        }
        self.kafka.send(KafkaTopics.MARKET_DATA_RAW, kafka_payload, key=symbol)

        # 6. Update metrics
        metrics.events_processed.labels(service_name='data-pipeline', event_type='market_data').inc()

        logger.info(f"{symbol}: Pipeline complete - {len(df_features)} rows processed")
        return df_features

    def run_full_pipeline(self):
        """Run complete multi-symbol pipeline once"""
        all_results = {}
        for symbol in self.symbols:
            result = self.process_symbol_pipeline(symbol)
            all_results[symbol] = result

            if not result.empty:
                latest_db = self.qdb.get_latest_features(symbol)
                logger.info(f"  Latest from QuestDB: {latest_db}")
                latest_redis = self.redis.get_latest_features(symbol)
                logger.info(f"  Latest from Redis: {latest_redis}")

        logger.debug("PIPELINE CYCLE COMPLETE.")
        return all_results

    def run_forever(self, interval_sec: int = 60):
        """Run the pipeline continuously"""
        logger.info(f"ODYSSEY v2 CONTINUOUS PIPELINE STARTED (source={self.data_source}, interval={interval_sec}s)...")
        
        # Ensure tables exist ONCE at startup
        try:
            # Note: create_tables drops the table! Only use if DB is fresh or schema changed.
            # For now, we assume tables exist or are created by the orchestrator.
            # self.qdb.create_tables() 
            pass
        except Exception as e:
            logger.error(f"Schema check failed: {e}")

        import time
        while True:
            try:
                self.run_full_pipeline()
            except Exception as e:
                logger.error(f"Pipeline cycle failed: {e}")
            
            time.sleep(interval_sec)


# === MAIN EXECUTION ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Odyssey v2 Data Pipeline')
    parser.add_argument('--source', choices=['auto', 'mt5', 'csv', 'sample'],
                        default='auto', help='Data source (default: auto)')
    args = parser.parse_args()

    pipeline = OdysseyPipeline(data_source=args.source)
    
    # Run once to warm up (optional)
    pipeline.run_full_pipeline()
    
    # Start continuous processing - this matches the HFT feel of the terminal
    pipeline.run_forever(interval_sec=60)
