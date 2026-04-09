"""
Odyssey v2 - Performance Metrics Engine
Calculates Sharpe, Sortino, Max Drawdown, and Alpha/Beta.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional


class PerformanceMetrics:
    """
    Standard quantitative finance performance metrics.
    """

    @staticmethod
    def calculate_sharpe_ratio(returns: np.ndarray, rf_rate: float = 0.0, periods_per_year: int = 252) -> float:
        """Annualized Sharpe Ratio."""
        if len(returns) < 2: return 0.0
        excess_returns = returns - (rf_rate / periods_per_year)
        std = np.std(excess_returns)
        if std == 0: return 0.0
        return np.mean(excess_returns) / std * np.sqrt(periods_per_year)

    @staticmethod
    def calculate_sortino_ratio(returns: np.ndarray, rf_rate: float = 0.0, periods_per_year: int = 252) -> float:
        """Annualized Sortino Ratio (only considers downside volatility)."""
        if len(returns) < 2: return 0.0
        excess_returns = returns - (rf_rate / periods_per_year)
        downside_returns = excess_returns[excess_returns < 0]
        if len(downside_returns) < 2: return 0.0
        downside_std = np.std(downside_returns)
        if downside_std == 0: return 0.0
        return np.mean(excess_returns) / downside_std * np.sqrt(periods_per_year)

    @staticmethod
    def calculate_max_drawdown(equity_curve: np.ndarray) -> float:
        """Maximum peak-to-trough decline."""
        if len(equity_curve) < 2: return 0.0
        peak = np.maximum.accumulate(equity_curve)
        drawdown = (equity_curve - peak) / peak
        return float(np.min(drawdown))

    @staticmethod
    def calculate_alpha_beta(returns: np.ndarray, benchmark_returns: np.ndarray) -> Tuple[float, float]:
        """Alpha and Beta relative to a benchmark."""
        if len(returns) != len(benchmark_returns) or len(returns) < 2:
            return 0.0, 1.0
        
        covariance = np.cov(returns, benchmark_returns)[0, 1]
        benchmark_variance = np.var(benchmark_returns)
        
        beta = covariance / benchmark_variance if benchmark_variance != 0 else 1.0
        alpha = np.mean(returns) - beta * np.mean(benchmark_returns)
        
        return float(alpha * 252), float(beta) # Annualized alpha

    @classmethod
    def get_full_report(cls, returns: np.ndarray, equity_curve: np.ndarray) -> Dict:
        """Generate a complete performance summary."""
        return {
            'sharpe': cls.calculate_sharpe_ratio(returns),
            'sortino': cls.calculate_sortino_ratio(returns),
            'max_drawdown': cls.calculate_max_drawdown(equity_curve),
            'total_return': (equity_curve[-1] / equity_curve[0]) - 1 if len(equity_curve) > 0 else 0,
            'volatility_ann': np.std(returns) * np.sqrt(252),
        }
