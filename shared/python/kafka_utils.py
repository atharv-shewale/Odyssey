"""
Kafka Utilities for Event Streaming
"""
import os
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import KafkaError
import json
from typing import Callable, Dict, Any, List
from datetime import datetime
from dotenv import load_dotenv
from logger import OdysseyLogger

load_dotenv()

_logger = OdysseyLogger('kafka')
_DEFAULT_BOOTSTRAP = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')

class KafkaProducerClient:
    """Kafka producer for publishing events"""
    
    def __init__(self, bootstrap_servers=None):
        bootstrap_servers = bootstrap_servers or _DEFAULT_BOOTSTRAP
        """Initialize Kafka producer"""
        self.producer = KafkaProducer(
            bootstrap_servers=bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            key_serializer=lambda k: k.encode('utf-8') if k else None,
            acks='all',
            retries=3,
            max_in_flight_requests_per_connection=1
        )
        _logger.info("Kafka Producer connected")
    
    def send(self, topic: str, message: Dict[str, Any], key: str = None):
        """
        Send message to Kafka topic
        
        Args:
            topic: Kafka topic name
            message: Message dictionary
            key: Optional partition key
        """
        try:
            future = self.producer.send(topic, value=message, key=key)
            record_metadata = future.get(timeout=10)
            return record_metadata
        except KafkaError as e:
            _logger.error(f"Failed to send message: {e}")
            raise
    
    def send_batch(self, topic: str, messages: List[Dict[str, Any]]):
        """Send multiple messages"""
        for msg in messages:
            self.send(topic, msg)
        self.producer.flush()
    
    def close(self):
        """Close producer"""
        self.producer.close()


class KafkaConsumerClient:
    """Kafka consumer for receiving events"""
    
    def __init__(self, topics: List[str], group_id: str, 
                 bootstrap_servers=None):
        bootstrap_servers = bootstrap_servers or _DEFAULT_BOOTSTRAP
        """
        Initialize Kafka consumer
        
        Args:
            topics: List of topics to subscribe to
            group_id: Consumer group ID
            bootstrap_servers: Kafka broker address
        """
        self.consumer = KafkaConsumer(
            *topics,
            bootstrap_servers=bootstrap_servers,
            group_id=group_id,
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            max_poll_records=100
        )
        self.handlers = {}
        _logger.info(f"Kafka Consumer connected to topics: {topics}")
    
    def register_handler(self, topic: str, handler: Callable):
        """
        Register message handler for a topic
        
        Args:
            topic: Topic name
            handler: Function to handle messages (takes message dict)
        """
        self.handlers[topic] = handler
    
    def start(self):
        """Start consuming messages"""
        _logger.info("Starting Kafka consumer...")
        
        try:
            for message in self.consumer:
                topic = message.topic
                value = message.value
                
                # Call registered handler
                if topic in self.handlers:
                    try:
                        self.handlers[topic](value)
                    except Exception as e:
                        _logger.error(f"Error handling message from {topic}: {e}")
                else:
                    _logger.warning(f"No handler for topic: {topic}")
        
        except KeyboardInterrupt:
            _logger.info("Consumer stopped by user")
        finally:
            self.close()
    
    def close(self):
        """Close consumer"""
        self.consumer.close()
        _logger.info("Kafka Consumer closed")


# Topic name helpers
class KafkaTopics:
    """Standard Kafka topic names for Odyssey v2 Event Streaming"""
    
    MARKET_DATA_RAW = "market.data.raw"
    ML_SIGNALS = "ml.signals"
    TRADING_ORDERS = "trading.orders"
    TRADING_ORDERS_APPROVED = "trading.orders.approved"
    TRADING_EXECUTIONS = "trading.executions"
    SENTIMENT_SCORES = "sentiment.scores"
    ALERTS = "system.alerts"

# Example usage
if __name__ == "__main__":
    # Test producer
    producer = KafkaProducerClient()
    
    # Send test message
    test_message = {
        'symbol': 'EURUSD',
        'bid': 1.0880,
        'ask': 1.0882,
        'timestamp': int(datetime.now().timestamp() * 1000)
    }
    
    topic = KafkaTopics.MARKET_DATA_RAW
    producer.send(topic, test_message)
    _logger.info(f"Sent test message to {topic}")
    
    producer.close()
    
    # Test consumer
    def handle_tick(message):
        print(f"📨 Received tick: {message}")
    
    consumer = KafkaConsumerClient(
        topics=[topic],
        group_id='test-consumer-group'
    )
    
    consumer.register_handler(topic, handle_tick)
    
    print("Press Ctrl+C to stop...")
    # consumer.start()  # Uncomment to test consumption
