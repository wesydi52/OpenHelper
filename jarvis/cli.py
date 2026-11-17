"""Консольный интерфейс Джарвиса."""
import argparse
import sys
import threading

from .brain import Brain
from .config import Config
from .scheduler import Scheduler
from .store import Store
from .tools import build_registry
from .voice import Voice, strip_wake_word

print_lock = threading.Lock()


def out(text: str, voice=None, prefix="Джарвис: "):
    with print_lock:
        print(f"\n{prefix}{text}")
    if voice:
        voice.say(text)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="jarvis", description="Джарвис — личный ИИ-ассистент")
    ap.add_argument("--voice", action="store_true", help="голосовой режим (wake-word «Джарвис»)")
    ap.add_argument("--briefing", action="store_true", help="сразу выдать утреннюю сводку")
    args = ap.parse_args(argv)

    cfg = Config()
    if not cfg.api_key:
        sys.exit("Задайте ANTHROPIC_API_KEY в переменных окружения.")

    voice = None
    if args.voice:
        try:
            voice = Voice(cfg)
        except RuntimeError as e:
            sys.exit(str(e))

    store = Store(cfg.home / "data.json")

    def confirm(name, params):
        with print_lock:
            print(f"\n[!] Джарвис хочет выполнить {name}: {params}")
        if voice:
            voice.say("Подтвердите действие в консоли.")
        return input("Разрешить? [y/N] ").strip().lower() in ("y", "yes", "д", "да")

    brain = Brain(cfg, build_registry(cfg, store), confirm=confirm)
    sched = Scheduler(store, lambda t: out(t, voice, "🔔 "))
    sched.start()

    def handle(text):
        try:
            out(brain.ask(text), voice)
        except Exception as e:
            out(f"Произошла ошибка: {e}", voice)

    if args.briefing:
        handle("Сделай утреннюю сводку: погода, мои дела на сегодня, главные новости и непрочитанная почта.")

    if voice:
        out(f"Слушаю. Скажите «{cfg.wake_word}».", voice)
        while True:
            heard = voice.listen(timeout=None)
            if not heard:
                continue
            print(f"\nВы (услышано): {heard}")
            cmd = strip_wake_word(heard, cfg.wake_word)
            if cmd is None:
                continue
            if cmd == "":
                out("Да?", voice)
                cmd = voice.listen(timeout=6)
                if not cmd:
                    continue
            if cmd.lower() in ("стоп", "выход", "до свидания"):
                out("До связи.", voice)
                break
            handle(cmd)
    else:
        print("Джарвис на связи. Команды: /reset — забыть диалог, /exit — выход.")
        while True:
            try:
                text = input("\nВы: ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text in ("/exit", "/quit"):
                break
            if text == "/reset":
                brain.reset()
                print("Диалог сброшен.")
                continue
            handle(text)
    sched.stop()
