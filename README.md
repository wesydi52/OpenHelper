# OpenHelper

## clipbot — автонарезка клипов из стрима Twitch

Бот пишет прямой эфир, следит за всплесками в чате и сам режет клипы 9:16 (по желанию с субтитрами).

### Быстрый старт (Windows / Mac / Linux)

1. Установите [Python 3.10+](https://www.python.org/downloads/) (на Windows отметьте «Add Python to PATH») и ffmpeg:
   - Windows: `winget install ffmpeg`
   - Mac: `brew install ffmpeg`
   - Linux: `sudo apt install ffmpeg`
2. В терминале:
   ```
   git clone https://github.com/wesydi52/OpenHelper.git
   cd OpenHelper
   git checkout claude/magical-fermi-4jcfqc
   pip install -r clipbot/requirements.txt
   python -m clipbot
   ```
3. Откроется меню в браузере (http://127.0.0.1:8765): вставьте ссылку на канал, который сейчас в эфире, и нажмите «Включить».
   Для проверки отметьте «Пробный клип через минуту».

Подробности и настройки: [clipbot/README.md](clipbot/README.md).
