"""Запуск Джарвиса: консоль, голос (слово «Джарвис»), Telegram-бот, автозапуск."""
import argparse
import sys
import threading
import time

from . import autostart
from .assistant import Assistant
from .config import Config
from .scheduler import Scheduler
from .spoken import Urgent
from .store import Store
from .telegram_bot import TelegramBot
from .voice import Voice, strip_wake_word

print_lock = threading.Lock()
STOP_WORDS = ("стоп", "выход", "пока", "до свидания", "выключись")
COMMAND_WAIT = 7   # секунд ждать команду, если сказано только «Джарвис»


def speak(voice, reply):
    """Озвучить ответ; новости и перевод — по частям, каждая своим голосом."""
    if not voice:
        return
    for lang, text in getattr(reply, "parts", None) or [("ru", str(reply))]:
        voice.say(text, lang)


def run_voice_loop(voice, assistant, cfg, say, dialog_seconds: int = 10):
    """Слушаем «Джарвис», выполняем команду и ещё dialog_seconds секунд принимаем уточнения без повтора имени."""
    while True:
        heard = voice.listen(timeout=None)
        if not heard:
            continue
        print(f"\n[услышал] {heard}", flush=True)
        cmd = strip_wake_word(heard, cfg.wake_words)
        if cmd is None:
            continue
        if cmd == "":
            say("Да?")
            cmd = voice.listen(timeout=COMMAND_WAIT)
        while cmd:
            if cmd.lower().strip(" .!") in STOP_WORDS:
                say("До связи.")
                return
            say(assistant.handle(cmd))
            cmd = voice.listen(timeout=dialog_seconds)          # окно диалога
            if cmd:
                bare = strip_wake_word(cmd, cfg.wake_words)
                cmd = cmd if bare is None else bare


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jarvis", description="Джарвис — личный помощник без облачного ИИ")
    ap.add_argument("--voice", action="store_true", help="слушать микрофон; команды после слова «Джарвис»")
    ap.add_argument("--telegram", action="store_true", help="включить Telegram-бота (нужен JARVIS_TG_TOKEN)")
    ap.add_argument("--headless", action="store_true", help="без консоли/микрофона: только планировщик и бот")
    ap.add_argument("--install-autostart", action="store_true", help="запускать Джарвиса при входе в Windows")
    ap.add_argument("--uninstall-autostart", action="store_true", help="убрать автозапуск")
    args = ap.parse_args(argv)

    if args.install_autostart:
        flags = " ".join(f for f, on in (("--voice", args.voice), ("--telegram", args.telegram),
                                         ("--headless", args.headless)) if on) or "--voice --telegram"
        print(autostart.install(flags))
        return
    if args.uninstall_autostart:
        print(autostart.uninstall())
        return

    cfg = Config()
    store = Store(cfg.home / "data.json")
    assistant = Assistant(cfg, store)

    voice = None
    if args.voice:
        try:
            voice = Voice(cfg)
        except RuntimeError as e:
            sys.exit(str(e))
        assistant.voice_mode = True
        missing = voice.missing_languages()
        if missing:
            names = {"ru": "русский", "pl": "польский", "uk": "украинский"}
            print("Нет голосов для: " + ", ".join(names[m] for m in missing) +
                  ". Новости на этих языках будут звучать чужим голосом — доустановите голоса Windows или Piper.")

    bot = None
    if args.telegram:
        if not cfg.tg_token:
            sys.exit("Задайте JARVIS_TG_TOKEN (токен от @BotFather).")
        bot = TelegramBot(cfg, store, assistant)

    def say(reply, prefix: str = "Джарвис: "):
        with print_lock:
            print(f"\n{prefix}{reply}", flush=True)
        speak(voice, reply)

    def notify(text: str):
        """Оповещение на ПК: консоль и голос. В Telegram оно уходит только как дубль, если на ПК не ответили за
        tg_dup_minutes. Без ПК (--headless) слушать некому — шлём в Telegram сразу.
        «Не беспокоить»: голос молчит, напоминание уходит в Telegram сразу и копится для сводки; будильник и таймер
        режим не глушит."""
        if assistant.dnd and not isinstance(text, Urgent):
            assistant.note_missed(str(text))
            with print_lock:
                print(f"\n🔕 {text}", flush=True)
            if bot:
                bot.send(str(text))
            return
        say(text, "🔔 ")
        if bot and args.headless:
            bot.send(str(text))

    sched = Scheduler(store, notify, review=assistant.daily_review,
                      notify_tg=bot.send if bot else None,
                      tg_dup_minutes=None if args.headless else cfg.tg_dup_minutes,
                      on_alert=assistant.on_alert, hooks=[assistant.tick], is_dnd=lambda: assistant.dnd)
    sched.start()
    if bot:
        bot.start()

    try:
        if voice:
            say(f"Слушаю. Скажите «{cfg.wake_words[0]}» и команду." + (" Режим офлайн." if voice.offline else ""))
            run_voice_loop(voice, assistant, cfg, say, dialog_seconds=cfg.dialog_seconds)
        elif args.headless:
            print("Джарвис работает в фоне. Ctrl+C — выход.", flush=True)
            while True:
                time.sleep(3600)
        else:
            print("Джарвис на связи. Пишите команды; «выход» — завершить.")
            while True:
                try:
                    text = input("\nВы: ").strip()
                except EOFError:
                    break
                if text.lower() in ("выход", "/exit", "/quit"):
                    break
                if text:
                    say(assistant.handle(text))
    except KeyboardInterrupt:
        pass
    finally:
        sched.stop()
        if bot:
            bot.stop()
