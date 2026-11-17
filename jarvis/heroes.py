"""Герои Dota 2: русские названия и сленг → английское имя (как в OpenDota/Dotabuff).

Совпадение по началу слова, поэтому «пуджа», «пуджу», «пуджем» находят «пудж».
Список составлен по памяти и может содержать пробелы — недостающие герои добавляются сюда же.
"""
import re

HEROES = {
    "Abaddon": ("аббадон", "абаддон"), "Alchemist": ("алхимик", "алкаш"), "Ancient Apparition": ("древний призрак", "анциент"),
    "Anti-Mage": ("антимаг", "анти маг"), "Arc Warden": ("арк варден", "арк"), "Axe": ("акс",),
    "Bane": ("бейн",), "Batrider": ("батрайдер", "бат"), "Beastmaster": ("бистмастер", "бист"),
    "Bloodseeker": ("бладсикер", "блад"), "Bounty Hunter": ("баунти хантер", "баунти"), "Brewmaster": ("брюмастер", "панда"),
    "Bristleback": ("бристлбэк", "бристл", "бристлбек"), "Broodmother": ("бруда", "бруд"), "Centaur Warrunner": ("кентавр",),
    "Chaos Knight": ("хаос найт", "хаос"), "Chen": ("чен",), "Clinkz": ("клинкз",), "Clockwerk": ("клокверк", "клок"),
    "Crystal Maiden": ("кристалка", "кристал мейден", "цм"), "Dark Seer": ("дарк сир",), "Dark Willow": ("дарк виллоу", "виллоу"),
    "Dawnbreaker": ("даунбрейкер", "доун"), "Dazzle": ("даззл",), "Death Prophet": ("дэс профет", "дес профет", "дп"),
    "Disruptor": ("дизраптор", "дизруптор"), "Doom": ("дум",), "Dragon Knight": ("драгон найт", "драгон", "дк"),
    "Drow Ranger": ("дровка", "дроу"), "Earth Spirit": ("земляной дух", "эрт спирит"), "Earthshaker": ("шейкер", "эртшейкер"),
    "Elder Titan": ("элдер титан", "эндер титан"), "Ember Spirit": ("эмбер",), "Enchantress": ("энчантресс", "энча"),
    "Enigma": ("энигма",), "Faceless Void": ("войд", "фейслес войд"), "Grimstroke": ("гримстрок",),
    "Gyrocopter": ("гирокоптер", "гиро"), "Hoodwink": ("худвинк",), "Huskar": ("хускар",), "Invoker": ("инвокер", "инвок"),
    "Io": ("ио",), "Jakiro": ("джакиро",), "Juggernaut": ("джаггернаут", "джагер", "джагернаут"),
    "Keeper of the Light": ("кипер оф зе лайт", "котл"), "Kez": ("кез",), "Kunkka": ("кунка",),
    "Legion Commander": ("легион командер", "легион"), "Leshrac": ("лешрак",), "Lich": ("лич",),
    "Lifestealer": ("лайфстилер", "лс"), "Lina": ("лина",), "Lion": ("лион",), "Lone Druid": ("лон друид",),
    "Luna": ("луна",), "Lycan": ("ликан",), "Magnus": ("магнус",), "Marci": ("марси",), "Mars": ("марс",),
    "Medusa": ("медуза",), "Meepo": ("мипо",), "Mirana": ("мирана",), "Monkey King": ("манки кинг", "обезьяна"),
    "Morphling": ("морфлинг", "морф"), "Muerta": ("муэрта",), "Naga Siren": ("нага сирена", "нага"),
    "Nature's Prophet": ("натур профет", "фурион", "нп"), "Necrophos": ("некрофос", "некр"), "Night Stalker": ("найт сталкер",),
    "Nyx Assassin": ("никс ассасин", "никс", "нюкс"), "Ogre Magi": ("огр маги", "огр"), "Omniknight": ("омникнайт", "омни"),
    "Oracle": ("оракл",), "Outworld Destroyer": ("аутворлд дестроер", "аутворлд", "од"), "Pangolier": ("панголиер",),
    "Phantom Assassin": ("фантомка", "фантом ассасин", "па"), "Phantom Lancer": ("фантом лансер", "пл"),
    "Phoenix": ("феникс",), "Primal Beast": ("примал бист", "прим бист"), "Puck": ("пак",), "Pudge": ("пудж",),
    "Pugna": ("пугна",), "Queen of Pain": ("квопа", "куин оф пейн"), "Razor": ("рейзор", "разор"), "Riki": ("рики",),
    "Ringmaster": ("рингмастер",), "Rubick": ("рубик",), "Sand King": ("сэнд кинг", "санд кинг"),
    "Shadow Demon": ("шадоу демон", "шэдоу демон"), "Shadow Fiend": ("шадоу фиенд", "шэдоу фиенд", "сф"),
    "Shadow Shaman": ("шадоу шаман", "шаман"), "Silencer": ("сайленсер", "силенсер"), "Skywrath Mage": ("скайрат", "скайрэт"),
    "Slardar": ("слардар",), "Slark": ("сларк",), "Snapfire": ("снапфаер",), "Sniper": ("снайпер",),
    "Spectre": ("спектра",), "Spirit Breaker": ("спирит брейкер", "сб"), "Storm Spirit": ("сторм спирит", "шторм"),
    "Sven": ("свен",), "Techies": ("течис", "техис"), "Templar Assassin": ("темплар ассасин", "темплар"),
    "Terrorblade": ("террорблейд", "тб"), "Tidehunter": ("тайдхантер", "тайд"), "Timbersaw": ("тимбер", "тимберсо"),
    "Tinker": ("тинкер",), "Tiny": ("тини",), "Treant Protector": ("трент протектор", "трент"),
    "Troll Warlord": ("тролль варлорд", "тролль", "троль"), "Tusk": ("туск",), "Underlord": ("андерлорд",),
    "Undying": ("андаинг",), "Ursa": ("урса",), "Vengeful Spirit": ("венжфул спирит", "венга"),
    "Venomancer": ("веномансер", "веном"), "Viper": ("вайпер",), "Visage": ("визаж",), "Void Spirit": ("войд спирит",),
    "Warlock": ("варлок",), "Weaver": ("вивер",), "Windranger": ("виндрейнджер", "виндранер"),
    "Winter Wyvern": ("винтер вивер", "винтер"), "Witch Doctor": ("витч доктор", "вд"), "Wraith King": ("рейф кинг", "рк", "вк"),
    "Zeus": ("зевс",),
}


def _norm(text: str) -> str:
    return re.sub(r"[^a-zа-я0-9' ]+", " ", text.lower().replace("ё", "е"))


def find_hero(text: str) -> str | None:
    """Английское имя героя по фразе («для пуджа», «против инвокера») или None."""
    words = _norm(text).split()
    phrase = " ".join(words)
    best, best_len = None, 0
    for en, aliases in HEROES.items():
        for alias in (*aliases, en.lower()):
            alias = alias.lower()
            # многословные — по вхождению начала каждого слова, однословные — по началу слова
            n = len(alias.split())
            for i in range(len(words) - n + 1):
                chunk = words[i:i + n]
                if all(c.startswith(a) if len(a) >= 3 else c == a for c, a in zip(chunk, alias.split())):
                    if len(alias) > best_len:
                        best, best_len = en, len(alias)
            if alias in phrase and len(alias) > best_len and len(alias) >= 3:
                best, best_len = en, len(alias)
    return best


def ru_name(en: str) -> str:
    """Как произнести имя героя по-русски: первое русское название или английское, если нет."""
    aliases = HEROES.get(en)
    return aliases[0].title() if aliases else en


def slug(en: str) -> str:
    """Адрес героя на dotabuff.com: 'Nature's Prophet' -> 'natures-prophet'."""
    return re.sub(r"[^a-z0-9]+", "-", en.lower().replace("'", "")).strip("-")


def protracker_name(en: str) -> str:
    """Название в адресе dota2protracker.com/hero/<Имя> (пробелы кодируются)."""
    return en.replace(" ", "%20").replace("'", "%27")
