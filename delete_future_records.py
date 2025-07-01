"""
Скрипт для удаления записей с будущими датами
Запуск: docker-compose exec web python manage.py shell < delete_future_records.py
"""

from datetime import date, datetime
from worktime.models import WorkLog
import json

print("🗑️ УДАЛЕНИЕ ЗАПИСЕЙ С БУДУЩИМИ ДАТАМИ")
print("=" * 50)

today = date.today()
print(f"🗓️ Сегодняшняя дата: {today.strftime('%d/%m/%Y')}")

# Найти записи для удаления
future_worklogs = WorkLog.objects.filter(check_in__date__gt=today)
count = future_worklogs.count()

print(f"📊 Найдено {count} записей для удаления")

if count > 0:
    # Создать бэкап
    print("💾 Создаю резервную копию...")
    backup_data = []
    
    for log in future_worklogs:
        backup_record = {
            'id': log.id,
            'employee_id': log.employee_id if hasattr(log, 'employee_id') else None,
            'employee_name': f"{log.employee.first_name} {log.employee.last_name}" if log.employee else "Unknown",
            'check_in': log.check_in.isoformat() if log.check_in else None,
            'check_out': log.check_out.isoformat() if log.check_out else None,
            'hours_worked': float(log.hours_worked) if hasattr(log, 'hours_worked') and log.hours_worked else 0,
            'location_check_in': log.location_check_in if hasattr(log, 'location_check_in') else None,
            'location_check_out': log.location_check_out if hasattr(log, 'location_check_out') else None,
            'notes': log.notes if hasattr(log, 'notes') else None,
        }
        backup_data.append(backup_record)
    
    # Сохранить бэкап в файл
    backup_filename = f"backup_future_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    
    try:
        with open(backup_filename, 'w', encoding='utf-8') as f:
            json.dump({
                'backup_date': datetime.now().isoformat(),
                'total_records': len(backup_data),
                'description': 'Резервная копия записей WorkLog с будущими датами перед удалением',
                'today_date': today.isoformat(),
                'records': backup_data
            }, f, ensure_ascii=False, indent=2)
        
        print(f"✅ Бэкап сохранен в файл: {backup_filename}")
        
        # Показать сводку
        employees = set()
        total_hours = 0
        for record in backup_data:
            employees.add(record['employee_name'])
            total_hours += record['hours_worked']
        
        print(f"📋 Бэкап содержит:")
        print(f"   • {len(backup_data)} записей")
        print(f"   • Затронуто сотрудников: {len(employees)}")
        print(f"   • Всего записей обработано")
        
        # УДАЛИТЬ ЗАПИСИ
        print("\n🗑️ Удаляю записи с будущими датами...")
        deleted_count, deleted_details = future_worklogs.delete()
        
        print(f"✅ Успешно удалено {deleted_count} записей!")
        print(f"Детали удаления: {deleted_details}")
        
        # Проверить результат
        remaining = WorkLog.objects.filter(check_in__date__gt=today).count()
        
        if remaining == 0:
            print("🎉 ВСЕ ЗАПИСИ С БУДУЩИМИ ДАТАМИ УСПЕШНО УДАЛЕНЫ!")
            print("✅ База данных очищена от проблемных записей")
        else:
            print(f"⚠️ Внимание: осталось еще {remaining} записей с будущими датами")
        
        print(f"\n📁 Резервная копия сохранена: {backup_filename}")
        print("💡 В случае необходимости данные можно восстановить из этого файла")
        
    except Exception as e:
        print(f"❌ Ошибка при создании бэкапа: {e}")
        print("⚠️ Удаление отменено для безопасности")
        
else:
    print("✅ Записей с будущими датами не найдено!")
    print("🎉 База данных уже чистая!")

print("\n" + "=" * 50)
print("✅ ОПЕРАЦИЯ ЗАВЕРШЕНА")