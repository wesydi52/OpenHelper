"""Настройки Джарвиса: всё из переменных окружения. Внешних ИИ-сервисов нет."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    p = Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis"))
    p.mkdir(parents=True, exist_ok=True)
    return p


def _list(name: str, default: str) -> list:
    return [x.strip().lower() for x in os.environ.get(name, default).split(",") if x.strip()]


@dataclass
class Config:
    home: Path = field(default_factory=_home)
    city: str = field(default_factory=lambda: os.environ.get("JARVIS_CITY", "Москва"))
    user_name: str = field(default_factory=lambda: os.environ.get("JARVIS_USER", ""))
    # Слово активации + варианты, как его часто «слышит» распознавание
    wake_words: list = field(default_factory=lambda: _list(
        "JARVIS_WAKE_WORDS", "джарвис,жарвис,джарвиз,джервис,джарвес,jarvis"))
    language: str = field(default_factory=lambda: os.environ.get("JARVIS_LANG", "ru-RU"))
    # Офлайн-распознавание: путь к распакованной модели Vosk (vosk-model-small-ru).
    # Без неё используется Google Web Speech (нужен интернет).
    vosk_model: str = field(default_factory=lambda: os.environ.get("JARVIS_VOSK_MODEL", ""))
    # Telegram
    tg_token: str = field(default_factory=lambda: os.environ.get("JARVIS_TG_TOKEN", ""))
    tg_owner: str = field(default_factory=lambda: os.environ.get("JARVIS_TG_OWNER", ""))
    tg_allow_pc: bool = field(default_factory=lambda: os.environ.get("JARVIS_TG_ALLOW_PC") == "1")
    # Почта (IMAP). Для Gmail нужен «пароль приложения».
    mail_user: str = field(default_factory=lambda: os.environ.get("JARVIS_MAIL_USER", ""))
    mail_password: str = field(default_factory=lambda: os.environ.get("JARVIS_MAIL_PASSWORD", ""))
    imap_host: str = field(default_factory=lambda: os.environ.get("JARVIS_IMAP_HOST", "imap.gmail.com"))
    news_feeds: list = field(default_factory=lambda: [
        u.strip() for u in os.environ.get(
            "JARVIS_NEWS_FEEDS", "https://lenta.ru/rss/news,https://feeds.bbci.co.uk/russian/rss.xml"
        ).split(",") if u.strip()])
