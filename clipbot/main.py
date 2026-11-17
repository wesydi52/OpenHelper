"""Ядро clipbot: пишем эфир, ловим всплески чата, режем клипы с субтитрами.

CLI:  python -m clipbot.main --channel <имя>
Меню: python -m clipbot          (откроется в браузере)
Работает только в прямом эфире.
"""
import argparse
import os
import re
import threading
import time

from .chat import ChatCounter
from .clipper import cut
from .config import Config
from .detector import SpikeDetector
from .recorder import Recorder


def parse_channel(text: str) -> str:
    """Принимает 'xqc', '@xqc' или ссылку twitch.tv/xqc."""
    t = text.strip().rstrip("/")
    m = re.search(r"twitch\.tv/([A-Za-z0-9_]+)", t)
    name = m.group(1) if m else t.lstrip("@#")
    if not re.fullmatch(r"[A-Za-z0-9_]{2,25}", name):
        raise ValueError("Не похоже на канал Twitch. Пример: xqc или https://twitch.tv/xqc")
    return name.lower()


def run(cfg: Config, stop=None, log=print, state=None):
    stop = stop or threading.Event()
    state = state if state is not None else {}
    os.makedirs(cfg.out_dir, exist_ok=True)
    rec_path = os.path.join(cfg.out_dir, f"{cfg.channel}_{int(time.time())}.ts")
    rec = Recorder(cfg.channel, cfg.quality, rec_path)
    chat = ChatCounter(cfg.channel, cfg.hype_words)
    det = SpikeDetector(cfg.history_windows, cfg.min_history, cfg.spike_sigma,
                        cfg.min_msgs, max(1, cfg.cooldown_sec // cfg.window_sec))
    tr = None
    if cfg.subtitles:
        log("Загружаю Whisper (первый раз скачивает модель, это долго)…")
        from .subtitles import Transcriber
        tr = Transcriber(cfg.whisper_model, cfg.language)

    rec.start()
    time.sleep(4)
    if not rec.alive():
        log("Не удалось начать запись. Канал не в эфире или нет доступа: " + rec.error_tail())
        state["running"] = False
        return
    chat.start()
    state.update(running=True, channel=cfg.channel, scores=[], threshold=None, spikes=0)
    pending, n, test_done = [], 0, False
    log(f"Пишу эфир канала {cfg.channel}. Жду всплеск чата…")
    try:
        while rec.alive() and not stop.is_set():
            if stop.wait(cfg.window_sec):
                break
            msgs, hype = chat.take()
            score = msgs + hype  # хайп-слова утяжеляют окно
            spike = det.push(score)
            state["scores"] = (state["scores"] + [score])[-60:]
            state["threshold"] = det.threshold()
            if spike:
                n += 1
                state["spikes"] = n
                pending.append((time.time(), n))
                log(f"Всплеск #{n}: {msgs} сообщений, {hype} хайп-слов")
            if cfg.test_mode and not test_done and time.time() - rec.started_at >= 45:
                test_done = True
                n += 1
                pending.append((time.time(), n))
                log("Тестовый режим: делаю пробный клип")
            for peak, num in [p for p in pending if time.time() - p[0] >= cfg.clip_after_sec]:
                pending.remove((peak, num))
                try:
                    _make_clip(cfg, rec, tr, peak, num, log)
                except Exception as e:  # клип не должен ронять запись
                    log(f"Ошибка при нарезке клипа #{num}: {e}")
        if not rec.alive() and not stop.is_set():
            log("Стрим закончился или запись оборвалась.")
    finally:
        chat.stop()
        rec.stop()
        state["running"] = False
        log("Остановлено.")


def _make_clip(cfg, rec, tr, peak, num, log):
    start = peak - rec.started_at - cfg.stream_delay_sec - cfg.clip_before_sec
    dur = cfg.clip_before_sec + cfg.clip_after_sec
    base = os.path.join(cfg.out_dir, f"{cfg.channel}_clip_{int(peak)}")
    srt = None
    if tr:
        raw = cut(rec.path, start, dur, base + "_raw.mp4", vertical=False)
        srt = tr.srt_for(raw, base + ".srt")
        os.remove(raw)
    out = cut(rec.path, start, dur, base + ".mp4", cfg.vertical, srt)
    log(f"Готов клип: {os.path.basename(out)}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", required=True)
    p.add_argument("--out", default="output")
    p.add_argument("--no-subs", action="store_true")
    p.add_argument("--landscape", action="store_true")
    p.add_argument("--test", action="store_true")
    a = p.parse_args()
    cfg = Config(channel=parse_channel(a.channel), out_dir=a.out,
                 subtitles=not a.no_subs, vertical=not a.landscape, test_mode=a.test)
    try:
        run(cfg)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
