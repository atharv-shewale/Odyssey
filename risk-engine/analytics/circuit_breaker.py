"""
Odyssey v2 - Drawdown Circuit Breaker
Multi-level escalating risk response to portfolio drawdown.
"""

from enum import IntEnum
from typing import Dict, Tuple, Optional
from datetime import datetime


class AlertLevel(IntEnum):
    """Circuit breaker alert levels."""
    NORMAL = 0      # No restrictions
    LEVEL_1 = 1     # Reduce position sizes by 50%
    LEVEL_2 = 2     # Only allow risk-reducing trades
    LEVEL_3 = 3     # Full halt — close everything


class CircuitBreaker:
    """
    Multi-level drawdown circuit breaker with automatic escalation
    and recovery. Protects capital during adverse market conditions.
    """

    DEFAULT_THRESHOLDS = {
        AlertLevel.LEVEL_1: 0.03,   # 3% drawdown
        AlertLevel.LEVEL_2: 0.06,   # 6% drawdown
        AlertLevel.LEVEL_3: 0.10,   # 10% drawdown
    }

    # Recovery requires drawdown to improve by this much before de-escalating
    RECOVERY_BUFFER = 0.01  # 1% buffer to prevent rapid flipping

    def __init__(self,
                 account_balance: float = 100000,
                 thresholds: Dict[AlertLevel, float] = None):
        """
        Args:
            account_balance: initial/peak account balance
            thresholds: {AlertLevel: drawdown_fraction} for each level
        """
        self.peak_equity = account_balance
        self.thresholds = thresholds or self.DEFAULT_THRESHOLDS
        self.current_level = AlertLevel.NORMAL
        self.last_trigger_time: Optional[str] = None
        self._history = []

    def update_equity(self, current_equity: float):
        """Update peak equity tracking."""
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity

    def get_drawdown(self, current_equity: float) -> float:
        """Calculate current drawdown from peak."""
        self.update_equity(current_equity)
        if self.peak_equity <= 0:
            return 0.0
        return (self.peak_equity - current_equity) / self.peak_equity

    def evaluate(self, current_equity: float) -> Tuple[AlertLevel, Dict]:
        """
        Evaluate current equity and determine circuit breaker level.

        Returns:
            (alert_level, details_dict)
        """
        drawdown = self.get_drawdown(current_equity)

        # Determine appropriate level
        new_level = AlertLevel.NORMAL
        for level in sorted(self.thresholds.keys(), reverse=True):
            if drawdown >= self.thresholds[level]:
                new_level = level
                break

        # Recovery logic: only de-escalate if drawdown dropped below
        # (threshold - buffer) to prevent rapid level flipping
        if new_level < self.current_level:
            recovery_threshold = self.thresholds[self.current_level] - self.RECOVERY_BUFFER
            if drawdown > recovery_threshold:
                new_level = self.current_level  # Stay at current level

        # Record level change
        if new_level != self.current_level:
            self._history.append({
                'timestamp': datetime.utcnow().isoformat(),
                'from_level': self.current_level.name,
                'to_level': new_level.name,
                'drawdown': drawdown,
                'equity': current_equity,
            })
            self.current_level = new_level
            self.last_trigger_time = datetime.utcnow().isoformat()

        details = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': self.current_level.name,
            'level_value': int(self.current_level),
            'drawdown': float(drawdown),
            'drawdown_pct': f"{drawdown:.2%}",
            'peak_equity': float(self.peak_equity),
            'current_equity': float(current_equity),
            'thresholds': {k.name: v for k, v in self.thresholds.items()},
        }

        return self.current_level, details

    def check_order(self, current_equity: float, order: Dict) -> Tuple[bool, Dict]:
        """
        Check if an order is allowed under current circuit breaker state.

        Args:
            current_equity: latest account equity
            order: order dict with 'action', 'volume', etc.

        Returns:
            (is_approved, modified_order_or_rejection)
        """
        level, details = self.evaluate(current_equity)

        result = {
            'circuit_breaker': details,
            'original_volume': order.get('volume', 0),
        }

        action = order.get('action', 'HOLD')

        if level == AlertLevel.NORMAL:
            # No restrictions
            result['approved'] = True
            result['volume'] = order.get('volume', 0)
            result['action'] = 'APPROVED'

        elif level == AlertLevel.LEVEL_1:
            # Reduce position sizes by 50%
            original_vol = order.get('volume', 0)
            reduced_vol = max(0.01, round(original_vol * 0.5, 2))
            result['approved'] = True
            result['volume'] = reduced_vol
            result['action'] = 'REDUCED'
            result['reduction_reason'] = f"L1 circuit breaker: {details['drawdown_pct']} drawdown"

        elif level == AlertLevel.LEVEL_2:
            # Only allow risk-reducing trades (closes, opposite-direction trades)
            is_risk_reducing = action in ('CLOSE', 'HEDGE')
            result['approved'] = is_risk_reducing
            result['volume'] = order.get('volume', 0) if is_risk_reducing else 0
            result['action'] = 'APPROVED' if is_risk_reducing else 'REJECTED'
            result['rejection_reason'] = (
                None if is_risk_reducing
                else f"L2 circuit breaker: only risk-reducing trades allowed ({details['drawdown_pct']} drawdown)"
            )

        elif level == AlertLevel.LEVEL_3:
            # Full halt — reject everything, signal to close all
            result['approved'] = False
            result['volume'] = 0
            result['action'] = 'HALTED'
            result['rejection_reason'] = f"L3 EMERGENCY HALT: {details['drawdown_pct']} drawdown — CLOSE ALL POSITIONS"
            result['close_all'] = True

        return result.get('approved', False), result

    def get_history(self) -> list:
        """Get circuit breaker level transition history."""
        return self._history

    def reset(self, new_peak: float):
        """Reset circuit breaker (e.g., after manual review)."""
        self.peak_equity = new_peak
        self.current_level = AlertLevel.NORMAL
        self._history.append({
            'timestamp': datetime.utcnow().isoformat(),
            'from_level': 'MANUAL_RESET',
            'to_level': 'NORMAL',
            'equity': new_peak,
        })
