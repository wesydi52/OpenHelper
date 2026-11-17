"""Настройки Джарвиса. Всё берётся из переменных окружения."""
import os
from dataclasses import dataclass, field
from pathlib import Path


def _home() -> Path:
    p = Path(os.environ.get("JARVIS_HOME", Path.home() / ".jarvis"))
    p.mkdir(parents=True, exist_ok=True)
    return p


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    model: str = field(default_factory=lambda: os.environ.get("JARVIS_MODEL", "claude-sonnet-5-5"))
    home: Path = field(default_factory=_home)
    city: str = field(default_factory=lambda: os.environ.get("JARVIS_CITY", "Москва"))
    user_name: str = field(default_factory=lambda: os.environ.get("JARVIS_USER", ""))
    wake_word: str = field(default_factory=lambda: os.environ.get("JARVIS_WAKE_WORD", "джарвис").lower())
    language: str = field(default_factory=lambda: os.environ.get("JARVIS_LANG", "ru-RU"))
    # Почта (IMAP/SMTP). Для Gmail нужен «пароль приложения».
    mail_user: str = field(default_factory=lambda: os.environ.get("JARVIS_MAIL_USER", ""))
    mail_password: str = field(default_factory=lambda: os.environ.get("JARVIS_MAIL_PASSWORD", ""))
    imap_host: str = field(default_factory=lambda: os.environ.get("JARVIS_IMAP_HOST", "imap.gmail.com"))
    smtp_host: str = field(default_factory=lambda: os.environ.get("JARVIS_SMTP_HOST", "smtp.gmail.com"))
    # Новости: RSS-ленты через запятую
    news_feeds: list = field(default_factory=lambda: [
        u for u in os.environ.get(
            "JARVIS_NEWS_FEEDS",
            "https://lenta.ru/rss/news,https://feeds.bbci.co.uk/russian/rss.xml",
        ).split(",") if u.strip()
    ])
