import os
import sys
import time
from dotenv import load_dotenv

load_dotenv()

# Add necessary paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(CURRENT_DIR, "trading-executor", "executor"))
sys.path.insert(0, os.path.join(CURRENT_DIR, "shared", "python"))

from router import SmartOrderRouter

def test_mock_flow():
    print("--- ODYSSEY MOCK BROKER TEST ---")
    router = SmartOrderRouter()
    router.initialize()
    
    # 1. Check account info before
    acc_before = router.get_consolidated_account()
    print(f"Initial Account: {acc_before}")
    
    # 2. Place a mock order
    print("\nPlacing BUY order for XAUUSD (mapped to MCX:GOLD)...")
    res = router.place_order(symbol="XAUUSD", action="BUY", volume=1.0)
    print(f"Order Result: {res}")
    
    if res.get('s') == 'ok':
        # 3. Check positions
        pos = router.fyers.get_open_positions()
        print(f"Active Positions: {pos}")
        
        # 4. Check account info (should show unrealized P&L based on price)
        time.sleep(1)
        acc_mid = router.get_consolidated_account()
        print(f"Mid-Trade Account: {acc_mid}")
        
        # 5. Close position
        print("\nClosing position...")
        router.fyers.close_position("MCX:GOLDM24OCTFUT")
        
        # 6. Check final balance
        acc_after = router.get_consolidated_account()
        print(f"Final Account: {acc_after}")
        print(f"Total Trade P&L: {acc_after['balance'] - acc_before['balance']:.2f}")

if __name__ == "__main__":
    test_mock_flow()
