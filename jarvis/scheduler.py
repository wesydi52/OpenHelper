"""Проактивные напоминания: фоновый поток проверяет хранилище и сообщает о делах."""
import threading
from datetime import datetime
from typing import Callable


class Scheduler(threading.Thread):
    def __init__(self, store, notify: Callable[[str], None], interval: float = 15.0):
        super().__init__(daemon=True)
        self.store, self.notify, self.interval = store, notify, interval
        self._stop_evt = threading.Event()

    def tick(self, now: datetime | None = None):
        for i in self.store.due(now or datetime.now()):
            if i["kind"] == "event":
                lead = f" через {i['lead_min']} мин" if i["lead_min"] else " сейчас"
                self.notify(f"Событие{lead}: {i['title']} (в {i['when'][-5:]}).")
            else:
                self.notify(f"Напоминаю: {i['title']}.")

    def run(self):
        while not self._stop_evt.wait(self.interval):
            try:
                self.tick()
            except Exception as e:
                print(f"[scheduler] {e}")

    def stop(self):
        self._stop_evt.set()
