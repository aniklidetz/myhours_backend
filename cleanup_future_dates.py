#!/usr/bin/env python
"""
Скрипт для удаления записей с будущими датами из базы данных MyHours
Сегодня: 24 июля 2025 (24/07/2025)

Этот скрипт:
1. Находит все записи WorkLog с датами больше сегодняшней
2. Показывает их для проверки
3. Предлагает безопасно удалить их
"""

import os
import sys
import django
from datetime import date, datetime

# Настройка Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from worktime.models import WorkLog
from users.models import Employee

def find_future_records():
    """Найти все записи с будущими датами"""
    today = date.today()
    print(f"🗓️ Сегодняшняя дата: {today.strftime('%d/%m/%Y')}")
    print("=" * 50)
    
    # Найти записи WorkLog с будущими датами
    future_worklogs = WorkLog.objects.filter(
        check_in__date__gt=today
    ).order_by('check_in')
    
    print(f"📊 Найдено {future_worklogs.count()} записей WorkLog с будущими датами:")
    print()
    
    if future_worklogs.exists():
        print("ID | Сотрудник | Дата входа | Дата выхода | Часы")
        print("-" * 60)
        
        for log in future_worklogs:
            employee_name = "Неизвестно"
            try:
                if log.employee:
                    employee_name = f"{log.employee.first_name} {log.employee.last_name}"
                elif hasattr(log, 'employee_id'):
                    try:
                        emp = Employee.objects.get(id=log.employee_id)
                        employee_name = f"{emp.first_name} {emp.last_name}"
                    except Employee.DoesNotExist:
                        employee_name = f"ID:{log.employee_id}"
            except Exception as e:
                employee_name = f"Ошибка: {str(e)}"
            
            check_in_date = log.check_in.strftime('%d/%m/%Y %H:%M') if log.check_in else "Нет"
            check_out_date = log.check_out.strftime('%d/%m/%Y %H:%M') if log.check_out else "Нет"
            hours = f"{log.hours_worked:.2f}h" if log.hours_worked else "0h"
            
            print(f"{log.id:3d} | {employee_name:15s} | {check_in_date:16s} | {check_out_date:16s} | {hours}")
    
    return future_worklogs

def analyze_impact(future_worklogs):
    """Анализ влияния этих записей"""
    print("\n" + "=" * 50)
    print("📈 АНАЛИЗ ВЛИЯНИЯ:")
    
    if not future_worklogs.exists():
        print("✅ Записей с будущими датами нет - всё в порядке!")
        return
    
    # Группировка по сотрудникам
    employees_affected = {}
    total_future_hours = 0
    
    for log in future_worklogs:
        employee_key = "unknown"
        try:
            if log.employee:
                employee_key = f"{log.employee.first_name} {log.employee.last_name}"
            elif hasattr(log, 'employee_id'):
                employee_key = f"Employee ID: {log.employee_id}"
        except:
            pass
        
        if employee_key not in employees_affected:
            employees_affected[employee_key] = {
                'records': 0,
                'hours': 0
            }
        
        employees_affected[employee_key]['records'] += 1
        if log.hours_worked:
            employees_affected[employee_key]['hours'] += log.hours_worked
            total_future_hours += log.hours_worked
    
    print(f"👥 Затронуто сотрудников: {len(employees_affected)}")
    print(f"⏰ Общие 'будущие' часы: {total_future_hours:.2f}h")
    print()
    
    print("Детали по сотрудникам:")
    for emp, data in employees_affected.items():
        print(f"  • {emp}: {data['records']} записей, {data['hours']:.2f}h")
    
    print("\n🚨 ПОЧЕМУ ЭТО ПРОБЛЕМА:")
    print("  • Искажает расчеты зарплат")
    print("  • Влияет на отчеты по часам")
    print("  • Может сломать логику приложения")
    print("  • Путает пользователей в админке")

def safe_delete_records(future_worklogs):
    """Безопасное удаление записей"""
    if not future_worklogs.exists():
        print("✅ Нечего удалять!")
        return
    
    print("\n" + "=" * 50)
    print("🗑️ УДАЛЕНИЕ ЗАПИСЕЙ")
    
    count = future_worklogs.count()
    
    # Подтверждение
    print(f"\n⚠️ Будет удалено {count} записей с будущими датами.")
    print("Это действие НЕОБРАТИМО!")
    
    while True:
        confirm = input("\nВы уверены? Введите 'да' для подтверждения или 'нет' для отмены: ").lower().strip()
        
        if confirm in ['да', 'yes', 'y']:
            print("\n🔄 Удаляем записи...")
            
            # Создаем резервную копию данных
            backup_data = []
            for log in future_worklogs:
                backup_data.append({
                    'id': log.id,
                    'employee_id': getattr(log, 'employee_id', None),
                    'check_in': log.check_in,
                    'check_out': log.check_out,
                    'hours_worked': log.hours_worked,
                })
            
            # Сохраняем бэкап в файл
            backup_filename = f"backup_future_records_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            with open(backup_filename, 'w', encoding='utf-8') as f:
                f.write("Резервная копия удаленных записей с будущими датами\n")
                f.write(f"Дата создания: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                f.write("=" * 60 + "\n")
                for item in backup_data:
                    f.write(f"ID: {item['id']}, Employee: {item['employee_id']}, "
                           f"Check-in: {item['check_in']}, Check-out: {item['check_out']}, "
                           f"Hours: {item['hours_worked']}\n")
            
            print(f"💾 Создан бэкап: {backup_filename}")
            
            # Удаляем записи
            deleted_count, deleted_details = future_worklogs.delete()
            
            print(f"✅ Успешно удалено {deleted_count} записей!")
            print("Детали:", deleted_details)
            
            # Проверяем что удаление прошло успешно
            remaining = WorkLog.objects.filter(check_in__date__gt=date.today()).count()
            if remaining == 0:
                print("🎉 Все записи с будущими датами успешно удалены!")
            else:
                print(f"⚠️ Остались еще {remaining} записей с будущими датами")
            
            break
            
        elif confirm in ['нет', 'no', 'n']:
            print("❌ Удаление отменено.")
            break
        else:
            print("Пожалуйста, введите 'да' или 'нет'")

def main():
    """Основная функция"""
    print("🧹 ОЧИСТКА ЗАПИСЕЙ С БУДУЩИМИ ДАТАМИ")
    print("=" * 50)
    
    try:
        # Найти записи с будущими датами
        future_records = find_future_records()
        
        # Проанализировать влияние
        analyze_impact(future_records)
        
        # Предложить удаление
        if future_records.exists():
            safe_delete_records(future_records)
        
        print("\n✅ Скрипт завершен!")
        
    except Exception as e:
        print(f"❌ Ошибка выполнения скрипта: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()