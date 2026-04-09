import os
import sys
import pandas as pd
import numpy as np

# Setup paths
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "ml-engine"))

from backtesting.backtester import SimpleBacktester
from models.lstm_model import OdysseyLSTM

def create_synthetic_data(filepath: str, rows: int = 500):
    np.random.seed(42)
    dates = pd.date_range(start="2026-01-01", periods=rows, freq="1min")
    
    df = pd.DataFrame({'time': dates})
    
    # OHLCV
    close_price = 1.0500 + np.cumsum(np.random.normal(0, 0.0001, rows))
    df['close'] = close_price
    df['open'] = close_price + np.random.normal(0, 0.0001, rows)
    df['high'] = df[['open', 'close']].max(axis=1) + abs(np.random.normal(0, 0.0001, rows))
    df['low'] = df[['open', 'close']].min(axis=1) - abs(np.random.normal(0, 0.0001, rows))
    df['volume'] = np.random.randint(10, 1000, size=rows)
    
    # Features required by LSTM 
    for col in OdysseyLSTM.FEATURE_COLS:
        if col not in df.columns:
            df[col] = np.random.uniform(0, 1, rows)
            
    df.to_csv(filepath, index=False)
    print(f"Created synthetic data: {filepath}")

def test_wfo():
    # 1. Create a dummy model
    model_dir = os.path.join(PROJECT_ROOT, "ml-engine", "models", "saved")
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, "dummy_lstm.pt")
    
    lstm = OdysseyLSTM(lookback=30)
    lstm.save(model_path)
    print(f"Saved dummy LSTM model to {model_path}")
    
    # 2. Create synthetic data
    data_dir = os.path.join(PROJECT_ROOT, "data", "historical")
    os.makedirs(data_dir, exist_ok=True)
    data_path = os.path.join(data_dir, "DUMMY_M1_features.csv")
    create_synthetic_data(data_path, rows=800)
    
    print("\n--- Testing Walk-Forward Optimization ---")
    bt = SimpleBacktester()
    params = {
        'take_profit_pips': 10.0,
        'stop_loss_pips': 5.0,
        'lot_size': 0.1,
        'confidence_threshold': 0.55
    }
    
    report_path = bt.run_walk_forward(
        symbol="DUMMY",
        timeframe="M1",
        data_path=data_path,
        model_path=model_path,
        params=params, 
        n_splits=3
    )
    
    print(f"\nSuccess! WFO Report HTML: {report_path}")
    print("Check backtesting/reports directory for .tex tearsheets as well.")

if __name__ == "__main__":
    test_wfo()
