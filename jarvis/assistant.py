"""Ядро Джарвиса без ИИ-сервисов: разбор русских команд правилами.

handle(text, source) -> ответ (строка). source: "local" (ПК, голос/консоль) или "telegram".
"""
import re
from datetime import datetime, time, timedelta

from . import fmt
from .common import CANCEL_WORDS, NO, YES
from .intents import EXTRA_KINDS, Extras
from .pc import Pc
from .ruparse import NUM, parse_when, resolve_ask, to_int
from .services import Services
from .skills import info, mail, system
from .spoken import Urgent
from .spotify import Spotify
from .vacuum import NotConfigured

HELP = ("Умею: запоминать дела со сроком («запомни, что мне надо сдать отчёт до пятницы 18:00»), "
        "напоминать («напомни через час позвонить маме»), называть дела («что у меня на сегодня»), "
        "отмечать выполненное («готово два») и удалять («удали три»), вести заметки "
        "(«запомни, что пароль от вайфая 1234», «покажи заметки»), говорить погоду, новости, время, "
        "проверять почту, открывать программы и сайты, менять громкость, искать в интернете.")

CMD_PREFIX = (r"^(?:(?:пожалуйста|слушай|эй)[, ]+)?(?:запомни|запиши(?:\s+в\s+(?:дела|задачи|список\s+дел))?|"
              r"добавь(?:\s+(?:задачу|дело|напоминание)|\s+в\s+(?:дела|задачи|список\s+дел))?|"
              r"напомни(?:ть)?|поставь\s+напоминание|создай\s+(?:задачу|напоминание))\b[ ,:]*")
FILLER = (r"^(?:(?:о том|про то)[, ]*)?(?:что\s+)?(?:мне\s+)?"
          r"(?:надо\s+бы|нужно\s+бы|надо|нужно|необходимо|не\s+забыть|я\s+должен|должен|обязательно)\b[ ,]*")
MODAL = re.compile(r"\b(надо|нужно|необходимо|не забыть|должен|обязательно)\b")

PENDING_TTL = timedelta(minutes=2)   # открытый вопрос «протухает», чтобы не перехватывать чужие фразы
MAX_RETRIES = 2                      # сколько раз переспросить, прежде чем сдаться
REACT_WINDOW_MIN = 120               # столько минут после напоминания слова «сделано/позже» относятся к нему
SNOOZE_DEFAULT = timedelta(minutes=30)   # «позже» / «потом» без времени — решение владельца
HEARD = re.compile(r"^(?:хорошо|понял[аи]?|понятно|принято|услышал[аи]?|ясно|ок|окей|ладно)$")
DONE = re.compile(r"^(?:я\s+)?(?:уже\s+)?(?:все\s+)?(?:готово|сделано|сделал[аи]?|выполнено|выполнил[аи]?|закончил[аи]?)$")
PAST = re.compile(r"^[а-я]{2,}(?:л|ла|ло|ли|лся|лась|лись)$")   # глагол прошедшего времени: «позвонил»
SNOOZE_WORDS = ("позже", "потом", "попозже", "отложи", "отложить", "не сейчас")
ORDINALS = {"первое": 1, "первый": 1, "второе": 2, "второй": 2, "третье": 3, "третий": 3}


ACTION_NAMES = {"restart": "перезапуск", "shutdown": "выключение", "sleep": "спящий режим"}


def fmt_action(action: str) -> str:
    return ACTION_NAMES.get(action, action)


def _clean_task(text: str) -> str:
    text = re.sub(r"^(?:мне\s+)?", "", text.strip())
    for _ in range(3):
        text = re.sub(FILLER, "", text)
        text = re.sub(r"^(?:что|мне)\s+", "", text)
    text = text.strip(" ,.;:-")
    return text[:1].upper() + text[1:]


class Assistant:
    def __init__(self, cfg, store, now=datetime.now, pc=None, spotify=None, services=None, vacuum=None):
        self.cfg, self.store, self.now = cfg, store, now
        self.pending: dict = {}  # source -> уточняющий вопрос
        self.fails: dict = {}    # source -> сколько раз подряд не поняли
        self.pc = pc or Pc()
        self.spotify = spotify or Spotify(cfg)
        self.services = services or Services(cfg)
        self.vacuum = vacuum or NotConfigured()
        self.countdown: dict | None = None     # отложенное опасное действие: {"action", "due", "source"}
        self.voice_mode = False                # включает cli в голосовом режиме
        self._music_paused = False             # музыку на паузу поставили мы (из-за шума) — потом вернём
        self.x = Extras(self)

    # ---------- вход ----------
    def handle(self, text: str, source: str = "local") -> str:
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return ""
        low = text.lower().replace("ё", "е").strip(" .!?")
        st = self.pending.get(source)
        if st and self.now() - st["ts"] > PENDING_TTL:
            del self.pending[source]
        if self.countdown and low in CANCEL_WORDS:
            what = fmt_action(self.countdown["action"])
            self.countdown = None
            return f"Отменил: {what}, {self.cfg.address}."
        if low in CANCEL_WORDS[:4]:
            self.fails.pop(source, None)
            return "Хорошо, отменил." if self.pending.pop(source, None) else "Нечего отменять."
        if source in self.pending:
            answered = self._answer_pending(source, text, low)
            if answered is not None:
                self.fails.pop(source, None)
                self._resume_music()
                return answered
        try:
            reply = self._route(text, low, source)
        except Exception as e:  # сеть, диск и т.п. — отвечаем, а не падаем
            return f"Не получилось выполнить: {e}"
        if reply is None:
            return self._not_understood(text, source)
        self.fails.pop(source, None)
        self._resume_music()
        return reply

    def _not_understood(self, text: str, source: str) -> str:
        """Раздел 2a плана: официально, два переспроса, затем сдаться и записать фразу для разбора."""
        a = self.cfg.address
        self.store.log_unrecognized(text, source, self.now())
        n = self.fails.get(source, 0) + 1
        self._pause_music(source)
        if n <= MAX_RETRIES:
            self.fails[source] = n
            if source == "telegram":
                return f"Прошу прощения, {a}, я не понял команду. Не могли бы вы сформулировать иначе?"
            return f"Прошу прощения, {a}, я не расслышал. Не могли бы вы повторить?"
        self.fails.pop(source, None)
        msg = f"Прошу прощения, {a}, мне не удалось разобрать команду. Я записал фразу для разбора."
        if source != "telegram" and self.cfg.tg_token:
            msg += " Вы можете написать её мне в Telegram."
        return msg

    # ---------- реакция на сработавшее напоминание ----------
    @staticmethod
    def _verb_matches(verb: str, title: str) -> bool:
        """«позвонил» ↔ «Позвонить врачу»: у глагола и слова из названия общее начало."""
        for w in re.findall(r"[а-я]{4,}", title.lower().replace("ё", "е")):
            n = 0
            while n < min(len(verb), len(w)) and verb[n] == w[n]:
                n += 1
            if n >= max(4, min(len(verb), len(w)) - 3):
                return True
        return False

    def _snooze_until(self, low: str, now: datetime):
        """None — это не просьба отложить; иначе момент повтора (может оказаться в прошлом)."""
        if low in SNOOZE_WORDS:
            return now + SNOOZE_DEFAULT
        m = re.match(r"^отложи(?:ть)?(?:\s+(?:это|напоминание))?\s+на\s+(.+)$", low)
        if m:
            p = parse_when("через " + m.group(1), now)
            return p.dt if p.dt and not p.text else None
        m = re.match(r"^напомни(?:ть)?(?:\s+мне)?(\s+еще\s+раз)?\s*(.*)$", low)
        if m and (m.group(1) or m.group(2)):
            rest = m.group(2).strip()
            if rest in ("", "позже", "потом", "попозже"):
                return now + SNOOZE_DEFAULT
            p = parse_when(rest, now)
            return p.dt if p.dt and p.has_time and not p.text and not p.ask else None
        if low.startswith("через "):
            p = parse_when(low, now)
            return p.dt if p.dt and p.has_time and not p.text else None
        m = re.fullmatch(rf"еще\s+({NUM})\s+минут\w*", low)   # «ещё пять минут» — будильник
        if m:
            return now + timedelta(minutes=to_int(m.group(1)))
        return None

    def _react(self, low: str, source: str) -> str | None:
        """Слова «сделано / понял / отложи» после напоминания. None — это не реакция."""
        now = self.now()
        wait = self.store.awaiting(now, REACT_WINDOW_MIN)    # ждём «понял» / «отложи»
        recent = self.store.recent(now, REACT_WINDOW_MIN)    # можно закрыть: «сделано», «я уже позвонил»
        if not recent:
            return None
        a = self.cfg.address
        if wait and any(i["kind"] == "alarm" for i in wait) and low in ("хватит", "стоп", "проснулся", "встал", "я проснулся"):
            for i in wait:
                self.store.ack(i["id"])
            self.stop_alarm_sound()
            return f"Доброе утро, {a}."
        if wait and HEARD.match(low):
            for i in wait:
                self.store.ack(i["id"])
            return f"Принял, {a}. Дело остаётся в списке."
        if DONE.match(low):
            return self._done_among(source, recent)
        until = self._snooze_until(low, now) if wait else None
        if until is not None:
            if until <= now:
                return f"Это время уже прошло, {a}. Назовите другое."
            for i in wait:
                self.store.snooze(i["id"], until)
            titles = "; ".join(i["title"] for i in wait)
            return f"Напомню {fmt.fmt_when(until, now, True)}: {titles}."
        words = low.split()
        if len(words) <= 4:  # «я уже позвонил» — закрыть дело по смыслу
            verb = next((w for w in words if PAST.match(w) and not HEARD.match(w)), None)  # «понял» — не «сделал»
            if verb:
                hits = [i for i in recent if self._verb_matches(verb, i["title"])]
                if hits:
                    return self._done_among(source, hits)
                if len(recent) == 1:
                    return self._ask(source, {"kind": "confirm_done", "id": recent[0]["id"]},
                                     f"Отметить «{recent[0]['title']}» выполненным, {a}?")
        return None

    def _done_among(self, source: str, items: list) -> str:
        if len(items) == 1:
            self.store.mark_done(items[0]["id"])
            return f"Отметил выполненным: {items[0]['title']}."
        listing = " ".join(f"{n}. {i['title']}." for n, i in enumerate(items, 1))
        return self._ask(source, {"kind": "pick_done", "ids": [i["id"] for i in items]},
                         f"Какое именно отметить, {self.cfg.address}? {listing}")

    # ---------- музыка при шуме ----------
    def _pause_music(self, source: str):
        """Не поняли фразу в голосовом режиме — ставим играющую музыку на паузу (только через Spotify API,
        иначе клавиша «пауза» могла бы, наоборот, запустить музыку)."""
        if self.voice_mode and source == "local" and self.spotify.configured and not self._music_paused:
            try:
                self._music_paused = self.spotify.pause_if_playing()
            except Exception:
                self._music_paused = False

    def _resume_music(self):
        if self._music_paused:
            self._music_paused = False
            try:
                self.spotify.resume()
            except Exception:
                pass

    # ---------- «не беспокоить» ----------
    @property
    def dnd(self) -> bool:
        return bool(self.store.meta("dnd", False))

    def set_dnd(self, on: bool) -> str:
        if on:
            self.store.set_meta("dnd", True)
            self.store.set_meta("dnd_missed", [])
            return f"Режим «не беспокоить» включён, {self.cfg.address}."
        self.store.set_meta("dnd", False)
        missed = self.store.meta("dnd_missed", []) or []
        self.store.set_meta("dnd_missed", [])
        if not missed:
            return f"Режим «не беспокоить» выключен. Пропущенных напоминаний нет, {self.cfg.address}."
        return (f"Режим «не беспокоить» выключен. Пока вы не беспокоились, было {len(missed)} "
                f"{fmt.plural(len(missed), 'напоминание', 'напоминания', 'напоминаний')}, {self.cfg.address}: "
                + " ".join(missed))

    def note_missed(self, text: str):
        missed = list(self.store.meta("dnd_missed", []) or [])
        missed.append(text)
        self.store.set_meta("dnd_missed", missed[-50:])

    # ---------- опасные действия с отсчётом ----------
    def start_countdown(self, action: str, source: str) -> str:
        n = self.cfg.countdown_seconds
        self.countdown = {"action": action, "due": self.now() + timedelta(seconds=n), "source": source}
        return (f"Хорошо, {self.cfg.address}. {fmt_action(action).capitalize()} через {n} "
                f"{fmt.plural(n, 'секунду', 'секунды', 'секунд')}. Скажите «отмена», чтобы остановить.")

    def tick(self, now: datetime) -> list:
        """Раз в секунду из планировщика: отсчёт опасных действий и повторяющиеся напоминания."""
        out = []
        cd = self.countdown
        if cd and now >= cd["due"]:
            self.countdown = None
            try:
                self.pc.power(cd["action"])
                out.append(f"Выполняю: {fmt_action(cd['action'])}.")
            except Exception as e:  # noqa: BLE001
                out.append(f"Не получилось выполнить: {e}")
        for r in self.store.recurring_due(now):
            if self.store.meta("game_mode") or self._dota_running():
                if "local" in self.pending:
                    self.store.postpone_recurring(r["id"], now + timedelta(minutes=5))
                    continue
                out.append(self._ask("local", {"kind": "match", "id": r["id"], "title": r["title"]},
                                     f"У вас матч, {self.cfg.address}?"))
            else:
                out.append(self.recurring_say(r["title"]))
        return out

    def recurring_say(self, title: str) -> str:
        return f"Напоминаю: {title}."

    def _dota_running(self) -> bool:
        try:
            return self.pc.os == "Windows" and self.pc.is_running("dota2.exe")
        except Exception:
            return False

    # ---------- будильник и таймер ----------
    def on_alert(self, item: dict, offset: int, now: datetime):
        """Оповещение по делу сработало: у будильника включаем музыку (или сигнал), у таймера — сигнал."""
        if item["kind"] == "alarm":
            played = False
            if self.spotify.configured:
                try:
                    p = self.spotify.find_playlist(self.cfg.alarm_playlist) if self.cfg.alarm_playlist else None
                    self.spotify.play(context_uri=p["uri"]) if p else self.spotify.resume()
                    played = True
                except Exception:
                    played = False
            if not played:
                self._beep()
            return Urgent(f"Будильник, {self.cfg.address}. Пора вставать." if played
                          else f"Будильник, {self.cfg.address}. Пора вставать. Музыку включить не удалось, играет сигнал.")
        if item["kind"] == "timer":
            self._beep()
            return Urgent("Таймер: время вышло.")
        return None

    def _beep(self):
        try:
            self.pc.beep(3)
        except Exception:
            pass

    def stop_alarm_sound(self):
        if self.spotify.configured:
            try:
                self.spotify.pause_if_playing()
            except Exception:
                pass

    def _ask(self, source: str, state: dict, question: str) -> str:
        self.pending[source] = {**state, "ts": self.now()}
        return question

    # ---------- журнал непонятных фраз ----------
    def _list_unrecognized(self) -> str:
        items = self.store.unrecognized()
        if not items:
            return f"Непонятных фраз нет, {self.cfg.address}."
        self.store.mark_unrecognized_reviewed()  # показали — считаем разобранными (данные остаются в журнале)
        return f"Непонятных фраз: {len(items)}. " + ". ".join(
            f"{n}. «{x['text']}»" for n, x in enumerate(items, 1)) + "."

    def daily_review(self, now: datetime) -> tuple[str, str] | None:
        """Раз в день после review_time: (реплика голосом, полный список для Telegram) или None."""
        hh, mm = (int(x) for x in self.cfg.review_time.split(":"))
        items = self.store.unrecognized()
        today = now.strftime("%Y-%m-%d")
        if (not items or now.time() < time(hh, mm) or self.store.meta("review_prompted") == today
                or "local" in self.pending):
            return None
        self.store.set_meta("review_prompted", today)
        n = len(items)
        verb = "Накопилась" if n % 10 == 1 and n % 100 != 11 else "Накопилось"
        voice = f"{verb} {fmt.unclear_phrases(n)}, {self.cfg.address}. Разберём?"
        self._ask("local", {"kind": "review"}, voice)
        tg = "Непонятные фразы:\n" + "\n".join(f"{i}. {x['text']}" for i, x in enumerate(items, 1))
        return voice, tg

    def _route(self, text: str, low: str, source: str) -> str:
        if (reaction := self._react(low, source)) is not None:
            return reaction
        # Явная просьба «в интернете / в Google» важнее ключевых слов вроде «погода» или «курс»
        if m := re.match(r"^(?:загугли|погугли)\s+(.+)$|^(?:найди|поищи|ищи)\s+в\s+(?:интернете|сети|гугле|гугл)\s+(.+)$", low):
            return self._search(m.group(1) or m.group(2), source)
        if (extra := self.x.route(text, low, source)) is not None:
            return extra
        if re.match(r"^(привет|здравствуй|добрый (день|вечер|утро)|доброе утро)", low):
            who = f", {self.cfg.user_name}" if self.cfg.user_name else ""
            return f"Здравствуйте{who}! Чем могу помочь?"
        if re.search(r"что ты умеешь|помощь|help|команды", low):
            return HELP
        if re.search(r"(?:непонятн|нераспознанн)\w*\s+фраз|журнал\w*\s+(?:непонятн|нераспознанн)", low):
            if re.search(r"очист|сотри|удали|сбрось", low):
                n = self.store.clear_unrecognized()
                return f"Журнал очистил, {self.cfg.address}. Удалено записей: {n}."
            return self._list_unrecognized()
        if m := re.match(CMD_PREFIX, low):
            return self._add(text[m.end():], low[:m.end()], source)
        if re.search(r"\b(спасибо|благодарю)\b", low):
            return "Всегда пожалуйста."
        if re.search(r"заметк|что ты помнишь|что ты запомнил", low):
            return self._notes(low)
        if re.search(r"^(?:что|какие|покажи|скажи|расскажи).*(дел[аоу]?|задач|напоминани|планах|запланирован|график)|"
                     r"^что у меня|"
                     r"^(список|мои)\s+(дел|задач|напоминани)|что мне (надо|нужно|делать)|что на (сегодня|завтра)", low):
            return self._list(low)
        if m := re.match(r"^(?:я\s+)?(?:готово|выполнено|сделано|сделал|выполнил|отметь(?:\s+как)?\s+(?:выполненн\w+|сделанн\w+))\s*(.*)$", low):
            return self._done(m.group(1))
        if m := re.match(r"^(?:удали|убери|отмени|сотри)\s+(.*)$", low):
            return self._delete(m.group(1))
        if re.search(r"погод", low):
            return self._weather(low)
        if re.search(r"который час|сколько времени|скажи время|сколько сейчас", low):
            return f"Сейчас {self.now():%H:%M}."
        if re.search(r"какое (сегодня )?число|какой (сегодня )?день|какая (сегодня )?дата", low):
            n = self.now()
            days = ["понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье"]
            return f"Сегодня {days[n.weekday()]}, {n.day} {fmt.MONTHS[n.month - 1]}."
        if re.search(r"(провер|прочита|есть ли|нов\w+|непрочитанн\w+|что).*(почт|письм)|^почта$", low) \
                and not low.startswith(("открой", "запусти")):
            return mail.unread(self.cfg)
        if m := re.match(r"^(?:найди|поищи|загугли|погугли|ищи)(?:\s+в\s+(?:интернете|сети|гугле))?\s+(.+)$", low):
            return self._search(m.group(1), source)
        if m := re.match(r"^(?:открой|запусти|включи)\s+(?:сайт\s+|программу\s+|приложение\s+)?(.+)$", low):
            return self._pc(source, lambda: system.open_url(m.group(1)) if re.search(r"\w\.\w{2,}", m.group(1))
                            else system.open_app(m.group(1)))
        if m := re.search(r"громкост\w*.*?(\d{1,3}|" + NUM + ")", low):
            return self._pc(source, lambda: system.set_volume(to_int(m.group(1))))
        return None  # не поняли — handle() переспросит или сдастся

    # ---------- задачи и напоминания ----------
    def _add(self, body: str, prefix: str, source: str) -> str:
        verb = "напомни" if re.search(r"напомни|напоминание", prefix) else "запомни"
        body = body.strip()
        if not body:
            return "Что именно запомнить?"
        p = parse_when(body, self.now())
        task = _clean_task(p.text)
        is_task = verb == "напомни" or p.dt is not None or p.ask is not None or bool(MODAL.search(body.lower()))
        if not is_task:  # «запомни, что пароль 1234» — просто заметка
            self.store.add_note(_clean_task(body))
            return "Запомнил."
        if not task:
            return self._ask(source, {"kind": "text", "p": p, "verb": verb}, f"О чём напомнить, {self.cfg.address}?")
        return self._schedule(source, task, p, verb)

    def _schedule(self, source: str, task: str, p, verb: str) -> str:
        """Есть название дела; дальше — спросить недостающее или создать."""
        a = self.cfg.address
        if p.ask:
            if p.ask == "weekend":
                q = f"В субботу или в воскресенье, {a}" + ("?" if p.tm else ", и во сколько?")
            elif p.ask == "next_week_day":
                q = f"Какого дня недели, {a}?"
            else:
                q = f"Какого числа, {a}?"
            return self._ask(source, {"kind": "ask", "ask": p.ask, "title": task, "verb": verb, "tm": p.tm}, q)
        if p.dt is None:
            if verb == "напомни":
                return self._ask(source, {"kind": "time", "title": task, "verb": verb}, f"Когда напомнить, {a}?")
            self.store.add_item("task", task, None)
            return f"Записал задачу: {task}. Срока нет."
        return self._create(task, p.dt, p.has_time, verb)

    def _create(self, title: str, dt: datetime, has_time: bool, verb: str) -> str:
        now = self.now()
        if verb == "запомни" and not has_time:
            dt = dt.replace(hour=18, minute=0)  # срок «до пятницы» = конец рабочего дня
        if dt <= now:
            return "Это время уже прошло. Назовите другое."
        if verb == "напомни":
            self.store.add_item("reminder", title, dt, [0])
            return f"Напомню {fmt.fmt_when(dt, now, has_time)}: {title}."
        # задача со сроком: заблаговременные оповещения + в момент срока
        mins = (dt - now).total_seconds() / 60
        offs = [0]
        if has_time:
            offs += [o for o in (60, 1440) if mins > o + 10]
        else:
            offs += [o for o in (540, 1440) if mins > o + 10]  # 09:00 в день срока и за сутки
        self.store.add_item("task", title, dt, offs)
        return f"Записал: {title}. Срок {fmt.fmt_when(dt, now, has_time)}. Напомню заранее."

    def _answer_pending(self, source: str, text: str, low: str) -> str | None:
        """Ответ на открытый вопрос. None — это не ответ: разбираем как обычную команду."""
        st = self.pending[source]
        kind = st["kind"]
        if kind in EXTRA_KINDS:
            return self.x.answer(kind, st, text, low, source)
        if kind == "review":
            if YES.match(low):
                del self.pending[source]
                return self._list_unrecognized()
            if NO.match(low):
                del self.pending[source]
                return f"Хорошо, {self.cfg.address}."
            return None
        if kind == "confirm_done":
            if YES.match(low):
                del self.pending[source]
                title = next((i["title"] for i in self.store.active() if i["id"] == st["id"]), "")
                self.store.mark_done(st["id"])
                return f"Отметил выполненным: {title}."
            if NO.match(low):
                del self.pending[source]
                return f"Хорошо, {self.cfg.address}."
            return None
        if kind == "pick_done":
            by_id = {i["id"]: i for i in self.store.active()}
            cands = [by_id[x] for x in st["ids"] if x in by_id]   # порядок — как зачитан в вопросе
            n = ORDINALS.get(low) or (to_int(low) if re.fullmatch(NUM, low) else 0)
            if 1 <= n <= len(cands):
                pick = cands[n - 1]
            else:
                words = [w[:5] for w in re.findall(r"\w{3,}", low)]
                hits = [i for i in cands if words and all(w in i["title"].lower() for w in words)]
                if len(hits) != 1:
                    return None
                pick = hits[0]
            del self.pending[source]
            self.store.mark_done(pick["id"])
            return f"Отметил выполненным: {pick['title']}."
        if kind == "time":
            p = parse_when(text, self.now())
            if p.dt is None:
                return None
            del self.pending[source]
            if st.get("date") is not None:  # дата уже известна, спрашивали только время
                if not p.has_time:
                    return None
                return self._create(st["title"], datetime.combine(st["date"], p.dt.time()), True, st["verb"])
            return self._create(st["title"], p.dt, p.has_time, st["verb"])
        if kind == "ask":
            r = resolve_ask(st["ask"], text, self.now(), st.get("tm"))
            if r is None:
                return None
            del self.pending[source]
            if r.has_time or st["verb"] == "запомни":  # у задачи без времени срок — 18:00
                return self._create(st["title"], r.dt, r.has_time, st["verb"])
            return self._ask(source, {"kind": "time", "title": st["title"], "verb": st["verb"],
                                      "date": r.dt.date()}, f"Во сколько, {self.cfg.address}?")
        # kind == "text": ждали название дела
        del self.pending[source]
        task = _clean_task(text)
        return self._schedule(source, task, st["p"], st["verb"])

    def _list(self, low: str) -> str:
        now = self.now()
        items = self.store.active()
        day = None
        if "сегодня" in low:
            day = now.date()
        elif "завтра" in low:
            day = (now + timedelta(days=1)).date()
        if day:
            items = [i for i in items if i["when"] and fmt.parse_ts(i["when"]).date() == day]
        if not items:
            return "На этот день дел нет." if day else "Дел нет."
        parts = []
        for n, i in enumerate(items, 1):
            when = f", {fmt.fmt_when(fmt.parse_ts(i['when']), now)}" if i["when"] else ""
            parts.append(f"{n}. {i['title']}{when}")
        return f"Дел: {len(items)}. " + ". ".join(parts) + "."

    def _pick(self, arg: str):
        """Выбор дела по номеру («2», «два») или по слову из названия."""
        items = self.store.active()
        arg = re.sub(r"^(?:задач\w*|дел\w*|напоминани\w*|номер)\s*", "", arg.strip())
        arg = re.sub(r"^(?:задач\w*|дел\w*|напоминани\w*|номер)\s*", "", arg)
        if re.fullmatch(NUM, arg):
            n = to_int(arg)
            return items[n - 1] if 1 <= n <= len(items) else None
        words = [w[:5] for w in re.findall(r"\w{3,}", arg)]
        hits = [i for i in items if words and all(w in i["title"].lower() for w in words)]
        return hits[0] if len(hits) == 1 else (hits if hits else None)

    def _done(self, arg: str) -> str:
        item = self._pick(arg) if arg else None
        if isinstance(item, list):
            return "Таких дел несколько, назовите номер."
        if not item:
            return "Не нашёл такое дело. Скажите номер из списка дел."
        self.store.mark_done(item["id"])
        return f"Отметил выполненным: {item['title']}."

    def _delete(self, arg: str) -> str:
        if re.search(r"заметк", arg):
            notes = self.store.notes()
            num = re.search(rf"({NUM})", arg)
            if num and 1 <= to_int(num.group(1)) <= len(notes):
                self.store.delete_note(notes[to_int(num.group(1)) - 1]["id"])
                return "Заметку удалил."
            return "Скажите номер заметки."
        item = self._pick(arg)
        if isinstance(item, list):
            return "Таких дел несколько, назовите номер."
        if not item:
            return "Не нашёл такое дело. Скажите номер из списка дел."
        self.store.delete_item(item["id"])
        return f"Удалил: {item['title']}."

    def _notes(self, low: str) -> str:
        notes = self.store.notes()
        if not notes:
            return "Заметок нет."
        return "Заметки. " + ". ".join(f"{n}. {x['text']}" for n, x in enumerate(notes, 1)) + "."

    # ---------- прочее ----------
    def _weather(self, low: str) -> str:
        m = re.search(r"погод\w*\s+(?:в|во|для)\s+([а-яa-z\- ]+?)(?:\s+(?:сегодня|завтра|на\s+\w+))?$", low)
        city = m.group(1).strip() if m else self.cfg.city
        return info.weather(city, 2 if "завтра" in low else 1)

    def _search(self, q: str, source: str) -> str:
        """Решение владельца: «найди …» = открыть Google с запросом (ответ ИИ Google будет на экране, без API)."""
        from urllib.parse import quote
        url = "https://www.google.com/search?q=" + quote(q)
        if source == "local":
            return self._pc(source, lambda: (self.pc.open_url(url), f"Ищу в Google: {q}.")[1])
        return info.web_search(q) or f"Ссылка на поиск в Google: {url}"

    def _pc(self, source: str, action) -> str:
        if source != "local" and not self.cfg.tg_allow_pc:
            return "Управление компьютером из Telegram выключено."
        return action()
