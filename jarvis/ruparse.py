"""Офлайн-разбор русских дат и времени из обычной речи.

parse_when("позвонить маме завтра в 18:00", now) -> Parsed(text="позвонить маме", dt=..., has_time=True)
Поддерживает: «через 2 часа», «через полчаса», «завтра», «послезавтра», «в пятницу»,
«25 ноября», «25.11», «до 5 числа», «в 18:30», «в шесть вечера», «к пяти часам»,
«утром/днём/вечером/ночью», «в полдень».
"""
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

WORDS = {"ноль": 0, "один": 1, "одну": 1, "одна": 1, "два": 2, "две": 2, "три": 3, "четыре": 4,
         "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9, "десять": 10,
         "одиннадцать": 11, "двенадцать": 12, "тринадцать": 13, "четырнадцать": 14,
         "пятнадцать": 15, "шестнадцать": 16, "семнадцать": 17, "восемнадцать": 18,
         "девятнадцать": 19, "двадцать": 20, "тридцать": 30, "сорок": 40, "пятьдесят": 50,
         "шестьдесят": 60}
# Падежные формы часов: «к пяти», «до шести»
HOUR_CASES = {"одному": 1, "двум": 2, "трем": 3, "четырем": 4, "пяти": 5, "шести": 6, "семи": 7,
              "восьми": 8, "девяти": 9, "десяти": 10, "одиннадцати": 11, "двенадцати": 12,
              "тринадцати": 13, "четырнадцати": 14, "пятнадцати": 15, "шестнадцати": 16,
              "семнадцати": 17, "восемнадцати": 18, "девятнадцати": 19}
MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа",
          "сентября", "октября", "ноября", "декабря"]
WEEKDAYS = [("понедельник", 0), ("вторник", 1), ("сред", 2), ("четверг", 3),
            ("пятниц", 4), ("суббот", 5), ("воскресень", 6)]

NUM = (r"(?:\d{1,3}|(?:(?:двадцать|тридцать|сорок|пятьдесят|шестьдесят)\s+)?"
       r"(?:одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|шестнадцать|семнадцать|"
       r"восемнадцать|девятнадцать|десять|девять|восемь|семь|шесть|пять|четыре|три|два|две|"
       r"одну|один|одна)|двадцать|тридцать|сорок|пятьдесят|шестьдесят)\b")
HOUR = r"(?:\d{1,2}\b|" + "|".join(sorted(HOUR_CASES, key=len, reverse=True)) + r"|" + NUM + r")"
_ORD1 = {"первого": 1, "второго": 2, "третьего": 3, "четвертого": 4, "пятого": 5, "шестого": 6,
         "седьмого": 7, "восьмого": 8, "девятого": 9}
ORD_DAYS = {**_ORD1, "десятого": 10, "одиннадцатого": 11, "двенадцатого": 12, "тринадцатого": 13,
            "четырнадцатого": 14, "пятнадцатого": 15, "шестнадцатого": 16, "семнадцатого": 17,
            "восемнадцатого": 18, "девятнадцатого": 19, "двадцатого": 20, "тридцатого": 30}
for _t, _n in (("двадцать", 20), ("тридцать", 30)):
    for _w, _v in _ORD1.items():
        if _n + _v <= 31:
            ORD_DAYS[f"{_t} {_w}"] = _n + _v
DAY = r"(?:\d{1,2}\b|" + "|".join(sorted(ORD_DAYS, key=len, reverse=True)) + r")"
# минуты словами после часа: «восемнадцать ноль ноль», «семь тридцать»
_ONES = "одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|шестнадцать|семнадцать|восемнадцать|девятнадцать|десять|девять|восемь|семь|шесть|пять|четыре|три|два|одна|один"
MINW = (rf"(?:ноль\s+(?:ноль|{_ONES})|(?:двадцать|тридцать|сорок|пятьдесят)(?:\s+(?:{_ONES}))?|"
        r"одиннадцать|двенадцать|тринадцать|четырнадцать|пятнадцать|шестнадцать|семнадцать|"
        r"восемнадцать|девятнадцать|десять)\b")
PRE = r"(?:\b(?:до|к|в|во|на)\s+)?"
MER = r"(утра|дня|вечера|ночи)"


def to_int(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    if s in ORD_DAYS:
        return ORD_DAYS[s]
    return sum(HOUR_CASES.get(w) if w in HOUR_CASES else WORDS[w] for w in s.split())


@dataclass
class Parsed:
    text: str
    dt: datetime | None
    has_time: bool
    # Нужно уточнить у владельца: "weekend" | "next_week_day" | "month_day" (dt в этом случае None)
    ask: str | None = None
    # Время суток из фразы («в выходные в 10»), если оно названо; нужно при уточнении даты
    tm: time | None = None


def _apply_mer(h: int, mer: str | None) -> int:
    if mer in ("дня", "вечера") and h < 12:
        return h + 12
    if mer == "ночи":
        return 0 if h == 12 else (h + 12 if 6 <= h < 12 else h)
    return h


def _mk_date(d: int, m: int, y: int | None, today: date) -> date | None:
    try:
        if y:
            y = y + 2000 if y < 100 else y
            return date(y, m, d)
        cand = date(today.year, m, d)
        return cand if cand >= today else date(today.year + 1, m, d)
    except ValueError:
        return None


def parse_when(text: str, now: datetime | None = None) -> Parsed:
    now = now or datetime.now()
    low = text.lower().replace("ё", "е")
    work = low
    spans: list[tuple[int, int]] = []

    def scan(pattern, check=None):
        nonlocal work
        found = []
        for m in re.finditer(pattern, work):
            val = check(m) if check else True
            if val is None or val is False:
                continue
            found.append((m, val))
        for m, _ in found:
            work = work[:m.start()] + "\0" * (m.end() - m.start()) + work[m.end():]
            spans.append((m.start(), m.end()))
        return found

    delta = None        # точное смещение (минуты/часы)
    target = None       # дата
    hm = None           # (час, минута, meridiem)
    daypart = None

    # --- «через ...» ---
    if scan(r"\bчерез\s+полчаса\b"):
        delta = timedelta(minutes=30)
    elif scan(r"\bчерез\s+полтора\s+часа\b"):
        delta = timedelta(minutes=90)
    elif scan(r"\bчерез\s+пару\s+часов\b"):
        delta = timedelta(minutes=150)  # «около 2–3 часов» — по решению владельца 2,5 часа
    elif scan(r"\bчерез\s+пару\s+минут\b"):
        delta = timedelta(minutes=2)
    elif scan(r"\bчерез\s+пару\s+(?:дней|дня)\b"):
        target = now.date() + timedelta(days=2)
    else:
        for m, _ in scan(rf"\bчерез\s+(?:({NUM})\s+)?(секунд\w*|минут\w*|час\w*|ден\w*|дн\w*|недел\w*|месяц\w*)\b"):
            n = to_int(m.group(1)) if m.group(1) else 1
            u = m.group(2)
            if u.startswith("сек"):
                delta = timedelta(seconds=n)
            elif u.startswith("мин"):
                delta = timedelta(minutes=n)
            elif u.startswith("час"):
                delta = timedelta(hours=n)
            else:
                days = n if u[:3] in ("ден", "дн") or u.startswith("дн") else n * 7 if u.startswith("нед") else n * 30
                target = now.date() + timedelta(days=days)
            break

    # --- даты ---
    for m, d in scan(PRE + rf"({DAY})\s+({'|'.join(MONTHS)})\b(?:\s+(\d{{4}})\b)?",
                     lambda m: _mk_date(to_int(m.group(1)), MONTHS.index(m.group(2)) + 1,
                                        int(m.group(3)) if m.group(3) else None, now.date())):
        target = d
    for m, _ in scan(PRE + rf"({DAY}|{NUM})\s+числа\b", lambda m: 1 <= to_int(m.group(1)) <= 31):
        day = to_int(m.group(1))
        cand = None
        for add in range(0, 13):
            y, mo = now.year + (now.month - 1 + add) // 12, (now.month - 1 + add) % 12 + 1
            try:
                c = date(y, mo, day)
            except ValueError:
                continue
            if c >= now.date():
                cand = c
                break
        target = cand or target

    # --- время ---
    for m, v in scan(PRE + rf"(\d{{1,2}}):(\d{{2}})\b(?:\s*{MER})?",
                     lambda m: int(m.group(1)) < 24 and int(m.group(2)) < 60):
        hm = (int(m.group(1)), int(m.group(2)), m.group(3))
    if not hm:
        for m, v in scan(rf"\b(?:в|к)\s+(\d{{1,2}})\.(\d{{2}})\b(?:\s*{MER})?",
                         lambda m: int(m.group(1)) < 24 and int(m.group(2)) < 60):
            hm = (int(m.group(1)), int(m.group(2)), m.group(3))
    for m, d in scan(PRE + rf"(\d{{1,2}})\.(\d{{1,2}})(?:\.(\d{{2,4}}))?\b",
                     lambda m: _mk_date(int(m.group(1)), int(m.group(2)),
                                        int(m.group(3)) if m.group(3) else None, now.date())
                     if 1 <= int(m.group(2)) <= 12 else None):
        target = d
    for m, _ in scan(PRE + r"(полдень|полночь)\b"):
        hm = (12 if m.group(1) == "полдень" else 0, 0, None)
    # расплывчатые части дня (значения назвал владелец)
    for pat, hour in ((r"\bпосле\s+обеда\b", 15), (r"\bпод\s+вечер\b", 17),
                      (PRE + r"(?:обеденное\s+время|обед)\b", 13)):
        if scan(pat) and hm is None:
            hm = (hour, 0, None)

    ask = None
    # «в начале месяца» — 1 число ближайшего следующего месяца; остальное спрашиваем
    if scan(PRE + r"начале\s+месяца\b"):
        target = date(now.year + (now.month == 12), now.month % 12 + 1, 1)
    if scan(PRE + r"(?:конц[аеу]\s+месяца|этом\s+месяце)\b"):
        ask = "month_day"
    if scan(PRE + r"выходн\w+\b"):
        ask = "weekend"
    nextweek = bool(scan(r"\bна\s+следующей\s+неделе\b"))

    # --- дни ---
    for m, _ in scan(PRE + r"(?:(следующ\w+|эту|этот)\s+)?"
                     r"(понедельник\w*|вторник\w*|сред[ауы]\b|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)"):
        wd = next(i for stem, i in WEEKDAYS if m.group(2).startswith(stem))
        if nextweek or (m.group(1) and m.group(1).startswith("следующ")):
            monday = now.date() - timedelta(days=now.weekday())
            target = monday + timedelta(days=7 + wd)
        else:
            target = now.date() + timedelta(days=(wd - now.weekday()) % 7 or 7)
        ask = None  # день названо явно — уточнять нечего
        nextweek = False
        break
    if nextweek:
        ask = "next_week_day"
    for m, _ in scan(PRE + r"(сегодня|послезавтра|завтра)\b"):
        target = now.date() + timedelta(days={"сегодня": 0, "завтра": 1, "послезавтра": 2}[m.group(1)])
        break

    # --- «в шесть вечера», «к пяти часам», «в 7» ---
    word_form = False  # время словами/цифрой без двоеточия: «в шесть», «к пяти часам»
    for m in re.finditer(rf"\b(?:в|к|до)\s+({HOUR})(?:\s+(?P<hw>час\w*))?(?:\s+(?:({NUM})\s+(?P<mn>минут\w*)|(?P<mw>{MINW})))?(?:\s+{MER.replace('(', '(?P<mer>')})?\b", work):
        h = to_int(m.group(1))
        if h > 23:
            continue
        explicit = m.group("hw") or m.group("mn") or m.group("mw") or m.group("mer")
        if not explicit and target is None:
            # «в 6 позвонить» / «позвонить в 6» — время; «купить в 2 магазинах» — нет
            at_edge = not work[:m.start()].replace("\0", "").strip() or not work[m.end():].replace("\0", "").strip(" ,.!?")
            if not at_edge:
                continue
        mins = to_int(m.group(3)) if m.group(3) else to_int(m.group("mw")) if m.group("mw") else 0
        if mins > 59:
            continue
        hm = hm or (h, mins, m.group("mer"))
        work = work[:m.start()] + "\0" * (m.end() - m.start()) + work[m.end():]
        spans.append((m.start(), m.end()))
        word_form = hm[2] is None
        break

    for m, _ in scan(r"\b(с\s+утра|утром|днем|вечером|ночью)\b"):
        daypart = m.group(1)

    # --- сборка ---
    if target is not None:
        ask = None  # дата названа явно — уточнять нечего
    if delta is None and target is None and hm is None and daypart is None and ask is None:
        return Parsed(_tidy(text, []), None, False)

    part_mer = {"утром": "утра", "с утра": "утра", "днем": "дня", "вечером": "вечера", "ночью": "ночи"}
    part_default = {"утром": 9, "с утра": 9, "днем": 14, "вечером": 19, "ночью": 23}
    tm = None
    if hm:
        h, mn, mer = hm
        if word_form and target is None and ask is None and not daypart and not mer and 1 <= h <= 7:
            mer = "дня"  # «в шесть» без даты — скорее вечер, а не 6 утра
        mer = mer or (part_mer.get(re.sub(r"\s+", " ", daypart)) if daypart else None)
        tm = time(_apply_mer(h, mer) % 24, mn)
    elif daypart:
        tm = time(part_default[re.sub(r"\s+", " ", daypart)], 0)

    if delta is not None:
        return Parsed(_tidy(text, spans), now + delta, True)
    if ask and target is None:
        return Parsed(_tidy(text, spans), None, False, ask, tm)
    dt = datetime.combine(target or now.date(), tm or time(0, 0))
    if tm is not None and target is None and dt <= now:
        dt += timedelta(days=1)  # ближайшее такое время — завтра
    return Parsed(_tidy(text, spans), dt, tm is not None)


def _weekday_of(text: str) -> int | None:
    m = re.search(r"(понедельник\w*|вторник\w*|сред[ауы]\b|четверг\w*|пятниц\w*|суббот\w*|воскресень\w*)", text)
    return next(i for stem, i in WEEKDAYS if m.group(1).startswith(stem)) if m else None


def _day_of_month(low: str, now: datetime) -> date | None:
    """Ответ на «Какого числа?»: «28», «двадцать восьмого», «30 числа» → ближайшая такая дата."""
    m = re.fullmatch(rf"\s*(?:до\s+|на\s+)?({DAY}|{NUM})\s*(?:числа)?\s*", low)
    if not m:
        return None
    day = to_int(m.group(1))
    if not 1 <= day <= 31:
        return None
    for add in range(0, 13):
        y, mo = now.year + (now.month - 1 + add) // 12, (now.month - 1 + add) % 12 + 1
        try:
            c = date(y, mo, day)
        except ValueError:
            continue  # в этом месяце нет такого числа
        if c >= now.date():
            return c
    return None


def resolve_ask(kind: str, answer: str, now: datetime | None = None, tm: time | None = None) -> Parsed | None:
    """Разбор ответа владельца на уточняющий вопрос. None — это не ответ на вопрос."""
    now = now or datetime.now()
    low = answer.lower().replace("ё", "е")
    p = parse_when(answer, now)
    if kind == "weekend":
        wd = _weekday_of(low)
        if wd not in (5, 6):
            return None
        d = now.date() + timedelta(days=(wd - now.weekday()) % 7 or 7)
    elif kind == "next_week_day":
        wd = _weekday_of(low)
        if wd is None:
            return None
        d = now.date() - timedelta(days=now.weekday()) + timedelta(days=7 + wd)
    elif kind == "month_day":
        d = p.dt.date() if p.dt else _day_of_month(low, now)
        if d is None:
            return None
    else:
        return None
    t = p.dt.time() if (p.dt and p.has_time) else tm
    return Parsed("", datetime.combine(d, t or time(0, 0)), t is not None)


def _tidy(text: str, spans) -> str:
    for s, e in sorted(spans, reverse=True):
        text = text[:s] + " " + text[e:]
    text = re.sub(r"\s+", " ", text).strip()
    for _ in range(3):
        text = re.sub(r"^(?:до|к|в|во|на|и|что)\s+", "", text)
        text = re.sub(r"\s+(?:до|к|в|во|на|и|а также|срок)$", "", text)
    return text.strip(" ,.;:-!?")
