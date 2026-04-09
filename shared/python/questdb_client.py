import os
import psycopg2
from psycopg2.extras import execute_batch, RealDictCursor
from typing import List, Dict, Tuple
import pandas as pd
from dotenv import load_dotenv
from logger import OdysseyLogger

load_dotenv()

_logger = OdysseyLogger('questdb-client')


class QuestDBClient:
    """QuestDB client for storing time-series trading data"""

    def __init__(self, host=None, port=None, user=None, password=None, database=None):
        host = host or os.getenv('QUESTDB_HOST', 'localhost')
        port = port or int(os.getenv('QUESTDB_PORT', '8812'))
        user = user or os.getenv('QUESTDB_USER', 'admin')
        password = password or os.getenv('QUESTDB_PASSWORD', 'quest')
        database = database or os.getenv('QUESTDB_DATABASE', 'qdb')
        try:
            self.conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=database
            )
            self.conn.autocommit = True
            _logger.info("QuestDB connected successfully")
        except Exception as e:
            _logger.error(f"QuestDB connection failed: {e}")
            raise

    def create_tables(self):
        """Create all necessary tables with updated schema"""
        with self.conn.cursor() as cur:
            cur.execute("DROP TABLE IF EXISTS ohlcv_1m;")
            _logger.info("DROPPED ohlcv_1m table - forcing schema refresh")

        create_ohlcv = """
        CREATE TABLE ohlcv_1m (
            timestamp TIMESTAMP,
            symbol SYMBOL,
            open DOUBLE,
            high DOUBLE,
            low DOUBLE,
            close DOUBLE,
            volume DOUBLE,
            rsi_14 DOUBLE,
            stoch_k DOUBLE,
            stoch_d DOUBLE,
            ema_9 DOUBLE,
            ema_21 DOUBLE,
            macd DOUBLE,
            macd_signal DOUBLE,
            macd_hist DOUBLE,
            adx_14 DOUBLE,
            bb_middle DOUBLE,
            bb_upper DOUBLE,
            bb_lower DOUBLE,
            atr_14 DOUBLE,
            obv DOUBLE,
            price_change_pct DOUBLE,
            high_low_ratio DOUBLE,
            close_position DOUBLE
        ) TIMESTAMP(timestamp) PARTITION BY DAY WAL;
        """

        with self.conn.cursor() as cur:
            cur.execute(create_ohlcv)

        other_tables = [
            """
            CREATE TABLE IF NOT EXISTS market_ticks (
                symbol SYMBOL,
                timestamp TIMESTAMP,
                bid DOUBLE,
                ask DOUBLE,
                volume LONG
            ) TIMESTAMP(timestamp) PARTITION BY DAY;
            """,
            """
            CREATE TABLE IF NOT EXISTS trades (
                trade_id SYMBOL,
                symbol SYMBOL,
                timestamp TIMESTAMP,
                side SYMBOL,
                entry_price DOUBLE,
                exit_price DOUBLE,
                volume DOUBLE,
                pnl DOUBLE,
                strategy SYMBOL,
                confidence DOUBLE,
                comment STRING
            ) TIMESTAMP(timestamp) PARTITION BY DAY;
            """,
            """
            CREATE TABLE IF NOT EXISTS predictions (
                symbol SYMBOL,
                timestamp TIMESTAMP,
                prediction DOUBLE,
                confidence DOUBLE,
                model_version SYMBOL,
                inference_time_ms LONG
            ) TIMESTAMP(timestamp) PARTITION BY DAY;
            """,
            """
            CREATE TABLE IF NOT EXISTS signals (
                symbol SYMBOL,
                timestamp TIMESTAMP,
                signal_type SYMBOL,
                confidence DOUBLE,
                strategy_id SYMBOL,
                entry_price DOUBLE,
                stop_loss DOUBLE,
                take_profit DOUBLE,
                reason STRING
            ) TIMESTAMP(timestamp) PARTITION BY DAY;
            """
        ]

        with self.conn.cursor() as cur:
            for sql in other_tables:
                cur.execute(sql)

        _logger.info("ALL TABLES RECREATED with correct schema!")

    def insert_enriched_data(self, df: pd.DataFrame):
        """Insert enriched OHLCV + features batch into QuestDB"""
        if df.empty:
            _logger.warning("insert_enriched_data received empty DataFrame.")
            return

        records = []
        for _, row in df.iterrows():
            record = (
                row['timestamp'],
                row['symbol'],
                row['open'],
                row['high'],
                row['low'],
                row['close'],
                row['volume'],
                row.get('rsi_14', None),
                row.get('stoch_k', None),
                row.get('stoch_d', None),
                row.get('ema_9', None),
                row.get('ema_21', None),
                row.get('macd', None),
                row.get('macd_signal', None),
                row.get('macd_hist', None),
                row.get('adx_14', None),
                row.get('bb_middle', None),
                row.get('bb_upper', None),
                row.get('bb_lower', None),
                row.get('atr_14', None),
                row.get('obv', None),
                row.get('price_change_pct', None),
                row.get('high_low_ratio', None),
                row.get('close_position', None)
            )
            records.append(record)

        insert_query = """
            INSERT INTO ohlcv_1m (
                timestamp, symbol, open, high, low, close, volume,
                rsi_14, stoch_k, stoch_d, ema_9, ema_21, macd, macd_signal,
                macd_hist, adx_14, bb_middle, bb_upper, bb_lower, atr_14,
                obv, price_change_pct, high_low_ratio, close_position
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
            )
        """

        try:
            with self.conn.cursor() as cur:
                execute_batch(cur, insert_query, records)
            _logger.info(f"Inserted {len(records)} enriched rows into QuestDB ohlcv_1m")
        except Exception as e:
            _logger.error(f"Failed to insert enriched data: {e}")
            self.conn.rollback()

    def get_latest_features(self, symbol: str, limit: int = 1) -> Dict:
        """Get latest features for ML/strategy consumption"""
        query = """
        SELECT rsi_14, macd, atr_14, adx_14, close, stoch_k, stoch_d
        FROM ohlcv_1m 
        WHERE symbol = %s 
        ORDER BY timestamp DESC 
        LIMIT %s
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (symbol, limit))
            result = cur.fetchone()
            return dict(result) if result else {}

    def get_recent_candles(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Get recent candles with all new features"""
        query = """
        SELECT * FROM ohlcv_1m
        WHERE symbol = %s
        ORDER BY timestamp DESC
        LIMIT %s
        """
        with self.conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(query, (symbol, limit))
            return cur.fetchall()

    def insert_prediction(self, symbol: str, prediction: float, confidence: float, model_version: str, inference_time_ms: int):
        query = """
        INSERT INTO predictions (symbol, timestamp, prediction, confidence, model_version, inference_time_ms)
        VALUES (%s, now(), %s, %s, %s, %s)
        """
        with self.conn.cursor() as cur:
            cur.execute(query, (symbol, prediction, confidence, model_version, inference_time_ms))

    def insert_signal(self, signal: dict):
        query = """
        INSERT INTO signals
        (symbol, timestamp, signal_type, confidence, strategy_id, entry_price, stop_loss, take_profit, reason)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        values = (
            signal.get("symbol"),
            signal.get("timestamp"),
            signal.get("signal_type"),
            signal.get("confidence"),
            signal.get("strategy_id"),
            signal.get("entry_price"),
            signal.get("stop_loss"),
            signal.get("take_profit"),
            signal.get("reason")
        )
        with self.conn.cursor() as cur:
            cur.execute(query, values)
            _logger.info(f"Signal inserted into QuestDB for {signal.get('symbol')}")

    def close(self):
        self.conn.close()
