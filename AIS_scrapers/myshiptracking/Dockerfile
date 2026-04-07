FROM python:3.11-slim

WORKDIR /app

# Установить зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Скопировать код скрапера
COPY config.py .
COPY scraper.py .

# Создать каталог для изображений (если понадобится в будущем)
RUN mkdir -p /app/images

# Запустить скрапер
CMD ["python", "scraper.py"]
