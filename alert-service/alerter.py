import os
import sys
import requests
import asyncio
import threading
import time
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
SHARED_PYTHON = os.path.join(PROJECT_ROOT, "shared", "python")
sys.path.insert(0, SHARED_PYTHON)

from logger import OdysseyLogger
from kafka_utils import KafkaConsumerClient, KafkaTopics
from redis_client import RedisClient
from metrics import metrics

logger = OdysseyLogger('alert-service')

class TelegramAlerter:
    def __init__(self):
        self.bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.getenv('TELEGRAM_CHAT_ID')
        self.api_url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        self.update_url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates"
        
        self.redis = RedisClient()
        self.last_update_id = 0
        
        # We hook into Orders, Executions, and System Alerts (Signals/Risk)
        self.kafka_consumer = KafkaConsumerClient(
            [KafkaTopics.TRADING_ORDERS, KafkaTopics.TRADING_EXECUTIONS, KafkaTopics.ALERTS], 
            group_id='alert-service'
        )
        
        metrics.start_server(8005) # Standalone metrics port

    def is_configured(self) -> bool:
        return bool(self.bot_token and self.chat_id)

    def send_telegram_message(self, text: str, chat_id: str = None):
        """Push plaintext message to Telegram API synchronously"""
        target_chat = chat_id or self.chat_id
        if not self.bot_token or not target_chat:
            logger.info(f"🚨 [MOCK TELEGRAM ALERT]\n{text}")
            return
            
        try:
            payload = {
                "chat_id": target_chat,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(self.api_url, json=payload, timeout=10)
            if response.status_code != 200:
                logger.error(f"Telegram API Error: {response.text}")
            else:
                logger.debug(f"Pushed alert to {target_chat}")
        except Exception as e:
            logger.error(f"Failed to push Telegram alert: {e}")

    def _poll_telegram(self):
        """Background thread to handle incoming Telegram commands (/status, /ping)"""
        logger.info("Interactivity: Telegram Polling Thread Started [Active]")
        while True:
            try:
                params = {"offset": self.last_update_id + 1, "timeout": 20}
                resp = requests.get(self.update_url, params=params, timeout=25).json()
                
                if resp.get("ok") and resp.get("result"):
                    for update in resp["result"]:
                        self.last_update_id = update["update_id"]
                        message = update.get("message")
                        if not message or "text" not in message: continue
                        
                        text = message["text"].lower()
                        chat_id = str(message["chat"]["id"])
                        
                        # Command Router
                        if text.startswith("/status"):
                            self._handle_status_command(chat_id)
                        elif text.startswith("/ping"):
                            self.send_telegram_message("🏓 <b>PONG!</b> System is responsive.", chat_id)
                        elif text.startswith("/start"):
                            self.send_telegram_message("👋 <b>ODYSSEY v2 INTERACTIVE</b>\nAvailable: /status, /ping", chat_id)
                
            except Exception as e:
                logger.error(f"Polling error: {e}")
            
            time.sleep(1)

    def _handle_status_command(self, chat_id: str):
        """Generate and send a detailed system health report"""
        redis_ok = self.redis.health_check()
        
        # Check pulse (last tick for XAUUSD)
        pulse = "🔴 NO DATA"
        tick = self.redis.get_cache("ticks:XAUUSD")
        if tick: pulse = "🟢 ACTIVE Ticks"
        
        # Account info
        balance = self.redis.get_cache("account:balance") or "N/A"
        equity = self.redis.get_cache("account:equity") or "N/A"
        
        mode = "Paper Trading (Mock)" if os.getenv('USE_MOCK_BROKER') == 'true' else "Live Execution"
        
        status_msg = (
            f"📊 <b>ODYSSEY SYSTEM REPORT</b>\n"
            f"<b>Status:</b> 🟢 ONLINE\n"
            f"<b>Database:</b> {'🟢 REDIS OK' if redis_ok else '🔴 REDIS DOWN'}\n"
            f"<b>Pipeline:</b> {pulse}\n"
            f"<b>Equity:</b> ${equity}\n"
            f"<b>Mode:</b> {mode}\n"
            f"<b>Time:</b> {datetime.utcnow().strftime('%H:%M:%S')} UTC"
        )
        self.send_telegram_message(status_msg, chat_id)

    def handle_order(self, message: dict):
        """Format and send Trading Order alerts"""
        symbol = message.get('symbol', 'UNKNOWN')
        action = message.get('action', 'N/A')
        volume = message.get('volume', 0.0)
        price = message.get('price', 0.0)
        
        text = (
            f"🔔 <b>NEW ORDER GENERATED</b>\n"
            f"<b>Symbol:</b> {symbol}\n"
            f"<b>Action:</b> {action}\n"
            f"<b>Volume:</b> {volume} lots\n"
            f"<b>Model Price:</b> {price}\n"
        )
        self.send_telegram_message(text)
        metrics.events_processed.labels(service_name='alert-service', event_type='order_alert_sent').inc()

    def handle_execution(self, message: dict):
        """Format and send Trading Execution alerts"""
        symbol = message.get('symbol', 'UNKNOWN')
        status = message.get('status', 'ERROR')
        retcode = message.get('retcode', 'N/A')
        
        if status == 'FILLED':
            emoji = "✅"
            action = message.get('action', 'N/A')
            price = message.get('price', 0.0)
            text = (
                f"{emoji} <b>ORDER EXECUTED</b>\n"
                f"<b>Symbol:</b> {symbol} | {action}\n"
                f"<b>Fill Price:</b> {price}\n"
            )
        else:
            emoji = "❌"
            comment = message.get('comment', 'No details provided')
            text = (
                f"{emoji} <b>ORDER FAILED</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Code:</b> {retcode} | {comment}\n"
            )
            
        self.send_telegram_message(text)
        metrics.events_processed.labels(service_name='alert-service', event_type='execution_alert_sent').inc()

    def handle_system_alert(self, message: dict):
        """Handle multi-type system alerts (Signals, Risk Rejections)"""
        alert_type = message.get('type', 'GENERAL')
        symbol = message.get('symbol', 'SYSTEM')
        
        if alert_type == 'SIGNAL':
            action = message.get('action', 'HOLD')
            conf = message.get('confidence', 0.0)
            strength = message.get('strength', 'NEUTRAL')
            emoji = "🎯" if action != 'HOLD' else "🔍"
            text = (
                f"{emoji} <b>NEW {strength} SIGNAL</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Action:</b> {action}\n"
                f"<b>Confidence:</b> {conf*100:.1f}%\n"
            )
        elif alert_type == 'RISK_REJECTION':
            reason = message.get('reason', 'Risk Limit Exceeded')
            text = (
                f"⚠️ <b>RISK REJECTION</b>\n"
                f"<b>Symbol:</b> {symbol}\n"
                f"<b>Reason:</b> {reason}\n"
            )
        else:
            msg = message.get('message', 'General system notification')
            text = f"💡 <b>SYSTEM NOTIFICATION</b>\n{msg}"

        self.send_telegram_message(text)
        metrics.events_processed.labels(service_name='alert-service', event_type='system_alert_sent').inc()

    def start(self):
        logger.info("Initializing Odyssey Alert Service...")
        if not self.is_configured():
            logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing in .env. Alerts will only be logged locally.")
        else:
            logger.info("Telegram configuration detected. Sending startup notification...")
            self.send_telegram_message("🚀 <b>ODYSSEY v2 ONLINE</b>\nTrading Pipeline and Alert Service are now synced.")
            
            # Start Interactive Polling Thread
            threading.Thread(target=self._poll_telegram, daemon=True).start()

        self.kafka_consumer.register_handler(KafkaTopics.TRADING_ORDERS, self.handle_order)
        self.kafka_consumer.register_handler(KafkaTopics.TRADING_EXECUTIONS, self.handle_execution)
        self.kafka_consumer.register_handler(KafkaTopics.ALERTS, self.handle_system_alert)
        self.kafka_consumer.start()

if __name__ == "__main__":
    alerter = TelegramAlerter()
    alerter.start()

