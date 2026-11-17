from datetime import datetime, timedelta

import pytest

from jarvis.assistant import Assistant
from jarvis.config import Config
from jarvis.fmt import alert_text
from jarvis.ruparse import parse_when
from jarvis.scheduler import Scheduler
from jarvis.store import Store
from jarvis.telegram_bot import TelegramBot
from jarvis.voice import strip_wake_word

NOW = datetime(2026, 11, 17, 10, 0)  # вторник


def D(*a):
    return datetime(*a)


@pytest.mark.parametrize("text,task,dt,has_time", [
    ("позвонить маме завтра в 18:00", "позвонить маме", D(2026, 11, 18, 18, 0), True),
    ("купить хлеб до пятницы", "купить хлеб", D(2026, 11, 20), False),
    ("через два часа выключить плиту", "выключить плиту", D(2026, 11, 17, 12, 0), True),
    ("в понедельник в 10 встреча", "встреча", D(2026, 11, 23, 10, 0), True),
    ("сдать отчёт до 25 ноября", "сдать отчёт", D(2026, 11, 25), False),
    ("встреча послезавтра в 9 утра", "встреча", D(2026, 11, 19, 9, 0), True),
    ("завтра вечером кино", "кино", D(2026, 11, 18, 19, 0), True),
    ("через полчаса чай", "чай", D(2026, 11, 17, 10, 30), True),
    ("к пяти часам закончить", "закончить", D(2026, 11, 17, 17, 0), True),
    ("до 5 числа оплатить", "оплатить", D(2026, 12, 5), False),
    ("в 7:30 зарядка", "зарядка", D(2026, 11, 18, 7, 30), True),
    ("в 6 позвонить", "позвонить", D(2026, 11, 17, 18, 0), True),
    ("завтра в 6 подъём", "подъём", D(2026, 11, 18, 6, 0), True),
    ("сдать до 10.12", "сдать", D(2026, 12, 10), False),
    ("дойти до магазина завтра", "дойти до магазина", D(2026, 11, 18), False),
    # как выдаёт офлайн-распознавание Vosk: слова вместо цифр
    ("сдать отчет двадцать пятого ноября", "сдать отчет", D(2026, 11, 25), False),
    ("позвонить завтра в восемнадцать ноль ноль", "позвонить", D(2026, 11, 18, 18, 0), True),
    ("встреча в пятницу в семь тридцать вечера", "встреча", D(2026, 11, 20, 19, 30), True),
    ("оплатить до пятого числа", "оплатить", D(2026, 12, 5), False),
])
def test_parse_when(text, task, dt, has_time):
    p = parse_when(text, NOW)
    assert (p.text, p.dt, p.has_time) == (task, dt, has_time)


def test_not_a_time():
    assert parse_when("купить в 2 магазинах", NOW).dt is None
    assert parse_when("купить молоко", NOW).dt is None


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    clock = {"now": NOW}
    store = Store(tmp_path / "d.json")
    a = Assistant(Config(), store, now=lambda: clock["now"])
    return a, store, clock


def test_remember_task_with_deadline(env):
    a, store, _ = env
    r = a.handle("Джарвис запомни что мне надо сдать отчёт до пятницы 18:00".replace("Джарвис ", ""))
    assert "Сдать отчёт" in r and "20 ноября в 18:00" in r
    item = store.active()[0]
    assert item["title"] == "Сдать отчёт" and item["when"] == "2026-11-20 18:00"
    assert item["alerts"] == [1440, 60, 0]


def test_date_only_deadline_defaults_to_18_and_morning_alert(env):
    a, store, _ = env
    a.handle("запомни, что нужно купить подарок до 25 ноября")
    item = store.active()[0]
    assert item["when"] == "2026-11-25 18:00" and 540 in item["alerts"] and 0 in item["alerts"]


def test_reminder_flow_and_voice_text(env):
    a, store, clock = env
    assert "Напомню" in a.handle("напомни мне через час позвонить маме")
    sent = []
    sch = Scheduler(store, sent.append)
    sch.tick(NOW + timedelta(minutes=30))
    assert sent == []
    sch.tick(NOW + timedelta(minutes=61))
    sch.tick(NOW + timedelta(minutes=62))  # второй раз не повторяется
    assert sent == ["Напоминаю: Позвонить маме."]


def test_task_alerts_in_order_and_once(env):
    a, store, _ = env
    a.handle("запомни что надо сдать отчёт завтра в 18:00")
    sent = []
    sch = Scheduler(store, sent.append)
    sch.tick(D(2026, 11, 18, 17, 5))   # за час
    sch.tick(D(2026, 11, 18, 18, 0))   # срок
    assert len(sent) == 2 and "осталось 1 час" in sent[0] and sent[1].startswith("Срок пришёл")


def test_missed_alerts_collapse_when_jarvis_was_off(env):
    a, store, _ = env
    a.handle("запомни что надо сдать отчёт в пятницу в 18:00")
    sent = []
    Scheduler(store, sent.append).tick(D(2026, 11, 21, 9, 0))  # включили на следующий день
    assert len(sent) == 1 and "Пропущенное напоминание" in sent[0]


def test_reminder_asks_when_then_answers(env):
    a, store, _ = env
    assert a.handle("напомни полить цветы") == "Когда напомнить, сэр?"
    assert "Напомню завтра в 09:00" in a.handle("завтра в 9 утра")
    assert store.active()[0]["title"] == "Полить цветы"


def test_remind_missing_text_then_text(env):
    a, store, _ = env
    assert a.handle("напомни завтра в 9 утра") == "О чём напомнить, сэр?"
    a.handle("позвонить в банк")
    assert store.active()[0]["title"] == "Позвонить в банк"


def test_past_time_rejected(env):
    a, store, _ = env
    assert "уже прошло" in a.handle("напомни сегодня в 9 утра позвонить")
    assert store.active() == []


def test_note_vs_task(env):
    a, store, _ = env
    assert a.handle("запомни что пароль от вайфая 1234") == "Запомнил."
    assert store.active() == [] and store.notes()[0]["text"] == "Пароль от вайфая 1234"
    assert "1234" in a.handle("покажи заметки")


def test_list_done_delete(env):
    a, store, _ = env
    a.handle("запомни что надо купить хлеб до пятницы")
    a.handle("запомни что надо позвонить врачу завтра в 12:00")
    listing = a.handle("что у меня на сегодня")
    assert listing == "На этот день дел нет."
    all_ = a.handle("какие у меня дела")
    assert all_.startswith("Дел: 2. 1. Позвонить врачу") and "2. Купить хлеб" in all_
    assert "Отметил выполненным: Позвонить врачу" in a.handle("готово один")
    assert "Купить хлеб" in a.handle("удали хлеб")
    assert store.active() == []


def test_cancel_pending(env):
    a, _, _ = env
    a.handle("напомни полить цветы")
    assert a.handle("отмена") == "Хорошо, отменил."


def test_unknown_and_help(env):
    a, _, _ = env
    assert "не расслышал" in a.handle("абракадабра")
    assert "запоминать" in a.handle("что ты умеешь")


def test_pc_control_blocked_from_telegram(env, monkeypatch):
    a, _, _ = env
    assert "выключено" in a.handle("открой калькулятор", source="telegram")
    assert "выключено" in a.handle("громкость 50", source="telegram")


def test_wake_word():
    ww = ["джарвис", "жарвис", "jarvis"]
    assert strip_wake_word("Джарвис, запомни купить хлеб", ww) == "запомни купить хлеб"
    assert strip_wake_word("ну жарвис", ww) == "ну"
    assert strip_wake_word("Джарвис", ww) == ""
    assert strip_wake_word("привет", ww) is None


def test_store_persists_and_survives_corruption(tmp_path):
    s = Store(tmp_path / "d.json")
    s.add_item("task", "x", D(2026, 1, 1, 10, 0), [0])
    assert Store(tmp_path / "d.json").active()[0]["title"] == "x"
    (tmp_path / "d.json").write_text("{broken")
    assert Store(tmp_path / "d.json").active() == []
    assert (tmp_path / "d.broken").exists()


class FakeBot(TelegramBot):
    def __init__(self, cfg, store, assistant):
        super().__init__(cfg, store, assistant)
        self.sent = []

    def api(self, method, **p):
        self.sent.append((p["chat_id"], p["text"]))


def test_telegram_pairing_and_access(env):
    a, store, _ = env
    bot = FakeBot(Config(tg_token="t"), store, a)

    def msg(chat, text):
        bot.handle_update({"message": {"text": text, "chat": {"id": chat}}})
        return bot.sent[-1]

    assert "не привязан" in msg(1, "напомни завтра в 9 позвонить")[1]
    assert "не привязан" in msg(1, "/start 000000")[1]
    assert "Привязано" in msg(1, f"/start {bot.code}")[1]
    assert store.meta("tg_owner") == "1"
    assert msg(2, "список дел") == ("2", "Доступ запрещён.")
    assert "Напомню завтра в 09:00" in msg(1, "напомни завтра в 9 утра позвонить")[1]
    bot.send("🔔 тест")
    assert bot.sent[-1] == ("1", "🔔 тест")


def test_alert_text_variants():
    base = {"kind": "task", "title": "Отчёт", "when": "2026-11-20 18:00"}
    assert "осталось 1 день" in alert_text(base, 1440, D(2026, 11, 19, 18, 0))
    assert alert_text({**base, "kind": "reminder"}, 0, D(2026, 11, 20, 18, 0)) == "Напоминаю: Отчёт."
