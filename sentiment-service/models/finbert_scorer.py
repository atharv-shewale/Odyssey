"""
Odyssey v2 - FinBERT Sentiment Scorer
Uses ProsusAI/finbert to score financial headlines as bullish/bearish/neutral.
"""

import os
import warnings
warnings.filterwarnings('ignore')
from typing import Dict, List, Tuple

import torch
import numpy as np


class FinBERTScorer:
    """
    Financial sentiment scorer using ProsusAI/finbert transformer model.
    Provides batch inference and net sentiment scoring.
    """

    MODEL_NAME = "ProsusAI/finbert"

    def __init__(self, device: str = None, cache_dir: str = None):
        """
        Args:
            device: 'cpu' or 'cuda' (auto-detects if None)
            cache_dir: where to cache the downloaded model
        """
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.cache_dir = cache_dir or os.path.join(
            os.path.dirname(os.path.abspath(__file__)), '..', 'model_cache'
        )
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self) -> bool:
        """Load FinBERT model and tokenizer. Returns True on success."""
        if self._loaded:
            return True

        try:
            from transformers import AutoTokenizer, AutoModelForSequenceClassification

            self.tokenizer = AutoTokenizer.from_pretrained(
                self.MODEL_NAME, cache_dir=self.cache_dir
            )
            self.model = AutoModelForSequenceClassification.from_pretrained(
                self.MODEL_NAME, cache_dir=self.cache_dir
            )
            self.model.to(self.device)
            self.model.eval()
            self._loaded = True
            return True

        except ImportError:
            print("transformers library required: pip install transformers")
            return False
        except Exception as e:
            print(f"Failed to load FinBERT: {e}")
            return False

    @torch.no_grad()
    def score_headline(self, headline: str) -> Dict:
        """
        Score a single headline.

        Returns:
            {
                'headline': str,
                'positive': float,   # probability of bullish sentiment
                'negative': float,   # probability of bearish sentiment
                'neutral': float,    # probability of neutral sentiment
                'net_score': float,  # positive - negative (range: -1 to +1)
                'label': str,        # 'BULLISH', 'BEARISH', or 'NEUTRAL'
            }
        """
        if not self._loaded:
            if not self.load():
                return self._fallback_score(headline)

        try:
            inputs = self.tokenizer(
                headline,
                return_tensors='pt',
                truncation=True,
                max_length=128,
                padding=True,
            ).to(self.device)

            outputs = self.model(**inputs)
            probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()[0]

            # FinBERT labels: [positive, negative, neutral]
            positive, negative, neutral = float(probs[0]), float(probs[1]), float(probs[2])
            net_score = positive - negative

            if positive > max(negative, neutral):
                label = 'BULLISH'
            elif negative > max(positive, neutral):
                label = 'BEARISH'
            else:
                label = 'NEUTRAL'

            return {
                'headline': headline,
                'positive': positive,
                'negative': negative,
                'neutral': neutral,
                'net_score': net_score,
                'label': label,
            }

        except Exception as e:
            return self._fallback_score(headline)

    def score_batch(self, headlines: List[str]) -> List[Dict]:
        """Score multiple headlines efficiently using batch inference."""
        if not self._loaded:
            if not self.load():
                return [self._fallback_score(h) for h in headlines]

        if not headlines:
            return []

        try:
            inputs = self.tokenizer(
                headlines,
                return_tensors='pt',
                truncation=True,
                max_length=128,
                padding=True,
            ).to(self.device)

            with torch.no_grad():
                outputs = self.model(**inputs)

            probs = torch.softmax(outputs.logits, dim=1).cpu().numpy()
            results = []

            for i, headline in enumerate(headlines):
                positive, negative, neutral = float(probs[i][0]), float(probs[i][1]), float(probs[i][2])
                net_score = positive - negative

                if positive > max(negative, neutral):
                    label = 'BULLISH'
                elif negative > max(positive, neutral):
                    label = 'BEARISH'
                else:
                    label = 'NEUTRAL'

                results.append({
                    'headline': headline,
                    'positive': positive,
                    'negative': negative,
                    'neutral': neutral,
                    'net_score': net_score,
                    'label': label,
                })

            return results

        except Exception:
            return [self._fallback_score(h) for h in headlines]

    @staticmethod
    def _fallback_score(headline: str) -> Dict:
        """Fallback neutral score when model isn't available."""
        return {
            'headline': headline,
            'positive': 0.33,
            'negative': 0.33,
            'neutral': 0.34,
            'net_score': 0.0,
            'label': 'NEUTRAL',
        }
