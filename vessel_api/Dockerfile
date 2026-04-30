FROM python:3.11-slim
WORKDIR /app

COPY vessel_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY ais_shared ./ais_shared
COPY vessel_api/app.py .

ENV PYTHONPATH=/app

# Повтор миграций до успеха: при первом старте Postgres иногда healthy раньше, чем принимает TCP.
CMD ["sh", "-c", "until alembic upgrade head; do echo 'alembic: DB not ready, retry in 2s'; sleep 2; done && exec uvicorn app:app --host 0.0.0.0 --port 8000"]
