"""Пылесос Dreame L40s Pro Ultra: слой команд («убери на кухне», «помой пол»…) и подключаемый бэкенд.

⚠️ Бэкенд для облака Dreamehome НЕ реализован: у Dreame нет открытого документированного API, а подбирать
недокументированный протокол вслепую без устройства и сети нельзя. Сейчас работает заглушка с честным ответом.
Рекомендованный путь, когда понадобится: интеграция Dreame для Home Assistant — тогда пишется
HomeAssistantBackend с теми же тремя методами (start/stop/dock). Весь диалог ниже проверен на подставном бэкенде.
"""
import re

ROOMS = {
    "kitchen": ("кухн",), "bedroom": ("спальн",), "living": ("гостин", "зал"),
    "hall": ("прихож", "коридор"), "bathroom": ("ванн",),
}
ROOM_NAMES = {"kitchen": "кухню", "bedroom": "спальню", "living": "гостиную", "hall": "прихожую и коридор",
              "bathroom": "ванную", "all": "всю квартиру"}
ROOM_IN = {"kitchen": "кухне", "bedroom": "спальне", "living": "гостиной", "hall": "прихожей и коридоре",
           "bathroom": "ванной", "all": "всей квартире"}


class VacuumError(Exception):
    pass


class VacuumBackend:
    def start(self, room: str, mode: str):   # mode: "dry" | "wet"
        raise NotImplementedError

    def stop(self):
        raise NotImplementedError

    def dock(self):
        raise NotImplementedError


class NotConfigured(VacuumBackend):
    MSG = ("Пылесос пока не подключён: у Dreame нет открытого API, нужен мост через Home Assistant "
           "(см. JARVIS_PLAN.md).")

    def start(self, room, mode):
        raise VacuumError(self.MSG)

    stop = dock = lambda self: (_ for _ in ()).throw(VacuumError(self.MSG))


def find_room(low: str) -> str | None:
    if re.search(r"\b(?:всю\s+квартиру|везде|весь\s+дом|всё|все\s+комнаты)\b", low):
        return "all"
    for key, stems in ROOMS.items():
        if any(re.search(rf"\b{s}", low) for s in stems):
            return key
    return None


def find_mode(low: str) -> str | None:
    """«помой»/«протри» → влажная; «подмети»/«пропылесось» → сухая; иначе None (спросить владельца)."""
    if re.search(r"\b(?:помой|мыть|вымой|протри|влажн\w+)", low):
        return "wet"
    if re.search(r"\b(?:подмети|пропылесось|сух\w+)", low):
        return "dry"
    return None
