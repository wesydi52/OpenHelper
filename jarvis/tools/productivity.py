"""Заметки, напоминания, календарь."""
from datetime import datetime, timedelta

from ..store import TS, parse_dt
from .registry import S


def _fmt(i: dict) -> str:
    extra = f", {i['duration_min']} мин" if i["duration_min"] else ""
    return f"[{i['id']}] {i['when']}{extra} — {i['title']}"


def register(reg, cfg, store):
    @reg.add("add_note", "Сохранить заметку.", {"text": S("Текст"), "title": S("Заголовок")}, ["text"])
    def add_note(text: str, title: str = ""):
        n = store.add_note(text, title)
        return f"Заметка сохранена (id {n['id']})."

    @reg.add("list_notes", "Показать заметки, можно с поиском по тексту.", {"query": S("Что искать")})
    def list_notes(query: str = ""):
        ns = store.notes(query)
        return "\n".join(f"[{n['id']}] {n['created']} {n['title']}: {n['text']}" for n in ns) or "Заметок нет."

    @reg.add("delete_note", "Удалить заметку по id.", {"id": S("id заметки")}, ["id"])
    def delete_note(id: str):
        return "Удалено." if store.delete_note(id) else "Нет такой заметки."

    @reg.add("add_reminder",
             "Поставить напоминание. Время в формате 'ГГГГ-ММ-ДД ЧЧ:ММ' (локальное). "
             "Сам переводи относительные фразы вроде «через час» в точное время.",
             {"text": S("О чём напомнить"), "when": S("Когда, 'ГГГГ-ММ-ДД ЧЧ:ММ'")}, ["text", "when"])
    def add_reminder(text: str, when: str):
        i = store.add_item("reminder", text, parse_dt(when))
        return f"Напомню {i['when']}: {text} (id {i['id']})."

    @reg.add("add_event", "Добавить событие в календарь с предварительным напоминанием.",
             {"title": S("Название"), "start": S("Начало, 'ГГГГ-ММ-ДД ЧЧ:ММ'"),
              "duration_min": S("Длительность в минутах", "integer"),
              "remind_before_min": S("За сколько минут напомнить", "integer")}, ["title", "start"])
    def add_event(title: str, start: str, duration_min: int = 60, remind_before_min: int = 10):
        i = store.add_item("event", title, parse_dt(start), duration_min, remind_before_min)
        return f"Событие добавлено (id {i['id']}): {_fmt(i)}"

    @reg.add("list_agenda", "Показать календарь и напоминания на ближайшие дни.",
             {"days": S("На сколько дней вперёд (по умолчанию 7)", "integer")})
    def list_agenda(days: int = 7):
        now = datetime.now()
        items = store.items(start=now - timedelta(hours=1), end=now + timedelta(days=days))
        return "\n".join(f"{'событие' if i['kind'] == 'event' else 'напоминание'} {_fmt(i)}"
                         for i in items) or "На этот период ничего нет."

    @reg.add("delete_agenda_item", "Удалить событие или напоминание по id.", {"id": S("id")}, ["id"])
    def delete_item(id: str):
        return "Удалено." if store.delete_item(id) else "Нет такого элемента."

    @reg.add("get_datetime", "Текущая дата и время.")
    def get_datetime():
        return datetime.now().strftime(TS + " (%A)")
