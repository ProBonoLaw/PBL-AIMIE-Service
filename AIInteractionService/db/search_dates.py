"""Calendar intervals for search filters and partially dated indexed records."""

import re
from calendar import month_abbr, month_name, monthrange
from datetime import date, datetime


def calendar_interval(value: str) -> tuple[date, date]:
    if not re.fullmatch(r"\d{4}(?:-\d{2}(?:-\d{2})?)?", value):
        raise ValueError("Dates must use YYYY, YYYY-MM, or YYYY-MM-DD.")
    parts = [int(part) for part in value.split("-")]
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    start = date(year, month, parts[2] if len(parts) == 3 else 1)
    end_month = month if len(parts) > 1 else 12
    end = date(year, end_month, parts[2] if len(parts) == 3 else monthrange(year, end_month)[1])
    return start, end


def normalize_date_filter(value: object, field: str) -> dict[str, str]:
    if not isinstance(value, dict) or not value or set(value) - {"from", "to"}:
        raise ValueError(f"{field} must contain from and/or to dates.")
    normalized = {}
    for key, bound in value.items():
        if not isinstance(bound, str):
            raise ValueError(f"{field}.{key} must be a date string.")
        calendar_interval(bound)
        normalized[key] = bound
    if "from" in normalized and "to" in normalized:
        if calendar_interval(normalized["from"])[0] > calendar_interval(normalized["to"])[1]:
            raise ValueError(f"{field}.from must not be after {field}.to.")
    return normalized


def indexed_date_interval(value: object) -> tuple[date, date] | None:
    try:
        if isinstance(value, datetime):
            return value.date(), value.date()
        if isinstance(value, str):
            return calendar_interval(value)
        if not isinstance(value, dict):
            return None
        year_text = str(value.get("year") or "").strip()
        if not re.fullmatch(r"\d{4}", year_text):
            return None
        year = int(year_text)
        month = str(value.get("month") or "").strip()
        day = str(value.get("day") or "").strip()
        if month:
            names = {name.lower(): number for names in (month_name, month_abbr)
                     for number, name in enumerate(names) if name} | {"sept": 9}
            month_number = int(month) if month.isdigit() else names[month.lower().rstrip(".")]
            return calendar_interval(f"{year:04d}-{month_number:02d}" + (f"-{int(day):02d}" if day else ""))
        if day:
            return None
        quarter = str(value.get("quarter") or "").lower().replace("quarter", "").replace("q", "").strip()
        if quarter:
            number = int(quarter)
            if not 1 <= number <= 4:
                return None
            start_month, end_month = (number - 1) * 3 + 1, number * 3
            return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1])
        season = str(value.get("season") or "").strip().lower()
        if season == "winter":
            return date(year, 12, 1), date(year + 1, 2, monthrange(year + 1, 2)[1])
        if season:
            start_month, end_month = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11), "autumn": (9, 11)}[season]
            return date(year, start_month, 1), date(year, end_month, monthrange(year, end_month)[1])
        return calendar_interval(year_text)
    except (ValueError, TypeError, KeyError, OverflowError):
        return None


def date_matches(value: object, bounds: dict[str, str]) -> bool:
    interval = indexed_date_interval(value)
    if interval is None:
        return False
    start, end = interval
    return (
        ("from" not in bounds or end >= calendar_interval(bounds["from"])[0])
        and ("to" not in bounds or start <= calendar_interval(bounds["to"])[1])
    )
