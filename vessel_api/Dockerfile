FROM python:3.11-slim
WORKDIR /app

COPY vessel_api/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY ais_shared ./ais_shared
COPY vessel_api/app.py .

ENV PYTHONPATH=/app

CMD ["sh", "-c", "alembic upgrade head && uvicorn app:app --host 0.0.0.0 --port 8000"]
