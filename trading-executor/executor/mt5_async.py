import os
import sys
import asyncio
import MetaTrader5 as mt5
from datetime import datetime
from typing import Dict, List
import threading
import queue
import warnings
warnings.filterwarnings('ignore')
from dotenv import load_dotenv

load_dotenv()

# =========================
# Enterprise import paths
# =========================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))  # trading-executor/executor/
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")
DATA_SERVICE_CONFIG = os.path.join(PROJECT_ROOT, "data-service", "config")

sys.path.insert(0, SHARED_PYTHON)
sys.path.insert(0, DATA_SERVICE_CONFIG)

from redis_client import RedisClient
from questdb_client import QuestDBClient
from kafka_utils import KafkaConsumerClient, KafkaProducerClient, KafkaTopics
from mt5_config import MT5_CONFIG  # stays in data-service/config/mt5_config.py
from logger import OdysseyLogger
from metrics import metrics

logger = OdysseyLogger('trading-executor')

class MT5TradingExecutor:
    def __init__(self):
        self.redis = RedisClient()
        self.qdb = QuestDBClient()
        self.kafka_producer = KafkaProducerClient()
        self.kafka_consumer = KafkaConsumerClient([KafkaTopics.TRADING_ORDERS_APPROVED], group_id='trading-executor')
        
        # Thread-safe queue to bridge Kafka consumer and asyncio executor
        self.order_queue = queue.Queue()
        
        # IMPORTANT: ensure these match your broker symbols exactly
        self.symbols = ['XAUUSD', 'EURUSD']
        self.account_balance = 100000
        self.max_positions = 5
        
        metrics.start_server(8004)

        # MT5 connection status
        self.mt5_initialized = False
        self.mt5_path = os.getenv('MT5_PATH', r"C:\Program Files\MetaTrader 5\terminal64.exe")

        logger.info("Initializing MT5 Trading Executor...")
        self._initialize_mt5()
        self.start_kafka_listener()

        if self.mt5_initialized:
            logger.info("MT5 Trading Executor ready - LIVE TRADING MODE")
        else:
            logger.warning("MT5 NOT READY - Check terminal/login")

    # =========================
    # MT5 INIT
    # =========================
    def _initialize_mt5(self):
        """Initialize MT5 using your mt5_config.py"""
        try:
            if MT5_CONFIG and MT5_CONFIG != {}:
                login = MT5_CONFIG.get('login')
                password = MT5_CONFIG.get('password')
                server = MT5_CONFIG.get('server')

                logger.info(f"Using MT5 config: login={login}, server={server[:8]}...")

                if not mt5.initialize(
                    path=self.mt5_path,
                    login=login,
                    password=password,
                    server=server,
                ):
                    logger.error(f"MT5 explicit login failed: {mt5.last_error()}")
                    return
            else:
                logger.info("Using currently logged-in MT5 terminal...")
                if not mt5.initialize(path=self.mt5_path):
                    logger.error(f"MT5 terminal connection failed: {mt5.last_error()}")
                    return

            self.mt5_initialized = True
            account_info = mt5.account_info()
            if account_info:
                logger.info(
                    f"MT5 Connected: Account {account_info.login} | "
                    f"Balance: ${account_info.balance:,.2f} | Equity: ${account_info.equity:,.2f}"
                )
                self.account_balance = account_info.balance
            else:
                logger.warning("MT5 connected but no account info")

        except Exception as e:
            logger.error(f"MT5 initialization exception: {e}")

    # =========================
    # ORDER SOURCE (Kafka)
    # =========================
    def get_queued_orders(self) -> List[Dict]:
        """Fetch pending trade orders from the thread-safe queue populated by Kafka"""
        orders: List[Dict] = []
        while not self.order_queue.empty():
            try:
                order_data = self.order_queue.get_nowait()
                if order_data and order_data.get('action') != 'HOLD':
                    # Optional legacy compatibility check if symbol wasn't passed directly:
                    if 'symbol' not in order_data:
                        logger.warning("Order payload missing symbol! Skipping...")
                        continue
                        
                    orders.append(order_data)
                    logger.info(f"Picked up Kafka order: {order_data['action']} {order_data['symbol']} @ {order_data['price']}")
                
                self.order_queue.task_done()
            except queue.Empty:
                break
            except Exception as e:
                logger.error(f"Error processing order from queue: {e}")
                
        return orders

    # =========================
    # EXECUTION
    # =========================
    async def execute_order(self, order: Dict) -> Dict:
        """Execute single trade order on MT5"""
        if not self.mt5_initialized:
            return {'status': 'ERROR', 'message': 'MT5 not initialized'}

        symbol = order['symbol']
        action = order['action'].upper()
        volume = float(order['volume'])
        sl = float(order.get('sl', 0))
        tp = float(order.get('tp', 0))

        # Ensure symbol exists and is visible
        info = mt5.symbol_info(symbol)
        if info is None:
            logger.error(f"Symbol {symbol} not found in MT5")
            return {'status': 'ERROR', 'message': f'Symbol {symbol} not found'}
        if not info.visible:
            if not mt5.symbol_select(symbol, True):
                logger.error(f"Failed to select symbol {symbol}")
                return {'status': 'ERROR', 'message': f'Cannot select {symbol}'}

        # Normalize volume to broker limits/step
        min_lot = info.volume_min
        max_lot = info.volume_max
        lot_step = info.volume_step or 0.01
        volume = max(min_lot, min(volume, max_lot))
        volume = round(volume / lot_step) * lot_step
        volume = float(f"{volume:.2f}")
        logger.debug(f"Normalized volume for {symbol}: {volume} (min={min_lot}, step={lot_step})")

        # Get current market price
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            logger.error(f"No tick data for {symbol} – is it visible in Market Watch?")
            return {'status': 'ERROR', 'message': f'No tick data for {symbol}'}

        logger.debug(f"Tick for {symbol}: bid={tick.bid}, ask={tick.ask}")

        # Determine supported filling mode
        # See MT5 docs: some symbols only allow FOK or RETURN, not IOC. [web:69][web:70]
        fill_const = mt5.ORDER_FILLING_RETURN  # safe default
        try:
            if info.trade_fill_mode == mt5.SYMBOL_FILLING_FOK:
                fill_const = mt5.ORDER_FILLING_FOK
            elif info.trade_fill_mode == mt5.SYMBOL_FILLING_IOC:
                fill_const = mt5.ORDER_FILLING_IOC
        except AttributeError:
            # Older MetaTrader5 Python builds may not expose all constants; keep RETURN
            pass

        # Prepare MT5 request
        if action == 'BUY':
            price = tick.ask
            order_type = mt5.ORDER_TYPE_BUY
        else:
            price = tick.bid
            order_type = mt5.ORDER_TYPE_SELL

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 30,
            "magic": 234000,  # Odyssey magic number
            "comment": order.get('comment', 'Odyssey v2'),
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": fill_const,
        }

        result = mt5.order_send(request)

        execution_result = {
            'status': 'FILLED' if result.retcode == mt5.TRADE_RETCODE_DONE else 'REJECTED',
            'order_id': getattr(result, 'order', 0),
            'ticket': getattr(result, 'order', 0),
            'volume': getattr(result, 'volume', 0),
            'price': getattr(result, 'price', 0),
            'retcode': result.retcode,
            'comment': getattr(result, 'comment', ''),
            'timestamp': datetime.utcnow().isoformat(),
        }

        await self.log_trade(symbol, action, execution_result)

        status_emoji = '✅' if execution_result['status'] == 'FILLED' else '❌'
        logger.info(
            f"{status_emoji} {action} {symbol} {volume} lots @ {execution_result['price']:.5f} "
            f"(Retcode: {result.retcode})"
        )
        
        metrics.events_processed.labels(service_name='trading-executor', event_type='trade_execution').inc()

        return execution_result

    # =========================
    # LOGGING
    # =========================
    async def log_trade(self, symbol: str, action: str, result: Dict):
        """TEMP: print-only logging (QuestDB insert_trade not implemented yet)"""
        logger.info(
            f"Trade result: {symbol} {action} status={result['status']} "
            f"retcode={result['retcode']} price={result['price']}"
        )
        # When QuestDBClient.insert_trade is implemented, call it here.

    # =========================
    # POSITION MGMT / HEALTH
    # =========================
    async def manage_positions(self):
        """Real-time position management (Trailing Stops & Partial Closes)"""
        if not self.mt5_initialized:
            return

        positions = mt5.positions_get()
        if not positions:
            return

        logger.info(f"Managing {len(positions)} active positions")
        
        for pos in positions:
            symbol = pos.symbol
            ticket = pos.ticket
            
            info = mt5.symbol_info(symbol)
            if not info:
                continue
                
            point = info.point
            
            # Simple threshold rules
            # E.g., at 30 pips profit, move SL to breakeven + 5 pips, close 50%
            profit_points_trigger = 300 * point # 30 pips
            lock_points = 50 * point # 5 pips
            
            # Calculate current profit in price distance
            if pos.type == mt5.ORDER_TYPE_BUY:
                distance = pos.price_current - pos.price_open
                new_sl = pos.price_open + lock_points
                is_in_profit = distance >= profit_points_trigger
                should_trail = is_in_profit and (pos.sl < new_sl or pos.sl == 0)
            else: # SELL
                distance = pos.price_open - pos.price_current
                new_sl = pos.price_open - lock_points
                is_in_profit = distance >= profit_points_trigger
                should_trail = is_in_profit and (pos.sl > new_sl or pos.sl == 0)
                
            if is_in_profit:
                # --- Trailing Stop ---
                if should_trail:
                    request = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": ticket,
                        "symbol": symbol,
                        "sl": new_sl,
                        "tp": pos.tp
                    }
                    result = mt5.order_send(request)
                    if result.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"Trailing Stop moved on {ticket} to {new_sl}")
                        metrics.events_processed.labels(service_name='trading-executor', event_type='trailing_stop').inc()
                
                # --- Partial Close (Optional Logic) ---
                # Let's say if volume is still full (e.g > min_lot), we divide it by 2
                min_lot = info.volume_min
                close_vol = max(min_lot, pos.volume / 2.0)
                # Keep it simple: Only close if volume hasn't been partialed yet
                if pos.volume > close_vol:
                    close_request = {
                        "action": mt5.TRADE_ACTION_DEAL,
                        "position": ticket,
                        "symbol": symbol,
                        "volume": close_vol,
                        "type": mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY,
                        "price": mt5.symbol_info_tick(symbol).bid if pos.type == mt5.ORDER_TYPE_BUY else mt5.symbol_info_tick(symbol).ask,
                        "magic": 234000,
                        "comment": "Partial Close",
                        "type_time": mt5.ORDER_TIME_GTC,
                        "type_filling": mt5.ORDER_FILLING_IOC,
                    }
                    res = mt5.order_send(close_request)
                    if res.retcode == mt5.TRADE_RETCODE_DONE:
                        logger.info(f"Partial Close executed on {ticket}: closed {close_vol} lots")
                        metrics.events_processed.labels(service_name='trading-executor', event_type='partial_close').inc()

    def check_account_health(self) -> bool:
        """Check daily P&L, drawdown limits"""
        if not self.mt5_initialized:
            return False

        account = mt5.account_info()
        if not account:
            return False

        daily_pnl = account.profit
        
        # Update gauges
        metrics.account_balance.set(account.balance)
        metrics.account_equity.set(account.equity)
        metrics.daily_pnl.set(daily_pnl)
        
        if daily_pnl < -self.account_balance * 0.06:  # -6% daily loss
            logger.critical("DAILY LOSS LIMIT HIT - EMERGENCY STOP ACTIVATED")
            return False

        positions = mt5.positions_get()
        metrics.active_positions.labels(symbol='ALL').set(len(positions) if positions else 0)
        
        if positions:
            # Count positions per symbol
            symbol_counts = {}
            for pos in positions:
                symbol_counts[pos.symbol] = symbol_counts.get(pos.symbol, 0) + 1
            for sym, count in symbol_counts.items():
                metrics.active_positions.labels(symbol=sym).set(count)
                
            if len(positions) >= self.max_positions:
                logger.warning("MAX POSITIONS REACHED")

        return True

    # =========================
    # MAIN LOOP
    # =========================
    async def process_order_queue(self):
        """Main order processing loop"""
        logger.info("Starting MT5 order processing loop...")

        while True:
            try:
                if not self.check_account_health():
                    logger.warning("Account health check failed - pausing execution")
                    await asyncio.sleep(30)
                    continue

                orders = self.get_queued_orders()

                for order in orders:
                    result = await self.execute_order(order)
                    # Cache in Redis so Gateway UI can see live positions/executions
                    self.redis.set_cache(f"executions:{order['symbol']}:latest", result)
                    
                    # Publish execution receipt back to Kafka
                    self.kafka_producer.send(KafkaTopics.TRADING_EXECUTIONS, result, key=order['symbol'])

                await self.manage_positions()

                await asyncio.sleep(3)

            except KeyboardInterrupt:
                logger.info("Executor stopped by user")
                break
            except Exception as e:
                logger.error(f"Executor error: {e}")
                await asyncio.sleep(10)

    def shutdown(self):
        """Clean shutdown"""
        if self.mt5_initialized:
            mt5.shutdown()
            logger.info("MT5 connection closed")


# =========================
# ENTRYPOINT
# =========================
async def main():
    executor = MT5TradingExecutor()

    try:
        if executor.mt5_initialized:
            await executor.process_order_queue()
        else:
            print("❌ Cannot start - MT5 not connected")
    finally:
        executor.shutdown()


if __name__ == "__main__":
    print("🧪 Testing MT5 connection with mt5_config.py...")
    executor = MT5TradingExecutor()

    if executor.mt5_initialized:
        print("\n🚀 MT5 LIVE - Ready for order execution!")
        print("💡 Tip: Run strategy-engine first to generate orders")
        asyncio.run(main())
    else:
        print("\n❌ MT5 Setup Checklist:")
        print("  1. Update MT5_CONFIG in data-service/config/mt5_config.py")
        print("  2. Ensure MT5 terminal is running & logged in")
        print("  3. Check Tools → Options → Expert Advisors → Allow algo trading")
        print("  4. Verify MT5 path: C:\\Program Files\\MetaTrader 5\\terminal64.exe")
