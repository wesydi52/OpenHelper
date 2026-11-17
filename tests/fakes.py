"""Подставные ПК, Spotify, сервисы и пылесос для тестов (Windows, звука и сети здесь нет)."""
from datetime import datetime
from pathlib import Path

from jarvis.assistant import Assistant
from jarvis.config import Config
from jarvis.pc import Unsupported
from jarvis.spotify import NoDevice, SpotifyError
from jarvis.store import Store
from jarvis.vacuum import VacuumBackend, VacuumError

NOW = datetime(2026, 11, 17, 10, 0)  # вторник


class FakePc:
    os = "Windows"

    def __init__(self):
        self.calls = []
        self.running = set()
        self.muted = False
        self.clipboard = ""
        self.youtube_tab = True
        self.fail = None

    def _rec(self, *c):
        self.calls.append(c)
        if self.fail:
            raise self.fail

    def set_volume(self, pct):
        self._rec("set_volume", pct)
        return max(0, min(100, pct))

    def change_volume(self, d):
        self._rec("change_volume", d)

    def set_mute(self, want):
        self._rec("set_mute", want)
        changed, self.muted = self.muted != want, want
        return changed

    def media(self, what):
        self._rec("media", what)

    def open_url(self, url):
        self._rec("open_url", url)

    def start(self, target):
        self._rec("start", target)

    def is_running(self, image):
        return image.lower() in {x.lower() for x in self.running}

    def launch(self, name):
        self._rec("launch", name)
        if name in ("dota", "дота") and "steam.exe" not in self.running:
            return "steam_started"
        return "ok"

    def close(self, image):
        self._rec("close", image)
        if image.lower() in {x.lower() for x in self.running}:
            self.running.discard(image)
            return "closed"
        return "not_running"

    def power(self, action):
        self._rec("power", action)

    def minimize_all(self):
        self._rec("minimize_all")

    def folder(self, key):
        self._rec("folder", key)
        return Path("C:/Users/x") / key

    def screenshot(self):
        self._rec("screenshot")
        return Path("C:/Users/x/Pictures/Скриншоты/s.png")

    def clipboard_get(self):
        return self.clipboard

    def type_text(self, text):
        self._rec("type_text", text)

    def bluetooth(self, on):
        self._rec("bluetooth", on)
        return True

    def wifi_on(self):
        self._rec("wifi_on")
        return True

    def wifi_reconnect(self):
        self._rec("wifi_reconnect")
        return True

    def audio_output(self, device):
        self._rec("audio_output", device)
        return "ok"

    def youtube_key(self, letter, repeat=1):
        self._rec("youtube_key", letter, repeat)
        return self.youtube_tab

    def status(self):
        return "Процессор загружен на 10 процентов."

    def beep(self, n=3):
        self._rec("beep", n)


class FakeSpotify:
    def __init__(self, configured=True):
        self.configured = configured
        self.calls = []
        self.playing = True
        self.error = None
        self.track = {"name": "Ниа", "artist": "Исполнитель", "uri": "spotify:track:1"}

    def _do(self, *c):
        self.calls.append(c)
        if self.error:
            raise self.error

    def search_track(self, q):
        self._do("search", q)
        return self.track

    def play(self, uri=None, context_uri=None):
        self._do("play", uri, context_uri)

    def pause(self):
        self._do("pause")

    def resume(self):
        self._do("resume")

    def next(self):
        self._do("next")

    def previous(self):
        self._do("previous")

    def current(self):
        self._do("current")
        return {"id": "1", "name": "Ниа", "artist": "Исполнитель", "is_playing": self.playing}

    def like_current(self):
        self._do("like")
        return {"name": "Ниа"}

    def find_playlist(self, name):
        self._do("playlist", name)
        return {"name": "Вечерний", "uri": "spotify:playlist:9"} if "вечер" in name.lower() else None

    def pause_if_playing(self):
        self._do("pause_if_playing")
        return self.playing


class FakeServices:
    def __init__(self):
        self.calls = []

    def _r(self, name, *a):
        self.calls.append((name, *a))
        return f"{name}:{','.join(map(str, a))}"

    def rate_text(self, w):
        return self._r("rate", w)

    def translate(self, text, lang):
        self.calls.append(("translate", text, lang))
        return f"[{lang}] {text}"

    def meta(self):
        return self._r("meta")

    def counters(self, hero):
        return self._r("counters", hero)

    def last_match(self):
        return self._r("last_match")

    def twitch_live(self):
        return self._r("twitch")


class FakeVacuum(VacuumBackend):
    def __init__(self):
        self.calls = []

    def start(self, room, mode):
        self.calls.append(("start", room, mode))

    def stop(self):
        self.calls.append(("stop",))

    def dock(self):
        self.calls.append(("dock",))


def make(tmp_path, monkeypatch, spotify_configured=True, env=None):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    for k in ("JARVIS_TG_TOKEN", "JARVIS_TG_ALLOW_PC", "JARVIS_AUDIO_DEVICES", "JARVIS_MAIL_USER"):
        monkeypatch.delenv(k, raising=False)
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    clock = {"now": NOW}
    store = Store(tmp_path / "d.json")
    pc, sp, svc, vac = FakePc(), FakeSpotify(spotify_configured), FakeServices(), FakeVacuum()
    a = Assistant(Config(), store, now=lambda: clock["now"], pc=pc, spotify=sp, services=svc, vacuum=vac)
    a.fk = type("Fakes", (), {"pc": pc, "sp": sp, "svc": svc, "vac": vac, "clock": clock, "store": store})
    return a
