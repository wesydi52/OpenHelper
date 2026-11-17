"""clipbot: пишем эфир, ловим всплески чата, режем клипы с субтитрами.

Запуск:  python -m clipbot.main --channel <имя>
Работает только в прямом эфире: нужен активный чат и идущая трансляция.
"""
import argparse
import os
import time

from .chat import ChatCounter
from .clipper import cut
from .config import Config
from .detector import SpikeDetector
from .recorder import Recorder


def run(cfg: Config):
    os.makedirs(cfg.out_dir, exist_ok=True)
    rec_path = os.path.join(cfg.out_dir, f"{cfg.channel}_{int(time.time())}.ts")
    rec = Recorder(cfg.channel, cfg.quality, rec_path)
    chat = ChatCounter(cfg.channel, cfg.hype_words)
    det = SpikeDetector(cfg.history_windows, cfg.min_history, cfg.spike_sigma,
                        cfg.min_msgs, max(1, cfg.cooldown_sec // cfg.window_sec))
    tr = None
    if cfg.subtitles:
        from .subtitles import Transcriber
        tr = Transcriber(cfg.whisper_model, cfg.language)

    rec.start()
    chat.start()
    pending = []  # (момент пика в epoch, номер)
    n = 0
    print(f"[clipbot] пишу {cfg.channel} -> {rec_path}")
    try:
        while rec.alive():
            time.sleep(cfg.window_sec)
            msgs, hype = chat.take()
            # хайп-слова утяжеляют окно
            score = msgs + hype
            if det.push(score):
                n += 1
                pending.append((time.time(), n))
                print(f"[clipbot] всплеск #{n}: {msgs} сообщений, {hype} хайп-слов")
            ready = [p for p in pending if time.time() - p[0] >= cfg.clip_after_sec]
            for peak, num in ready:
                pending.remove((peak, num))
                _make_clip(cfg, rec, tr, peak, num)
    except KeyboardInterrupt:
        pass
    finally:
        chat.stop()
        rec.stop()


def _make_clip(cfg, rec, tr, peak, num):
    video_t = peak - rec.started_at - cfg.stream_delay_sec
    start = video_t - cfg.clip_before_sec
    dur = cfg.clip_before_sec + cfg.clip_after_sec
    base = os.path.join(cfg.out_dir, f"clip_{num:03}")
    srt = None
    if tr:
        raw = cut(rec.path, start, dur, base + "_raw.mp4", vertical=False)
        srt = tr.srt_for(raw, base + ".srt")
    out = cut(rec.path, start, dur, base + ".mp4", cfg.vertical, srt)
    print(f"[clipbot] готов клип: {out}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--channel", required=True)
    p.add_argument("--out", default="output")
    p.add_argument("--no-subs", action="store_true")
    p.add_argument("--landscape", action="store_true")
    a = p.parse_args()
    run(Config(channel=a.channel, out_dir=a.out, subtitles=not a.no_subs,
               vertical=not a.landscape))


if __name__ == "__main__":
    main()
