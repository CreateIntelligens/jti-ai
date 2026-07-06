from datetime import datetime, timedelta, timezone

_UTC8 = timezone(timedelta(hours=8), "UTC+8")
_WEEKDAYS_EN = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
_WEEKDAYS_ZH = ("星期一", "星期二", "星期三", "星期四", "星期五", "星期六", "星期日")

DATE_REASONING_HINT_ZH = (
    "使用這個日期時間判斷今天、目前日期、星期幾、現在時間或時區；"
    "例如使用者提到「今天要掛號」或其他今天/明天相關問題時，先依此理解時間上下文。"
)
DATE_REASONING_HINT_EN = (
    "Use this date/time to interpret today, the current date, the weekday, "
    "the current time, or the timezone; for example, when the user says "
    "they want to book an appointment today or asks about today/tomorrow, "
    "ground the time context in this value."
)


def _format_day(value: datetime, language: str) -> str:
    weekdays = _WEEKDAYS_EN if language == "en" else _WEEKDAYS_ZH
    return f"{value:%Y-%m-%d} {weekdays[value.weekday()]}"


def format_current_utc8_datetime(language: str) -> str:
    now = datetime.now(_UTC8)
    yesterday = now - timedelta(days=1)
    tomorrow = now + timedelta(days=1)
    current = f"{_format_day(now, language)} {now:%H:%M} UTC+8"
    if language == "en":
        return (
            f"{current}\n"
            f"Date reference: Yesterday was {_format_day(yesterday, language)}; "
            f"Today is {_format_day(now, language)}; "
            f"Tomorrow is {_format_day(tomorrow, language)}."
        )
    return (
        f"{current}\n"
        f"日期換算：昨天是{_format_day(yesterday, language)}；"
        f"今天是{_format_day(now, language)}；"
        f"明天是{_format_day(tomorrow, language)}。"
    )
