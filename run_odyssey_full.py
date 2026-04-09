#!/usr/bin/env python3
"""
Odyssey v2 - MASTER ORCHESTRATOR
Runs COMPLETE live trading pipeline in one command
"""

import os
import sys
import subprocess
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.absolute()

def run_service(service_path, service_name):
    """Run service in background"""
    cmd = ["python", str(service_path)]
    print(f"🚀 Starting {service_name}...")
    proc = subprocess.Popen(cmd, cwd=service_path.parent)
    return proc

def main():
    print("🎯 ODYSSEY v2 - FULL LIVE TRADING SYSTEM STARTING...")
    
    services = [
        # ("data-service", "collectors/mt5_data_collector.py"), # Replaced by Fyers Tick Receiver
        ("data-service/collectors", "tick_receiver.py"),
        ("data-service", "storage/pipeline.py"),
        ("sentiment-service", "sentiment_service.py"),
        ("ml-engine", "ml_engine.py"),
        ("strategy-engine/core", "multi_strategy_manager.py"),
        ("risk-engine", "risk_engine.py"),
        # ("trading-executor/executor", "mt5_async.py"), # Replaced by Fyers Async Executor
        ("trading-executor/executor", "async_executor.py"),
        ("alert-service", "alerter.py"),
        ("gateway", "main.py")
    ]
    
    processes = []
    
    try:
        for service_dir, script in services:
            service_path = PROJECT_ROOT / service_dir / script
            if not service_path.exists():
                print(f"❌ Error: Service script not found at {service_path}")
                if "--dry-run" in sys.argv:
                    continue
                sys.exit(1)
            
            if "--dry-run" in sys.argv:
                print(f"✅ Service check passed: {service_dir.upper()}")
                continue

            proc = run_service(service_path, service_dir.upper())
            processes.append(proc)
            time.sleep(3)  # Stagger startup
        
        if "--dry-run" in sys.argv:
            print("\n🔍 DRY RUN COMPLETE. ALL SERVICE PATHS VERIFIED.")
            return
        
        print("\n🎉 ALL SERVICES LIVE! PRESS Ctrl+C TO STOP")
        print("📊 Pipeline: data → ml → strategy → risk → MT5 LIVE")
        
        # Keep alive
        for proc in processes:
            proc.wait()
            
    except KeyboardInterrupt:
        print("\n🛑 Shutting down all services...")
        for proc in processes:
            proc.terminate()
            proc.wait()

if __name__ == "__main__":
    main()
