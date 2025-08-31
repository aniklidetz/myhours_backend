"""
Django management command to fix holiday status - mark only official Israeli holidays for premium pay
"""

from django.core.management.base import BaseCommand

from integrations.models import Holiday


class Command(BaseCommand):
    help = "Fix holiday status to mark only official Israeli holidays for premium pay"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would be changed without saving",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]

        # Official Israeli holidays that require premium pay (1.5x)
        # Based on Israeli labor law
        official_holidays = [
            "Rosh Hashana",  # Jewish New Year (2 days)
            "Yom Kippur",  # Day of Atonement
            "Sukkot",  # First and last days only
            "Simchat Torah",
            "Pesach",  # Passover - first and last days only
            "Shavuot",  # Pentecost
            "Tish'a B'Av",  # 9th of Av (some workplaces)
            "Yom HaAtzmaut",  # Independence Day
            "Yom HaShoah",  # Holocaust Remembrance Day (some workplaces)
            "Yom HaZikaron",  # Memorial Day (some workplaces)
        ]

        # Minor holidays that should NOT have premium pay
        minor_holidays = [
            "Pesach Sheni",
            "Tu BiShvat",
            "Tu B'Av",
            "Lag BaOmer",
            "Chanukah",  # Regular work days except for schools
            "Purim",  # Regular work day except in Jerusalem/walled cities
            "Shushan Purim",
            "Shabbat Shekalim",
            "Shabbat Zachor",
            "Shabbat Parah",
            "Shabbat HaChodesh",
            "Shabbat Shirah",
        ]

        self.stdout.write("=== Fixing Holiday Status ===\n")

        # First, remove premium pay from minor holidays
        removed_count = 0
        for holiday_name in minor_holidays:
            holidays = Holiday.objects.filter(
                name__icontains=holiday_name, is_holiday=True
            )

            if holidays.exists():
                self.stdout.write(f"Removing premium pay from {holiday_name}:")
                for h in holidays:
                    self.stdout.write(f"  - {h.date}: {h.name}")
                    if not dry_run:
                        h.is_holiday = False
                        h.save()
                    removed_count += 1

        # Fix Pesach and Sukkot - only first and last days are holidays
        self.stdout.write("\n=== Fixing Pesach (only first and last days) ===")
        pesach_chol_hamoed = Holiday.objects.filter(
            name__icontains="CH'M", is_holiday=True  # Chol HaMoed (intermediate days)
        )

        for h in pesach_chol_hamoed:
            self.stdout.write(f"  - Removing premium pay from {h.date}: {h.name}")
            if not dry_run:
                h.is_holiday = False
                h.save()
            removed_count += 1

        # Summary
        self.stdout.write(f"\n=== Summary ===")
        self.stdout.write(f"Removed premium pay from {removed_count} minor holidays")

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDRY RUN - no changes made"))
        else:
            self.stdout.write(self.style.SUCCESS("\nHoliday status fixed!"))

        # Show remaining holidays with premium pay
        self.stdout.write("\n=== Remaining holidays with premium pay ===")
        remaining = Holiday.objects.filter(is_holiday=True).order_by("date")[:20]
        for h in remaining:
            self.stdout.write(f"{h.date}: {h.name}")
