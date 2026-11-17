"""Параметры clipbot: запись стрима, детектор всплесков чата, нарезка."""
from dataclasses import dataclass, field


@dataclass
class Config:
    channel: str = "xqc"                 # канал Twitch (без #)
    quality: str = "720p60,720p,best"
    out_dir: str = "output"

    # детектор: окно подсчёта сообщений чата
    window_sec: int = 10                 # «каждые 10 секунд»
    history_windows: int = 30            # сколько окон помним для базовой линии
    min_history: int = 6                 # пока истории меньше — не срабатываем
    spike_sigma: float = 3.0             # порог: среднее + N * std
    min_msgs: int = 15                   # абсолютный минимум сообщений в окне
    cooldown_sec: int = 45               # не резать клипы чаще

    # нарезка
    clip_before_sec: int = 20            # секунд до пика
    clip_after_sec: int = 10             # секунд после пика
    stream_delay_sec: float = 8.0        # чат опережает видео (задержка стрима)
    vertical: bool = True                # 9:16 для TikTok/Shorts

    # субтитры
    subtitles: bool = True
    whisper_model: str = "small"
    language: str = "ru"
    hype_words: list = field(default_factory=lambda: [
        "LUL", "KEKW", "OMEGALUL", "POG", "POGGERS", "W", "HOLY", "WTF", "LMAO", "CLIP"])
