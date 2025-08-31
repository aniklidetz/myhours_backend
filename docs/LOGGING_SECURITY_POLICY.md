# Политика безопасного логирования

## Основные принципы

### ❌ НИКОГДА не логировать:
- Employee ID в открытом виде 
- User ID в открытом виде
- Точные зарплаты/ставки
- Биометрические данные (face_encoding, similarity scores)
- Токены авторизации
- Пароли, секретные ключи  
- Email адреса полностью
- Номера телефонов полностью
- Точные GPS координаты
- Содержимое HTTP заголовков (Authorization, Cookie)
- Полное содержимое dict с request данными

### ✅ БЕЗОПАСНО логировать:
- Булевы флаги (`has_employee_id`, `is_authenticated`)
- Счетчики (`embeddings_count`, `query_params_count`)
- Категориальные уровни (`confidence_level: "high/medium/low"`)
- Псевдо-идентификаторы (`public_emp_id()`, hashed IDs)
- Типы событий (`salary_changed: true`)
- Диапазоны/бакеты (`salary_range: "5k-10k"`)
- Статусы операций (`result: "success"`)

## Универсальные функции

### public_emp_id()
```python
from core.logging_utils import public_emp_id

# ❌ НЕ ДЕЛАТЬ:
logger.info(f"Employee {employee_id} updated")

# ✅ ПРАВИЛЬНО:
logger.info("Employee updated", extra={"employee": public_emp_id(employee_id)})
```

### safe_extra() и safe_biometric_subject()
```python
from core.logging_utils import safe_extra, safe_biometric_subject

# ✅ ПРАВИЛЬНО:
logger.info(
    "Biometric verification", 
    extra=safe_extra({
        "subject": safe_biometric_subject(employee, "employee"),
        "has_match": similarity >= threshold
    }, allow={"has_match"})
)
```

### err_tag() для исключений
```python
from core.logging_utils import err_tag

# ✅ ПРАВИЛЬНО:
logger.error("Operation failed", extra={"err": err_tag(e)})
```

## Правила по модулям

### Зарплатные данные (users/views.py, payroll/)
```python
# ❌ НЕ ДЕЛАТЬ:
logger.info("Updated salary", extra={"new_salary": salary.base_salary})

# ✅ ПРАВИЛЬНО:
logger.info("Updated salary", extra={
    **safe_log_employee(employee, "salary_update"),
    "salary_changed": True
})
```

### Биометрические данные (biometrics/)
```python  
# ❌ НЕ ДЕЛАТЬ:
logger.info(f"Face match: employee {employee_id}, confidence {confidence}")

# ✅ ПРАВИЛЬНО:
logger.info("Face match found", extra=safe_extra({
    "subject": safe_biometric_subject({"id": employee_id}, "employee"),
    "confidence_level": "high" if confidence >= 0.8 else "medium" if confidence >= 0.6 else "low"
}, allow={"confidence_level"}))
```

### Debug информация (debug_views.py)
```python
# ❌ НЕ ДЕЛАТЬ:  
logger.info(f"Debug: {request.META}")

# ✅ ПРАВИЛЬНО:
if settings.DEBUG:
    safe_debug = {
        "has_auth_header": "HTTP_AUTHORIZATION" in request.META,
        "is_authenticated": request.user.is_authenticated,
        "query_params_count": len(request.GET or {})
    }
    logger.info("Debug info (safe)", extra=safe_debug)
```

## Подавление алертов

Используйте `# lgtm[py/clear-text-logging-sensitive-data]` только после:
1. Применения безопасных методов логирования
2. Проверки отсутствия чувствительных данных
3. Добавления `settings.DEBUG` гейтов где необходимо

```python
# ✅ ПРАВИЛЬНО - после санитизации:
logger.info("Safe operation", extra=safe_extra(data))  # lgtm[py/clear-text-logging-sensitive-data]
```

## Тестирование безопасности

Перед коммитом проверить:
```bash
# Поиск потенциально опасных логов
grep -r "employee_id.*logger" --include="*.py"
grep -r "confidence.*logger" --include="*.py"  
grep -r "salary.*logger" --include="*.py"
```

## При ошибках тестов

Если тесты требуют определенный формат сообщений:
1. Сначала исправить логирование на безопасное
2. Обновить тесты под новый формат  
3. Только в крайнем случае использовать подавление с пояснением

```python
# Если тест требует конкретный текст:
logger.error(f"Failed for employee {employee_id}: {err_tag(e)}")  # lgtm[py/clear-text-logging-sensitive-data] - Required by test_employee_error_format
```

## Мониторинг

Настроить алерты на:
- Логи содержащие email паттерны
- Логи с числами похожими на ID (> 6 цифр)
- Логи с токенами (Bearer, длинные base64 строки)
- Логи с координатами (float с 4+ знаками после запятой)