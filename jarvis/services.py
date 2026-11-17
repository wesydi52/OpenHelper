"""Внешние данные: курсы валют, перевод, статистика Dota (OpenDota), стримы Twitch.

Все запросы идут через подменяемый http-клиент (тесты не ходят в сеть). **Вживую не проверено.**
Облачных ИИ-моделей здесь нет: курсы — open.er-api.com (без ключа), перевод — MyMemory (без ключа),
Dota — OpenDota (открытый API), Twitch — официальный Helix API (нужны ключи владельца).
"""
import re

import requests

from . import heroes
from .fmt import plural

UA = {"User-Agent": "JarvisAssistant/2.0"}
CURRENCIES = {"доллар": "USD", "доллара": "USD", "евро": "EUR", "злотый": "PLN", "злотого": "PLN", "злотых": "PLN",
              "злотые": "PLN"}
LANGS = {"английск": "en", "польск": "pl", "русск": "ru", "украинск": "uk"}
LANG_NAMES = {"en": "по-английски", "pl": "по-польски", "ru": "по-русски", "uk": "по-украински"}


class ServiceError(Exception):
    pass


class Services:
    def __init__(self, cfg, http=requests):
        self.cfg, self.http = cfg, http
        self._heroes = None

    def _get(self, url, **kw):
        try:
            r = self.http.get(url, headers={**UA, **kw.pop("headers", {})}, timeout=15, **kw)
        except Exception as e:  # сеть
            raise ServiceError(f"Нет связи с сервисом: {e}") from e
        if r.status_code != 200:
            raise ServiceError(f"Сервис ответил ошибкой {r.status_code}.")
        return r.json()

    # ---------- валюты ----------
    def rate_text(self, word: str) -> str:
        """Курс в долларах (по решению владельца); «доллар» называем в злотых."""
        code = CURRENCIES[word]
        rates = self._get("https://open.er-api.com/v6/latest/USD")["rates"]
        if code == "USD":
            value, unit = rates["PLN"], "злотого"
            return f"Один доллар стоит {_num(value)} {unit}."
        in_usd = 1 / rates[code]
        name = "евро" if code == "EUR" else "злотый"
        return f"Один {name} стоит {_num(in_usd)} доллара."

    # ---------- перевод ----------
    @staticmethod
    def detect_lang(text: str) -> str:
        if re.search(r"[іїєґ]", text.lower()):
            return "uk"
        if re.search(r"[а-яё]", text.lower()):
            return "ru"
        if re.search(r"[ąćęłńóśźż]", text.lower()):
            return "pl"
        return "en"

    def translate(self, text: str, target: str) -> str:
        source = self.detect_lang(text)
        if source == target:
            return text
        data = self._get("https://api.mymemory.translated.net/get", params={"q": text, "langpair": f"{source}|{target}"})
        out = (data.get("responseData") or {}).get("translatedText")
        if not out or data.get("responseStatus") not in (200, "200"):
            raise ServiceError("Переводчик не вернул результат.")
        return out

    # ---------- Dota (OpenDota) ----------
    def _hero_list(self):
        if self._heroes is None:
            self._heroes = self._get("https://api.opendota.com/api/heroes")
        return self._heroes

    def _hero_id(self, en: str) -> int | None:
        return next((h["id"] for h in self._hero_list() if h["localized_name"] == en), None)

    def _hero_name(self, hero_id: int) -> str:
        en = next((h["localized_name"] for h in self._hero_list() if h["id"] == hero_id), None)
        return heroes.ru_name(en) if en else "неизвестный герой"

    def meta(self, top: int = 5) -> str:
        """Сильные герои сейчас: процент побед в высоких рангах (5–8) среди часто выбираемых."""
        stats = self._get("https://api.opendota.com/api/heroStats")
        rows = []
        for h in stats:
            picks = sum(h.get(f"{n}_pick", 0) for n in range(5, 9))
            wins = sum(h.get(f"{n}_win", 0) for n in range(5, 9))
            if picks:
                rows.append((wins / picks, picks, h["localized_name"]))
        if not rows:
            raise ServiceError("OpenDota не вернул статистику.")
        avg = sum(p for _, p, _ in rows) / len(rows)
        best = sorted((r for r in rows if r[1] >= avg), reverse=True)[:top]
        return "Сильные герои сейчас: " + ", ".join(
            f"{heroes.ru_name(n)} — {w * 100:.0f} процентов побед" for w, _, n in best) + "."

    def counters(self, en: str, top: int = 5) -> str:
        hid = self._hero_id(en)
        if hid is None:
            raise ServiceError("Не нашёл героя в OpenDota.")
        rows = self._get(f"https://api.opendota.com/api/heroes/{hid}/matchups")
        scored = [(r["wins"] / r["games_played"], r["hero_id"]) for r in rows if r.get("games_played", 0) >= 50]
        if not scored:
            raise ServiceError("Мало данных о матчах этого героя.")
        worst = sorted(scored)[:top]       # у кого у героя самый низкий процент побед
        return (f"Против {heroes.ru_name(en)} хорошо играют: " +
                ", ".join(self._hero_name(h) for _, h in worst) + ".")

    def last_match(self) -> str:
        if not self.cfg.dota_id:
            raise ServiceError("Укажите ваш Dota ID в переменной JARVIS_DOTA_ID и откройте профиль в Dota.")
        rows = self._get(f"https://api.opendota.com/api/players/{self.cfg.dota_id}/recentMatches")
        if not rows:
            raise ServiceError("Матчей не нашёл: профиль закрыт или Dota ID неверный.")
        m = rows[0]
        won = (m["player_slot"] < 128) == bool(m["radiant_win"])
        mins = m["duration"] // 60
        return (f"Последний матч: {self._hero_name(m['hero_id'])}, {'победа' if won else 'поражение'}, "
                f"{m['kills']} убийств, {m['deaths']} смертей, {m['assists']} помощи, "
                f"{mins} {plural(mins, 'минута', 'минуты', 'минут')}.")

    # ---------- Twitch ----------
    def twitch_live(self) -> str:
        c = self.cfg
        if not (c.twitch_client_id and c.twitch_token and c.twitch_user_id):
            raise ServiceError("Twitch не настроен: нужны JARVIS_TWITCH_CLIENT_ID, JARVIS_TWITCH_TOKEN и JARVIS_TWITCH_USER_ID.")
        data = self._get("https://api.twitch.tv/helix/streams/followed", params={"user_id": c.twitch_user_id},
                         headers={"Client-Id": c.twitch_client_id, "Authorization": f"Bearer {c.twitch_token}"})
        live = data.get("data", [])
        if not live:
            return "Из ваших подписок сейчас никого нет в эфире."
        return "В эфире: " + "; ".join(
            f"{s['user_name']}" + (f" — {s['game_name']}" if s.get("game_name") else "") for s in live[:8]) + "."


def _num(x: float) -> str:
    return f"{x:.2f}".replace(".", ",")
