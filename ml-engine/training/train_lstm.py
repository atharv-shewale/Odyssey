"""
Odyssey v2 - LSTM Training Pipeline
Trains a production LSTM model on multi-timeframe historical CSV data
with time-series aware splitting (no lookahead bias).

Usage:
    python train_lstm.py
    python train_lstm.py --symbols EURUSD XAUUSD --epochs 50
"""

import os
import sys
import argparse
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import List, Tuple

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader

import warnings
warnings.filterwarnings('ignore')

# Import paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
ML_ENGINE_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
PROJECT_ROOT = os.path.abspath(os.path.join(ML_ENGINE_DIR, ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "data-service"))

from processors.indicators import TechnicalIndicators
from logger import OdysseyLogger

# Import our LSTM model
sys.path.insert(0, ML_ENGINE_DIR)
from models.lstm_model import OdysseyLSTM, LSTMNet

logger = OdysseyLogger('lstm-training')


# ============================================================
# Dataset
# ============================================================
class TimeSeriesDataset(Dataset):
    """Sliding-window dataset for LSTM training."""

    def __init__(self, X: np.ndarray, y: np.ndarray):
        self.X = torch.tensor(X, dtype=torch.float32)
        self.y = torch.tensor(y, dtype=torch.float32).unsqueeze(1)

    def __len__(self):
        return len(self.X)

    def __getitem__(self, idx):
        return self.X[idx], self.y[idx]


# ============================================================
# Data Loading & Feature Engineering
# ============================================================
def load_and_compute_features(symbols: List[str], timeframes: List[str], project_root: str) -> pd.DataFrame:
    """Load CSV data, compute indicators, and merge multi-TF features."""
    indicators = TechnicalIndicators()
    all_symbol_dfs = []

    for symbol in symbols:
        tf_features = {}

        for tf in timeframes:
            csv_path = os.path.join(project_root, "data", "historical", f"{symbol}_{tf}_candles.csv")
            if not os.path.exists(csv_path):
                logger.warning(f"CSV not found: {csv_path}, skipping")
                continue

            df = pd.read_csv(csv_path)
            if 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
            df['timestamp'] = pd.to_datetime(df['timestamp'])

            if 'volume' not in df.columns and 'tick_volume' in df.columns:
                df['volume'] = df['tick_volume']
            elif 'volume' not in df.columns:
                df['volume'] = 0

            df = df.sort_values('timestamp').reset_index(drop=True)
            df_feat = indicators.compute_all_features(df, symbol)
            tf_features[tf] = df_feat
            logger.info(f"Loaded {len(df_feat)} bars for {symbol} {tf}")

        if 'M1' not in tf_features:
            logger.warning(f"No M1 data for {symbol}, skipping")
            continue

        # Base = M1 features
        base = tf_features['M1'].copy()

        # Add multi-TF context columns (forward-fill to align with M1 timestamps)
        for tf, prefix in [('M5', 'm5'), ('H1', 'h1')]:
            if tf in tf_features and not tf_features[tf].empty:
                tf_df = tf_features[tf][['timestamp', 'rsi_14', 'macd', 'atr_14']].copy()
                tf_df = tf_df.rename(columns={
                    'rsi_14': f'{prefix}_rsi_14',
                    'macd': f'{prefix}_macd',
                    'atr_14': f'{prefix}_atr_14',
                })
                base = pd.merge_asof(
                    base.sort_values('timestamp'),
                    tf_df.sort_values('timestamp'),
                    on='timestamp',
                    direction='backward'
                )

        base['symbol'] = symbol
        all_symbol_dfs.append(base)

    if not all_symbol_dfs:
        return pd.DataFrame()

    combined = pd.concat(all_symbol_dfs, ignore_index=True)
    logger.info(f"Total combined data: {len(combined)} rows")
    return combined


def create_sequences(df: pd.DataFrame, feature_cols: List[str], lookback: int = 30) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create sliding-window sequences with binary target (next bar UP/DOWN).
    Returns X: (N, lookback, features), y: (N,)
    """
    # Create target: 1 if next close > current close
    df = df.copy()
    df['target'] = (df['close'].shift(-1) > df['close']).astype(float)

    # Drop NaN rows
    df = df.dropna(subset=feature_cols + ['target'])

    features = df[feature_cols].values
    targets = df['target'].values

    X, y = [], []
    for i in range(lookback, len(features) - 1):
        X.append(features[i - lookback:i])
        y.append(targets[i])

    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


# ============================================================
# Training Loop
# ============================================================
def train_lstm(symbols, timeframes, project_root, output_dir, epochs=50, lr=0.001, lookback=30, batch_size=64):
    """Full LSTM training pipeline."""

    # 1. Load and prepare data
    logger.info("Loading and computing features...")
    df = load_and_compute_features(symbols, timeframes, project_root)
    if df.empty:
        logger.error("No data loaded - check CSV files in data/historical/")
        return None

    # 2. Create sequences
    feature_cols = OdysseyLSTM.FEATURE_COLS
    
    # Fill missing multi-TF columns with 0.5 (neutral)
    for col in feature_cols:
        if col not in df.columns:
            df[col] = 0.5
            logger.warning(f"Missing feature column '{col}' — filled with 0.5")

    logger.info(f"Creating sequences (lookback={lookback})...")
    X, y = create_sequences(df, feature_cols, lookback)

    if len(X) < 100:
        logger.error(f"Insufficient sequences: {len(X)} (need >= 100)")
        return None

    logger.info(f"Total sequences: {len(X)}, shape: {X.shape}")
    logger.info(f"Class balance: UP={y.mean():.2%}, DOWN={1 - y.mean():.2%}")

    # 3. Time-series split (80/20, no shuffle)
    split = int(len(X) * 0.8)
    X_train, X_val = X[:split], X[split:]
    y_train, y_val = y[:split], y[split:]

    train_ds = TimeSeriesDataset(X_train, y_train)
    val_ds = TimeSeriesDataset(X_val, y_val)
    train_loader = DataLoader(train_ds, batch_size=batch_size, shuffle=False)
    val_loader = DataLoader(val_ds, batch_size=batch_size, shuffle=False)

    # 4. Model, loss, optimizer
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    logger.info(f"Training on device: {device}")

    model = LSTMNet(input_size=len(feature_cols)).to(device)
    criterion = nn.BCELoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer, patience=5, factor=0.5)

    # 5. Training loop
    best_val_loss = float('inf')
    best_val_acc = 0.0
    best_epoch = 0

    for epoch in range(epochs):
        # Train
        model.train()
        train_loss = 0.0
        train_correct = 0
        train_total = 0

        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)
            optimizer.zero_grad()
            output = model(X_batch)
            loss = criterion(output, y_batch)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
            optimizer.step()

            train_loss += loss.item() * len(X_batch)
            preds = (output > 0.5).float()
            train_correct += (preds == y_batch).sum().item()
            train_total += len(y_batch)

        # Validate
        model.eval()
        val_loss = 0.0
        val_correct = 0
        val_total = 0

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                output = model(X_batch)
                loss = criterion(output, y_batch)
                val_loss += loss.item() * len(X_batch)
                preds = (output > 0.5).float()
                val_correct += (preds == y_batch).sum().item()
                val_total += len(y_batch)

        avg_train_loss = train_loss / train_total
        avg_val_loss = val_loss / val_total
        train_acc = train_correct / train_total
        val_acc = val_correct / val_total

        scheduler.step(avg_val_loss)

        if avg_val_loss < best_val_loss:
            best_val_loss = avg_val_loss
            best_val_acc = val_acc
            best_epoch = epoch
            # Save best model
            os.makedirs(output_dir, exist_ok=True)
            model_path = os.path.join(output_dir, 'lstm_model.pt')
            torch.save({
                'model_state_dict': model.state_dict(),
                'input_size': len(feature_cols),
                'lookback': lookback,
                'feature_cols': feature_cols,
            }, model_path)

        if (epoch + 1) % 5 == 0 or epoch == 0:
            logger.info(
                f"Epoch {epoch + 1}/{epochs} | "
                f"Train Loss: {avg_train_loss:.4f} Acc: {train_acc:.4f} | "
                f"Val Loss: {avg_val_loss:.4f} Acc: {val_acc:.4f}"
            )

    logger.info(f"\nBest model at epoch {best_epoch + 1}: val_loss={best_val_loss:.4f}, val_acc={best_val_acc:.4f}")

    # 6. Save metadata
    metadata = {
        'model_type': 'LSTM',
        'architecture': {
            'input_size': len(feature_cols),
            'hidden_size': 128,
            'num_layers': 2,
            'dropout': 0.3,
            'lookback': lookback,
        },
        'features': feature_cols,
        'training': {
            'epochs': epochs,
            'lr': lr,
            'batch_size': batch_size,
            'train_samples': len(X_train),
            'val_samples': len(X_val),
            'best_epoch': best_epoch + 1,
            'best_val_loss': best_val_loss,
            'best_val_accuracy': best_val_acc,
        },
        'symbols': symbols,
        'timeframes': timeframes,
        'trained_at': datetime.utcnow().isoformat(),
    }

    meta_path = os.path.join(output_dir, 'lstm_model_metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to: {meta_path}")

    return model


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train Odyssey LSTM model')
    parser.add_argument('--symbols', nargs='+', default=['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'])
    parser.add_argument('--timeframes', nargs='+', default=['M1', 'M5', 'H1'])
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--lookback', type=int, default=30)
    parser.add_argument('--batch-size', type=int, default=64)
    args = parser.parse_args()

    output_dir = os.path.join(ML_ENGINE_DIR, 'models', 'saved')
    model = train_lstm(
        args.symbols, args.timeframes, PROJECT_ROOT, output_dir,
        epochs=args.epochs, lr=args.lr, lookback=args.lookback, batch_size=args.batch_size
    )

    if model:
        logger.info("LSTM Training COMPLETE — model ready for production!")
    else:
        logger.error("LSTM Training FAILED — check data and logs")
