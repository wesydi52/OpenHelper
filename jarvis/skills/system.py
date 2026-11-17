"""Управление ПК: приложения, сайты, громкость. Только из локального режима."""
import os
import platform
import shutil
import subprocess
import webbrowser

OS = platform.system()  # Linux / Darwin / Windows

SITES = {"ютуб": "https://youtube.com", "youtube": "https://youtube.com", "гугл": "https://google.com",
         "google": "https://google.com", "почту": "https://mail.google.com", "почта": "https://mail.google.com",
         "вк": "https://vk.com", "гитхаб": "https://github.com", "github": "https://github.com"}
# русское имя -> команда по ОС
APPS = {
    "браузер": None,
    "калькулятор": {"Windows": "calc", "Darwin": "Calculator", "Linux": "gnome-calculator"},
    "блокнот": {"Windows": "notepad", "Darwin": "TextEdit", "Linux": "gedit"},
    "проводник": {"Windows": "explorer", "Darwin": "Finder", "Linux": "xdg-open ."},
    "терминал": {"Windows": "cmd", "Darwin": "Terminal", "Linux": "x-terminal-emulator"},
    "хром": {"Windows": "chrome", "Darwin": "Google Chrome", "Linux": "google-chrome"},
    "телеграм": {"Windows": "telegram", "Darwin": "Telegram", "Linux": "telegram-desktop"},
    "телеграмм": {"Windows": "telegram", "Darwin": "Telegram", "Linux": "telegram-desktop"},
}


def open_app(name: str) -> str:
    name = name.strip().lower()
    if name in SITES:
        webbrowser.open(SITES[name])
        return f"Открываю {name}."
    if name in APPS:
        cmd = APPS[name]
        if cmd is None:
            webbrowser.open("about:blank")
            return "Открываю браузер."
        cmd = cmd.get(OS, name)
    else:
        cmd = name
    try:
        if OS == "Windows":
            os.startfile(cmd.split()[0])  # noqa
        elif OS == "Darwin":
            subprocess.Popen(["open", "-a", cmd])
        else:
            parts = cmd.split()
            if not shutil.which(parts[0]):
                return f"Не нашёл программу {name}."
            subprocess.Popen(parts, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as e:
        return f"Не получилось запустить {name}: {e}"
    return f"Запускаю {name}."


def open_url(url: str) -> str:
    webbrowser.open(url if "://" in url else "https://" + url)
    return f"Открываю {url}."


def search_in_browser(query: str) -> str:
    from urllib.parse import quote
    webbrowser.open("https://duckduckgo.com/?q=" + quote(query))
    return f"Ищу в браузере: {query}."


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))
    try:
        if OS == "Darwin":
            subprocess.run(["osascript", "-e", f"set volume output volume {percent}"], check=True)
        elif OS == "Linux" and shutil.which("pactl"):
            subprocess.run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"], check=True)
        elif OS == "Linux" and shutil.which("amixer"):
            subprocess.run(["amixer", "sset", "Master", f"{percent}%"], check=True)
        else:
            return "На этой системе не могу менять громкость."
    except (subprocess.CalledProcessError, OSError) as e:
        return f"Не получилось изменить громкость: {e}"
    return f"Громкость {percent} процентов."
