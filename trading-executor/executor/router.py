import os
import logging
from typing import Dict, Any
from broker_connector import FyersAPI, OandaAPI, MockBrokerAPI

logger = logging.getLogger('router')

class SmartOrderRouter:
    """
    Routes Odyssey signals to the correct broker (Fyers for IN, Oanda for Global).
    Supports MOCK mode for paper trading.
    """
    
    def __init__(self):
        self.use_mock = os.getenv("USE_MOCK_BROKER", "false").lower() == "true"
        
        if self.use_mock:
            self.fyers = MockBrokerAPI()
            self.oanda = MockBrokerAPI()
            logger.info("🛠️ [ROUTER] Running in MOCK Mode (Paper Trading)")
        else:
            self.fyers = FyersAPI()
            self.oanda = OandaAPI()
        
        self.fyers_connected = False
        self.oanda_connected = False
        
    def initialize(self):
        logger.info("Initializing Smart Order Router Brokers...")
        self.fyers_connected = self.fyers.initialize()
        self.oanda_connected = self.oanda.initialize()
        
        if self.use_mock:
            logger.info("✅ MOCK Brokers initialized successfully.")
            return

        if self.fyers_connected:
            logger.info("✅ FYERS (India) API initialized successfully.")
        else:
            logger.warning("⚠️ FYERS (India) API failed to initialize.")
            
        if self.oanda_connected:
            logger.info("✅ OANDA (Forex) API initialized successfully.")
        else:
            logger.warning("⚠️ OANDA (Forex) API failed to initialize.")
            
    def _determine_broker(self, generic_symbol: str) -> tuple:
        """Determines which broker to use and returns the mapped symbol."""
        # Fyers mapping logic
        if generic_symbol == 'XAUUSD':
            return self.fyers, 'MCX:GOLDM24OCTFUT'
        if generic_symbol == 'EURINR':
            return self.fyers, 'NSE:EURINR24OCTFUT'
            
        # Default fallback to Oanda for major forex pairs
        return self.oanda, generic_symbol
            
    def place_order(self, symbol: str, action: str, volume: float, order_type: str = "MARKET", price: float = None) -> Dict[str, Any]:
        broker, mapped_symbol = self._determine_broker(symbol)
        
        logger.info(f"[ROUTER] Sending {order_type} {action} {volume} {symbol} -> {mapped_symbol} via {broker.__class__.__name__}")
        
        res = broker.place_order(
            symbol=mapped_symbol,
            action=action,
            volume=volume,
            order_type=order_type,
            price=price
        )
        return res
        
    def close_all_positions(self) -> bool:
        r1 = self.fyers.close_all_positions() if self.fyers_connected else False
        r2 = self.oanda.close_all_positions() if self.oanda_connected else False
        return r1 and r2
        
    def get_consolidated_account(self) -> Dict[str, Any]:
        """Aggregate balance from both broker accounts into a unified view."""
        # If both are using the same MockBroker instance/state, we should avoid double counting
        if self.use_mock:
            return self.fyers.get_account_info()
            
        b1 = self.fyers.get_account_info() if self.fyers_connected else {"balance": 0, "equity": 0, "pnl": 0}
        b2 = self.oanda.get_account_info() if self.oanda_connected else {"balance": 0, "equity": 0, "pnl": 0}
        
        return {
            "balance": b1["balance"] + b2["balance"],
            "equity": b1["equity"] + b2["equity"],
            "pnl": b1["pnl"] + b2["pnl"]
        }
