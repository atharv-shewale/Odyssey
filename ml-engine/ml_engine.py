"""
Odyssey v2 - ML Prediction Engine (Enterprise Architecture)
Dual-model: LSTM (primary) + RandomForest (shadow/fallback)
Consumes Kafka features → predictions → QuestDB/Redis storage
"""

import os
import sys
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Tuple
from collections import deque
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

load_dotenv()

# Fix imports for ENTERPRISE structure
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # ml-engine/
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")
DATA_SERVICE = os.path.join(PROJECT_ROOT, "data-service", "storage")

sys.path.insert(0, SHARED_PYTHON)
sys.path.insert(0, DATA_SERVICE)
sys.path.insert(0, CURRENT_DIR)

import joblib
import shap
from sklearn.ensemble import RandomForestRegressor
from sklearn.cluster import KMeans
from redis_client import RedisClient
from questdb_client import QuestDBClient
from kafka_utils import KafkaConsumerClient, KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger
from metrics import metrics

# LSTM model import
from models.lstm_model import OdysseyLSTM

logger = OdysseyLogger('ml-engine')


class MLTradingEngine:
    def __init__(self):
        self.redis = RedisClient()
        self.qdb = QuestDBClient()
        self.kafka_producer = KafkaProducerClient()
        self.symbols = [
            'XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY', 'DAX40', 'SPX500',
            # INDIAN MARKETS
            'USDINR', 'NIFTY50', 'SENSEX', 'BANKNIFTY', 
            'RELIANCE', 'INFY', 'SBIN', 'BHARTIARTL', 'ITC', 'LTIM', 'KOTAKBANK'
        ]
        self.prediction_history = {sym: deque(maxlen=2000) for sym in self.symbols}
        
        metrics.start_server(8002)

        # ============================
        # PRIMARY MODEL: LSTM
        # ============================
        self.lstm = OdysseyLSTM(lookback=30)
        lstm_path = os.path.join(PROJECT_ROOT, "ml-engine", "models", "saved", "lstm_model.pt")
        if self.lstm.load(lstm_path):
            logger.info("PRIMARY MODEL: LSTM loaded from checkpoint")
        else:
            logger.warning("PRIMARY MODEL: LSTM checkpoint not found — will use RandomForest fallback until trained")

        # ============================
        # SHADOW/FALLBACK: RandomForest + XAI (SHAP)
        # ============================
        self.rf_feature_order = [
            'rsi_14', 'inst_rsi', 'stoch_k', 'stoch_d', 'ema_9', 'ema_21', 'macd', 
            'macd_signal', 'macd_hist', 'atr_14', 'adx_14', 'cci_14',
            'bb_upper', 'bb_lower', 'obv', 'vol_sma', 'm5_rsi_14', 'm15_rsi_14',
            'log_returns', 'realized_vol_20', 'spread_proxy', 'vol_imbalance', 'sentiment_score', 'global_mood'
        ]
        
        self.models_dir = os.path.join(PROJECT_ROOT, "ml-engine", "models", "saved")
        os.makedirs(self.models_dir, exist_ok=True)
        self.shadow_model = self._load_rf_model('rf_model.pkl')
        
        # Initialize SHAP Explainer for the Shadow Model
        try:
            self.shap_explainer = shap.TreeExplainer(self.shadow_model)
            logger.info("XAI Engine: SHAP TreeExplainer initialized for shadow model")
        except Exception as e:
            logger.warning(f"XAI Engine: SHAP init failed: {e}")
            self.shap_explainer = None
        
        # ============================
        # ADVANCED AI: Regime Detection (Online Learning)
        # ============================
        self._init_regime_model()
        
        logger.info("ML Engine initialized — LSTM primary + RF shadow + SHAP XAI — Research Grade ready")
    
    def _init_regime_model(self):
        """Initialize KMeans for regime detection. Refitted iteratively."""
        try:
            self.regime_model = KMeans(n_clusters=4, random_state=42, n_init='auto')
            np.random.seed(42)
            X_dummy = np.random.rand(10, len(self.rf_feature_order))
            self.regime_model.fit(X_dummy)
            self.feature_buffer = deque(maxlen=1000)
            logger.info("Regime Detector (KMeans) initialized. Will adapt online.")
        except Exception as e:
            logger.error(f"Regime detector init failed: {e}")
            self.regime_model = None
    
    def _load_rf_model(self, model_filename: str):
        """Load RandomForest model or create fallback."""
        model_path = os.path.join(self.models_dir, model_filename)
        
        try:
            if os.path.exists(model_path):
                model = joblib.load(model_path)
                logger.info(f"Loaded RF shadow model: {model_filename}")
                return model
        except Exception as e:
            logger.warning(f"Failed to load {model_filename}: {e}")
        
        # Create fallback model
        logger.warning(f"Creating FALLBACK RF model (train a real model with ml-engine/training/train_model.py)")
        model = RandomForestRegressor(n_estimators=100, random_state=42, n_jobs=-1)
        
        np.random.seed(42)
        X_dummy = np.random.rand(1000, len(self.rf_feature_order))
        y_dummy = np.random.rand(1000) * 0.1 - 0.05
        model.fit(X_dummy, y_dummy)
        
        joblib.dump(model, model_path)
        logger.info(f"Fallback RF model saved: {model_filename}")
        return model
    
    def _get_rf_features(self, features_dict: Dict) -> np.ndarray:
        """Get feature vector for RandomForest."""
        feature_vector = [features_dict.get(feat, 0.5) for feat in self.rf_feature_order]
        return np.array(feature_vector).reshape(1, -1)
    
    def predict(self, symbol: str, features_dict: Dict) -> Tuple[float, float, list, dict, float]:
        """
        Generate prediction using LSTM (primary) or RF (fallback).
        Returns (prediction, confidence, attention_weights, feature_importance, uncertainty_std).
        """
        # Try LSTM first: update buffer and predict if ready
        self.lstm.update_buffer(symbol, features_dict)
        
        if self.lstm.is_ready(symbol):
            try:
                prob, confidence, attn_weights, feature_importance, prob_std = self.lstm.predict(symbol)
                # Convert probability to signed prediction for signal generation
                prediction = (prob - 0.5) * 0.1  # Scale to roughly ±0.05 range
                logger.info(f"LSTM MC prediction for {symbol}: prob={prob:.4f} ± {prob_std:.4f}, conf={confidence:.2f}")
                return float(prediction), float(confidence), attn_weights, feature_importance, float(prob_std)
            except Exception as e:
                logger.error(f"LSTM prediction failed for {symbol}: {e}")
        
        # Fallback to RandomForest
        return self._rf_predict(symbol, features_dict)
    
    def _rf_predict(self, symbol: str, features_dict: Dict) -> Tuple[float, float, list, dict, float]:
        """RandomForest fallback prediction with SHAP XAI."""
        try:
            X = self._get_rf_features(features_dict)
            pred = self.shadow_model.predict(X)[0]
            
            # Generate SHAP explanations
            feature_importance = {}
            if self.shap_explainer:
                try:
                    shap_values = self.shap_explainer.shap_values(X)
                    # Convert to normalized importance
                    total_abs_shap = np.sum(np.abs(shap_values[0]))
                    if total_abs_shap > 0:
                        importances = np.abs(shap_values[0]) / total_abs_shap
                        feature_importance = {
                            feat: float(imp) 
                            for feat, imp in zip(self.rf_feature_order, importances)
                            if imp > 0.05 # Only include significant contributors
                        }
                except Exception as e:
                    logger.warning(f"SHAP explanation failed: {e}")

            feature_completeness = sum(1 for v in X[0] if 0.1 <= v <= 0.9) / len(X[0])
            confidence = min(0.95, 0.5 + feature_completeness * 0.3)
            return float(pred), float(confidence), [], feature_importance, 0.0
        except Exception as e:
            logger.error(f"RF prediction also failed for {symbol}: {e}")
            return 0.0, 0.0, [], {}, 0.0
    
    def generate_signal(self, symbol: str, prediction: float, confidence: float, attn_weights: list, feature_importance: dict, uncertainty: float) -> Dict:
        """Convert prediction to actionable trading signal using Z-Scoring and Percentiles."""
        self.prediction_history[symbol].append(prediction)
        
        history = np.array(self.prediction_history[symbol])
        if len(history) < 30:
            z_score = 0.0
            percentile = 50.0
        else:
            mean_pred = np.mean(history)
            std_pred = np.std(history) + 1e-9
            z_score = (prediction - mean_pred) / std_pred
            percentile = float(pd.Series(history).rank(pct=True).iloc[-1] * 100)

        signal = {
            'symbol': symbol,
            'timestamp': datetime.utcnow().isoformat(),
            'raw_prediction': prediction,
            'z_score': float(z_score),
            'percentile': percentile,
            'confidence': confidence,
            'uncertainty_std': uncertainty,
            'signal_strength': abs(z_score) * confidence if len(history) >= 30 else 0,
            'model_version': 'odyssey_quant_v3.0',
            'attention_weights': attn_weights,
            'feature_importance': feature_importance
        }
        
        # Enterprise-grade signal thresholds (Quantiles)
        if percentile >= 95 and confidence > 0.65:
            signal['action'] = 'BUY'
            signal['strength'] = 'STRONG' if percentile >= 98 else 'MEDIUM'
        elif percentile <= 5 and confidence > 0.65:
            signal['action'] = 'SELL' 
            signal['strength'] = 'STRONG' if percentile <= 2 else 'MEDIUM'
        else:
            signal['action'] = 'HOLD'
            signal['strength'] = 'NEUTRAL'
        
        metrics.signal_strength.labels(symbol=symbol).set(signal['signal_strength'])
        
        return signal
    
    def store_prediction(self, symbol: str, prediction: float, confidence: float):
        """Store raw prediction in QuestDB."""
        try:
            self.qdb.insert_prediction(
                symbol, prediction, confidence, 'odyssey_lstm_v3.0', 25
            )
            logger.info(f"Stored prediction: {symbol} pred={prediction:.4f} conf={confidence:.2f}")
        except Exception as e:
            logger.error(f"Prediction storage failed: {e}")
    
    def cache_signal(self, signal: Dict):
        """Cache signal for strategy-engine consumption."""
        try:
            self.redis.cache_prediction(signal['symbol'], signal)
        except Exception as e:
            logger.error(f"Signal cache failed: {e}")
    
    def publish_signal(self, signal: Dict):
        """Publish signal to Kafka for Strategy Engine."""
        try:
            self.kafka_producer.send(KafkaTopics.ML_SIGNALS, signal, key=signal['symbol'])
            
            # Send alert for actionable signals
            if signal.get('action') in ['BUY', 'SELL']:
                alert = {"type": "SIGNAL", **signal}
                self.kafka_producer.send(KafkaTopics.ALERTS, alert, key=signal['symbol'])
                
            logger.info(f"Published signal: {signal['action']} {signal['symbol']} ({signal['strength']})")
        except Exception as e:
            logger.error(f"Kafka signal publish failed: {e}")
            
    def handle_market_data(self, message: dict):
        """Kafka callback for new market data."""
        symbol = message.get('symbol')
        features = message.get('features', {})
        timeframes = message.get('timeframes_processed', ['M1'])

        if not symbol or not features:
            logger.warning("Received invalid message payload")
            return

        # Inject sentiment score from Redis (published by sentiment-service)
        try:
            sentiment_data = self.redis.get_cache(f"sentiment:{symbol}")
            if sentiment_data and isinstance(sentiment_data, dict):
                features['sentiment_score'] = float(sentiment_data.get('score', 0.0))
            else:
                features['sentiment_score'] = 0.0
            
            # [ENRICHMENT] Inject AlphaVantage Macro & Institutional Features
            macro_status = self.redis.get_cache("macro:market_status")
            if macro_status:
                mood_map = {"Bullish": 1.0, "Consolidating": 0.5, "Bearish": 0.0}
                features['global_mood'] = mood_map.get(macro_status.get('global_mood'), 0.5)
            else:
                features['global_mood'] = 0.5
            
            av_rsi = self.redis.get_feature(symbol, "inst_rsi")
            features['inst_rsi'] = float(av_rsi.get('value', 50.0)) if av_rsi else 50.0

        except Exception as e:
            logger.warning(f"Feature enrichment failed: {e}")
            features['sentiment_score'] = 0.0
            features['global_mood'] = 0.5
            features['inst_rsi'] = 50.0
            
        logger.info(f"Received market data for {symbol} (TFs: {timeframes}) | AV Enriched: {features.get('inst_rsi')}")
        
        # Primary prediction (LSTM or RF fallback)
        pri_pred, pri_conf, pri_attn, pri_feat, pri_std = self.predict(symbol, features)
        pri_signal = self.generate_signal(symbol, pri_pred, pri_conf, pri_attn, pri_feat, pri_std)
        
        # Shadow comparison (always RF for A/B analysis)
        try:
            X = self._get_rf_features(features)
            sha_pred = self.shadow_model.predict(X)[0]
            sha_signal = self.generate_signal(symbol, sha_pred, 0.6, [], {}, 0.0)
            logger.debug(f"{symbol} Shadow RF Signal: {sha_signal['action']} ({sha_pred:.5f})")
            
            pri_signal['shadow_action'] = sha_signal['action']
            pri_signal['shadow_divergence'] = pri_pred - sha_pred
        except Exception as e:
            logger.warning(f"Shadow model failed on {symbol}: {e}")

        # Regime detection online learning gate
        if self.regime_model is not None:
            try:
                X_feat = self._get_rf_features(features)
                self.feature_buffer.append(X_feat[0])
                
                # Online learning: refit every 100 ticks once we have enough data
                if len(self.feature_buffer) >= 500 and len(self.feature_buffer) % 100 == 0:
                    self.regime_model.fit(np.array(self.feature_buffer))
                    logger.debug(f"Retrained Regime Model on last 500 ticks.")
                
                regime_cluster = self.regime_model.predict(X_feat)[0]
                pri_signal['regime_cluster'] = int(regime_cluster)
            except Exception as e:
                logger.error(f"Regime detection failed: {e}")

        # Persist results using primary outputs
        self.store_prediction(symbol, pri_pred, pri_conf)
        self.cache_signal(pri_signal)
        self.publish_signal(pri_signal)
        
        metrics.events_processed.labels(service_name='ml-engine', event_type='market_data').inc()
    
    def start(self):
        """Start Kafka consumer loop."""
        logger.info("ODYSSEY ML ENGINE v2 — LSTM + RF DUAL MODEL — EVENT DRIVEN FORECASTING STARTED")
        self.kafka_consumer.register_handler(KafkaTopics.MARKET_DATA_RAW, self.handle_market_data)
        self.kafka_consumer.start()

# MAIN EXECUTION
if __name__ == "__main__":
    engine = MLTradingEngine()
    engine.start()
