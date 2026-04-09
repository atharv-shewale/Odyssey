FROM python:3.10-slim

WORKDIR /app

# The gateway has its own requirements.txt + the global one
COPY requirements.txt pyproject.toml gateway/requirements.txt* ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ -f gateway/requirements.txt ]; then pip install --no-cache-dir -r gateway/requirements.txt; fi && \
    pip install -e .

COPY . .

EXPOSE 8000

ENV HOST=0.0.0.0
ENV PORT=8000

CMD ["python", "gateway/main.py"]
