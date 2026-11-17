"""JSON-хранилище: задачи/напоминания, заметки и служебные данные."""
import json
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

TS = "%Y-%m-%d %H:%M"
SNOOZE_OFFSET = -1   # признак повторного оповещения после «отложи»


def parse_ts(v: str) -> datetime:
    return datetime.strptime(v, TS)


class Store:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self.data = {"notes": [], "items": [], "meta": {}, "unrecognized": []}
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

    # --- журнал нераспознанных фраз (только текст; аудио не сохраняется) ---
    UNRECOGNIZED_LIMIT = 1000

    def log_unrecognized(self, text: str, source: str, when: datetime) -> None:
        with self._lock:
            log = self.data.setdefault("unrecognized", [])
            log.append({"ts": when.strftime(TS), "text": text, "source": source, "reviewed": False})
            del log[:-self.UNRECOGNIZED_LIMIT]
            self._save()

    def unrecognized(self, only_new: bool = True) -> list:
        with self._lock:
            return [dict(x) for x in self.data.get("unrecognized", []) if not (only_new and x["reviewed"])]

    def mark_unrecognized_reviewed(self) -> None:
        with self._lock:
            for x in self.data.get("unrecognized", []):
                x["reviewed"] = True
            self._save()

    def clear_unrecognized(self) -> int:
        with self._lock:
            n = len(self.data.get("unrecognized", []))
            self.data["unrecognized"] = []
            self._save()
            return n

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
                    i["awaiting"] = None
                    i["snooze_until"] = None
                    self._save()
                    return True
            return False

    # --- повторяющиеся напоминания («напоминай пить воду каждые два часа») ---
    def add_recurring(self, title: str, interval_min: int, first: datetime) -> dict:
        with self._lock:
            r = {"id": uuid.uuid4().hex[:6], "title": title, "interval_min": interval_min,
                 "next": first.strftime(TS)}
            self.data.setdefault("recurring", []).append(r)
            self._save()
            return dict(r)

    def recurring(self) -> list:
        with self._lock:
            return [dict(r) for r in self.data.get("recurring", [])]

    def recurring_due(self, now: datetime) -> list:
        """Напоминания, которым пора. Следующий раз — через interval от now (после простоя серией не сыплем)."""
        with self._lock:
            out = []
            for r in self.data.get("recurring", []):
                if parse_ts(r["next"]) <= now:
                    out.append(dict(r))
                    r["next"] = (now + timedelta(minutes=r["interval_min"])).strftime(TS)
            if out:
                self._save()
            return out

    def postpone_recurring(self, rid: str, until: datetime) -> bool:
        with self._lock:
            for r in self.data.get("recurring", []):
                if r["id"] == rid:
                    r["next"] = until.strftime(TS)
                    self._save()
                    return True
            return False

    def delete_recurring(self, rid: str) -> bool:
        with self._lock:
            n = len(self.data.get("recurring", []))
            self.data["recurring"] = [r for r in self.data.get("recurring", []) if r["id"] != rid]
            self._save()
            return len(self.data["recurring"]) < n

    # --- реакция владельца на сработавшее напоминание ---
    def awaiting(self, now: datetime, window_min: int = 120) -> list:
        """Дела, о которых Джарвис напомнил и ждёт реакции (не старше window_min минут)."""
        with self._lock:
            out = []
            for i in self.data["items"]:
                ts = i.get("awaiting")
                if i["done"] or not ts:
                    continue
                if now - parse_ts(ts) <= timedelta(minutes=window_min):
                    out.append(dict(i))
            return sorted(out, key=lambda i: i["awaiting"])

    def recent(self, now: datetime, window_min: int = 120) -> list:
        """Дела, о которых недавно напоминали — даже если владелец уже сказал «понял».
        По ним можно закрыть дело словами «я уже позвонил»."""
        with self._lock:
            out = []
            for i in self.data["items"]:
                ts = i.get("alerted") or i.get("awaiting")   # старые данные: поля alerted нет
                if i["done"] or not ts:
                    continue
                if now - parse_ts(ts) <= timedelta(minutes=window_min):
                    out.append(dict(i, alerted=ts))
            return sorted(out, key=lambda i: i["alerted"])

    def _update(self, item_id: str, **fields) -> bool:
        with self._lock:
            for i in self.data["items"]:
                if i["id"] == item_id:
                    i.update(fields)
                    self._save()
                    return True
            return False

    def ack(self, item_id: str) -> bool:
        """«Понял»: дело остаётся активным, но это напоминание больше не повторяется и не дублируется."""
        return self._update(item_id, awaiting=None, tg_dup=False)

    def snooze(self, item_id: str, until: datetime) -> bool:
        """Отложить: напомнить ещё раз в момент until."""
        return self._update(item_id, awaiting=None, tg_dup=False, snooze_until=until.strftime(TS))

    def unacked(self, now: datetime, minutes: int) -> list:
        """Дела без реакции дольше minutes минут, которые ещё не дублировались в Telegram."""
        with self._lock:
            return [dict(i) for i in self.data["items"]
                    if not i["done"] and i.get("awaiting") and not i.get("tg_dup")
                    and now - parse_ts(i["awaiting"]) >= timedelta(minutes=minutes)]

    def mark_tg_dup(self, item_id: str) -> bool:
        return self._update(item_id, tg_dup=True)

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
            stamp = now.strftime(TS)
            for i in self.data["items"]:
                if i["done"] or not i["when"]:
                    continue
                when = parse_ts(i["when"])
                hit = [a for a in i["alerts"] if a not in i["fired"] and when - timedelta(minutes=a) <= now]
                snooze = i.get("snooze_until")
                if hit:
                    i["fired"].extend(hit)
                    i["snooze_until"] = None   # плановое оповещение важнее отложенного
                    i["awaiting"], i["alerted"], i["tg_dup"] = stamp, stamp, False
                    out.append((dict(i), min(hit)))
                elif snooze and parse_ts(snooze) <= now:
                    i["snooze_until"] = None
                    i["awaiting"], i["alerted"], i["tg_dup"] = stamp, stamp, False
                    out.append((dict(i), SNOOZE_OFFSET))   # «Повторяю: …»
            if out:
                self._save()
            return out
