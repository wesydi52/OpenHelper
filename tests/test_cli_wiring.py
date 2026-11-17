"""Как cli связывает каналы: на ПК — голос/консоль, в Telegram — дубль через 15 минут (или сразу в --headless)."""
import builtins

import pytest

import jarvis.cli as cli


class FakeBot:
    instances = []

    def __init__(self, cfg, store, assistant):
        self.sent = []
        FakeBot.instances.append(self)

    def start(self):
        pass

    def stop(self):
        pass

    def send(self, text, chat_id=None):
        self.sent.append(text)


class RecordingScheduler:
    last = None

    def __init__(self, store, notify, **kw):
        self.notify, self.kw = notify, kw
        RecordingScheduler.last = self

    def start(self):
        pass

    def stop(self):
        pass


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_TG_TOKEN", "t")
    monkeypatch.delenv("JARVIS_TG_DUP_MINUTES", raising=False)
    FakeBot.instances.clear()
    monkeypatch.setattr(cli, "TelegramBot", FakeBot)
    monkeypatch.setattr(cli, "Scheduler", RecordingScheduler)
    return monkeypatch


def test_console_mode_alert_stays_on_pc_and_telegram_gets_duplicate_only(wired, capsys):
    wired.setattr(builtins, "input", lambda *_: "выход")
    cli.main(["--telegram"])
    sch, bot = RecordingScheduler.last, FakeBot.instances[0]
    assert sch.kw["tg_dup_minutes"] == 15
    assert sch.kw["notify_tg"] == bot.send
    sch.notify("Напоминаю: Позвонить врачу.")
    assert bot.sent == []                                   # в Telegram сразу не уходит
    assert "Напоминаю: Позвонить врачу." in capsys.readouterr().out


def test_headless_sends_to_telegram_immediately_without_duplicates(wired):
    def stop(_):
        raise KeyboardInterrupt
    wired.setattr(cli.time, "sleep", stop)
    cli.main(["--telegram", "--headless"])
    sch, bot = RecordingScheduler.last, FakeBot.instances[0]
    assert sch.kw["tg_dup_minutes"] is None
    sch.notify("Напоминаю: Позвонить врачу.")
    assert bot.sent == ["Напоминаю: Позвонить врачу."]


def test_dup_minutes_is_configurable(wired):
    wired.setenv("JARVIS_TG_DUP_MINUTES", "5")
    wired.setattr(builtins, "input", lambda *_: "выход")
    cli.main(["--telegram"])
    assert RecordingScheduler.last.kw["tg_dup_minutes"] == 5


def test_without_telegram_no_duplicate_channel(wired):
    wired.delenv("JARVIS_TG_TOKEN")
    wired.setattr(builtins, "input", lambda *_: "выход")
    cli.main([])
    assert RecordingScheduler.last.kw["notify_tg"] is None
