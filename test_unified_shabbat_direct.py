#!/usr/bin/env python
"""
Test UnifiedShabbatService directly with proper Django setup
"""
import os
import sys
import django

# Setup Django before any imports
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'myhours.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

# Now we can import Django-dependent modules
from datetime import date
from integrations.services.unified_shabbat_service import get_shabbat_times

def test_unified_shabbat_service():
    """Test that UnifiedShabbatService works correctly"""
    try:
        # Test getting Shabbat times
        result = get_shabbat_times(date(2024, 6, 14))

        # Check required fields are present
        required_fields = {'shabbat_start', 'shabbat_end', 'friday_sunset', 'saturday_sunset', 'timezone'}
        assert required_fields.issubset(result.keys()), f"Missing fields. Got: {result.keys()}"

        # Check timezone is Israeli
        assert result['timezone'] == 'Asia/Jerusalem', f"Wrong timezone: {result['timezone']}"

        print("✅ UnifiedShabbatService works correctly!")
        print(f"   Shabbat start: {result['shabbat_start']}")
        print(f"   Shabbat end: {result['shabbat_end']}")
        print(f"   Friday sunset: {result['friday_sunset']}")
        print(f"   Saturday sunset: {result['saturday_sunset']}")
        print(f"   Timezone: {result['timezone']}")
        print(f"   Is estimated: {result['is_estimated']}")

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_unified_shabbat_service()
    sys.exit(0 if success else 1)