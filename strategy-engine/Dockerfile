FROM python:3.10-slim

WORKDIR /app
COPY requirements.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements.txt && pip install -e .

COPY . .

# Environment variables should be injected by docker-compose
CMD ["python", "strategy-engine/core/multi_strategy_manager.py"]
