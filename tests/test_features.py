"""Пункты 3–10 плана: звук, сайты, Spotify, YouTube, питание, режимы, пылесос, таймеры, «не беспокоить» и др.

Фразы — владельца из JARVIS_PLAN.md. ПК, Spotify, сервисы и пылесос подменены (fakes.py).
Вживую (Windows, звук, сеть, аккаунты) НИЧЕГО из этого не проверено.
"""
from datetime import timedelta

import pytest

from fakes import NOW, make
from jarvis.pc import Unsupported
from jarvis.spotify import NoDevice, SpotifyError


@pytest.fixture
def a(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch)


@pytest.fixture
def a_nosp(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch, spotify_configured=False)


def calls(a, name=None):
    return [c for c in a.fk.pc.calls if name is None or c[0] == name]


# ================= «не беспокоить» =================
def test_dnd_on_off_and_summary(a):
    assert not a.dnd
    assert "Telegram" in a.handle("не беспокоить")
    assert a.dnd
    a.note_missed("Напоминаю: Позвонить врачу.")
    a.note_missed("Напоминаю: Купить хлеб.")
    out = a.handle("выключи не беспокоить")
    assert not a.dnd and "было 2 напоминания" in out and "Позвонить врачу" in out and "Купить хлеб" in out
    assert "только в Telegram" in a.handle("включи режим не беспокоить") and a.dnd
    assert "Пропущенных напоминаний нет" in a.handle("выключи режим не беспокоить")      # сводка не повторяется


def test_dnd_off_without_missed(a):
    a.handle("не беспокоить")
    assert "Пропущенных напоминаний нет" in a.handle("отключи не беспокоить")


def test_dnd_allowed_from_telegram(a):
    a.handle("не беспокоить", source="telegram")
    assert a.dnd


# ================= громкость =================
@pytest.mark.parametrize("phrase,call", [
    ("громче", ("change_volume", 20)), ("Сделай громче", ("change_volume", 20)), ("прибавь звук", ("change_volume", 20)),
    ("тише", ("change_volume", -20)), ("убавь громкость", ("change_volume", -20)),
    ("громкость 30", ("set_volume", 30)), ("поставь громкость на 45 процентов", ("set_volume", 45)),
    ("громкость на половину", ("set_volume", 50)), ("громкость на максимум", ("set_volume", 100)),
    ("громкость на минимум", ("set_volume", 0)), ("громкость тридцать", ("set_volume", 30)),
])
def test_volume(a, phrase, call):
    a.handle(phrase)
    assert call in calls(a)


def test_mute_unmute(a):
    assert a.handle("выключи звук") == "Звук выключен."
    assert a.handle("выключи звук") == "Звук уже выключен."
    assert a.handle("включи звук") == "Звук включён."


def test_volume_blocked_from_telegram(a):
    assert "выключено" in a.handle("громче", source="telegram")
    assert calls(a) == []


def test_pc_error_becomes_a_reply(a):
    a.fk.pc.fail = Unsupported("Эта команда работает только в Windows.")
    assert a.handle("громче") == "Эта команда работает только в Windows."


# ================= музыка =================
def test_pause_next_with_spotify_api(a):
    a.handle("пауза")
    a.handle("продолжи")
    a.handle("переключи песню в спотифай")
    assert [c[0] for c in a.fk.sp.calls] == ["pause", "resume", "next"]
    assert calls(a, "media") == []


def test_media_keys_without_spotify_api(a_nosp):
    a_nosp.handle("поставь на паузу")
    a_nosp.handle("переключи песню")
    a_nosp.handle("следующая песня")
    assert calls(a_nosp, "media") == [("media", "play_pause"), ("media", "next"), ("media", "next")]


def test_spotify_failure_falls_back_to_media_key(a):
    a.fk.sp.error = SpotifyError("boom")
    a.handle("переключи песню")
    assert ("media", "next") in calls(a)


def test_spotify_no_device_launches_the_app(a):
    a.fk.sp.error = NoDevice("x")
    assert "Spotify не запущен" in a.handle("продолжи")
    assert ("launch", "spotify") in calls(a)


def test_find_song_asks_then_plays(a):
    q = a.handle('найди песню "Ниа" в спотифай')
    assert q == "Нашёл Ниа, исполнитель Исполнитель. Включить, сэр?"
    assert ("search", "Ниа") in a.fk.sp.calls
    assert "Включаю Ниа — Исполнитель" in a.handle("да")
    assert ("play", "spotify:track:1", None) in a.fk.sp.calls


def test_find_song_decline(a):
    a.handle("найди песню Ниа в спотифай")
    assert a.handle("нет") == "Хорошо, сэр."
    assert not [c for c in a.fk.sp.calls if c[0] == "play"]


def test_find_song_not_found(a):
    a.fk.sp.search_track = lambda q: None
    assert "Ничего не нашёл" in a.handle("найди песню абвгд в спотифай")


def test_find_song_without_api_opens_search_in_app(a_nosp):
    out = a_nosp.handle("найди песню Ниа в спотифай")
    assert "Открыл поиск" in out
    assert ("start", "spotify:search:%D0%9D%D0%B8%D0%B0") in calls(a_nosp)


def test_now_playing_like_playlist(a):
    assert a.handle("что играет") == "Сейчас играет Ниа — Исполнитель."
    assert "Поставил лайк" in a.handle("поставь лайк")
    assert a.handle("включи мой плейлист") == "Какой плейлист, сэр?"
    assert "Включаю плейлист Вечерний" in a.handle("вечерний")
    assert "Плейлист «рок» не нашёл" in a.handle("включи плейлист рок")


def test_spotify_only_features_explain_when_not_configured(a_nosp):
    for phrase in ("что играет", "поставь лайк", "включи плейлист рок"):
        assert "не настроен" in a_nosp.handle(phrase)


# ================= YouTube =================
def test_youtube_search_opens_results(a):
    a.handle("найди на ютубе Lens")
    a.handle("поищи в ютубе дота гайд")
    urls = [c[1] for c in calls(a, "open_url")]
    assert urls == ["https://www.youtube.com/results?search_query=lens",
                    "https://www.youtube.com/results?search_query=%D0%B4%D0%BE%D1%82%D0%B0%20%D0%B3%D0%B0%D0%B9%D0%B4"]


def test_youtube_controls(a):
    a.handle("поставь видео на паузу")
    a.handle("перемотай на 30 секунд")
    a.handle("перемотай назад на минуту")
    a.handle("полный экран")
    assert calls(a, "youtube_key") == [("youtube_key", "k", 1), ("youtube_key", "l", 3),
                                       ("youtube_key", "j", 6), ("youtube_key", "f", 1)]


def test_youtube_tab_missing(a):
    a.fk.pc.youtube_tab = False
    assert "Не нашёл открытую вкладку YouTube" in a.handle("пауза на ютубе")


# ================= сайты, программы, папки =================
@pytest.mark.parametrize("phrase,url", [
    ("открой ютуб", "https://www.youtube.com"), ("открой гугл", "https://www.google.com"),
    ("открой яндекс", "https://ya.ru"), ("открой твич", "https://www.twitch.tv"),
    ("открой телеграм", "https://web.telegram.org"), ("открой telegram web", "https://web.telegram.org"),
    ("открой дискорд в браузере", "https://discord.com/app"), ("открой стим сайт", "https://store.steampowered.com"),
    ("открой дотабафф", "https://www.dotabuff.com"), ("открой дотапротрекер", "https://dota2protracker.com"),
])
def test_sites(a, phrase, url):
    a.handle(phrase)
    assert ("open_url", url) in calls(a)


def test_dota_hero_pages(a):
    a.handle("открой дотабафф для пуджа")
    a.handle("открой дотапротрекер пудж")
    a.handle("открой дотабафф антимага")
    urls = [c[1] for c in calls(a, "open_url")]
    assert urls == ["https://www.dotabuff.com/heroes/pudge", "https://dota2protracker.com/hero/Pudge",
                    "https://www.dotabuff.com/heroes/anti-mage"]


def test_unknown_hero_opens_main_page_and_says_so(a):
    out = a.handle("открой дотабафф для чебурашки")
    assert "не нашёл" in out and ("open_url", "https://www.dotabuff.com") in calls(a)


def test_launch_programs(a):
    a.fk.pc.running.add("steam.exe")
    for p in ("запусти дискорд", "запусти дота 2", "открой диспетчер задач", "запусти стим"):
        a.handle(p)
    assert [c[1] for c in calls(a, "launch")] == ["дискорд", "дота", "диспетчер задач", "стим"]


def test_launch_dota_with_steam_off_says_to_log_in(a):
    out = a.handle("запусти Dota 2")
    assert "Steam не был запущен" in out and "войдите в аккаунт" in out


def test_folders(a):
    for p in ("открой загрузки", "открой рабочий стол", "открой картинки", "открой скриншоты"):
        a.handle(p)
    assert [c[1] for c in calls(a, "folder")] == ["downloads", "desktop", "pictures", "screenshots"]


def test_unknown_open_is_left_for_old_handler(a):
    assert a.x.route("открой что-то странное", "открой что-то странное", "local") is None


def test_programs_blocked_from_telegram(a):
    assert "выключено" in a.handle("запусти дискорд", source="telegram")
    assert "выключено" in a.handle("открой ютуб", source="telegram")


# ================= питание: «да» + отсчёт 15 секунд =================
@pytest.mark.parametrize("phrase,ask,action", [
    ("перезапусти компьютер", "Перезапустить компьютер, сэр?", "restart"),
    ("выключи ПК", "Выключить компьютер, сэр?", "shutdown"),
    ("спящий режим", "Перевести компьютер в спящий режим, сэр?", "sleep"),
])
def test_power_needs_yes_then_countdown(a, phrase, ask, action):
    assert a.handle(phrase) == ask
    assert calls(a, "power") == []
    out = a.handle("да")
    assert "через 15 секунд" in out and "отмена" in out
    assert a.tick(NOW + timedelta(seconds=14)) == [] and calls(a, "power") == []
    msgs = a.tick(NOW + timedelta(seconds=15))
    assert calls(a, "power") == [("power", action)] and msgs and msgs[0].startswith("Выполняю")
    assert a.tick(NOW + timedelta(seconds=30)) == []     # один раз


def test_power_cancel_during_countdown(a):
    a.handle("перезапусти компьютер")
    a.handle("да")
    assert "Отменил: перезапуск" in a.handle("отмена")
    a.tick(NOW + timedelta(minutes=1))
    assert calls(a, "power") == []


def test_power_declined(a):
    a.handle("выключи компьютер")
    assert a.handle("нет") == "Хорошо, сэр."
    assert a.countdown is None


def test_power_answer_that_is_not_yes_is_not_confirmation(a):
    a.handle("перезапусти компьютер")
    assert a.handle("который час") == "Сейчас 10:00."
    assert a.countdown is None and calls(a, "power") == []


def test_power_confirmation_expires(a):
    a.handle("перезапусти компьютер")
    a.fk.clock["now"] = NOW + timedelta(minutes=5)
    assert "не расслышал" in a.handle("да")
    assert a.countdown is None


def test_power_not_from_telegram_by_default(a):
    assert "выключено" in a.handle("перезапусти компьютер", source="telegram")
    assert a.pending == {}


def test_lock_is_immediate(a):
    a.handle("заблокируй компьютер")
    assert calls(a, "power") == [("power", "lock")]


def test_custom_countdown_length(tmp_path, monkeypatch):
    a = make(tmp_path, monkeypatch, env={"JARVIS_COUNTDOWN": "5"})
    a.handle("перезапусти компьютер")
    assert "через 5 секунд" in a.handle("да")


# ================= закрыть программу: всегда «да» =================
def test_close_program_asks_first(a):
    a.fk.pc.running.add("Discord.exe")
    assert a.handle("закрой дискорд") == "Закрыть Discord, сэр?"
    assert calls(a, "close") == []
    assert a.handle("да") == "Discord закрыт."
    assert calls(a, "close") == [("close", "Discord.exe")]


def test_close_declined_and_not_running(a):
    a.handle("закрой дискорд")
    assert a.handle("нет") == "Хорошо, сэр."
    assert a.handle("закрой браузер") == "Закрыть браузер, сэр?"
    assert a.handle("да") == "Браузер и не был запущен."
    assert ("close", "opera.exe") in calls(a)


def test_close_unknown_name_is_not_a_command(a):
    assert "не расслышал" in a.handle("закрой дверь")


def test_close_blocked_from_telegram(a):
    assert "выключено" in a.handle("закрой дискорд", source="telegram")


# ================= окна, состояние, калькулятор =================
def test_minimize_status_calc(a):
    a.handle("сверни все окна")
    assert calls(a, "minimize_all")
    assert a.handle("как дела у компьютера") == "Процессор загружен на 10 процентов."
    assert a.handle("сколько будет 15 процентов от 2300") == "Получится 345."
    assert a.handle("сколько будет два плюс два") == "Получится 4."
    assert "Не смог посчитать" in a.handle("сколько будет абракадабра")


# ================= режимы =================
def test_game_mode_launches_discord_spotify_dota(a):
    a.fk.pc.running.add("steam.exe")
    out = a.handle("включи режим игры")
    assert [c[1] for c in calls(a, "launch")] == ["дискорд", "спотифай", "дота"]
    assert "Режим игры включён" in out and a.store.meta("game_mode") is True


def test_game_mode_when_steam_not_running_mentions_login(a):
    assert "Войдите в аккаунт" in a.handle("включи режим игры")


def test_work_mode_asks_then_closes_steam_dota_quiet_and_dnd(a):
    a.fk.pc.running.update({"dota2.exe", "steam.exe"})
    a.store.set_meta("game_mode", True)
    q = a.handle("включи режим работы")
    assert "Закрою Steam и Dota 2" in q and calls(a, "close") == []
    out = a.handle("да")
    assert [c[1] for c in calls(a, "close")] == ["dota2.exe", "steam.exe"]
    assert ("set_volume", 30) in calls(a) and a.dnd and a.store.meta("game_mode") is False
    assert "Режим работы включён" in out
    assert "выключен" in a.handle("выключи режим работы") and not a.dnd


def test_rest_mode_opens_youtube(a):
    a.store.set_meta("game_mode", True)
    assert "Отдыхайте" in a.handle("перекур")
    assert ("open_url", "https://www.youtube.com") in calls(a) and a.store.meta("game_mode") is False
    a.handle("режим отдыха")


def test_game_mode_off(a):
    a.handle("включи режим игры")
    a.handle("выключи режим игры")
    assert a.store.meta("game_mode") is False


# ================= таймеры и будильник =================
def test_timer(a):
    assert a.handle("таймер на 15 минут") == "Таймер на 15 минут запущен."
    assert a.handle("поставь таймер на полчаса") == "Таймер на 30 минут запущен."
    assert "30 секунд" in a.handle("таймер на 30 секунд")
    assert a.handle("таймер на 2 секунды") == "Таймер на 2 секунды запущен."
    whens = sorted(i["when"] for i in a.store.active() if i["kind"] == "timer")
    assert whens[0] == "2026-11-17 10:00" and whens[-1] == "2026-11-17 10:30"


def test_timer_without_duration_asks(a):
    assert "На сколько поставить таймер" in a.handle("таймер на чуть-чуть")


@pytest.mark.parametrize("phrase,when", [
    ("поставь будильник на 7 утра", "2026-11-18 07:00"), ("разбуди меня в 7", "2026-11-18 07:00"),
    ("будильник на 7:30", "2026-11-18 07:30"), ("разбуди меня в 6", "2026-11-18 06:00"),
    ("разбуди меня через 8 часов", "2026-11-17 18:00"), ("будильник на 14:00", "2026-11-17 14:00"),
])
def test_alarm_times(a, phrase, when):
    a.handle(phrase)
    alarm = [i for i in a.store.active() if i["kind"] == "alarm"][0]
    assert alarm["when"] == when


def test_alarm_without_time_asks(a):
    assert "На какое время поставить будильник" in a.handle("будильник на когда-нибудь")


def test_alarm_fires_with_spotify_and_is_urgent(a):
    from jarvis.spoken import Urgent
    a.handle("будильник на 11:00")
    item = a.store.due(NOW + timedelta(hours=1))[0][0]
    text = a.on_alert(item, 0, NOW + timedelta(hours=1))
    assert isinstance(text, Urgent) and "Пора вставать" in text and "Музыку включить не удалось" not in text
    assert ("resume",) in a.fk.sp.calls          # плейлист не задан — просто продолжаем музыку


def test_alarm_plays_chosen_playlist(tmp_path, monkeypatch):
    a = make(tmp_path, monkeypatch, env={"JARVIS_ALARM_PLAYLIST": "вечерний"})
    a.on_alert({"kind": "alarm", "title": "Будильник"}, 0, NOW)
    assert ("play", None, "spotify:playlist:9") in a.fk.sp.calls


def test_alarm_falls_back_to_beep_and_voice(a_nosp):
    text = a_nosp.on_alert({"kind": "alarm", "title": "Будильник"}, 0, NOW)
    assert "играет сигнал" in text and ("beep", 3) in calls(a_nosp)
    a_nosp.fk.pc.calls.clear()
    a_nosp.on_alert({"kind": "alarm", "title": "Будильник"}, 0, NOW)
    a_nosp.fk.sp.configured = True
    a_nosp.fk.sp.error = SpotifyError("down")
    assert "играет сигнал" in a_nosp.on_alert({"kind": "alarm", "title": "Будильник"}, 0, NOW)


def test_timer_fires_with_beep(a):
    from jarvis.spoken import Urgent
    text = a.on_alert({"kind": "timer", "title": "Таймер"}, 0, NOW)
    assert isinstance(text, Urgent) and text == "Таймер: время вышло." and ("beep", 3) in calls(a)


def test_other_items_have_no_alert_override(a):
    assert a.on_alert({"kind": "reminder", "title": "x"}, 0, NOW) is None


def test_alarm_snooze_five_more_minutes_and_stop(a):
    a.handle("будильник на 10:00")         # ровно «сейчас» — это уже завтра
    assert [i["when"] for i in a.store.active() if i["kind"] == "alarm"] == ["2026-11-18 10:00"]
    a.store.delete_item(a.store.active()[0]["id"])
    a.handle("будильник на 10:01")
    a.fk.clock["now"] = NOW + timedelta(minutes=1)
    a.store.due(a.fk.clock["now"])         # будильник сработал
    assert a.handle("ещё пять минут").startswith("Напомню сегодня в 10:06")
    a.fk.clock["now"] = NOW + timedelta(minutes=6)
    a.store.due(a.fk.clock["now"])
    assert a.handle("хватит") == "Доброе утро, сэр."
    assert ("pause_if_playing",) in a.fk.sp.calls


def test_cancel_alarms_and_timers(a):
    a.handle("будильник на 7 утра")
    a.handle("таймер на 5 минут")
    assert a.handle("выключи будильник") == "Будильник выключен."
    assert a.handle("отмени таймер") == "Таймер выключен."
    assert "Активных будильников нет" in a.handle("выключи будильник")


# ================= повторяющиеся напоминания =================
def test_recurring_create_list_stop(a):
    assert "каждые 2 часа" in a.handle("напоминай пить воду каждые два часа")
    assert "каждые 1 час" in a.handle("напоминай делать перерыв каждый час")
    assert "Пить воду — каждые 2 часа" in a.handle("какие повторяющиеся напоминания")
    assert "Больше не напоминаю: Пить воду" in a.handle("останови напоминания про воду")
    assert "Такого повторяющегося напоминания нет" in a.handle("перестань напоминать про воду")


@pytest.mark.parametrize("phrase,minutes", [
    ("напоминай пить воду каждые два часа", 120), ("напоминай мне пить воду каждые 30 минут", 30),
    ("напоминай размяться каждый час", 60), ("напоминай пить воду каждые полчаса", 30),
])
def test_recurring_intervals(a, phrase, minutes):
    a.handle(phrase)
    assert a.store.recurring()[0]["interval_min"] == minutes


def test_recurring_fires_and_reschedules(a):
    a.handle("напоминай пить воду каждые два часа")
    assert a.tick(NOW + timedelta(hours=1, minutes=59)) == []
    assert a.tick(NOW + timedelta(hours=2)) == ["Напоминаю: Пить воду."]
    assert a.tick(NOW + timedelta(hours=3)) == []
    assert a.tick(NOW + timedelta(hours=4)) == ["Напоминаю: Пить воду."]


def test_recurring_asks_about_match_during_game(a):
    a.handle("напоминай пить воду каждые два часа")
    a.store.set_meta("game_mode", True)
    a.fk.clock["now"] = NOW + timedelta(hours=2)          # часы ассистента и планировщика идут вместе
    assert a.tick(a.fk.clock["now"]) == ["У вас матч, сэр?"]
    assert "напомню позже" in a.handle("да")
    assert a.tick(NOW + timedelta(hours=2, minutes=19)) == []
    a.fk.clock["now"] = NOW + timedelta(hours=2, minutes=20)
    assert a.tick(a.fk.clock["now"]) == ["У вас матч, сэр?"]      # режим игры всё ещё включён — спросит снова
    assert a.handle("нет") == "Напоминаю: Пить воду."


def test_recurring_no_match_reminds_immediately(a):
    a.handle("напоминай пить воду каждые два часа")
    a.store.set_meta("game_mode", True)
    a.tick(NOW + timedelta(hours=2))
    assert a.handle("нет") == "Напоминаю: Пить воду."


def test_recurring_asks_when_dota_is_running_even_without_game_mode(a):
    a.fk.pc.running.add("dota2.exe")
    a.handle("напоминай пить воду каждые два часа")
    assert a.tick(NOW + timedelta(hours=2)) == ["У вас матч, сэр?"]


def test_recurring_postponed_silently_if_dialog_is_open(a):
    a.handle("напоминай пить воду каждые два часа")
    a.store.set_meta("game_mode", True)
    a.handle("напомни полить цветы")           # открыт вопрос «Когда напомнить?»
    assert a.tick(NOW + timedelta(hours=2)) == []
    assert a.store.recurring()[0]["next"] == "2026-11-17 12:05"


# ================= текст, буфер, сеть =================
def test_dictation_keeps_case(a):
    assert a.handle("Напечатай Привет, Мир") == "Напечатал, сэр."
    assert calls(a, "type_text") == [("type_text", "Привет, Мир")]
    assert "выключено" in a.handle("напечатай привет", source="telegram")


def test_save_link_from_clipboard(a):
    a.fk.pc.clipboard = "https://example.com/page"
    assert a.handle("запомни эту ссылку") == "Сохранил ссылку в заметки."
    assert a.store.notes()[0]["text"] == "Ссылка: https://example.com/page"
    a.fk.pc.clipboard = "просто текст"
    assert "нет ссылки" in a.handle("сохрани ссылку")


def test_read_clipboard_asks_before_reading_aloud(a):
    a.fk.pc.clipboard = "пароль: hunter2"
    q = a.handle("прочитай буфер обмена")
    assert q == "В буфере 15 символов. Прочитать вслух, сэр?" and "hunter2" not in q
    assert a.handle("да") == "пароль: hunter2"
    a.handle("что в буфере")
    assert a.handle("нет") == "Хорошо, сэр."
    a.fk.pc.clipboard = ""
    assert a.handle("прочитай буфер") == "Буфер обмена пуст."


def test_bluetooth_and_wifi(a):
    a.handle("включи блютуз")
    a.handle("выключи bluetooth")
    a.handle("включи вайфай")
    a.handle("переподключи wi-fi")
    assert [c[0] for c in calls(a)] == ["bluetooth", "bluetooth", "wifi_on", "wifi_reconnect"]
    assert ("bluetooth", True) in calls(a) and ("bluetooth", False) in calls(a)


def test_wifi_off_is_refused_by_owners_decision(a):
    out = a.handle("выключи вайфай")
    assert "отключить Wi-Fi я не стану" in out and calls(a) == []
    assert "не стану" in a.handle("отключи wi-fi")


def test_screenshot(a):
    assert "«Скриншоты» в Картинках" in a.handle("сделай скриншот")
    assert calls(a, "screenshot")


# ================= внешние данные (подставные сервисы) =================
def test_currency(a):
    a.handle("сколько стоит доллар")
    a.handle("курс евро")
    a.handle("сколько стоит злотый")
    assert [c[1] for c in a.fk.svc.calls] == ["доллар", "евро", "злотый"]


def test_translate_is_spoken_in_target_language(a):
    out = a.handle("как будет по-английски Доброе утро")
    assert out.parts == [("ru", "По-английски:"), ("en", "[en] Доброе утро")]
    out = a.handle("переведи на польский спасибо большое")
    assert out.parts[1] == ("pl", "[pl] спасибо большое")
    assert a.handle("как по-польски привет").parts[1][0] == "pl"


def test_dota_questions(a):
    assert a.handle("кто в мете") == "meta:"
    assert a.handle("мой последний матч") == "last_match:"
    assert a.handle("против инвокера кого брать") == "counters:Invoker"
    assert a.handle("контрпик на пуджа") == "counters:Pudge"
    assert "Не нашёл героя" in a.handle("против чебурашки кого брать")


def test_twitch(a):
    assert a.handle("кто сейчас в эфире") == "twitch:"


def test_mail_important_is_routed(a, monkeypatch):
    monkeypatch.setattr("jarvis.intents.mail.important", lambda cfg: "Важное письмо от банка.")
    assert a.handle("прочитай письмо и выбери главное") == "Важное письмо от банка."
    assert a.handle("прочитай главное") == "Важное письмо от банка."
    assert a.handle("что в почте важное") == "Важное письмо от банка."


# ================= устройство вывода =================
def test_audio_output_needs_config(a):
    assert "JARVIS_AUDIO_DEVICES" in a.handle("поменяй устройство вывода")


def test_audio_output_by_name_and_cycling(tmp_path, monkeypatch):
    a = make(tmp_path, monkeypatch, env={"JARVIS_AUDIO_DEVICES": "наушники=Headphones;колонки=Speakers;блютуз=JBL"})
    assert a.handle("переключи звук на наушники") == "Переключил звук: наушники."
    assert ("audio_output", "Headphones") in calls(a)
    a.handle("поменяй устройство вывода")
    a.handle("поменяй устройство вывода")
    a.handle("поменяй устройство вывода")
    assert [c[1] for c in calls(a, "audio_output")] == ["Headphones", "Speakers", "JBL", "Headphones"]
    assert "Есть: наушники" in a.handle("переключи звук на микроволновку")


# ================= новости =================
def test_news_default_languages_and_spoken_parts(a, monkeypatch):
    seen = {}
    def fake(feeds, langs=None, limit=5):
        seen["langs"] = langs
        return [("pl", "Pierwszy"), ("pl", "Drugi"), ("uk", "Перший")]
    monkeypatch.setattr("jarvis.intents.info.news_items", fake)
    out = a.handle("новости")
    assert seen["langs"] == {"pl", "uk"}
    assert out.parts == [("ru", "Новости Польши."), ("pl", "Pierwszy. Drugi."),
                         ("ru", "Новости Украины."), ("uk", "Перший.")]


@pytest.mark.parametrize("phrase,langs", [("новости по-русски", {"ru"}), ("польские новости", {"pl"}),
                                          ("украинские новости", {"uk"}), ("русские новости", {"ru"})])
def test_news_language_requests(a, monkeypatch, phrase, langs):
    seen = {}
    monkeypatch.setattr("jarvis.intents.info.news_items", lambda f, l=None, limit=5: seen.update(l=l) or [("pl", "x")])
    a.handle(phrase)
    assert seen["l"] == langs


def test_news_unavailable(a, monkeypatch):
    monkeypatch.setattr("jarvis.intents.info.news_items", lambda *args, **kw: [])
    assert a.handle("новости") == "Не удалось получить новости."


# ================= пылесос =================
def test_vacuum_kitchen_asks_dry_or_wet_then_starts(a):
    assert a.handle("убери на кухне") == "Сухая или влажная уборка, сэр?"
    assert a.handle("сухая") == "Запускаю сухую уборку: кухню."
    assert a.fk.vac.calls == [("start", "kitchen", "dry")]


def test_vacuum_wet_word_skips_the_question(a):
    a.handle("помой пол на кухне")
    a.handle("джарвис помой пол в спальне".replace("джарвис ", ""))
    assert a.fk.vac.calls == [("start", "kitchen", "wet"), ("start", "bedroom", "wet")]


def test_vacuum_dry_words(a):
    a.handle("пропылесось в гостиной")
    a.handle("подмети в ванной")
    assert a.fk.vac.calls == [("start", "living", "dry"), ("start", "bathroom", "dry")]


def test_vacuum_without_room_asks_open_question(a):
    assert a.handle("убери") == "Какую комнату, сэр?"
    assert a.handle("прихожая") == "Сухая или влажная уборка, сэр?"
    a.handle("влажная")
    assert a.fk.vac.calls == [("start", "hall", "wet")]


def test_vacuum_hall_and_corridor_are_one_zone(a):
    a.handle("помой пол в коридоре")
    a.handle("запусти пылесос в прихожей")
    a.handle("мокрая")
    assert [c[1] for c in a.fk.vac.calls] == ["hall", "hall"]


def test_vacuum_start_phrase_asks_mode(a):
    assert a.handle("запусти пылесос на кухне") == "Сухая или влажная уборка, сэр?"


def test_vacuum_whole_flat_stop_dock(a):
    a.handle("помой пол везде")
    assert a.handle("останови пылесос") == "Остановил пылесос."
    assert a.handle("пылесос на базу") == "Отправляю пылесос на базу."
    assert a.fk.vac.calls == [("start", "all", "wet"), ("stop",), ("dock",)]


def test_vacuum_answer_that_is_not_an_answer(a):
    a.handle("убери на кухне")
    assert a.handle("который час") == "Сейчас 10:00."
    assert a.fk.vac.calls == []


def test_clean_something_else_is_not_vacuum(a):
    a.handle("будильник на 7 утра")
    a.handle("убери будильник")
    assert a.fk.vac.calls == [] and a.pending == {}


def test_vacuum_not_configured_is_honest(tmp_path, monkeypatch):
    a = make(tmp_path, monkeypatch)
    from jarvis.vacuum import NotConfigured
    a.vacuum = NotConfigured()
    a.handle("помой пол на кухне")
    out = a.handle("помой пол на кухне")
    assert "Пылесос пока не подключён" in out


def test_vacuum_allowed_from_telegram(a):
    a.handle("помой пол на кухне", source="telegram")
    assert a.fk.vac.calls == [("start", "kitchen", "wet")]


# ================= музыка при шуме (голосовой режим) =================
def test_noise_pauses_music_and_answer_resumes_it(a):
    a.voice_mode = True
    assert "не расслышал" in a.handle("бессвязное бормотание")
    assert ("pause_if_playing",) in a.fk.sp.calls
    a.handle("который час")
    assert ("resume",) in a.fk.sp.calls


def test_noise_does_not_pause_in_console_mode_or_without_api(a, a_nosp):
    a.handle("бессвязное бормотание")
    assert ("pause_if_playing",) not in a.fk.sp.calls
    a_nosp.voice_mode = True
    a_nosp.handle("бессвязное бормотание")
    assert a_nosp.fk.sp.calls == []


def test_music_not_resumed_if_we_did_not_pause_it(a):
    a.voice_mode = True
    a.fk.sp.playing = False
    a.handle("бормотание")
    a.handle("который час")
    assert ("resume",) not in a.fk.sp.calls


# ================= краткий ответ = Google в браузере =================
def test_search_opens_google_in_browser(a):
    assert a.handle("загугли погоду в Варшаве") == "Ищу в Google: погоду в варшаве."
    a.handle("найди в интернете сколько лет Варшаве")
    urls = [c[1] for c in calls(a, "open_url")]
    assert urls[0].startswith("https://www.google.com/search?q=") and "%D0%BF%D0%BE%D0%B3%D0%BE%D0%B4%D1%83" in urls[0]
    assert len(urls) == 2


def test_search_from_telegram_returns_link_not_pc_action(a, monkeypatch):
    monkeypatch.setattr("jarvis.assistant.info.web_search", lambda q: None)
    out = a.handle("загугли курс злотого", source="telegram")
    assert out.startswith("Ссылка на поиск в Google: https://www.google.com/search?q=") and calls(a) == []
