from datetime import datetime, timedelta
from types import SimpleNamespace as NS

from jarvis.brain import Brain
from jarvis.config import Config
from jarvis.scheduler import Scheduler
from jarvis.store import Store
from jarvis.tools import build_registry
from jarvis.voice import strip_wake_word


def make(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    cfg = Config(api_key="x")
    store = Store(tmp_path / "d.json")
    return cfg, store, build_registry(cfg, store)


class FakeClient:
    """Первый ответ — вызов инструмента, второй — текст."""
    def __init__(self, tool_name, tool_input):
        self.calls, self.seq = [], [
            NS(content=[NS(type="tool_use", id="t1", name=tool_name, input=tool_input)]),
            NS(content=[NS(type="text", text="Готово.")]),
        ]
        self.messages = self

    def create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})
        return self.seq[len(self.calls) - 1]


def test_tool_loop_adds_note(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    client = FakeClient("add_note", {"text": "купить молоко"})
    assert Brain(cfg, reg, client=client).ask("запиши: купить молоко") == "Готово."
    assert store.notes()[0]["text"] == "купить молоко"


def test_confirm_required_tool_declined(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    client = FakeClient("run_command", {"command": "echo hi"})
    brain = Brain(cfg, reg, client=client, confirm=lambda n, a: False)
    brain.ask("выполни")
    result = client.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] and "отклонил" in result["content"]


def test_confirm_accepted_runs(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    client = FakeClient("run_command", {"command": "echo hi"})
    Brain(cfg, reg, client=client, confirm=lambda n, a: True).ask("выполни")
    assert "hi" in client.calls[1]["messages"][-1]["content"][0]["content"]


def test_unknown_tool_and_bad_args_do_not_crash(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    for name, inp in (("nope", {}), ("add_note", {"wrong": 1})):
        client = FakeClient(name, inp)
        assert Brain(cfg, reg, client=client).ask("x") == "Готово."
        assert client.calls[1]["messages"][-1]["content"][0]["is_error"]


def test_reminder_fires_once(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    now = datetime.now().replace(second=0, microsecond=0)
    reg.get("add_reminder").func("позвонить маме", (now - timedelta(minutes=1)).strftime("%Y-%m-%d %H:%M"))
    reg.get("add_event").func("встреча", (now + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M"), 30, 10)
    got = []
    s = Scheduler(store, got.append)
    s.tick(now)
    s.tick(now)
    assert len(got) == 2 and "мам" in got[0] and "встреча" in got[1]


def test_store_persists(tmp_path):
    s = Store(tmp_path / "d.json")
    s.add_note("a")
    assert Store(tmp_path / "d.json").notes()[0]["text"] == "a"


def test_agenda_and_delete(tmp_path, monkeypatch):
    cfg, store, reg = make(tmp_path, monkeypatch)
    when = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
    reg.get("add_event").func("врач", when)
    assert "врач" in reg.get("list_agenda").func()
    item_id = store.items()[0]["id"]
    assert reg.get("delete_agenda_item").func(item_id) == "Удалено."


def test_wake_word():
    assert strip_wake_word("Джарвис, какая погода", "джарвис") == "какая погода"
    assert strip_wake_word("Джарвис", "джарвис") == ""
    assert strip_wake_word("привет", "джарвис") is None


def test_schemas_valid(tmp_path, monkeypatch):
    _, _, reg = make(tmp_path, monkeypatch)
    for s in reg.schemas():
        assert s["name"] and s["description"] and s["input_schema"]["type"] == "object"
