# Odyssey v2 🌌

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/Frontend-React-61dafb)](https://reactjs.org/)
[![QuestDB](https://img.shields.io/badge/Database-QuestDB-blueviolet)](https://questdb.io/)

**Odyssey v2** is a professional-grade algorithmic trading platform featuring a microservices architecture, real-time ML-powered signal generation, and multi-broker execution capabilities. Designed for institutional-level reliability, it integrates adaptive strategy weighting, advanced risk management, and high-performance time-series processing.

---

## 🚀 Core Features

### 🧠 Adaptive Strategy Engine
The system employs a **Multi-Strategy Manager** that orchestrates an ensemble of trading logics:
*   **ML-Driven Signals**: Price trend predictions via LSTM/ONNX models.
*   **Dynamic Trend Following**: Moving average and MACD-based trend identification.
*   **Statistical Mean Reversion**: Mean reversion logic using Bollinger Bands and RSI.
*   **Volatility Breakout**: ATR-based breakout detection.
*   **Momentum Formulation**: RSI-based momentum tracking.
*   **Adaptive Weighting**: Strategies are dynamically weighted based on their **Sharpe Ratio** and a **Correlation Penalty** to ensure portfolio diversification.

### 🛡️ Institutional Risk Management
*   **Daily Loss Circuit Breakers**: Automatic trading suspension if daily loss exceeds **6%**.
*   **Drawdown Protection**: System-wide lock if peak-to-trough drawdown hits **10%**.
*   **Exposure Limits**: Strict limits on concurrent positions (max 5) and per-symbol exposure (max 2).
*   **Sophisticated Sizing**: ATR-based position sizing with Kelly-like scaling.

### ⚡ Technical Infrastructure
*   **Data Pipeline**: Low-latency ingestion of `XAUUSD` and `EURUSD` ticks via WebSockets.
*   **QuestDB Integration**: Optimized for sub-millisecond querying of OHLCV and technical features.
*   **Event-Driven Communication**: Microservices communicate asynchronously via **Kafka** and **Redis**.
*   **Monitoring**: Real-time Prometheus metrics for system health and strategy performance.

---

## 🏗️ Architecture

| Service | Primary Responsibility |
| :--- | :--- |
| **`data-service`** | Real-time tick collection and feature engineering (QuestDB). |
| **`ml-engine`** | Runs LSTM models to generate directional confidence scores. |
| **`strategy-engine`**| Ensemble manager that resolves multiple signals into actionable trades. |
| **`risk-engine`** | Final gatekeeper for order validation and capital preservation. |
| **`trading-executor`**| Multi-broker bridge for order execution (MT5 / Fyers). |
| **`api-gateway`** | FastAPI hub for the dashboard and external integrations. |

---

## 🛠️ Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Languages** | Python 3.10+, JavaScript (Node.js), SQL |
| **Core Frameworks** | FastAPI, React, PyTorch |
| **Messaging** | Apache Kafka, Redis (Pub/Sub + Cache) |
| **Data Storage** | QuestDB (Time-series), Redis (Real-time state) |
| **Visualization** | TradingView Lightweight Charts, Prometheus/Grafana |
| **Deployment** | Docker, Docker Compose |

---

## ⚙️ Setup & Installation

### Prerequisites
*   Docker & Docker Compose
*   Python 3.10+
*   Broker API credentials (Fyers / MT5)

### Execution
1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/atharv-shewale/Odyssey.git
    cd Odyssey
    ```
2.  **Environment Setup**:
    Configure your `.env` file with broker keys and database settings.
3.  **Launch System**:
    ```bash
    docker-compose up --build
    ```
4.  **Access**:
    *   **Frontend**: `http://localhost:3000`
    *   **API Gateway**: `http://localhost:8000`
    *   **Prometheus Metrics**: `http://localhost:8003`

---

## 🛡️ Risk Disclaimer
Trading financial markets involves significant risk. This software is for educational and development purposes. Performance in paper trading or backtesting does not guarantee future results. Always use a dedicated risk-controlled environment.

---

## 📄 License
This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
