import requests
import logging
from datetime import date, datetime, timedelta
from django.core.cache import cache
from integrations.models import Holiday
from .sunrise_sunset_service import SunriseSunsetService
from integrations.config.israeli_holidays import is_official_holiday
from .israeli_holidays_service import IsraeliHolidaysService

logger = logging.getLogger(__name__)

class HebcalService:
    """
    Service for working with Hebcal API to retrieve information about Jewish holidays.
    
    Features automatic synchronization on app startup with 7-day caching to prevent
    excessive API calls. Manual sync can be forced using: python manage.py sync_holidays --force
    """
    
    BASE_URL = "https://www.hebcal.com/hebcal"
    CACHE_KEY_PREFIX = "hebcal_holidays_"
    CACHE_TIMEOUT = 60 * 60 * 24 * 7  # 7 days as suggested by user
    
    @classmethod
    def _parse_items(cls, raw, year):
        """Parse and filter holiday items by year and category"""
        items = [
            item for item in raw.get("items", [])
            if item.get("category") == "holiday" and item["date"].startswith(str(year))
        ]
        # Debug: log filtered count
        if len(raw.get("items", [])) != len(items):
            logger.debug(f"Filtered {len(raw.get('items', []))} → {len(items)} items for year {year}")
        return items
    
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
            "i": "on"     # Israel holidays (not diaspora)
        }
        
        if month:
            params["month"] = month
            
        try:
            logger.info(f"Fetching holidays from Hebcal API for year {year}")
            response = requests.get(cls.BASE_URL, params=params)
            response.raise_for_status()
            
            data = response.json()
            
            # Use _parse_items for filtering
            holidays = cls._parse_items(data, year)
            
            logger.info(f"Successfully retrieved {len(holidays)} holidays")
            
            # Cache results if enabled (cache even empty results to avoid repeated API calls)
            if use_cache:
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
    def sync_holidays_to_db(cls, year=None, include_weekly_shabbats=True):
        """
        Synchronizes holidays and Shabbats with the database
        
        Args:
            year (int, optional): Year to synchronize. Defaults to the current year.
            include_weekly_shabbats (bool): Whether to include weekly Shabbats. Defaults to True.
            
        Returns:
            tuple: (created_count, updated_count)
        """
        holidays = cls.fetch_holidays(year, use_cache=True)
        weekly_shabbats = cls.generate_weekly_shabbats(year) if include_weekly_shabbats else []
        
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
               holiday.get('subcat') in ['major', 'minor', 'modern'] and 
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
                    "is_holiday": False,  # Special Shabbats are not official holidays
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
                
                # Check if this is an official holiday requiring premium pay
                requires_premium_pay = is_official_holiday(title)
                
                defaults = {
                    "name": title,
                    "is_holiday": requires_premium_pay,  # Only official holidays get premium pay
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
        
        # Add Israeli national holidays (like Independence Day)
        try:
            nat_created, nat_updated = IsraeliHolidaysService.sync_national_holidays(year)
            created_count += nat_created
            updated_count += nat_updated
        except Exception as e:
            logger.error(f"Error syncing Israeli national holidays: {e}")
        
        return created_count, updated_count
    
    @classmethod
    def get_holiday_name(cls, holiday_date):
        """
        Get the name of a holiday for a specific date
        
        Args:
            holiday_date (date): The date to check for holiday
            
        Returns:
            str or None: Holiday name if found, None otherwise
        """
        try:
            # Check database first
            holiday = Holiday.objects.filter(date=holiday_date, is_holiday=True).first()
            if holiday:
                return holiday.name
            
            # Fallback: check API data (use year-level cache for consistency)
            year = holiday_date.year
            holidays = cls.fetch_holidays(year, use_cache=True)
            
            for holiday_data in holidays:
                try:
                    api_date = datetime.strptime(holiday_data.get("date"), "%Y-%m-%d").date()
                    if api_date == holiday_date:
                        title = holiday_data.get("title", "")
                        # Only return the name if it's an official holiday
                        if is_official_holiday(title):
                            return title
                except (ValueError, TypeError):
                    continue
                    
            return None
            
        except Exception as e:
            logger.error(f"Error getting holiday name for {holiday_date}: {e}")
            return None
    
    @classmethod  
    def is_holiday(cls, check_date):
        """
        Check if a specific date is a holiday
        
        Args:
            check_date (date): The date to check
            
        Returns:
            bool: True if the date is a holiday, False otherwise
        """
        try:
            # Check database first
            holiday = Holiday.objects.filter(date=check_date, is_holiday=True).exists()
            if holiday:
                return True
            
            # Fallback: check API data (use year-level cache for consistency)
            year = check_date.year
            holidays = cls.fetch_holidays(year, use_cache=True)
            
            for holiday_data in holidays:
                try:
                    api_date = datetime.strptime(holiday_data.get("date"), "%Y-%m-%d").date()
                    if api_date == check_date:
                        # Check if this holiday requires premium pay
                        title = holiday_data.get("title", "")
                        return is_official_holiday(title)
                except (ValueError, TypeError):
                    continue
                    
            return False
            
        except Exception as e:
            logger.error(f"Error checking if {check_date} is holiday: {e}")
            return False