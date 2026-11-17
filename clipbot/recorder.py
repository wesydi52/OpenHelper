"""Запись эфира через Streamlink в один .ts файл (можно резать на лету)."""
import subprocess
import time


class Recorder:
    def __init__(self, channel, quality, path):
        self.url = f"https://twitch.tv/{channel}"
        self.quality = quality
        self.path = path
        self.started_at = None  # epoch начала записи
        self._proc = None

    def start(self):
        self.log_path = self.path + ".log"
        self._log = open(self.log_path, "wb")
        self._proc = subprocess.Popen(
            ["streamlink", "--twitch-disable-ads", "-o", self.path, self.url, self.quality],
            stdout=subprocess.DEVNULL, stderr=self._log)
        self.started_at = time.time()

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def stop(self):
        if self._proc and self.alive():
            self._proc.terminate()
            self._proc.wait(timeout=15)

    def error_tail(self):
        try:
            with open(self.log_path, encoding="utf-8", errors="replace") as f:
                return f.read()[-400:].strip()
        except OSError:
            return ""
