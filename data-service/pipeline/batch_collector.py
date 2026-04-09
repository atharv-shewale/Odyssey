import os
import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

symbols = ['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD']
timeframes = {'M1': mt5.TIMEFRAME_M1, 'M5': mt5.TIMEFRAME_M5, 'H1': mt5.TIMEFRAME_H1}
CANDLE_WINDOW = 250  # Number of candles to fetch per symbol/tf

LOGIN    = int(os.getenv('MT5_LOGIN', '0'))
PASSWORD = os.getenv('MT5_PASSWORD', '')
SERVER   = os.getenv('MT5_SERVER', 'MetaQuotes-Demo')

if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
    print("❌ MT5 init error")
    exit()

for symbol in symbols:
    for tf_str, tf_val in timeframes.items():
        rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, CANDLE_WINDOW)
        if rates is None or len(rates) == 0:
            print(f"❌ No data for {symbol} {tf_str}, skipping.")
            continue
        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s')
        outpath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', f"{symbol}_{tf_str}_candles.csv")
        df.to_csv(outpath, index=False)
        print(f"✅ Saved {len(df)} candles for {symbol}-{tf_str} → {outpath}")

mt5.shutdown()
print("🔁 Batch candle generation run complete.")
