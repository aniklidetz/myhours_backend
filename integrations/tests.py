from django.test import TestCase
from rest_framework.test import APITestCase
from rest_framework import status
from django.urls import reverse
from integrations.models import Holiday
from datetime import date
from unittest.mock import patch, MagicMock


class HolidayModelTest(TestCase):
    def test_holiday_creation(self):
        holiday = Holiday.objects.create(
            date=date(2025, 4, 14),
            name="Passover",
            is_holiday=True,
            is_shabbat=False
        )
        
        self.assertEqual(str(holiday), "Passover - 2025-04-14")
        self.assertTrue(holiday.is_holiday)
        self.assertFalse(holiday.is_shabbat)

    def test_shabbat_creation(self):
        shabbat = Holiday.objects.create(
            date=date(2025, 3, 15),
            name="Shabbat",
            is_holiday=False,
            is_shabbat=True
        )
        
        self.assertEqual(str(shabbat), "Shabbat - 2025-03-15")
        self.assertFalse(shabbat.is_holiday)
        self.assertTrue(shabbat.is_shabbat)


class HebcalServiceTest(TestCase):
    @patch('requests.get')
    def test_fetch_holidays(self, mock_get):
        # Mock response from Hebcal API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "items": [
                {
                    "title": "Shabbat",
                    "date": "2025-03-15"
                },
                {
                    "title": "Passover",
                    "date": "2025-04-14"
                }
            ]
        }
        mock_get.return_value = mock_response
        
        # Import here to avoid circular import issues
        from integrations.services.hebcal_service import HebcalService
        
        # Call the service method
        holidays = HebcalService.fetch_holidays(2025)
        
        # Assertions
        self.assertEqual(len(holidays), 2)
        self.assertEqual(holidays[0]["title"], "Shabbat")
        self.assertEqual(holidays[1]["title"], "Passover")


class SunriseSunsetServiceTest(TestCase):
    @patch('requests.get')
    def test_get_times(self, mock_get):
        # Mock response from Sunrise-Sunset API
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "OK",
            "results": {
                "sunrise": "2025-03-15T05:45:23+00:00",
                "sunset": "2025-03-15T17:52:14+00:00"
            }
        }
        mock_get.return_value = mock_response
        
        # Import here to avoid circular import issues
        from integrations.services.sunrise_sunset_service import SunriseSunsetService
        
        # Call the service method
        times = SunriseSunsetService.get_times(date(2025, 3, 15))
        
        # Assertions
        self.assertEqual(times["sunrise"], "2025-03-15T05:45:23+00:00")
        self.assertEqual(times["sunset"], "2025-03-15T17:52:14+00:00")  