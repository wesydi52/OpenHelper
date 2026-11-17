"""Детектор всплесков активности чата (чистая логика, без сети)."""
from collections import deque
from statistics import mean, pstdev


class SpikeDetector:
    """Принимает число сообщений за окно; возвращает True, если это всплеск."""

    def __init__(self, history_windows=30, min_history=6, sigma=3.0,
                 min_msgs=15, cooldown_windows=4):
        self.history = deque(maxlen=history_windows)
        self.min_history = min_history
        self.sigma = sigma
        self.min_msgs = min_msgs
        self.cooldown_windows = cooldown_windows
        self._cooldown = 0

    def push(self, count: int) -> bool:
        spike = False
        if self._cooldown > 0:
            self._cooldown -= 1
        elif len(self.history) >= self.min_history and count >= self.min_msgs:
            m, s = mean(self.history), pstdev(self.history)
            if count > m + self.sigma * max(s, 1.0):
                spike = True
                self._cooldown = self.cooldown_windows
        # всплеск не портит базовую линию
        self.history.append(min(count, mean(self.history) * 2) if (spike and self.history) else count)
        return spike
