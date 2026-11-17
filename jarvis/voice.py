"""Голос: распознавание (Vosk офлайн или Google Web Speech) и озвучка (pyttsx3, офлайн)."""
import json
import re
import threading

from .tts import make_engine


class Voice:
    def __init__(self, cfg, engine=None):
        try:
            import speech_recognition as sr
        except ImportError as e:
            raise RuntimeError("Для голоса: pip install SpeechRecognition pyaudio pyttsx3") from e
        self.cfg, self.sr = cfg, sr
        self.rec = sr.Recognizer()
        self.mic = sr.Microphone()
        self.vosk = None
        if cfg.vosk_model:
            try:
                from vosk import Model, SetLogLevel
            except ImportError as e:
                raise RuntimeError("JARVIS_VOSK_MODEL задан, но vosk не установлен: pip install vosk") from e
            SetLogLevel(-1)
            self.vosk = Model(cfg.vosk_model)
        self.offline = self.vosk is not None
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        try:
            self.engine = engine or make_engine(cfg)
        except ImportError as e:
            raise RuntimeError("Для голоса: pip install pyttsx3 (или piper-tts для нейросетевого голоса)") from e
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)

    def missing_languages(self, needed=("ru", "pl", "uk")) -> list:
        """Языки новостей, для которых нет голоса, — чтобы подсказать, что доустановить."""
        have = self.engine.languages()
        return [lang for lang in needed if lang not in have]

    def say(self, text: str, lang: str = "ru"):
        with self._lock:
            self._speaking.set()
            try:
                self.engine.say(text, lang)
            finally:
                self._speaking.clear()

    def _recognize(self, audio) -> str:
        if self.vosk:
            from vosk import KaldiRecognizer
            r = KaldiRecognizer(self.vosk, 16000)
            r.AcceptWaveform(audio.get_raw_data(convert_rate=16000, convert_width=2))
            return json.loads(r.FinalResult()).get("text", "")
        return self.rec.recognize_google(audio, language=self.cfg.language)

    def listen(self, timeout: float | None = 5, phrase_limit: float = 20) -> str | None:
        """Одна фраза или None (тишина / не распознано / в это время говорил сам Джарвис)."""
        if self._speaking.is_set():
            return None
        with self.mic as src:
            try:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
            except self.sr.WaitTimeoutError:
                return None
        if self._speaking.is_set():  # не принимаем собственный голос
            return None
        try:
            return self._recognize(audio).strip() or None
        except (self.sr.UnknownValueError, self.sr.RequestError):
            return None


def strip_wake_word(text: str, wake_words) -> str | None:
    """Команда без слова активации; '' если сказано только «Джарвис»; None если слова нет."""
    if isinstance(wake_words, str):
        wake_words = [wake_words]
    pat = "|".join(re.escape(w) for w in wake_words)
    m = re.search(rf"\b(?:{pat})\b", text, re.IGNORECASE)
    if not m:
        return None
    return (text[:m.start()] + " " + text[m.end():]).strip(" ,.!?")
