"""Пункт 1 плана: расплывчатое время, «добавь в дела», «не понял», журнал нераспознанного.

Фразы взяты из JARVIS_PLAN.md (разделы 2a и 3) — это слова владельца.
"""
from datetime import datetime, timedelta

import pytest

from jarvis.assistant import Assistant
from jarvis.config import Config
from jarvis.ruparse import parse_when, resolve_ask
from jarvis.scheduler import Scheduler
from jarvis.store import Store

NOW = datetime(2026, 11, 17, 10, 0)  # вторник


def D(*a):
    return datetime(*a)


# ---------- разбор расплывчатого времени ----------
@pytest.mark.parametrize("text,task,dt,has_time", [
    ("позвонить в обед", "позвонить", D(2026, 11, 17, 13, 0), True),
    ("позвонить после обеда", "позвонить", D(2026, 11, 17, 15, 0), True),
    ("позвонить под вечер", "позвонить", D(2026, 11, 17, 17, 0), True),
    ("завтра в обед созвон", "созвон", D(2026, 11, 18, 13, 0), True),
    ("через пару часов выпить воду", "выпить воду", D(2026, 11, 17, 12, 30), True),
    ("через минутку выключить плиту", "выключить плиту", D(2026, 11, 17, 10, 1), True),
    ("через пару минут чай", "чай", D(2026, 11, 17, 10, 2), True),
    ("через пару дней позвонить", "позвонить", D(2026, 11, 19), False),
    ("в начале месяца оплатить аренду", "оплатить аренду", D(2026, 12, 1), False),
    ("на следующей неделе в среду врач", "врач", D(2026, 11, 25), False),
    ("на следующей неделе в среду в 10 врач", "врач", D(2026, 11, 25, 10, 0), True),
])
def test_vague_time(text, task, dt, has_time):
    p = parse_when(text, NOW)
    assert (p.text, p.dt, p.has_time, p.ask) == (task, dt, has_time, None)


def test_start_of_month_on_first_goes_to_next_month():
    p = parse_when("в начале месяца оплатить", D(2026, 12, 1, 9, 0))
    assert p.dt == D(2027, 1, 1)


@pytest.mark.parametrize("text,task,ask", [
    ("позвонить маме в выходные", "позвонить маме", "weekend"),
    ("позвонить маме на выходных", "позвонить маме", "weekend"),
    ("сделать это на следующей неделе", "сделать это", "next_week_day"),
    ("сдать отчёт в конце месяца", "сдать отчёт", "month_day"),
    ("сдать отчёт до конца месяца", "сдать отчёт", "month_day"),
    ("заплатить в этом месяце", "заплатить", "month_day"),
])
def test_needs_clarification(text, task, ask):
    p = parse_when(text, NOW)
    assert (p.text, p.dt, p.ask) == (task, None, ask)


def test_weekend_keeps_time_from_phrase():
    p = parse_when("позвонить маме в выходные в 10", NOW)
    assert p.ask == "weekend" and p.dt is None and p.tm.hour == 10 and p.has_time is False
    assert p.text == "позвонить маме"


def test_explicit_date_wins_over_ask():
    p = parse_when("сдать 25 ноября в конце месяца", NOW)
    assert p.ask is None and p.dt == D(2026, 11, 25)


@pytest.mark.parametrize("kind,answer,expected,has_time", [
    ("weekend", "в субботу", D(2026, 11, 21), False),
    ("weekend", "воскресенье в 10", D(2026, 11, 22, 10, 0), True),
    ("next_week_day", "в среду", D(2026, 11, 25), False),
    ("next_week_day", "в пятницу вечером", D(2026, 11, 27, 19, 0), True),
    ("month_day", "28", D(2026, 11, 28), False),
    ("month_day", "двадцать восьмого", D(2026, 11, 28), False),
    ("month_day", "30 числа", D(2026, 11, 30), False),
    ("month_day", "5", D(2026, 12, 5), False),        # в этом месяце уже прошло
    ("month_day", "31", D(2026, 12, 31), False),      # в ноябре нет 31-го
])
def test_resolve_ask(kind, answer, expected, has_time):
    r = resolve_ask(kind, answer, NOW)
    assert (r.dt, r.has_time) == (expected, has_time)


@pytest.mark.parametrize("kind,answer", [
    ("weekend", "в понедельник"), ("weekend", "привет"),
    ("next_week_day", "завтра"), ("month_day", "бла бла"), ("month_day", "35"),
])
def test_resolve_ask_rejects_non_answers(kind, answer):
    assert resolve_ask(kind, answer, NOW) is None


def test_resolve_ask_uses_time_from_original_phrase():
    p = parse_when("в выходные в 10 позвонить", NOW)
    r = resolve_ask("weekend", "в субботу", NOW, tm=p.tm)
    assert r.dt == D(2026, 11, 21, 10, 0) and r.has_time


# ---------- ассистент ----------
@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.delenv("JARVIS_TG_TOKEN", raising=False)
    clock = {"now": NOW}
    store = Store(tmp_path / "d.json")
    a = Assistant(Config(), store, now=lambda: clock["now"])
    return a, store, clock


@pytest.mark.parametrize("phrase,kind", [
    ("Напомни завтра в 10 позвонить врачу", "reminder"),
    ("Напомни, что мне надо позвонить врачу завтра в 10 утра", "reminder"),
    ("Запомни, что завтра в 10 утра нужно позвонить врачу", "task"),
    ("Добавь в дела позвонить врачу на завтра в 10", "task"),
    ("запиши в дела позвонить врачу на завтра в 10", "task"),
    ("добавь в задачи позвонить врачу на завтра в 10", "task"),
])
def test_owner_phrases_for_doctor(env, phrase, kind):
    a, store, _ = env
    a.handle(phrase)
    item = store.active()[0]
    assert (item["kind"], item["title"], item["when"]) == (kind, "Позвонить врачу", "2026-11-18 10:00")


def test_remind_at_lunch_and_in_a_couple_of_hours(env):
    a, store, _ = env
    a.handle("напомни в обед позвонить")
    a.handle("напомни через пару часов выпить воду")
    whens = {i["title"]: i["when"] for i in store.active()}
    assert whens == {"Позвонить": "2026-11-17 13:00", "Выпить воду": "2026-11-17 12:30"}


def test_weekend_reminder_asks_with_variants_and_time(env):
    a, store, _ = env
    q = a.handle("напомни в выходные позвонить маме")
    assert q == "В субботу или в воскресенье, сэр, и во сколько?"
    assert "Напомню 21 ноября в 10:00" in a.handle("в субботу в 10")
    assert store.active()[0]["when"] == "2026-11-21 10:00"


def test_weekend_with_time_in_phrase_asks_only_day(env):
    a, store, _ = env
    assert a.handle("напомни в выходные в 10 позвонить маме") == "В субботу или в воскресенье, сэр?"
    a.handle("воскресенье")
    assert store.active()[0]["when"] == "2026-11-22 10:00"


def test_weekend_day_without_time_asks_time_for_reminder(env):
    a, store, _ = env
    a.handle("напомни в выходные позвонить маме")
    assert a.handle("в субботу") == "Во сколько, сэр?"
    a.handle("в 9")
    assert store.active()[0]["when"] == "2026-11-21 09:00"


def test_weekend_task_without_time_gets_default_evening(env):
    a, store, _ = env
    a.handle("запомни что надо сдать отчёт в выходные")
    a.handle("в воскресенье")
    assert store.active()[0]["when"] == "2026-11-22 18:00"


def test_next_week_asks_day_then_time(env):
    a, store, _ = env
    assert a.handle("напомни на следующей неделе позвонить в банк") == "Какого дня недели, сэр?"
    assert a.handle("в среду") == "Во сколько, сэр?"
    a.handle("в 10")
    assert store.active()[0]["when"] == "2026-11-25 10:00"


@pytest.mark.parametrize("phrase", [
    "запомни что надо заплатить за свет в конце месяца",
    "запомни что надо заплатить за свет в этом месяце",
])
def test_month_phrases_ask_day_of_month(env, phrase):
    a, store, _ = env
    assert a.handle(phrase) == "Какого числа, сэр?"
    a.handle("двадцать восьмого")
    assert store.active()[0]["when"] == "2026-11-28 18:00"


def test_open_question_when_data_missing_uses_address(env):
    a, _, _ = env
    assert a.handle("напомни полить цветы") == "Когда напомнить, сэр?"
    a.handle("отмена")
    assert a.handle("напомни завтра в 9 утра") == "О чём напомнить, сэр?"


def test_non_answer_falls_through_to_normal_command(env):
    a, store, _ = env
    a.handle("напомни в выходные позвонить маме")
    assert a.handle("который час") == "Сейчас 10:00."
    assert store.active() == []


def test_pending_question_expires(env):
    a, store, clock = env
    a.handle("напомни в выходные позвонить маме")
    clock["now"] = NOW + timedelta(minutes=5)
    assert "не расслышал" in a.handle("в субботу в 10")
    assert store.active() == []


def test_custom_address(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_ADDRESS", "Алексей")
    a = Assistant(Config(), Store(tmp_path / "d.json"), now=lambda: NOW)
    assert a.handle("напомни полить цветы") == "Когда напомнить, Алексей?"


# ---------- «не понял» ----------
def test_not_understood_asks_twice_then_gives_up_and_logs(env):
    a, store, _ = env
    assert a.handle("абракадабра") == "Прошу прощения, сэр, я не расслышал. Не могли бы вы повторить?"
    assert "не расслышал" in a.handle("абракадабра два")
    third = a.handle("абракадабра три")
    assert "записал фразу для разбора" in third and "не расслышал" not in third
    assert "Telegram" not in third  # бот не настроен — не предлагаем
    assert [x["text"] for x in store.unrecognized()] == ["абракадабра", "абракадабра два", "абракадабра три"]
    assert "не расслышал" in a.handle("снова")  # счётчик сброшен


def test_give_up_suggests_telegram_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_TG_TOKEN", "t")
    a = Assistant(Config(), Store(tmp_path / "d.json"), now=lambda: NOW)
    for _ in range(2):
        a.handle("бла")
    assert "написать её мне в Telegram" in a.handle("бла")


def test_success_resets_retry_counter(env):
    a, _, _ = env
    a.handle("абра")
    a.handle("абра")
    assert a.handle("который час") == "Сейчас 10:00."
    assert "не расслышал" in a.handle("абра")  # снова первая попытка, а не сдача


def test_telegram_wording_and_separate_counters(env):
    a, _, _ = env
    msg = a.handle("бла", source="telegram")
    assert "я не понял команду" in msg and "расслышал" not in msg
    assert "не расслышал" in a.handle("бла")  # у ПК свой счётчик
    a.handle("бла", source="telegram")
    last = a.handle("бла", source="telegram")
    assert "записал фразу для разбора" in last and "Telegram" not in last


def test_help_and_known_commands_are_not_logged(env):
    a, store, _ = env
    a.handle("что ты умеешь")
    a.handle("который час")
    assert store.unrecognized() == []


# ---------- журнал ----------
def test_show_unrecognized_lists_then_marks_reviewed(env):
    a, store, _ = env
    assert a.handle("покажи непонятные фразы") == "Непонятных фраз нет, сэр."
    a.handle("абракадабра")
    a.handle("тарабарщина")
    shown = a.handle("покажи непонятные фразы")
    assert "Непонятных фраз: 2" in shown and "абракадабра" in shown and "тарабарщина" in shown
    assert a.handle("покажи непонятные фразы") == "Непонятных фраз нет, сэр."
    assert len(store.unrecognized(only_new=False)) == 2  # данные остаются для разбора


def test_clear_unrecognized(env):
    a, store, _ = env
    a.handle("абракадабра")
    assert "очистил" in a.handle("очисти журнал непонятных фраз").lower()
    assert store.unrecognized(only_new=False) == []


def test_daily_review_prompt_once_and_answer_yes(env):
    a, store, clock = env
    a.handle("абракадабра")
    a.handle("тарабарщина")
    assert a.daily_review(D(2026, 11, 17, 19, 59)) is None
    voice, tg = a.daily_review(D(2026, 11, 17, 20, 1))
    assert voice == "Накопилось 2 непонятные фразы, сэр. Разберём?"
    assert "абракадабра" in tg and "тарабарщина" in tg
    assert a.daily_review(D(2026, 11, 17, 21, 0)) is None   # один раз в день
    assert "абракадабра" in a.handle("да, разберём")
    assert store.unrecognized() == []


def test_daily_review_answer_no_and_next_day(env):
    a, store, _ = env
    a.handle("абракадабра")
    assert a.daily_review(D(2026, 11, 17, 20, 5))
    assert a.handle("нет") == "Хорошо, сэр."
    assert len(store.unrecognized()) == 1                   # не показано — не потеряно
    voice, _ = a.daily_review(D(2026, 11, 18, 20, 5))
    assert voice == "Накопилась 1 непонятная фраза, сэр. Разберём?"


def test_daily_review_silent_when_nothing_to_review(env):
    a, _, _ = env
    assert a.daily_review(D(2026, 11, 17, 21, 0)) is None


def test_daily_review_skipped_while_dialog_is_open(env):
    a, _, _ = env
    a.handle("абракадабра")
    a.handle("напомни в выходные позвонить маме")  # открытый вопрос
    assert a.daily_review(D(2026, 11, 17, 20, 5)) is None


def test_scheduler_sends_review_to_voice_and_telegram_list(env):
    a, store, _ = env
    a.handle("абракадабра")
    voice, tg = [], []
    s = Scheduler(store, voice.append, review=a.daily_review, notify_tg=tg.append)
    s.tick(D(2026, 11, 17, 20, 1))
    s.tick(D(2026, 11, 17, 20, 2))
    assert len(voice) == 1 and "Разберём?" in voice[0]
    assert len(tg) == 1 and "абракадабра" in tg[0]


def test_unrecognized_log_is_capped(tmp_path):
    s = Store(tmp_path / "d.json")
    for i in range(1100):
        s.log_unrecognized(f"фраза {i}", "local", NOW)
    texts = [x["text"] for x in s.unrecognized(only_new=False)]
    assert len(texts) == 1000 and texts[-1] == "фраза 1099" and texts[0] == "фраза 100"
