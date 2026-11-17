"""Субтитры через Whisper (faster-whisper) -> .srt."""


def _ts(t):
    h, rem = divmod(int(t * 1000), 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def to_srt(segments):
    out = []
    for i, (start, end, text) in enumerate(segments, 1):
        out.append(f"{i}\n{_ts(start)} --> {_ts(end)}\n{text.strip()}\n")
    return "\n".join(out)


class Transcriber:
    def __init__(self, model="small", language="ru"):
        from faster_whisper import WhisperModel  # тяжёлый импорт — лениво
        self.model = WhisperModel(model, compute_type="int8")
        self.language = language

    def srt_for(self, media_path, srt_path):
        segs, _ = self.model.transcribe(media_path, language=self.language)
        text = to_srt([(s.start, s.end, s.text) for s in segs])
        with open(srt_path, "w", encoding="utf-8") as f:
            f.write(text)
        return srt_path if text.strip() else None
