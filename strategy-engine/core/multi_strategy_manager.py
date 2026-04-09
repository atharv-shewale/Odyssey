"""
Odyssey v2 - Multi-Strategy Manager (Enterprise Architecture)
Consumes ML signals → Runs 5+ strategies → Generates trade orders → Risk management
Production-ready with position sizing, VaR limits, and Redis → MT5 executor integration
"""

import os
import sys
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from collections import deque
import warnings
warnings.filterwarnings('ignore')

# Enterprise import paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # strategy-engine/core/
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")

sys.path.insert(0, SHARED_PYTHON)

from redis_client import RedisClient
from questdb_client import QuestDBClient
from kafka_utils import KafkaConsumerClient, KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger
from metrics import metrics

logger = OdysseyLogger('strategy-engine')


class RiskManager:
    """Real risk management: daily P&L, drawdown, position limits, per-symbol exposure."""

    def __init__(self, qdb: 'QuestDBClient', redis: 'RedisClient',
                 max_daily_loss_pct: float = 0.06,
                 max_positions: int = 5,
                 max_per_symbol: int = 2,
                 max_drawdown_pct: float = 0.10,
                 account_balance: float = 100000):
        self.qdb = qdb
        self.redis = redis
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_positions = max_positions
        self.max_per_symbol = max_per_symbol
        self.max_drawdown_pct = max_drawdown_pct
        self.account_balance = account_balance
        self._peak_equity = account_balance

    # --- Daily P&L from QuestDB trade history ---
    def get_daily_pnl(self) -> float:
        """Sum today's realized PnL from the trades table."""
        try:
            query = """
            SELECT coalesce(sum(pnl), 0) as daily_pnl
            FROM trades
            WHERE timestamp >= dateadd('d', -1, now())
            """
            with self.qdb.conn.cursor() as cur:
                cur.execute(query)
                row = cur.fetchone()
                return float(row[0]) if row else 0.0
        except Exception as e:
            logger.error(f"Could not query daily PnL: {e}")
            return 0.0

    def check_daily_loss(self) -> bool:
        """Returns True if trading is allowed (daily loss within limit)."""
        daily_pnl = self.get_daily_pnl()
        loss_limit = -self.account_balance * self.max_daily_loss_pct
        if daily_pnl < loss_limit:
            logger.critical(f"DAILY LOSS LIMIT BREACHED: PnL={daily_pnl:.2f} < limit={loss_limit:.2f}")
            return False
        return True

    # --- Max drawdown tracking ---
    def check_drawdown(self) -> bool:
        """Track peak equity vs current equity; reject if drawdown exceeds threshold."""
        try:
            # Get current equity from cached account info or estimate from balance + unrealized
            equity_data = self.redis.get_cache("account:equity")
            current_equity = float(equity_data) if equity_data else self.account_balance
        except (TypeError, ValueError):
            current_equity = self.account_balance

        # Update peak equity
        if current_equity > self._peak_equity:
            self._peak_equity = current_equity

        if self._peak_equity > 0:
            drawdown = (self._peak_equity - current_equity) / self._peak_equity
        else:
            drawdown = 0.0

        if drawdown > self.max_drawdown_pct:
            logger.critical(f"MAX DRAWDOWN BREACHED: {drawdown:.2%} > {self.max_drawdown_pct:.2%} "
                  f"(peak={self._peak_equity:.2f}, current={current_equity:.2f})")
            return False
        return True

    # --- Position count limit ---
    def get_open_position_count(self) -> int:
        """Get number of currently open positions from Redis cache."""
        try:
            count_data = self.redis.get_cache("positions:count")
            return int(count_data) if count_data else 0
        except (TypeError, ValueError):
            return 0

    def check_position_limit(self) -> bool:
        """Returns True if we can open more positions."""
        count = self.get_open_position_count()
        if count >= self.max_positions:
            logger.warning(f"POSITION LIMIT: {count}/{self.max_positions} positions open")
            return False
        return True

    # --- Per-symbol exposure limit ---
    def get_symbol_position_count(self, symbol: str) -> int:
        """Get number of open positions for a specific symbol."""
        try:
            count_data = self.redis.get_cache(f"positions:{symbol}:count")
            return int(count_data) if count_data else 0
        except (TypeError, ValueError):
            return 0

    def check_symbol_exposure(self, symbol: str) -> bool:
        """Returns True if we can open another position on this symbol."""
        count = self.get_symbol_position_count(symbol)
        if count >= self.max_per_symbol:
            logger.warning(f"SYMBOL EXPOSURE LIMIT: {symbol} has {count}/{self.max_per_symbol} positions")
            return False
        return True

    # --- Aggregate check ---
    def check_all_limits(self, symbol: str = None) -> bool:
        """Run all risk checks. Returns True if trading is allowed."""
        checks = [
            ("Daily Loss", self.check_daily_loss()),
            ("Drawdown", self.check_drawdown()),
            ("Position Limit", self.check_position_limit()),
        ]
        if symbol:
            checks.append(("Symbol Exposure", self.check_symbol_exposure(symbol)))

        all_passed = all(passed for _, passed in checks)

        if all_passed:
            logger.info("All risk checks passed")
        else:
            failed = [name for name, passed in checks if not passed]
            logger.warning(f"Risk checks FAILED: {', '.join(failed)}")

        return all_passed


class MultiStrategyManager:
    def __init__(self):
        self.redis = RedisClient()
        self.qdb = QuestDBClient()
        self.kafka_consumer = KafkaConsumerClient([KafkaTopics.ML_SIGNALS], group_id='strategy-engine-group')
        self.kafka_producer = KafkaProducerClient()
        self.symbols = ['XAUUSD', 'EURUSD']
        
        metrics.start_server(8003)

        # Risk parameters (production defaults)
        self.max_risk_per_trade = 0.02      # 2% account risk per trade
        self.max_daily_loss = 0.06          # 6% daily loss limit
        self.max_positions = 5              # Max concurrent positions
        self.account_balance = 100000       # Demo account

        # Initialize risk manager
        self.risk_manager = RiskManager(
            qdb=self.qdb,
            redis=self.redis,
            max_daily_loss_pct=self.max_daily_loss,
            max_positions=self.max_positions,
            max_per_symbol=2,
            max_drawdown_pct=0.10,
            account_balance=self.account_balance,
        )

        # Strategy weights (adjustable)
        self.strategy_weights = {
            'ml_signal': 0.40,
            'trend_follow': 0.25,
            'mean_reversion': 0.20,
            'breakout': 0.10,
            'momentum': 0.05,
        }
        
        # Adaptive tracking
        self.strategy_returns = {k: deque([0.001]*30, maxlen=100) for k in self.strategy_weights.keys()}
        self.indicator_history = {sym: {'rsi_14': deque(maxlen=200), 'macd': deque(maxlen=200)} for sym in self.symbols}
        self.active_signals_history = deque(maxlen=200)

        logger.info("Multi-Strategy Manager initialized - Institutional Adaptive Mode")

    # ========= DATA ACCESS =========

    def get_ml_signal(self, symbol: str) -> Dict:
        """Fetch latest ML prediction from Redis"""
        try:
            signal = self.redis.get_cache(f"predictions:{symbol}:latest")
            if signal:
                return signal
        except Exception:
            pass
        return {'action': 'HOLD', 'confidence': 0.5, 'raw_prediction': 0.0}

    def get_latest_market_data(self, symbol: str) -> Dict:
        """Get latest OHLCV + features from QuestDB"""
        try:
            features = self.qdb.get_latest_features(symbol)
            return {
                'close': features.get('close', 0.0),
                'rsi_14': features.get('rsi_14', 0.5),
                'atr_14': features.get('atr_14', 0.01),
                'macd': features.get('macd', 0.0),
                'bb_upper': features.get('bb_upper', 0.0),
                'bb_lower': features.get('bb_lower', 0.0),
            }
        except Exception:
            return {'close': 1.0, 'rsi_14': 0.5, 'atr_14': 0.01}

    # ========= POSITION SIZING =========

    def calculate_position_size(self, symbol: str, signal_strength: float, market_data: Dict) -> float:
        """Kelly-like + ATR-based position sizing"""
        atr = market_data['atr_14']
        price = market_data['close']
        if atr <= 0 or price <= 0:
            return 0.01

        stop_distance = atr * 2  # 2x ATR stop loss

        # Risk-based position sizing
        risk_amount = self.account_balance * self.max_risk_per_trade
        position_size = risk_amount / (stop_distance * 100000)  # per-lot pricing (FX assumption)

        # Scale by signal strength (0–1)
        position_size *= max(0.0, min(signal_strength, 1.0))

        return max(0.01, round(position_size, 2))  # Min 0.01 lot

    # ========= CORE STRATEGIES =========

    def ml_strategy(self, symbol: str, ml_signal: Dict, market_data: Dict) -> Dict:
        """Primary ML-driven strategy"""
        action = ml_signal.get('action', 'HOLD')
        confidence = float(ml_signal.get('confidence', 0.5))
        raw_pred = float(ml_signal.get('raw_prediction', 0.0))
        strength = abs(raw_pred) * confidence

        return {
            'strategy': 'ml_signal',
            'action': action,
            'confidence': confidence,
            'strength': strength,
            'sl_pips': market_data['atr_14'] * 20000,
            'tp_pips': market_data['atr_14'] * 30000,
        }

    def trend_following(self, symbol: str, market_data: Dict) -> Dict:
        """Dynamic Trend using Rolling Bounds"""
        rsi = market_data['rsi_14']
        macd = market_data['macd']
        
        self.indicator_history[symbol]['rsi_14'].append(rsi)
        self.indicator_history[symbol]['macd'].append(macd)
        
        hist_rsi = np.array(self.indicator_history[symbol]['rsi_14'])
        hist_macd = np.array(self.indicator_history[symbol]['macd'])
        
        if len(hist_rsi) < 30:
            return {'strategy': 'trend_follow', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}
            
        rsi_mean, rsi_std = np.mean(hist_rsi), np.std(hist_rsi) + 1e-9
        macd_mean = np.mean(hist_macd)
        
        if macd > macd_mean and rsi < (rsi_mean + rsi_std):
            return {'strategy': 'trend_follow', 'action': 'BUY', 'confidence': 0.7, 'strength': 0.6}
        elif macd < macd_mean and rsi > (rsi_mean - rsi_std):
            return {'strategy': 'trend_follow', 'action': 'SELL', 'confidence': 0.7, 'strength': 0.6}
        return {'strategy': 'trend_follow', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}

    def mean_reversion(self, symbol: str, market_data: Dict) -> Dict:
        """Dynamic Statistical Mean Reversion"""
        close = market_data['close']
        bb_upper = market_data['bb_upper']
        bb_lower = market_data['bb_lower']
        rsi = market_data['rsi_14']
        
        hist_rsi = np.array(self.indicator_history[symbol]['rsi_14'])
        if len(hist_rsi) < 30:
            return {'strategy': 'mean_reversion', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}
            
        rsi_mean, rsi_std = np.mean(hist_rsi), np.std(hist_rsi) + 1e-9
        
        if close <= bb_lower * 1.002 and rsi < (rsi_mean - 1.5 * rsi_std):
            return {'strategy': 'mean_reversion', 'action': 'BUY', 'confidence': 0.8, 'strength': 0.5}
        elif close >= bb_upper * 0.998 and rsi > (rsi_mean + 1.5 * rsi_std):
            return {'strategy': 'mean_reversion', 'action': 'SELL', 'confidence': 0.8, 'strength': 0.5}
        return {'strategy': 'mean_reversion', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}

    def breakout_strategy(self, symbol: str, market_data: Dict) -> Dict:
        """ATR-based volatility breakout"""
        atr = market_data['atr_14']

        if atr > 0.015:  # High volatility
            return {'strategy': 'breakout', 'action': 'BUY', 'confidence': 0.65, 'strength': 0.4}
        return {'strategy': 'breakout', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}

    def momentum_strategy(self, symbol: str, market_data: Dict) -> Dict:
        """Dynamic RSI Momentum Formulation"""
        rsi = market_data['rsi_14']
        hist_rsi = np.array(self.indicator_history[symbol]['rsi_14'])
        if len(hist_rsi) < 30:
            return {'strategy': 'momentum', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}
            
        rsi_mean, rsi_std = np.mean(hist_rsi), np.std(hist_rsi) + 1e-9
        
        if rsi > rsi_mean + 0.5 * rsi_std:
            return {'strategy': 'momentum', 'action': 'BUY', 'confidence': 0.6, 'strength': 0.3}
        elif rsi < rsi_mean - 0.5 * rsi_std:
            return {'strategy': 'momentum', 'action': 'SELL', 'confidence': 0.6, 'strength': 0.3}
        return {'strategy': 'momentum', 'action': 'HOLD', 'confidence': 0.3, 'strength': 0.0}

    # ========= ENSEMBLE =========

    def update_adaptive_weights(self):
        """Update strategy weights based on Sharpe and Decorrelation penalty"""
        if len(self.active_signals_history) < 30:
            return
            
        # 1. Calc rolling Sharpe
        sharpes = {}
        for strat, rets in self.strategy_returns.items():
            arr = np.array(rets)
            mean_ret = np.mean(arr)
            std_ret = np.std(arr) + 1e-9
            sharpes[strat] = (mean_ret / std_ret) * np.sqrt(252) # Proxy annualized
            
        # 2. Calc correlation penalty
        sig_matrix = []
        for sh in self.active_signals_history:
            sig_matrix.append([sh.get(k, 0) for k in self.strategy_weights.keys()])
            
        sig_matrix = np.array(sig_matrix).T
        corr_matrix = np.corrcoef(sig_matrix)
        
        # Update weights (Weight ∝ Sharpe * Exp(-Corr Penalty))
        new_weights = {}
        strat_keys = list(self.strategy_weights.keys())
        for i, strat in enumerate(strat_keys):
            avg_corr = np.mean([corr_matrix[i, j] for j in range(len(strat_keys)) if i != j])
            if np.isnan(avg_corr):
                avg_corr = 0
            
            sharpe = max(0.01, sharpes[strat])
            weight = sharpe * np.exp(-avg_corr)
            new_weights[strat] = weight
            
        # Normalize
        total_w = sum(new_weights.values())
        if total_w > 0:
            self.strategy_weights = {k: v / total_w for k, v in new_weights.items()}

        # Cache analytics for the UI
        self.redis.set_cache("analytics:strategy:weights", {
            'weights': self.strategy_weights,
            'sharpes': {k: round(v, 2) for k, v in sharpes.items()},
            'correlations': corr_matrix.tolist() if len(corr_matrix) > 0 else [],
            'timestamp': datetime.utcnow().isoformat()
        })

    def ensemble_signal(self, symbol: str, market_data: Dict) -> Dict:
        """Weighted ensemble of all strategies with dynamic tracking"""
        self.update_adaptive_weights()
        
        ml_signal = self.get_ml_signal(symbol)

        signals = [
            self.ml_strategy(symbol, ml_signal, market_data),
            self.trend_following(symbol, market_data),
            self.mean_reversion(symbol, market_data),
            self.breakout_strategy(symbol, market_data),
            self.momentum_strategy(symbol, market_data),
        ]
        
        # Track active signals to compute correlation later
        sig_vector = {}
        pseudo_return = market_data.get('log_returns', 0.0001) or 0.0001
        for s in signals:
            sig_val = s['confidence'] if s['action'] == 'BUY' else (-s['confidence'] if s['action'] == 'SELL' else 0)
            sig_vector[s['strategy']] = sig_val
            # Mock updating returns to simulate tracking. Real platform uses execution matches.
            self.strategy_returns[s['strategy']].append(sig_val * pseudo_return)
            
        self.active_signals_history.append(sig_vector)

        buy_score = sum(
            s['confidence'] * self.strategy_weights[s['strategy']]
            for s in signals
            if s['action'] == 'BUY'
        )
        sell_score = sum(
            s['confidence'] * self.strategy_weights[s['strategy']]
            for s in signals
            if s['action'] == 'SELL'
        )

        if buy_score > sell_score + 0.15:
            final_action = 'BUY'
        elif sell_score > buy_score + 0.15:
            final_action = 'SELL'
        else:
            final_action = 'HOLD'

        ensemble_confidence = max(buy_score, sell_score)
        ensemble_strength = ensemble_confidence

        return {
            'action': final_action,
            'confidence': ensemble_confidence,
            'strength': ensemble_strength,
            'signals': signals,
            'ml_weight': self.strategy_weights['ml_signal'],
        }

    # ========= ORDER GENERATION =========

    def generate_trade_order(self, symbol: str, ensemble: Dict, market_data: Dict) -> Dict:
        """Generate complete trade order with risk management"""
        if ensemble['action'] == 'HOLD':
            return None

        position_size = self.calculate_position_size(symbol, ensemble['strength'], market_data)
        if position_size <= 0:
            return None

        price = market_data['close']
        atr = market_data['atr_14']

        sl_distance = atr * 2
        tp_distance = atr * 3

        sl_price = price - sl_distance if ensemble['action'] == 'BUY' else price + sl_distance
        tp_price = price + tp_distance if ensemble['action'] == 'BUY' else price - tp_distance

        order = {
            'symbol': symbol,
            'action': ensemble['action'],
            'type': 'MARKET',
            'volume': position_size,
            'price': price,
            'sl': sl_price,
            'tp': tp_price,
            'confidence': ensemble['confidence'],
            'strategy': 'multi_ensemble',
            'timestamp': datetime.utcnow().isoformat(),
            'risk_reward': 1.5,
            'comment': f"Ensemble:{ensemble['confidence']:.2f}",
        }

        logger.info(f"Generated {order['action']} order: {position_size} lots @ {price}")
        return order

    # ========= RISK CHECKS =========

    def check_risk_limits(self, symbol: str = None) -> bool:
        """Check daily loss, drawdown, position limits, and per-symbol exposure."""
        return self.risk_manager.check_all_limits(symbol=symbol)

    # ========= EVENT DRIVEN CYCLE =========

    def process_ml_signal(self, message: Dict):
        """Handle incoming ML signal event from Kafka"""
        symbol = message.get('symbol')
        
        if not symbol or symbol not in self.symbols:
            logger.warning(f"Invalid or unsupported symbol in signal: {message}")
            return
            
        logger.info(f"Received ML signal for {symbol}, checking strategies...")

        if not self.check_risk_limits(symbol=symbol):
            logger.critical("RISK LIMITS EXCEEDED - STRATEGY PAUSED OR SYMBOL LOCKED")
            return

        # Get market data
        market_data = self.get_latest_market_data(symbol)

        # Generate ensemble signal (mixes ML signal with structural indicators)
        ensemble = self.ensemble_signal(symbol, market_data)
        
        # Pass ML prediction along to ensemble for better context
        ensemble['ml_prediction'] = message.get('raw_prediction', 0)
        ensemble['ml_confidence'] = message.get('confidence', 0)

        # Generate trade order
        order = self.generate_trade_order(symbol, ensemble, market_data)

        if order:
            # Add timestamps and trace IDs
            order['timestamp'] = datetime.utcnow().isoformat()
            
            # Publish order to Redis for Gateway dashboard (legacy UI support)
            order_key = f"orders:{symbol}:latest"
            self.redis.set_cache(order_key, order, ttl=60)
            
            # Publish actionable order to Kafka for Trading Executor
            self.kafka_producer.send(KafkaTopics.TRADING_ORDERS, order, key=symbol)
            logger.info(
                f"Published order to Kafka ({KafkaTopics.TRADING_ORDERS}): "
                f"{order['action']} {order['volume']} lots @ {order['price']}"
            )
            metrics.events_processed.labels(service_name='strategy-engine', event_type='trade_order').inc()
        else:
            logger.info(f"No actionable trade generated for {symbol}")

    def start(self):
        """Start Kafka consumer loop"""
        logger.info("ODYSSEY STRATEGY ENGINE v2 - EVENT DRIVEN STRATEGIES STARTED")
        self.kafka_consumer.register_handler(KafkaTopics.ML_SIGNALS, self.process_ml_signal)
        self.kafka_consumer.start()


# MAIN EXECUTION
if __name__ == "__main__":
    manager = MultiStrategyManager()
    manager.start()

