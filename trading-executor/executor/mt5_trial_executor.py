import os
import MetaTrader5 as mt5
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv()

MT5_LOGIN    = int(os.getenv('MT5_LOGIN', '0'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER   = os.getenv('MT5_SERVER', 'MetaQuotes-Demo')
MT5_PATH     = os.getenv('MT5_PATH', r'C:\Program Files\MetaTrader 5\terminal64.exe')

SYMBOLS = ["XAUUSD", "EURUSD"]


def init_mt5() -> bool:
    print("🔄 Initializing MT5 (trial executor)...")
    init_kwargs = {
        "login": MT5_LOGIN,
        "password": MT5_PASSWORD,
        "server": MT5_SERVER,
        "timeout": 60000,
        "portable": False,
    }
    if MT5_PATH and os.path.exists(MT5_PATH):
        init_kwargs["path"] = MT5_PATH

    ok = mt5.initialize(**init_kwargs)
    if not ok:
        print("❌ mt5.initialize failed:", mt5.last_error())
        return False

    info = mt5.account_info()
    if info:
        print(
            f"✅ MT5 Connected: Account {info.login} | "
            f"Balance: ${info.balance:,.2f} | Equity: ${info.equity:,.2f}"
        )
    else:
        print("⚠️ MT5 connected but no account info")
    return True


def send_test_order(symbol: str, lots: float = 0.01):
    print(f"\n🚀 Sending TEST BUY order for {symbol} ({lots} lots)")

    s_info = mt5.symbol_info(symbol)
    if s_info is None:
        print(f"❌ Symbol {symbol} not found in MT5")
        return
    if not s_info.visible:
        if not mt5.symbol_select(symbol, True):
            print(f"❌ Failed to select symbol {symbol}")
            return

    min_lot = s_info.volume_min
    max_lot = s_info.volume_max
    step = s_info.volume_step or 0.01
    volume = max(min_lot, min(lots, max_lot))
    volume = round(volume / step) * step
    volume = float(f"{volume:.2f}")
    print(f"🔧 Normalized volume: {volume} (min={min_lot}, step={step})")

    tick = mt5.symbol_info_tick(symbol)
    if not tick:
        print(f"❌ No tick data for {symbol}")
        return
    print(f"🔎 Tick: bid={tick.bid}, ask={tick.ask}")

    price = tick.ask
    deviation = 100
    fill_mode = mt5.ORDER_FILLING_RETURN

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": volume,
        "type": mt5.ORDER_TYPE_BUY,
        "price": price,
        "sl": 0.0,
        "tp": 0.0,
        "deviation": deviation,
        "magic": 999001,
        "comment": "odyssey_trial",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": fill_mode,
    }

    print("📤 Order request:", request)
    result = mt5.order_send(request)
    print("📥 Order result:", result)

    if result.retcode == mt5.TRADE_RETCODE_DONE:
        print(f"✅ FILLED {symbol} {volume} lots @ {result.price}")
    else:
        print(f"❌ REJECTED {symbol} (retcode={result.retcode})")


def main():
    if not init_mt5():
        return
    for sym in SYMBOLS:
        send_test_order(sym, lots=0.01)
        time.sleep(1)
    mt5.shutdown()
    print("\n✅ MT5 connection closed (trial executor finished)")


if __name__ == "__main__":
    main()
