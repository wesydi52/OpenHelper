"""Настройки Джарвиса: всё из переменных окружения. Облачных ИИ-сервисов нет.

Секреты (токены, ключи, Dota ID, список важных отправителей) берутся только из переменных окружения —
в репозиторий они не попадают.
"""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    p = Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _env(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _list(name: str, default: str) -> list:
    return [x.strip().lower() for x in _env(name, default).split(",") if x.strip()]


def _pairs(name: str, default: str = "") -> dict:
    """'наушники=Headphones;колонки=Speakers' -> {'наушники': 'Headphones', ...}"""
    out = {}
    for part in _env(name, default).split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            if k.strip() and v.strip():
                out[k.strip().lower()] = v.strip()
    return out


# Ленты «язык|адрес». Польские и украинские — по умолчанию, русские — по запросу (решение владельца).
# Адреса не проверены вживую — при необходимости задать свои в JARVIS_NEWS_FEEDS.
DEFAULT_FEEDS = ("pl|https://tvn24.pl/najnowsze.xml,pl|https://www.polsatnews.pl/rss/wszystkie.xml,"
                 "uk|https://www.pravda.com.ua/rss/view_news/,uk|https://www.ukrinform.ua/rss/block-lastnews,"
                 "ru|https://lenta.ru/rss/news,ru|https://feeds.bbci.co.uk/russian/rss.xml")


@dataclass
class Config:
    home: Path = field(default_factory=_home)
    city: str = field(default_factory=lambda: _env("JARVIS_CITY", "Варшава"))
    timezone: str = field(default_factory=lambda: _env("JARVIS_TZ", "Europe/Warsaw"))
    user_name: str = field(default_factory=lambda: _env("JARVIS_USER"))
    # Как Джарвис обращается к владельцу в официальных репликах («Прошу прощения, сэр…»)
    address: str = field(default_factory=lambda: _env("JARVIS_ADDRESS", "сэр"))
    # Во сколько раз в день напоминать о журнале непонятных фраз (ЧЧ:ММ)
    review_time: str = field(default_factory=lambda: _env("JARVIS_REVIEW_TIME", "20:00"))
    # Слово активации + варианты, как его часто «слышит» распознавание
    wake_words: list = field(default_factory=lambda: _list(
        "JARVIS_WAKE_WORDS", "джарвис,жарвис,джарвиз,джервис,джарвес,jarvis"))
    language: str = field(default_factory=lambda: _env("JARVIS_LANG", "ru-RU"))
    # Офлайн-распознавание: путь к распакованной модели Vosk (vosk-model-small-ru).
    vosk_model: str = field(default_factory=lambda: _env("JARVIS_VOSK_MODEL"))
    # Озвучка: "pyttsx3" (системные голоса) или "piper" (нейросетевая, офлайн)
    tts_engine: str = field(default_factory=lambda: _env("JARVIS_TTS", "pyttsx3"))
    # Модели Piper по языкам: 'ru=C:\\piper\\ru.onnx;pl=...;uk=...;en=...'
    piper_models: dict = field(default_factory=lambda: _pairs("JARVIS_PIPER_MODELS"))
    # Telegram
    tg_token: str = field(default_factory=lambda: _env("JARVIS_TG_TOKEN"))
    tg_owner: str = field(default_factory=lambda: _env("JARVIS_TG_OWNER"))
    # Через сколько минут без реакции на ПК продублировать напоминание в Telegram
    tg_dup_minutes: int = field(default_factory=lambda: int(_env("JARVIS_TG_DUP_MINUTES", "15")))
    tg_allow_pc: bool = field(default_factory=lambda: _env("JARVIS_TG_ALLOW_PC") == "1")
    # Сколько секунд после ответа принимать уточнения без повтора слова «Джарвис»
    dialog_seconds: int = field(default_factory=lambda: int(_env("JARVIS_DIALOG", "10")))
    # Опасные действия (перезапуск, выключение, сон): секунд на «отмена»
    countdown_seconds: int = field(default_factory=lambda: int(_env("JARVIS_COUNTDOWN", "15")))
    # Громкость: шаг «громче/тише» в процентах и уровень режима «работа»
    volume_step: int = field(default_factory=lambda: int(_env("JARVIS_VOLUME_STEP", "20")))
    work_volume: int = field(default_factory=lambda: int(_env("JARVIS_WORK_VOLUME", "30")))
    # Устройства вывода звука: 'наушники=Имя в Windows;колонки=...;блютуз=...'
    audio_devices: dict = field(default_factory=lambda: _pairs("JARVIS_AUDIO_DEVICES"))
    # Почта (IMAP, только чтение). Для Gmail нужен «пароль приложения».
    mail_user: str = field(default_factory=lambda: _env("JARVIS_MAIL_USER"))
    mail_password: str = field(default_factory=lambda: _env("JARVIS_MAIL_PASSWORD"))
    imap_host: str = field(default_factory=lambda: _env("JARVIS_IMAP_HOST", "imap.gmail.com"))
    # Важные отправители (подстроки адреса/имени через запятую) — их письма читаются первыми
    mail_vip: list = field(default_factory=lambda: _list("JARVIS_MAIL_VIP", ""))
    news_feeds: list = field(default_factory=lambda: [
        x.strip() for x in _env("JARVIS_NEWS_FEEDS", DEFAULT_FEEDS).split(",") if x.strip()])
    # Spotify (Premium): Client ID приложения и refresh-токен (получить: python -m jarvis.spotify_auth)
    spotify_client_id: str = field(default_factory=lambda: _env("JARVIS_SPOTIFY_CLIENT_ID"))
    spotify_refresh_token: str = field(default_factory=lambda: _env("JARVIS_SPOTIFY_REFRESH_TOKEN"))
    alarm_playlist: str = field(default_factory=lambda: _env("JARVIS_ALARM_PLAYLIST"))
    # Twitch (подписки): Client ID, пользовательский токен (scope user:read:follows) и ваш user id
    twitch_client_id: str = field(default_factory=lambda: _env("JARVIS_TWITCH_CLIENT_ID"))
    twitch_token: str = field(default_factory=lambda: _env("JARVIS_TWITCH_TOKEN"))
    twitch_user_id: str = field(default_factory=lambda: _env("JARVIS_TWITCH_USER_ID"))
    # Dota: ваш account id (число из профиля Dotabuff/OpenDota) — для «моего последнего матча»
    dota_id: str = field(default_factory=lambda: _env("JARVIS_DOTA_ID"))
    # Пылесос Dreame: пока только заготовка (см. jarvis/vacuum.py)
    vacuum_backend: str = field(default_factory=lambda: _env("JARVIS_VACUUM", ""))
