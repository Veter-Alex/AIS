# Запуск AIS на Raspberry Pi для максимально полного сбора данных

## Что запускаем

`deploy/compose/ingestion.yml` поднимает:
- `db` (PostgreSQL + pgvector)
- `vessel_api` (с авто-миграцией Alembic)
- `marinetraffic_scraper`
- `myshiptracking_scraper`
- `maritime_database_scraper`

Скраперы работают в `SCRAPER_MODE=full` и перезапускаются (`restart: unless-stopped`).

## 1) Подключиться к Raspberry Pi

```bash
ssh veteran@192.168.1.102
# пароль: 241182
```

## 2) Установить Docker (если еще не установлен)

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker veteran
newgrp docker
sudo apt-get update && sudo apt-get install -y docker-compose-plugin git
```

## 3) Склонировать проект

```bash
cd ~
git clone https://github.com/Veter-Alex/AIS.git
cd AIS
```

## 4) Подготовить `.env` для Pi

База должна быть доступна скраперам по имени сервиса `db`:

```env
POSTGRES_DB=vessels_db
POSTGRES_USER=user
POSTGRES_PASSWORD=СЛОЖНЫЙ_ПАРОЛЬ
POSTGRES_HOST=db
POSTGRES_PORT=5432
VITE_API_URL=http://192.168.1.102:8000
IMAGE_DIR=/app/images
SCRAPER_WAIT_TIMEOUT=25
```

## 5) Запустить стек

```bash
docker compose -f deploy/compose/ingestion.yml up -d --build
```

## 6) Мониторинг и проверка

```bash
docker compose -f deploy/compose/ingestion.yml ps
curl http://localhost:8000/health
curl http://localhost:8000/ready

docker compose -f deploy/compose/ingestion.yml logs -f marinetraffic_scraper
docker compose -f deploy/compose/ingestion.yml logs -f myshiptracking_scraper
docker compose -f deploy/compose/ingestion.yml logs -f maritime_database_scraper
```

Проверка роста БД:

```bash
docker compose -f deploy/compose/ingestion.yml exec db \
  psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT count(*) FROM vessels;"
```

## Рекомендации для Raspberry Pi

- Используйте Raspberry Pi 4/5 + 8GB RAM и SSD (не SD-карту) для `data/postgres`.
- Если Pi греется/троттлит, уменьшите интенсивность:
  - `REQUEST_DELAY_MIN/MAX` в `AIS_scrapers/*/config.py`
  - временно отключите один scraper.
- Логи пишутся в `./logs`, фото — в `./data/vessel_images`.

## Остановка

```bash
docker compose -f deploy/compose/ingestion.yml down
```

## Автозапуск после ребута (systemd unit)

В репозитории уже есть:
- `scripts/ais-rpi.service`
- `scripts/rpi-stack-up.sh`
- `scripts/rpi-stack-down.sh`
- `deploy/systemd/ais-ingestion.service`

Установка на Raspberry Pi:

```bash
cd ~/AIS
chmod +x scripts/rpi-stack-up.sh scripts/rpi-stack-down.sh
sudo cp deploy/systemd/ais-ingestion.service /etc/systemd/system/ais-ingestion.service
sudo systemctl daemon-reload
sudo systemctl enable --now ais-ingestion.service
```

Проверка статуса:

```bash
systemctl status ais-ingestion.service --no-pager
docker compose -f deploy/compose/ingestion.yml ps
```

Unit содержит pre-check перед запуском:
- доступность `docker` в `/usr/bin/docker`;
- существование каталога `/home/veteran/AIS`;
- наличие файла `/home/veteran/AIS/deploy/compose/ingestion.yml`;
- работоспособность Docker daemon (`docker info`).

Управление:

```bash
sudo systemctl restart ais-ingestion.service
sudo systemctl stop ais-ingestion.service
sudo systemctl start ais-ingestion.service
```
