import threading
from prometheus_client import start_http_server, Counter, Gauge, Histogram
from logger import OdysseyLogger

logger = OdysseyLogger('metrics')

class OdysseyMetrics:
    """Standardized Prometheus metrics for Odyssey v2 services"""
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(OdysseyMetrics, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
            
        # Core Platform Metrics
        self.events_processed = Counter('odyssey_events_processed_total', 'Total events processed', ['service_name', 'event_type'])
        self.errors_total = Counter('odyssey_errors_total', 'Total errors encountered', ['service_name', 'error_type'])
        self.system_latency = Histogram('odyssey_system_latency_seconds', 'Latency of various operations', ['service_name', 'operation'])
        
        # Strategy & Pipeline specific
        self.active_positions = Gauge('odyssey_active_positions', 'Number of open trades', ['symbol'])
        self.signal_strength = Gauge('odyssey_signal_strength', 'Strength of latest ML signal', ['symbol'])
        self.account_equity = Gauge('odyssey_account_equity', 'Current MT5 Account Equity')
        self.account_balance = Gauge('odyssey_account_balance', 'Current MT5 Account Balance')
        self.daily_pnl = Gauge('odyssey_daily_pnl', 'Daily Profit/Loss')
        
        self.server_thread = None
        self._initialized = True

    def start_server(self, port: int):
        """Start the Prometheus HTTP metrics server in a background thread"""
        try:
            start_http_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
        except Exception as e:
            logger.error(f"Failed to start Prometheus server on port {port}: {e}")

# Global singleton
metrics = OdysseyMetrics()
