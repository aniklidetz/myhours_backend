import logging

logger = logging.getLogger(__name__)

class BiometricService:
    """
    Заглушка для сервиса биометрии.
    Временная реализация для обеспечения работы миграций.
    """
    
    @staticmethod
    def get_collection():
        logger.warning("Метод get_collection вызван, но MongoDB не настроен")
        return None
    
    @classmethod
    def save_face_encoding(cls, employee_id, face_encoding, image_data=None):
        logger.warning("Метод save_face_encoding вызван, но MongoDB не настроен")
        return "temporary_id"
    
    @classmethod
    def get_employee_face_encodings(cls, employee_id=None):
        logger.warning("Метод get_employee_face_encodings вызван, но MongoDB не настроен")
        return []
    
    @classmethod
    def delete_employee_face_encodings(cls, employee_id):
        logger.warning("Метод delete_employee_face_encodings вызван, но MongoDB не настроен")
        return 0