"""
Configuration for official Israeli holidays that require premium pay (1.5x)
Based on Israeli labor law
"""

# Official holidays in Israel that require premium pay
OFFICIAL_HOLIDAYS_WITH_PREMIUM_PAY = [
    # Rosh Hashana (2 days)
    "Rosh Hashana",
    "Rosh Hashana II",
    # Yom Kippur
    "Yom Kippur",
    # Sukkot (first day only)
    "Sukkot I",
    # Shmini Atzeret/Simchat Torah
    "Shmini Atzeret",
    "Simchat Torah",
    # Pesach (first and last days only)
    "Pesach I",
    "Pesach VII",
    "Pesach VIII",
    # Shavuot
    "Shavuot",
    # Independence Day
    "Yom HaAtzmaut",
    "Yom Ha'atzmaut",
    # Tish'a B'Av (optional - depends on workplace)
    # Can be commented out if not observed
    # "Tish'a B'Av",
]

# Keywords that indicate non-official holidays
NON_OFFICIAL_HOLIDAY_KEYWORDS = [
    "Erev",  # Eve of holiday
    "CH'M",  # Chol HaMoed (intermediate days)
    "(CH",  # Another format for Chol HaMoed
    "Sheni",  # Second Passover
    "Tu B",  # Tu BiShvat, Tu B'Av
    "Lag",  # Lag BaOmer
    "Chanukah",
    "Purim",
    "Shushan",
    "Shabbat Shekalim",
    "Shabbat Zachor",
    "Shabbat Parah",
    "Shabbat HaChodesh",
    "Shabbat Shirah",
    "Shabbat HaGadol",
    "Shabbat Chazon",
    "Shabbat Nachamu",
    "Leil Selichot",
    "Tzom",  # Fast days
    "Ta'anit",  # Fast days
    "Zikaron",  # Memorial Day
    "HaShoah",  # Holocaust Day
    "LaBehemot",  # Rosh Hashana for animals
    "Hoshana Raba",  # Part of Sukkot but not official holiday
]


def is_official_holiday(holiday_name):
    """
    Check if a holiday requires premium pay according to Israeli labor law

    Args:
        holiday_name (str): Name of the holiday

    Returns:
        bool: True if holiday requires premium pay, False otherwise
    """
    # First check if it contains any non-official keywords
    for keyword in NON_OFFICIAL_HOLIDAY_KEYWORDS:
        if keyword in holiday_name:
            return False

    # Then check if it's in the official list
    for official in OFFICIAL_HOLIDAYS_WITH_PREMIUM_PAY:
        if official in holiday_name or holiday_name in official:
            return True

    return False
