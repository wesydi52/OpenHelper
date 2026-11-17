"""Погода (Open-Meteo), новости (RSS), поиск (DuckDuckGo). Ключи не нужны."""
import re
import xml.etree.ElementTree as ET

import requests

WMO = {0: "ясно", 1: "в основном ясно", 2: "переменная облачность", 3: "пасмурно", 45: "туман",
       48: "изморозь", 51: "лёгкая морось", 53: "морось", 55: "сильная морось", 61: "небольшой дождь",
       63: "дождь", 65: "сильный дождь", 71: "небольшой снег", 73: "снег", 75: "сильный снег",
       80: "ливень", 81: "сильный ливень", 95: "гроза", 96: "гроза с градом", 99: "гроза с градом"}
UA = {"User-Agent": "JarvisAssistant/2.0"}


def _get(url, **kw):
    r = requests.get(url, headers=UA, timeout=15, **kw)
    r.raise_for_status()
    return r


def _find_city(name: str):
    # «в Казани» → пробуем «Казани», «Казан», «Каза» (склонения)
    for cand in (name, name[:-1], name[:-2]):
        if len(cand) < 3:
            continue
        res = _get("https://geocoding-api.open-meteo.com/v1/search",
                   params={"name": cand, "count": 1, "language": "ru"}).json().get("results")
        if res:
            return res[0]
    return None


def weather(city: str, days: int = 2) -> str:
    g = _find_city(city)
    if not g:
        return f"Не нашёл город {city}."
    w = _get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
        "current": "temperature_2m,apparent_temperature,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_sum",
        "forecast_days": max(1, min(days, 7))}).json()
    c, d = w["current"], w["daily"]
    parts = [f"{g['name']}: сейчас {c['temperature_2m']:.0f} градусов, ощущается как "
             f"{c['apparent_temperature']:.0f}, {WMO.get(c['weather_code'], '')}, ветер {c['wind_speed_10m']:.0f} км/ч."]
    for i, day in enumerate(d["time"][1:], 1):
        parts.append(f"{day}: от {d['temperature_2m_min'][i]:.0f} до {d['temperature_2m_max'][i]:.0f}, "
                     f"{WMO.get(d['weather_code'][i], '')}.")
    return " ".join(parts)


def news(feeds: list, limit: int = 5) -> str:
    titles = []
    for url in feeds:
        try:
            root = ET.fromstring(_get(url).content)
        except Exception:
            continue
        for item in root.iter("item"):
            t = re.sub(r"\s+", " ", item.findtext("title") or "").strip()
            if t:
                titles.append(t)
            if len(titles) >= limit:
                return "Главное: " + "; ".join(titles) + "."
    return ("Главное: " + "; ".join(titles) + ".") if titles else "Не удалось получить новости."


def web_search(query: str, limit: int = 3) -> str | None:
    """Короткая выдача или None, если ddgs не установлен."""
    try:
        from ddgs import DDGS
    except ImportError:
        return None
    res = DDGS().text(query, max_results=limit)
    return "\n".join(f"{r['title']}: {r['body'][:150]} ({r['href']})" for r in res) or "Ничего не найдено."
