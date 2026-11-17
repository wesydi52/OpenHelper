"""Локальное меню clipbot: http://127.0.0.1:8765 (только stdlib, доступно лишь с этого ПК)."""
import json
import mimetypes
import os
import shutil
import threading
import time
import webbrowser
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote

from .config import Config
from .main import parse_channel, run

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.abspath("output")
PORT = 8765


class Session:
    """Одна запущенная запись; меню управляет ею через start/stop."""

    def __init__(self):
        self.lock = threading.Lock()
        self.thread = None
        self.stop_ev = threading.Event()
        self.state = {"running": False, "scores": [], "threshold": None, "spikes": 0}
        self.logs = deque(maxlen=200)

    def log(self, msg):
        self.logs.append(f"{time.strftime('%H:%M:%S')}  {msg}")
        print(msg, flush=True)

    def running(self):
        return self.thread is not None and self.thread.is_alive()

    def start(self, cfg):
        with self.lock:
            if self.running():
                raise RuntimeError("Уже запущено")
            c = checks()
            if not c["ffmpeg"]:
                raise RuntimeError("Не найден ffmpeg. Установите его (см. README) и перезапустите меню.")
            if not c["streamlink"]:
                raise RuntimeError("Не найден streamlink. Выполните: pip install streamlink")
            if cfg.subtitles and not c["whisper"]:
                raise RuntimeError("Для субтитров нужен faster-whisper: pip install faster-whisper")
            self.stop_ev = threading.Event()
            self.state = {"running": True, "channel": cfg.channel, "scores": [],
                          "threshold": None, "spikes": 0}
            self.thread = threading.Thread(
                target=self._work, args=(cfg, self.stop_ev, self.state), daemon=True)
            self.thread.start()

    def _work(self, cfg, stop, state):
        try:
            run(cfg, stop, self.log, state)
        except Exception as e:
            self.log(f"Ошибка: {e}")
            state["running"] = False

    def stop(self):
        self.stop_ev.set()


S = Session()


def checks():
    try:
        import faster_whisper  # noqa: F401
        whisper = True
    except ImportError:
        whisper = False
    return {"ffmpeg": bool(shutil.which("ffmpeg")),
            "streamlink": bool(shutil.which("streamlink")),
            "whisper": whisper}


def list_clips():
    if not os.path.isdir(OUT_DIR):
        return []
    files = [f for f in os.listdir(OUT_DIR) if f.endswith(".mp4") and "_clip_" in f]
    files.sort(key=lambda f: os.path.getmtime(os.path.join(OUT_DIR, f)), reverse=True)
    return files[:50]


def build_config(d):
    sens = float(d.get("sensitivity", 3.0))  # σ: меньше = чувствительнее
    return Config(
        channel=parse_channel(d.get("channel", "")),
        out_dir=OUT_DIR,
        spike_sigma=max(1.0, min(sens, 6.0)),
        min_msgs=max(1, int(d.get("min_msgs", 15))),
        clip_before_sec=max(5, min(int(d.get("before", 20)), 90)),
        clip_after_sec=max(3, min(int(d.get("after", 10)), 60)),
        vertical=bool(d.get("vertical", True)),
        subtitles=bool(d.get("subtitles", False)),
        language=d.get("language", "ru"),
        test_mode=bool(d.get("test_mode", False)),
    )


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/":
            with open(os.path.join(HERE, "ui.html"), "rb") as f:
                body = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            self._json({"state": S.state, "running": S.running(), "logs": list(S.logs),
                        "clips": list_clips(), "checks": checks()})
        elif self.path.startswith("/clips/"):
            self._serve_clip(unquote(self.path[len("/clips/"):]))
        else:
            self.send_error(404)

    def _serve_clip(self, name):
        path = os.path.join(OUT_DIR, os.path.basename(name))
        if not name.endswith(".mp4") or not os.path.isfile(path):
            return self.send_error(404)
        size = os.path.getsize(path)
        start, end, code = 0, size - 1, 200
        rng = self.headers.get("Range", "")
        if rng.startswith("bytes="):  # нужен для перемотки видео в браузере
            a, _, b = rng[6:].partition("-")
            start = int(a or 0)
            end = int(b) if b else size - 1
            code = 206
        end = min(end, size - 1)
        self.send_response(code)
        self.send_header("Content-Type", mimetypes.guess_type(path)[0] or "video/mp4")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if code == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = f.read(min(65536, left))
                if not chunk:
                    break
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break
                left -= len(chunk)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        try:
            data = json.loads(self.rfile.read(n) or b"{}")
            if self.path == "/api/start":
                S.start(build_config(data))
                S.log(f"Запуск: {data.get('channel')}")
                return self._json({"ok": True})
            if self.path == "/api/stop":
                S.stop()
                return self._json({"ok": True})
        except (ValueError, RuntimeError) as e:
            return self._json({"ok": False, "error": str(e)}, 400)
        self.send_error(404)


def serve(open_browser=True):
    os.makedirs(OUT_DIR, exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    url = f"http://127.0.0.1:{PORT}"
    print(f"clipbot: меню открыто на {url}  (Ctrl+C — выход)")
    if open_browser:
        threading.Timer(0.8, webbrowser.open, args=(url,)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        S.stop()
        print("Выход.")
