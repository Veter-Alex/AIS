FROM python:3.11-slim

WORKDIR /app

COPY ai_agent/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY ais_shared ./ais_shared
COPY ai_agent/app.py .
COPY ai_agent/services ./services

ENV PYTHONPATH=/app

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8100"]
