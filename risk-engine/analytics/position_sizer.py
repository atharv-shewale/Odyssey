"""
Odyssey v2 - Dynamic Kelly Criterion Position Sizer
Computes optimal position size based on model confidence,
portfolio heat, and risk parameters.
"""

import numpy as np
from typing import Dict, Tuple
from datetime import datetime


class KellyPositionSizer:
    """
    Dynamic position sizer using Kelly Criterion with safety caps.
    Uses Half-Kelly by default to reduce variance at the cost of
    slightly lower expected growth.
    """

    def __init__(self,
                 account_balance: float = 100000,
                 max_risk_per_trade: float = 0.02,
                 max_portfolio_heat: float = 0.10,
                 kelly_fraction: float = 0.5,
                 min_lot: float = 0.01,
                 max_lot: float = 10.0):
        """
        Args:
            account_balance: total account value in USD
            max_risk_per_trade: max risk per single trade as fraction of account
            max_portfolio_heat: max total risk across all open trades
            kelly_fraction: fraction of Kelly to use (0.5 = half-Kelly)
            min_lot: minimum tradeable lot size
            max_lot: maximum lot size
        """
        self.account_balance = account_balance
        self.max_risk_per_trade = max_risk_per_trade
        self.max_portfolio_heat = max_portfolio_heat
        self.kelly_fraction = kelly_fraction
        self.min_lot = min_lot
        self.max_lot = max_lot

    def update_balance(self, balance: float):
        """Update account balance (e.g., from MT5 account info)."""
        self.account_balance = balance

    def kelly_optimal_fraction(self, win_prob: float, avg_win: float, avg_loss: float) -> float:
        """
        Compute Kelly optimal fraction.

        Kelly formula: f* = (p * b - q) / b
        where:
            p = probability of winning
            q = 1 - p = probability of losing
            b = ratio of avg win to avg loss (odds)

        Returns:
            optimal fraction of capital to risk (before kelly_fraction scaling)
        """
        if avg_loss <= 0 or avg_win <= 0 or win_prob <= 0 or win_prob >= 1:
            return 0.0

        p = win_prob
        q = 1.0 - p
        b = avg_win / avg_loss  # payout odds
        f_star = (p * b - q) / b

        # Cap at 0 (don't bet on negative edge)
        return max(0.0, f_star)

    def cvar_optimal_fraction(self, expected_return: float, cvar_pct: float) -> float:
        """
        Implementation of Fractional Kelly using CVaR.
        f* = 0.25 * (Expected Return / CVaR^2)
        Units must be in un-levered portfolio percent.
        """
        if expected_return <= 0 or cvar_pct <= 0:
            return 0.0
        # 0.25 acts as the fractional "Safety" multiplier on the theoretical maximum
        f_star = 0.25 * (expected_return / (cvar_pct ** 2))
        return max(0.0, f_star)

    def compute_portfolio_heat(self, open_positions: Dict[str, Dict]) -> float:
        """
        Compute current portfolio heat: total risk of all open positions
        as fraction of account balance.

        Args:
            open_positions: {symbol: {'volume': float, 'risk_usd': float}}

        Returns:
            portfolio heat as fraction (0.0 - 1.0)
        """
        total_risk = sum(pos.get('risk_usd', 0.0) for pos in open_positions.values())
        return total_risk / self.account_balance if self.account_balance > 0 else 1.0

    def calculate_position_size(self,
                                 symbol: str,
                                 direction: str,
                                 confidence: float,
                                 stop_loss_pips: float,
                                 pip_value: float,
                                 open_positions: Dict[str, Dict] = None,
                                 historical_win_rate: float = 0.55,
                                 historical_rr: float = 1.5) -> Dict:
        """
        Calculate optimal position size with Kelly + portfolio heat adjustment.

        Args:
            symbol: trading instrument
            direction: 'BUY' or 'SELL'
            confidence: model confidence (0-1), used as proxy for win probability
            stop_loss_pips: distance to stop loss in pips
            pip_value: value of 1 pip per 1 lot in account currency
            open_positions: current open positions for heat calculation
            historical_win_rate: historical strategy win rate (fallback)
            historical_rr: historical risk/reward ratio (fallback)

        Returns:
            Dict with sizing details and final volume
        """
        open_positions = open_positions or {}

        # 1. Estimate win probability from model confidence
        # Blend: 60% model confidence + 40% historical rate
        win_prob = confidence * 0.6 + historical_win_rate * 0.4
        win_prob = np.clip(win_prob, 0.01, 0.99)

        # 2. Institutional Tail-Risk Kelly (using CVaR)
        # Convert pips to percentage of price to get expected return pct
        # We assume 1 pip = 0.0001 for proxy if exact price unknown, but simpler:
        # We use a proxy cvar_pct built from recent volatility or just structural limits.
        # Fallback to standard Kelly if CVaR isn't passed (handled in risk_engine)
        avg_win = stop_loss_pips * historical_rr  # expected win in pips
        avg_loss = stop_loss_pips  # expected loss in pips
        kelly_full = self.kelly_optimal_fraction(win_prob, avg_win, avg_loss)
        
        # We apply the 0.25 institutional safety cap globally now
        kelly_scaled = kelly_full * 0.25 

        # 3. Portfolio heat adjustment
        current_heat = self.compute_portfolio_heat(open_positions)
        remaining_heat = max(0.0, self.max_portfolio_heat - current_heat)
        heat_multiplier = min(1.0, remaining_heat / self.max_risk_per_trade) if self.max_risk_per_trade > 0 else 0.0

        # 4. Final risk fraction
        risk_fraction = min(kelly_scaled, self.max_risk_per_trade) * heat_multiplier

        # 5. Convert to lot size
        risk_usd = self.account_balance * risk_fraction
        if stop_loss_pips > 0 and pip_value > 0:
            lot_size = risk_usd / (stop_loss_pips * pip_value)
        else:
            lot_size = self.min_lot

        # Clamp to min/max
        lot_size = np.clip(lot_size, self.min_lot, self.max_lot)
        lot_size = round(lot_size, 2)

        # Actual risk with final lot size
        actual_risk_usd = lot_size * stop_loss_pips * pip_value

        result = {
            'timestamp': datetime.utcnow().isoformat(),
            'symbol': symbol,
            'direction': direction,
            'confidence': confidence,
            'win_prob_blended': float(win_prob),
            'kelly_full': float(kelly_full),
            'kelly_scaled': float(kelly_scaled),
            'portfolio_heat': float(current_heat),
            'heat_multiplier': float(heat_multiplier),
            'risk_fraction': float(risk_fraction),
            'risk_usd': float(actual_risk_usd),
            'volume': float(lot_size),
            'stop_loss_pips': stop_loss_pips,
        }

        return result
