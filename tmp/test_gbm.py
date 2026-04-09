import sys
import os

# Add workspace to path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))

from shared.python.market_simulator import StochasticEngine

def test_gbm():
    print("Starting GBM Test...", flush=True)
    engine = StochasticEngine(base_prices={"GOLD": 2000.0}, volatility=0.01)
    prices = []
    for _ in range(100): # Small sample
        tick = engine.get_next_tick("GOLD")
        prices.append(tick['price'])
    
    print(f"Generated 100 ticks. Start: {prices[0]:.2f}, End: {prices[-1]:.2f}", flush=True)
    print(f"Max: {max(prices):.2f}, Min: {min(prices):.2f}", flush=True)
    print(f"Change: {((prices[-1]/prices[0]) - 1)*100:.4f}%", flush=True)
    print("Test Complete.", flush=True)

if __name__ == "__main__":
    test_gbm()
