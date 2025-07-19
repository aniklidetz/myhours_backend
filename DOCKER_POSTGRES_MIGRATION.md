# Docker PostgreSQL Migration Guide

## 🔍 Текущая ситуация
- Docker контейнеры запущены
- PostgreSQL контейнер работает (myhours_postgres)
- Но Django использует SQLite вместо PostgreSQL
- Изменения в .env уже сделаны

## 📋 Шаги миграции

### 1. Сделайте бэкап (опционально, но рекомендуется)
```bash
cd /Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend
./backup_before_postgres.sh
```

### 2. Примените изменения БЕЗ остановки контейнеров
```bash
# Скопируйте обновленный .env в контейнер
docker cp .env myhours_web:/app/.env

# Перезапустите только web контейнер
docker restart myhours_web

# Подождите 10-15 секунд для инициализации
sleep 15
```

### 3. Проверьте, что Django теперь использует PostgreSQL
```bash
docker exec myhours_web python -c "
import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
import django
django.setup()
from django.conf import settings
print('Database:', settings.DATABASES['default']['ENGINE'])
"
```

Должно показать: `django.db.backends.postgresql`

### 4. Запустите миграции
```bash
# Создайте все таблицы включая biometric_profiles
docker exec myhours_web python manage.py migrate

# Если есть проблемы с миграциями, используйте:
docker exec myhours_web python manage.py migrate --run-syncdb
```

### 5. Проверьте, что таблица создана
```bash
docker exec myhours_postgres psql -U myhours_user -d myhours_db -c "\dt biometric*"
```

### 6. Перезапустите все сервисы для надёжности
```bash
docker-compose restart
```

## ✅ После миграции
1. MongoDB очищена - данные удалены
2. PostgreSQL активен с таблицей biometric_profiles
3. Можно регистрировать биометрию заново

## ⚠️ Если что-то пошло не так
```bash
# Откатиться на SQLite (временно)
docker exec myhours_web bash -c "unset DATABASE_URL && python manage.py runserver"

# Или полный перезапуск
docker-compose down
docker-compose up -d
```