FROM python:3.11-slim

WORKDIR /app

COPY maritime_database/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY maritime_database/scraper.py maritime_database/config.py ./
COPY common ./common

ENV PYTHONPATH=/app

RUN mkdir -p /app/images

CMD ["python", "scraper.py"]
