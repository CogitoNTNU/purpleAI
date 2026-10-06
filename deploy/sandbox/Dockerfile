FROM python:3.12-slim AS base
WORKDIR /app
RUN pip install --no-cache-dir flask==3.1.0 requests==2.34.2 gunicorn==23.0.0
ENV PYTHONDONTWRITEBYTECODE=1 HOME=/workspace LANGCHAIN_TRACING_V2=false LANGSMITH_TRACING=false
COPY deploy/sandbox/check_network.py ./check_network.py

# Each Compose service selects its stage below.
FROM base AS gateway
COPY deploy/sandbox/gateway.py .
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:9000", "--workers", "1", "--threads", "4", "--timeout", "150", "gateway:create_app()"]

FROM base AS attacker
RUN apt-get update && apt-get install -y --no-install-recommends nmap curl && rm -rf /var/lib/apt/lists/*
COPY src/nmap-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/nmap-agent/*.py ./
COPY src/nmap-agent/tools ./tools
USER 10001:10001
CMD ["python", "main.py"]

FROM base AS defender
RUN pip install --no-cache-dir 'langchain-openai>=1.0,<2'
COPY src/defender/defender-agent/defender.py .
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "1", "--threads", "4", "--timeout", "180", "defender:app"]

FROM base AS target
COPY src/defender/vulnerable-app/ ./
ENV VULNSHOP_DB_PATH=/data/vulnshop.db
USER 10001:10001
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "4", "app:app"]
