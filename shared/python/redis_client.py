"""
Redis Client for Feature Store and Caching
"""
import os
import redis
import json
from typing import Any, Optional, Dict, List
from datetime import datetime
from dotenv import load_dotenv
from logger import OdysseyLogger

load_dotenv()

_logger = OdysseyLogger('redis-client')

class RedisClient:
    """Redis client for Odyssey trading bot"""
    
    def __init__(self, host=None, port=None, db=None):
        host = host or os.getenv('REDIS_HOST', 'localhost')
        port = port or int(os.getenv('REDIS_PORT', '6379'))
        db = db if db is not None else int(os.getenv('REDIS_DB', '0'))
        """Initialize Redis connection"""
        self.client = redis.Redis(
            host=host,
            port=port,
            db=db,
            decode_responses=True,
            socket_connect_timeout=5,
            socket_keepalive=True
        )
        self._test_connection()
    
    def _test_connection(self):
        """Test Redis connection"""
        try:
            self.client.ping()
            _logger.info("Redis connected successfully")
        except redis.ConnectionError as e:
            _logger.error(f"Redis connection failed: {e}")
            raise
    
    # ==========================================
    # Feature Store Operations
    # ==========================================
    
    def set_feature(self, symbol: str, indicator: str, value: float, timestamp: int = None):
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        key = f"features:{symbol}:{indicator}"
        data = {'value': value, 'timestamp': timestamp}
        
        self.client.set(key, json.dumps(data))
        self.client.expire(key, 3600)

    def get_feature(self, symbol: str, indicator: str) -> Optional[Dict]:
        key = f"features:{symbol}:{indicator}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def set_features_batch(self, symbol: str, features: Dict[str, float], timestamp: int = None):
        if timestamp is None:
            timestamp = int(datetime.now().timestamp())
        
        pipe = self.client.pipeline()
        
        for indicator, value in features.items():
            key = f"features:{symbol}:{indicator}"
            data = {'value': value, 'timestamp': timestamp}
            pipe.set(key, json.dumps(data))
            pipe.expire(key, 3600)
        
        pipe.execute()
    
    def get_all_features(self, symbol: str) -> Dict[str, Dict]:
        pattern = f"features:{symbol}:*"
        keys = self.client.keys(pattern)
        features = {}
        
        for key in keys:
            indicator = key.split(':')[-1]
            data = self.client.get(key)
            if data:
                features[indicator] = json.loads(data)
        
        return features
    
    # ==========================================
    # ML Predictions Cache
    # ==========================================
    
    def cache_prediction(self, symbol: str, prediction: Dict):
        key = f"predictions:{symbol}:latest"
        self.client.set(key, json.dumps(prediction))
        self.client.expire(key, 300)
    
    def get_prediction(self, symbol: str) -> Optional[Dict]:
        key = f"predictions:{symbol}:latest"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    # ==========================================
    # Risk Metrics Cache
    # ==========================================
    
    def set_risk_metric(self, account_id: str, metric: str, value: float):
        key = f"risk:{account_id}:{metric}"
        self.client.set(key, value)
        self.client.expire(key, 60)
    
    def get_risk_metric(self, account_id: str, metric: str) -> Optional[float]:
        key = f"risk:{account_id}:{metric}"
        value = self.client.get(key)
        if value:
            return float(value)
        return None
    
    def get_all_risk_metrics(self, account_id: str) -> Dict[str, float]:
        pattern = f"risk:{account_id}:*"
        keys = self.client.keys(pattern)
        metrics = {}
        
        for key in keys:
            metric = key.split(':')[-1]
            value = self.client.get(key)
            if value:
                metrics[metric] = float(value)
        
        return metrics
    
    # ==========================================
    # General Cache Operations
    # ==========================================
    
    def set_cache(self, key: str, value: Any, ttl: int = 300):
        self.client.set(key, json.dumps(value))
        if ttl:
            self.client.expire(key, ttl)
    
    def get_cache(self, key: str) -> Optional[Any]:
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def delete_cache(self, key: str):
        self.client.delete(key)
    
    def clear_pattern(self, pattern: str):
        keys = self.client.keys(pattern)
        if keys:
            self.client.delete(*keys)
    
    # ==========================================
    # Session Management
    # ==========================================
    
    def set_session(self, user_id: str, session_data: Dict, ttl: int = 86400):
        key = f"session:{user_id}"
        self.client.set(key, json.dumps(session_data))
        self.client.expire(key, ttl)
    
    def get_session(self, user_id: str) -> Optional[Dict]:
        key = f"session:{user_id}"
        data = self.client.get(key)
        if data:
            return json.loads(data)
        return None
    
    def delete_session(self, user_id: str):
        key = f"session:{user_id}"
        self.client.delete(key)
    
    # ==========================================
    # Health Check
    # ==========================================
    
    def health_check(self) -> bool:
        try:
            return self.client.ping()
        except:
            return False
    
    def get_info(self) -> Dict:
        return self.client.info()
    
    def close(self):
        self.client.close()

    # ==========================================
    # NEW: Cache Signal (fixed & added correctly)
    # ==========================================
    def cache_signal(self, symbol: str, data: dict):
        key = f"signals:{symbol}:latest"
        self.client.hmset(key, data)
        self.client.expire(key, 3600)  # 1 hour TTL
    # ==========================================added
    def cache_latest_features(self, symbol: str, features: dict):
        """Cache latest technical features for ML/strategy"""
        key = f"features:{symbol}"
        self.client.hset(key, mapping=features)  # Fixed: self.client not self.r
        self.client.expire(key, 3600)  # 1 hour TTL
        _logger.info(f"Cached {len(features)} features in Redis for {symbol}")

    def get_latest_features(self, symbol: str) -> dict:
        """Get latest cached features"""
        key = f"features:{symbol}"
        data = self.client.hgetall(key)  # Fixed: self.client not self.r
        return {k: float(v) for k, v in data.items()} if data else {}


# Example usage
if __name__ == "__main__":
    redis_client = RedisClient()
    
    redis_client.set_feature('EURUSD', 'RSI_14', 65.3)
    feature = redis_client.get_feature('EURUSD', 'RSI_14')
    print(f"Feature: {feature}")
    
    features = {
        'EMA_20': 1.0885,
        'EMA_50': 1.0880,
        'MACD': 0.0005
    }
    redis_client.set_features_batch('EURUSD', features)
    
    all_features = redis_client.get_all_features('EURUSD')
    print(f"All features: {all_features}")
    
    prediction = {
        'value': 1.0890,
        'confidence': 0.85,
        'model_version': 'v1.0'
    }
    redis_client.cache_prediction('EURUSD', prediction)
    
    print(f"Redis healthy: {redis_client.health_check()}")
