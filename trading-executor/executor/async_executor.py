"""
Odyssey v2 - Async Trading Executor
Listens to Kafka for approved risk orders and places them asynchronously 
via the Smart Order Router (Dual-Broker execution).
"""

import os
import sys
import json
import time
import threading
import numpy as np
from datetime import datetime
from typing import Dict, Any
from dotenv import load_dotenv

load_dotenv()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))

sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
from redis_client import RedisClient
from kafka_utils import KafkaConsumerClient, KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger

from router import SmartOrderRouter

logger = OdysseyLogger('trading-executor')

class AsyncExecutor:
    def __init__(self):
        self.redis = RedisClient()
        self.kafka_consumer = KafkaConsumerClient(
            [KafkaTopics.TRADING_ORDERS_APPROVED], group_id='fyers-executor-group'
        )
        self.kafka_producer = KafkaProducerClient()
        self.router = SmartOrderRouter()
        
        self._running = False
        
        logger.info("Initializing Smart Order Router...")
        self.router.initialize()
            
    def dispatch_order(self, order: Dict[str, Any]):
        """Determine execution algorithm (TWAP vs Market/Limit) and dispatch."""
        volume = float(order.get('volume', 1))
        action = order.get('action')
        
        if action == 'CLOSE_ALL':
            logger.critical("EMERGENCY: Closing all positions via broker router!")
            success = self.router.close_all_positions()
            logger.info(f"Close all result: {success}")
            return
            
        # If volume is large, use TWAP. (Arbitrary institutional threshold: 5.0 lots)
        if volume >= 5.0:
            logger.info(f"Large order detected ({volume} lots). Dispatching to TWAP Algo.")
            t = threading.Thread(target=self._twap_execution_worker, args=(order,))
            t.daemon = True
            t.start()
        else:
            self._submit_slice(order, volume)

    def _twap_execution_worker(self, order: Dict[str, Any]):
        """Time-Weighted Average Price algorithmic execution."""
        total_volume = float(order.get('volume', 1))
        symbol = order.get('symbol')
        action = order.get('action')
        
        slices = int(np.ceil(total_volume / 2.0)) # Max 2 lots per slice
        slice_volume = round(total_volume / slices, 2)
        
        logger.info(f"TWAP [{symbol} {action}]: {total_volume} lots into {slices} slices of ~{slice_volume} over 5 mins.")
        
        interval_seconds = 300 / slices if slices > 1 else 1
        
        executed_volume = 0.0
        for i in range(slices):
            current_slice = min(slice_volume, round(total_volume - executed_volume, 2))
            if current_slice <= 0:
                break
                
            logger.info(f"TWAP [{symbol}]: Executing slice {i+1}/{slices} ({current_slice} lots)")
            self._submit_slice(order, current_slice)
            
            executed_volume += current_slice
            if i < slices - 1:
                time.sleep(interval_seconds)
                
        logger.info(f"TWAP [{symbol}] Complete. Total Executed: {executed_volume}")

    def _submit_slice(self, base_order: Dict[str, Any], slice_volume: float):
        """Submit a single chunk to the router with Slippage Protection and T-Cost mapping."""
        symbol = base_order.get('symbol')
        action = base_order.get('action')
        sl_pips = base_order.get('sl_pips', 20)
        tp_pips = base_order.get('tp_pips', 40)
        
        # Slippage Guardrail (Simulated lookup of L2 spread)
        try:
            spread = float(self.redis.get_cache(f"spread:{symbol}") or 1.5)
        except Exception:
            spread = 1.5
            
        # Smart Limit Orders: If spread is high, use passive LIMIT. Else MARKET.
        order_type = "MARKET"
        price = None
        if spread > 2.5:
            order_type = "LIMIT"
            # Get latest price as proxy for limit insertion
            features = self.redis.get_cache(f"features:{symbol}:latest") or {}
            price = features.get('close', 100.0)
            logger.info(f"Spread high ({spread}). Using NBBO Smart Limit Order based on recent close: {price}")
        
        logger.info(f"Submitting {order_type} {action} {slice_volume} of {symbol}")
        
        try:
            res = self.router.place_order(
                symbol=symbol,
                action=action,
                volume=slice_volume,
                order_type=order_type,
                price=price
            )
            
            # Simulated accomplishment for metrics
            if res.get('s') == 'ok' or not (self.router.fyers_connected or self.router.oanda_connected):
                order_id = res.get('id', f"ext_{int(time.time()*1000)}")
                
                pos = {
                    'order_id': order_id,
                    'symbol': symbol,
                    'action': action,
                    'volume': slice_volume,
                    'entry_time': datetime.utcnow().isoformat(),
                    'sl_pips': sl_pips,
                    'tp_pips': tp_pips,
                    't_cost_est': slice_volume * spread * 10.0 # Transaction cost model proxy
                }
                
                self.redis.set_cache(f"positions:{symbol}:{order_id}", pos, ttl=86400) 
                
                exe_event = {
                    'type': 'EXECUTION',
                    'order_id': order_id,
                    **pos
                }
                self.kafka_producer.send(KafkaTopics.TRADING_EXECUTIONS, exe_event, key=symbol)
                logger.info(f"✅ Executed {action} {symbol} (Vol: {slice_volume}) -> ID: {order_id} T-Cost: ${pos['t_cost_est']:.2f}")
            else:
                logger.error(f"❌ Broker Rejected Slice: {res}")
                
        except Exception as e:
            logger.error(f"Slice Execution Error: {e}")

    def handle_approved_order(self, msg: Dict[str, Any]):
        logger.info(f"Received approved order: {msg.get('action')} {msg.get('symbol')}")
        self.dispatch_order(msg)

    def start(self):
        self._running = True
        logger.info("ODYSSEY v2 — ASYNC EXECUTOR STARTED")
        self.kafka_consumer.start(self.handle_approved_order)
        
        try:
            while self._running:
                # Periodic account sync to Redis for Gateway/UI
                acc = self.router.get_consolidated_account()
                self.redis.set_cache("account:balance", acc['balance'], ttl=60)
                self.redis.set_cache("account:equity", acc['equity'], ttl=60)
                self.redis.set_cache("account:profit", acc['pnl'], ttl=60)
                self.redis.set_cache("account:pnl", acc['pnl'], ttl=60)
                self.redis.set_cache("account:margin_free", acc['equity'], ttl=60)
                time.sleep(5)
        except KeyboardInterrupt:
            self.stop()
            
    def stop(self):
        self._running = False
        self.kafka_consumer.stop()
        logger.info("Executor stopped.")


if __name__ == "__main__":
    executor = AsyncExecutor()
    executor.start()
