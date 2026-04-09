"""
Odyssey v2 - Cross-Asset Correlation Matrix
Detects hidden exposure and correlated risk across the portfolio.
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional
from datetime import datetime


class CorrelationMatrix:
    """
    Builds rolling correlation matrices from price returns to detect
    hidden portfolio exposure and prevent excessive correlated risk.
    """

    # Currency decomposition: which base/quote currencies each pair exposes
    CURRENCY_EXPOSURE = {
        'EURUSD': {'long': 'EUR', 'short': 'USD'},
        'GBPUSD': {'long': 'GBP', 'short': 'USD'},
        'USDJPY': {'long': 'USD', 'short': 'JPY'},
        'XAUUSD': {'long': 'XAU', 'short': 'USD'},
        'AUDUSD': {'long': 'AUD', 'short': 'USD'},
        'USDCAD': {'long': 'USD', 'short': 'CAD'},
        'USDCHF': {'long': 'USD', 'short': 'CHF'},
        'NZDUSD': {'long': 'NZD', 'short': 'USD'},
    }

    def __init__(self, window: int = 60, max_correlation: float = 0.75, max_currency_exposure: float = 3.0):
        """
        Args:
            window: rolling window for correlation computation (bars)
            max_correlation: max allowed pairwise correlation before flagging
            max_currency_exposure: max net directional lots in any single currency
        """
        self.window = window
        self.max_correlation = max_correlation
        self.max_currency_exposure = max_currency_exposure
        self._returns_cache: Dict[str, np.ndarray] = {}

    def load_returns(self, symbol: str, prices: np.ndarray):
        """Compute and cache log returns from price series."""
        if len(prices) < 2:
            return
        returns = np.diff(np.log(prices))
        returns = returns[~np.isnan(returns)]
        self._returns_cache[symbol] = returns

    def compute_correlation_matrix(self) -> Tuple[pd.DataFrame, List[str]]:
        """
        Build pairwise correlation matrix from cached returns.
        Returns (correlation_df, list_of_symbols).
        """
        symbols = sorted(self._returns_cache.keys())
        if len(symbols) < 2:
            return pd.DataFrame(), symbols

        # Align lengths (use shortest)
        min_len = min(len(self._returns_cache[s]) for s in symbols)
        min_len = min(min_len, self.window)

        data = {s: self._returns_cache[s][-min_len:] for s in symbols}
        df = pd.DataFrame(data)
        corr = df.corr()

        return corr, symbols

    def get_high_correlations(self) -> List[Dict]:
        """Find all pairs with correlation above threshold."""
        corr, symbols = self.compute_correlation_matrix()
        if corr.empty:
            return []

        flagged = []
        for i, s1 in enumerate(symbols):
            for j, s2 in enumerate(symbols):
                if i >= j:
                    continue
                c = corr.loc[s1, s2]
                if abs(c) >= self.max_correlation:
                    flagged.append({
                        'pair': (s1, s2),
                        'correlation': float(c),
                        'risk': 'HIGH' if abs(c) > 0.9 else 'ELEVATED',
                    })

        return flagged

    # ============================
    # Currency Exposure Analysis
    # ============================
    def compute_net_currency_exposure(self, open_positions: Dict[str, Dict]) -> Dict[str, float]:
        """
        Compute net directional exposure per base currency.

        Args:
            open_positions: {symbol: {'direction': 'BUY'|'SELL', 'volume': float}}

        Returns:
            {currency: net_lots} (positive = long, negative = short)
        """
        exposure: Dict[str, float] = {}

        for symbol, pos in open_positions.items():
            if symbol not in self.CURRENCY_EXPOSURE:
                continue

            mapping = self.CURRENCY_EXPOSURE[symbol]
            direction = 1.0 if pos['direction'] == 'BUY' else -1.0
            volume = pos['volume'] * direction

            long_ccy = mapping['long']
            short_ccy = mapping['short']

            exposure[long_ccy] = exposure.get(long_ccy, 0.0) + volume
            exposure[short_ccy] = exposure.get(short_ccy, 0.0) - volume

        return exposure

    def check_correlation_risk(self, new_symbol: str, new_direction: str,
                                new_volume: float,
                                open_positions: Dict[str, Dict]) -> Tuple[bool, Dict]:
        """
        Check if adding a new position creates excessive correlated risk.

        Returns:
            (is_approved, analysis_dict)
        """
        analysis = {
            'timestamp': datetime.utcnow().isoformat(),
            'new_order': {'symbol': new_symbol, 'direction': new_direction, 'volume': new_volume},
            'flags': [],
            'approved': True,
        }

        # 1. Check pairwise correlation
        high_corrs = self.get_high_correlations()
        for hc in high_corrs:
            s1, s2 = hc['pair']
            # Flag if the new symbol is in a highly correlated pair
            # AND we already have a position in the other symbol
            if new_symbol in (s1, s2):
                other = s2 if new_symbol == s1 else s1
                if other in open_positions:
                    existing_dir = open_positions[other]['direction']
                    # Same direction on correlated pairs = amplified risk
                    if (hc['correlation'] > 0 and new_direction == existing_dir) or \
                       (hc['correlation'] < 0 and new_direction != existing_dir):
                        analysis['flags'].append({
                            'type': 'CORRELATED_EXPOSURE',
                            'detail': f"{new_symbol}↔{other} corr={hc['correlation']:.2f}, same effective direction",
                            'severity': hc['risk'],
                        })

        # 2. Check net currency exposure
        projected_positions = dict(open_positions)
        projected_positions[new_symbol] = {
            'direction': new_direction,
            'volume': new_volume + open_positions.get(new_symbol, {}).get('volume', 0.0),
        }

        currency_exp = self.compute_net_currency_exposure(projected_positions)
        for ccy, net_lots in currency_exp.items():
            if abs(net_lots) > self.max_currency_exposure:
                analysis['flags'].append({
                    'type': 'EXCESSIVE_CURRENCY_EXPOSURE',
                    'detail': f"Net {ccy} exposure: {net_lots:+.2f} lots (limit: ±{self.max_currency_exposure})",
                    'severity': 'HIGH',
                })

        analysis['currency_exposure'] = currency_exp

        # Reject if any HIGH severity flags
        has_high = any(f['severity'] == 'HIGH' for f in analysis['flags'])
        analysis['approved'] = not has_high

        return analysis['approved'], analysis
