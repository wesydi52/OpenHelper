"""Telegram-бот на чистом Bot API (requests, без сторонних библиотек).

Доступ только владельцу. Привязка: при первом запуске в консоли печатается одноразовый код,
отправьте боту «/start КОД» — chat id запомнится в хранилище.
"""
import secrets
import threading
import time

import requests


class TelegramBot(threading.Thread):
    def __init__(self, cfg, store, assistant):
        super().__init__(daemon=True)
        self.cfg, self.store, self.assistant = cfg, store, assistant
        self.base = f"https://api.telegram.org/bot{cfg.tg_token}/"
        self.offset = 0
        self.code = secrets.token_hex(3)
        self._stop_evt = threading.Event()

    @property
    def owner(self) -> str:
        return self.cfg.tg_owner or str(self.store.meta("tg_owner", "") or "")

    def api(self, method: str, **params):
        r = requests.post(self.base + method, json=params, timeout=40)
        r.raise_for_status()
        return r.json()["result"]

    def send(self, text: str, chat_id: str | None = None):
        chat = chat_id or self.owner
        if not chat:
            return
        try:
            self.api("sendMessage", chat_id=chat, text=text)
        except requests.RequestException as e:
            print(f"[telegram] не удалось отправить: {e}")

    def handle_update(self, upd: dict):
        msg = upd.get("message") or {}
        text = (msg.get("text") or "").strip()
        chat = str(msg.get("chat", {}).get("id", ""))
        if not text or not chat:
            return
        if not self.owner:
            if text == f"/start {self.code}":
                self.store.set_meta("tg_owner", chat)
                self.send("Привязано. Теперь я буду присылать напоминания сюда. Напишите «что ты умеешь».", chat)
            else:
                self.send("Бот не привязан. Отправьте /start и код из консоли Джарвиса.", chat)
            return
        if chat != self.owner:
            self.send("Доступ запрещён.", chat)
            return
        if text.startswith("/start"):
            text = "привет"
        elif text.startswith("/"):
            text = text[1:].replace("_", " ")  # /help, /tasks -> команда
            text = {"tasks": "что у меня на сегодня", "list": "список дел"}.get(text, text)
        reply = self.assistant.handle(text, source="telegram")
        if reply:
            self.send(reply, chat)

    def run(self):
        if not self.owner:
            print(f"[telegram] Для привязки отправьте боту: /start {self.code}")
        backoff = 2
        while not self._stop_evt.is_set():
            try:
                for upd in self.api("getUpdates", offset=self.offset, timeout=25):
                    self.offset = upd["update_id"] + 1
                    self.handle_update(upd)
                backoff = 2
            except requests.RequestException as e:
                print(f"[telegram] нет связи ({e}); повтор через {backoff} с")
                time.sleep(backoff)
                backoff = min(backoff * 2, 60)

    def stop(self):
        self._stop_evt.set()
