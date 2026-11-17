"""Погода, новости и поиск в интернете."""
import re
import xml.etree.ElementTree as ET

import requests

from .registry import S

WMO = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно",
       45: "туман", 48: "изморозь", 51: "лёгкая морось", 53: "морось", 55: "сильная морось",
       61: "небольшой дождь", 63: "дождь", 65: "сильный дождь", 71: "небольшой снег",
       73: "снег", 75: "сильный снег", 80: "ливень", 81: "сильный ливень",
       95: "гроза", 96: "гроза с градом", 99: "сильная гроза с градом"}
UA = {"User-Agent": "JarvisAssistant/1.0"}


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=15, **kw)
    r.raise_for_status()
    return r


def weather(city: str, days: int = 3) -> str:
    geo = _get("https://geocoding-api.open-meteo.com/v1/search",
               params={"name": city, "count": 1, "language": "ru"}).json()
    if not geo.get("results"):
        return f"Город «{city}» не найден."
    g = geo["results"][0]
    w = _get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
        "forecast_days": max(1, min(days, 7)),
    }).json()
    c = w["current"]
    lines = [f"{g['name']}: сейчас {c['temperature_2m']:.0f}°C "
             f"(ощущается как {c['apparent_temperature']:.0f}°C), "
             f"{WMO.get(c['weather_code'], 'без описания')}, ветер {c['wind_speed_10m']:.0f} км/ч."]
    d = w["daily"]
    for i, day in enumerate(d["time"]):
        lines.append(f"{day}: {d['temperature_2m_min'][i]:.0f}…{d['temperature_2m_max'][i]:.0f}°C, "
                     f"{WMO.get(d['weather_code'][i], '')}, осадки {d['precipitation_sum'][i]} мм")
    return "\n".join(lines)


def news(feeds: list, limit: int = 5) -> str:
    out = []
    for url in feeds:
        try:
            root = ET.fromstring(_get(url).content)
        except Exception as e:  # лента может быть недоступна — не валим всё
            out.append(f"[{url}: ошибка {e}]")
            continue
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description") or "").strip()
            if title:
                out.append(f"- {title}" + (f" — {desc[:160]}" if desc else ""))
            if len([o for o in out if o.startswith("- ")]) >= limit:
                break
        if len([o for o in out if o.startswith("- ")]) >= limit:
            break
    return "\n".join(out) or "Новостей не найдено."


def web_search(query: str, limit: int = 5) -> str:
    try:
        from ddgs import DDGS
    except ImportError:
        return "Для поиска установите пакет: pip install ddgs"
    results = DDGS().text(query, max_results=limit)
    if not results:
        return "Ничего не найдено."
    return "\n".join(f"- {r['title']}: {r['body']} ({r['href']})" for r in results)


def fetch_page(url: str, max_chars: int = 4000) -> str:
    html = _get(url).text
    html = re.sub(r"(?is)<(script|style|noscript).*?</\1>", " ", html)
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)).strip()
    return text[:max_chars]


def register(reg, cfg, store):
    @reg.add("get_weather", "Текущая погода и прогноз. Если город не указан — город пользователя.",
             {"city": S("Название города"), "days": S("Дней прогноза 1-7", "integer")})
    def _weather(city: str = "", days: int = 3):
        return weather(city or cfg.city, days)

    @reg.add("get_news", "Свежие новости из RSS-лент.", {"limit": S("Сколько новостей", "integer")})
    def _news(limit: int = 5):
        return news(cfg.news_feeds, limit)

    @reg.add("web_search", "Поиск информации в интернете.",
             {"query": S("Поисковый запрос"), "limit": S("Число результатов", "integer")}, ["query"])
    def _search(query: str, limit: int = 5):
        return web_search(query, limit)

    @reg.add("fetch_page", "Скачать и прочитать текст веб-страницы по URL.",
             {"url": S("Адрес страницы")}, ["url"])
    def _fetch(url: str):
        return fetch_page(url)
