"""Команды Windows: громкость, программы, питание, скриншот, буфер обмена, Bluetooth, звук.

Всё взаимодействие с системой идёт через три подменяемые точки (runner, key_sender, opener), поэтому логика
проверяется тестами на Linux. **Вживую на Windows не проверено** — см. JARVIS_PLAN.md, раздел «Разрыв».
"""
import base64
import os
import platform
import re
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path

# Виртуальные клавиши Windows
VK = {"mute": 0xAD, "vol_down": 0xAE, "vol_up": 0xAF, "next": 0xB0, "prev": 0xB1, "stop": 0xB2,
      "play_pause": 0xB3, "ctrl": 0x11, "lwin": 0x5B}
MEDIA_KEYS = {0xAD, 0xAE, 0xAF, 0xB0, 0xB1, 0xB2, 0xB3}
PCT_PER_PRESS = 2          # одно нажатие громкости в Windows меняет её на 2%

SITES = {
    "ютуб": "https://www.youtube.com", "youtube": "https://www.youtube.com", "ютьюб": "https://www.youtube.com",
    "гугл": "https://www.google.com", "google": "https://www.google.com",
    "яндекс": "https://ya.ru", "твич": "https://www.twitch.tv", "twitch": "https://www.twitch.tv",
    "телеграм веб": "https://web.telegram.org", "telegram web": "https://web.telegram.org",
    "дискорд в браузере": "https://discord.com/app", "стим сайт": "https://store.steampowered.com",
    "стим магазин": "https://store.steampowered.com", "дотабафф": "https://www.dotabuff.com",
    "дотабаф": "https://www.dotabuff.com", "dotabuff": "https://www.dotabuff.com",
    "дотапротрекер": "https://dota2protracker.com", "дота протрекер": "https://dota2protracker.com",
    "дота про трекер": "https://dota2protracker.com", "dota2protracker": "https://dota2protracker.com",
    "телеграм": "https://web.telegram.org", "telegram": "https://web.telegram.org",
    "вк": "https://vk.com", "гитхаб": "https://github.com", "github": "https://github.com",
    "почту": "https://mail.google.com", "почта": "https://mail.google.com",
}
# программа -> (что запускать через «start»; имя процесса для проверки/закрытия)
PROGRAMS = {
    "steam": ("steam://open/main", "steam.exe"), "стим": ("steam://open/main", "steam.exe"),
    "discord": ("discord:", "Discord.exe"), "дискорд": ("discord:", "Discord.exe"),
    "spotify": ("spotify:", "Spotify.exe"), "спотифай": ("spotify:", "Spotify.exe"),
    "dota": ("steam://rungameid/570", "dota2.exe"), "дота": ("steam://rungameid/570", "dota2.exe"),
    "диспетчер задач": ("taskmgr", "Taskmgr.exe"), "диспетчер": ("taskmgr", "Taskmgr.exe"),
    "калькулятор": ("calc", "CalculatorApp.exe"), "блокнот": ("notepad", "notepad.exe"),
    "проводник": ("explorer", "explorer.exe"), "терминал": ("wt", "WindowsTerminal.exe"),
}
# Что можно закрыть голосом: имя -> процесс (браузер владельца — Opera GX, процесс opera.exe)
CLOSABLE = {**{k: v[1] for k, v in PROGRAMS.items()}, "браузер": "opera.exe", "опера": "opera.exe", "opera": "opera.exe"}
# Эти процессы можно закрыть принудительно, если мягкое закрытие не сработало (владелец подтвердил «да»)
FORCE_OK = {"steam.exe", "dota2.exe"}
POWER_CMDS = {
    "restart": ["shutdown", "/r", "/t", "0"],
    "shutdown": ["shutdown", "/s", "/t", "0"],
    # Внимание: при включённой гибернации SetSuspendState уйдёт в гибернацию, а не в сон.
    "sleep": ["rundll32.exe", "powrprof.dll,SetSuspendState", "0,1,0"],
    "lock": ["rundll32.exe", "user32.dll,LockWorkStation"],
}
BLUETOOTH_PS = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | ? { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
Function Await($WinRtTask, $ResultType) {
  $asTask = $asTaskGeneric.MakeGenericMethod($ResultType)
  $netTask = $asTask.Invoke($null, @($WinRtTask)); $netTask.Wait(-1) | Out-Null; $netTask.Result }
[Windows.Devices.Radios.Radio,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
[Windows.Devices.Radios.RadioAccessStatus,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ([Windows.Devices.Radios.Radio]::RequestAccessAsync()) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
$radios = Await ([Windows.Devices.Radios.Radio]::GetRadiosAsync()) ([System.Collections.Generic.IReadOnlyList[Windows.Devices.Radios.Radio]])
$bt = $radios | ? { $_.Kind -eq 'Bluetooth' }
if (-not $bt) { Write-Output 'NO_BLUETOOTH'; exit 2 }
[Windows.Devices.Radios.RadioState,Windows.System.Devices,ContentType=WindowsRuntime] | Out-Null
Await ($bt.SetStateAsync('%STATE%')) ([Windows.Devices.Radios.RadioAccessStatus]) | Out-Null
Write-Output 'OK'
"""


class Unsupported(Exception):
    """Команда доступна только в Windows (или нужная утилита не найдена)."""


class Pc:
    def __init__(self, os_name=None, runner=None, key_sender=None, opener=None, env=None, sleeper=time.sleep,
                 now=datetime.now):
        self.os = os_name or platform.system()
        self._runner = runner or self._default_runner
        self._key_sender = key_sender or self._default_keys
        self._open = opener or webbrowser.open
        self.env = env if env is not None else os.environ
        self.sleep, self.now = sleeper, now
        self.muted = False   # у Windows нет отдельных клавиш mute/unmute — состояние ведём сами (может разойтись)

    # ---------- низкий уровень ----------
    def _need_windows(self):
        if self.os != "Windows":
            raise Unsupported("Эта команда работает только в Windows.")

    @staticmethod
    def _default_runner(cmd):
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=60,
                               encoding="utf-8", errors="replace")
        except (OSError, subprocess.TimeoutExpired) as e:
            return 1, str(e)
        return r.returncode, (r.stdout + r.stderr).strip()

    def run(self, cmd) -> tuple[int, str]:
        self._need_windows()
        return self._runner(cmd)

    def ps(self, script: str) -> tuple[int, str]:
        return self.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script])

    @staticmethod
    def _default_keys(combo, repeat):
        import ctypes
        user32 = ctypes.windll.user32
        for _ in range(repeat):
            for vk in combo:
                user32.keybd_event(vk, 0, 1 if vk in MEDIA_KEYS else 0, 0)
            for vk in reversed(combo):
                user32.keybd_event(vk, 0, (1 if vk in MEDIA_KEYS else 0) | 2, 0)

    def press(self, *vks: int, repeat: int = 1):
        self._need_windows()
        self._key_sender(list(vks), repeat)

    def _home(self) -> Path:
        return Path(self.env.get("USERPROFILE") or Path.home())

    # ---------- звук ----------
    def set_volume(self, percent: int) -> int:
        percent = max(0, min(100, int(percent)))
        self.press(VK["vol_down"], repeat=100 // PCT_PER_PRESS)      # сначала в ноль
        if percent:
            self.press(VK["vol_up"], repeat=percent // PCT_PER_PRESS)
        self.muted = False
        return percent

    def change_volume(self, delta: int):
        key = VK["vol_up"] if delta > 0 else VK["vol_down"]
        self.press(key, repeat=max(1, abs(delta) // PCT_PER_PRESS))
        self.muted = False

    def set_mute(self, want: bool) -> bool:
        """True, если состояние изменилось. Windows умеет только переключать, поэтому ведём учёт сами."""
        if self.muted == want:
            return False
        self.press(VK["mute"])
        self.muted = want
        return True

    def media(self, what: str):
        self.press(VK[what])   # play_pause | next | prev | stop

    def beep(self, times: int = 3):
        self._need_windows()
        import winsound
        for _ in range(times):
            winsound.Beep(1000, 400)
            self.sleep(0.2)

    # ---------- программы и сайты ----------
    def open_url(self, url: str):
        self._open(url if "://" in url else "https://" + url)

    def start(self, target: str):
        self.run(["cmd", "/c", "start", "", target])

    def is_running(self, image: str) -> bool:
        _, out = self.run(["tasklist", "/FI", f"IMAGENAME eq {image}", "/NH"])
        return image.lower() in out.lower()

    def launch(self, name: str) -> str:
        """Запустить программу из таблицы PROGRAMS. Возвращает ключ результата."""
        target, image = PROGRAMS[name]
        if image == "dota2.exe" and not self.is_running("steam.exe"):
            self.start(PROGRAMS["steam"][0])
            return "steam_started"   # аккаунт Steam мог не войти — Джарвис уточнит у владельца
        self.start(target)
        return "ok"

    def close(self, image: str) -> str:
        """Мягкое закрытие; для игр Steam/Dota — принудительно, если не закрылось. 'closed'|'not_running'|'failed'."""
        if not self.is_running(image):
            return "not_running"
        self.run(["taskkill", "/IM", image])
        self.sleep(3)
        if not self.is_running(image):
            return "closed"
        if image.lower() in FORCE_OK:
            self.run(["taskkill", "/F", "/IM", image])
            self.sleep(1)
            return "closed" if not self.is_running(image) else "failed"
        return "failed"

    def power(self, action: str):
        self.run(POWER_CMDS[action])

    def minimize_all(self):
        self.press(VK["lwin"], ord("D"))

    def folder(self, key: str) -> Path:
        home = self._home()
        path = {"downloads": home / "Downloads", "desktop": home / "Desktop", "pictures": home / "Pictures",
                "screenshots": home / "Pictures" / "Скриншоты"}[key]
        path.mkdir(parents=True, exist_ok=True) if key == "screenshots" else None
        self.run(["explorer", str(path)])   # explorer всегда возвращает код 1 — код не проверяем
        return path

    def screenshot(self) -> Path:
        folder = self._home() / "Pictures" / "Скриншоты"
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"Скриншот_{self.now():%Y-%m-%d_%H-%M-%S}.png"
        script = (
            "Add-Type -AssemblyName System.Windows.Forms,System.Drawing;"
            "$b=[System.Windows.Forms.SystemInformation]::VirtualScreen;"
            "$bmp=New-Object System.Drawing.Bitmap $b.Width,$b.Height;"
            "$g=[System.Drawing.Graphics]::FromImage($bmp);"
            "$g.CopyFromScreen($b.Location,[System.Drawing.Point]::Empty,$b.Size);"
            f"$bmp.Save('{str(path).replace(chr(39), chr(39) * 2)}',[System.Drawing.Imaging.ImageFormat]::Png)")
        rc, out = self.ps(script)
        if rc != 0:
            raise Unsupported(f"Не удалось сделать скриншот: {out or rc}")
        return path

    # ---------- буфер обмена и ввод текста ----------
    def clipboard_get(self) -> str:
        _, out = self.ps("Get-Clipboard -Raw")
        return out

    def clipboard_set(self, text: str):
        b64 = base64.b64encode(text.encode("utf-8")).decode("ascii")   # без проблем с кодировкой кириллицы
        self.ps(f"Set-Clipboard -Value ([Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('{b64}')))")

    def type_text(self, text: str):
        """Вставить текст в активное окно через буфер (кириллица) и вернуть прежний буфер."""
        saved = self.clipboard_get()
        self.clipboard_set(text)
        self.press(VK["ctrl"], ord("V"))
        self.sleep(0.4)
        if saved:
            self.clipboard_set(saved)

    # ---------- сеть и звуковые устройства ----------
    def bluetooth(self, on: bool) -> bool:
        rc, out = self.ps(BLUETOOTH_PS.replace("%STATE%", "On" if on else "Off"))
        if "NO_BLUETOOTH" in out:
            raise Unsupported("Bluetooth-адаптер не найден.")
        return rc == 0

    def wifi_on(self) -> bool:
        """Включить адаптер Wi-Fi (нужны права администратора)."""
        rc, _ = self.run(["netsh", "interface", "set", "interface", "name=Wi-Fi", "admin=enabled"])
        return rc == 0

    def wifi_reconnect(self) -> bool:
        _, out = self.run(["netsh", "wlan", "show", "interfaces"])
        m = re.search(r"Profile\s*:\s*(.+)", out)
        if not m:
            _, profiles = self.run(["netsh", "wlan", "show", "profiles"])
            m = re.search(r":\s*(.+)$", profiles, re.M)
        if not m:
            return False
        name = m.group(1).strip()
        self.run(["netsh", "wlan", "disconnect"])
        self.sleep(2)
        rc, _ = self.run(["netsh", "wlan", "connect", f"name={name}"])
        return rc == 0

    def audio_output(self, device: str) -> str:
        """Переключить вывод звука через модуль AudioDeviceCmdlets. 'ok' | 'no_module' | 'not_found'."""
        name = device.replace("'", "''")
        rc, out = self.ps(
            "if (-not (Get-Command Set-AudioDevice -ErrorAction SilentlyContinue)) { Write-Output 'NO_MODULE'; exit 3 };"
            f"$d = Get-AudioDevice -List | Where-Object {{ $_.Type -eq 'Playback' -and $_.Name -like '*{name}*' }} "
            "| Select-Object -First 1; if (-not $d) { Write-Output 'NOT_FOUND'; exit 4 }; "
            "Set-AudioDevice -ID $d.ID | Out-Null; Write-Output 'OK'")
        if "NO_MODULE" in out:
            return "no_module"
        if "NOT_FOUND" in out:
            return "not_found"
        return "ok" if rc == 0 else "not_found"

    # ---------- вкладка YouTube ----------
    def youtube_key(self, letter: str, repeat: int = 1) -> bool:
        """Нажать клавишу плеера YouTube (k — пауза, j/l — ±10 с, f — весь экран) в окне с «YouTube» в заголовке."""
        rc, out = self.ps("(New-Object -ComObject WScript.Shell).AppActivate('YouTube')")
        if "True" not in out:
            return False
        self.sleep(0.4)
        self.press(ord(letter.upper()), repeat=repeat)
        return True

    # ---------- состояние ----------
    def status(self) -> str:
        try:
            import psutil
        except ImportError:
            raise Unsupported("Для состояния компьютера установите пакет psutil.")
        cpu = psutil.cpu_percent(interval=0.5)
        ram = psutil.virtual_memory()
        disk = psutil.disk_usage(str(self._home().anchor or "/"))
        return (f"Процессор загружен на {cpu:.0f} процентов, память занята на {ram.percent:.0f} процентов, "
                f"на диске свободно {disk.free // 2 ** 30} гигабайт. Температуру Windows без датчика не показывает.")
