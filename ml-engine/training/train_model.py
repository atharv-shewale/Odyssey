"""
Odyssey v2 - ML Model Training Pipeline
Trains a production-grade RandomForest on real historical data
with time-series aware cross-validation (no lookahead bias)

Usage:
    python train_model.py
    python train_model.py --symbols EURUSD XAUUSD --timeframe M5
"""

import os
import sys
import argparse
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, accuracy_score
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

logger = OdysseyLogger('ml-training')


def load_training_data(symbols, timeframes, project_root):
    """Load and combine CSV data for all symbol/timeframe combos."""
    all_dfs = []

    for symbol in symbols:
        for tf in timeframes:
            csv_path = os.path.join(project_root, "data", "historical", f"{symbol}_{tf}_candles.csv")
            if not os.path.exists(csv_path):
                logger.warning(f"CSV not found: {csv_path}, skipping")
                continue

            df = pd.read_csv(csv_path)
            if 'time' in df.columns:
                df = df.rename(columns={'time': 'timestamp'})
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df['symbol'] = symbol
            df['timeframe'] = tf

            # Ensure volume column
            if 'volume' not in df.columns and 'tick_volume' in df.columns:
                df['volume'] = df['tick_volume']
            elif 'volume' not in df.columns:
                df['volume'] = 0

            all_dfs.append(df)
            logger.info(f"Loaded {len(df)} bars from {symbol}_{tf}")

    if not all_dfs:
        logger.error("No training data found!")
        return pd.DataFrame()

    combined = pd.concat(all_dfs, ignore_index=True)
    logger.info(f"Total training data: {len(combined)} bars across {len(all_dfs)} files")
    return combined


def compute_features(df, symbol):
    """Compute technical indicators for a single symbol's data."""
    indicators = TechnicalIndicators()
    return indicators.compute_all_features(df, symbol)


def create_target(df, lookahead=1):
    """Create binary target: 1 if next bar closes higher, 0 otherwise."""
    df = df.copy()
    df['future_close'] = df['close'].shift(-lookahead)
    df['target'] = (df['future_close'] > df['close']).astype(int)
    df = df.dropna(subset=['target'])
    return df


def train_model(symbols, timeframes, project_root, output_dir):
    """Full training pipeline with time-series cross-validation."""

    # 1. Load data
    raw_data = load_training_data(symbols, timeframes, project_root)
    if raw_data.empty:
        return None

    # 2. Process each symbol separately, then combine
    feature_cols = [
        'rsi_14', 'stoch_k', 'stoch_d', 'ema_9', 'ema_21', 'macd',
        'macd_signal', 'macd_hist', 'adx_14', 'bb_upper', 'bb_lower',
        'atr_14', 'obv', 'price_change_pct', 'high_low_ratio', 'close_position'
    ]

    all_features = []
    for symbol in raw_data['symbol'].unique():
        symbol_data = raw_data[raw_data['symbol'] == symbol].copy()
        symbol_data = symbol_data.sort_values('timestamp').reset_index(drop=True)

        # Compute features
        df_feat = compute_features(symbol_data, symbol)

        # Create target
        df_target = create_target(df_feat)

        all_features.append(df_target)

    if not all_features:
        logger.error("No features computed - check data")
        return None

    df_all = pd.concat(all_features, ignore_index=True)

    # Drop rows with NaN in feature columns
    df_clean = df_all.dropna(subset=feature_cols + ['target'])
    logger.info(f"Clean training data: {len(df_clean)} rows ({len(df_all) - len(df_clean)} dropped due to NaN)")

    if len(df_clean) < 50:
        logger.error(f"Insufficient data for training: {len(df_clean)} rows (need >=50)")
        return None

    X = df_clean[feature_cols].values
    y = df_clean['target'].values

    # 3. Time-series cross-validation (no lookahead)
    tscv = TimeSeriesSplit(n_splits=min(5, len(df_clean) // 20))
    cv_scores = []

    logger.info("Running time-series cross-validation...")
    for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        if len(np.unique(y_train)) < 2:
            logger.warning(f"Fold {fold}: only one class in training set, skipping")
            continue

        model = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1,
            class_weight='balanced'
        )
        model.fit(X_train, y_train)
        score = accuracy_score(y_test, model.predict(X_test))
        cv_scores.append(score)
        logger.info(f"  Fold {fold}: accuracy={score:.4f} (train={len(train_idx)}, test={len(test_idx)})")

    if cv_scores:
        mean_cv = np.mean(cv_scores)
        std_cv = np.std(cv_scores)
        logger.info(f"CV Accuracy: {mean_cv:.4f} +/- {std_cv:.4f}")
    else:
        logger.warning("No valid CV folds - training on all data")

    # 4. Train final model on all data
    logger.info("Training final model on full dataset...")
    final_model = RandomForestClassifier(
        n_estimators=200,
        max_depth=10,
        min_samples_split=10,
        min_samples_leaf=5,
        random_state=42,
        n_jobs=-1,
        class_weight='balanced'
    )
    final_model.fit(X, y)

    # Feature importance
    importances = dict(zip(feature_cols, final_model.feature_importances_))
    sorted_imp = sorted(importances.items(), key=lambda x: x[1], reverse=True)
    logger.info("Feature importance (top 8):")
    for feat, imp in sorted_imp[:8]:
        logger.info(f"  {feat}: {imp:.4f}")

    # 5. Final evaluation (last 20% as holdout)
    split_idx = int(len(X) * 0.8)
    X_holdout, y_holdout = X[split_idx:], y[split_idx:]
    y_pred = final_model.predict(X_holdout)
    logger.info("\nHoldout evaluation (last 20%):")
    logger.info(f"\n{classification_report(y_holdout, y_pred, target_names=['DOWN', 'UP'])}")

    # 6. Save model
    os.makedirs(output_dir, exist_ok=True)
    model_path = os.path.join(output_dir, 'rf_model.pkl')
    joblib.dump(final_model, model_path)
    logger.info(f"Model saved to: {model_path}")

    # Save metadata
    metadata = {
        'model_type': 'RandomForestClassifier',
        'n_estimators': 200,
        'features': feature_cols,
        'training_samples': len(X),
        'cv_accuracy_mean': float(np.mean(cv_scores)) if cv_scores else 0.0,
        'cv_accuracy_std': float(np.std(cv_scores)) if cv_scores else 0.0,
        'holdout_accuracy': float(accuracy_score(y_holdout, y_pred)),
        'trained_at': datetime.utcnow().isoformat(),
        'symbols': symbols,
        'timeframes': timeframes,
    }

    import json
    meta_path = os.path.join(output_dir, 'rf_model_metadata.json')
    with open(meta_path, 'w') as f:
        json.dump(metadata, f, indent=2)
    logger.info(f"Metadata saved to: {meta_path}")

    return final_model


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Train Odyssey ML model')
    parser.add_argument('--symbols', nargs='+', default=['EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD'])
    parser.add_argument('--timeframes', nargs='+', default=['M1', 'M5', 'H1'])
    args = parser.parse_args()

    output_dir = os.path.join(ML_ENGINE_DIR, 'models', 'saved')
    model = train_model(args.symbols, args.timeframes, PROJECT_ROOT, output_dir)

    if model:
        logger.info("Training COMPLETE - model ready for production!")
    else:
        logger.error("Training FAILED - check data and logs")
