FROM python:3.11-slim

WORKDIR /app

COPY marinetraffic/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY marinetraffic/scraper.py marinetraffic/config.py ./
COPY common ./common

ENV PYTHONPATH=/app

RUN mkdir -p /app/images

CMD ["python", "-u", "scraper.py"]
