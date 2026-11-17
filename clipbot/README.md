# clipbot

Автонарезка клипов из стрима Twitch (идея из видео про GTA 6):

1. **Streamlink** пишет эфир в `.ts`.
2. **Чат Twitch** (анонимный IRC) считается окнами по 10 с; всплеск = среднее + 3σ.
3. **ffmpeg** вырезает 20 с до и 10 с после пика, делает 9:16 с размытым фоном.
4. **Whisper** (faster-whisper) делает субтитры и вшивает их.

Ограничение: работает только в прямом эфире, прошлые стримы не обработает.

```
pip install -r clipbot/requirements.txt   # + нужен ffmpeg в PATH
python -m clipbot.main --channel <имя>    # --no-subs, --landscape, --out DIR
python -m pytest clipbot
```

Пороги и длины клипов: `clipbot/config.py`. Если клипы съезжают по времени, подберите `stream_delay_sec`.
