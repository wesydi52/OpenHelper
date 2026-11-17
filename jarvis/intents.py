"""Команды второго круга: звук, сайты, Spotify, YouTube, питание, режимы, пылесос, таймеры, Dota и т. д.

Extras.route(text, low, source) -> ответ или None (None — не моя команда, разбирает основной маршрутизатор).
Всё, что трогает ПК, проходит через Extras.pc_do(): из Telegram оно выключено по умолчанию.
"""
import re
from datetime import timedelta

from . import fmt
from .common import NO, YES
from .heroes import find_hero, protracker_name, ru_name, slug
from .pc import CLOSABLE, PROGRAMS, SITES, Unsupported
from .ruparse import NUM, parse_when, to_int
from .services import CURRENCIES, LANG_NAMES, LANGS, ServiceError
from .skills import info, mail
from .spoken import Spoken, Urgent
from .spotify import NoDevice, SpotifyError, search_uri
from .vacuum import ROOM_IN, ROOM_NAMES, VacuumError, find_mode, find_room

LABELS = {"restart": "Перезапуск", "shutdown": "Выключение", "sleep": "Спящий режим"}
ASK = {"restart": "Перезапустить компьютер", "shutdown": "Выключить компьютер", "sleep": "Перевести компьютер в спящий режим"}
PROGRAM_TITLES = {"steam": "Steam", "стим": "Steam", "discord": "Discord", "дискорд": "Discord", "spotify": "Spotify",
                  "спотифай": "Spotify", "dota": "Dota 2", "дота": "Dota 2", "диспетчер задач": "диспетчер задач",
                  "диспетчер": "диспетчер задач", "калькулятор": "калькулятор", "блокнот": "блокнот",
                  "проводник": "проводник", "терминал": "терминал"}
FOLDERS = {"загрузки": "downloads", "рабочий стол": "desktop", "картинки": "pictures", "изображения": "pictures",
           "скриншоты": "screenshots"}
MATCH_POSTPONE = timedelta(minutes=20)    # «У вас матч?» — «да» → напомнить позже (решено без владельца)
EXTRA_KINDS = {"confirm_power", "confirm_close", "confirm_work", "spotify_playlist", "spotify_play", "vac_room",
               "vac_mode", "confirm_clip", "match"}


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip(" .,!?«»\"'"))


def _original(text: str, fragment: str) -> str:
    """Тот же фрагмент, но с регистром и диакритикой исходной фразы («Ниа», «Łąka»)."""
    found = re.search(re.escape(fragment), text, re.I)
    return _clean(found.group(0) if found else fragment)


def _program(name: str) -> str | None:
    """«дота 2», «программу дискорд» → ключ PROGRAMS."""
    name = re.sub(r"^(?:программу|приложение|игру|клиент)\s+", "", name.strip())
    name = re.sub(r"\s*(?:2|два)$", "", name) if name.startswith(("дота", "dota")) else name
    return name if name in PROGRAMS else None


class Extras:
    def __init__(self, assistant):
        self.a = assistant
        self.handlers = [
            self.h_dnd, self.h_modes, self.h_timers, self.h_recurring, self.h_volume, self.h_media, self.h_youtube,
            self.h_sites, self.h_power, self.h_close, self.h_windows, self.h_status, self.h_calc, self.h_twitch,
            self.h_dictation, self.h_clipboard, self.h_net, self.h_screenshot, self.h_currency, self.h_translate,
            self.h_dota, self.h_vacuum, self.h_mail, self.h_audio, self.h_news,
        ]

    # ---------- доступ к зависимостям ----------
    cfg = property(lambda s: s.a.cfg)
    store = property(lambda s: s.a.store)
    pc = property(lambda s: s.a.pc)
    sp = property(lambda s: s.a.spotify)
    svc = property(lambda s: s.a.services)
    vac = property(lambda s: s.a.vacuum)
    addr = property(lambda s: s.a.cfg.address)

    def route(self, text: str, low: str, source: str) -> str | None:
        for h in self.handlers:
            r = h(text, low, source)
            if r is not None:
                return r
        return None

    # ---------- общие помощники ----------
    def pc_do(self, source: str, fn):
        """Выполнить действие на ПК: из Telegram — только если разрешено; ошибки превращаем в реплику."""
        if source != "local" and not self.cfg.tg_allow_pc:
            return "Управление компьютером из Telegram выключено."
        try:
            return fn()
        except Unsupported as e:
            return str(e)
        except Exception as e:  # noqa: BLE001 — любая сбойная команда не должна ронять Джарвиса
            return f"Не получилось выполнить команду на компьютере: {e}"

    def ask(self, source, state, question):
        return self.a._ask(source, state, question)

    def sp_do(self, fn, fallback=None):
        """Вызов Spotify с понятными ответами при ошибках."""
        try:
            return fn()
        except NoDevice:
            try:
                self.pc.launch("spotify")
            except Unsupported:
                pass
            return f"Spotify не запущен, {self.addr}. Запустил его — повторите команду через несколько секунд."
        except SpotifyError as e:
            return fallback() if fallback else str(e)

    # ================= «не беспокоить» и режимы =================
    def h_dnd(self, text, low, source):
        if re.fullmatch(r"(?:(?:включи|включить|поставь)\s+)?(?:режим\s+)?не\s+беспокоить", low):
            self.a.set_dnd(True)
            return f"Хорошо, {self.addr}. Напоминания буду присылать только в Telegram."
        if re.fullmatch(r"(?:выключи|отключи|убери|сними|выйди\s+из)\s+(?:режима?\s+)?не\s+беспокоить", low):
            return self.a.set_dnd(False)
        return None

    def h_modes(self, text, low, source):
        if re.fullmatch(r"(?:включи|запусти)\s+(?:режим\s+игры|игровой\s+режим)", low):
            return self.pc_do(source, self.game_on)
        if re.fullmatch(r"(?:выключи|отключи|закончи)\s+(?:режим\s+игры|игровой\s+режим)", low):
            self.store.set_meta("game_mode", False)
            return f"Режим игры выключен, {self.addr}."
        if re.fullmatch(r"(?:включи|запусти)\s+(?:режим\s+работы|рабочий\s+режим)", low):
            return self.ask(source, {"kind": "confirm_work"},
                            f"Закрою Steam и Dota 2, включу «не беспокоить» и сделаю тише, {self.addr}. Подтверждаете?")
        if re.fullmatch(r"(?:выключи|отключи|закончи)\s+(?:режим\s+работы|рабочий\s+режим)", low):
            return self.a.set_dnd(False)
        if re.fullmatch(r"(?:включи\s+)?(?:режим\s+отдыха|перекур|давай\s+перекур)", low):
            self.store.set_meta("game_mode", False)
            return self.pc_do(source, lambda: (self.pc.open_url(SITES["ютуб"]), f"Отдыхайте, {self.addr}. Открываю YouTube.")[1])
        return None

    def game_on(self):
        steps, note = [], ""
        for name in ("дискорд", "спотифай", "дота"):
            if self.pc.launch(name) == "steam_started":
                note = f" Steam не был запущен — открыл его. Войдите в аккаунт, {self.addr}, и повторите запуск Dota."
        self.store.set_meta("game_mode", True)
        return f"Режим игры включён: запускаю Discord, Spotify и Dota 2.{note}"

    def work_on(self):
        res = [self.pc.close("dota2.exe"), self.pc.close("steam.exe")]
        self.pc.set_volume(self.cfg.work_volume)
        self.store.set_meta("game_mode", False)
        self.a.set_dnd(True)
        failed = "failed" in res
        return (f"Режим работы включён: игры закрыты{', но не всё удалось закрыть' if failed else ''}, "
                f"громкость {self.cfg.work_volume} процентов, «не беспокоить» включён.")

    # ================= таймеры и будильник =================
    def h_timers(self, text, low, source):
        m = re.fullmatch(r"(?:поставь\s+|засеки\s+|включи\s+|запусти\s+)?таймер\s+на\s+(.+)", low)
        if m:
            now = self.a.now()
            p = parse_when("через " + m.group(1), now)
            if not p.dt or p.text:
                return f"На сколько поставить таймер, {self.addr}?"
            self.store.add_item("timer", "Таймер", p.dt, [0])
            secs = int((p.dt - now).total_seconds())
            label = (fmt.human_delta(max(1, round(secs / 60))) if secs >= 60
                     else f"{secs} {fmt.plural(secs, 'секунду', 'секунды', 'секунд')}")
            return f"Таймер на {label} запущен."
        m = re.fullmatch(r"(?:поставь\s+)?будильник\s+(?:на\s+|в\s+)?(.+)|разбуди(?:\s+меня)?\s+(.+)", low)
        if m:
            when = m.group(1) or m.group(2)
            now = self.a.now()
            when = re.sub(r"^на\s+(?=\d)", "в ", when)
            if re.match(r"\d", when):
                when = "в " + when
            # «в 7» для будильника — утро, а не 19:00 (у parse_when для таймера час 1–7 без пометки — вечер)
            when = re.sub(r"^(в\s+\d{1,2}(?::\d{2})?)(?!\s*(?:утра|дня|вечера|ночи|\d))\s*$",
                          lambda mm: mm.group(1) + (" утра" if int(re.search(r"\d+", mm.group(1)).group()) < 12 else ""), when)
            p = parse_when(when, now)
            if not p.dt or not p.has_time:
                return f"На какое время поставить будильник, {self.addr}?"
            self.store.add_item("alarm", "Будильник", p.dt, [0])
            return f"Будильник на {fmt.fmt_when(p.dt, now, True)}."
        m = re.fullmatch(r"(?:выключи|отключи|отмени|убери|сбрось)\s+(?:все\s+)?(будильник\w*|таймер\w*)", low)
        if m:
            kind = "alarm" if m.group(1).startswith("будил") else "timer"
            n = 0
            for i in self.store.active():
                if i["kind"] == kind:
                    self.store.delete_item(i["id"])
                    n += 1
            self.a.stop_alarm_sound()
            return (f"{'Будильник' if kind == 'alarm' else 'Таймер'} выключен." if n
                    else f"Активных {'будильников' if kind == 'alarm' else 'таймеров'} нет, {self.addr}.")
        return None

    # ================= повторяющиеся напоминания =================
    def h_recurring(self, text, low, source):
        m = re.fullmatch(r"напоминай(?:те)?(?:\s+мне)?\s+(.+?)\s+кажд\w+\s+(?:(полчаса)|(?:(" + NUM + r")\s+)?(минут\w*|час\w*))", low)
        if m:
            if m.group(2):
                minutes = 30
            else:
                n = to_int(m.group(3)) if m.group(3) else 1
                minutes = n if m.group(4).startswith("мин") else n * 60
            if minutes < 1:
                return None
            title = _clean(m.group(1))
            title = title[:1].upper() + title[1:]
            now = self.a.now()
            self.store.add_recurring(title, minutes, now + timedelta(minutes=minutes))
            return f"Хорошо, {self.addr}. Буду напоминать «{title}» каждые {fmt.human_delta(minutes)}."
        m = re.search(r"(?:(?:останови|выключи|отключи|убери)\s+напоминани\w+|(?:перестань|хватит)\s+напоминать(?:\s+мне)?)"
                      r"\s+(?:про|о|об)\s+(.+)", low)
        if m:
            words = [w[:5] for w in re.findall(r"\w{3,}", m.group(1))]
            hits = [r for r in self.store.recurring() if words and all(w in r["title"].lower().replace("ё", "е") for w in words)]
            for r in hits:
                self.store.delete_recurring(r["id"])
            return (f"Больше не напоминаю: {', '.join(r['title'] for r in hits)}." if hits
                    else f"Такого повторяющегося напоминания нет, {self.addr}.")
        if re.search(r"повторяющ\w+\s+напоминани", low):
            rs = self.store.recurring()
            return ("Повторяющиеся напоминания: " + ". ".join(f"{r['title']} — каждые {fmt.human_delta(r['interval_min'])}"
                                                           for r in rs) + ".") if rs else "Повторяющихся напоминаний нет."
        return None

    # ================= громкость =================
    def h_volume(self, text, low, source):
        step = self.cfg.volume_step
        if re.fullmatch(r"(?:выключи|отключи|убери)\s+звук|без\s+звука|заглуши\s+звук", low):
            return self.pc_do(source, lambda: "Звук выключен." if self.pc.set_mute(True) else "Звук уже выключен.")
        if re.fullmatch(r"(?:включи|верни)\s+звук", low):
            return self.pc_do(source, lambda: "Звук включён." if self.pc.set_mute(False) else "Звук уже включён.")
        if re.fullmatch(r"(?:сделай\s+)?(?:погромче|громче)|(?:прибавь|увеличь|добавь)\s+(?:звук|громкость)", low):
            return self.pc_do(source, lambda: (self.pc.change_volume(step), "Сделал громче.")[1])
        if re.fullmatch(r"(?:сделай\s+)?(?:потише|тише)|(?:убавь|уменьши|убери)\s+(?:звук|громкость)", low):
            return self.pc_do(source, lambda: (self.pc.change_volume(-step), "Сделал тише.")[1])
        m = re.search(rf"(?:громкост\w*|звук)\s*(?:на\s+)?(?:({NUM})(?:\s*процент\w*)?|(половин\w*|максимум|максимальн\w*|минимум))", low)
        if m and len(low.split()) <= 7:
            if m.group(1):
                pct = to_int(m.group(1))
            else:
                word = m.group(2)
                pct = 50 if word.startswith("половин") else 100 if word.startswith("макс") else 0
            return self.pc_do(source, lambda: f"Громкость {self.pc.set_volume(pct)} процентов.")
        return None

    # ================= музыка (Spotify и клавиши) =================
    def music_key(self, what: str):
        self.pc.media(what)

    def h_media(self, text, low, source):
        if re.fullmatch(r"(?:поставь\s+)?(?:музыку\s+|песню\s+)?на\s+паузу|пауза(?:\s+(?:музыке|музыка|музыку))?|останови\s+(?:музыку|песню)", low):
            def pause():
                if self.sp.configured:
                    r = self.sp_do(lambda: (self.sp.pause(), "Поставил на паузу.")[1], lambda: None)
                    if r:
                        return r
                self.music_key("play_pause")   # без Spotify API клавиша только переключает паузу/воспроизведение
                return "Поставил на паузу."
            return self.pc_do(source, pause)
        if re.fullmatch(r"(?:продолжи|продолжай|продолжить)(?:\s+(?:музыку|песню|играть))?|сними\s+с\s+паузы|играй|включи\s+музыку", low):
            def resume():
                if self.sp.configured:
                    r = self.sp_do(lambda: (self.sp.resume(), "Продолжаю.")[1], lambda: None)
                    if r:
                        return r
                self.music_key("play_pause")
                return "Продолжаю."
            return self.pc_do(source, resume)
        if re.fullmatch(r"(?:переключи|смени|включи|поставь)\s+(?:следующ\w+|друг\w+)\s+(?:песню|трек|композицию)|"
                        r"(?:переключи|смени)\s+(?:песню|трек)(?:\s+в\s+(?:спотифай|spotify))?|следующ\w+\s+(?:песня|трек)|дальше|next", low):
            def nxt():
                if self.sp.configured:
                    r = self.sp_do(lambda: (self.sp.next(), "Переключаю.")[1], lambda: None)
                    if r:
                        return r
                self.music_key("next")
                return "Переключаю."
            return self.pc_do(source, nxt)
        if re.fullmatch(r"предыдущ\w+\s+(?:песня|трек|песню)|верни\s+(?:песню|трек)|назад", low):
            return self.pc_do(source, lambda: (self.music_key("prev"), "Возвращаю предыдущую.")[1])
        if re.search(r"что\s+(?:сейчас\s+)?играет|что\s+за\s+песня|какая\s+(?:это\s+)?песня", low):
            if not self.sp.configured:
                return f"Название песни я узнаю только через Spotify API, {self.addr} — он не настроен."
            def now_playing():
                cur = self.sp.current()
                return f"Сейчас играет {cur['name']} — {cur['artist']}." if cur else "Сейчас ничего не играет."
            return self.sp_do(now_playing)
        if re.fullmatch(r"(?:поставь\s+)?лайк(?:\s+(?:песне|треку))?|лайкни(?:\s+(?:песню|трек))?", low):
            if not self.sp.configured:
                return f"Лайк ставится только через Spotify API, {self.addr} — он не настроен."
            def like():
                cur = self.sp.like_current()
                return f"Поставил лайк: {cur['name']}." if cur else "Сейчас ничего не играет."
            return self.sp_do(like)
        m = re.fullmatch(r"(?:включи|запусти|поставь)\s+(?:мой\s+)?плейлист(?:\s+(.+))?", low)
        if m:
            if not self.sp.configured:
                return f"Плейлисты работают только через Spotify API, {self.addr} — он не настроен."
            if not m.group(1):
                return self.ask(source, {"kind": "spotify_playlist"}, f"Какой плейлист, {self.addr}?")
            return self.play_playlist(m.group(1))
        m = (re.fullmatch(r"(?:найди|поищи|включи)\s+(?:песню|трек|композицию)\s+(.+?)(?:\s+в\s+(?:спотифай|spotify))?", low)
             or re.fullmatch(r"(?:найди|поищи|включи)\s+(.+?)\s+в\s+(?:спотифай|spotify)", low))
        if m:
            query = _original(text, m.group(1))
            return self.pc_do(source, lambda: self.find_song(query, source))
        return None

    def find_song(self, query: str, source: str) -> str:
        if not self.sp.configured:   # без API хотя бы откроем поиск в приложении
            self.pc.start(search_uri(query))
            return f"Spotify API не настроен, {self.addr}. Открыл поиск «{query}» в приложении."
        def search():
            t = self.sp.search_track(query)
            if not t:
                return f"Ничего не нашёл по запросу «{query}»."
            return self.ask(source, {"kind": "spotify_play", "uri": t["uri"], "label": f"{t['name']} — {t['artist']}"},
                            f"Нашёл {t['name']}, исполнитель {t['artist']}. Включить, {self.addr}?")
        return self.sp_do(search)

    def play_playlist(self, name: str) -> str:
        def go():
            p = self.sp.find_playlist(name)
            if not p:
                return f"Плейлист «{name}» не нашёл."
            self.sp.play(context_uri=p["uri"])
            return f"Включаю плейлист {p['name']}."
        return self.sp_do(go)

    # ================= YouTube =================
    def h_youtube(self, text, low, source):
        yt = r"(?:ютубе|ютюбе|ютьюбе|youtube|ютуб)"
        m = re.fullmatch(rf"(?:найди|поищи|ищи)\s+(?:на|в)\s+{yt}\s+(.+)", low) or \
            re.fullmatch(rf"(?:найди|поищи)\s+(.+?)\s+(?:на|в)\s+{yt}", low)
        if m:
            q = _clean(m.group(1))
            from urllib.parse import quote
            return self.pc_do(source, lambda: (self.pc.open_url("https://www.youtube.com/results?search_query=" + quote(q)),
                                               f"Открываю результаты поиска на YouTube: {q}.")[1])
        def key(letter, ok, repeat=1):
            return self.pc_do(source, lambda: ok if self.pc.youtube_key(letter, repeat)
                              else f"Не нашёл открытую вкладку YouTube, {self.addr}.")
        if re.fullmatch(r"(?:поставь\s+)?видео\s+на\s+паузу|пауза\s+(?:на\s+)?(?:ютубе|видео)", low):
            return key("k", "Поставил видео на паузу.")
        if re.fullmatch(r"продолжи\s+видео|включи\s+видео", low):
            return key("k", "Продолжаю видео.")
        m = re.fullmatch(rf"перемотай(?:\s+видео)?(\s+назад|\s+вперед)?\s+на\s+(?:({NUM})\s*)?(секунд\w*|минут\w*)", low)
        if m:
            secs = (to_int(m.group(2)) if m.group(2) else 1) * (60 if m.group(3).startswith("мин") else 1)
            return key("j" if (m.group(1) or "").strip() == "назад" else "l", f"Перемотал на {secs} секунд.",
                       max(1, round(secs / 10)))
        if re.fullmatch(r"(?:открой\s+|включи\s+)?(?:на\s+)?(?:весь|полный)\s+экран|выйди\s+из\s+полного\s+экрана", low):
            return key("f", "Готово.")
        return None

    # ================= сайты, программы, папки =================
    def h_sites(self, text, low, source):
        m = re.fullmatch(r"(?:открой|покажи)\s+(дотабафф|дотабаф|dotabuff|дотапротрекер|дота\s*про\s*трекер|dota2protracker)"
                         r"(?:\s+(?:для|про|по|на)?\s*(.+))?", low)
        if m:
            site = "dotabuff" if "буф" in m.group(1) or "баф" in m.group(1) or "buff" in m.group(1) else "protracker"
            main = SITES["дотабафф" if site == "dotabuff" else "дотапротрекер"]
            hero = find_hero(m.group(2)) if m.group(2) else None
            url = main
            if hero:
                url = f"https://www.dotabuff.com/heroes/{slug(hero)}" if site == "dotabuff" \
                    else f"https://dota2protracker.com/hero/{protracker_name(hero)}"
            note = f" Героя «{m.group(2)}» не нашёл, открыл главную." if m.group(2) and not hero else ""
            return self.pc_do(source, lambda: (self.pc.open_url(url),
                                               f"Открываю {'Dotabuff' if site == 'dotabuff' else 'Dota Protracker'}"
                                               + (f": {ru_name(hero)}" if hero else "") + f".{note}")[1])
        m = re.fullmatch(r"(?:открой|запусти|включи|покажи)\s+(?:папку\s+)?(загрузки|рабочий\s+стол|картинки|изображения|скриншоты)", low)
        if m:
            key = FOLDERS[re.sub(r"\s+", " ", m.group(1))]
            return self.pc_do(source, lambda: f"Открываю папку: {self.pc.folder(key)}.")
        m = re.fullmatch(r"(?:открой|запусти|включи|покажи)\s+(.+)", low)
        if not m:
            return None
        name = _clean(m.group(1))
        prog = _program(name)
        if prog:
            def go():
                res = self.pc.launch(prog)
                if res == "steam_started":
                    return (f"Steam не был запущен, {self.addr}. Открыл его — войдите в аккаунт "
                            f"и повторите команду.")
                return f"Запускаю {PROGRAM_TITLES.get(prog, prog)}."
            return self.pc_do(source, go)
        name = re.sub(r"^сайт\s+", "", name)
        if name in SITES:
            return self.pc_do(source, lambda: (self.pc.open_url(SITES[name]), f"Открываю {name}.")[1])
        return None

    # ================= питание, закрытие, окна =================
    def h_power(self, text, low, source):
        action = None
        if re.fullmatch(r"(?:перезапусти|перезагрузи)\s+(?:компьютер|пк|комп|систему)|перезагрузка", low):
            action = "restart"
        elif re.fullmatch(r"выключи\s+(?:компьютер|пк|комп)", low):
            action = "shutdown"
        elif re.fullmatch(r"спящий\s+режим|усыпи\s+(?:компьютер|пк)|засыпай|переведи\s+(?:компьютер|пк)\s+в\s+спящий\s+режим", low):
            action = "sleep"
        elif re.fullmatch(r"заблокируй\s+(?:компьютер|пк|экран)|блокировка", low):
            return self.pc_do(source, lambda: (self.pc.power("lock"), "Блокирую.")[1])
        if not action:
            return None
        if source != "local" and not self.cfg.tg_allow_pc:
            return "Управление компьютером из Telegram выключено."
        return self.ask(source, {"kind": "confirm_power", "action": action}, f"{ASK[action]}, {self.addr}?")

    def h_close(self, text, low, source):
        m = re.fullmatch(r"закрой\s+(?:программу\s+|приложение\s+)?(.+)", low)
        if not m:
            return None
        name = re.sub(r"\s*(?:2|два)$", "", _clean(m.group(1))) if m.group(1).startswith(("дота", "dota")) else _clean(m.group(1))
        image = CLOSABLE.get(name)
        if not image:
            return None
        if source != "local" and not self.cfg.tg_allow_pc:
            return "Управление компьютером из Telegram выключено."
        title = PROGRAM_TITLES.get(name, name)
        return self.ask(source, {"kind": "confirm_close", "image": image, "title": title}, f"Закрыть {title}, {self.addr}?")

    def h_windows(self, text, low, source):
        if re.fullmatch(r"сверни\s+(?:все\s+окна|все|всё)|покажи\s+рабочий\s+стол", low):
            return self.pc_do(source, lambda: (self.pc.minimize_all(), "Свернул.")[1])
        return None

    def h_status(self, text, low, source):
        if re.search(r"как\s+(?:дела\s+у\s+)?(?:компьютер\w*|пк)\b|состояни\w+\s+(?:компьютера|пк)|загрузк\w+\s+(?:процессора|компьютера)|"
                     r"сколько\s+(?:памяти|свободно\s+места)", low):
            return self.pc_do(source, self.pc.status)
        return None

    # ================= прочее без ПК =================
    def h_calc(self, text, low, source):
        m = re.fullmatch(r"(?:сколько\s+будет|посчитай|вычисли|реши)\s+(.+)", low)
        if not m:
            return None
        from .calc import evaluate
        res = evaluate(m.group(1))
        return f"Получится {res}." if res else f"Не смог посчитать, {self.addr}."

    def h_twitch(self, text, low, source):
        if re.search(r"кто\s+(?:сейчас\s+)?(?:в\s+эфире|на\s+твиче|стримит)|стримеры\s+в\s+эфире", low):
            return self._svc(self.svc.twitch_live)
        return None

    def _svc(self, fn):
        try:
            return fn()
        except ServiceError as e:
            return str(e)

    def h_currency(self, text, low, source):
        m = re.search(r"(?:сколько\s+стоит|курс)\s+(доллар\w*|евро|злот\w+)", low)
        if not m:
            return None
        word = m.group(1)
        key = "доллар" if word.startswith("доллар") else "злотый" if word.startswith("злот") else "евро"
        return self._svc(lambda: self.svc.rate_text(key if key != "евро" else "евро"))

    def h_translate(self, text, low, source):
        m = re.fullmatch(r"как\s+(?:будет\s+|сказать\s+)?по[-\s]?(английски|польски|русски|украински)\s+(.+)", low) or \
            re.fullmatch(r"переведи\s+на\s+(английский|польский|русский|украинский)\s+(.+)", low)
        if not m:
            return None
        lang = next(v for k, v in LANGS.items() if m.group(1).startswith(k[:5]))
        phrase = _original(text, m.group(2))
        try:
            out = self.svc.translate(phrase, lang)
        except ServiceError as e:
            return str(e)
        return Spoken([("ru", f"{LANG_NAMES[lang].capitalize()}:"), (lang, out)])

    def h_dota(self, text, low, source):
        if re.search(r"(?:мой\s+)?последн\w+\s+матч", low):
            return self._svc(self.svc.last_match)
        m = re.search(r"против\s+(.+?)\s+(?:кого|кем)\s+(?:брать|играть|пикать|пикнуть)|"
                      r"(?:контрпик\w*)\s+(?:на|против|для)?\s*(.+)|кем\s+играть\s+против\s+(.+)|"
                      r"кого\s+(?:брать|пикнуть|пикать)\s+против\s+(.+)", low)
        if m:
            target = next(g for g in m.groups() if g)
            hero = find_hero(target)
            return self._svc(lambda: self.svc.counters(hero)) if hero else f"Не нашёл героя «{_clean(target)}», {self.addr}."
        if re.search(r"в\s+мете|сильн\w+\s+(?:герои|пики)|^мета$|кого\s+(?:пикнуть|пикать|брать)$", low):
            return self._svc(self.svc.meta)
        return None

    def h_mail(self, text, low, source):
        if re.search(r"прочитай\s+(?:мне\s+)?(?:главное|письм\w+|почт\w+)|что\s+(?:в\s+почте\s+)?(?:главное|важное)|главное\s+в\s+почте", low):
            return mail.important(self.cfg)
        return None

    def h_audio(self, text, low, source):
        m = re.fullmatch(r"(?:переключи|поменяй|смени)\s+(?:устройство\s+вывода|вывод\s+звука|звук)(?:\s+на\s+(.+))?", low)
        if not m:
            return None
        devices = self.cfg.audio_devices
        if not devices:
            return (f"Укажите устройства в JARVIS_AUDIO_DEVICES, {self.addr}, например "
                    "«наушники=Headphones;колонки=Speakers;блютуз=JBL».")
        names = list(devices)
        if m.group(1):
            want = _clean(m.group(1))
            key = next((n for n in names if want.startswith(n[:5]) or n.startswith(want[:5])), None)
            if not key:
                return f"Не знаю такое устройство, {self.addr}. Есть: {', '.join(names)}."
        else:
            idx = (int(self.store.meta("audio_idx", -1)) + 1) % len(names)
            key = names[idx]
        res = self.pc_do(source, lambda: self.pc.audio_output(devices[key]))
        if res not in ("ok", "no_module", "not_found"):
            return res
        self.store.set_meta("audio_idx", names.index(key))
        return {"ok": f"Переключил звук: {key}.",
                "no_module": "Нужен модуль AudioDeviceCmdlets: в PowerShell выполните Install-Module AudioDeviceCmdlets.",
                "not_found": f"Устройство «{devices[key]}» не найдено — возможно, оно не подключено."}[res]

    def h_news(self, text, low, source):
        if "новост" not in low:
            return None
        langs = {"ru"} if re.search(r"по-?русски|русск", low) else {"pl"} if "польск" in low else \
            {"uk"} if "украинск" in low else {"pl", "uk"}
        items = info.news_items(self.cfg.news_feeds, langs)
        if not items:
            return "Не удалось получить новости."
        titles = {"pl": "Новости Польши.", "uk": "Новости Украины.", "ru": "Новости России."}
        parts = []
        for lang in dict.fromkeys(l for l, _ in items):
            parts.append(("ru", titles.get(lang, "Новости.")))
            parts.append((lang, ". ".join(t for l, t in items if l == lang) + "."))
        return Spoken(parts)

    # ================= ввод текста и буфер =================
    def h_dictation(self, text, low, source):
        m = re.match(r"^(?:напечатай|набери\s+текст|набери)\s+(.+)$", text.strip(), re.I)
        if not m:
            return None
        return self.pc_do(source, lambda: (self.pc.type_text(m.group(1)), f"Напечатал, {self.addr}.")[1])

    def h_clipboard(self, text, low, source):
        if re.fullmatch(r"(?:запомни|сохрани)\s+(?:эту\s+)?ссылку", low):
            def save():
                clip = self.pc.clipboard_get().strip()
                if not re.match(r"https?://\S+$", clip):
                    return f"В буфере нет ссылки, {self.addr}."
                self.store.add_note(f"Ссылка: {clip}")
                return "Сохранил ссылку в заметки."
            return self.pc_do(source, save)
        if re.fullmatch(r"(?:прочитай\s+)?(?:что\s+)?(?:в\s+)?буфер(?:е)?(?:\s+обмена)?|прочитай\s+буфер(?:\s+обмена)?", low):
            def ask_read():
                clip = self.pc.clipboard_get()
                if not clip.strip():
                    return "Буфер обмена пуст."
                return self.ask(source, {"kind": "confirm_clip", "text": clip},
                                f"В буфере {len(clip)} символов. Прочитать вслух, {self.addr}?")
            return self.pc_do(source, ask_read)
        return None

    # ================= сеть, скриншот =================
    def h_net(self, text, low, source):
        m = re.fullmatch(r"(включи|выключи|отключи)\s+(?:блютуз|блютус|блутуз|bluetooth)", low)
        if m:
            on = m.group(1) == "включи"
            return self.pc_do(source, lambda: f"Bluetooth {'включён' if on else 'выключен'}." if self.pc.bluetooth(on)
                              else "Не удалось переключить Bluetooth.")
        wifi = r"(?:вай\s*фай|wi-?\s*fi|вайфай)"
        if re.fullmatch(rf"включи\s+{wifi}", low):
            return self.pc_do(source, lambda: "Wi-Fi включён." if self.pc.wifi_on()
                              else "Не получилось: для включения адаптера нужны права администратора.")
        if re.fullmatch(rf"переподключи\s+(?:{wifi}|интернет)", low):
            return self.pc_do(source, lambda: "Переподключил Wi-Fi." if self.pc.wifi_reconnect()
                              else "Не удалось переподключить Wi-Fi.")
        if re.fullmatch(rf"(?:выключи|отключи)\s+{wifi}", low):
            return (f"Простите, {self.addr}, отключить Wi-Fi я не стану: пропали бы Telegram, Spotify и мои "
                    "напоминания. Могу включить или переподключить.")
        return None

    def h_screenshot(self, text, low, source):
        if re.fullmatch(r"(?:сделай\s+)?скриншот(?:\s+экрана)?|сфотографируй\s+экран", low):
            return self.pc_do(source, lambda: (self.pc.screenshot(), "Скриншот сохранён в папку «Скриншоты» в Картинках.")[1])
        return None

    # ================= пылесос =================
    def h_vacuum(self, text, low, source):
        if re.search(r"(?:останови|выключи|стоп)\s+пылесос|пылесос\s+(?:стоп|остановись)", low):
            return self._vac(lambda: (self.vac.stop(), "Остановил пылесос.")[1])
        if re.search(r"пылесос\s+(?:на\s+базу|домой)|(?:отправь|верни|поезжай).*(?:на\s+базу|домой)", low):
            return self._vac(lambda: (self.vac.dock(), "Отправляю пылесос на базу.")[1])
        m = re.match(r"(?:запусти|включи|начни)\s+(?:пылесос|уборку)|(?:убери(?:сь)?|пропылесось|подмети|помой\s+пол|вымой\s+пол|протри\s+пол)\b", low)
        if not m:
            return None
        room, mode = find_room(low), find_mode(low)
        rest = re.sub(r"^(?:убери(?:сь)?|пропылесось|подмети)\s*", "", low)
        if room is None and low.startswith("убери") and rest and not rest.startswith(("пылесос", "в ", "на ")):
            return None   # «убери будильник» и т. п. — не уборка
        return self.vacuum_step(source, room, mode)

    def vacuum_step(self, source, room, mode):
        if room is None:
            return self.ask(source, {"kind": "vac_room", "mode": mode}, f"Какую комнату, {self.addr}?")
        if mode is None:
            return self.ask(source, {"kind": "vac_mode", "room": room}, f"Сухая или влажная уборка, {self.addr}?")
        word = "сухую" if mode == "dry" else "влажную"
        return self._vac(lambda: (self.vac.start(room, mode), f"Запускаю {word} уборку: {ROOM_NAMES[room]}.")[1])

    def _vac(self, fn):
        try:
            return fn()
        except VacuumError as e:
            return str(e)

    # ================= ответы на открытые вопросы =================
    def answer(self, kind, st, text, low, source):
        a = self.addr
        if kind in ("confirm_power", "confirm_close", "confirm_work", "spotify_play", "confirm_clip", "match"):
            if NO.match(low):
                del self.a.pending[source]
                if kind == "match":   # «нет, не матч» — напомнить сейчас
                    return self.a.recurring_say(st["title"])
                return f"Хорошо, {a}."
            if not YES.match(low):
                return None
            del self.a.pending[source]
            if kind == "confirm_power":
                return self.a.start_countdown(st["action"], source)
            if kind == "confirm_close":
                return self.pc_do(source, lambda: {"closed": f"{st['title'].capitalize()} закрыт.",
                                                   "not_running": f"{st['title'].capitalize()} и не был запущен.",
                                                   "failed": f"Не удалось закрыть {st['title']}."}[self.pc.close(st["image"])])
            if kind == "confirm_work":
                return self.pc_do(source, self.work_on)
            if kind == "spotify_play":
                return self.sp_do(lambda: (self.sp.play(uri=st["uri"]), f"Включаю {st['label']}.")[1])
            if kind == "confirm_clip":
                return st["text"][:300]
            if kind == "match":   # у владельца матч — напомнить позже
                self.store.postpone_recurring(st["id"], self.a.now() + MATCH_POSTPONE)
                return f"Хорошо, {a}, напомню позже."
        if kind == "spotify_playlist":
            del self.a.pending[source]
            return self.play_playlist(_clean(text))
        if kind == "vac_room":
            room = find_room(low)
            if room is None:
                return None
            del self.a.pending[source]
            return self.vacuum_step(source, room, st["mode"])
        if kind == "vac_mode":
            mode = "dry" if re.search(r"сух|пылесос|подмет", low) else "wet" if re.search(r"влаж|мыть|помой|мокр", low) else None
            if mode is None:
                return None
            del self.a.pending[source]
            return self.vacuum_step(source, st["room"], mode)
        return None
