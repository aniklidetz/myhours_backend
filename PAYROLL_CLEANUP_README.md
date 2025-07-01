# Payroll Data Cleanup

## Проблема
В системе присутствуют тестовые данные зарплат, которые искажают расчеты и отображение в UI.

## Решение

### 1. Автоматическая очистка (рекомендуется)
```bash
cd /path/to/backend/myhours-backend
python manage.py cleanup_test_payroll --test-only --dry-run
```

Проверить что будет удалено, затем:
```bash
python manage.py cleanup_test_payroll --test-only
```

### 2. Ручная очистка через SQL
```bash
cd /path/to/backend/myhours-backend
# Запустить SQL скрипт
python manage.py dbshell < cleanup_test_payroll.sql
```

### 3. Очистка конкретных записей
Удалить зарплаты с нереалистичными значениями:
- base_salary > 40,000 ILS
- hourly_rate > 200 ILS  
- exact values like 50,000 (hardcoded test data)

### 4. Проверка результата
После очистки проверить в Django admin:
- Payroll > Salaries должны содержать только реалистичные данные
- Диапазон base_salary: 9,300 - 25,000 ILS
- Диапазон hourly_rate: 45 - 80 ILS

## Результат
- Current Month Progress виджет будет показывать корректные суммы
- Карточки периодов будут отображать реальные часы и зарплаты
- Исчезнут фиктивные значения типа ₪48,333