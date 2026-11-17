"""Разовая авторизация Spotify: python -m jarvis.spotify_auth

1. В https://developer.spotify.com/dashboard создайте приложение, Redirect URI: http://127.0.0.1:8888/callback
2. Задайте JARVIS_SPOTIFY_CLIENT_ID и запустите этот модуль, откройте ссылку и разрешите доступ.
3. Выданный refresh-токен положите в переменную окружения JARVIS_SPOTIFY_REFRESH_TOKEN (в git не коммитить).
"""
import os
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

from .spotify import authorization_url, exchange_code, make_pkce

REDIRECT = "http://127.0.0.1:8888/callback"


def main():
    client_id = os.environ.get("JARVIS_SPOTIFY_CLIENT_ID", "")
    if not client_id:
        sys.exit("Задайте JARVIS_SPOTIFY_CLIENT_ID (Client ID приложения Spotify).")
    verifier, challenge = make_pkce()
    state = secrets.token_urlsafe(8)
    got = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if q.get("state", [""])[0] == state and "code" in q:
                got["code"] = q["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write("Готово, можно закрыть вкладку.".encode("utf-8"))

        def log_message(self, *a):
            pass

    url = authorization_url(client_id, REDIRECT, challenge, state)
    print("Откройте ссылку и разрешите доступ:\n", url)
    webbrowser.open(url)
    server = HTTPServer(("127.0.0.1", 8888), Handler)
    while "code" not in got:
        server.handle_request()
    token = exchange_code(client_id, REDIRECT, got["code"], verifier)
    print("\nВаш refresh-токен (держите в секрете, в git не коммитить):\n", token)
    print("\nPowerShell: setx JARVIS_SPOTIFY_REFRESH_TOKEN \"<токен>\"")


if __name__ == "__main__":
    main()
