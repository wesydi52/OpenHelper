"""Автозапуск Джарвиса при входе в Windows через Планировщик заданий (schtasks).

**Вживую на Windows не проверено.** Токены и ключи берутся из переменных окружения пользователя (setx),
которые задача наследует при входе. Подробности — JARVIS.md.
"""
import os
import subprocess
import sys

TASK_NAME = "Jarvis"


def task_command(python: str, args: str, workdir: str) -> list:
    """schtasks: запуск при входе пользователя, без окна консоли (pythonw), из папки проекта."""
    pythonw = python[:-10] + "pythonw.exe" if python.lower().endswith("python.exe") else python
    action = f'cmd /c cd /d "{workdir}" && "{pythonw}" -m jarvis {args}'
    return ["schtasks", "/Create", "/TN", TASK_NAME, "/TR", action, "/SC", "ONLOGON", "/RL", "LIMITED", "/F"]


def remove_command() -> list:
    return ["schtasks", "/Delete", "/TN", TASK_NAME, "/F"]


def _run(cmd):
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return r.returncode, (r.stdout + r.stderr).strip()


def install(args: str = "--voice --telegram", runner=_run, python=None, workdir=None, os_name=None) -> str:
    if (os_name or os.name) != "nt":
        return "Автозапуск настраивается только в Windows."
    rc, out = runner(task_command(python or sys.executable, args, workdir or os.getcwd()))
    return "Автозапуск включён." if rc == 0 else f"Не удалось включить автозапуск: {out}"


def uninstall(runner=_run, os_name=None) -> str:
    if (os_name or os.name) != "nt":
        return "Автозапуск настраивается только в Windows."
    rc, out = runner(remove_command())
    return "Автозапуск выключен." if rc == 0 else f"Не удалось выключить автозапуск: {out}"
