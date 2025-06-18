# 🔍 API & Database Diagnostic Instructions

## Проблемы которые мы исправляем:

1. **Logout Error** - ошибка 401 при logout (исправлено в коде)
2. **Роль пользователя не видна** - не отображается в UI (исправлено в коде)  
3. **API авторизация** - токены могут истекать
4. **Пустые данные** - нет тестовых данных в БД
5. **Dev элементы** - скрыты за __DEV__ флагом

## Шаги для диагностики:

### 1. Убедитесь что Docker запущен
```bash
# Проверьте запущенные контейнеры
docker ps

# Если нет - запустите
cd /Users/aniklidetz/Documents/MyPythonProject/MyHours/backend/myhours-backend
docker-compose up -d
```

### 2. Запустите диагностический скрипт
```bash
# Войдите в контейнер Django
docker-compose exec web python debug_api.py

# Или если Docker не запущен:
python debug_api.py
```

### 3. Исправьте проблемы с авторизацией
```bash
# Исправить проблемы с токенами и создать тестовых пользователей
docker-compose exec web python fix_auth_issues.py

# Выберите опцию 3 (Both) для полного исправления
```

### 4. Проверьте API endpoints вручную

#### Тест health check:
```bash
curl http://127.0.0.1:8000/api/health/
```

#### Тест login:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/users/auth/enhanced-login/ \
  -H "Content-Type: application/json" \
  -d '{
    "email": "admin@example.com",
    "password": "admin123",
    "device_id": "test_device_123",
    "device_info": {
      "platform": "test",
      "os_version": "1.0",
      "app_version": "1.0.0",
      "device_model": "Test Device",
      "device_id": "test_device_123"
    }
  }'
```

#### Тест с токеном (замените YOUR_TOKEN):
```bash
# Employees
curl -H "Authorization: DeviceToken YOUR_TOKEN" \
  http://127.0.0.1:8000/api/v1/users/employees/

# Work Time
curl -H "Authorization: DeviceToken YOUR_TOKEN" \
  http://127.0.0.1:8000/api/v1/worktime/worklogs/

# Payroll
curl -H "Authorization: DeviceToken YOUR_TOKEN" \
  http://127.0.0.1:8000/api/v1/payroll/salaries/
```

## Исправления в коде:

### ✅ Уже исправлено:
1. **Logout error handling** - теперь игнорирует 401 ошибки при logout
2. **Role display** - добавлен fallback для undefined роли  
3. **Cancel button navigation** - использует прямую навигацию вместо router.back()
4. **Dev elements** - скрыты за __DEV__ флагом
5. **Empty states** - добавлены для Work Time
6. **NaN calculations** - исправлены в Payroll
7. **Date parsing** - безопасная обработка в Work Time

### 🔧 Что проверить после диагностики:

1. **Данные в БД**: должны появиться тестовые пользователи и записи
2. **API ответы**: должны возвращать 200 с данными
3. **Роли пользователей**: должны отображаться в Dashboard
4. **Logout**: не должен вызывать ошибки

## Тестовые пользователи после исправления:

- **admin@example.com** / admin123 (Admin)
- **mikhail.plotnik@gmail.com** / admin123 (Accountant)  
- **employee1@example.com** / employee123 (Employee)

## Если проблемы остаются:

1. Проверьте логи Django: `docker-compose logs web`
2. Проверьте подключение к MongoDB: `docker-compose logs mongodb`
3. Очистите кэш фронтенда и перезапустите Expo
4. Убедитесь что IP адрес в config.js правильный

## Результат:

После выполнения всех шагов:
- ✅ Logout работает без ошибок
- ✅ Роли отображаются корректно
- ✅ API возвращает реальные данные
- ✅ Dev элементы скрыты в продакшене
- ✅ Пустые состояния показывают понятные сообщения