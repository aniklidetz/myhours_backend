"""
Targeted tests for biometrics/models.py
Focus on achieving 90%+ coverage for uncovered model methods and validations
"""

import uuid
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone

from biometrics.models import (
    BiometricAttempt,
    BiometricLog,
    BiometricProfile,
    FaceQualityCheck,
)
from users.models import Employee


class BiometricProfileTest(TestCase):
    """Test BiometricProfile model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )

    def test_biometric_profile_creation(self):
        """Test BiometricProfile creation with default values"""
        profile = BiometricProfile.objects.create(employee=self.employee)
        
        self.assertEqual(profile.employee, self.employee)
        self.assertEqual(profile.embeddings_count, 0)
        self.assertTrue(profile.is_active)
        self.assertIsNone(profile.mongodb_id)
        self.assertIsNotNone(profile.created_at)
        self.assertIsNotNone(profile.last_updated)

    def test_biometric_profile_str_method(self):
        """Test BiometricProfile __str__ method"""
        profile = BiometricProfile.objects.create(employee=self.employee)
        
        expected_str = f"Biometric Profile for {self.employee.get_full_name()}"
        self.assertEqual(str(profile), expected_str)

    def test_biometric_profile_str_with_custom_employee_name(self):
        """Test BiometricProfile __str__ method with different employee name"""
        # Create employee with different name
        user2 = User.objects.create_user(
            username='janedoe',
            email='jane@example.com',
            password='pass123'
        )
        employee2 = Employee.objects.create(
            user=user2,
            first_name='Jane',
            last_name='Doe',
            email='jane@example.com',
            employment_type='part_time',
            role='manager'
        )
        
        profile = BiometricProfile.objects.create(employee=employee2)
        expected_str = "Biometric Profile for Jane Doe"
        self.assertEqual(str(profile), expected_str)

    def test_biometric_profile_meta_attributes(self):
        """Test BiometricProfile meta attributes"""
        self.assertEqual(BiometricProfile._meta.db_table, "biometric_profiles")
        self.assertEqual(BiometricProfile._meta.verbose_name, "Biometric Profile")
        self.assertEqual(BiometricProfile._meta.verbose_name_plural, "Biometric Profiles")

    def test_biometric_profile_one_to_one_relationship(self):
        """Test one-to-one relationship with Employee"""
        profile = BiometricProfile.objects.create(employee=self.employee)
        
        # Test reverse relationship
        self.assertEqual(self.employee.biometric_profile, profile)

    def test_biometric_profile_update_fields(self):
        """Test updating BiometricProfile fields"""
        profile = BiometricProfile.objects.create(employee=self.employee)
        
        # Update fields
        profile.embeddings_count = 5
        profile.is_active = False
        profile.mongodb_id = "test_mongo_id_123"
        profile.save()
        
        # Refresh from database
        profile.refresh_from_db()
        
        self.assertEqual(profile.embeddings_count, 5)
        self.assertFalse(profile.is_active)
        self.assertEqual(profile.mongodb_id, "test_mongo_id_123")


class BiometricLogTest(TestCase):
    """Test BiometricLog model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='John',
            last_name='Smith',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )

    def test_biometric_log_creation_with_employee(self):
        """Test BiometricLog creation with employee"""
        log = BiometricLog.objects.create(
            employee=self.employee,
            action='check_in',
            confidence_score=0.95,
            location='Office Building',
            device_info={'device': 'iPhone 14', 'version': '16.0'},
            ip_address='192.168.1.100',
            success=True
        )
        
        self.assertEqual(log.employee, self.employee)
        self.assertEqual(log.action, 'check_in')
        self.assertEqual(log.confidence_score, 0.95)
        self.assertEqual(log.location, 'Office Building')
        self.assertTrue(log.success)
        self.assertIsInstance(log.id, uuid.UUID)

    def test_biometric_log_creation_without_employee(self):
        """Test BiometricLog creation without employee (failed attempt)"""
        log = BiometricLog.objects.create(
            employee=None,
            action='failed',
            success=False,
            error_message='No face detected',
            ip_address='192.168.1.200'
        )
        
        self.assertIsNone(log.employee)
        self.assertEqual(log.action, 'failed')
        self.assertFalse(log.success)
        self.assertEqual(log.error_message, 'No face detected')

    def test_biometric_log_str_method_with_employee(self):
        """Test BiometricLog __str__ method with employee"""
        log = BiometricLog.objects.create(
            employee=self.employee,
            action='check_out',
            success=True
        )
        
        expected_str = f"check_out - John Smith - {log.created_at}"
        self.assertEqual(str(log), expected_str)

    def test_biometric_log_str_method_without_employee(self):
        """Test BiometricLog __str__ method without employee"""
        log = BiometricLog.objects.create(
            employee=None,
            action='failed',
            success=False
        )
        
        expected_str = f"failed - Unknown - {log.created_at}"
        self.assertEqual(str(log), expected_str)

    def test_biometric_log_action_choices(self):
        """Test BiometricLog action choices"""
        expected_choices = [
            ("check_in", "Check In"),
            ("check_out", "Check Out"),
            ("registration", "Registration"),
            ("failed", "Failed Attempt"),
        ]
        
        self.assertEqual(BiometricLog.ACTION_CHOICES, expected_choices)

    def test_biometric_log_meta_attributes(self):
        """Test BiometricLog meta attributes"""
        self.assertEqual(BiometricLog._meta.db_table, "biometric_logs")
        self.assertEqual(BiometricLog._meta.verbose_name, "Biometric Log")
        self.assertEqual(BiometricLog._meta.verbose_name_plural, "Biometric Logs")
        self.assertEqual(BiometricLog._meta.ordering, ["-created_at"])

    def test_biometric_log_default_values(self):
        """Test BiometricLog default values"""
        log = BiometricLog.objects.create(action='registration')
        
        self.assertFalse(log.success)
        self.assertEqual(log.device_info, {})
        self.assertEqual(log.error_message, '')
        self.assertEqual(log.location, '')

    def test_biometric_log_with_processing_time(self):
        """Test BiometricLog with processing time"""
        log = BiometricLog.objects.create(
            employee=self.employee,
            action='check_in',
            processing_time_ms=1250,
            success=True
        )
        
        self.assertEqual(log.processing_time_ms, 1250)


class BiometricAttemptTest(TestCase):
    """Test BiometricAttempt model functionality"""

    def setUp(self):
        """Set up test data"""
        self.ip_address = '192.168.1.100'

    def test_biometric_attempt_creation(self):
        """Test BiometricAttempt creation"""
        attempt = BiometricAttempt.objects.create(ip_address=self.ip_address)
        
        self.assertEqual(attempt.ip_address, self.ip_address)
        self.assertEqual(attempt.attempts_count, 0)
        self.assertIsNotNone(attempt.last_attempt)
        self.assertIsNone(attempt.blocked_until)

    def test_is_blocked_method_not_blocked(self):
        """Test is_blocked method when not blocked"""
        attempt = BiometricAttempt.objects.create(ip_address=self.ip_address)
        
        self.assertFalse(attempt.is_blocked())

    def test_is_blocked_method_blocked_still_valid(self):
        """Test is_blocked method when blocked and still valid"""
        attempt = BiometricAttempt.objects.create(
            ip_address=self.ip_address,
            blocked_until=timezone.now() + timedelta(minutes=2)
        )
        
        self.assertTrue(attempt.is_blocked())

    def test_is_blocked_method_blocked_expired(self):
        """Test is_blocked method when blocked but expired"""
        attempt = BiometricAttempt.objects.create(
            ip_address=self.ip_address,
            blocked_until=timezone.now() - timedelta(minutes=1)
        )
        
        self.assertFalse(attempt.is_blocked())

    def test_increment_attempts_normal(self):
        """Test increment_attempts method under limit"""
        attempt = BiometricAttempt.objects.create(ip_address=self.ip_address)
        
        # Increment a few times
        attempt.increment_attempts()
        self.assertEqual(attempt.attempts_count, 1)
        self.assertIsNone(attempt.blocked_until)
        
        attempt.increment_attempts()
        self.assertEqual(attempt.attempts_count, 2)
        self.assertIsNone(attempt.blocked_until)

    def test_increment_attempts_reaches_limit(self):
        """Test increment_attempts method reaches blocking limit"""
        attempt = BiometricAttempt.objects.create(ip_address=self.ip_address)
        
        # Increment to reach limit (5 attempts)
        for i in range(5):
            attempt.increment_attempts()
        
        self.assertEqual(attempt.attempts_count, 5)
        self.assertIsNotNone(attempt.blocked_until)
        
        # Check that blocked_until is in the future
        self.assertGreater(attempt.blocked_until, timezone.now())
        
        # Check that it's blocked for approximately 5 minutes
        expected_unblock_time = timezone.now() + timedelta(minutes=5)
        time_diff = abs((attempt.blocked_until - expected_unblock_time).total_seconds())
        self.assertLess(time_diff, 60)  # Within 1 minute tolerance

    def test_increment_attempts_beyond_limit(self):
        """Test increment_attempts method beyond blocking limit"""
        attempt = BiometricAttempt.objects.create(
            ip_address=self.ip_address,
            attempts_count=5,
            blocked_until=timezone.now() + timedelta(minutes=3)
        )
        
        original_blocked_until = attempt.blocked_until
        attempt.increment_attempts()
        
        self.assertEqual(attempt.attempts_count, 6)
        # blocked_until should be updated to a new time
        self.assertNotEqual(attempt.blocked_until, original_blocked_until)

    def test_reset_attempts_method(self):
        """Test reset_attempts method"""
        attempt = BiometricAttempt.objects.create(
            ip_address=self.ip_address,
            attempts_count=3,
            blocked_until=timezone.now() + timedelta(minutes=2)
        )
        
        attempt.reset_attempts()
        
        self.assertEqual(attempt.attempts_count, 0)
        self.assertIsNone(attempt.blocked_until)

    def test_biometric_attempt_meta_attributes(self):
        """Test BiometricAttempt meta attributes"""
        self.assertEqual(BiometricAttempt._meta.db_table, "biometric_attempts")
        self.assertEqual(BiometricAttempt._meta.verbose_name, "Biometric Attempt")
        self.assertEqual(BiometricAttempt._meta.verbose_name_plural, "Biometric Attempts")

    def test_biometric_attempt_auto_update_last_attempt(self):
        """Test that last_attempt is auto-updated"""
        attempt = BiometricAttempt.objects.create(ip_address=self.ip_address)
        original_last_attempt = attempt.last_attempt
        
        # Wait a small amount and save again
        import time
        time.sleep(0.1)
        attempt.save()
        
        # last_attempt should be updated due to auto_now=True
        self.assertGreater(attempt.last_attempt, original_last_attempt)


class FaceQualityCheckTest(TestCase):
    """Test FaceQualityCheck model functionality"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='Test',
            last_name='User',
            email='test@example.com',
            employment_type='full_time',
            role='employee'
        )
        
        self.biometric_log = BiometricLog.objects.create(
            employee=self.employee,
            action='check_in',
            success=True
        )

    def test_face_quality_check_creation(self):
        """Test FaceQualityCheck creation with default values"""
        quality_check = FaceQualityCheck.objects.create(
            biometric_log=self.biometric_log
        )
        
        self.assertEqual(quality_check.biometric_log, self.biometric_log)
        self.assertFalse(quality_check.face_detected)
        self.assertEqual(quality_check.face_count, 0)
        self.assertFalse(quality_check.eye_visibility)
        self.assertIsNotNone(quality_check.created_at)

    def test_face_quality_check_with_metrics(self):
        """Test FaceQualityCheck creation with quality metrics"""
        quality_check = FaceQualityCheck.objects.create(
            biometric_log=self.biometric_log,
            face_detected=True,
            face_count=1,
            brightness_score=0.75,
            blur_score=0.90,
            face_size_ratio=0.35,
            eye_visibility=True
        )
        
        self.assertTrue(quality_check.face_detected)
        self.assertEqual(quality_check.face_count, 1)
        self.assertEqual(quality_check.brightness_score, 0.75)
        self.assertEqual(quality_check.blur_score, 0.90)
        self.assertEqual(quality_check.face_size_ratio, 0.35)
        self.assertTrue(quality_check.eye_visibility)

    def test_face_quality_check_one_to_one_relationship(self):
        """Test one-to-one relationship with BiometricLog"""
        quality_check = FaceQualityCheck.objects.create(
            biometric_log=self.biometric_log,
            face_detected=True
        )
        
        # Test reverse relationship
        self.assertEqual(self.biometric_log.quality_check, quality_check)

    def test_face_quality_check_meta_attributes(self):
        """Test FaceQualityCheck meta attributes"""
        self.assertEqual(FaceQualityCheck._meta.db_table, "face_quality_checks")
        self.assertEqual(FaceQualityCheck._meta.verbose_name, "Face Quality Check")
        self.assertEqual(FaceQualityCheck._meta.verbose_name_plural, "Face Quality Checks")

    def test_face_quality_check_nullable_fields(self):
        """Test FaceQualityCheck nullable fields"""
        quality_check = FaceQualityCheck.objects.create(
            biometric_log=self.biometric_log,
            face_detected=False,
            brightness_score=None,
            blur_score=None,
            face_size_ratio=None
        )
        
        self.assertIsNone(quality_check.brightness_score)
        self.assertIsNone(quality_check.blur_score)
        self.assertIsNone(quality_check.face_size_ratio)


class BiometricModelsIntegrationTest(TestCase):
    """Integration tests for biometric models working together"""

    def setUp(self):
        """Set up test data"""
        self.user = User.objects.create_user(
            username='integrationuser',
            email='integration@example.com',
            password='testpass123'
        )
        self.employee = Employee.objects.create(
            user=self.user,
            first_name='Integration',
            last_name='Test',
            email='integration@example.com',
            employment_type='full_time',
            role='employee'
        )

    def test_full_biometric_workflow(self):
        """Test complete biometric workflow with all models"""
        # Create biometric profile
        profile = BiometricProfile.objects.create(
            employee=self.employee,
            embeddings_count=1,
            mongodb_id='test_mongo_id'
        )
        
        # Create successful check-in log
        check_in_log = BiometricLog.objects.create(
            employee=self.employee,
            action='check_in',
            confidence_score=0.92,
            success=True,
            processing_time_ms=850
        )
        
        # Create quality check for the log
        quality_check = FaceQualityCheck.objects.create(
            biometric_log=check_in_log,
            face_detected=True,
            face_count=1,
            brightness_score=0.8,
            blur_score=0.9,
            eye_visibility=True
        )
        
        # Verify relationships
        self.assertEqual(self.employee.biometric_profile, profile)
        self.assertIn(check_in_log, self.employee.biometric_logs.all())
        self.assertEqual(check_in_log.quality_check, quality_check)
        
        # Test __str__ methods
        self.assertIn('Integration Test', str(profile))
        self.assertIn('check_in - Integration Test', str(check_in_log))

    def test_failed_attempt_blocking_workflow(self):
        """Test failed attempt blocking workflow"""
        ip_address = '192.168.1.50'
        
        # Create multiple failed attempts
        attempt = BiometricAttempt.objects.create(ip_address=ip_address)
        
        # Create failed logs and increment attempts
        for i in range(3):
            BiometricLog.objects.create(
                action='failed',
                ip_address=ip_address,
                success=False,
                error_message='Face not recognized'
            )
            attempt.increment_attempts()
        
        # Should not be blocked yet (3 < 5)
        self.assertFalse(attempt.is_blocked())
        self.assertEqual(attempt.attempts_count, 3)
        
        # Add 2 more attempts to reach limit
        for i in range(2):
            BiometricLog.objects.create(
                action='failed',
                ip_address=ip_address,
                success=False
            )
            attempt.increment_attempts()
        
        # Should now be blocked
        self.assertTrue(attempt.is_blocked())
        self.assertEqual(attempt.attempts_count, 5)
        self.assertIsNotNone(attempt.blocked_until)
        
        # Reset attempts
        attempt.reset_attempts()
        self.assertFalse(attempt.is_blocked())
        self.assertEqual(attempt.attempts_count, 0)

    def test_employee_cascade_deletion(self):
        """Test that deleting employee cascades to biometric models"""
        profile = BiometricProfile.objects.create(employee=self.employee)
        log = BiometricLog.objects.create(employee=self.employee, action='registration')
        
        # Delete employee
        employee_id = self.employee.id
        self.employee.delete()
        
        # Verify cascade deletion
        self.assertFalse(BiometricProfile.objects.filter(employee_id=employee_id).exists())
        self.assertFalse(BiometricLog.objects.filter(employee_id=employee_id).exists())