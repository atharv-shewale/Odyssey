# Odyssey v2 Event-Driven Architecture

## Core Philosophy
Odyssey v2 transitioned from a Redis-polled microservices architecture into an Event-Driven Kafka-backed framework. It relies on standard structured JSON payloads enabling horizontal scaling.

## Microservices
### 1. Data Service (`data-service/`)
- Gathers data either from local CSV chunks, dummy randomized sets, or dynamically via MT5 terminal.
- Computes standard technical indicators via `pandas_ta` / `talib`.
- **Outputs**: `market.data.raw` Kafka topic.

### 2. ML Engine (`ml-engine/`)
- Consumes `market.data.raw` payloads automatically.
- Processes vectors against a pre-trained `scikit-learn` RandomForest model.
- Includes fallback synthetic modeling for robust continued execution.
- **Outputs**: `ml.signals` Kafka topic.

### 3. Strategy Engine (`strategy-engine/`)
- Consumes `ml.signals` payloads.
- Validates trades against strict risk parameters (Daily PnL drawdowns, Max Open positions).
- Generates precise Stop Loss and Take Profit levels leveraging ATR inputs.
- **Outputs**: `trading.orders` Kafka topic.

### 4. Trading Executor (`trading-executor/`)
- Connects natively to Windows MetaTrader 5 terminal (`mt5_async.py`).
- Consumes `trading.orders` and interfaces with the live broker.
- Utilizes Trailing Stops to lock profits and Partial Closes to limit risk.
- **Outputs**: `trading.executions` Kafka topic.

## System Infrastructure (`docker-compose.yml`)
1. **Kafka / Zookeeper:** Brokers JSON event messages across the platform.
2. **Redis:** Maintains high-speed caching for immediate Gateway visibility (e.g., latest MT5 Account Balance, current order status).
3. **QuestDB:** High-performance Time-series database for persisting historical tick data and permanent audit trails of Executions.
4. **Prometheus / Grafana:** Ingests metric data from the Python core services on `http://localhost:8001 -> 8004` and dynamically visuals latency, throughput, and financial performance.

## Fast API Gateway (`gateway/`)
- Provides REST (`/api/health`, `/api/account`, `/api/risk`) and WebSocket (`/ws/live`) endpoints.
- Proxies historical data, current ML confidence factors, and connected Redis state logic automatically into a React frontend client.
