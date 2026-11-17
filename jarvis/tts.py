"""Озвучка: системные голоса (pyttsx3) или нейросетевые офлайн-голоса Piper — по языкам ru/pl/uk/en.

**Вживую не проверено** (нет звука и Windows). Логика выбора голоса и запуска Piper проверена тестами с подменой.
"""
import os
import subprocess
import tempfile

# Подсказки в идентификаторе/имени голоса. Windows SAPI: ...\Tokens\MSTTS_V110_ruRU_IrinaM
LANG_HINTS = {
    "ru": ("ru-ru", "ru_ru", "ruru", "russian", "irina", "pavel"),
    "pl": ("pl-pl", "pl_pl", "plpl", "polish", "paulina"),
    "uk": ("uk-ua", "uk_ua", "ukua", "ukrain", "polina", "ostap"),
    "en": ("en-us", "en_us", "enus", "en-gb", "english", "zira", "david"),
}


class Pyttsx3Engine:
    def __init__(self, engine, rate: int = 175):
        self.engine = engine
        self.voices = list(engine.getProperty("voices"))
        engine.setProperty("rate", rate)

    def voice_for(self, lang: str):
        for v in self.voices:
            blob = f"{getattr(v, 'id', '')} {getattr(v, 'name', '')} {getattr(v, 'languages', '')}".lower()
            if any(h in blob for h in LANG_HINTS.get(lang, ())):
                return v.id
        return None

    def languages(self) -> set:
        return {lang for lang in LANG_HINTS if self.voice_for(lang)}

    def say(self, text: str, lang: str = "ru"):
        vid = self.voice_for(lang) or self.voice_for("ru")
        if vid:
            self.engine.setProperty("voice", vid)
        self.engine.say(text)
        self.engine.runAndWait()


class PiperEngine:
    """Piper (pip install piper-tts + файлы .onnx голосов). JARVIS_PIPER_MODELS='ru=...;pl=...;uk=...'."""

    def __init__(self, models: dict, exe: str = "piper", runner=None, player=None):
        self.models, self.exe = models, exe
        self._run = runner or self._default_run
        self._play = player or self._default_play

    @staticmethod
    def _default_run(cmd, text):
        return subprocess.run(cmd, input=text, text=True, encoding="utf-8", capture_output=True, timeout=60).returncode

    @staticmethod
    def _default_play(path):
        if os.name == "nt":
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
        else:
            subprocess.run(["aplay", "-q", path], timeout=120)

    def languages(self) -> set:
        return {lang for lang, path in self.models.items() if path}

    def say(self, text: str, lang: str = "ru"):
        model = self.models.get(lang) or self.models.get("ru")
        if not model:
            raise RuntimeError(f"Для Piper не задана модель для языка {lang}: JARVIS_PIPER_MODELS.")
        fd, wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            if self._run([self.exe, "--model", model, "--output_file", wav], text) == 0:
                self._play(wav)
        finally:
            try:
                os.remove(wav)
            except OSError:
                pass


def make_engine(cfg, pyttsx3_module=None):
    if cfg.tts_engine == "piper":
        return PiperEngine(cfg.piper_models)
    if pyttsx3_module is None:
        import pyttsx3 as pyttsx3_module
    return Pyttsx3Engine(pyttsx3_module.init())
