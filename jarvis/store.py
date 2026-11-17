"""JSON-хранилище: задачи/напоминания, заметки и служебные данные."""
import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

TS = "%Y-%m-%d %H:%M"


def parse_ts(v: str) -> datetime:
    return datetime.strptime(v, TS)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = {"notes": [], "items": [], "meta": {}}
        if self.path.exists():
            try:
                self.data.update(json.loads(self.path.read_text(encoding="utf-8")))
            except json.JSONDecodeError:
                self.path.rename(self.path.with_suffix(".broken"))  # не теряем битый файл

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    # --- служебное ---
    def meta(self, key, default=None):
        with self._lock:
            return self.data["meta"].get(key, default)

    def set_meta(self, key, value):
        with self._lock:
            self.data["meta"][key] = value
            self._save()

    # --- заметки ---
    def add_note(self, text: str) -> dict:
        with self._lock:
            n = {"id": uuid.uuid4().hex[:6], "text": text, "created": datetime.now().strftime(TS)}
            self.data["notes"].append(n)
            self._save()
            return n

    def notes(self) -> list:
        with self._lock:
            return list(self.data["notes"])

    def delete_note(self, note_id: str) -> bool:
        with self._lock:
            n = len(self.data["notes"])
            self.data["notes"] = [x for x in self.data["notes"] if x["id"] != note_id]
            self._save()
            return len(self.data["notes"]) < n

    # --- задачи (kind=task, срок необязателен) и напоминания (kind=reminder) ---
    def add_item(self, kind: str, title: str, when: datetime | None, alerts: list | None = None) -> dict:
        with self._lock:
            item = {"id": uuid.uuid4().hex[:6], "kind": kind, "title": title,
                    "when": when.strftime(TS) if when else None, "done": False,
                    "alerts": sorted(alerts or [], reverse=True), "fired": []}
            self.data["items"].append(item)
            self._save()
            return dict(item)

    def active(self) -> list:
        """Невыполненные элементы: сначала со сроком по возрастанию, потом без срока."""
        with self._lock:
            items = [dict(i) for i in self.data["items"] if not i["done"]]
        return sorted(items, key=lambda i: (i["when"] is None, i["when"] or "", i["title"]))

    def mark_done(self, item_id: str) -> bool:
        with self._lock:
            for i in self.data["items"]:
                if i["id"] == item_id:
                    i["done"] = True
                    self._save()
                    return True
            return False

    def delete_item(self, item_id: str) -> bool:
        with self._lock:
            n = len(self.data["items"])
            self.data["items"] = [i for i in self.data["items"] if i["id"] != item_id]
            self._save()
            return len(self.data["items"]) < n

    def due(self, now: datetime) -> list:
        """[(элемент, смещение_в_минутах)] — о чём пора сообщить.

        Если программа была выключена и сработали сразу несколько оповещений одного дела,
        возвращается только последнее (ближайшее к сроку), остальные гасятся.
        """
        with self._lock:
            out = []
            for i in self.data["items"]:
                if i["done"] or not i["when"]:
                    continue
                when = parse_ts(i["when"])
                hit = [a for a in i["alerts"] if a not in i["fired"] and when - timedelta(minutes=a) <= now]
                if hit:
                    i["fired"].extend(hit)
                    out.append((dict(i), min(hit)))
            if out:
                self._save()
            return out
