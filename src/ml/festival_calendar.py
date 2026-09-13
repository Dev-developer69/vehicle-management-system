"""
Festival Calendar — koi bhi API/internet call NAHI karta. Iske bajaye
Python ka `holidays` package use karta hai (pip install holidays) — ek
open-source, community-maintained library jisme India ke saare
holidays/festivals ki real (lunar-calendar-accurate) dates already
bundled hain, offline. Isliye na koi API key chahiye, na koi network
request — bas library installed honi chahiye.

Government/secular holidays (Republic Day, Independence Day, Gandhi
Jayanti, Ambedkar Jayanti, Good Friday) ko yahan FILTER OUT kiya gaya hai
kyunki wo "festival" nahi hain — bus ridership/income surge trigger nahi
karte jaise Diwali/Holi/Eid karte hain. Sirf religious/cultural festivals
rakhe gaye hain.

Setup: `pip install holidays` (requirements.txt me add kar dena — ek baar
ka kaam hai, phir kabhi touch nahi karna, na koi key manage karni hai).
"""

from datetime import date

try:
    import holidays as _holidays_lib
    _HOLIDAYS_LIB_AVAILABLE = True
except ImportError:
    _HOLIDAYS_LIB_AVAILABLE = False

import streamlit as st

# ✅ Yeh government/secular holidays hain, festival nahi — exclude karo
_EXCLUDE_KEYWORDS = {
    "republic day", "independence day", "gandhi", "ambedkar",
    "good friday", "labour day", "may day",
}

# Bade/multi-day festivals ke liye extra window (rush/income-surge kai din
# tak rehta hai — sirf ek din ka flag kaafi nahi hota inke liye)
_MULTI_DAY_WINDOWS = {
    "diwali": 3, "deepavali": 3, "holi": 2, "id-ul-fitr": 2, "id-ul-zuha": 2,
    "bakrid": 2, "eid": 2, "dussehra": 2, "durga puja": 2, "navratri": 1,
}

# ✅ STATIC FALLBACK — sirf tab use hota hai jab `holidays` library installed
# na ho (fresh environment me pip install hone se pehle). Best-effort dates.
FESTIVALS_FALLBACK_2026 = [
    {"name": "Holi",                "date": date(2026, 3, 4),   "window_days": 2},
    {"name": "Id-ul-Fitr",          "date": date(2026, 3, 20),  "window_days": 2},
    {"name": "Ram Navami",          "date": date(2026, 3, 27),  "window_days": 1},
    {"name": "Id-ul-Zuha (Bakrid)", "date": date(2026, 5, 27),  "window_days": 2},
    {"name": "Raksha Bandhan",      "date": date(2026, 8, 28),  "window_days": 1},
    {"name": "Janmashtami",         "date": date(2026, 9, 4),   "window_days": 1},
    {"name": "Dussehra",            "date": date(2026, 10, 20), "window_days": 2},
    {"name": "Diwali",              "date": date(2026, 11, 8),  "window_days": 3},
    {"name": "Christmas",           "date": date(2026, 12, 25), "window_days": 1},
]


def _infer_window_days(name: str) -> int:
    name_l = name.lower()
    for key, days in _MULTI_DAY_WINDOWS.items():
        if key in name_l:
            return days
    return 1


def _is_excluded(name: str) -> bool:
    name_l = name.lower()
    return any(k in name_l for k in _EXCLUDE_KEYWORDS)


@st.cache_data(ttl=86400, show_spinner=False)  # ✅ din me ek baar hi compute (offline hai, sasta hai, phir bhi cache)
def _get_festival_list() -> list:
    """`holidays` library se India ke festivals nikalta hai (is saal +
    agla saal), government holidays filter karke. Library available na
    ho to static fallback list deta hai."""
    if not _HOLIDAYS_LIB_AVAILABLE:
        return FESTIVALS_FALLBACK_2026

    today = date.today()
    try:
        in_holidays = _holidays_lib.India(years=[today.year, today.year + 1])
    except Exception:
        return FESTIVALS_FALLBACK_2026

    festivals = []
    for d, name in sorted(in_holidays.items()):
        name = name.strip()
        if not name or _is_excluded(name):
            continue
        festivals.append({"name": name, "date": d, "window_days": _infer_window_days(name)})

    return festivals if festivals else FESTIVALS_FALLBACK_2026


def is_festival_window(d) -> tuple:
    """d: date object (ya pd.Timestamp/string jisme .date() ho ya khud
    date ho). Returns (is_festival: bool, name: str|None,
    days_from_festival: int|None) — days_from_festival negative hai agar
    d festival se pehle hai, positive agar baad me, 0 agar exact din hai."""
    if d is None:
        return False, None, None
    if hasattr(d, "date") and callable(getattr(d, "date")):
        d = d.date()
    if not isinstance(d, date):
        return False, None, None

    for fest in _get_festival_list():
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
    for fest in _get_festival_list():
        days_away = (fest["date"] - today).days
        if 0 <= days_away <= days_ahead:
            upcoming.append({"name": fest["name"], "date": fest["date"], "days_away": days_away})
    upcoming.sort(key=lambda f: f["days_away"])
    return upcoming


# ✅ Backward-compat alias — kuch older code isi naam se import karta tha
FESTIVALS_2026 = FESTIVALS_FALLBACK_2026
