import os
import redis
from kafka import KafkaProducer
import requests
from dotenv import load_dotenv

load_dotenv()

def check_redis():
    host = os.getenv('REDIS_HOST', 'localhost')
    port = int(os.getenv('REDIS_PORT', '6379'))
    try:
        r = redis.Redis(host=host, port=port, socket_connect_timeout=2)
        r.ping()
        print(f"✅ Redis connected at {host}:{port}")
        return True
    except Exception as e:
        print(f"❌ Redis connection failed: {e}")
        return False

def check_kafka():
    bootstrap_servers = os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'localhost:9092')
    try:
        producer = KafkaProducer(bootstrap_servers=bootstrap_servers, request_timeout_ms=2000)
        producer.close()
        print(f"✅ Kafka connected at {bootstrap_servers}")
        return True
    except Exception as e:
        print(f"❌ Kafka connection failed: {e}")
        return False

def check_questdb():
    host = os.getenv('QUESTDB_HOST', 'localhost')
    port = os.getenv('QUESTDB_PORT', '8812') # PG wire port
    # QuestDB also has a REST API on 9000 by default
    rest_url = f"http://{host}:9000/exec?query=select 1"
    try:
        resp = requests.get(rest_url, timeout=2)
        if resp.status_code == 200:
            print(f"✅ QuestDB REST API connected at {host}:9000")
            return True
        else:
            print(f"❌ QuestDB REST API returned status {resp.status_code}")
            return False
    except Exception as e:
        print(f"❌ QuestDB connection failed: {e}")
        return False

if __name__ == "__main__":
    print("🔍 Checking Odyssey Infrastructure...")
    r = check_redis()
    k = check_kafka()
    q = check_questdb()
    
    if r and k and q:
        print("\n🚀 INFRASTRUCTURE IS READY!")
    else:
        print("\n⚠️ SOME SERVICES ARE DOWN. PLEASE CHECK DOCKER.")
