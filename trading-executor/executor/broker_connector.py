import os
import json
import time
import random
import requests
from abc import ABC, abstractmethod
from typing import Dict, Any, List
from datetime import datetime

# Import Redis for real-time price fetching
import sys
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
try:
    from redis_client import RedisClient
except ImportError:
    RedisClient = None

try:
    from market_simulator import PriceProvider
except ImportError:
    PriceProvider = None

class BrokerAPI(ABC):
    """Abstract base class for all broker execution platforms."""
    
    @abstractmethod
    def initialize(self) -> bool:
        """Authenticate and initialize connection to the broker."""
        pass
        
    @abstractmethod
    def place_order(self, symbol: str, action: str, volume: float, price: float = None, sl: float = None, tp: float = None, order_type: str = "MARKET") -> Dict[str, Any]:
        """Place an order with the broker and return the order response/ID."""
        pass
        
    @abstractmethod
    def modify_order(self, order_id: str, new_sl: float = None, new_tp: float = None) -> bool:
        """Modify an existing open order (e.g., trail stop loss)."""
        pass
        
    @abstractmethod
    def close_position(self, symbol: str) -> bool:
        """Close an open position completely."""
        pass
        
    @abstractmethod
    def close_all_positions(self) -> bool:
        """Emergency circuit breaker: close all active positions."""
        pass
        
    @abstractmethod
    def get_account_info(self) -> Dict[str, Any]:
        """Fetch current balance, equity, margin, and P&L."""
        pass
        
    @abstractmethod
    def get_open_positions(self) -> List[Dict[str, Any]]:
        """Fetch all currently open positions."""
        pass


class FyersAPI(BrokerAPI):
    """
    Implementation for Fyers API (India).
    Requires 'fyers_apiv3' package.
    """
    
    def __init__(self):
        self.client_id = os.getenv("FYERS_CLIENT_ID")
        self.secret_key = os.getenv("FYERS_SECRET_KEY")
        self.access_token = os.getenv("FYERS_ACCESS_TOKEN") # Stored securely
        
        self.fyers = None
        self.connected = False
        
    def initialize(self) -> bool:
        from fyers_apiv3 import fyersModel
        
        try:
            self.fyers = fyersModel.FyersModel(
                client_id=self.client_id, 
                is_async=False, 
                token=self.access_token, 
                log_path=""
            )
            # Ping to verify
            profile = self.fyers.get_profile()
            if profile.get('s') == 'ok':
                self.connected = True
                return True
            return False
        except Exception as e:
            print(f"Fyers Init Error: {e}")
            return False

    def place_order(self, symbol: str, action: str, volume: float, price: float = None, sl: float = None, tp: float = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.connected: return {}
        
        # Map generic action to Fyers side
        side = 1 if action == 'BUY' else -1
        
        # 2 represents MARKET, 1 represents LIMIT
        type_code = 2 if order_type == "MARKET" else 1
        
        data = {
            "symbol": symbol,
            "qty": int(volume), # India markets mostly trade in discrete lot chunks or shares
            "type": type_code,
            "side": side,
            "productType": "INTRADAY", # MIS for intraday leveraging
            "limitPrice": price if order_type == "LIMIT" else 0,
            "stopPrice": 0,
            "validity": "DAY",
            "disclosedQty": 0,
            "offlineOrder": False,
        }
        
        if sl and tp:
            # Fyers supports BO/CO (Bracket/Cover orders), but for simplicity, we use generic and manage SL/TP in Odyssey.
            # Alternatively, if productType is BO (Bracket Order):
            # data["stopLoss"] = sl_diff
            # data["takeProfit"] = tp_diff
            pass
            
        response = self.fyers.place_order(data=data)
        return response
        
    def modify_order(self, order_id: str, new_sl: float = None, new_tp: float = None) -> bool:
        pass # To be implemented via broker-specific endpoints
        
    def close_position(self, symbol: str) -> bool:
        if not self.connected: return False
        data = {"id": symbol }
        res = self.fyers.exit_positions(data=data)
        return res.get('s') == 'ok'
        
    def close_all_positions(self) -> bool:
        if not self.connected: return False
        res = self.fyers.exit_positions(data={})
        return res.get('s') == 'ok'
        
    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected: 
            return {"balance": 100000.0, "equity": 100000.0, "pnl": 0.0}
            
        res = self.fyers.funds()
        if res.get('s') == 'ok':
            funds = res['fund_limit']
            # Find specific fund objects (e.g., 'Available Balance')
            balance = next((x['equityAmount'] for x in funds if x['title'] == 'Available Balance'), 0)
            return {"balance": balance, "equity": balance, "pnl": 0.0}
        return {"balance": 100000.0, "equity": 100000.0, "pnl": 0.0}
        
    def get_open_positions(self) -> List[Dict[str, Any]]:
        if not self.connected: return []
        try:
            res = self.fyers.positions()
            if res.get('s') == 'ok':
                return res.get('netPositions', [])
        except Exception:
            pass
        return []

# Remove redundant import if it exists further down
# import requests

class OandaAPI(BrokerAPI):
    """
    Implementation for OANDA REST-V20 API (Forex).
    """
    
    def __init__(self):
        self.access_token = os.getenv("OANDA_ACCESS_TOKEN")
        self.account_id = os.getenv("OANDA_ACCOUNT_ID")
        env = os.getenv("OANDA_ENVIRONMENT", "practice") # 'practice' or 'live'
        
        domain = "api-fxtrade.oanda.com" if env == "live" else "api-fxpractice.oanda.com"
        self.base_url = f"https://{domain}/v3"
        self.connected = False
        
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
    def initialize(self) -> bool:
        if not self.access_token or not self.account_id:
            print("OANDA Init Error: Missing API keys in environment.")
            return False
            
        try:
            url = f"{self.base_url}/accounts/{self.account_id}/summary"
            response = requests.get(url, headers=self.headers)
            if response.status_code == 200:
                self.connected = True
                return True
            print(f"OANDA Init Error: {response.text}")
            return False
        except Exception as e:
            print(f"OANDA Request Error: {e}")
            return False

    def place_order(self, symbol: str, action: str, volume: float, price: float = None, sl: float = None, tp: float = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.connected: return {}
        
        # Oanda format: EUR_USD, units negative for sell
        oanda_symbol = symbol.replace("USD", "_USD").replace("EUR", "EUR_").replace("GBP", "GBP_").strip('_')
        if oanda_symbol == 'XAU_USD': oanda_symbol = 'XAU_USD' # Assuming mapping
        
        units = str(int(volume * 100000)) if action == "BUY" else str(int(-volume * 100000))
        
        order_dict = {
            "order": {
                "units": units,
                "instrument": oanda_symbol,
                "timeInForce": "FOK",
                "type": order_type,
                "positionFill": "DEFAULT"
            }
        }
        
        url = f"{self.base_url}/accounts/{self.account_id}/orders"
        try:
            res = requests.post(url, headers=self.headers, json=order_dict)
            if res.status_code in [200, 201]:
                return {"s": "ok", "id": res.json().get("orderCreateTransaction", {}).get("id")}
            return {"s": "error", "message": res.text}
        except Exception as e:
            return {"s": "error", "message": str(e)}

    def modify_order(self, order_id: str, new_sl: float = None, new_tp: float = None) -> bool:
        if not self.connected: return False
        
        # Modifying open position's SL/TP via Trade ID
        url = f"{self.base_url}/accounts/{self.account_id}/trades/{order_id}/orders"
        body = {}
        if new_sl: body["stopLoss"] = {"price": str(new_sl)}
        if new_tp: body["takeProfit"] = {"price": str(new_tp)}
        
        try:
            res = requests.put(url, headers=self.headers, json=body)
            return res.status_code in [200, 201]
        except Exception:
            return False
        
    def close_position(self, symbol: str) -> bool:
        if not self.connected: return False
        oanda_symbol = symbol[:3] + '_' + symbol[3:]
        url = f"{self.base_url}/accounts/{self.account_id}/positions/{oanda_symbol}/close"
        try:
            res = requests.put(url, headers=self.headers, json={"longUnits": "ALL"} if True else {"shortUnits": "ALL"})
            return res.status_code == 200
        except: return False

    def close_all_positions(self) -> bool:
        if not self.connected: return False
        positions = self.get_open_positions()
        success = True
        for pos in positions:
            symbol = pos.get('instrument', '').replace('_', '')
            if not self.close_position(symbol):
                success = False
        return success
        
    def get_account_info(self) -> Dict[str, Any]:
        if not self.connected: return {"balance": 100000.0, "equity": 100000.0, "pnl": 0.0}
        url = f"{self.base_url}/accounts/{self.account_id}/summary"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                acc = res.json().get('account', {})
                return {
                    "balance": float(acc.get('balance', 0)),
                    "equity": float(acc.get('NAV', 0)),
                    "pnl": float(acc.get('unrealizedPL', 0))
                }
        except: pass
        return {"balance": 100000.0, "equity": 100000.0, "pnl": 0.0}
        
    def get_open_positions(self) -> List[Dict[str, Any]]:
        if not self.connected: return []
        url = f"{self.base_url}/accounts/{self.account_id}/openPositions"
        try:
            res = requests.get(url, headers=self.headers)
            if res.status_code == 200:
                return res.json().get('positions', [])
        except: pass
        return []

class MockBrokerAPI(BrokerAPI):
    """
    Real-Time Mock Broker for paper trading.
    Simulates execution, slippage, and P&L using live Redis ticks.
    """
    
    def __init__(self, price_provider: PriceProvider = None):
        self.state_file = os.path.join(PROJECT_ROOT, "mock_account_state.json")
        self.initial_balance = float(os.getenv("MOCK_INITIAL_BALANCE", 1000000.0))
        self.price_provider = price_provider
        
        try:
            self.redis = RedisClient() if RedisClient else None
        except Exception as e:
            if not self.price_provider:
                print(f"DEBUG: Mock Broker using internal pricing (Redis unavailable: {e})")
            self.redis = None
            
        self.connected = False
        self.state = {
            "balance": self.initial_balance,
            "positions": {},
            "history": []
        }
        
    def _load_state(self):
        if os.path.exists(self.state_file):
            try:
                with open(self.state_file, 'r') as f:
                    self.state = json.load(f)
            except:
                pass
                
    def _save_state(self):
        with open(self.state_file, 'w') as f:
            json.dump(self.state, f, indent=4)
            
    def initialize(self) -> bool:
        self._load_state()
        self.connected = True
        self._sync_to_redis()
        return True
    
    def _sync_to_redis(self):
        """Publish current state to Redis so Gateway/UI can read it."""
        if not self.redis:
            return
        try:
            # Account state
            acc = self.get_account_info()
            self.redis.set_cache("account:balance", acc['balance'], ttl=60)
            self.redis.set_cache("account:equity", acc['equity'], ttl=60)
            self.redis.set_cache("account:profit", acc['pnl'], ttl=60)
            self.redis.set_cache("account:margin_free", acc['equity'], ttl=60)
            
            # Open positions list for the UI
            open_positions = []
            for sym, pos in self.state.get('positions', {}).items():
                curr_price = self._get_latest_price(sym)
                if pos['action'] == 'BUY':
                    live_pnl = (curr_price - pos['entry_price']) * pos['volume']
                else:
                    live_pnl = (pos['entry_price'] - curr_price) * pos['volume']
                open_positions.append({
                    'symbol': sym,
                    'action': pos['action'],
                    'volume': pos['volume'],
                    'entry_price': pos['entry_price'],
                    'entry_time': pos.get('entry_time', ''),
                    'pnl': round(live_pnl, 2),
                    'status': 'OPEN',
                    'order_id': pos.get('order_id', '')
                })
            self.redis.set_cache("mock:positions:live", open_positions, ttl=30)
            self.redis.set_cache("positions:count", len(open_positions), ttl=30)
            
            # Trade history (last 50)
            history = self.state.get('history', [])[-50:]
            self.redis.set_cache("mock:trade_history", history, ttl=300)
        except Exception as e:
            print(f"DEBUG: Redis sync failed (non-fatal): {e}")
        
    def _get_latest_price(self, symbol: str) -> float:
        """Fetch latest price from Provider or Redis Stream."""
        # 1. Check if we have a simulated price provider (Stochastic/Historical)
        if self.price_provider:
            tick = self.price_provider.get_next_tick(symbol)
            if tick and 'price' in tick:
                return float(tick['price'])
        
        # 2. Fallback to Redis
        if self.redis:
            try:
                # Try to get from market:ticks:{symbol}
                stream_key = f"market:ticks:{symbol}"
                data = self.redis.client.xrevrange(stream_key, count=1)
                if data:
                    return float(data[0][1]['price'])
                
                # Fallback to feature store if stream is empty
                feat = self.redis.get_feature(symbol, 'LTP')
                if feat:
                    return float(feat['value'])
            except:
                pass
                
        return 2000.0 # Ultimate fallback

    def place_order(self, symbol: str, action: str, volume: float, price: float = None, sl: float = None, tp: float = None, order_type: str = "MARKET") -> Dict[str, Any]:
        if not self.connected: self.initialize()
        
        # 1. Fetch current price
        current_price = self._get_latest_price(symbol)
        
        # 2. Simulate Slippage (0.01% - 0.05%)
        slippage_pct = random.uniform(0.0001, 0.0005)
        if action == "BUY":
            entry_price = current_price * (1 + slippage_pct)
        else:
            entry_price = current_price * (1 - slippage_pct)
            
        # 3. Simulate Latency
        time.sleep(random.uniform(0.05, 0.2))
        
        order_id = f"mock_{int(time.time()*1000)}"
        
        # 4. Update internal state
        self.state["positions"][symbol] = {
            "order_id": order_id,
            "symbol": symbol,
            "action": action,
            "volume": volume,
            "entry_price": entry_price,
            "entry_time": datetime.now().isoformat(),
            "sl": sl,
            "tp": tp
        }
        
        self._save_state()
        self._sync_to_redis()
        print(f"MOCK FILL: {action} {volume} {symbol} @ {entry_price:.5f}")
        
        return {"s": "ok", "id": order_id, "price": entry_price}
        
    def modify_order(self, order_id: str, new_sl: float = None, new_tp: float = None) -> bool:
        for sym, pos in self.state["positions"].items():
            if pos["order_id"] == order_id:
                if new_sl: pos["sl"] = new_sl
                if new_tp: pos["tp"] = new_tp
                self._save_state()
                return True
        return False
        
    def close_position(self, symbol: str) -> bool:
        if symbol not in self.state["positions"]:
            return False
            
        pos = self.state["positions"].pop(symbol)
        exit_price = self._get_latest_price(symbol)
        
        # Calculate P&L
        if pos["action"] == "BUY":
            pnl = (exit_price - pos["entry_price"]) * pos["volume"]
        else:
            pnl = (pos["entry_price"] - exit_price) * pos["volume"]
            
        self.state["balance"] += pnl
        self.state["history"].append({**pos, "exit_price": exit_price, "pnl": round(pnl, 2), "exit_time": datetime.now().isoformat()})
        
        self._save_state()
        self._sync_to_redis()
        print(f"MOCK CLOSE: {symbol} at {exit_price:.5f}. P&L: {pnl:.2f}")
        return True
        
    def close_all_positions(self) -> bool:
        symbols = list(self.state["positions"].keys())
        for sym in symbols:
            self.close_position(sym)
        return True
        
    def get_account_info(self) -> Dict[str, Any]:
        unrealized_pnl = 0
        for sym, pos in self.state["positions"].items():
            curr_price = self._get_latest_price(sym)
            if pos["action"] == "BUY":
                unrealized_pnl += (curr_price - pos["entry_price"]) * pos["volume"]
            else:
                unrealized_pnl += (pos["entry_price"] - curr_price) * pos["volume"]
                
        return {
            "balance": self.state["balance"],
            "equity": self.state["balance"] + unrealized_pnl,
            "pnl": unrealized_pnl
        }
        
    def get_open_positions(self) -> List[Dict[str, Any]]:
        return list(self.state["positions"].values())

    def get_trade_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return closed trade history (most recent first)."""
        return list(reversed(self.state.get('history', [])[-limit:]))
