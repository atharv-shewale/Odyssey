"""
MT5 Credential + Initialization Utility
Loads credentials from environment variables (.env file)
"""

import os
import MetaTrader5 as mt5
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN    = int(os.getenv('MT5_LOGIN', '0'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER   = os.getenv('MT5_SERVER', 'MetaQuotes-Demo')

def init_mt5():
    print("=" * 60)
    print("MetaTrader 5 - Python Connection")
    print("=" * 60)
    print(f"Login : {MT5_LOGIN}")
    print(f"Server: {MT5_SERVER}")
    print(f"----- Initializing -----")
    # Try with explicit credentials first
    initialized = mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER)
    if initialized:
        print("✅ MT5 connection established!")
        return True
    else:
        print(f"❌ Initialization failed: {mt5.last_error()}")
        print("Retrying without credentials (fallback)...")
        if mt5.initialize():
            print("✅ Connected via open terminal session!")
            return True
        else:
            print(f"❌ Fallback failed: {mt5.last_error()}")
            return False

def get_account_print_summary():
    info = mt5.account_info()
    if info:
        print(f"Login: {info.login} | Balance: {info.balance} | Equity: {info.equity} | Currency: {info.currency}")
        print(f"Name: {info.name} | Server: {info.server}")
        print(f"Leverage: 1:{info.leverage} | Margin Level: {info.margin_level}")
    else:
        print("❌ Can't fetch account info!")

def shutdown_mt5():
    mt5.shutdown()
    print("[MT5] Shutdown complete.")

if __name__ == "__main__":
    if init_mt5():
        get_account_print_summary()
        shutdown_mt5()
    else:
        print("❌ Could not connect to MT5. Check credentials or run MT5 manually.")
