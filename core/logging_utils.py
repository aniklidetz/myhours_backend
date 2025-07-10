"""
Утилиты для безопасного логирования с автоматическим маскированием PII данных
"""
import re
import hashlib
import logging
from typing import Any, Dict, Optional, Union


def mask_email(email: str) -> str:
    """
    Маскирует email адрес для безопасного логирования
    
    Args:
        email: Email адрес для маскирования
        
    Returns:
        Маскированный email (например: a***@example.com)
    """
    if not email or '@' not in email:
        return '[invalid_email]'
    
    username, domain = email.split('@', 1)
    if len(username) <= 1:
        return f"*@{domain}"
    
    return f"{username[0]}***@{domain}"


def mask_phone(phone: str) -> str:
    """
    Маскирует номер телефона для безопасного логирования
    
    Args:
        phone: Номер телефона для маскирования
        
    Returns:
        Маскированный номер (например: ***4567)
    """
    if not phone:
        return '[no_phone]'
    
    # Убираем все нецифровые символы
    digits = re.sub(r'\D', '', phone)
    
    if len(digits) < 4:
        return '***'
    
    return f"***{digits[-4:]}"


def mask_coordinates(lat: float, lng: float) -> str:
    """
    Маскирует GPS координаты для безопасного логирования
    
    Args:
        lat: Широта
        lng: Долгота
        
    Returns:
        Обобщённое местоположение
    """
    # Простое определение зоны по координатам
    if 32.0 <= lat <= 32.1 and 34.7 <= lng <= 34.9:
        return "Office Area"
    elif 31.5 <= lat <= 33.0 and 34.0 <= lng <= 35.5:
        return "City Area"
    else:
        return "Remote Location"


def mask_name(full_name: str) -> str:
    """
    Маскирует полное имя для безопасного логирования
    
    Args:
        full_name: Полное имя для маскирования
        
    Returns:
        Инициалы (например: M.P.)
    """
    if not full_name or not full_name.strip():
        return '[no_name]'
    
    parts = full_name.strip().split()
    if len(parts) == 1:
        return f"{parts[0][0]}."
    elif len(parts) >= 2:
        return f"{parts[0][0]}.{parts[1][0]}."
    
    return '[no_name]'


def hash_user_id(user_id: Union[int, str], salt: str = "myhours_2025") -> str:
    """
    Создаёт хэш от user ID для безопасного логирования
    
    Args:
        user_id: ID пользователя
        salt: Соль для хэширования
        
    Returns:
        Хэшированный ID (первые 8 символов)
    """
    if not user_id:
        return '[no_id]'
    
    hash_input = f"{salt}:{user_id}"
    hash_obj = hashlib.sha256(hash_input.encode())
    return f"usr_{hash_obj.hexdigest()[:8]}"


def safe_log_user(user, action: str = "action") -> Dict[str, Any]:
    """
    Создаёт безопасный объект для логирования данных пользователя
    
    Args:
        user: Объект пользователя (Django User model)
        action: Описание действия
        
    Returns:
        Словарь с безопасными для логирования данными
    """
    if not user:
        return {"action": action, "user": "anonymous"}
    
    safe_data = {
        "action": action,
        "user_hash": hash_user_id(user.id),
        "role": getattr(user, 'role', 'unknown'),
        "is_superuser": getattr(user, 'is_superuser', False)
    }
    
    # Маскируем email если присутствует
    if hasattr(user, 'email') and user.email:
        safe_data["email_masked"] = mask_email(user.email)
    
    return safe_data


def safe_log_employee(employee, action: str = "action") -> Dict[str, Any]:
    """
    Создаёт безопасный объект для логирования данных сотрудника
    
    Args:
        employee: Объект сотрудника (Employee model)
        action: Описание действия
        
    Returns:
        Словарь с безопасными для логирования данными
    """
    if not employee:
        return {"action": action, "employee": "none"}
    
    safe_data = {
        "action": action,
        "employee_hash": hash_user_id(employee.id),
        "role": getattr(employee, 'role', 'unknown'),
        "employment_type": getattr(employee, 'employment_type', 'unknown')
    }
    
    # Маскируем персональные данные
    if hasattr(employee, 'email') and employee.email:
        safe_data["email_masked"] = mask_email(employee.email)
    
    if hasattr(employee, 'first_name') and hasattr(employee, 'last_name'):
        full_name = f"{employee.first_name or ''} {employee.last_name or ''}".strip()
        if full_name:
            safe_data["name_initials"] = mask_name(full_name)
    
    if hasattr(employee, 'phone') and employee.phone:
        safe_data["phone_masked"] = mask_phone(employee.phone)
    
    return safe_data


def safe_log_location(lat: Optional[float], lng: Optional[float]) -> str:
    """
    Создаёт безопасное представление местоположения для логирования
    
    Args:
        lat: Широта
        lng: Долгота
        
    Returns:
        Обобщённое местоположение
    """
    if lat is None or lng is None:
        return "Location Unknown"
    
    return mask_coordinates(lat, lng)


def get_safe_logger(name: str) -> logging.Logger:
    """
    Создаёт logger с предупреждением о безопасности
    
    Args:
        name: Имя logger'а
        
    Returns:
        Настроенный logger
    """
    logger = logging.getLogger(name)
    
    # Добавляем фильтр для обнаружения потенциальных PII
    class PIIDetectionFilter(logging.Filter):
        def filter(self, record):
            message = record.getMessage()
            
            # Простые паттерны для обнаружения PII
            email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
            coord_pattern = r'\b\d{1,3}\.\d{4,}\b'  # Точные координаты
            
            if re.search(email_pattern, message):
                record.msg = "[WARNING: Potential email detected in log] " + record.msg
            
            if re.search(coord_pattern, message):
                record.msg = "[WARNING: Potential coordinates detected in log] " + record.msg
            
            return True
    
    logger.addFilter(PIIDetectionFilter())
    return logger


# Примеры использования:
"""
# В views.py вместо:
logger.info(f"Invitation URL for {employee.email}: {invitation_url}")

# Используйте:
logger.info(f"Invitation URL generated", extra=safe_log_employee(employee, "invitation_sent"))

# Вместо:
logger.info(f"User {user.email} logged in from {lat}, {lng}")

# Используйте:
safe_logger = get_safe_logger(__name__)
safe_logger.info(f"User login", extra={
    **safe_log_user(user, "login"),
    "location": safe_log_location(lat, lng)
})
"""