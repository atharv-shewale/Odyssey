"""
Odyssey v2 - XAI LSTM Deep Learning Model
Sequence-aware neural network with Temporal Attention and Feature Importance.
Architecture: LSTM → Self-Attention → FC → Sigmoid
"""

import os
import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Dict, Optional, Tuple, Any


class AttentionLSTMNet(nn.Module):
    """PyTorch Attention-LSTM network for XAI price movement prediction."""

    def __init__(self, input_size: int, hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.3):
        super(AttentionLSTMNet, self).__init__()
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0.0,
        )
        
        # Temporal Attention Mechanism
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.Tanh(),
            nn.Linear(hidden_size // 2, 1)
        )
        
        self.dropout = nn.Dropout(dropout)
        self.fc = nn.Linear(hidden_size, 1)
        self.sigmoid = nn.Sigmoid()

    def forward(self, x: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """
        Returns:
            out: (batch, 1) probability of UP movement
            attn_weights: (batch, seq_len, 1) temporal attention weights
        """
        # lstm_out: (batch, seq_len, hidden_size)
        lstm_out, _ = self.lstm(x)
        
        # Calculate attention weights
        # attn_scores: (batch, seq_len, 1)
        attn_scores = self.attention(lstm_out)
        attn_weights = F.softmax(attn_scores, dim=1)
        
        # Context vector (weighted sum of lstm outputs)
        # context: (batch, 1, hidden_size)
        context = torch.bmm(attn_weights.transpose(1, 2), lstm_out)
        context = context.squeeze(1) # (batch, hidden_size)
        
        out = self.dropout(context)
        out = self.fc(out)
        out = self.sigmoid(out)
        
        return out, attn_weights


class OdysseyLSTM:
    """
    Production XAI wrapper around the PyTorch Attention-LSTM model.
    Handles loading, saving, and extracting Explainable AI metrics (SHAP approx).
    """

    FEATURE_COLS = [
        'rsi_14', 'stoch_k', 'stoch_d', 'ema_9', 'ema_21', 'macd',
        'macd_signal', 'macd_hist', 'atr_14', 'adx_14', 'cci_14',
        'bb_upper', 'bb_lower', 'obv', 'vol_sma',
        'm5_rsi_14', 'm5_macd', 'm5_atr_14',
        'h1_rsi_14', 'h1_macd', 'h1_atr_14',
        'sentiment_score',
    ]

    def __init__(self, lookback: int = 30, device: str = 'cpu'):
        self.lookback = lookback
        self.device = torch.device(device)
        self.input_size = len(self.FEATURE_COLS)
        self.model = AttentionLSTMNet(input_size=self.input_size).to(self.device)
        self.model.eval()

        self.buffers: Dict[str, list] = {}

    def load(self, model_path: str) -> bool:
        if not os.path.exists(model_path): return False
        try:
            checkpoint = torch.load(model_path, map_location=self.device, weights_only=False)
            # Support loading both legacy LSTMNet and new AttentionLSTMNet
            state_dict = checkpoint['model_state_dict']
            self.model.load_state_dict(state_dict, strict=False)
            self.model.eval()
            return True
        except Exception:
            return False

    def save(self, model_path: str):
        os.makedirs(os.path.dirname(model_path), exist_ok=True)
        torch.save({
            'model_state_dict': self.model.state_dict(),
            'input_size': self.input_size,
            'lookback': self.lookback,
            'feature_cols': self.FEATURE_COLS,
        }, model_path)

    def _extract_features(self, features_dict: Dict) -> np.ndarray:
        return np.array([features_dict.get(f, 0.5) for f in self.FEATURE_COLS], dtype=np.float32)

    def update_buffer(self, symbol: str, features_dict: Dict):
        vec = self._extract_features(features_dict)
        if symbol not in self.buffers:
            self.buffers[symbol] = []
        self.buffers[symbol].append(vec)
        if len(self.buffers[symbol]) > self.lookback:
            self.buffers[symbol] = self.buffers[symbol][-self.lookback:]

    def is_ready(self, symbol: str) -> bool:
        return symbol in self.buffers and len(self.buffers[symbol]) >= self.lookback

    def explain_prediction(self, x: torch.Tensor) -> Dict[str, float]:
        """
        Fast Gradient-based Feature Importance (Approximation for SHAP).
        Calculates Input * Gradient to find local feature contribution.
        """
        x.requires_grad = True
        self.model.zero_grad()
        prob, _ = self.model(x)
        prob.backward()
        
        # importance = element-wise grad * input magnitude, sum over sequence
        grad = x.grad.data.abs().squeeze(0).cpu().numpy() # (seq_len, features)
        x_val = x.data.abs().squeeze(0).cpu().numpy()
        
        importance = np.sum(grad * x_val, axis=0)
        # Normalize to exactly 100%
        if np.sum(importance) > 0:
            importance = importance / np.sum(importance)
            
        feature_importance = {col: float(imp) for col, imp in zip(self.FEATURE_COLS, importance)}
        return feature_importance

    def predict(self, symbol: str, mc_samples: int = 20) -> Tuple[float, float, list, dict, float]:
        """
        Runs Bayesian XAI inference using Monte Carlo Dropout.
        Returns: (probability_mean, confidence, attention_weights, feature_importance, uncertainty_std)
        """
        if not self.is_ready(symbol):
            return 0.5, 0.0, [], {}, 0.0

        sequence = np.array(self.buffers[symbol][-self.lookback:], dtype=np.float32)
        x = torch.tensor(sequence, dtype=torch.float32).unsqueeze(0).to(self.device)

        # 1. Base Forward pass mapping (for Attention & SHAP)
        self.model.eval()
        prob_tensor, attn_tensor = self.model(x)
        prob = prob_tensor.item()
        
        # 2. Attention extraction
        attn_weights = attn_tensor.squeeze().detach().cpu().numpy().tolist()
        
        # 3. Feature Importance extraction
        feature_importance = self.explain_prediction(x)
        
        # 4. Monte Carlo Dropout for Uncertainty
        self.model.train() # Enable dropout layers for stochastic forward passes
        mc_predictions = []
        with torch.no_grad():
            for _ in range(mc_samples):
                p, _ = self.model(x)
                mc_predictions.append(p.item())
        
        self.model.eval() # Revert to eval mode
        
        prob_mean = float(np.mean(mc_predictions))
        prob_std = float(np.std(mc_predictions))

        confidence = min(1.0, abs(prob_mean - 0.5) * 2.0)

        return prob_mean, confidence, attn_weights, feature_importance, prob_std

    def predict_from_sequence(self, sequence: np.ndarray, mc_samples: int = 20) -> Tuple[float, float, list, dict, float]:
        x = torch.tensor(sequence, dtype=torch.float32).unsqueeze(0).to(self.device)
        self.model.eval()
        prob_tensor, attn_tensor = self.model(x)
        attn_weights = attn_tensor.squeeze().detach().cpu().numpy().tolist()
        feature_importance = self.explain_prediction(x)
        
        self.model.train()
        mc_predictions = []
        with torch.no_grad():
            for _ in range(mc_samples):
                p, _ = self.model(x)
                mc_predictions.append(p.item())
        self.model.eval()
        
        prob_mean = float(np.mean(mc_predictions))
        prob_std = float(np.std(mc_predictions))
        confidence = min(1.0, abs(prob_mean - 0.5) * 2.0)
        
        return prob_mean, confidence, attn_weights, feature_importance, prob_std
