"""
Odyssey v2 - Research-Grade Backtesting Engine (Phase 7)
=========================================================
Event-driven, Walk-Forward, with full Statistical Validation.
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, '..'))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'shared', 'python'))
sys.path.insert(0, os.path.join(PROJECT_ROOT, 'ml-engine'))

from logger import OdysseyLogger
from backtesting.metrics_calculator import MetricsCalculator
from backtesting.statistical_validator import StatisticalValidator
from backtesting.report_generator import ReportGenerator
from backtesting.data_loader import HistoricalDataLoader

logger = OdysseyLogger('backtester')


class SimpleBacktester:
    """
    Event-driven backtester with:
    - Realistic spread, latency, commission models
    - Walk-Forward Optimization (WFO)  
    - Buy-and-Hold benchmark comparison
    - Full statistical significance validation
    """

    def __init__(self, initial_balance: float = 100000.0,
                 spread_pips: float = 1.0,
                 latency_ms: int = 50,
                 commission_per_lot: float = 3.5):
        self.initial_balance = initial_balance
        self.spread_pips = spread_pips
        self.latency_ms = latency_ms
        self.commission_per_lot = commission_per_lot

        self.metrics_calc = MetricsCalculator()
        self.stat_validator = StatisticalValidator()
        self.report_gen = ReportGenerator(os.path.join(CURRENT_DIR, 'reports'))
        self.data_loader = HistoricalDataLoader()

        self.pip_value = 10.0
        self.pip_multiplier = 0.0001

    def _setup_symbol_params(self, symbol: str):
        if 'JPY' in symbol:
            self.pip_multiplier = 0.01
            self.pip_value = 6.8
        elif 'XAU' in symbol:
            self.pip_multiplier = 0.01
            self.pip_value = 10.0
        elif 'INR' in symbol or symbol in ('NIFTY50', 'SENSEX', 'BANKNIFTY'):
            self.pip_multiplier = 0.01
            self.pip_value = 1.0
        else:
            self.pip_multiplier = 0.0001
            self.pip_value = 10.0

    def _simulate(self, df: pd.DataFrame, signal_func, params: Dict[str, Any],
                  starting_balance: float) -> tuple:
        """
        Core bar-by-bar event simulation loop.
        Works with any callable signal_func(row_features) → (prob, confidence).
        """
        tp_pips = params.get('take_profit_pips', 40.0)
        sl_pips = params.get('stop_loss_pips', 20.0)
        lot_size = params.get('lot_size', 1.0)
        confidence_thresh = params.get('confidence_threshold', 0.6)
        lookback = params.get('lookback', 30)

        balance = starting_balance
        equity_curve = [starting_balance]
        trades = []
        pos = None
        buffer = []

        closes = df['close'].values
        highs = df['high'].values
        lows = df['low'].values
        timestamps = df.index.strftime('%Y-%m-%d %H:%M:%S').values if hasattr(df.index, 'strftime') else df.index.astype(str).values

        feature_cols = [c for c in df.columns if c not in ('open', 'high', 'low', 'close', 'volume')]
        has_features = len(feature_cols) > 0

        for i in range(len(df)):
            close_p = closes[i]
            high_p = highs[i]
            low_p = lows[i]
            ts = timestamps[i]

            # --- Manage Open Position ---
            if pos is not None:
                closed = False
                exit_price = 0.0

                if pos['action'] == 'BUY':
                    if low_p <= pos['sl']:
                        exit_price = pos['sl']
                        closed = True
                    elif high_p >= pos['tp']:
                        exit_price = pos['tp']
                        closed = True
                else:  # SELL
                    if high_p >= pos['sl']:
                        exit_price = pos['sl']
                        closed = True
                    elif low_p <= pos['tp']:
                        exit_price = pos['tp']
                        closed = True

                if closed:
                    pip_diff = (exit_price - pos['entry_price']) / self.pip_multiplier
                    if pos['action'] == 'SELL':
                        pip_diff = -pip_diff

                    # Transaction cost model
                    pip_diff -= self.spread_pips
                    pip_diff -= (self.latency_ms / 100.0) * 0.1  # latency slippage

                    pnl = pip_diff * self.pip_value * pos['volume']
                    pnl -= self.commission_per_lot * pos['volume'] * 2  # round-trip

                    balance += pnl
                    pos['exit_time'] = ts
                    pos['exit_price'] = exit_price
                    pos['pnl'] = pnl
                    trades.append(pos)
                    equity_curve.append(balance)
                    pos = None

            # --- Build Feature Buffer ---
            row = df.iloc[i]
            if has_features:
                feat_vec = row[feature_cols].fillna(0.5).values
            else:
                # Use basic OHLCV features if no indicators
                feat_vec = np.array([
                    close_p, high_p - low_p,
                    (close_p - low_p) / max(high_p - low_p, 1e-9)
                ])

            buffer.append(feat_vec)
            if len(buffer) > lookback:
                buffer.pop(0)

            # --- Entry Signal ---
            if pos is None and len(buffer) == lookback:
                try:
                    prob, confidence = signal_func(np.array(buffer))
                except Exception:
                    continue

                if confidence >= confidence_thresh:
                    action = 'BUY' if prob > 0.5 else 'SELL'
                    spread_adj = self.spread_pips * self.pip_multiplier
                    entry_price = close_p + (spread_adj if action == 'BUY' else -spread_adj)

                    sl = (entry_price - sl_pips * self.pip_multiplier if action == 'BUY'
                          else entry_price + sl_pips * self.pip_multiplier)
                    tp = (entry_price + tp_pips * self.pip_multiplier if action == 'BUY'
                          else entry_price - tp_pips * self.pip_multiplier)

                    pos = {
                        'action': action, 'entry_price': entry_price,
                        'sl': sl, 'tp': tp, 'volume': lot_size,
                        'time': ts, 'confidence': float(confidence)
                    }

        # Close any open position at end of data
        if pos is not None:
            exit_price = closes[-1]
            pip_diff = (exit_price - pos['entry_price']) / self.pip_multiplier
            if pos['action'] == 'SELL':
                pip_diff = -pip_diff
            pip_diff -= self.spread_pips
            pnl = pip_diff * self.pip_value * pos['volume']
            pnl -= self.commission_per_lot * pos['volume'] * 2
            balance += pnl
            pos['exit_time'] = timestamps[-1]
            pos['exit_price'] = exit_price
            pos['pnl'] = pnl
            trades.append(pos)
            equity_curve.append(balance)

        return balance, equity_curve, trades

    def _make_random_signal_func(self, seed: int = 42):
        """Returns a random signal function (used for benchmark comparison)."""
        rng = np.random.default_rng(seed)
        def _random(buffer):
            prob = rng.random()
            return prob, 0.7
        return _random

    def _bah_return(self, df: pd.DataFrame) -> float:
        """Buy-and-Hold return over the data period."""
        if len(df) < 2:
            return 0.0
        return float((df['close'].iloc[-1] / df['close'].iloc[0]) - 1)

    def run_full(self, symbol: str, timeframe: str = 'D1',
                 signal_func=None, params: Dict[str, Any] = None,
                 period_days: int = 365, wfo_splits: int = 5,
                 n_stat_trials: int = 1) -> Dict:
        """
        Run a complete research-grade backtest:
        1. Fetch data via DataLoader
        2. Walk-Forward Optimization
        3. Calculate extended metrics
        4. Run statistical validation
        5. Generate HTML + LaTeX reports

        Args:
            symbol:       Odyssey symbol (EURUSD, NIFTY50, etc.)
            timeframe:    D1, H1, M15, etc.
            signal_func:  callable(buffer: np.ndarray) → (prob: float, confidence: float)
                          If None, uses a synthetic random HOLD benchmark
            params:       backtest params (TP, SL, lot size, confidence threshold)
            period_days:  look-back history period
            wfo_splits:   number of WFO folds
            n_stat_trials: number of strategies tested (for DSR)
        """
        logger.info(f"[Backtest] Starting {symbol} {timeframe} — WFO={wfo_splits} splits")
        params = params or {
            'take_profit_pips': 40.0,
            'stop_loss_pips': 20.0,
            'lot_size': 1.0,
            'confidence_threshold': 0.60,
            'lookback': 30
        }

        self._setup_symbol_params(symbol)

        # 1. Load historical data
        df = self.data_loader.load(symbol, timeframe, period_days)
        if df is None or len(df) < 100:
            return {'error': f'Insufficient data for {symbol} {timeframe}'}

        # Default signal function: RF shadow model mock (prob=0.5+noise)
        if signal_func is None:
            rng = np.random.default_rng(seed=99)
            def signal_func(buffer):
                # Deterministic rule: if last close > N-bar mean → BUY
                closes = buffer[:, 0] if buffer.ndim > 1 else buffer
                prob = 0.52 + 0.1 * (np.sign(closes[-1] - np.mean(closes)) * 0.5)
                return float(min(max(prob, 0.0), 1.0)), 0.65
            logger.warning("No signal_func provided — using simple momentum rule")

        # 2. Walk-Forward Optimization
        fold_size = max(len(df) // (wfo_splits + 1), 50)
        all_trades = []
        equity_curve = [self.initial_balance]
        current_balance = self.initial_balance

        for fold in range(wfo_splits):
            train_end = (fold + 1) * fold_size
            test_end = train_end + fold_size if fold < wfo_splits - 1 else len(df)

            df_oos = df.iloc[train_end:test_end].copy()
            if len(df_oos) < 10:
                continue

            logger.info(f"  WFO Fold {fold + 1}/{wfo_splits}: OOS={len(df_oos)} bars")
            final_bal, fold_eq, fold_trades = self._simulate(
                df_oos, signal_func, params, current_balance
            )

            all_trades.extend(fold_trades)
            equity_curve.extend(fold_eq[1:])
            current_balance = final_bal

        logger.info(f"[Backtest] WFO complete. {len(all_trades)} trades. Final: ${current_balance:.2f}")

        if not all_trades:
            return {'error': 'No trades generated — lower confidence_threshold or check data'}

        # 3. Buy-and-Hold Benchmark
        bah_return = self._bah_return(df)
        bah_final = self.initial_balance * (1 + bah_return)
        logger.info(f"[Benchmark] Buy-and-Hold return: {bah_return*100:.2f}%")

        # 4. Extended Metrics
        bench_ret = self.data_loader.get_benchmark_returns('SPX500', timeframe, period_days)
        metrics = self.metrics_calc.calculate(equity_curve, all_trades, self.initial_balance, bench_ret)
        metrics['wfo_splits'] = wfo_splits
        metrics['bah_return_pct'] = round(bah_return, 4)
        metrics['bah_final_balance'] = round(bah_final, 2)
        metrics['vs_benchmark'] = round(metrics['return_pct'] - bah_return, 4)

        # 5. Statistical Validation
        trade_returns = np.array(metrics.pop('_trade_returns', []))
        if len(trade_returns) > 10:
            stat_result = self.stat_validator.validate_all(
                trade_returns, n_trials=n_stat_trials
            )
            metrics['statistical_validation'] = stat_result
        else:
            metrics['statistical_validation'] = {'error': 'Insufficient trades for validation (need > 10)'}

        # 6. Generate Reports
        report_path = self.report_gen.generate(symbol, timeframe, metrics, equity_curve, all_trades)
        self.report_gen.generate_latex(symbol, timeframe, metrics, params)

        # 7. Save JSON for dashboard
        json_path = os.path.join(CURRENT_DIR, 'reports', f'latest_{symbol}.json')
        with open(json_path, 'w') as f:
            json.dump({k: v for k, v in metrics.items() if k != 'statistical_validation'}, f, indent=2, default=str)
        stat_json_path = os.path.join(CURRENT_DIR, 'reports', f'stats_{symbol}.json')
        with open(stat_json_path, 'w') as f:
            json.dump(metrics.get('statistical_validation', {}), f, indent=2, default=str)

        logger.info(f"[Backtest] Report: {report_path}")
        metrics['report_path'] = report_path
        return metrics


if __name__ == '__main__':
    bt = SimpleBacktester()
    result = bt.run_full('EURUSD', 'D1', period_days=365, wfo_splits=5)
    print(f"\nSharpe: {result.get('sharpe_ratio')}")
    print(f"Sortino: {result.get('sortino_ratio')}")
    print(f"Calmar: {result.get('calmar_ratio')}")
    print(f"Win Rate: {result.get('win_rate', 0)*100:.1f}%")
    sv = result.get('statistical_validation', {})
    tt = sv.get('sharpe_ttest', {})
    print(f"Sharpe p-value: {tt.get('p_value')} (Significant: {tt.get('significant')})")
    print(f"Overall: {sv.get('overall_verdict', {}).get('summary')}")
