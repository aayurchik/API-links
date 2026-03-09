FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app

# Миграции и запуск приложения с портом из переменной окружения Render
CMD alembic upgrade head && uvicorn src.main:app --host 0.0.0.0 --port $PORT
