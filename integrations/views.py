from datetime import datetime

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Holiday
from .serializers import HolidaySerializer
from .services.hebcal_service import HebcalService
from .services.sunrise_sunset_service import SunriseSunsetService


class HolidayViewSet(viewsets.ReadOnlyModelViewSet):
    """API for managing holidays and Shabbats"""

    queryset = Holiday.objects.all().order_by("-date")
    serializer_class = HolidaySerializer
    permission_classes = [IsAuthenticated]

    @action(detail=False, methods=["get"])
    def sync(self, request):
        """
        Synchronizes holidays and Shabbats with the Hebcal API

        Parameters:
            year (int): Year for synchronization (defaults to the current year)
        """
        year = request.query_params.get("year")
        if year:
            try:
                year = int(year)
            except ValueError:
                return Response(
                    {"error": "Year must be a valid integer"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
        else:
            year = datetime.now().year

        created, updated = HebcalService.sync_holidays_to_db(year)

        return Response(
            {
                "message": f"Successfully synced holidays for year {year}",
                "created": created,
                "updated": updated,
            }
        )

    @action(detail=False, methods=["get"])
    def shabbat_times(self, request):
        """
        Retrieves Shabbat start and end times for a given date

        Parameters:
            date (str): Date in YYYY-MM-DD format (defaults to the nearest Friday)
            lat (float): Latitude (default: Jerusalem)
            lng (float): Longitude (default: Jerusalem)
        """
        date_str = request.query_params.get("date")
        lat = request.query_params.get("lat", 31.7683)
        lng = request.query_params.get("lng", 35.2137)

        try:
            if date_str:
                date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
            else:
                # Find the nearest Friday
                today = datetime.now().date()
                days_until_friday = (4 - today.weekday()) % 7
                date_obj = today.replace(day=today.day + days_until_friday)

            from .services.sunrise_sunset_service import SunriseSunsetService

            times = SunriseSunsetService.get_shabbat_times(
                date_obj, float(lat), float(lng)
            )

            if not times:
                return Response(
                    {"error": "Could not determine Shabbat times for the given date"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            return Response(times)

        except Exception as e:
            logger.exception("Integration API error")
            return Response(
                {"error": "Internal server error"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )
