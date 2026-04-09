"""
Odyssey v2 - Extended Performance Metrics Calculator (Research-Grade)
Calculates all standard quantitative finance metrics for backtesting.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional


class MetricsCalculator:
    """
    Research-grade metrics calculator.
    Computes: Sharpe, Sortino, Calmar, Information Ratio, Profit Factor,
    Recovery Factor, Max Drawdown, consecutive streaks and more.
    """

    def __init__(self, risk_free_rate: float = 0.02, periods_per_year: int = 252):
        self.risk_free_rate = risk_free_rate
        self.periods_per_year = periods_per_year

    def calculate(self, equity_curve: List[float], trades: List[Dict[str, Any]],
                  initial_balance: float = 100000.0,
                  benchmark_returns: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Calculate full suite of performance metrics.

        Args:
            equity_curve:       list of balance snapshots after each trade
            trades:             list of trade dicts with 'pnl' key
            initial_balance:    starting account balance
            benchmark_returns:  optional array of buy-and-hold returns for
                                information ratio calculation
        """
        if not trades:
            return self._empty_metrics()

        eq = np.array(equity_curve, dtype=float)
        final_balance = float(eq[-1])
        net_profit = final_balance - initial_balance
        return_pct = net_profit / initial_balance

        # ― Trade-level arrays ―
        pnls = np.array([t['pnl'] for t in trades])
        wins = pnls[pnls > 0]
        losses = pnls[pnls <= 0]
        n = len(pnls)

        win_rate = float(len(wins) / n) if n > 0 else 0.0
        profit_factor = float(wins.sum() / abs(losses.sum())) if losses.sum() != 0 else float('inf')
        avg_trade = float(np.mean(pnls))
        best_trade = float(np.max(wins)) if len(wins) > 0 else 0.0
        worst_trade = float(np.min(losses)) if len(losses) > 0 else 0.0

        # ― Equity Curve Analytics ―
        peak = np.maximum.accumulate(eq)
        drawdown = (eq - peak) / peak
        max_drawdown = float(abs(np.min(drawdown)))

        # ― Trade Returns (sequential per-trade returns) ―
        balance_track = initial_balance
        trade_returns = []
        for t in trades:
            ret = t['pnl'] / balance_track if balance_track != 0 else 0
            trade_returns.append(ret)
            balance_track += t['pnl']
        ret_arr = np.array(trade_returns)

        # ― Sharpe Ratio ―
        excess = ret_arr - (self.risk_free_rate / self.periods_per_year)
        std_ret = np.std(ret_arr, ddof=1) if len(ret_arr) > 1 else 0
        sharpe = float(np.mean(excess) / std_ret * np.sqrt(self.periods_per_year)) if std_ret > 0 else 0.0

        # ― Sortino Ratio (downside deviation only) ―
        downside = ret_arr[ret_arr < 0]
        down_std = np.std(downside, ddof=1) if len(downside) > 1 else 1e-9
        sortino = float(np.mean(excess) / down_std * np.sqrt(self.periods_per_year)) if down_std > 0 else 0.0

        # ― Calmar Ratio (annualized return / max drawdown) ―
        # Approximate annualization: assume 252 trades/year
        annual_return = return_pct * (self.periods_per_year / max(n, 1))
        calmar = float(annual_return / max_drawdown) if max_drawdown > 0 else 0.0

        # ― Recovery Factor (net profit / max drawdown in $) ―
        max_dd_usd = max_drawdown * initial_balance
        recovery_factor = float(net_profit / max_dd_usd) if max_dd_usd > 0 else 0.0

        # ― Information Ratio vs. benchmark ―
        information_ratio = 0.0
        if benchmark_returns is not None and len(benchmark_returns) == len(ret_arr):
            active_returns = ret_arr - benchmark_returns
            tracking_err = np.std(active_returns, ddof=1)
            if tracking_err > 0:
                information_ratio = float(np.mean(active_returns) / tracking_err * np.sqrt(self.periods_per_year))

        # ― Consecutive Win/Loss Streaks ―
        max_win_streak, max_loss_streak, cur_win, cur_loss = 0, 0, 0, 0
        for p in pnls:
            if p > 0:
                cur_win += 1
                cur_loss = 0
            else:
                cur_loss += 1
                cur_win = 0
            max_win_streak = max(max_win_streak, cur_win)
            max_loss_streak = max(max_loss_streak, cur_loss)

        # ― Expectancy (per trade, normalized) ―
        avg_win = float(np.mean(wins)) if len(wins) > 0 else 0.0
        avg_loss = float(np.mean(np.abs(losses))) if len(losses) > 0 else 0.0
        expectancy = (win_rate * avg_win) - ((1 - win_rate) * avg_loss)

        return {
            # Core
            'total_trades': n,
            'net_profit': round(net_profit, 2),
            'return_pct': round(return_pct, 4),
            'final_balance': round(final_balance, 2),

            # Risk-Adjusted Returns
            'sharpe_ratio': round(sharpe, 4),
            'sortino_ratio': round(sortino, 4),
            'calmar_ratio': round(calmar, 4),
            'information_ratio': round(information_ratio, 4),

            # Drawdown
            'max_drawdown': round(max_drawdown, 4),
            'max_drawdown_usd': round(max_dd_usd, 2),
            'recovery_factor': round(recovery_factor, 4),

            # Trade Quality
            'win_rate': round(win_rate, 4),
            'profit_factor': round(profit_factor, 4),
            'expectancy': round(expectancy, 2),
            'average_trade': round(avg_trade, 2),
            'best_trade': round(best_trade, 2),
            'worst_trade': round(worst_trade, 2),

            # Streak Analysis
            'max_consecutive_wins': max_win_streak,
            'max_consecutive_losses': max_loss_streak,

            # Raw returns for statistical validator
            '_trade_returns': trade_returns,
        }

    def _empty_metrics(self) -> Dict[str, Any]:
        keys = [
            'total_trades', 'net_profit', 'return_pct', 'final_balance',
            'sharpe_ratio', 'sortino_ratio', 'calmar_ratio', 'information_ratio',
            'max_drawdown', 'max_drawdown_usd', 'recovery_factor',
            'win_rate', 'profit_factor', 'expectancy', 'average_trade',
            'best_trade', 'worst_trade', 'max_consecutive_wins',
            'max_consecutive_losses'
        ]
        m = {k: 0.0 for k in keys}
        m['total_trades'] = 0
        m['_trade_returns'] = []
        return m
