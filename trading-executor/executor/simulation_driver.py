import os
import sys
import time
import logging
from datetime import datetime

# Add necessary paths
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "shared", "python"))
sys.path.insert(0, CURRENT_DIR)

from market_simulator import StochasticEngine, HybridSimulator
from broker_connector import MockBrokerAPI

# Setup Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('sim-driver')

def run_stochastic_simulation():
    logger.info("🚀 Starting Rank 3: Stochastic (GBM) Simulation...")
    
    # 1. Initialize Simulator (Gold with 2% daily-ish vol)
    raw_engine = StochasticEngine(base_prices={"MCX:GOLDM24OCTFUT": 72000.0}, volatility=0.015)
    simulator = HybridSimulator(raw_engine, spread_pct=0.0002) # 0.02% spread
    
    # 2. Initialize Mock Broker with injected simulator
    broker = MockBrokerAPI(price_provider=simulator)
    broker.initialize()
    
    # 3. Initial State
    acc_init = broker.get_account_info()
    logger.info(f"Initial Balance: ₹{acc_init['balance']:.2f}")
    
    # 4. Scenario: Place a trade and watch it evolve
    symbol = "MCX:GOLDM24OCTFUT"
    logger.info(f"Placing BUY order for {symbol}...")
    order = broker.place_order(symbol=symbol, action="BUY", volume=1.0)
    
    if order.get('s') == 'ok':
        entry_price = order['price']
        logger.info(f"✅ Order Filled at ₹{entry_price:.2f}")
        
        # 5. Let the simulation run for a few "ticks"
        for i in range(10):
            time.sleep(0.5) # Speed up for demo
            acc = broker.get_account_info()
            pos = broker.get_open_positions()[0]
            
            # Since _get_latest_price advances the simulator, we see price movement
            logger.info(f"Tick {i+1}: P&L: ₹{acc['pnl']:.2f} | Current Equity: ₹{acc['equity']:.2f}")
            
            if i == 5:
                logger.info("Manual Check: Simulating a volatility spike...")
                # We could modify the raw_engine volatility here if needed
                
        # 6. Close the trade
        logger.info("Closing position to realize P&L...")
        broker.close_position(symbol)
        
        acc_final = broker.get_account_info()
        total_pnl = acc_final['balance'] - acc_init['balance']
        logger.info(f"💰 Simulation Finished.")
        logger.info(f"Final Balance: ₹{acc_final['balance']:.2f}")
        logger.info(f"Total Realized P&L: ₹{total_pnl:.2f}")
    else:
        logger.error("Order failed!")

if __name__ == "__main__":
    run_stochastic_simulation()
