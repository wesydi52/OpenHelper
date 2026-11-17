"""Простое JSON-хранилище: заметки, напоминания и события календаря."""
import json
import threading
import uuid
from datetime import datetime
from pathlib import Path

TS = "%Y-%m-%d %H:%M"


def parse_dt(value: str) -> datetime:
    """Принимает 'YYYY-MM-DD HH:MM' или ISO-формат."""
    value = value.strip().replace("T", " ")
    for fmt in (TS, "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError(f"Не понимаю дату/время: {value!r}. Нужен формат 'ГГГГ-ММ-ДД ЧЧ:ММ'.")


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = {"notes": [], "items": []}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                pass

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # --- заметки ---
    def add_note(self, text: str, title: str = "") -> dict:
        with self._lock:
            note = {"id": uuid.uuid4().hex[:6], "title": title, "text": text,
                    "created": datetime.now().strftime(TS)}
            self.data["notes"].append(note)
            self._save()
            return note

    def notes(self, query: str = "") -> list:
        q = query.lower()
        with self._lock:
            return [n for n in self.data["notes"]
                    if not q or q in n["text"].lower() or q in n["title"].lower()]

    def delete_note(self, note_id: str) -> bool:
        with self._lock:
            before = len(self.data["notes"])
            self.data["notes"] = [n for n in self.data["notes"] if n["id"] != note_id]
            self._save()
            return len(self.data["notes"]) < before

    # --- напоминания (kind=reminder) и события (kind=event) ---
    def add_item(self, kind: str, title: str, when: datetime,
                 duration_min: int = 0, lead_min: int = 0) -> dict:
        with self._lock:
            item = {"id": uuid.uuid4().hex[:6], "kind": kind, "title": title,
                    "when": when.strftime(TS), "duration_min": duration_min,
                    "lead_min": lead_min, "notified": False}
            self.data["items"].append(item)
            self._save()
            return item

    def items(self, kind: str | None = None, start: datetime | None = None,
              end: datetime | None = None) -> list:
        with self._lock:
            out = []
            for i in self.data["items"]:
                if kind and i["kind"] != kind:
                    continue
                w = parse_dt(i["when"])
                if start and w < start:
                    continue
                if end and w > end:
                    continue
                out.append(i)
            return sorted(out, key=lambda i: i["when"])

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            before = len(self.data["items"])
            self.data["items"] = [i for i in self.data["items"] if i["id"] != item_id]
            self._save()
            return len(self.data["items"]) < before

    def due(self, now: datetime) -> list:
        """Элементы, о которых пора сообщить. Помечает их как уведомлённые."""
        from datetime import timedelta
        with self._lock:
            fired = []
            for i in self.data["items"]:
                if i["notified"]:
                    continue
                trigger = parse_dt(i["when"]) - timedelta(minutes=i["lead_min"])
                if trigger <= now:
                    i["notified"] = True
                    fired.append(dict(i))
            if fired:
                self._save()
            return fired
