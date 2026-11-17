# Джарвис

Консольный ИИ-ассистент на Python. «Мозг» — Claude с вызовом инструментов, каждая функция — отдельный инструмент.

## Запуск
```bash
pip install -r requirements-jarvis.txt
export ANTHROPIC_API_KEY=sk-ant-...
python -m jarvis              # текстовый режим
python -m jarvis --briefing   # + утренняя сводка
python -m jarvis --voice      # голос: скажите «Джарвис, ...»
```
Голосовой режим требует `pip install SpeechRecognition pyaudio pyttsx3` (распознавание через Google Web Speech, нужен интернет и микрофон).

## Возможности
| Функция | Инструменты |
|---|---|
| Чат с ИИ, память диалога | `/reset` сбрасывает |
| Голос | wake-word «Джарвис», озвучка ответов (pyttsx3) |
| Компьютер | `open_app`, `open_url`, `set_volume`, `find_files`, `read_file`, `system_info`, `run_command` (с подтверждением) |
| Почта | `list_unread_mail`, `read_mail`, `send_mail` (с подтверждением), IMAP/SMTP |
| Календарь, заметки | `add_event`, `list_agenda`, `add_note`, `list_notes`… (локально, `~/.jarvis/data.json`) |
| Погода, новости, поиск | Open-Meteo, RSS, DuckDuckGo (`ddgs`) |
| Проактивность | фоновый планировщик сам сообщает о напоминаниях и событиях |

## Настройка (переменные окружения)
`JARVIS_CITY`, `JARVIS_USER`, `JARVIS_MODEL`, `JARVIS_WAKE_WORD`, `JARVIS_NEWS_FEEDS`,
`JARVIS_MAIL_USER` / `JARVIS_MAIL_PASSWORD` (для Gmail — пароль приложения), `JARVIS_HOME`.

## Добавить свой инструмент
В `jarvis/tools/*.py` внутри `register(reg, cfg, store)`:
```python
@reg.add("my_tool", "Что делает", {"arg": S("описание")}, ["arg"], confirm=False)
def my_tool(arg): return "результат"
```

## Тесты
`python -m pytest tests`
