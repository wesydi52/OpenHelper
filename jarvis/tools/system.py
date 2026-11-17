"""Управление компьютером. Опасные действия требуют подтверждения."""
import os
import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path

from .registry import S

OS = platform.system()  # Linux / Darwin / Windows


def _run(cmd, timeout=30) -> str:
    r = subprocess.run(cmd, shell=isinstance(cmd, str), capture_output=True, text=True, timeout=timeout)
    out = (r.stdout + r.stderr).strip()
    return (out[:3000] or "(нет вывода)") + ("" if r.returncode == 0 else f"\n[код возврата {r.returncode}]")


def open_app(name: str) -> str:
    if OS == "Windows":
        os.startfile(name)  # noqa
    elif OS == "Darwin":
        subprocess.Popen(["open", "-a", name])
    else:
        exe = shutil.which(name) or shutil.which(name.lower())
        if not exe:
            return f"Приложение «{name}» не найдено в PATH."
        subprocess.Popen([exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return f"Запускаю {name}."


def set_volume(percent: int) -> str:
    percent = max(0, min(100, percent))
    if OS == "Darwin":
        return _run(["osascript", "-e", f"set volume output volume {percent}"]) and f"Громкость {percent}%."
    if OS == "Linux":
        if shutil.which("pactl"):
            _run(["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{percent}%"])
        elif shutil.which("amixer"):
            _run(["amixer", "sset", "Master", f"{percent}%"])
        else:
            return "Не нашёл pactl/amixer."
        return f"Громкость {percent}%."
    return "Регулировка громкости на этой ОС пока не поддерживается."


def register(reg, cfg, store):
    @reg.add("open_app", "Запустить приложение по имени.", {"name": S("Имя программы")}, ["name"])
    def _open_app(name: str):
        return open_app(name)

    @reg.add("open_url", "Открыть адрес в браузере.", {"url": S("URL")}, ["url"])
    def open_url(url: str):
        webbrowser.open(url)
        return f"Открыл {url}."

    @reg.add("set_volume", "Установить громкость 0-100.", {"percent": S("Громкость", "integer")}, ["percent"])
    def _vol(percent: int):
        return set_volume(percent)

    @reg.add("system_info", "Информация о системе: ОС, диск, память.")
    def system_info():
        du = shutil.disk_usage(Path.home())
        return (f"{platform.platform()}, Python {platform.python_version()}\n"
                f"Диск: свободно {du.free // 2**30} ГБ из {du.total // 2**30} ГБ")

    @reg.add("find_files", "Найти файлы по части имени в домашней папке.",
             {"pattern": S("Часть имени файла"), "limit": S("Максимум результатов", "integer")}, ["pattern"])
    def find_files(pattern: str, limit: int = 20):
        res = []
        for p in Path.home().rglob(f"*{pattern}*"):
            if any(part.startswith(".") for part in p.parts[len(Path.home().parts):]):
                continue
            res.append(str(p))
            if len(res) >= limit:
                break
        return "\n".join(res) or "Ничего не найдено."

    @reg.add("read_file", "Прочитать текстовый файл (до 4000 символов).", {"path": S("Путь")}, ["path"])
    def read_file(path: str):
        return Path(path).expanduser().read_text(encoding="utf-8", errors="replace")[:4000]

    @reg.add("run_command", "Выполнить команду в оболочке. ВСЕГДА требует подтверждения пользователя.",
             {"command": S("Команда")}, ["command"], confirm=True)
    def run_command(command: str):
        return _run(command, timeout=60)
