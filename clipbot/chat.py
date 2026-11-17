"""Анонимное чтение чата Twitch по IRC (только stdlib)."""
import random
import socket
import threading
import time


class ChatCounter:
    """Фоновый поток: считает сообщения и хайп-слова, отдаёт счётчики по окнам."""

    def __init__(self, channel, hype_words=()):
        self.channel = channel.lower().lstrip("#")
        self.hype = {w.upper() for w in hype_words}
        self._lock = threading.Lock()
        self._msgs = 0
        self._hype = 0
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        self._thread.start()

    def stop(self):
        self._stop.set()

    def take(self):
        """Вернуть (сообщения, хайп-слова) с прошлого вызова и обнулить."""
        with self._lock:
            r = (self._msgs, self._hype)
            self._msgs = self._hype = 0
        return r

    def _on_message(self, text):
        words = text.upper().split()
        with self._lock:
            self._msgs += 1
            self._hype += sum(1 for w in words if w in self.hype)

    def _run(self):
        while not self._stop.is_set():
            try:
                self._session()
            except OSError as e:
                print(f"[chat] соединение потеряно: {e}; переподключение через 5с")
                time.sleep(5)

    def _session(self):
        nick = f"justinfan{random.randint(10000, 99999)}"
        with socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=30) as s:
            s.sendall(f"PASS SCHMOOPIIE\r\nNICK {nick}\r\nJOIN #{self.channel}\r\n".encode())
            s.settimeout(60)
            buf = b""
            while not self._stop.is_set():
                data = s.recv(4096)
                if not data:
                    raise OSError("EOF")
                buf += data
                *lines, buf = buf.split(b"\r\n")
                for raw in lines:
                    line = raw.decode("utf-8", "replace")
                    if line.startswith("PING"):
                        s.sendall(b"PONG :tmi.twitch.tv\r\n")
                    elif " PRIVMSG " in line:
                        self._on_message(line.split(" :", 1)[-1] if " :" in line else "")
