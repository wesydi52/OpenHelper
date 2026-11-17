"""Голос: распознавание речи (SpeechRecognition) и озвучка (pyttsx3). Зависимости необязательны."""
import re
import threading


class Voice:
    def __init__(self, cfg):
        try:
            import speech_recognition as sr
            import pyttsx3
        except ImportError as e:
            raise RuntimeError("Для голоса: pip install SpeechRecognition pyaudio pyttsx3") from e
        self.cfg, self.sr = cfg, sr
        self.rec = sr.Recognizer()
        self.mic = sr.Microphone()
        self._lock = threading.Lock()
        self.tts = pyttsx3.init()
        for v in self.tts.getProperty("voices"):  # пробуем найти русский голос
            if "ru" in (v.id + v.name).lower() or "russian" in v.name.lower():
                self.tts.setProperty("voice", v.id)
                break
        with self.mic as src:
            self.rec.adjust_for_ambient_noise(src, duration=1)

    def say(self, text: str):
        with self._lock:
            self.tts.say(text)
            self.tts.runAndWait()

    def listen(self, timeout: float = 5, phrase_limit: float = 15) -> str | None:
        with self.mic as src:
            try:
                audio = self.rec.listen(src, timeout=timeout, phrase_time_limit=phrase_limit)
            except self.sr.WaitTimeoutError:
                return None
        try:
            return self.rec.recognize_google(audio, language=self.cfg.language)
        except (self.sr.UnknownValueError, self.sr.RequestError):
            return None


def strip_wake_word(text: str, wake: str) -> str | None:
    """Вернуть команду без wake-word, '' если сказано только «Джарвис», None если слова нет."""
    m = re.search(re.escape(wake), text, re.IGNORECASE)
    if not m:
        return None
    return (text[:m.start()] + " " + text[m.end():]).strip(" ,.!?")
