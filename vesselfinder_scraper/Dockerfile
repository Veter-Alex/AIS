FROM python:3.11-slim
WORKDIR /app

# Установка зависимостей для headless Chrome
RUN apt-get update && \
	apt-get install -y --no-install-recommends \
	chromium-driver \
	chromium \
	fonts-liberation \
	libasound2 \
	libatk-bridge2.0-0 \
	libatk1.0-0 \
	libc6 \
	libcairo2 \
	libcups2 \
	libdbus-1-3 \
	libdrm2 \
	libgbm1 \
	libgtk-3-0 \
	libnspr4 \
	libnss3 \
	libx11-xcb1 \
	libxcomposite1 \
	libxdamage1 \
	libxrandr2 \
	xdg-utils \
	wget \
	ca-certificates \
	&& rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium
ENV CHROMEDRIVER_BIN=/usr/bin/chromedriver

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY scraper.py .
COPY debug_vessel_html.py .
RUN mkdir -p /app/images
CMD ["python", "scraper.py"]
