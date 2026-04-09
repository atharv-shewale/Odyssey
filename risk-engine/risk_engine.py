"""
Odyssey v2 - Risk Engine Microservice
Kafka-connected risk gate between Strategy Engine and Trading Executor.
Validates every order against portfolio-level risk analytics before forwarding.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, Optional
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

load_dotenv()

# Import paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")

sys.path.insert(0, SHARED_PYTHON)
sys.path.insert(0, CURRENT_DIR)

from redis_client import RedisClient
from questdb_client import QuestDBClient
from kafka_utils import KafkaConsumerClient, KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger
from metrics import metrics

from analytics.portfolio_var import PortfolioVaR
from analytics.correlation_matrix import CorrelationMatrix
from analytics.position_sizer import KellyPositionSizer
from analytics.circuit_breaker import CircuitBreaker, AlertLevel

logger = OdysseyLogger('risk-engine')


class RiskEngine:
    """
    Portfolio-level risk engine that intercepts orders and validates them
    against VaR limits, correlation exposure, position sizing rules,
    and drawdown circuit breakers.
    """

    # Dynamic Pip values will be loaded from Broker/Redis
    # Fallbacks in case broker metadata is unavailable
    DEFAULT_PIP_VALUES = {
        'EURUSD': 10.0,
        'GBPUSD': 10.0,
        'USDJPY': 6.8,
        'XAUUSD': 10.0,
    }

    def __init__(self):
        # Infrastructure
        self.redis = RedisClient()
        self.qdb = QuestDBClient()
        self.kafka_consumer = KafkaConsumerClient(
            [KafkaTopics.TRADING_ORDERS], group_id='risk-engine-group'
        )
        self.kafka_producer = KafkaProducerClient()

        metrics.start_server(8005)

        # Account state
        self.account_balance = float(os.getenv('ACCOUNT_BALANCE', '100000'))
        self.symbols = ['XAUUSD', 'EURUSD', 'GBPUSD', 'USDJPY']

        # ============================
        # Analytics engines
        # ============================
        self.var_engine = PortfolioVaR(
            confidence_levels=[0.95, 0.99],
            n_simulations=10000,
            horizon_days=1,
        )
        self.correlation = CorrelationMatrix(
            window=60,
            max_correlation=0.75,
            max_currency_exposure=3.0,
        )
        self.sizer = KellyPositionSizer(
            account_balance=self.account_balance,
            max_risk_per_trade=0.02,
            max_portfolio_heat=0.10,
            kelly_fraction=0.5,
        )
        self.circuit_breaker = CircuitBreaker(
            account_balance=self.account_balance,
        )

        # Load historical data for VaR and correlation
        self._load_historical_data()

        logger.info(f"Risk Engine initialized — account=${self.account_balance:,.0f}")

    def _load_historical_data(self):
        """Seed initial volatility and VaR using live QuestDB query (EWMA style streaming)."""
        logger.info("Initializing Risk Metrics from live QuestDB...")
        for symbol in self.symbols:
            try:
                # Get last 10,000 prices (approx 1 week of M1) to seed correlation/VaR
                prices, _ = self.qdb.get_history(symbol, "M1", 10000)
                if len(prices) > 100:
                    self.var_engine.load_returns_from_prices(symbol, prices)
                    self.correlation.load_returns(symbol, prices)
                    logger.info(f"Loaded {len(prices)} live history bars for {symbol}")
                else:
                    logger.warning(f"Insufficient live history for {symbol}")
            except Exception as e:
                logger.warning(f"Failed to seed live data for {symbol}: {e}")

    def get_pip_value(self, symbol: str) -> float:
        """Dynamically determine pip value from broker metadata in Redis."""
        try:
            meta = self.redis.get_cache(f"symbol_meta:{symbol}")
            if meta and 'pip_value' in meta:
                return float(meta['pip_value'])
        except Exception:
            pass
        return self.DEFAULT_PIP_VALUES.get(symbol, 10.0)

    def _get_open_positions(self) -> Dict[str, Dict]:
        """Get current open positions from Redis cache."""
        positions = {}
        for symbol in self.symbols:
            try:
                pos_data = self.redis.get_cache(f"positions:{symbol}:active")
                if pos_data:
                    positions[symbol] = pos_data
            except Exception:
                pass
        return positions

    def _get_current_equity(self) -> float:
        """Get current equity from Redis or fallback to balance."""
        try:
            equity = self.redis.get_cache("account:equity")
            if equity:
                return float(equity)
        except (TypeError, ValueError):
            pass
        return self.account_balance

    def validate_order(self, order: Dict) -> Dict:
        """
        Run all risk checks on an incoming order.
        Returns the order with risk annotations (approved/rejected/modified).
        """
        symbol = order.get('symbol', '')
        action = order.get('action', 'HOLD')
        volume = float(order.get('volume', 0))
        confidence = float(order.get('confidence', 0.5))

        if action == 'HOLD' or volume <= 0:
            return {**order, 'risk_approved': False, 'risk_reason': 'No actionable order'}

        result = {
            **order,
            'risk_checks': {},
            'risk_approved': True,
        }

        open_positions = self._get_open_positions()
        current_equity = self._get_current_equity()

        # ============================
        # 1. Circuit Breaker
        # ============================
        cb_approved, cb_details = self.circuit_breaker.check_order(current_equity, order)
        result['risk_checks']['circuit_breaker'] = cb_details

        if not cb_approved:
            result['risk_approved'] = False
            result['risk_reason'] = cb_details.get('rejection_reason', 'Circuit breaker triggered')
            logger.critical(f"CIRCUIT BREAKER REJECTED: {symbol} {action} — {cb_details['circuit_breaker']['level']}")

            if cb_details.get('close_all'):
                result['close_all_positions'] = True

            return result

        # Apply circuit breaker volume adjustment
        if cb_details.get('volume') is not None and cb_details['volume'] != volume:
            logger.warning(f"Circuit breaker reduced volume: {volume} → {cb_details['volume']}")
            volume = cb_details['volume']
            result['volume'] = volume

        # ============================
        # 2. VaR Check
        # ============================
        try:
            # Build position map with the new order included
            position_values = {}
            for sym, pos in open_positions.items():
                position_values[sym] = float(pos.get('value', 0))

            # Add proposed position value
            pip_value = self.get_pip_value(symbol)
            atr_pips = float(order.get('sl_pips', 20))
            proposed_value = volume * atr_pips * pip_value
            position_values[symbol] = position_values.get(symbol, 0) + proposed_value

            var_ok, var_details = self.var_engine.check_var_limit(
                position_values,
                max_var_pct=0.05,
                account_balance=self.account_balance,
            )
            result['risk_checks']['var'] = var_details.get('risk_check', {})

            if not var_ok:
                result['risk_approved'] = False
                result['risk_reason'] = f"VaR limit exceeded: {var_details['risk_check']['current_var_99']:.2f} > {var_details['risk_check']['max_var_usd']:.2f}"
                logger.warning(f"VAR REJECTED: {symbol} — {result['risk_reason']}")
                return result

        except Exception as e:
            logger.warning(f"VaR check failed (allowing order): {e}")
            result['risk_checks']['var'] = {'error': str(e), 'approved': True}

        # ============================
        # 3. Correlation Check
        # ============================
        try:
            pos_map = {}
            for sym, pos in open_positions.items():
                pos_map[sym] = {
                    'direction': pos.get('direction', 'BUY'),
                    'volume': float(pos.get('volume', 0)),
                }

            corr_ok, corr_details = self.correlation.check_correlation_risk(
                symbol, action, volume, pos_map
            )
            result['risk_checks']['correlation'] = {
                'approved': corr_ok,
                'flags': corr_details.get('flags', []),
                'currency_exposure': corr_details.get('currency_exposure', {}),
            }

            if not corr_ok:
                result['risk_approved'] = False
                flags_str = '; '.join(f['detail'] for f in corr_details['flags'])
                result['risk_reason'] = f"Correlation risk: {flags_str}"
                logger.warning(f"CORRELATION REJECTED: {symbol} — {result['risk_reason']}")
                return result

        except Exception as e:
            logger.warning(f"Correlation check failed (allowing order): {e}")
            result['risk_checks']['correlation'] = {'error': str(e), 'approved': True}

        # ============================
        # 4. Kelly Position Sizing
        # ============================
        try:
            sl_pips = float(order.get('sl_pips', 20))
            pip_value = self.get_pip_value(symbol)

            pos_for_heat = {}
            for sym, pos in open_positions.items():
                pos_for_heat[sym] = {
                    'volume': float(pos.get('volume', 0)),
                    'risk_usd': float(pos.get('risk_usd', 0)),
                }

            sizing = self.sizer.calculate_position_size(
                symbol=symbol,
                direction=action,
                confidence=confidence,
                stop_loss_pips=sl_pips,
                pip_value=pip_value,
                open_positions=pos_for_heat,
            )
            result['risk_checks']['kelly_sizing'] = sizing

            # Use Kelly-adjusted volume (take the minimum of original and Kelly)
            kelly_vol = sizing['volume']
            if kelly_vol < volume:
                logger.info(f"Kelly resized: {volume} → {kelly_vol} lots")
                result['volume'] = kelly_vol

        except Exception as e:
            logger.warning(f"Kelly sizing failed (using original volume): {e}")
            result['risk_checks']['kelly_sizing'] = {'error': str(e)}

        # ============================
        # Final approval
        # ============================
        if result['risk_approved']:
            logger.info(
                f"RISK APPROVED: {action} {result['volume']} lots {symbol} "
                f"(original={order.get('volume')}, confidence={confidence:.2f})"
            )

        return result

    def handle_order(self, message: Dict):
        """Kafka handler: validate order and forward if approved."""
        symbol = message.get('symbol', 'UNKNOWN')
        logger.info(f"Risk Engine received order for {symbol}")

        validated = self.validate_order(message)

        if validated.get('risk_approved'):
            # Forward approved order
            self.kafka_producer.send(
                KafkaTopics.TRADING_ORDERS_APPROVED,
                validated,
                key=symbol,
            )
            logger.info(f"Order FORWARDED to executor: {validated['action']} {validated['volume']} {symbol}")
            metrics.events_processed.labels(service_name='risk-engine', event_type='order_approved').inc()
        else:
            logger.warning(f"Order REJECTED: {validated.get('risk_reason', 'Unknown')}")
            metrics.events_processed.labels(service_name='risk-engine', event_type='order_rejected').inc()

            # Publish rejection event (for audit/dashboard)
            rejection = {
                'symbol': symbol,
                'action': 'REJECTED',
                'reason': validated.get('risk_reason', 'Risk check failed'),
                'timestamp': datetime.utcnow().isoformat(),
                'details': validated.get('risk_checks', {}),
            }
            self.redis.set_cache(f"risk:rejections:{symbol}:latest", rejection, ttl=300)
            
            # Send Telegram alert for hard rejections 
            alert = {"type": "RISK_REJECTION", **rejection}
            self.kafka_producer.send(KafkaTopics.ALERTS, alert, key=symbol)

            # Handle emergency close-all
            if validated.get('close_all_positions'):
                logger.critical("EMERGENCY: Publishing CLOSE_ALL signal")
                self.kafka_producer.send(
                    KafkaTopics.TRADING_ORDERS_APPROVED,
                    {'action': 'CLOSE_ALL', 'reason': 'Circuit breaker L3', 'timestamp': datetime.utcnow().isoformat()},
                    key='SYSTEM',
                )
                
                # Send emergency circuit breaker alert
                self.kafka_producer.send(
                    KafkaTopics.ALERTS,
                    {"type": "CIRCUIT_BREAKER", "level": "L3", "drawdown": 0.10, "action": "CLOSE_ALL_POSITIONS"},
                    key="SYSTEM"
                )

    def start(self):
        """Start Kafka consumer loop."""
        logger.info("ODYSSEY RISK ENGINE v1 — PORTFOLIO GUARDIAN STARTED")
        logger.info(f"  VaR: {self.var_engine.n_simulations} Monte Carlo simulations")
        logger.info(f"  Correlation: max={self.correlation.max_correlation}, currency_limit={self.correlation.max_currency_exposure}")
        logger.info(f"  Kelly: fraction={self.sizer.kelly_fraction}, max_heat={self.sizer.max_portfolio_heat}")
        logger.info(f"  Circuit Breaker: L1={self.circuit_breaker.thresholds[AlertLevel.LEVEL_1]:.0%}, "
                     f"L2={self.circuit_breaker.thresholds[AlertLevel.LEVEL_2]:.0%}, "
                     f"L3={self.circuit_breaker.thresholds[AlertLevel.LEVEL_3]:.0%}")

        self.kafka_consumer.register_handler(KafkaTopics.TRADING_ORDERS, self.handle_order)
        self.kafka_consumer.start()


# MAIN EXECUTION
if __name__ == "__main__":
    engine = RiskEngine()
    engine.start()
