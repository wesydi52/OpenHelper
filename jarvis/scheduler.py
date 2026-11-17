"""Проактивные напоминания: фоновый поток проверяет хранилище и оповещает по всем каналам."""
import threading
from datetime import datetime
from typing import Callable

from .fmt import alert_text


class Scheduler(threading.Thread):
    def __init__(self, store, notify: Callable[[str], None], interval: float = 10.0,
                 review: Callable[[datetime], tuple | None] | None = None,
                 notify_tg: Callable[[str], None] | None = None):
        super().__init__(daemon=True)
        self.store, self.notify, self.interval = store, notify, interval
        self.review, self.notify_tg = review, notify_tg  # ежедневная сводка непонятных фраз
        self._stop_evt = threading.Event()

    def tick(self, now: datetime | None = None):
        now = now or datetime.now()
        for item, offset in self.store.due(now):
            self.notify(alert_text(item, offset, now))
        if self.review and (r := self.review(now)):
            voice_text, tg_list = r
            self.notify(voice_text)          # консоль + голос (+ Telegram, если включён)
            if self.notify_tg:
                self.notify_tg(tg_list)      # полный список — только в Telegram

    def run(self):
        while not self._stop_evt.wait(self.interval):
            try:
                self.tick()
            except Exception as e:
                print(f"[scheduler] {e}")

    def stop(self):
        self._stop_evt.set()
