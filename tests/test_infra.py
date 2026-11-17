"""Нижний слой пунктов 3–10: Spotify-клиент, сервисы, почта, озвучка, автозапуск, голосовой цикл, планировщик.

Сеть, звук, микрофон и Windows подменены. Вживую ничего из этого не проверено.
"""
import builtins
import email.message
import json
from datetime import datetime, timedelta
from types import SimpleNamespace as NS

import pytest

import jarvis.cli as cli
from jarvis import autostart
from jarvis.config import Config
from jarvis.scheduler import Scheduler
from jarvis.services import ServiceError, Services
from jarvis.skills import info, mail
from jarvis.spoken import Spoken, Urgent
from jarvis.spotify import (NoDevice, Spotify, SpotifyError, authorization_url, exchange_code, make_pkce,
                            search_uri)
from jarvis.store import Store
from jarvis.tts import PiperEngine, Pyttsx3Engine, make_engine
from fakes import FakePc, make

NOW = datetime(2026, 11, 17, 10, 0)


# ---------- фальшивый HTTP ----------
class Resp:
    def __init__(self, status=200, data=None, text=""):
        self.status_code, self._data, self.text = status, data, text or (json.dumps(data) if data is not None else "")
        self.content = self.text.encode()

    def json(self):
        return self._data


class Http:
    def __init__(self, routes):
        self.routes, self.log = routes, []

    def _find(self, method, url):
        for (m, frag), val in self.routes.items():
            if m == method and frag in url:
                return val(url) if callable(val) else val
        return Resp(404, text="no route")

    def get(self, url, **kw):
        self.log.append(("GET", url, kw))
        return self._find("GET", url)

    def post(self, url, **kw):
        self.log.append(("POST", url, kw))
        return self._find("POST", url)

    def request(self, method, url, **kw):
        self.log.append((method, url, kw))
        return self._find(method, url)


# ================= Spotify =================
def spotify(routes, clock=None):
    cfg = NS(spotify_client_id="cid", spotify_refresh_token="rt")
    base = {("POST", "/api/token"): Resp(200, {"access_token": "AT", "expires_in": 3600})}
    return Spotify(cfg, http=Http({**base, **routes}), clock=clock or (lambda: 1000.0), sleeper=lambda s: None)


def test_spotify_not_configured():
    s = Spotify(NS(spotify_client_id="", spotify_refresh_token=""))
    assert not s.configured
    with pytest.raises(SpotifyError):
        s.next()


def test_spotify_token_is_refreshed_once_and_sent_as_bearer():
    s = spotify({("POST", "/me/player/next"): Resp(204)})
    s.next()
    s.next()
    tokens = [e for e in s.http.log if "/api/token" in e[1]]
    assert len(tokens) == 1 and tokens[0][2]["data"]["grant_type"] == "refresh_token"
    assert s.http.log[-1][2]["headers"] == {"Authorization": "Bearer AT"}


def test_spotify_token_expiry_refreshes_again():
    t = {"now": 1000.0}
    s = spotify({("POST", "/me/player/next"): Resp(204)}, clock=lambda: t["now"])
    s.next()
    t["now"] += 4000
    s.next()
    assert len([e for e in s.http.log if "/api/token" in e[1]]) == 2


def test_spotify_bad_refresh_token_message():
    s = Spotify(NS(spotify_client_id="c", spotify_refresh_token="bad"), http=Http({("POST", "/api/token"): Resp(400)}))
    with pytest.raises(SpotifyError, match="токен недействителен"):
        s.next()


def test_spotify_search_and_play():
    data = {"tracks": {"items": [{"name": "Ниа", "uri": "spotify:track:1", "artists": [{"name": "А"}, {"name": "Б"}]}]}}
    s = spotify({("GET", "/search"): Resp(200, data), ("PUT", "/me/player/play"): Resp(204)})
    assert s.search_track("Ниа") == {"name": "Ниа", "artist": "А, Б", "uri": "spotify:track:1"}
    s.play(uri="spotify:track:1")
    assert s.http.log[-1][2]["json"] == {"uris": ["spotify:track:1"]}
    s.play(context_uri="spotify:playlist:9")
    assert s.http.log[-1][2]["json"] == {"context_uri": "spotify:playlist:9"}
    s.resume()
    assert s.http.log[-1][2]["json"] is None


def test_spotify_search_nothing():
    s = spotify({("GET", "/search"): Resp(200, {"tracks": {"items": []}})})
    assert s.search_track("абвгд") is None


def test_spotify_no_active_device():
    s = spotify({("PUT", "/me/player/play"): Resp(404, text='{"error":{"reason":"NO_ACTIVE_DEVICE"}}')})
    with pytest.raises(NoDevice):
        s.play(uri="x")


def test_spotify_401_retries_with_new_token():
    answers = iter([Resp(401), Resp(204)])
    s = spotify({("POST", "/me/player/next"): lambda url: next(answers)})
    s.next()
    assert len([e for e in s.http.log if "/api/token" in e[1]]) == 2


def test_spotify_server_error():
    s = spotify({("POST", "/me/player/next"): Resp(500)})
    with pytest.raises(SpotifyError, match="500"):
        s.next()


def test_spotify_current_like_playlist_pause_if_playing():
    cur = {"item": {"id": "7", "name": "Ниа", "artists": [{"name": "А"}]}, "is_playing": True}
    pls = {"items": [{"name": "Вечерний Чил", "uri": "spotify:playlist:9"}, None]}
    s = spotify({("GET", "/currently-playing"): Resp(200, cur), ("PUT", "/me/tracks"): Resp(200, {}, text="{}"),
                 ("GET", "/me/playlists"): Resp(200, pls), ("PUT", "/me/player/pause"): Resp(204)})
    assert s.current() == {"id": "7", "name": "Ниа", "artist": "А", "is_playing": True}
    assert s.like_current()["name"] == "Ниа"
    assert [e for e in s.http.log if e[1].endswith("/me/tracks")][0][2]["json"] == {"ids": ["7"]}
    assert s.find_playlist("вечерний") == {"name": "Вечерний Чил", "uri": "spotify:playlist:9"}
    assert s.find_playlist("рок") is None
    assert s.pause_if_playing() is True


def test_spotify_pause_if_playing_when_idle():
    s = spotify({("GET", "/currently-playing"): Resp(204)})
    assert s.pause_if_playing() is False
    assert not any(e[1].endswith("/pause") for e in s.http.log)


def test_spotify_search_uri_and_pkce_flow():
    assert search_uri("Ниа") == "spotify:search:%D0%9D%D0%B8%D0%B0"
    verifier, challenge = make_pkce()
    assert len(verifier) >= 43 and "=" not in challenge
    url = authorization_url("cid", "http://127.0.0.1:8888/callback", challenge, "st")
    assert "code_challenge_method=S256" in url and "user-modify-playback-state" in url and "state=st" in url
    http = Http({("POST", "/api/token"): Resp(200, {"refresh_token": "RT"})})
    assert exchange_code("cid", "uri", "code", verifier, http) == "RT"
    assert http.log[0][2]["data"]["code_verifier"] == verifier
    with pytest.raises(SpotifyError):
        exchange_code("cid", "uri", "code", verifier, Http({("POST", "/api/token"): Resp(400)}))


# ================= сервисы =================
def svc(routes, **cfg):
    base = dict(dota_id="", twitch_client_id="", twitch_token="", twitch_user_id="")
    base.update(cfg)
    return Services(NS(**base), http=Http(routes))


def test_rates_in_dollars_dollar_in_zloty():
    s = svc({("GET", "open.er-api.com"): Resp(200, {"rates": {"PLN": 4.0, "EUR": 0.92}})})
    assert s.rate_text("доллар") == "Один доллар стоит 4,00 злотого."
    assert s.rate_text("евро") == "Один евро стоит 1,09 доллара."
    assert s.rate_text("злотый") == "Один злотый стоит 0,25 доллара."


def test_service_errors_are_readable():
    s = svc({("GET", "open.er-api.com"): Resp(500)})
    with pytest.raises(ServiceError, match="500"):
        s.rate_text("доллар")

    class Boom:
        def get(self, *a, **k):
            raise OSError("no net")
    with pytest.raises(ServiceError, match="Нет связи"):
        Services(NS(), http=Boom()).rate_text("доллар")


def test_translate_detects_source_language():
    s = svc({("GET", "mymemory"): Resp(200, {"responseData": {"translatedText": "Good morning"}, "responseStatus": 200})})
    assert s.translate("Доброе утро", "en") == "Good morning"
    assert s.http.log[0][2]["params"] == {"q": "Доброе утро", "langpair": "ru|en"}
    assert s.translate("Dzień dobry", "ru") == "Good morning"
    assert s.http.log[1][2]["params"]["langpair"] == "pl|ru"
    assert s.translate("привет", "ru") == "привет"      # тот же язык — не ходим в сеть
    assert len(s.http.log) == 2


def test_translate_failure():
    s = svc({("GET", "mymemory"): Resp(200, {"responseData": {"translatedText": ""}, "responseStatus": 403})})
    with pytest.raises(ServiceError):
        s.translate("привет", "en")


HEROES = [{"id": 1, "localized_name": "Anti-Mage"}, {"id": 14, "localized_name": "Pudge"}, {"id": 2, "localized_name": "Axe"}]


def test_dota_meta_orders_by_winrate_among_popular_heroes():
    stats = [{"localized_name": "Pudge", **{f"{n}_pick": 100 for n in range(5, 9)}, **{f"{n}_win": 60 for n in range(5, 9)}},
             {"localized_name": "Axe", **{f"{n}_pick": 100 for n in range(5, 9)}, **{f"{n}_win": 50 for n in range(5, 9)}},
             {"localized_name": "Anti-Mage", **{f"{n}_pick": 1 for n in range(5, 9)}, **{f"{n}_win": 1 for n in range(5, 9)}}]
    out = svc({("GET", "heroStats"): Resp(200, stats)}).meta(top=2)
    assert out.startswith("Сильные герои сейчас: Пудж — 60 процентов побед, Акс — 50 процентов побед")
    assert "Антимаг" not in out        # редкий герой с 100% не попадает


def test_dota_counters_lowest_winrate_against_hero():
    rows = [{"hero_id": 2, "games_played": 100, "wins": 40}, {"hero_id": 1, "games_played": 100, "wins": 70},
            {"hero_id": 14, "games_played": 10, "wins": 0}]       # мало матчей — не считаем
    s = svc({("GET", "/heroes/14/matchups"): Resp(200, rows), ("GET", "/api/heroes"): Resp(200, HEROES)})
    assert s.counters("Pudge", top=2) == "Против Пудж хорошо играют: Акс, Антимаг."


def test_dota_counters_unknown_hero():
    s = svc({("GET", "/api/heroes"): Resp(200, HEROES)})
    with pytest.raises(ServiceError):
        s.counters("Nobody")


def test_dota_last_match_win_and_loss_and_missing_id():
    row = {"hero_id": 14, "player_slot": 0, "radiant_win": True, "kills": 10, "deaths": 3, "assists": 12, "duration": 2100}
    routes = {("GET", "recentMatches"): Resp(200, [row]), ("GET", "/api/heroes"): Resp(200, HEROES)}
    out = svc(routes, dota_id="123").last_match()
    assert out == "Последний матч: Пудж, победа, 10 убийств, 3 смертей, 12 помощи, 35 минут."
    row2 = dict(row, player_slot=130)                                   # Dire, а победил Radiant
    assert "поражение" in svc({**routes, ("GET", "recentMatches"): Resp(200, [row2])}, dota_id="123").last_match()
    with pytest.raises(ServiceError, match="JARVIS_DOTA_ID"):
        svc(routes).last_match()
    with pytest.raises(ServiceError, match="профиль закрыт"):
        svc({("GET", "recentMatches"): Resp(200, [])}, dota_id="123").last_match()


def test_twitch_live_and_nobody_and_not_configured():
    cfg = dict(twitch_client_id="cid", twitch_token="tok", twitch_user_id="42")
    live = {"data": [{"user_name": "Nix", "game_name": "Dota 2"}, {"user_name": "Lens", "game_name": ""}]}
    s = svc({("GET", "streams/followed"): Resp(200, live)}, **cfg)
    assert s.twitch_live() == "В эфире: Nix — Dota 2; Lens."
    assert s.http.log[0][2]["headers"]["Authorization"] == "Bearer tok"
    assert "никого нет в эфире" in svc({("GET", "streams/followed"): Resp(200, {"data": []})}, **cfg).twitch_live()
    with pytest.raises(ServiceError, match="Twitch не настроен"):
        svc({}).twitch_live()


# ================= почта: «главное» без ИИ =================
def msg(sender, subject, body):
    m = email.message.EmailMessage()
    m["From"], m["Subject"] = sender, subject
    m.set_content(body)
    return m.as_bytes()


class FakeImap:
    def __init__(self, messages):
        self.messages, self.selected = messages, None

    def login(self, u, p):
        pass

    def select(self, box, readonly=False):
        self.selected = (box, readonly)

    def search(self, charset, crit):
        return "OK", [" ".join(str(i) for i in self.messages).encode()]

    def fetch(self, i, what):
        raw = self.messages[int(i)]
        if "HEADER" in what:
            head = email.message_from_bytes(raw)
            return "OK", [(b"", f"From: {head['From']}\r\nSubject: {head['Subject']}\r\n\r\n".encode())]
        return "OK", [(b"", raw)]

    def logout(self):
        pass


def mailcfg(**kw):
    return NS(mail_user="u", mail_password="p", imap_host="h", mail_vip=kw.get("vip", []))


def test_first_sentences_skips_quotes_links_and_signature():
    text = "Здравствуйте! Счёт на 5000 злотых до пятницы. Подробнее https://x.pl/abc тут.\n> цитата\n-- \nИван"
    assert mail.first_sentences(text) == "Здравствуйте! Счёт на 5000 злотых до пятницы."
    assert mail.first_sentences("Одно предложение без точки") == "Одно предложение без точки"


def test_important_mail_prefers_vip_senders_and_reads_without_marking():
    box = {1: msg("Bank PKO <alert@pkobp.pl>", "Платёж", "Списано 100 zł. Баланс 900 zł. Спасибо."),
           2: msg("Рассылка <news@shop.pl>", "Скидки", "Только сегодня скидки!")}
    imap = FakeImap(box)
    out = mail.important(mailcfg(vip=["pkobp"]), imap_factory=lambda: imap)
    assert out == "Важное письмо от Bank PKO. Тема: Платёж. Списано 100 zł. Баланс 900 zł. Ещё непрочитанных: 1."
    assert imap.selected == ("INBOX", True)                      # readonly: письма не помечаются прочитанными


def test_important_mail_newest_first_without_vip():
    box = {1: msg("A <a@x>", "Старое", "Старый текст."), 2: msg("B <b@x>", "Новое", "Новый текст.")}
    out = mail.important(mailcfg(), imap_factory=lambda: FakeImap(box))
    assert out.startswith("Письмо от B.") and "Тема: Новое." in out


def test_important_mail_nothing_and_not_configured():
    assert mail.important(mailcfg(), imap_factory=lambda: FakeImap({})) == "Непрочитанных писем нет."
    assert "не настроена" in mail.important(NS(mail_user="", mail_password="", mail_vip=[]))


# ================= новости по языкам =================
def test_news_items_group_by_language(monkeypatch):
    rss = "<rss><channel><item><title>Заголовок {n}</title></item><item><title>Другой</title></item></channel></rss>"
    monkeypatch.setattr(info, "_get", lambda url, **kw: NS(content=rss.replace("{n}", url[-1]).encode()))
    feeds = ["pl|http://a/1", "uk|http://b/2", "ru|http://c/3"]
    assert info.news_items(feeds, {"pl", "uk"}, limit=1) == [("pl", "Заголовок 1"), ("uk", "Заголовок 2")]
    assert [l for l, _ in info.news_items(feeds)] == ["pl", "pl", "uk", "uk", "ru", "ru"]


def test_news_items_survive_a_broken_feed(monkeypatch):
    def fake(url, **kw):
        if "bad" in url:
            raise OSError("down")
        return NS(content=b"<rss><channel><item><title>Ok</title></item></channel></rss>")
    monkeypatch.setattr(info, "_get", fake)
    assert info.news_items(["pl|http://bad", "pl|http://good"]) == [("pl", "Ok")]


def test_default_config_is_warsaw_with_polish_and_ukrainian_news(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    for k in ("JARVIS_CITY", "JARVIS_TZ", "JARVIS_NEWS_FEEDS"):
        monkeypatch.delenv(k, raising=False)
    cfg = Config()
    assert cfg.city == "Варшава" and cfg.timezone == "Europe/Warsaw"
    langs = [f.split("|")[0] for f in cfg.news_feeds]
    assert langs[:2] == ["pl", "pl"] and "uk" in langs and langs[-1] == "ru"


def test_config_pairs_and_numbers(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_AUDIO_DEVICES", "Наушники=Headphones; колонки = Speakers;мусор")
    monkeypatch.setenv("JARVIS_PIPER_MODELS", "ru=C:\\p\\ru.onnx;pl=C:\\p\\pl.onnx")
    monkeypatch.setenv("JARVIS_MAIL_VIP", "Bank, Boss ")
    cfg = Config()
    assert cfg.audio_devices == {"наушники": "Headphones", "колонки": "Speakers"}
    assert cfg.piper_models == {"ru": "C:\\p\\ru.onnx", "pl": "C:\\p\\pl.onnx"} and cfg.mail_vip == ["bank", "boss"]
    assert (cfg.volume_step, cfg.work_volume, cfg.countdown_seconds, cfg.dialog_seconds) == (20, 30, 15, 10)


# ================= озвучка =================
class FakeEngine:
    def __init__(self, voices):
        self.voices, self.props, self.said = voices, {}, []

    def getProperty(self, name):
        return self.voices

    def setProperty(self, name, value):
        self.props[name] = value

    def say(self, text):
        self.said.append((self.props.get("voice"), text))

    def runAndWait(self):
        pass


WIN_VOICES = [NS(id=r"HKEY\Speech\Voices\Tokens\MSTTS_V110_ruRU_IrinaM", name="Microsoft Irina Desktop - Russian"),
              NS(id=r"HKEY\Speech\Voices\Tokens\MSTTS_V110_plPL_PaulinaM", name="Microsoft Paulina - Polish"),
              NS(id=r"HKEY\Speech\Voices\Tokens\MSTTS_V110_enUS_ZiraM", name="Microsoft Zira Desktop - English (United States)")]


def test_pyttsx3_picks_voice_by_language():
    eng = Pyttsx3Engine(FakeEngine(WIN_VOICES))
    assert eng.languages() == {"ru", "pl", "en"}
    eng.say("Dzień dobry", "pl")
    eng.say("Привет", "ru")
    assert [v.split("_")[-1] if v else v for v, _ in eng.engine.said] == ["PaulinaM", "IrinaM"]


def test_pyttsx3_missing_language_falls_back_to_russian_and_reports():
    eng = Pyttsx3Engine(FakeEngine(WIN_VOICES))
    assert "uk" not in eng.languages()
    eng.say("Привіт", "uk")
    assert eng.engine.said[0][0].endswith("IrinaM")


def test_make_engine_selects_by_config(monkeypatch, tmp_path):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_TTS", "piper")
    monkeypatch.setenv("JARVIS_PIPER_MODELS", "ru=ru.onnx")
    assert isinstance(make_engine(Config()), PiperEngine)
    monkeypatch.setenv("JARVIS_TTS", "pyttsx3")
    fake = NS(init=lambda: FakeEngine(WIN_VOICES))
    assert isinstance(make_engine(Config(), pyttsx3_module=fake), Pyttsx3Engine)


def test_piper_runs_model_for_language_and_cleans_up(tmp_path):
    ran, played = [], []
    def run(cmd, text):
        ran.append((cmd, text))
        open(cmd[-1], "wb").write(b"RIFF")
        return 0
    eng = PiperEngine({"ru": "ru.onnx", "pl": "pl.onnx"}, runner=run, player=lambda p: played.append(open(p, "rb").read()))
    eng.say("Dzień dobry", "pl")
    eng.say("Привет", "uk")                     # украинской модели нет — русская
    assert [c[0][2] for c in ran] == ["pl.onnx", "ru.onnx"] and ran[0][1] == "Dzień dobry"
    assert played == [b"RIFF", b"RIFF"]
    import os
    assert not os.path.exists(ran[0][0][-1])    # временный wav удалён
    assert eng.languages() == {"ru", "pl"}


def test_piper_without_model_is_a_clear_error():
    with pytest.raises(RuntimeError, match="JARVIS_PIPER_MODELS"):
        PiperEngine({}).say("x", "pl")


# ================= автозапуск Windows =================
def test_autostart_command_uses_pythonw_and_project_dir():
    cmd = autostart.task_command(r"C:\Py\python.exe", "--voice --telegram", r"C:\Jarvis")
    assert cmd[:4] == ["schtasks", "/Create", "/TN", "Jarvis"]
    assert r'cd /d "C:\Jarvis"' in cmd[5] and r'"C:\Py\pythonw.exe" -m jarvis --voice --telegram' in cmd[5]
    assert "ONLOGON" in cmd and "/F" in cmd


def test_autostart_install_uninstall_with_runner():
    seen = []
    runner = lambda c: (seen.append(c) or (0, ""))
    assert autostart.install("--voice", runner=runner, python=r"C:\Py\python.exe", workdir="C:\\J", os_name="nt") == "Автозапуск включён."
    assert autostart.uninstall(runner=runner, os_name="nt") == "Автозапуск выключен."
    assert seen[1] == ["schtasks", "/Delete", "/TN", "Jarvis", "/F"]
    assert "Не удалось" in autostart.install(runner=lambda c: (1, "denied"), python="python.exe", workdir=".", os_name="nt")


def test_autostart_refuses_outside_windows():
    assert "только в Windows" in autostart.install(os_name="posix")
    assert "только в Windows" in autostart.uninstall(os_name="posix")


def test_cli_install_autostart_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli.autostart, "install", lambda flags: f"installed:{flags}")
    cli.main(["--install-autostart", "--voice"])
    cli.main(["--install-autostart"])
    out = capsys.readouterr().out
    assert "installed:--voice" in out and "installed:--voice --telegram" in out


# ================= голосовой цикл с диалоговым окном =================
class FakeVoice:
    def __init__(self, script):
        self.script, self.timeouts = list(script), []

    def listen(self, timeout=5, phrase_limit=20):
        self.timeouts.append(timeout)
        if not self.script:
            raise SystemExit("конец сценария")
        return self.script.pop(0)


def run_loop(script, handle):
    said = []
    voice = FakeVoice(script)
    cfg = NS(wake_words=["джарвис", "жарвис"])
    assistant = NS(handle=lambda c: said.append(("handle", c)) or handle(c))
    try:
        cli.run_voice_loop(voice, assistant, cfg, lambda r: said.append(("say", str(r))), dialog_seconds=10)
    except SystemExit:
        pass
    return said, voice


def test_voice_loop_wake_word_command_and_dialog_window_without_name():
    said, voice = run_loop(["Джарвис, напомни полить цветы", "завтра в 9", None, "шум без имени", "Джарвис, стоп"],
                           lambda c: f"ответ на {c}")
    assert ("handle", "напомни полить цветы") in said and ("handle", "завтра в 9") in said
    assert ("handle", "шум без имени") not in said               # окно закрылось тишиной — имя снова нужно
    assert said[-1] == ("say", "До связи.")
    assert voice.timeouts[:3] == [None, 10, 10]


def test_voice_loop_only_name_waits_seven_seconds():
    said, voice = run_loop(["Джарвис", "который час", None, "Джарвис, выход"], lambda c: "10:00")
    assert said[0] == ("say", "Да?") and ("handle", "который час") in said
    assert voice.timeouts[1] == 7


def test_voice_loop_name_only_and_silence_goes_back_to_listening():
    said, _ = run_loop(["Джарвис", None, "Джарвис, стоп"], lambda c: "x")
    assert said == [("say", "Да?"), ("say", "До связи.")]


def test_voice_loop_ignores_phrases_without_wake_word_and_strips_repeated_name():
    said, _ = run_loop(["просто разговор", "Джарвис, громче", "Джарвис, ещё громче", None, "Джарвис стоп"], lambda c: "ок")
    assert [c for k, c in said if k == "handle"] == ["громче", "ещё громче"]


def test_speak_uses_each_language_voice():
    spoken = []
    voice = NS(say=lambda text, lang="ru": spoken.append((lang, text)))
    cli.speak(voice, Spoken([("ru", "Новости Польши."), ("pl", "Pierwszy.")]))
    cli.speak(voice, "Обычная строка")
    cli.speak(None, "ничего")
    assert spoken == [("ru", "Новости Польши."), ("pl", "Pierwszy."), ("ru", "Обычная строка")]


# ================= планировщик =================
def test_scheduler_hooks_and_on_alert_override(tmp_path):
    store = Store(tmp_path / "d.json")
    store.add_item("alarm", "Будильник", NOW, [0])
    out = []
    s = Scheduler(store, out.append, on_alert=lambda item, off, now: Urgent("Подъём, сэр!"),
                  hooks=[lambda now: ["из хука"], lambda now: None])
    s.tick(NOW)
    assert out == ["Подъём, сэр!", "из хука"] and isinstance(out[0], Urgent)


def test_scheduler_default_alert_texts_for_timer_and_alarm(tmp_path):
    store = Store(tmp_path / "d.json")
    store.add_item("timer", "Таймер", NOW, [0])
    store.add_item("alarm", "Будильник", NOW, [0])
    out = []
    Scheduler(store, out.append).tick(NOW)
    assert out == ["Таймер: время вышло.", "Будильник. Пора вставать."]


def test_scheduler_checks_every_second_by_default(tmp_path):
    assert Scheduler(Store(tmp_path / "d.json"), lambda t: None).interval == 1.0


def test_scheduler_skips_telegram_duplicate_in_dnd(tmp_path):
    store = Store(tmp_path / "d.json")
    store.add_item("reminder", "Позвонить врачу", NOW, [0])
    tg, dnd = [], {"on": True}
    s = Scheduler(store, lambda t: None, notify_tg=tg.append, tg_dup_minutes=15, is_dnd=lambda: dnd["on"])
    s.tick(NOW)
    s.tick(NOW + timedelta(minutes=20))
    assert tg == []                      # «не беспокоить»: в Telegram и так ушло сразу
    dnd["on"] = False
    s.tick(NOW + timedelta(minutes=21))
    assert len(tg) == 1


def test_store_recurring_survives_restart(tmp_path):
    s = Store(tmp_path / "d.json")
    r = s.add_recurring("Пить воду", 120, NOW + timedelta(hours=2))
    assert Store(tmp_path / "d.json").recurring()[0]["title"] == "Пить воду"
    assert s.recurring_due(NOW) == []
    assert [x["title"] for x in s.recurring_due(NOW + timedelta(hours=5))] == ["Пить воду"]
    assert s.recurring()[0]["next"] == (NOW + timedelta(hours=7)).strftime("%Y-%m-%d %H:%M")
    assert s.postpone_recurring(r["id"], NOW) and s.delete_recurring(r["id"]) and s.recurring() == []


# ================= cli: «не беспокоить», будильник, каналы =================
class FakeBot:
    instances = []

    def __init__(self, cfg, store, assistant):
        self.sent = []
        FakeBot.instances.append(self)

    start = stop = lambda self: None

    def send(self, text, chat_id=None):
        self.sent.append(text)


class RecScheduler:
    last = None

    def __init__(self, store, notify, **kw):
        self.notify, self.kw = notify, kw
        RecScheduler.last = self

    start = stop = lambda self: None


@pytest.fixture
def wired(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_HOME", str(tmp_path))
    monkeypatch.setenv("JARVIS_TG_TOKEN", "t")
    FakeBot.instances.clear()
    monkeypatch.setattr(cli, "TelegramBot", FakeBot)
    monkeypatch.setattr(cli, "Scheduler", RecScheduler)
    lines = iter(["не беспокоить", "выход"])
    monkeypatch.setattr(builtins, "input", lambda *_: next(lines))
    return monkeypatch


def boot(args=("--telegram",)):
    cli.main(list(args))
    return RecScheduler.last, FakeBot.instances[0]


def test_cli_wires_hooks_alert_handler_and_dnd_check(wired):
    sch, _ = boot()
    assert sch.kw["on_alert"] and len(sch.kw["hooks"]) == 1 and sch.kw["is_dnd"]() is True   # после «не беспокоить»


def test_cli_dnd_silences_voice_sends_to_telegram_at_once_and_collects(wired, capsys):
    sch, bot = boot()                                    # консоль ввела «не беспокоить»
    sch.notify("Напоминаю: Позвонить врачу.")
    assert bot.sent == ["Напоминаю: Позвонить врачу."]
    assert "🔕 Напоминаю: Позвонить врачу." in capsys.readouterr().out


def test_cli_alarm_and_timer_ignore_dnd(wired, capsys):
    sch, bot = boot()
    sch.notify(Urgent("Будильник. Пора вставать."))
    out = capsys.readouterr().out
    assert "🔔 Будильник. Пора вставать." in out and "🔕" not in out
    assert bot.sent == []                                # на ПК слышно, в Telegram только как обычно (дубль)
