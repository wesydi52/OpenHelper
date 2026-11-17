"""Spotify Web API (нужен Premium). Токены — только из переменных окружения, в репозиторий не попадают.

Без настройки (нет Client ID/refresh-токена) Джарвис управляет музыкой клавишами Windows, а поиск открывает
прямо в приложении (spotify:search:…). **Вживую не проверено** — нужны ваш аккаунт и сеть.
"""
import base64
import hashlib
import secrets
import time
from urllib.parse import quote, urlencode

import requests

API = "https://api.spotify.com/v1"
ACCOUNTS = "https://accounts.spotify.com"
SCOPES = "user-read-playback-state user-modify-playback-state user-library-modify playlist-read-private"


class SpotifyError(Exception):
    pass


class NoDevice(SpotifyError):
    """Нет активного плеера Spotify (приложение не запущено)."""


class Spotify:
    def __init__(self, cfg, http=requests, clock=time.time, sleeper=time.sleep):
        self.client_id, self.refresh_token = cfg.spotify_client_id, cfg.spotify_refresh_token
        self.http, self.clock, self.sleep = http, clock, sleeper
        self._token, self._expires = "", 0.0

    @property
    def configured(self) -> bool:
        return bool(self.client_id and self.refresh_token)

    def _access_token(self) -> str:
        if self._token and self.clock() < self._expires - 30:
            return self._token
        r = self.http.post(f"{ACCOUNTS}/api/token", data={
            "grant_type": "refresh_token", "refresh_token": self.refresh_token, "client_id": self.client_id}, timeout=15)
        if r.status_code != 200:
            raise SpotifyError("Не удалось войти в Spotify: токен недействителен. Получите новый: python -m jarvis.spotify_auth")
        data = r.json()
        self._token, self._expires = data["access_token"], self.clock() + data.get("expires_in", 3600)
        if data.get("refresh_token"):
            self.refresh_token = data["refresh_token"]
        return self._token

    def _call(self, method: str, path: str, retry: bool = True, **kw):
        if not self.configured:
            raise SpotifyError("Spotify не настроен.")
        r = self.http.request(method, API + path, headers={"Authorization": f"Bearer {self._access_token()}"},
                              timeout=15, **kw)
        if r.status_code == 401 and retry:
            self._token = ""
            return self._call(method, path, retry=False, **kw)
        if r.status_code == 404 and "NO_ACTIVE_DEVICE" in (r.text or ""):
            raise NoDevice("Нет активного плеера Spotify.")
        if r.status_code >= 400:
            raise SpotifyError(f"Spotify ответил ошибкой {r.status_code}.")
        return r.json() if r.content and r.status_code != 204 else None

    # ---------- поиск и воспроизведение ----------
    def search_track(self, query: str) -> dict | None:
        data = self._call("GET", "/search", params={"q": query, "type": "track", "limit": 1})
        items = (data or {}).get("tracks", {}).get("items", [])
        if not items:
            return None
        t = items[0]
        return {"name": t["name"], "artist": ", ".join(a["name"] for a in t["artists"]), "uri": t["uri"]}

    def play(self, uri: str | None = None, context_uri: str | None = None):
        body = {}
        if uri:
            body["uris"] = [uri]
        if context_uri:
            body["context_uri"] = context_uri
        self._call("PUT", "/me/player/play", json=body or None)

    def pause(self):
        self._call("PUT", "/me/player/pause")

    def resume(self):
        self.play()

    def next(self):
        self._call("POST", "/me/player/next")

    def previous(self):
        self._call("POST", "/me/player/previous")

    def current(self) -> dict | None:
        data = self._call("GET", "/me/player/currently-playing")
        if not data or not data.get("item"):
            return None
        it = data["item"]
        return {"id": it["id"], "name": it["name"], "artist": ", ".join(a["name"] for a in it["artists"]),
                "is_playing": bool(data.get("is_playing"))}

    def like_current(self) -> dict | None:
        cur = self.current()
        if not cur:
            return None
        self._call("PUT", "/me/tracks", json={"ids": [cur["id"]]})
        return cur

    def find_playlist(self, name: str) -> dict | None:
        data = self._call("GET", "/me/playlists", params={"limit": 50})
        name = name.lower().replace("ё", "е").strip()
        for p in (data or {}).get("items", []):
            if p and name in p["name"].lower().replace("ё", "е"):
                return {"name": p["name"], "uri": p["uri"]}
        return None

    def pause_if_playing(self) -> bool:
        """Поставить на паузу, только если музыка играет (чтобы потом вернуть как было)."""
        cur = self.current()
        if cur and cur["is_playing"]:
            self.pause()
            return True
        return False


def search_uri(query: str) -> str:
    """Поиск прямо в приложении Spotify (работает без API)."""
    return "spotify:search:" + quote(query)


# ---------- получение refresh-токена: python -m jarvis.spotify_auth ----------
def make_pkce():
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def authorization_url(client_id: str, redirect_uri: str, challenge: str, state: str) -> str:
    return ACCOUNTS + "/authorize?" + urlencode({
        "client_id": client_id, "response_type": "code", "redirect_uri": redirect_uri, "scope": SCOPES,
        "code_challenge_method": "S256", "code_challenge": challenge, "state": state})


def exchange_code(client_id: str, redirect_uri: str, code: str, verifier: str, http=requests) -> str:
    r = http.post(f"{ACCOUNTS}/api/token", data={
        "grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri,
        "client_id": client_id, "code_verifier": verifier}, timeout=15)
    if r.status_code != 200:
        raise SpotifyError(f"Spotify не выдал токен (код {r.status_code}).")
    return r.json()["refresh_token"]
