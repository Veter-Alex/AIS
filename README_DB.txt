# Использование:
# docker exec -i <container_id> psql -U user -d vessels_db < /docker-entrypoint-initdb.d/init.sql

# Для автоматической инициализации при старте контейнера, можно добавить volume:
#    - ./init.sql:/docker-entrypoint-initdb.d/init.sql
