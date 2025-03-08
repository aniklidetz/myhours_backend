# Заглушка для face_recognition
import logging
import numpy as np

logger = logging.getLogger(__name__)

class FaceRecognitionService:
    """
    Заглушка для сервиса распознавания лиц.
    Временная реализация для обеспечения работы миграций.
    """
    
    @staticmethod
    def decode_image(base64_image):
        logger.warning("Метод decode_image вызван, но face_recognition не установлен")
        return None
    
    @staticmethod
    def encode_face(image):
        logger.warning("Метод encode_face вызван, но face_recognition не установлен")
        return []
    
    @classmethod
    def save_employee_face(cls, employee_id, base64_image):
        logger.warning("Метод save_employee_face вызван, но face_recognition не установлен")
        return None
    
    @classmethod
    def recognize_employee(cls, base64_image, tolerance=0.6):
        logger.warning("Метод recognize_employee вызван, но face_recognition не установлен")
        return None