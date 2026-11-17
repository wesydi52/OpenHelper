"""Пункт 2 плана: реакция на напоминание («сделано», «понял», «отложи») и дубль в Telegram через 15 минут.

Правила — из JARVIS_PLAN.md, раздел 3:
- «сделано» / «я уже позвонил» → закрыть дело (по смыслу, не только «готово»);
- «хорошо» / «понял» → услышал: дело остаётся активным, это напоминание не повторяется;
- «отложи на 10 минут», «напомни позже», «позже»/«потом» → 30 минут по умолчанию,
  «напомни ещё раз вечером» → 19:00;
- нет ответа на ПК 15 минут → продублировать в Telegram.
"""
from datetime import datetime, timedelta

import pytest

from jarvis.assistant import Assistant
from jarvis.config import Config
from jarvis.fmt import alert_text
from jarvis.scheduler import Scheduler
from jarvis.store import Store

NOW = datetime(2026, 11, 17, 10, 0)  # вторник


def D(*a):
    return datetime(*a)


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("JARVIS_TG_TOKEN", raising=False)
    clock = {"now": NOW}
    store = Store(tmp_path / "d.json")
    a = Assistant(Config(), store, now=lambda: clock["now"])
    return a, store, clock


def fire(store, title="Позвонить врачу", kind="reminder", when=NOW):
    """Создать элемент и «сработать» им в момент when — Джарвис ждёт реакции."""
    item = store.add_item(kind, title, when, [0])
    assert [i["id"] for i, _ in store.due(when)] == [item["id"]]
    return item


# ---------- состояние «ждём реакции» ----------
def test_alert_marks_item_as_awaiting_reaction(env):
    _, store, _ = env
    item = fire(store)
    assert [i["id"] for i in store.awaiting(NOW)] == [item["id"]]
    store.ack(item["id"])
    assert store.awaiting(NOW) == []


def test_awaiting_expires_after_window(env):
    _, store, _ = env
    fire(store)
    assert store.awaiting(NOW + timedelta(hours=2)) != []
    assert store.awaiting(NOW + timedelta(hours=2, minutes=1)) == []


# ---------- «сделано» ----------
@pytest.mark.parametrize("phrase", ["сделано", "готово", "Выполнено", "я сделал", "всё сделано", "закончил"])
def test_done_words(env, phrase):
    a, store, _ = env
    fire(store)
    assert a.handle(phrase) == "Отметил выполненным: Позвонить врачу."
    assert store.active() == [] and store.awaiting(NOW) == []


@pytest.mark.parametrize("phrase", ["я уже позвонил", "Я позвонила", "уже позвонил врачу", "позвонил"])
def test_done_by_meaning_verb_matches_title(env, phrase):
    a, store, _ = env
    fire(store)
    assert "Отметил выполненным: Позвонить врачу" in a.handle(phrase)
    assert store.active() == []


def test_done_unrelated_verb_asks_for_confirmation(env):
    a, store, _ = env
    fire(store)
    assert a.handle("я уже поел") == "Отметить «Позвонить врачу» выполненным, сэр?"
    assert "Отметил выполненным" in a.handle("да")
    assert store.active() == []


def test_done_unrelated_verb_declined(env):
    a, store, _ = env
    fire(store)
    a.handle("я уже поел")
    assert a.handle("нет") == "Хорошо, сэр."
    assert len(store.active()) == 1 and len(store.awaiting(NOW)) == 1


def test_long_chatter_is_not_treated_as_done(env):
    a, store, _ = env
    fire(store)
    assert "не расслышал" in a.handle("я вчера весь день гулял по городу")
    assert len(store.active()) == 1


def test_done_with_two_awaiting_matches_by_verb(env):
    a, store, _ = env
    fire(store, "Позвонить врачу")
    fire(store, "Купить хлеб")
    assert "Позвонить врачу" in a.handle("я уже позвонил")
    assert [i["title"] for i in store.active()] == ["Купить хлеб"]


def test_done_with_two_awaiting_asks_which(env):
    a, store, _ = env
    fire(store, "Позвонить врачу")
    fire(store, "Купить хлеб")
    q = a.handle("сделано")
    assert q.startswith("Какое именно отметить, сэр?") and "1. Позвонить врачу" in q and "2. Купить хлеб" in q
    assert "Купить хлеб" in a.handle("два")
    assert [i["title"] for i in store.active()] == ["Позвонить врачу"]


def test_done_for_task_with_deadline(env):
    a, store, _ = env
    fire(store, "Сдать отчёт", kind="task")
    assert "Сдать отчёт" in a.handle("сделано")


def test_done_without_awaiting_keeps_old_behaviour(env):
    a, store, _ = env
    store.add_item("task", "Купить хлеб", D(2026, 11, 20, 18, 0), [0])
    assert "Отметил выполненным: Купить хлеб" in a.handle("готово один")
    assert "Не нашёл" in a.handle("сделано")


def test_done_ignored_when_awaiting_is_stale(env):
    a, store, clock = env
    fire(store)
    clock["now"] = NOW + timedelta(hours=3)
    assert "Не нашёл" in a.handle("сделано")
    assert len(store.active()) == 1


# ---------- «хорошо» / «понял» ----------
@pytest.mark.parametrize("phrase", ["хорошо", "Понял", "понятно", "принято", "услышал", "ясно", "ок"])
def test_heard_keeps_item_active_and_silences_it(env, phrase):
    a, store, _ = env
    fire(store)
    assert a.handle(phrase) == "Принял, сэр. Дело остаётся в списке."
    assert len(store.active()) == 1 and store.awaiting(NOW) == []
    assert store.unacked(NOW + timedelta(minutes=30), 15) == []   # дубля в Telegram не будет


def test_heard_applies_to_all_awaiting(env):
    a, store, _ = env
    fire(store, "Позвонить врачу")
    fire(store, "Купить хлеб")
    a.handle("понял")
    assert store.awaiting(NOW) == []


def test_heard_word_without_awaiting_is_not_a_command(env):
    a, _, _ = env
    assert "не расслышал" in a.handle("хорошо")


# ---------- отложить ----------
@pytest.mark.parametrize("phrase,minutes", [
    ("отложи на 10 минут", 10),
    ("отложи на час", 60),
    ("отложи на полчаса", 30),
    ("отложи на пару часов", 150),
    ("отложи", 30),
    ("позже", 30),
    ("потом", 30),
    ("напомни позже", 30),
    ("напомни ещё раз позже", 30),
    ("напомни через 15 минут", 15),
    ("через 10 минут", 10),
])
def test_snooze_phrases(env, phrase, minutes):
    a, store, _ = env
    fire(store)
    reply = a.handle(phrase)
    until = NOW + timedelta(minutes=minutes)
    assert reply.startswith("Напомню") and "Позвонить врачу" in reply
    assert store.awaiting(NOW) == []
    assert store.due(until - timedelta(seconds=1)) == []
    assert [(i["title"], off) for i, off in store.due(until)] == [("Позвонить врачу", -1)]
    assert store.due(until + timedelta(hours=1)) == []   # один раз


def test_snooze_evening_is_19_00(env):
    a, store, _ = env
    fire(store)
    assert a.handle("напомни ещё раз вечером") == "Напомню сегодня в 19:00: Позвонить врачу."
    assert [off for _, off in store.due(D(2026, 11, 17, 19, 0))] == [-1]


def test_snooze_evening_after_19_goes_to_next_day(env):
    a, store, clock = env
    clock["now"] = D(2026, 11, 17, 20, 0)
    fire(store, when=clock["now"])
    assert a.handle("напомни ещё раз вечером") == "Напомню завтра в 19:00: Позвонить врачу."


def test_snooze_applies_to_all_awaiting(env):
    a, store, _ = env
    fire(store, "Позвонить врачу")
    fire(store, "Купить хлеб")
    reply = a.handle("позже")
    assert reply.startswith("Напомню") and store.awaiting(NOW) == []
    assert len(store.due(NOW + timedelta(minutes=30))) == 2


def test_new_reminder_with_text_is_not_a_snooze(env):
    a, store, _ = env
    fire(store)
    a.handle("напомни через час позвонить маме")
    titles = sorted(i["title"] for i in store.active())
    assert titles == ["Позвонить врачу", "Позвонить маме"]
    assert len(store.awaiting(NOW)) == 1   # врач по-прежнему ждёт реакции


def test_snooze_without_awaiting_is_not_a_command(env):
    a, store, _ = env
    assert "не расслышал" in a.handle("позже")
    assert "не расслышал" in a.handle("отложи на 10 минут")


def test_snooze_to_the_past_is_rejected(env):
    a, store, _ = env
    fire(store)
    assert "уже прошло" in a.handle("напомни в 9 утра сегодня")  # новая фраза, но время в прошлом
    assert len(store.awaiting(NOW)) == 1


def test_done_item_is_not_snoozed_back(env):
    a, store, _ = env
    fire(store)
    a.handle("отложи на 10 минут")
    a.handle("готово один")
    assert store.due(NOW + timedelta(hours=1)) == []


# ---------- реакция из Telegram засчитывается ----------
def test_reaction_from_telegram_counts(env):
    a, store, _ = env
    fire(store)
    assert "Отметил выполненным" in a.handle("сделано", source="telegram")
    fire(store, "Купить хлеб")
    assert a.handle("отложи на 10 минут", source="telegram").startswith("Напомню")


def test_pending_question_is_per_source(env):
    a, store, _ = env
    fire(store, "Позвонить врачу")
    fire(store, "Купить хлеб")
    a.handle("сделано")                       # вопрос «какое?» задан на ПК
    assert "не понял команду" in a.handle("два", source="telegram")   # в Telegram вопроса не было
    assert len(store.active()) == 2
    assert "Купить хлеб" in a.handle("два")   # а на ПК ответ принят


# ---------- повторное напоминание и текст ----------
def test_repeat_alert_text():
    item = {"kind": "reminder", "title": "Позвонить врачу", "when": "2026-11-17 10:00"}
    assert alert_text(item, -1, D(2026, 11, 17, 10, 30)) == "Повторяю: Позвонить врачу."
    assert alert_text(item, -1, D(2026, 11, 17, 19, 0)) == "Повторяю: Позвонить врачу."


# ---------- дубль в Telegram ----------
def make_scheduler(store, a=None, dup=15, tg=True):
    voice, tg_out = [], []
    s = Scheduler(store, voice.append, review=a.daily_review if a else None,
                  notify_tg=tg_out.append if tg else None, tg_dup_minutes=dup)
    return s, voice, tg_out


def test_duplicate_to_telegram_after_15_minutes_without_reaction(env):
    _, store, _ = env
    item = store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, voice, tg = make_scheduler(store)
    s.tick(NOW)
    assert voice == ["Напоминаю: Позвонить врачу."] and tg == []
    s.tick(NOW + timedelta(minutes=14, seconds=59))
    assert tg == []
    s.tick(NOW + timedelta(minutes=15))
    assert tg == ["Напоминание без ответа: Позвонить врачу (сработало в 10:00)."]
    s.tick(NOW + timedelta(minutes=45))
    assert len(tg) == 1        # один раз
    assert [i["id"] for i in store.awaiting(NOW)] == [item["id"]]   # реакции всё ещё ждём


def test_no_duplicate_if_owner_reacted_on_pc(env):
    a, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, _, tg = make_scheduler(store, a)
    s.tick(NOW)
    a.handle("понял")
    s.tick(NOW + timedelta(minutes=20))
    assert tg == []


def test_snooze_resets_duplicate_timer(env):
    a, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, voice, tg = make_scheduler(store, a)
    s.tick(NOW)
    a.handle("отложи на 10 минут")
    s.tick(NOW + timedelta(minutes=10))     # повтор на ПК
    assert voice[-1] == "Повторяю: Позвонить врачу."
    s.tick(NOW + timedelta(minutes=24))
    assert tg == []                          # от повтора ещё не прошло 15 минут
    s.tick(NOW + timedelta(minutes=25))
    assert len(tg) == 1


def test_no_duplicate_when_telegram_not_configured(env):
    _, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, voice, tg = make_scheduler(store, tg=False)
    s.tick(NOW)
    s.tick(NOW + timedelta(hours=1))
    assert len(voice) == 1 and tg == []


def test_no_duplicate_when_dup_disabled(env):
    _, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, _, tg = make_scheduler(store, dup=None)
    s.tick(NOW)
    s.tick(NOW + timedelta(hours=1))
    assert tg == []


def test_each_unacked_item_is_duplicated_separately(env):
    _, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    store.add_item("task", "Сдать отчёт", NOW + timedelta(minutes=5), [0])
    s, _, tg = make_scheduler(store)
    s.tick(NOW)
    s.tick(NOW + timedelta(minutes=5))
    s.tick(NOW + timedelta(minutes=15))
    s.tick(NOW + timedelta(minutes=20))
    assert len(tg) == 2 and "Позвонить врачу" in tg[0] and "Сдать отчёт" in tg[1]


def test_done_item_is_not_duplicated(env):
    a, store, _ = env
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    s, _, tg = make_scheduler(store, a)
    s.tick(NOW)
    a.handle("сделано")
    s.tick(NOW + timedelta(minutes=30))
    assert tg == []


def test_old_data_without_new_fields_still_works(tmp_path):
    """Файл данных от прошлой версии: у дел нет полей awaiting/snooze_until/tg_dup."""
    import json
    (tmp_path / "d.json").write_text(json.dumps({"notes": [], "meta": {}, "items": [
        {"id": "a1", "kind": "reminder", "title": "Старое", "when": "2026-11-17 10:00",
         "done": False, "alerts": [0], "fired": []}]}), encoding="utf-8")
    s = Store(tmp_path / "d.json")
    assert [i["title"] for i, _ in s.due(NOW)] == ["Старое"]
    assert [i["title"] for i in s.awaiting(NOW)] == ["Старое"]
    assert s.unacked(NOW + timedelta(minutes=15), 15)[0]["title"] == "Старое"


# ---------- закрыть дело можно и после «понял» (в течение окна) ----------
def test_done_by_meaning_after_heard(env):
    a, store, _ = env
    fire(store)
    a.handle("понял")
    assert "Отметил выполненным: Позвонить врачу" in a.handle("я уже позвонил")
    assert store.active() == []


def test_bare_done_after_heard_and_after_snooze_fire(env):
    a, store, clock = env
    fire(store)
    a.handle("хорошо")
    assert "Отметил выполненным" in a.handle("сделано")


def test_done_after_window_is_not_applied_even_if_heard(env):
    a, store, clock = env
    fire(store)
    a.handle("хорошо")
    clock["now"] = NOW + timedelta(hours=3)
    assert "не расслышал" in a.handle("я уже позвонил")
    assert len(store.active()) == 1


def test_heard_and_snooze_still_need_awaiting(env):
    a, store, clock = env
    fire(store)
    a.handle("хорошо")
    assert "не расслышал" in a.handle("понял")      # уже принято, реагировать не на что
    assert "не расслышал" in a.handle("позже")


def test_recent_is_not_affected_by_done_items(env):
    a, store, _ = env
    fire(store)
    a.handle("сделано")
    assert "не расслышал" in a.handle("я уже позвонил")
