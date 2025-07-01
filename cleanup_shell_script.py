"""
Скрипт для запуска через Django shell:
python manage.py shell < cleanup_shell_script.py

Либо интерактивно:
python manage.py shell
exec(open('cleanup_shell_script.py').read())
"""

from datetime import date, datetime
from worktime.models import WorkLog
from users.models import Employee

def cleanup_future_dates():
    today = date.today()
    print(f"🗓️ Сегодняшняя дата: {today.strftime('%d/%m/%Y')}")
    print("=" * 50)
    
    # Найти записи WorkLog с будущими датами
    try:
        future_worklogs = WorkLog.objects.filter(
            check_in__date__gt=today
        ).order_by('check_in')
        
        count = future_worklogs.count()
        print(f"📊 Найдено {count} записей WorkLog с будущими датами:")
        print()
        
        if count > 0:
            print("ID | Сотрудник | Дата входа | Дата выхода | Часы")
            print("-" * 60)
            
            total_hours = 0
            employees_affected = set()
            
            for log in future_worklogs:
                employee_name = "Неизвестно"
                try:
                    if log.employee:
                        employee_name = f"{log.employee.first_name} {log.employee.last_name}"
                        employees_affected.add(employee_name)
                    elif hasattr(log, 'employee_id') and log.employee_id:
                        try:
                            emp = Employee.objects.get(id=log.employee_id)
                            employee_name = f"{emp.first_name} {emp.last_name}"
                            employees_affected.add(employee_name)
                        except Employee.DoesNotExist:
                            employee_name = f"ID:{log.employee_id}"
                except Exception as e:
                    employee_name = f"Ошибка: {str(e)}"
                
                check_in_date = log.check_in.strftime('%d/%m/%Y %H:%M') if log.check_in else "Нет"
                check_out_date = log.check_out.strftime('%d/%m/%Y %H:%M') if log.check_out else "Нет"
                hours = 0
                if hasattr(log, 'hours_worked') and log.hours_worked:
                    hours = log.hours_worked
                    total_hours += hours
                hours_str = f"{hours:.2f}h" if hours else "0h"
                
                print(f"{log.id:3d} | {employee_name:15s} | {check_in_date:16s} | {check_out_date:16s} | {hours_str}")
            
            print("\n" + "=" * 50)
            print("📈 АНАЛИЗ ВЛИЯНИЯ:")
            print(f"👥 Затронуто сотрудников: {len(employees_affected)}")
            print(f"⏰ Общие 'будущие' часы: {total_hours:.2f}h")
            if employees_affected:
                print("Список затронутых сотрудников:")
                for emp in sorted(employees_affected):
                    print(f"  • {emp}")
            
            print("\n🚨 ПОЧЕМУ ЭТО ПРОБЛЕМА:")
            print("  • Искажает расчеты зарплат")
            print("  • Влияет на отчеты по часам")
            print("  • Может сломать логику приложения")
            print("  • Путает пользователей в админке")
            
            print(f"\n⚠️ ГОТОВ УДАЛИТЬ {count} ЗАПИСЕЙ С БУДУЩИМИ ДАТАМИ")
            print("Для удаления выполните:")
            print("=" * 50)
            print("# Создать бэкап")
            print(f"backup_data = list(WorkLog.objects.filter(check_in__date__gt=date.today()).values())")
            print(f"print(f'Создан бэкап из {{len(backup_data)}} записей')")
            print()
            print("# Удалить записи")
            print(f"deleted_count, details = WorkLog.objects.filter(check_in__date__gt=date.today()).delete()")
            print(f"print(f'Удалено {{deleted_count}} записей: {{details}}')")
            print()
            print("# Проверить результат") 
            print(f"remaining = WorkLog.objects.filter(check_in__date__gt=date.today()).count()")
            print(f"print(f'Осталось записей с будущими датами: {{remaining}}')")
            
        else:
            print("✅ Записей с будущими датами нет - всё в порядке!")
            
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

# Запустить анализ
cleanup_future_dates()

print("\n" + "=" * 50)
print("💡 ПОДСКАЗКА:")
print("Если хотите удалить записи прямо сейчас, выполните:")
print()
print("from datetime import date")
print("from worktime.models import WorkLog")
print("count = WorkLog.objects.filter(check_in__date__gt=date.today()).count()")
print("print(f'Будет удалено: {count} записей')")
print("deleted = WorkLog.objects.filter(check_in__date__gt=date.today()).delete()")
print("print(f'Удалено: {deleted}')")