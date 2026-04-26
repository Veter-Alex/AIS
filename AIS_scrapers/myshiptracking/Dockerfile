FROM python:3.11-slim

WORKDIR /app

COPY myshiptracking/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY myshiptracking/scraper.py myshiptracking/config.py ./
COPY common ./common

ENV PYTHONPATH=/app

RUN mkdir -p /app/images

CMD ["python", "scraper.py"]
