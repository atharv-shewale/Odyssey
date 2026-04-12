# Odyssey v2 🌌

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue)](https://www.python.org/)
[![React](https://img.shields.io/badge/Frontend-React-61dafb)](https://reactjs.org/)
[![QuestDB](https://img.shields.io/badge/Database-QuestDB-blueviolet)](https://questdb.io/)

**Odyssey v2** is a professional-grade algorithmic trading platform featuring a microservices architecture, real-time ML-powered signal generation, and multi-broker execution capabilities. Designed for low latency and high reliability, it integrates sentiment analysis, advanced risk management, and a high-performance time-series database.

---

## 🚀 Key Features

*   **Machine Learning Engine**: High-performance LSTM and ONNX models for real-time price trend prediction.
*   **Multi-Broker Execution**: Seamlessly execute trades across **MetaTrader 5 (MT5)** and **Fyers API**.
*   **Time-Series Optimization**: Leverages **QuestDB** for ultra-fast ingestion and querying of tick-level market data.
*   **Intelligent Risk Management**: Built-in circuit breakers, drawdown monitoring, and exposure limits to protect capital.
*   **Sentiment Service**: Real-time news and social media sentiment aggregation to enhance trading signals.
*   **Real-time Dashboard**: Interactive React frontend with **TradingView Lightweight Charts** for market visualization and system monitoring.
*   **Event-Driven Architecture**: Powered by **Kafka** and **Redis** for efficient asynchronous communication between microservices.

---

## 🏗️ Architecture

The system is composed of several specialized microservices:

*   **`data-service`**: Handles real-time tick data collection (WebSockets) and ingestion into QuestDB.
*   **`ml-engine`**: Runs predictive models on incoming data streams.
*   **`strategy-engine`**: Orchestrates trading logic based on technical indicators and ML signals.
*   **`risk-engine`**: Validates every signal against risk parameters before execution.
*   **`trading-executor`**: Manages order placement, tracking, and broker communication.
*   **`gateway`**: Provides a FastAPI-based REST and WebSocket endpoint for the frontend.
*   **`sentiment-service`**: Scrapes and analyzes external news sources for market sentiment.

---

## 🛠️ Tech Stack

| Layer | Technologies |
| :--- | :--- |
| **Backend** | Python 3.10+, FastAPI, Redis, Kafka |
| **Machine Learning** | PyTorch, Scikit-Learn, ONNX |
| **Database** | QuestDB (Time-series), Redis (Cache) |
| **Frontend** | React, Lightweight Charts, Lucide Icons |
| **Infrastructure** | Docker, Docker Compose |
| **Brokers** | MT5, Fyers |

---

## ⚙️ Setup & Installation

### Prerequisites

*   Docker & Docker Compose
*   Python 3.10+ (for local development)
*   Broker API credentials (Fyers / MT5 setup)

### Execution

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/atharv-shewale/Odyssey.git
    cd Odyssey
    ```

2.  **Configure Environment**:
    Create a `.env` file in the root directory and populate it with your credentials (see `.env.example` if available or consult `infrastructure/config`).

3.  **Launch via Docker**:
    ```bash
    docker-compose up --build
    ```

4.  **Access the Dashboard**:
    Open your browser and navigate to `http://localhost:3000` (Frontend) or `http://localhost:8000/docs` (API Swagger).

---

## 🛡️ Risk Disclaimer

Trading financial markets involves significant risk. This software is for educational and development purposes. Performance in paper trading or backtesting does not guarantee future results. Always use a dedicated risk-controlled environment.

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
