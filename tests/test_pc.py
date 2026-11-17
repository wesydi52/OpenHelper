"""Команды Windows через подменённые runner/клавиши/браузер. Вживую на Windows не проверено."""
import base64
from datetime import datetime

import pytest

from jarvis.calc import evaluate
from jarvis.heroes import find_hero, protracker_name, ru_name, slug
from jarvis.pc import VK, Pc, Unsupported


class Rec:
    def __init__(self, outs=None):
        self.cmds, self.outs = [], dict(outs or {})

    def __call__(self, cmd):
        self.cmds.append(cmd)
        key = " ".join(cmd) if isinstance(cmd, list) else cmd
        for k, v in self.outs.items():
            if k in key:
                return v if isinstance(v, tuple) else (0, v)
        return 0, ""


@pytest.fixture
def pc(tmp_path):
    keys, opened = [], []
    rec = Rec()
    p = Pc(os_name="Windows", runner=rec, key_sender=lambda combo, n: keys.append((combo, n)),
           opener=opened.append, env={"USERPROFILE": str(tmp_path)}, sleeper=lambda s: None,
           now=lambda: datetime(2026, 11, 17, 10, 5, 7))
    p.rec, p.keys, p.opened = rec, keys, opened
    return p


def test_not_windows_is_refused():
    p = Pc(os_name="Linux", runner=lambda c: (0, ""), key_sender=lambda *a: None)
    with pytest.raises(Unsupported):
        p.set_volume(30)
    with pytest.raises(Unsupported):
        p.power("restart")


def test_set_volume_zeroes_then_raises_by_two_percent_steps(pc):
    assert pc.set_volume(30) == 30
    assert pc.keys == [([VK["vol_down"]], 50), ([VK["vol_up"]], 15)]
    pc.keys.clear()
    pc.set_volume(0)
    assert pc.keys == [([VK["vol_down"]], 50)]
    assert pc.set_volume(250) == 100


def test_relative_volume_step_20_is_ten_presses(pc):
    pc.change_volume(20)
    pc.change_volume(-20)
    assert pc.keys == [([VK["vol_up"]], 10), ([VK["vol_down"]], 10)]


def test_mute_state_is_tracked_not_toggled_blindly(pc):
    assert pc.set_mute(True) is True
    assert pc.set_mute(True) is False            # уже без звука — клавишу не жмём
    assert pc.keys == [([VK["mute"]], 1)]
    assert pc.set_mute(False) is True
    pc.set_mute(True)
    pc.change_volume(20)                          # громкость сама снимает mute
    assert pc.muted is False


def test_media_keys(pc):
    pc.media("next")
    pc.media("play_pause")
    assert pc.keys == [([VK["next"]], 1), ([VK["play_pause"]], 1)]


def test_launch_dota_starts_steam_first_when_not_running(pc):
    pc.rec.outs["tasklist"] = (0, "INFO: No tasks are running")
    assert pc.launch("dota") == "steam_started"
    assert pc.rec.cmds[-1] == ["cmd", "/c", "start", "", "steam://open/main"]


def test_launch_dota_when_steam_running(pc):
    pc.rec.outs["tasklist"] = (0, "steam.exe   1234 Console")
    assert pc.launch("dota") == "ok"
    assert pc.rec.cmds[-1] == ["cmd", "/c", "start", "", "steam://rungameid/570"]


def test_launch_discord_and_task_manager(pc):
    pc.launch("дискорд")
    pc.launch("диспетчер задач")
    assert [c[-1] for c in pc.rec.cmds] == ["discord:", "taskmgr"]


def test_close_soft_then_force_only_for_game_processes(pc):
    states = iter(["dota2.exe 1", "dota2.exe 1", ""])        # запущена, после мягкого — ещё жива, после /F — нет
    pc._runner = lambda cmd: ((0, next(states)) if cmd[0] == "tasklist" else (pc.rec(cmd)))
    assert pc.close("dota2.exe") == "closed"
    assert ["taskkill", "/IM", "dota2.exe"] in pc.rec.cmds and ["taskkill", "/F", "/IM", "dota2.exe"] in pc.rec.cmds


def test_close_never_forces_ordinary_programs(pc):
    pc._runner = lambda cmd: ((0, "notepad.exe 1") if cmd[0] == "tasklist" else pc.rec(cmd))
    assert pc.close("notepad.exe") == "failed"
    assert ["taskkill", "/F", "/IM", "notepad.exe"] not in pc.rec.cmds


def test_close_not_running(pc):
    pc.rec.outs["tasklist"] = (0, "INFO: No tasks")
    assert pc.close("steam.exe") == "not_running"


@pytest.mark.parametrize("action,cmd", [
    ("restart", ["shutdown", "/r", "/t", "0"]), ("shutdown", ["shutdown", "/s", "/t", "0"]),
    ("lock", ["rundll32.exe", "user32.dll,LockWorkStation"]),
])
def test_power(pc, action, cmd):
    pc.power(action)
    assert pc.rec.cmds[-1] == cmd


def test_minimize_all_is_win_d(pc):
    pc.minimize_all()
    assert pc.keys == [([VK["lwin"], ord("D")], 1)]


def test_screenshot_goes_to_pictures_screenshots(pc, tmp_path):
    path = pc.screenshot()
    assert path == tmp_path / "Pictures" / "Скриншоты" / "Скриншот_2026-11-17_10-05-07.png"
    assert path.parent.is_dir()
    assert str(path) in pc.rec.cmds[-1][-1]


def test_screenshot_failure_is_reported(pc):
    pc.rec.outs["powershell"] = (1, "access denied")
    with pytest.raises(Unsupported):
        pc.screenshot()


def test_folders(pc, tmp_path):
    assert pc.folder("downloads") == tmp_path / "Downloads"
    assert pc.folder("screenshots") == tmp_path / "Pictures" / "Скриншоты"
    assert pc.rec.cmds[-1][0] == "explorer"


def test_type_text_uses_clipboard_and_restores_it(pc):
    pc.rec.outs["Get-Clipboard"] = (0, "старый буфер")
    pc.type_text("Привет, мир")
    scripts = [c[-1] for c in pc.rec.cmds if c[0] == "powershell"]
    decoded = [base64.b64decode(s.split("FromBase64String('")[1].split("'")[0]).decode() for s in scripts if "FromBase64" in s]
    assert decoded == ["Привет, мир", "старый буфер"]
    assert pc.keys == [([VK["ctrl"], ord("V")], 1)]


def test_bluetooth_on_off_and_missing_adapter(pc):
    assert pc.bluetooth(True) is True
    assert "SetStateAsync('On')" in pc.rec.cmds[-1][-1]
    pc.bluetooth(False)
    assert "SetStateAsync('Off')" in pc.rec.cmds[-1][-1]
    pc.rec.outs["powershell"] = (2, "NO_BLUETOOTH")
    with pytest.raises(Unsupported):
        pc.bluetooth(True)


def test_wifi_reconnect_uses_current_profile(pc):
    pc.rec.outs["show interfaces"] = (0, "    Name : Wi-Fi\n    Profile    : MojaSiec\n")
    assert pc.wifi_reconnect() is True
    assert ["netsh", "wlan", "disconnect"] in pc.rec.cmds
    assert pc.rec.cmds[-1] == ["netsh", "wlan", "connect", "name=MojaSiec"]


@pytest.mark.parametrize("out,expected", [("OK", "ok"), ("NO_MODULE", "no_module"), ("NOT_FOUND", "not_found")])
def test_audio_output(pc, out, expected):
    pc.rec.outs["powershell"] = (0 if out == "OK" else 3, out)
    assert pc.audio_output("Headphones") == expected


def test_audio_output_escapes_quotes(pc):
    pc.audio_output("Jim's 'Phones")
    assert "Jim''s ''Phones" in pc.rec.cmds[-1][-1]


def test_youtube_key_needs_the_tab(pc):
    pc.rec.outs["AppActivate"] = (0, "True")
    assert pc.youtube_key("l", repeat=3) is True
    assert pc.keys == [([ord("L")], 3)]
    pc.keys.clear()
    pc.rec.outs["AppActivate"] = (0, "False")
    assert pc.youtube_key("k") is False and pc.keys == []


# ---------- калькулятор и герои ----------
@pytest.mark.parametrize("text,result", [
    ("сколько будет 15 процентов от 2300", "345"), ("два плюс два", "4"), ("сколько будет 12 умножить на 3", "36"),
    ("десять разделить на 4", "2,5"), ("100 минус 7,5", "92,5"), ("2 х 3", "6"),
    ("привет", None), ("7", None), ("5 разделить на 0", None), ("__import__('os')", None),
])
def test_calc(text, result):
    assert evaluate(text) == result


@pytest.mark.parametrize("text,hero", [
    ("для пуджа", "Pudge"), ("против инвокера кого брать", "Invoker"), ("антимага", "Anti-Mage"),
    ("кристал мейден", "Crystal Maiden"), ("про шторм спирита", "Storm Spirit"), ("лс", "Lifestealer"),
    ("rubick", "Rubick"), ("что-то непонятное", None),
])
def test_find_hero(text, hero):
    assert find_hero(text) == hero


def test_hero_names_and_urls():
    assert ru_name("Pudge") == "Пудж" and slug("Nature's Prophet") == "natures-prophet"
    assert protracker_name("Queen of Pain") == "Queen%20of%20Pain"
