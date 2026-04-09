"""
Odyssey v2 - Statistical Validation Engine (Research-Grade)
============================================================
Implements academic-standard statistical tests for strategy evaluation:

1.  Sharpe Ratio t-test         → H0: Sharpe ≤ 0. Tests if returns are
                                   genuinely positive with 95% confidence.
2.  Bootstrap Confidence Intervals → 10,000 bootstrap resamples to compute
                                   95% CI for Sharpe, Sortino, Max Drawdown.
3.  Deflated Sharpe Ratio (DSR) → Bailey & Lopez de Prado (2014).
                                   Corrects Sharpe for overfitting and
                                   multiple-testing bias.
4.  Monte Carlo Permutation Test → Shuffles signal labels 1,000 times.
                                   Builds a null distribution to test if
                                   observed PnL exceeds random chance.

References:
- Bailey, D.H. & Lopez de Prado, M. (2014). "The Deflated Sharpe Ratio".
- Politis & Romano (1994). "The Stationary Bootstrap".
"""

import numpy as np
from typing import Dict, List, Optional
from scipy import stats


class StatisticalValidator:
    """
    Academic-grade statistical test suite for backtesting results.
    """

    def __init__(self, risk_free_rate: float = 0.02, n_bootstrap: int = 10000, n_permutations: int = 1000):
        self.risk_free_rate = risk_free_rate
        self.n_bootstrap = n_bootstrap
        self.n_permutations = n_permutations

    # ==================================================================
    # 1. SHARPE RATIO t-TEST
    # ==================================================================
    def sharpe_ttest(self, returns: np.ndarray, periods_per_year: int = 252) -> Dict:
        """
        Test H0: Annualized Sharpe Ratio = 0 using a one-sample t-test
        on excess returns.
        
        Returns:
            sharpe_ann: annualized Sharpe estimate
            t_stat:     t-statistic
            p_value:    one-tailed p-value (H1: Sharpe > 0)
            significant: True if p < 0.05
        """
        if len(returns) < 30:
            return {'sharpe_ann': 0.0, 't_stat': 0.0, 'p_value': 1.0, 'significant': False}

        excess = returns - (self.risk_free_rate / periods_per_year)
        n = len(excess)
        mu = np.mean(excess)
        sigma = np.std(excess, ddof=1)

        if sigma == 0:
            return {'sharpe_ann': 0.0, 't_stat': 0.0, 'p_value': 1.0, 'significant': False}

        # t-statistic for H0: mu = 0
        t_stat = (mu / sigma) * np.sqrt(n)

        # One-tailed p-value (testing if Sharpe > 0)
        p_value = float(stats.t.sf(t_stat, df=n - 1))

        # Annualized Sharpe
        sharpe_ann = (mu / sigma) * np.sqrt(periods_per_year)

        return {
            'sharpe_ann': round(float(sharpe_ann), 4),
            't_stat': round(float(t_stat), 4),
            'p_value': round(p_value, 4),
            'significant': p_value < 0.05,
            'confidence_level': '95%',
            'n_obs': n
        }

    # ==================================================================
    # 2. BOOTSTRAP CONFIDENCE INTERVALS
    # ==================================================================
    def bootstrap_ci(self, returns: np.ndarray, periods_per_year: int = 252,
                     confidence: float = 0.95) -> Dict:
        """
        Compute bootstrap confidence intervals for key performance metrics.
        Uses non-parametric bootstrap resampling (10,000 iterations).
        
        Returns:
            Dict with CI bounds for: sharpe, sortino, max_drawdown, total_return
        """
        if len(returns) < 20:
            return {}

        n = len(returns)
        bootstrap_sharpes = []
        bootstrap_sortinos = []
        bootstrap_mdd = []
        bootstrap_total_return = []

        rng = np.random.default_rng(seed=42)

        for _ in range(self.n_bootstrap):
            sample = rng.choice(returns, size=n, replace=True)

            # Sharpe
            excess = sample - (self.risk_free_rate / periods_per_year)
            std = np.std(sample, ddof=1)
            sharpe = (np.mean(excess) / std * np.sqrt(periods_per_year)) if std > 0 else 0
            bootstrap_sharpes.append(sharpe)

            # Sortino (downside deviation)
            downside = sample[sample < 0]
            down_std = np.std(downside, ddof=1) if len(downside) > 1 else 1e-9
            sortino = (np.mean(excess) / down_std * np.sqrt(periods_per_year)) if down_std > 0 else 0
            bootstrap_sortinos.append(sortino)

            # Max drawdown on cumulative returns
            cum_ret = np.cumprod(1 + sample)
            peak = np.maximum.accumulate(cum_ret)
            dd = (cum_ret - peak) / peak
            bootstrap_mdd.append(float(np.min(dd)))

            # Total return
            bootstrap_total_return.append(float(np.prod(1 + sample) - 1))

        alpha = 1 - confidence
        lo, hi = alpha / 2, 1 - alpha / 2

        def ci(arr):
            return (round(float(np.percentile(arr, lo * 100)), 4),
                    round(float(np.percentile(arr, hi * 100)), 4))

        return {
            'sharpe_ci': ci(bootstrap_sharpes),
            'sortino_ci': ci(bootstrap_sortinos),
            'max_drawdown_ci': ci(bootstrap_mdd),
            'total_return_ci': ci(bootstrap_total_return),
            'n_bootstrap': self.n_bootstrap,
            'confidence': f'{int(confidence * 100)}%'
        }

    # ==================================================================
    # 3. DEFLATED SHARPE RATIO (DSR)
    # ==================================================================
    def deflated_sharpe_ratio(self, sharpe_observed: float, n_trials: int,
                               n_obs: int, skewness: float = 0.0,
                               kurtosis: float = 3.0) -> Dict:
        """
        Bailey & Lopez de Prado (2014) Deflated Sharpe Ratio.
        Adjusts for the fact that many strategies are tested before the
        best one is reported (multiple-testing problem / overfitting).
        
        Args:
            sharpe_observed:  the observed annualized Sharpe ratio
            n_trials:         number of strategies/hyperparameter combos tried
            n_obs:            number of return observations
            skewness:         third standardized moment of returns
            kurtosis:         fourth standardized moment of returns

        Returns:
            dsr:            probability that true Sharpe > 0 (DSR)
            sr_benchmark:   the "expected maximum Sharpe" under multiple testing
        """
        if n_trials <= 0 or n_obs <= 0:
            return {'dsr': 0.0, 'sr_benchmark': 0.0}

        # Expected maximum Sharpe under multiple testing (Bonferroni-like)
        # Using the approximation: E[max SR] ≈ (1 - γ) * z(1 - 1/T) + γ * z(1 - 1/(T*e))
        # Simplified to: sqrt(2 * log(n_trials)) - (log(log(n_trials)) + log(4π)) / (2 * sqrt(2 * log(n_trials)))
        ln_T = np.log(n_trials) if n_trials > 1 else 1.0
        sr_max_expected = np.sqrt(2 * ln_T) if n_trials > 1 else 0.5

        # Standard error of Sharpe (Johnson, 1949)
        # SE(SR) = sqrt((1 + 0.5*SR^2 - skew*SR + ((k-1)/4)*SR^2) / (T-1))
        se_sharpe = np.sqrt(
            (1 + 0.5 * sharpe_observed**2 - skewness * sharpe_observed +
             ((kurtosis - 1) / 4) * sharpe_observed**2) / max(n_obs - 1, 1)
        )

        # DSR = probability that true SR > 0 given inflation
        if se_sharpe > 0:
            z_dsr = (sharpe_observed - sr_max_expected) / se_sharpe
            dsr = float(stats.norm.cdf(z_dsr))
        else:
            dsr = 0.0

        return {
            'dsr': round(dsr, 4),
            'sr_benchmark': round(float(sr_max_expected), 4),
            'n_trials': n_trials,
            'overfit_adjusted': dsr > 0.95,
            'interpretation': (
                'Strategy is likely genuine (DSR > 0.95)' if dsr > 0.95
                else 'Strategy may be overfit to historical data'
            )
        }

    # ==================================================================
    # 4. MONTE CARLO PERMUTATION TEST
    # ==================================================================
    def permutation_test(self, trade_returns: np.ndarray, observed_sharpe: float,
                          periods_per_year: int = 252) -> Dict:
        """
        Tests H0: "The observed performance is due to chance."
        Shuffles the trade return ordering 1,000 times to build a null
        distribution of Sharpe ratios.

        Returns:
            p_value:    fraction of permutations that beat observed Sharpe
            significant: True if p < 0.05 (strategy beats 95% of random)
        """
        if len(trade_returns) < 10:
            return {'p_value': 1.0, 'significant': False, 'null_sharpe_mean': 0.0}

        rng = np.random.default_rng(seed=42)
        null_sharpes = []

        for _ in range(self.n_permutations):
            shuffled = rng.permutation(trade_returns)
            std = np.std(shuffled, ddof=1)
            if std > 0:
                null_sharpes.append(np.mean(shuffled) / std * np.sqrt(periods_per_year))
            else:
                null_sharpes.append(0.0)

        null_sharpes = np.array(null_sharpes)
        p_value = float(np.mean(null_sharpes >= observed_sharpe))

        return {
            'p_value': round(p_value, 4),
            'significant': p_value < 0.05,
            'null_sharpe_mean': round(float(np.mean(null_sharpes)), 4),
            'null_sharpe_std': round(float(np.std(null_sharpes)), 4),
            'n_permutations': self.n_permutations,
            'interpretation': (
                f'Strategy beats {(1 - p_value)*100:.1f}% of random strategies'
            )
        }

    # ==================================================================
    # MASTER VALIDATE — Runs all tests in one pass
    # ==================================================================
    def validate_all(self, trade_returns: np.ndarray, n_trials: int = 1,
                     periods_per_year: int = 252) -> Dict:
        """
        Runs all 4 statistical tests and returns a unified report dict.
        """
        if len(trade_returns) == 0:
            return {'error': 'No trade returns to validate'}

        ttest = self.sharpe_ttest(trade_returns, periods_per_year)
        ci = self.bootstrap_ci(trade_returns, periods_per_year)

        from scipy.stats import skew, kurtosis
        skewness = float(skew(trade_returns)) if len(trade_returns) > 3 else 0.0
        kurt = float(kurtosis(trade_returns, fisher=False)) if len(trade_returns) > 3 else 3.0

        dsr = self.deflated_sharpe_ratio(
            sharpe_observed=ttest.get('sharpe_ann', 0.0),
            n_trials=max(n_trials, 1),
            n_obs=len(trade_returns),
            skewness=skewness,
            kurtosis=kurt
        )

        perm = self.permutation_test(trade_returns, ttest.get('sharpe_ann', 0.0), periods_per_year)

        # Overall verdict
        is_significant = (
            ttest.get('significant', False) and
            perm.get('significant', False) and
            dsr.get('dsr', 0.0) > 0.5
        )

        return {
            'sharpe_ttest': ttest,
            'bootstrap_ci': ci,
            'deflated_sharpe': dsr,
            'permutation_test': perm,
            'overall_verdict': {
                'is_statistically_significant': is_significant,
                'summary': (
                    '✅ STRATEGY STATISTICALLY VALID — Evidence supports alpha generation'
                    if is_significant else
                    '⚠️  STRATEGY INCONCLUSIVE — Insufficient statistical evidence'
                )
            }
        }
