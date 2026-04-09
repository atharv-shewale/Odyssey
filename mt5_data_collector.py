"""
Odyssey MT5 Data Collector - Ticks & Candles
Loads credentials from environment variables (.env file)
"""

import os
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import time
from dotenv import load_dotenv

load_dotenv()

# --- Config ---
MT5_LOGIN    = int(os.getenv('MT5_LOGIN', '0'))
MT5_PASSWORD = os.getenv('MT5_PASSWORD', '')
MT5_SERVER   = os.getenv('MT5_SERVER', 'MetaQuotes-Demo')
TRADE_SYMBOL = "EURUSD"
CANDLE_TF    = mt5.TIMEFRAME_M1    # 1 minute candles
CANDLE_WINDOW = 100                # How many historical candles to pull on startup
TICK_STREAM_DURATION = 30          # Seconds to stream live ticks

def init_mt5():
    if mt5.initialize(login=MT5_LOGIN, password=MT5_PASSWORD, server=MT5_SERVER):
        print("✅ Connected to MT5!")
        return True
    else:
        print(f"❌ Could not connect! {mt5.last_error()}")
        return False

def fetch_candles():
    """Fetch last N candles"""
    rates = mt5.copy_rates_from_pos(TRADE_SYMBOL, CANDLE_TF, 0, CANDLE_WINDOW)
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    print(f"Pulled {len(df)} candles")
    print(df.tail(5)[['time', 'open', 'high', 'low', 'close', 'tick_volume']])
    return df

def stream_ticks(duration=TICK_STREAM_DURATION):
    """Stream live ticks for X seconds"""
    start = time.time()
    ticks = []
    while time.time() - start < duration:
        tick = mt5.symbol_info_tick(TRADE_SYMBOL)
        if tick:
            record = {
                'time': datetime.fromtimestamp(tick.time),
                'bid': tick.bid,
                'ask': tick.ask,
                'spread': (tick.ask - tick.bid)*10000
            }
            ticks.append(record)
            print(f"[{record['time']}]: Bid {record['bid']} Ask {record['ask']} Spread {record['spread']:.1f} pips")
        time.sleep(1)  # Adjust streaming speed here
    print(f"Streamed {len(ticks)} ticks")
    return pd.DataFrame(ticks)

def shutdown_mt5():
    mt5.shutdown()
    print("MT5 shutdown complete.")

if __name__ == "__main__":
    if init_mt5():
        print("--- CANDLE DATA ---")
        candles_df = fetch_candles()
        print("--- LIVE TICK STREAM ---")
        tick_df = stream_ticks()
        # (Optional) Save to CSV for experiments:
        candles_df.to_csv(f"{TRADE_SYMBOL}_candles.csv", index=False)
        tick_df.to_csv(f"{TRADE_SYMBOL}_ticks.csv", index=False)
        print("CSV files saved!")
        shutdown_mt5()
    else:
        print("Could not start data collector. Check credentials and MT5 state.")
