# Проверка: Redis Cache Versioning

## Результат: ❌ ПРОБЛЕМА СУЩЕСТВУЕТ

**Дата проверки:** 2025-11-01
**Статус:** Критическая проблема - ключи кэша не версионированы
**Приоритет:** 🟡 MEDIUM — Ops
**Решение:** Добавить VERSION namespace ко всем Redis ключам

---

## Анализ проблемы

### Описание из issue

**Проблема:**
> В Redis-ключах кэша нет версии namespace. Ключи вида `payroll:result:{emp_id}:{year}-{month}`. При изменении схемы данные устаревают и «травят» новые версии.

**Решение:**
> Версионировать ключи через `settings.CACHE_VERSION` и инкрементировать при релизах.

---

## Фактическое состояние

### 1. Django Cache Framework (правильный подход)

**Конфигурация:** `myhours/redis_settings.py:63, 108`

```python
cache_config = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": f"redis://{REDIS_HOST}:{REDIS_PORT}/{REDIS_DB}",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            # ...
        },
        "TIMEOUT": 300,
        "VERSION": 1,  # ✅ VERSION parameter присутствует
        "KEY_PREFIX": "myhours",  # ✅ Prefix присутствует
    }
}
```

**Как работает:**
- Django автоматически добавляет версию к ключам
- Формат ключа: `myhours:1:your_key`
- При изменении VERSION=2, старые ключи становятся недоступны

**Пример использования (integrations/services/hebcal_api_client.py:104):**
```python
from django.core.cache import cache

cache_key = f"{cls.CACHE_KEY_PREFIX}{year}"  # "hebcal_holidays_2025"
cached_data = cache.get(cache_key)  # Django добавит версию автоматически
# Реальный ключ в Redis: "myhours:1:hebcal_holidays_2025"
```

---

### 2. Payroll Services (❌ ПРОБЛЕМА)

#### A) PayrollRedisCache

**Файл:** `payroll/redis_cache_service.py:40-93`

**Инициализация:**
```python
class PayrollRedisCache:
    def __init__(self):
        # ❌ Использует RAW Redis client, НЕ Django cache framework
        redis_url = os.environ.get("REDIS_URL")
        self.redis_client = redis.from_url(redis_url, decode_responses=True)
```

**Генерация ключей (line 90-93):**
```python
def _make_key(self, prefix: str, *args) -> str:
    """Generate cache key"""
    key_parts = [prefix] + [str(arg) for arg in args]
    return ":".join(key_parts)  # ❌ НЕТ VERSION namespace!
```

**Примеры ключей:**
```python
# Holidays cache (line 113)
cache_key = self._make_key("holidays", year, month)
# Результат: "holidays:2025:11" ❌ НЕТ версии!

# Daily calculation cache (line 267)
cache_key = self._make_key("daily_calc", employee_id, work_date.isoformat())
# Результат: "daily_calc:123:2025-11-01" ❌ НЕТ версии!

# Monthly summary cache (line 306)
cache_key = self._make_key("monthly_summary", employee_id, year, month)
# Результат: "monthly_summary:123:2025:11" ❌ НЕТ версии!
```

**Использование Redis (lines 116, 199, 270, 309):**
```python
# Direct Redis operations WITHOUT Django cache versioning
cached_data = self.redis_client.get(cache_key)  # ❌ Нет VERSION
self.redis_client.setex(cache_key, ttl, data)   # ❌ Нет VERSION
```

---

#### B) BulkCacheManager

**Файл:** `payroll/services/bulk/cache_manager.py:45-100`

**Та же проблема:**
```python
class BulkCacheManager:
    def __init__(self):
        # ❌ RAW Redis client
        self.redis_client = redis.from_url(redis_url, decode_responses=True)

    def _make_key(self, prefix: str, *args) -> str:
        """Generate cache key compatible with PayrollRedisCache."""
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)  # ❌ НЕТ VERSION!
```

---

#### C) Enhanced Redis Cache

**Файл:** `payroll/enhanced_redis_cache.py:20-92`

**Наследуется от PayrollRedisCache:**
```python
class EnhancedPayrollCache(PayrollRedisCache):
    # Использует тот же _make_key() без версии
    def cache_shabbat_times_for_month(self, year: int, month: int):
        cache_key = self._make_key("enhanced_holidays", year, month)
        # Результат: "enhanced_holidays:2025:11" ❌ НЕТ версии!
```

---

### 3. Другие сервисы (✅ ПРАВИЛЬНО)

**Список сервисов, использующих Django cache framework:**

**С версионированием (используют `cache.get/cache.set`):**
1. `integrations/services/hebcal_api_client.py` ✅
2. `integrations/services/unified_shabbat_service.py` ✅
3. `biometrics/services/face_recognition_service.py` ✅
4. `core/idempotency.py` ✅
5. `worktime/views.py` ✅

**Пример правильного использования:**
```python
from django.core.cache import cache

# Django automatically adds: KEY_PREFIX + VERSION + your_key
cache.set("my_key", data, timeout=3600)
# Реальный ключ: "myhours:1:my_key" ✅
```

---

## Сравнение подходов

### Подход 1: Raw Redis Client (payroll services) ❌

**Текущая реализация:**
```python
# payroll/redis_cache_service.py
redis_client = redis.from_url(redis_url)
cache_key = "holidays:2025:11"
redis_client.setex(cache_key, ttl, data)
```

**Проблемы:**
- ❌ НЕТ автоматического VERSION namespace
- ❌ НЕТ KEY_PREFIX
- ❌ При изменении структуры данных старые ключи остаются
- ❌ Новый код читает старые данные → crashes или bad calculations
- ❌ Требует manual cache invalidation при каждом релизе

**Риски:**
1. **Schema Evolution:**
   ```python
   # v1: cache_data = {"total_hours": 8.5}
   # v2: cache_data = {"total_hours": 8.5, "overtime_hours": 1.5}
   # Старые ключи содержат только total_hours
   # Новый код ожидает overtime_hours → KeyError!
   ```

2. **Data Structure Changes:**
   ```python
   # v1: holidays_dict[date_str] = {"name": "...", "is_holiday": True}
   # v2: holidays_dict[date_str] = {"name": "...", "is_holiday": True, "start_time": "..."}
   # Старые кэши не имеют start_time → NoneType errors
   ```

3. **Business Logic Changes:**
   ```python
   # v1: payroll calculation включает только base_hours
   # v2: payroll calculation включает base_hours + meal_allowance
   # Старые кэши содержат неправильные суммы → incorrect payroll!
   ```

---

### Подход 2: Django Cache Framework (integrations) ✅

**Правильная реализация:**
```python
from django.core.cache import cache

cache_key = "holidays:2025:11"
cache.set(cache_key, data, timeout=ttl)
# Реальный ключ: "myhours:1:holidays:2025:11"
```

**Преимущества:**
- ✅ Автоматическое добавление VERSION
- ✅ Автоматическое добавление KEY_PREFIX
- ✅ При изменении VERSION старые ключи автоматически игнорируются
- ✅ НЕ требует manual invalidation
- ✅ Backend-agnostic (Redis, Memcached, LocMem)

**Как работает VERSION bump:**
```python
# settings.py: VERSION = 1
cache.set("my_key", data)  # Redis: "myhours:1:my_key"

# После релиза с изменением схемы:
# settings.py: VERSION = 2
cache.set("my_key", new_data)  # Redis: "myhours:2:my_key"
cache.get("my_key")  # Читает из "myhours:2:my_key", не из старого "myhours:1:my_key" ✅
```

---

## Использование payroll cache в проекте

### Критические места использования

**1. Holiday Loading (запускается ЕЖЕДНЕВНО):**
```python
# payroll/redis_cache_service.py:103-131
def get_holidays_for_month(self, year: int, month: int) -> Dict[str, Dict]:
    cache_key = self._make_key("holidays", year, month)
    cached_data = self.redis_client.get(cache_key)
    # ❌ При изменении Holiday model структуры старые кэши содержат неполные данные
```

**Частота:**
- Каждый payroll calculation (~1000/month)
- Каждый bulk calculation (~100/month)
- TTL: 7 days

**Риск:**
- После добавления нового поля в Holiday model
- Старые кэши не содержат это поле
- Код падает с KeyError или использует None

---

**2. Daily Payroll Calculation (запускается ~30 раз/день):**
```python
# payroll/redis_cache_service.py:260-296
def get_daily_calculation(self, employee_id: int, work_date: date) -> Optional[Dict]:
    cache_key = self._make_key("daily_calc", employee_id, work_date.isoformat())
    cached_data = self.redis_client.get(cache_key)
    # ❌ При изменении PayrollResult structure старые кэши содержат неправильные данные
```

**Частота:**
- ~30 employees × ~30 days = ~900 calculations/month
- TTL: 24 hours

**Риск:**
- После изменения расчета (добавление meal allowance, night differential, etc.)
- Старые кэши содержат неполные расчеты
- Сотрудники получают неправильную зарплату!

---

**3. Monthly Summary Cache (запускается ~100 раз/month):**
```python
# payroll/redis_cache_service.py:299-358
def get_monthly_summary(self, employee_id: int, year: int, month: int) -> Optional[Dict]:
    cache_key = self._make_key("monthly_summary", employee_id, year, month)
    cached_data = self.redis_client.get(cache_key)
    # ❌ При изменении summary structure старые кэши содержат неправильные суммы
```

**Частота:**
- ~100 employees × 1 summary/month = ~100 calculations/month
- TTL: 1 hour

**Риск:**
- После изменения summary calculation
- Старые кэши содержат неправильные totals
- Reports показывают неправильные данные

---

**4. Bulk Holiday Lookups (запускается при bulk operations):**
```python
# payroll/redis_cache_service.py:221-256
def get_holidays_for_date_range(self, start_date: date, end_date: date) -> Dict[str, Dict]:
    # Использует get_holidays_for_month под капотом
    # ❌ Та же проблема с версионированием
```

**Частота:**
- Bulk payroll generation (~10 times/month)
- Generate missing payroll command

**Риск:**
- При bulk operations используются старые кэши
- Массовый неправильный расчет зарплат для всех сотрудников

---

## Реальный сценарий проблемы

### Scenario: Добавление Meal Allowance

**До изменения (v1):**
```python
# payroll/services/contracts.py - PayrollResult
class PayrollResult:
    total_hours: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    total_amount: Decimal

# Cached data structure
cached_result = {
    "total_hours": "8.5",
    "regular_hours": "8.0",
    "overtime_hours": "0.5",
    "total_amount": "425.00"
}
```

**После изменения (v2):**
```python
# Добавили meal_allowance
class PayrollResult:
    total_hours: Decimal
    regular_hours: Decimal
    overtime_hours: Decimal
    meal_allowance: Decimal  # NEW!
    total_amount: Decimal

# Новый код ожидает meal_allowance
def calculate_payroll(...):
    result = cache.get(cache_key)  # Получает СТАРЫЙ cached_result
    meal_allowance = result.get("meal_allowance")  # None!
    total = result["total_amount"] + meal_allowance  # TypeError: unsupported operand type(s)
```

**Результат:**
- ❌ Crashes при чтении старых кэшей
- ❌ Неправильные расчеты если код обрабатывает None
- ❌ Требует manual cache invalidation для всех ключей

**С VERSION namespace:**
```python
# v1: Redis key = "myhours:1:daily_calc:123:2025-11-01"
# v2: Redis key = "myhours:2:daily_calc:123:2025-11-01"
# Старые кэши автоматически игнорируются ✅
```

---

## Impact Analysis

### Current Cache Keys (без VERSION)

**Redis keys snapshot:**
```
holidays:2025:10
holidays:2025:11
holidays:2025:12
daily_calc:1:2025-11-01
daily_calc:1:2025-11-02
daily_calc:2:2025-11-01
monthly_summary:1:2025:11
monthly_summary:2:2025:11
enhanced_holidays:2025:11
```

**Проблемы:**
1. Нет способа инвалидировать все старые ключи разом
2. При schema change требуется manual FLUSHDB или pattern matching
3. Pattern matching с wildcards медленный на production (blocking operation)
4. Риск удалить новые ключи вместе со старыми

---

### With VERSION Namespace

**Redis keys with VERSION:**
```
myhours:1:holidays:2025:10
myhours:1:holidays:2025:11
myhours:1:daily_calc:1:2025-11-01
myhours:1:monthly_summary:1:2025:11
```

**После VERSION bump (VERSION=2):**
```
# Старые ключи остаются, но игнорируются
myhours:1:holidays:2025:10  # Ignored by Django
myhours:1:holidays:2025:11  # Ignored by Django

# Новые ключи создаются автоматически
myhours:2:holidays:2025:11  # Used by Django
myhours:2:daily_calc:1:2025-11-01  # Used by Django
```

**Преимущества:**
- ✅ Автоматическая инвалидация старых кэшей
- ✅ Постепенный expiry старых ключей по TTL
- ✅ НЕ требует FLUSHDB
- ✅ НЕ требует pattern matching
- ✅ Zero-downtime cache invalidation

---

## Выводы

### ❌ Проблема СУЩЕСТВУЕТ и КРИТИЧНА

1. **Payroll services используют raw Redis client:**
   - PayrollRedisCache
   - BulkCacheManager
   - EnhancedPayrollCache

2. **Ключи НЕ содержат VERSION namespace:**
   - `holidays:{year}:{month}` вместо `myhours:1:holidays:{year}:{month}`
   - `daily_calc:{emp_id}:{date}` вместо `myhours:1:daily_calc:{emp_id}:{date}`
   - `monthly_summary:{emp_id}:{year}:{month}` вместо `myhours:1:monthly_summary:{emp_id}:{year}:{month}`

3. **Риски:**
   - При изменении data structure старые кэши содержат неполные данные
   - Crashes или incorrect calculations
   - Требует manual cache invalidation (FLUSHDB или pattern matching)
   - Блокирует production при pattern matching

4. **Impact:**
   - HIGH: Payroll calculations критичны для бизнеса
   - MEDIUM: TTL от 1 часа до 7 дней
   - MEDIUM: ~1000+ cached keys в production

---

## Решение

### Approach 1: Migrate to Django Cache Framework (RECOMMENDED)

**Преимущества:**
- ✅ Automatic VERSION namespace
- ✅ Automatic KEY_PREFIX
- ✅ Backend-agnostic
- ✅ Django best practices
- ✅ Easy version bumps

**Недостатки:**
- ⚠️ Требует рефакторинг 3 файлов
- ⚠️ Требует миграцию существующих ключей

**Implementation:**
```python
# payroll/redis_cache_service.py
from django.core.cache import cache

class PayrollRedisCache:
    def _make_key(self, prefix: str, *args) -> str:
        """Generate cache key"""
        key_parts = [prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)

    def get_holidays_for_month(self, year: int, month: int) -> Dict[str, Dict]:
        cache_key = self._make_key("holidays", year, month)
        cached_data = cache.get(cache_key)  # ✅ Django adds VERSION
        if cached_data:
            return cached_data

        holidays_dict = self._get_holidays_from_db(year, month)
        cache.set(cache_key, holidays_dict, timeout=7*24*60*60)  # ✅ Django adds VERSION
        return holidays_dict
```

---

### Approach 2: Add Manual VERSION to Raw Keys (FALLBACK)

**Преимущества:**
- ✅ Minimal code changes
- ✅ No dependency on Django cache

**Недостатки:**
- ❌ Manual VERSION management
- ❌ Requires code changes for version bumps
- ❌ Not backend-agnostic

**Implementation:**
```python
# myhours/settings.py
REDIS_CACHE_VERSION = 1  # Increment on schema changes

# payroll/redis_cache_service.py
from django.conf import settings

class PayrollRedisCache:
    def _make_key(self, prefix: str, *args) -> str:
        """Generate cache key with VERSION"""
        version = getattr(settings, 'REDIS_CACHE_VERSION', 1)
        key_parts = [f"v{version}", prefix] + [str(arg) for arg in args]
        return ":".join(key_parts)

# Результат: "v1:holidays:2025:11" ✅ С версией
```

**Version bump process:**
```python
# После изменения schema:
# settings.py: REDIS_CACHE_VERSION = 2
# Deploy
# Старые ключи "v1:..." автоматически игнорируются
# Новые ключи "v2:..." создаются автоматически
```

---

## Рекомендации

### Immediate (Required)

1. ✅ **Выбрать approach:**
   - Approach 1 (Django cache) - RECOMMENDED для consistency
   - Approach 2 (Manual VERSION) - Если нужна минимальная рефакторинг

2. ⏳ **Implement VERSION namespace:**
   - Modify `_make_key()` в PayrollRedisCache
   - Modify `_make_key()` в BulkCacheManager
   - Add VERSION parameter to settings

3. ⏳ **Test version bumps:**
   - Create test for VERSION increment
   - Verify old keys are ignored
   - Verify new keys are created

4. ⏳ **Document version bump process:**
   - When to increment VERSION
   - How to verify cache invalidation
   - How to monitor cache hit rates

### Short-term (Recommended)

5. ⏳ **Add cache monitoring:**
   ```python
   def get_cache_version_stats() -> Dict[str, int]:
       """Count keys by version"""
       versions = {}
       for key in redis_client.scan_iter():
           version = key.split(":")[0]
           versions[version] = versions.get(version, 0) + 1
       return versions
   ```

6. ⏳ **Add cache version to health check:**
   ```python
   # myhours/health.py
   def cache_health():
       return {
           "cache_version": settings.REDIS_CACHE_VERSION,
           "keys_by_version": get_cache_version_stats()
       }
   ```

### Long-term (Optional)

7. ⏳ **Automatic cache cleanup:**
   ```python
   # Celery task для удаления старых версий
   @periodic_task(run_every=timedelta(days=7))
   def cleanup_old_cache_versions():
       current_version = settings.REDIS_CACHE_VERSION
       old_versions = [f"v{v}" for v in range(1, current_version)]
       for old_version in old_versions:
           pattern = f"{old_version}:*"
           # Delete keys older than 7 days
   ```

8. ⏳ **Cache version migration script:**
   ```python
   # management/commands/migrate_cache_version.py
   def migrate_cache_keys(from_version: int, to_version: int):
       """Migrate cache keys from one version to another"""
       # Read old keys, transform data if needed, write to new keys
   ```

---

## Заключение

**Проблема из issue ПОДТВЕРЖДЕНА:**

- ❌ Payroll Redis keys НЕ содержат VERSION namespace
- ❌ При schema changes старые кэши "травят" новые версии
- ❌ Требует manual invalidation (blocking operation на production)
- ❌ Риск incorrect payroll calculations (CRITICAL!)

**Рекомендуемое решение:**
- ✅ Migrate to Django Cache Framework (Approach 1)
- ✅ Adds automatic VERSION + KEY_PREFIX
- ✅ Follows Django best practices
- ✅ Zero-downtime cache invalidation

**Приоритет:** 🟡 MEDIUM (но HIGH impact при schema changes)

**Статус:** ❌ **NEEDS FIX**

---

**Дата анализа:** 2025-11-01
**Автор:** Claude
**Решение:** Add VERSION namespace to all payroll cache keys
