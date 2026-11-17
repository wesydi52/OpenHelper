"""Человекочитаемые тексты: даты, интервалы, тексты оповещений."""
from datetime import datetime, timedelta

from .ruparse import MONTHS
from .store import parse_ts


def plural(n: int, one: str, few: str, many: str) -> str:
    n = abs(n)
    if 11 <= n % 100 <= 14:
        return many
    return one if n % 10 == 1 else few if 2 <= n % 10 <= 4 else many


def human_delta(minutes: int) -> str:
    if minutes >= 1440:
        d = minutes // 1440
        return f"{d} {plural(d, 'день', 'дня', 'дней')}"
    if minutes >= 60:
        h = minutes // 60
        return f"{h} {plural(h, 'час', 'часа', 'часов')}"
    return f"{minutes} {plural(minutes, 'минута', 'минуты', 'минут')}"


def fmt_when(dt: datetime, now: datetime, with_time: bool = True) -> str:
    days = (dt.date() - now.date()).days
    day = {0: "сегодня", 1: "завтра", 2: "послезавтра"}.get(days) or f"{dt.day} {MONTHS[dt.month - 1]}"
    return f"{day} в {dt:%H:%M}" if with_time else day


def alert_text(item: dict, offset: int, now: datetime) -> str:
    when = parse_ts(item["when"])
    title = item["title"]
    if now - when > timedelta(minutes=5):
        return f"Пропущенное напоминание: {title}. Время было {fmt_when(when, now)}."
    if item["kind"] == "reminder":
        return f"Напоминаю: {title}."
    if offset == 0:
        return f"Срок пришёл: {title}."
    return f"Не забудьте: {title}. Срок {fmt_when(when, now)}, осталось {human_delta(offset)}."
