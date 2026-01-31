FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc g++ && rm -rf /var/lib/apt/lists/*

RUN pip install uv
COPY pyproject.toml uv.lock ./
RUN uv pip install --system .

COPY core/ ./core/
COPY telegram_bot/ ./telegram_bot/
COPY bot.py ./

CMD ["python", "bot.py"]
