#!/usr/bin/env python
"""
Финальная проверка статуса биометрической системы
"""

import os
import sys
import django

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
django.setup()

from biometrics.services.mongodb_service import mongodb_service
from django.conf import settings

print("=== ФИНАЛЬНАЯ ПРОВЕРКА БИОМЕТРИЧЕСКОЙ СИСТЕМЫ ===")
print()

# 1. Проверяем настройки
print("1. НАСТРОЙКИ СИСТЕМЫ:")
print(f"   - DEBUG режим: {settings.DEBUG}")
print(f"   - ENABLE_BIOMETRIC_MOCK: {settings.ENABLE_BIOMETRIC_MOCK}")
print()

# 2. Статус готовности
if settings.ENABLE_BIOMETRIC_MOCK:
    print("⚠️  ВНИМАНИЕ: Mock режим ВКЛ - тестовые данные!")
    print("   - Любой может войти с любым лицом")
    print("   - Биометрия НЕ сохраняется реально")
    print("   🔧 Для продакшена установите ENABLE_BIOMETRIC_MOCK=False")
else:
    print("✅ ОТЛИЧНО: Mock режим ВЫКЛ!")
    print("   - Реальная биометрия АКТИВНА")
    print("   - Только зарегистрированные лица работают")
    print("   - Данные сохраняются в MongoDB")

print()

# 3. Проверяем данные в MongoDB
print("2. БИОМЕТРИЧЕСКИЕ ДАННЫЕ:")
if mongodb_service.collection is not None:
    total_docs = mongodb_service.collection.count_documents({})
    active_docs = mongodb_service.collection.count_documents({"is_active": True})
    
    print(f"   - Всего записей в MongoDB: {total_docs}")
    print(f"   - Активных записей: {active_docs}")
    
    if total_docs > 0:
        docs = list(mongodb_service.collection.find({"is_active": True}))
        print("   - Зарегистрированные сотрудники:")
        for doc in docs:
            employee_id = doc.get('employee_id')
            embeddings_count = len(doc.get('embeddings', []))
            print(f"     * Employee ID {employee_id}: {embeddings_count} лиц")
    else:
        print("   ⚠️ Биометрических данных нет!")
        print("   📝 Пользователи должны зарегистрировать биометрию")
else:
    print("   ❌ MongoDB недоступна!")

print()

# 4. Итоговый статус
print("3. ИТОГОВЫЙ СТАТУС:")
if not settings.ENABLE_BIOMETRIC_MOCK and mongodb_service.collection is not None:
    print("   🎉 СИСТЕМА ГОТОВА К РАБОТЕ!")
    print("   ✅ Реальная биометрия включена")
    print("   ✅ MongoDB подключена")
    if total_docs > 0:
        print(f"   ✅ {active_docs} сотрудников с биометрией")
    else:
        print("   📝 Нужно зарегистрировать биометрию пользователей")
else:
    print("   ⚠️ СИСТЕМА НЕ ГОТОВА:")
    if settings.ENABLE_BIOMETRIC_MOCK:
        print("   - Mock режим включен")
    if mongodb_service.collection is None:
        print("   - MongoDB недоступна")

print("\n=== КОНЕЦ ПРОВЕРКИ ===")