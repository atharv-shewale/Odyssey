"""
Odyssey v2 - Advanced Monte Carlo VaR (Research Grade)
Computes portfolio-level risk using correlation-aware Multi-Asset Simulation.
Supports Gaussian and Student-T (Fat-tail) distributions.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime
from scipy.stats import t, norm


class PortfolioVaR:
    """
    Research-grade Portfolio Value at Risk calculator.
    Features:
    - Multi-Asset Correlation-aware Monte Carlo
    - Student-T distribution for fat-tail modeling
    - Expected Shortfall (CVaR) computation
    """

    def __init__(self, confidence_levels: List[float] = None, n_simulations: int = 20000, horizon_days: int = 1):
        self.confidence_levels = confidence_levels or [0.95, 0.99]
        self.n_simulations = n_simulations
        self.horizon_days = horizon_days
        self._returns_cache: Dict[str, np.ndarray] = {}
        self.symbols: List[str] = []

    def load_returns_from_prices(self, symbol: str, prices: np.ndarray):
        """Compute and cache log returns from a price series."""
        if len(prices) < 2:
            return
        returns = np.diff(np.log(prices))
        returns = returns[~np.isnan(returns)]
        self._returns_cache[symbol] = returns
        if symbol not in self.symbols:
            self.symbols.append(symbol)

    def get_returns_df(self) -> pd.DataFrame:
        """Align all cached returns into a single DataFrame for correlation analysis."""
        if not self._returns_cache:
            return pd.DataFrame()
        
        # Determine minimum length for alignment
        min_len = min(len(r) for r in self._returns_cache.values())
        data = {sym: r[-min_len:] for sym, r in self._returns_cache.items()}
        return pd.DataFrame(data)

    def compute_advanced_mc_portfolio(self, positions: Dict[str, float], use_t_dist: bool = True) -> Dict:
        """
        Correlation-aware Multi-Asset Monte Carlo Simulation.
        
        Args:
            positions: {symbol: usd_value}
            use_t_dist: if True, uses Student-T (df=5) for fat tails.
        """
        returns_df = self.get_returns_df()
        active_symbols = [s for s in self.symbols if s in positions]
        
        if len(active_symbols) == 0 or returns_df.empty:
            return {f"mc_var_{int(cl*100)}": 0.0 for cl in self.confidence_levels}

        # Filter and compute Covariance Matrix
        df_subset = returns_df[active_symbols]
        cov_matrix = df_subset.cov().values
        mu = df_subset.mean().values
        weights = np.array([positions[s] for s in active_symbols])
        
        # Cholesky Decomposition for correlated random variables
        try:
            L = np.linalg.cholesky(cov_matrix)
        except np.linalg.LinAlgError:
            # If not positive definite, use a small diagonal ridge
            ridge = np.eye(len(cov_matrix)) * 1e-8
            L = np.linalg.cholesky(cov_matrix + ridge)

        # Generate Random Innovations
        if use_t_dist:
            # Student-T distributed innovations (df=5 is standard for markets)
            Z = t.rvs(df=5, size=(self.n_simulations, len(active_symbols)))
        else:
            Z = np.random.normal(0, 1, (self.n_simulations, len(active_symbols)))

        # Correlated returns: R = mu + Z * L^T
        correlated_returns = mu + Z @ L.T
        
        # Portfolio P&L: sum(R_i * Value_i)
        portfolio_pnl = correlated_returns @ weights

        results = {}
        for cl in self.confidence_levels:
            # VaR is the (1-cl) percentile of losses
            var_value = -np.percentile(portfolio_pnl, (1 - cl) * 100)
            
            # CVaR (Expected Shortfall)
            tail_losses = portfolio_pnl[portfolio_pnl <= -var_value]
            cvar_value = -np.mean(tail_losses) if len(tail_losses) > 0 else var_value
            
            results[f"mc_var_{int(cl*100)}"] = max(0.0, float(var_value))
            results[f"mc_cvar_{int(cl*100)}"] = max(0.0, float(cvar_value))

        results['n_sims'] = self.n_simulations
        results['dist'] = 'Student-T' if use_t_dist else 'Gaussian'
        return results

    def portfolio_var(self, positions: Dict[str, float]) -> Dict:
        """
        Compute full portfolio risk profile including diversification benefits.
        """
        total_exposure = sum(abs(v) for v in positions.values())
        if total_exposure == 0:
            return {'portfolio': {'mc_var_95': 0.0, 'total_exposure': 0.0}}

        # Correlation-aware MC (The "Gold Standard")
        mc_results = self.compute_advanced_mc_portfolio(positions, use_t_dist=True)
        
        # Individual Parametric VaR (For reference/drill-down)
        component_var = {}
        for sym, val in positions.items():
            ret = self._returns_cache.get(sym)
            if ret is not None:
                std = np.std(ret)
                component_var[sym] = {
                    'var_95': abs(val) * 1.645 * std,
                    'var_99': abs(val) * 2.326 * std
                }

        return {
            'timestamp': datetime.utcnow().isoformat(),
            'portfolio': {
                **mc_results,
                'total_exposure': total_exposure,
                'diversification_benefit': sum(v['var_95'] for v in component_var.values()) - mc_results.get('mc_var_95', 0) if component_var else 0
            },
            'components': component_var
        }

    def check_var_limit(self, positions: Dict[str, float], max_var_pct: float = 0.05,
                        account_balance: float = 100000) -> Tuple[bool, Dict]:
        """Check if portfolio VaR is within limits."""
        var_result = self.portfolio_var(positions)
        max_var_usd = account_balance * max_var_pct

        current_var = var_result['portfolio'].get('mc_var_99', 0.0)
        is_ok = current_var <= max_var_usd

        var_result['risk_check'] = {
            'max_var_pct': max_var_pct,
            'max_var_usd': max_var_usd,
            'current_var_99': current_var,
            'approved': is_ok,
            'utilization': current_var / max_var_usd if max_var_usd > 0 else 0.0,
        }

        return is_ok, var_result

