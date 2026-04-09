import sys
import os
import pytest
import numpy as np
from unittest.mock import MagicMock, patch

# Add parent to path to allow relative imports inside test environment
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

@patch('redis_client.RedisClient')
@patch('questdb_client.QuestDBClient')
@patch('kafka_utils.KafkaProducerClient')
@patch('kafka_utils.KafkaConsumerClient')
def test_ml_engine_initialization(mock_consumer, mock_producer, mock_qdb, mock_redis):
    from ml_engine import MLTradingEngine
    engine = MLTradingEngine()
    
    assert engine.symbols == ['XAUUSD', 'EURUSD']
    assert len(engine.feature_order) == 17
    assert engine.primary_model is not None
    assert engine.shadow_model is not None

@patch('redis_client.RedisClient')
@patch('questdb_client.QuestDBClient')
@patch('kafka_utils.KafkaProducerClient')
@patch('kafka_utils.KafkaConsumerClient')
def test_ml_engine_get_features_vector(mock_consumer, mock_producer, mock_qdb, mock_redis):
    from ml_engine import MLTradingEngine
    engine = MLTradingEngine()
    
    # Test dictionary with partial features
    dummy_features = {
        'rsi_14': 0.75,
        'macd': 0.0012,
        'close': 1.0850
    }
    
    vector = engine.get_features_vector(dummy_features)
    
    assert isinstance(vector, np.ndarray)
    assert vector.shape == (1, 17)
    assert vector[0][0] == 0.75  # rsi_14 mapped
    assert vector[0][1] == 0.50  # missing stoch_k mapped to 0.50

@patch('redis_client.RedisClient')
@patch('questdb_client.QuestDBClient')
@patch('kafka_utils.KafkaProducerClient')
@patch('kafka_utils.KafkaConsumerClient')
def test_ml_engine_generate_signal(mock_consumer, mock_producer, mock_qdb, mock_redis):
    from ml_engine import MLTradingEngine
    engine = MLTradingEngine()
    
    # Test Strong Buy
    signal = engine.generate_signal('EURUSD', 0.03, 0.85)
    assert signal['action'] == 'BUY'
    assert signal['strength'] == 'STRONG'
    
    # Test Sell
    signal = engine.generate_signal('XAUUSD', -0.016, 0.80)
    assert signal['action'] == 'SELL'
    assert signal['strength'] == 'MEDIUM'
    
    # Test Hold (low confidence)
    signal = engine.generate_signal('EURUSD', 0.04, 0.50)
    assert signal['action'] == 'HOLD'
