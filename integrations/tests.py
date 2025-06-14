# integrations/tests.py
from django.test import TestCase
from django.urls import reverse
from rest_framework import status
from unittest.mock import patch, MagicMock
from tests.base import BaseAPITestCase, UnauthenticatedAPITestCase
from integrations.models import Holiday
from integrations.services.hebcal_service import HebcalService
from datetime import date


class HolidayModelTest(TestCase):
    """Holiday model test"""
    
    def test_holiday_creation(self):
        """Test holiday creation"""
        holiday = Holiday.objects.create(
            date=date(2025, 9, 16),
            name="Rosh Hashanah",
            is_holiday=True,
            is_shabbat=False
        )
        
        self.assertEqual(holiday.name, "Rosh Hashanah")
        self.assertTrue(holiday.is_holiday)
        self.assertFalse(holiday.is_shabbat)


class HebcalServiceTest(TestCase):
    """HebcalService test"""
    
    @patch('integrations.services.hebcal_service.cache')
    @patch('integrations.services.hebcal_service.requests.get')
    def test_fetch_holidays_success(self, mock_get, mock_cache):
        """Test successful holiday fetching"""
        # Mock cache to return None (no cached data)
        mock_cache.get.return_value = None
        
        # Mock successful API response
        mock_response = MagicMock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Rosh Hashanah",
                    "date": "2025-09-16",
                    "category": "holiday",
                    "subcat": "major"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Test the service
        holidays = HebcalService.fetch_holidays(2025)
        
        # Verify results
        self.assertEqual(len(holidays), 1)
        self.assertEqual(holidays[0]['title'], "Rosh Hashanah")
        
        # Verify API was called
        mock_get.assert_called_once()
        
        # Verify cache was attempted to be set
        mock_cache.set.assert_called_once()
    
    @patch('integrations.services.hebcal_service.cache')
    def test_fetch_holidays_from_cache(self, mock_cache):
        """Test fetching holidays from cache"""
        # Mock cached data
        cached_holidays = [
            {
                "title": "Yom Kippur",
                "date": "2025-10-04",
                "category": "holiday",
                "subcat": "major"
            }
        ]
        mock_cache.get.return_value = cached_holidays
        
        # Test the service
        holidays = HebcalService.fetch_holidays(2025)
        
        # Verify cached data was returned
        self.assertEqual(holidays, cached_holidays)
        self.assertEqual(len(holidays), 1)
    
    @patch('integrations.services.hebcal_service.cache')
    @patch('integrations.services.hebcal_service.requests.get')
    def test_fetch_holidays_api_error(self, mock_get, mock_cache):
        """Test API error handling"""
        # Mock cache to return None (no cached data)
        mock_cache.get.return_value = None
        
        # Mock API error
        mock_get.side_effect = Exception("API Error")
        
        # Test the service
        holidays = HebcalService.fetch_holidays(2025, use_cache=False)
        
        # Should return empty list on error
        self.assertEqual(holidays, [])


class HolidayAPITest(BaseAPITestCase):
    """Holiday API test"""
    
    def setUp(self):
        super().setUp()
        
        # Create test holidays
        Holiday.objects.create(
            date=date(2025, 9, 16),
            name="Rosh Hashanah",
            is_holiday=True,
            is_shabbat=False
        )
        
        Holiday.objects.create(
            date=date(2025, 9, 20),
            name="Shabbat",
            is_holiday=False,
            is_shabbat=True
        )
    
    def test_list_holidays_authenticated(self):
        """Test holiday list retrieval with authentication"""
        url = reverse('holiday-list')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('results', response.data)
        self.assertGreaterEqual(len(response.data['results']), 2)
    
    @patch('integrations.services.hebcal_service.HebcalService.sync_holidays_to_db')
    def test_sync_holidays_authenticated(self, mock_sync):
        """Test holiday synchronization with authentication"""
        mock_sync.return_value = (5, 2)  # created, updated
        
        url = reverse('holiday-sync')
        
        response = self.client.get(url, {'year': 2025})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('message', response.data)
        self.assertEqual(response.data['created'], 5)
        self.assertEqual(response.data['updated'], 2)
        
        mock_sync.assert_called_once_with(2025)


class HolidayAPIUnauthenticatedTest(UnauthenticatedAPITestCase):
    """Holiday API test without authentication"""
    
    def test_list_holidays_unauthenticated(self):
        """Test holiday list retrieval without authentication"""
        url = reverse('holiday-list')
        
        response = self.client.get(url)
        
        # Holidays should require authentication in this setup
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_sync_holidays_unauthenticated(self):
        """Test holiday synchronization without authentication"""
        url = reverse('holiday-sync')
        
        response = self.client.get(url)
        
        # Sync should require authentication
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)