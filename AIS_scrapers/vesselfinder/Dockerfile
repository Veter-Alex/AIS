FROM python:3.11-slim

WORKDIR /app

COPY vesselfinder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY vesselfinder/scraper.py vesselfinder/config.py ./
COPY vesselfinder/debug_vessel_html.py ./
COPY common ./common

ENV PYTHONPATH=/app

RUN mkdir -p /app/images

CMD ["python", "scraper.py"]
