"""Запуск Джарвиса: консоль, голос (слово «Джарвис»), Telegram-бот."""
import argparse
import sys
import threading
import time

from .assistant import Assistant
from .config import Config
from .scheduler import Scheduler
from .store import Store
from .telegram_bot import TelegramBot
from .voice import Voice, strip_wake_word

print_lock = threading.Lock()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jarvis", description="Джарвис — личный помощник без облачного ИИ")
    ap.add_argument("--voice", action="store_true", help="слушать микрофон; команды после слова «Джарвис»")
    ap.add_argument("--telegram", action="store_true", help="включить Telegram-бота (нужен JARVIS_TG_TOKEN)")
    ap.add_argument("--headless", action="store_true", help="без консоли/микрофона: только планировщик и бот")
    args = ap.parse_args(argv)

    cfg = Config()
    store = Store(cfg.home / "data.json")
    assistant = Assistant(cfg, store)

    voice = None
    if args.voice:
        try:
            voice = Voice(cfg)
        except RuntimeError as e:
            sys.exit(str(e))

    bot = None
    if args.telegram:
        if not cfg.tg_token:
            sys.exit("Задайте JARVIS_TG_TOKEN (токен от @BotFather).")
        bot = TelegramBot(cfg, store, assistant)

    def say(text: str, prefix: str = "Джарвис: "):
        with print_lock:
            print(f"\n{prefix}{text}", flush=True)
        if voice:
            voice.say(text)

    def notify(text: str):
        """Оповещение на ПК: консоль и голос. В Telegram оно уходит только как дубль, если на ПК
        не ответили за tg_dup_minutes. Без ПК (--headless) слушать некому — шлём в Telegram сразу."""
        say(text, "🔔 ")
        if bot and args.headless:
            bot.send(text)

    sched = Scheduler(store, notify, review=assistant.daily_review,
                      notify_tg=bot.send if bot else None,
                      tg_dup_minutes=None if args.headless else cfg.tg_dup_minutes)
    sched.start()
    if bot:
        bot.start()

    try:
        if voice:
            names = cfg.wake_words[0]
            say(f"Слушаю. Скажите «{names}» и команду." + (" Режим офлайн." if voice.offline else ""))
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
                    cmd = voice.listen(timeout=7)
                    if not cmd:
                        continue
                if cmd.lower().strip(" .!") in ("стоп", "выход", "пока", "до свидания", "выключись"):
                    say("До связи.")
                    break
                say(assistant.handle(cmd))
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
