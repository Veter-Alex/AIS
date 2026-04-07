FROM python:3.11-slim

WORKDIR /app

# Установить зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать код скрапера
COPY scraper.py config.py ./

# Создать директорию для изображений
RUN mkdir -p /app/images

# Запустить скрапер
CMD ["python", "-u", "scraper.py"]
