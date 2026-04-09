"""
Odyssey v2 - Telegram Alert Bot
Listens to Kafka ALERTS topic and pushes formatted messages to Telegram.
"""

import os
import sys
import time
import json
import logging
from typing import Dict, Any

# Fix for nested asyncio loops often encountered in Windows/Python integrations
import nest_asyncio
nest_asyncio.apply()

from telegram import Bot
from dotenv import load_dotenv

load_dotenv()

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))

from kafka_utils import KafkaConsumerClient, KafkaTopics
from logger import OdysseyLogger

logger = OdysseyLogger('alerts-bot')

class TelegramAlertService:
    def __init__(self):
        self.token = os.getenv("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.getenv("TELEGRAM_CHAT_ID")
        
        if not self.token or not self.chat_id:
            logger.warning("TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID not set in .env. Bot will only log locally.")
            self.bot = None
        else:
            self.bot = Bot(token=self.token)
        
        # Subscribe to ALERTS topic
        self.consumer = KafkaConsumerClient(
            [KafkaTopics.ALERTS], 
            group_id='alerts-bot-group'
        )
        self._running = False
        logger.info("Telegram Alert Service initialized")

    async def _send_message(self, text: str):
        """Send message safely."""
        if self.bot and self.chat_id:
            try:
                await self.bot.send_message(chat_id=self.chat_id, text=text, parse_mode='HTML')
                logger.info("Message sent to Telegram")
            except Exception as e:
                logger.error(f"Failed to send Telegram message: {e}")
        else:
            # Fallback local log if credentials missing
            logger.info(f"[SIMULATED TELEGRAM ALERT]\n{text}\n{'='*40}")

    def format_alert(self, data: Dict[str, Any]) -> str:
        """Format JSON alert data into Telegram HTML message."""
        alert_type = data.get("type", "INFO").upper()
        
        if alert_type == "SIGNAL":
            emoji = "🟢" if data.get("action") == "BUY" else "🔴"
            return (
                f"{emoji} <b>ML SIGNAL ALERT</b>\n"
                f"<b>Symbol:</b> {data.get('symbol')}\n"
                f"<b>Action:</b> {data.get('action')}\n"
                f"<b>Confidence:</b> {data.get('confidence', 0)*100:.1f}%\n"
                f"<b>Price:</b> {data.get('price', 0):.5f}\n"
            )
        elif alert_type == "RISK_REJECTION":
            return (
                f"⛔ <b>RISK REJECTION</b>\n"
                f"<b>Symbol:</b> {data.get('symbol')}\n"
                f"<b>Reason:</b> {data.get('reason')}\n"
                f"<b>Details:</b> {data.get('details', '')}"
            )
        elif alert_type == "CIRCUIT_BREAKER":
            return (
                f"⚠️ <b>CIRCUIT BREAKER TRIGGERED</b>\n"
                f"<b>Level:</b> {data.get('level')}\n"
                f"<b>Drawdown:</b> {data.get('drawdown', 0)*100:.2f}%\n"
                f"<b>Action:</b> {data.get('action')}"
            )
        elif alert_type == "SENTIMENT_SHIFT":
            score = data.get('score', 0)
            emoji = "📈" if score > 0 else "📉"
            return (
                f"{emoji} <b>MAJOR SENTIMENT SHIFT</b>\n"
                f"<b>Asset:</b> {data.get('asset')}\n"
                f"<b>Net Score:</b> {score:+.3f}\n"
                f"<b>Details:</b> {data.get('details', '')}"
            )
        else:
            return f"ℹ️ <b>SYSTEM ALERT</b>\n<pre>{json.dumps(data, indent=2)}</pre>"

    def handle_message(self, msg: Dict[str, Any]):
        """Process incoming Kafka message"""
        text = self.format_alert(msg)
        
        # We need to run awaitably, but we are in a sync loop. 
        # Using nest_asyncio allows us to run asyncio.run() even if an event loop is already running.
        import asyncio
        asyncio.run(self._send_message(text))

    def start(self):
        """Start listening for alerts"""
        self._running = True
        logger.info("Starting Telegram Alert Service loop...")
        
        self.consumer.start(self.handle_message)

        try:
            while self._running:
                time.sleep(1)
        except KeyboardInterrupt:
            logger.info("Stopping Telegram service...")
        finally:
            self.stop()

    def stop(self):
        self._running = False
        self.consumer.stop()

if __name__ == "__main__":
    service = TelegramAlertService()
    service.start()
