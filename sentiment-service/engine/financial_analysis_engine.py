"""
Odyssey v2 - Financial Analysis & Explanation Engine
Correlates micro-technical (XAI) with macro-sentimental factors.
Generates human-readable "Deep Dive" explanations for the Terminal.
"""

from typing import Dict, List, Optional
import numpy as np


class FinancialAnalysisEngine:
    """
    Core engine for generating detailed trade/market explanations.
    Combines:
    1. ML Feature Importance (SHAP/Attention)
    2. Sentiment Aggregation (News & Social)
    3. Market Context (Regime, Correlation)
    """

    @staticmethod
    def generate_deep_dive(symbol: str, signal: Dict, sentiment_summary: Dict) -> Dict:
        """
        Produce a structured explanation for a given signal and sentiment context.
        """
        action = signal.get('action', 'HOLD')
        confidence = signal.get('confidence', 0.0)
        feat_imp = signal.get('feature_importance', {})
        
        # 1. Technical Explanation (from XAI)
        top_features = sorted(feat_imp.items(), key=lambda x: x[1], reverse=True)[:3]
        tech_summary = "Technical drivers: " + ", ".join([f"{f[0].upper()} ({f[1]*100:.1f}%)" for f in top_features])
        
        # 2. Sentiment Explanation
        pair_sentiment = sentiment_summary.get('pairs', {}).get(symbol, 0.0)
        recent_news = [h for h in sentiment_summary.get('recent_headlines', []) if symbol[:3] in h['headline'].upper() or symbol[3:] in h['headline'].upper()][:2]
        
        sent_flavor = "BULLISH" if pair_sentiment > 0.1 else ("BEARISH" if pair_sentiment < -0.1 else "NEUTRAL")
        sent_summary = f"Sentiment is currently {sent_flavor} ({pair_sentiment:+.2f})."
        
        news_context = ""
        if recent_news:
            news_context = " Key headlines: " + " | ".join([f"\"{h['headline'][:60]}...\" ({h['label']})" for h in recent_news])

        # 3. Combined Analysis
        combined_text = (
            f"Analysis for {symbol}: The model suggests a {action} position with {confidence*100:.1f}% confidence. "
            f"{tech_summary}. {sent_summary}{news_context}"
        )

        return {
            'symbol': symbol,
            'summary': combined_text,
            'technical_drivers': tech_summary,
            'sentiment_context': sent_summary,
            'key_headlines': recent_news,
            'confidence_score': confidence,
            'regime': signal.get('regime_cluster', 'Stable'),
            'sources': list(set([h.get('source', 'Multi-Source') for h in recent_news])) or ['Financial Terminals']
        }

    @staticmethod
    def get_market_mood(sentiment_summary: Dict) -> str:
        """Get a global 'Market Mood' string based on currency aggregates."""
        currencies = sentiment_summary.get('currencies', {})
        if not currencies: return "Neutral / Awaiting Data"
        
        bullish = [c for c, s in currencies.items() if s['score'] > 0.2]
        bearish = [c for c, s in currencies.items() if s['score'] < -0.2]
        
        if not bullish and not bearish: return "Consolidating / Low Volatility Mood"
        
        mood = ""
        if bullish: mood += f"Strong demand for {', '.join(bullish)}. "
        if bearish: mood += f"Pressure on {', '.join(bearish)}."
        
        return mood.strip()
