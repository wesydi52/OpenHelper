"""Ядро Джарвиса без ИИ-сервисов: разбор русских команд правилами.

handle(text, source) -> ответ (строка). source: "local" (ПК, голос/консоль) или "telegram".
"""
import re
from datetime import datetime, timedelta

from . import fmt
from .ruparse import NUM, parse_when, to_int
from .skills import info, mail, system

HELP = ("Умею: запоминать дела со сроком («запомни, что мне надо сдать отчёт до пятницы 18:00»), "
        "напоминать («напомни через час позвонить маме»), называть дела («что у меня на сегодня»), "
        "отмечать выполненное («готово два») и удалять («удали три»), вести заметки "
        "(«запомни, что пароль от вайфая 1234», «покажи заметки»), говорить погоду, новости, время, "
        "проверять почту, открывать программы и сайты, менять громкость, искать в интернете.")

CMD_PREFIX = (r"^(?:(?:пожалуйста|слушай|эй)[, ]+)?(?:запомни|запиши|добавь(?:\s+(?:задачу|дело|напоминание))?|"
              r"напомни(?:ть)?|поставь\s+напоминание|создай\s+(?:задачу|напоминание))\b[ ,:]*")
FILLER = (r"^(?:(?:о том|про то)[, ]*)?(?:что\s+)?(?:мне\s+)?"
          r"(?:надо\s+бы|нужно\s+бы|надо|нужно|необходимо|не\s+забыть|я\s+должен|должен|обязательно)\b[ ,]*")
MODAL = re.compile(r"\b(надо|нужно|необходимо|не забыть|должен|обязательно)\b")


def _clean_task(text: str) -> str:
    text = re.sub(r"^(?:мне\s+)?", "", text.strip())
    for _ in range(3):
        text = re.sub(FILLER, "", text)
        text = re.sub(r"^(?:что|мне)\s+", "", text)
    text = text.strip(" ,.;:-")
    return text[:1].upper() + text[1:]


class Assistant:
    def __init__(self, cfg, store, now=datetime.now):
        self.cfg, self.store, self.now = cfg, store, now
        self.pending: dict = {}  # source -> уточняющий вопрос

    # ---------- вход ----------
    def handle(self, text: str, source: str = "local") -> str:
        text = re.sub(r"\s+", " ", text.strip())
        if not text:
            return ""
        low = text.lower().replace("ё", "е").strip(" .!?")
        if low in ("отмена", "отмени", "забудь", "неважно"):
            return "Хорошо, отменил." if self.pending.pop(source, None) else "Нечего отменять."
        if source in self.pending:
            answered = self._answer_pending(source, text)
            if answered is not None:
                return answered
        try:
            return self._route(text, low, source)
        except Exception as e:  # сеть, диск и т.п. — отвечаем, а не падаем
            return f"Не получилось выполнить: {e}"

    def _route(self, text: str, low: str, source: str) -> str:
        if re.match(r"^(привет|здравствуй|добрый (день|вечер|утро)|доброе утро)", low):
            who = f", {self.cfg.user_name}" if self.cfg.user_name else ""
            return f"Здравствуйте{who}! Чем могу помочь?"
        if re.search(r"что ты умеешь|помощь|help|команды", low):
            return HELP
        if m := re.match(CMD_PREFIX, low):
            return self._add(text[m.end():], low[:m.end()], source)
        if re.search(r"\b(спасибо|благодарю)\b", low):
            return "Всегда пожалуйста."
        if re.search(r"заметк|что ты помнишь|что ты запомнил", low):
            return self._notes(low)
        if re.search(r"^(?:что|какие|покажи|скажи|расскажи).*(дел[аоу]?|задач|напоминани|планах|запланирован|график)|"
                     r"^что у меня (на|в|есть)|"
                     r"^(список|мои)\s+(дел|задач|напоминани)|что мне (надо|нужно|делать)|что на (сегодня|завтра)", low):
            return self._list(low)
        if m := re.match(r"^(?:я\s+)?(?:готово|выполнено|сделано|сделал|выполнил|отметь(?:\s+как)?\s+(?:выполненн\w+|сделанн\w+))\s*(.*)$", low):
            return self._done(m.group(1))
        if m := re.match(r"^(?:удали|убери|отмени|сотри)\s+(.*)$", low):
            return self._delete(m.group(1))
        if re.search(r"погод", low):
            return self._weather(low)
        if re.search(r"новост", low):
            return info.news(self.cfg.news_feeds)
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
        return "Не понял команду. Скажите «что ты умеешь»."

    # ---------- задачи и напоминания ----------
    def _add(self, body: str, prefix: str, source: str) -> str:
        verb = "напомни" if re.search(r"напомни|напоминание", prefix) else "запомни"
        body = body.strip()
        if not body:
            return "Что именно запомнить?"
        now = self.now()
        p = parse_when(body, now)
        task = _clean_task(p.text)
        is_task = verb == "напомни" or p.dt is not None or bool(MODAL.search(body.lower()))
        if not is_task:  # «запомни, что пароль 1234» — просто заметка
            self.store.add_note(_clean_task(body))
            return "Запомнил."
        if not task:
            self.pending[source] = {"kind": "text", "when": p.dt, "has_time": p.has_time, "verb": verb}
            return "О чём напомнить?"
        if p.dt is None:
            if verb == "напомни":
                self.pending[source] = {"kind": "time", "title": task, "verb": verb}
                return "Когда напомнить?"
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

    def _answer_pending(self, source: str, text: str) -> str | None:
        st = self.pending[source]
        if st["kind"] == "time":
            p = parse_when(text, self.now())
            if p.dt is None:
                return None  # это не ответ на вопрос — разбираем как обычную команду
            del self.pending[source]
            return self._create(st["title"], p.dt, p.has_time, st["verb"])
        del self.pending[source]
        task = _clean_task(text)
        if st["when"] is None:
            self.store.add_item("task" if st["verb"] == "запомни" else "reminder", task, None)
            return "Записал."
        return self._create(task, st["when"], st["has_time"], st["verb"])

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
        res = info.web_search(q)
        if source == "local" and res is None:
            return system.search_in_browser(q)
        return res or f"Для поиска в Telegram установите пакет ddgs. Запрос: {q}"

    def _pc(self, source: str, action) -> str:
        if source != "local" and not self.cfg.tg_allow_pc:
            return "Управление компьютером из Telegram выключено."
        return action()
