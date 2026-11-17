"""Проактивные напоминания: фоновый поток проверяет хранилище и оповещает по всем каналам."""
import threading
from datetime import datetime
from typing import Callable

from .fmt import alert_text, unacked_text


class Scheduler(threading.Thread):
    def __init__(self, store, notify: Callable[[str], None], interval: float = 1.0,
                 review: Callable[[datetime], tuple | None] | None = None,
                 notify_tg: Callable[[str], None] | None = None,
                 tg_dup_minutes: int | None = None,
                 on_alert: Callable | None = None,
                 hooks: list | None = None,
                 is_dnd: Callable[[], bool] | None = None):
        super().__init__(daemon=True)
        self.store, self.notify, self.interval = store, notify, interval
        # Если на ПК не отреагировали за столько минут — продублировать напоминание в Telegram
        self.tg_dup_minutes = tg_dup_minutes
        self.on_alert = on_alert          # (item, offset, now) -> свой текст оповещения или None (будильник, таймер)
        self.hooks = hooks or []          # [(now) -> [тексты]]: отсчёты, повторяющиеся напоминания
        self.is_dnd = is_dnd              # при «не беспокоить» дубль в Telegram не нужен: туда и так шлём сразу
        self.review, self.notify_tg = review, notify_tg  # ежедневная сводка непонятных фраз
        self._stop_evt = threading.Event()

    def tick(self, now: datetime | None = None):
        now = now or datetime.now()
        for item, offset in self.store.due(now):
            text = (self.on_alert(item, offset, now) if self.on_alert else None) or alert_text(item, offset, now)
            self.notify(text)
        for hook in self.hooks:
            for msg in hook(now) or []:
                self.notify(msg)
        if self.notify_tg and self.tg_dup_minutes and not (self.is_dnd and self.is_dnd()):
            for item in self.store.unacked(now, self.tg_dup_minutes):
                self.notify_tg(unacked_text(item))
                self.store.mark_tg_dup(item["id"])
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
