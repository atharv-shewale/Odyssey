"""
Logging Utility for All Services
"""
import logging
import sys
from datetime import datetime
from pathlib import Path

class OdysseyLogger:
    """Centralized logger for Odyssey services"""
    
    def __init__(self, service_name: str, log_level=logging.INFO):
        """
        Initialize logger
        
        Args:
            service_name: Name of the service (e.g., 'ml-engine', 'data-service')
            log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        self.service_name = service_name
        self.logger = logging.getLogger(service_name)
        self.logger.setLevel(log_level)
        
        # Prevent duplicate handlers
        if self.logger.handlers:
            return
        
        # Create formatters
        detailed_formatter = logging.Formatter(
            '[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        simple_formatter = logging.Formatter(
            '[%(levelname)s] %(message)s'
        )
        
        # Console handler (stdout)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(log_level)
        console_handler.setFormatter(simple_formatter)
        self.logger.addHandler(console_handler)
        
        # File handler
        log_dir = Path(__file__).parent.parent.parent / 'logs' / service_name
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / f"{service_name}_{datetime.now().strftime('%Y%m%d')}.log"
        
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(detailed_formatter)
        self.logger.addHandler(file_handler)
    
    def debug(self, message: str):
        """Log debug message"""
        self.logger.debug(message)
    
    def info(self, message: str):
        """Log info message"""
        self.logger.info(message)
    
    def warning(self, message: str):
        """Log warning message"""
        self.logger.warning(message)
    
    def error(self, message: str, exc_info=False):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info)
    
    def critical(self, message: str, exc_info=False):
        """Log critical message"""
        self.logger.critical(message, exc_info=exc_info)
    
    def log_trade(self, trade_info: dict):
        """Log trade execution"""
        self.info(f"TRADE: {trade_info}")
    
    def log_signal(self, signal_info: dict):
        """Log trading signal"""
        self.info(f"SIGNAL: {signal_info}")
    
    def log_prediction(self, prediction_info: dict):
        """Log ML prediction"""
        self.info(f"PREDICTION: {prediction_info}")
    
    def log_error_with_context(self, error: Exception, context: dict):
        """Log error with additional context"""
        self.error(f"Error: {str(error)} | Context: {context}", exc_info=True)


# Example usage
if __name__ == "__main__":
    # Test logger
    logger = OdysseyLogger('test-service', log_level=logging.DEBUG)
    
    logger.debug("This is a debug message")
    logger.info("This is an info message")
    logger.warning("This is a warning message")
    logger.error("This is an error message")
    
    # Test trade logging
    logger.log_trade({
        'symbol': 'EURUSD',
        'side': 'BUY',
        'price': 1.0880,
        'volume': 0.1
    })
    
    print("✅ Logger test complete - check logs/ directory")
