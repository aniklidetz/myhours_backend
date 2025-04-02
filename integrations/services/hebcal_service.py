import requests
import logging
from datetime import date, datetime, timedelta
from django.core.cache import cache
from integrations.models import Holiday
from .sunrise_sunset_service import SunriseSunsetService

logger = logging.getLogger(__name__)

class HebcalService:
    """Service for working with Hebcal API to retrieve information about Jewish holidays"""
    
    BASE_URL = "https://www.hebcal.com/hebcal"
    CACHE_KEY_PREFIX = "hebcal_holidays_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 30  # 30 days - holidays rarely change
    
    @classmethod
    def fetch_holidays(cls, year=None, month=None, use_cache=True):
        """
        Retrieves holiday and Shabbat information from the Hebcal API
        
        Args:
            year (int, optional): Year for the request. Defaults to the current year.
            month (int, optional): Month for the request. Defaults to all months.
            use_cache (bool): Whether to use caching. Defaults to True.
            
        Returns:
            list: List of holidays and Shabbats
        """
        if year is None:
            year = date.today().year
            
        # Generate cache key
        cache_key = f"{cls.CACHE_KEY_PREFIX}{year}"
        if month:
            cache_key += f"_{month}"
            
        # Check cache if enabled
        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"Using cached holiday data for {year}")
                return cached_data
                
        # Request parameters
        params = {
            "v": 1,
            "cfg": "json",
            "year": year,
            "ss": "on",   # Include Shabbats
            "c": "on",    # Use Gregorian calendar
            "maj": "on",  # Major holidays
            "min": "on",  # Minor holidays
            "nx": "on",   # Modern holidays
            "d": "on"     # Diaspora (galut) holidays
        }
        
        if month:
            params["month"] = month
            
        try:
            logger.info(f"Fetching holidays from Hebcal API for year {year}")
            response = requests.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            items = data.get("items", [])
            
            # Filter holidays
            holidays = [
                item for item in items 
                if (item.get('category') == 'holiday' and 
                    item.get('subcat') in ['major', 'minor'] and 
                    'Candle' not in item.get('title', ''))
            ]
            
            logger.info(f"Successfully retrieved {len(holidays)} holidays")
            
            # Cache results if enabled
            if use_cache and holidays:
                cache.set(cache_key, holidays, cls.CACHE_TIMEOUT)
                
            return holidays
            
        except Exception as e:
            logger.error(f"Error fetching holidays from Hebcal API: {e}")
            return []  # Return an empty list on failure
    
    @classmethod
    def generate_weekly_shabbats(cls, year, lat=31.7683, lng=35.2137):
        """Generates a list of weekly Shabbats for the year with precise start times"""
        shabbats = []
        start_date = date(year, 1, 1)
        end_date = date(year, 12, 31)
        
        current_date = start_date
        while current_date <= end_date:
            if current_date.weekday() == 4:  # Friday
                try:
                    shabbat_times = SunriseSunsetService.get_shabbat_times(current_date, lat, lng)
                    shabbats.append({
                        "title": "Shabbat",
                        "date": current_date.isoformat(),
                        "category": "holiday",
                        "subcat": "shabbat",
                        "start_time": shabbat_times['start'],
                        "end_time": shabbat_times['end']
                    })
                except Exception as e:
                    logger.error(f"Error generating Shabbat for {current_date}: {e}")
            
            current_date += timedelta(days=1)
        
        return shabbats
            
    @classmethod
    def sync_holidays_to_db(cls, year=None):
        """
        Synchronizes holidays and Shabbats with the database
        
        Args:
            year (int, optional): Year to synchronize. Defaults to the current year.
            
        Returns:
            tuple: (created_count, updated_count)
        """
        holidays = cls.fetch_holidays(year, use_cache=True)
        weekly_shabbats = cls.generate_weekly_shabbats(year)
        
        created_count = 0
        updated_count = 0
        
        # Special Shabbats
        special_shabbats = [
            holiday for holiday in holidays 
            if holiday.get('category') == 'holiday' and holiday.get('subcat') == 'shabbat'
        ]
        
        # Other holidays
        other_holidays = [
            holiday for holiday in holidays 
            if holiday.get('category') == 'holiday' and 
               holiday.get('subcat') in ['major', 'minor'] and 
               holiday.get('subcat') != 'shabbat'
        ]
             
        # Processing special Shabbats
        for holiday_data in special_shabbats:
            title = holiday_data.get("title")
            holiday_date_str = holiday_data.get("date")
            
            try:
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
                
                defaults = {
                    "name": title,
                    "is_holiday": True,
                    "is_shabbat": True,
                    "is_special_shabbat": True
                }
                
                holiday, created = Holiday.objects.update_or_create(
                    date=holiday_date,
                    defaults=defaults
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error syncing special Shabbat {title} on {holiday_date_str}: {e}")
   
        # Processing other holidays
        for holiday_data in other_holidays:
            title = holiday_data.get("title")
            holiday_date_str = holiday_data.get("date")
            
            try:
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
                
                defaults = {
                    "name": title,
                    "is_holiday": True,
                    "is_shabbat": False,
                    "is_special_shabbat": False
                }
                
                holiday, created = Holiday.objects.update_or_create(
                    date=holiday_date,
                    defaults=defaults
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error syncing holiday {title} on {holiday_date_str}: {e}")
        
        # Processing weekly Shabbats
        for holiday_data in weekly_shabbats:
            title = holiday_data.get("title")
            holiday_date_str = holiday_data.get("date")
            
            try:
                holiday_date = datetime.strptime(holiday_date_str, "%Y-%m-%d").date()
                
                defaults = {
                    "name": "Shabbat",
                    "is_holiday": False,
                    "is_shabbat": True,
                    "is_special_shabbat": False,
                    "start_time": datetime.fromisoformat(holiday_data["start_time"]) if holiday_data.get("start_time") else None,
                    "end_time": datetime.fromisoformat(holiday_data["end_time"]) if holiday_data.get("end_time") else None
                }
                
                holiday, created = Holiday.objects.update_or_create(
                    date=holiday_date,
                    defaults=defaults
                )
                
                if created:
                    created_count += 1
                else:
                    updated_count += 1
                    
            except Exception as e:
                logger.error(f"Error syncing weekly Shabbat on {holiday_date_str}: {e}")
        
        return created_count, updated_count