FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/apps/bot/src

WORKDIR /app

COPY pyproject.toml README.md ./
COPY apps/bot ./apps/bot
COPY src ./src

RUN pip install --upgrade pip \
    && pip install --no-cache-dir -e .

CMD ["python", "-m", "bot.polling"]
