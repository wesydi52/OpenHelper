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
        self._proc = subprocess.Popen(
            ["streamlink", "--twitch-disable-ads", "-o", self.path, self.url, self.quality],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.started_at = time.time()

    def alive(self):
        return self._proc is not None and self._proc.poll() is None

    def stop(self):
        if self._proc and self.alive():
            self._proc.terminate()
            self._proc.wait(timeout=15)
