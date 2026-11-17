"""Проактивные напоминания: фоновый поток проверяет хранилище и оповещает по всем каналам."""
import threading
from datetime import datetime
from typing import Callable

from .fmt import alert_text


class Scheduler(threading.Thread):
    def __init__(self, store, notify: Callable[[str], None], interval: float = 10.0):
        super().__init__(daemon=True)
        self.store, self.notify, self.interval = store, notify, interval
        self._stop_evt = threading.Event()

    def tick(self, now: datetime | None = None):
        now = now or datetime.now()
        for item, offset in self.store.due(now):
            self.notify(alert_text(item, offset, now))

    def run(self):
        while not self._stop_evt.wait(self.interval):
            try:
                self.tick()
            except Exception as e:
                print(f"[scheduler] {e}")

    def stop(self):
        self._stop_evt.set()
