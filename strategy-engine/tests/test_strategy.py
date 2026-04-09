import sys
import os
import pytest
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'core')))

def test_risk_manager_daily_loss():
    from multi_strategy_manager import RiskManager
    
    # Mocking QuestDB and Redis
    mock_qdb = MagicMock()
    mock_redis = MagicMock()
    
    # Init RiskManager with 6% max daily loss on 100k account = 6000
    rm = RiskManager(
        qdb=mock_qdb, 
        redis=mock_redis, 
        max_daily_loss_pct=0.06, 
        account_balance=100000
    )
    
    # Mock daily pnl to be -6500 (breaches limit)
    rm.get_daily_pnl = MagicMock(return_value=-6500.0)
    
    # Mock position count and symbol exposure to avoid breaching there
    rm.count_active_positions = MagicMock(return_value=2)
    rm.count_symbol_exposure = MagicMock(return_value=1)
    
    assert rm.check_all_limits('EURUSD') == False

def test_risk_manager_max_positions():
    from multi_strategy_manager import RiskManager
    
    mock_qdb = MagicMock()
    mock_redis = MagicMock()
    
    rm = RiskManager(qdb=mock_qdb, redis=mock_redis, max_positions=5)
    
    # Daily PNL well above limit
    rm.get_daily_pnl = MagicMock(return_value=1000.0)
    
    # 5 active positions triggers the block
    rm.count_active_positions = MagicMock(return_value=5)
    rm.count_symbol_exposure = MagicMock(return_value=0)
    
    assert rm.check_all_limits('XAUUSD') == False

@patch('redis_client.RedisClient')
@patch('questdb_client.QuestDBClient')
@patch('kafka_utils.KafkaProducerClient')
@patch('kafka_utils.KafkaConsumerClient')
def test_multi_strategy_generate_trade_order(mock_consumer, mock_prod, mock_qdb, mock_redis):
    from multi_strategy_manager import MultiStrategyManager
    
    manager = MultiStrategyManager()
    
    # Passing ensemble signal that has high confidence
    ensemble = {
        'action': 'BUY',
        'confidence': 0.85,  # Needs >= 0.65 threshold
    }
    
    market_data = {
        'close': 1950.50,
        'atr_14': 2.5     # Used for Stop Loss/Take Profit calculation
    }
    
    # Check proper order generation
    order = manager.generate_trade_order('XAUUSD', ensemble, market_data)
    
    assert order is not None
    assert order['action'] == 'BUY'
    
    # Calculate expected SL (ATR * 1.5)
    expected_sl_dist = 2.5 * 1.5
    assert round(order['sl'], 2) == round(1950.50 - expected_sl_dist, 2)
    
    # Calculate Expected TP (SL Dist * 2.0 RR)
    expected_tp_dist = expected_sl_dist * 2.0
    assert round(order['tp'], 2) == round(1950.50 + expected_tp_dist, 2)
    
    # Volume calculation check (2% risk / sl distance)
    # Risk amount = 100000 * 0.02 = 2000
    expected_volume = round((2000 / expected_sl_dist) / 100, 2)
    assert order['volume'] == max(0.01, expected_volume)

    # Missing ensemble action -> HOLD
    ensemble['action'] = 'HOLD'
    order_hold = manager.generate_trade_order('XAUUSD', ensemble, market_data)
    assert order_hold is None
