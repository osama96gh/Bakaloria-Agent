FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
COPY bulbul_agent/ ./bulbul_agent/
COPY telegram_service/ ./telegram_service/

RUN uv pip install --system .

CMD ["python", "-m", "telegram_service.main"]
