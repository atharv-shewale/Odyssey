"""
Test all shared utilities
"""
from redis_client import RedisClient
from questdb_client import QuestDBClient
from kafka_utils import KafkaProducerClient, KafkaTopics
from logger import OdysseyLogger

def test_all():
    """Test all utilities"""
    
    print("=" * 50)
    print("Testing Odyssey Shared Utilities")
    print("=" * 50)
    
    # 1. Test Logger
    print("\n1. Testing Logger...")
    logger = OdysseyLogger('test-utilities')
    logger.info("Logger initialized successfully")
    
    # 2. Test Redis
    print("\n2. Testing Redis...")
    try:
        redis_client = RedisClient()
        redis_client.set_feature('EURUSD', 'RSI_14', 65.5)
        feature = redis_client.get_feature('EURUSD', 'RSI_14')
        logger.info(f"Redis feature stored and retrieved: {feature}")
    except Exception as e:
        logger.error(f"Redis test failed: {e}")
    
    # 3. Test QuestDB
    print("\n3. Testing QuestDB...")
    try:
        qdb = QuestDBClient()
        qdb.create_tables()
        logger.info("QuestDB tables created successfully")
    except Exception as e:
        logger.error(f"QuestDB test failed: {e}")
    
    # 4. Test Kafka Producer
    print("\n4. Testing Kafka Producer...")
    try:
        producer = KafkaProducerClient()
        test_message = {
            'symbol': 'EURUSD',
            'value': 1.0880,
            'timestamp': 1699712400
        }
        topic = KafkaTopics.get_market_ticks_topic('EURUSD')
        producer.send(topic, test_message)
        logger.info(f"Kafka message sent to {topic}")
        producer.close()
    except Exception as e:
        logger.error(f"Kafka test failed: {e}")
    
    print("\n" + "=" * 50)
    print("✅ All utilities tested!")
    print("=" * 50)

if __name__ == "__main__":
    test_all()
