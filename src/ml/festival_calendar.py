"""
Festival Calendar — Indian festivals ki approximate dates (2026) aur
helper functions jo batate hain ki koi date festival-window mein aati
hai ya nahi, aur agle N din mein kaunse festivals aa rahe hain.

⚠️ NOTE: Lunar-calendar-based festivals (Diwali, Holi, Eid, Raksha Bandhan,
etc.) ki exact date saal-dar-saal shift hoti hai aur official panchang se
confirm honi chahiye — yahan diye gaye dates best-effort approximate hain.
Deploy karne se pehle in dates ko current official calendar se verify/
update kar lena, especially agar Eid jaisa moon-sighting-dependent
festival ho.
"""

from datetime import date

# Har entry: {"name": ..., "date": date(...), "window_days": kitne din
# pehle/baad tak "festival window" maana jaaye (traffic/income surge
# aksar festival ke ek-do din pehle bhi shuru ho jaata hai)}
FESTIVALS_2026 = [
    {"name": "Makar Sankranti",   "date": date(2026, 1, 14),  "window_days": 1},
    {"name": "Republic Day",      "date": date(2026, 1, 26),  "window_days": 1},
    {"name": "Holi",              "date": date(2026, 3, 4),   "window_days": 2},
    {"name": "Eid al-Fitr",       "date": date(2026, 3, 20),  "window_days": 2},
    {"name": "Ram Navami",        "date": date(2026, 3, 27),  "window_days": 1},
    {"name": "Eid al-Adha",       "date": date(2026, 5, 27),  "window_days": 2},
    {"name": "Raksha Bandhan",    "date": date(2026, 8, 28),  "window_days": 1},
    {"name": "Independence Day",  "date": date(2026, 8, 15),  "window_days": 1},
    {"name": "Janmashtami",       "date": date(2026, 9, 4),   "window_days": 1},
    {"name": "Gandhi Jayanti",    "date": date(2026, 10, 2),  "window_days": 1},
    {"name": "Dussehra",          "date": date(2026, 10, 20), "window_days": 2},
    {"name": "Diwali",            "date": date(2026, 11, 8),  "window_days": 3},
    {"name": "Bhai Dooj",         "date": date(2026, 11, 10), "window_days": 1},
    {"name": "Christmas",         "date": date(2026, 12, 25), "window_days": 1},
]


def is_festival_window(d) -> tuple:
    """d: date object (ya pd.Timestamp/string jisme .date() ho ya
    ho hi date ho). Returns (is_festival: bool, name: str|None,
    days_from_festival: int|None) — days_from_festival negative hai agar
    d festival se pehle hai, positive agar baad me, 0 agar exact din hai."""
    if d is None:
        return False, None, None
    if hasattr(d, "date") and callable(getattr(d, "date")):
        d = d.date()
    if not isinstance(d, date):
        return False, None, None

    for fest in FESTIVALS_2026:
        window = fest.get("window_days", 1)
        delta = (d - fest["date"]).days
        if -window <= delta <= window:
            return True, fest["name"], delta
    return False, None, None


def get_upcoming_festivals(days_ahead: int = 20) -> list:
    """Aaj se lekar agle `days_ahead` din tak jo bhi festivals aa rahe
    hain, unki list deta hai (sabse jaldi wala pehle), har entry:
    {"name", "date", "days_away"}."""
    today = date.today()
    upcoming = []
    for fest in FESTIVALS_2026:
        days_away = (fest["date"] - today).days
        if 0 <= days_away <= days_ahead:
            upcoming.append({"name": fest["name"], "date": fest["date"], "days_away": days_away})
    upcoming.sort(key=lambda f: f["days_away"])
    return upcoming
