"""Мозг Джарвиса: диалог с Claude и цикл вызова инструментов."""
from datetime import datetime
from typing import Callable

MAX_STEPS = 8
MAX_HISTORY = 40

SYSTEM = """Ты — Джарвис, личный голосовой ассистент{user}. Отвечай по-русски, кратко и по делу: \
твои ответы часто озвучиваются, поэтому без markdown, списков с символами и длинных вступлений.
Сейчас {now}. Город пользователя: {city}.
Используй инструменты, когда нужны данные или действия (погода, новости, поиск, почта, календарь, \
заметки, управление компьютером). Относительное время («через час», «завтра в 9») переводи в точную \
дату сам. Не выдумывай результаты: если инструмент вернул ошибку — скажи об этом честно. \
Перед необратимыми действиями (отправка писем, команды оболочки) действуй только если пользователь \
действительно этого просил."""


class Brain:
    def __init__(self, cfg, registry, client=None, confirm: Callable[[str, dict], bool] | None = None):
        self.cfg = cfg
        self.registry = registry
        self.confirm = confirm or (lambda name, args: False)
        if client is None:
            import anthropic
            client = anthropic.Anthropic(api_key=cfg.api_key)
        self.client = client
        self.history: list = []

    def reset(self):
        self.history.clear()

    def _system(self) -> str:
        return SYSTEM.format(user=f" {self.cfg.user_name}" if self.cfg.user_name else "",
                             now=datetime.now().strftime("%Y-%m-%d %H:%M, %A"), city=self.cfg.city)

    def _run_tool(self, block) -> dict:
        tool = self.registry.get(block.name)
        if tool is None:
            result, err = f"Неизвестный инструмент {block.name}", True
        elif tool.confirm and not self.confirm(block.name, block.input):
            result, err = "Пользователь отклонил действие.", True
        else:
            try:
                result, err = str(tool.func(**block.input)), False
            except Exception as e:
                result, err = f"Ошибка: {type(e).__name__}: {e}", True
        return {"type": "tool_result", "tool_use_id": block.id, "content": result, "is_error": err}

    def ask(self, text: str) -> str:
        self.history.append({"role": "user", "content": text})
        # Обрезаем историю, но так, чтобы она начиналась с обычного сообщения пользователя
        if len(self.history) > MAX_HISTORY:
            self.history = self.history[-MAX_HISTORY:]
            while self.history and not (self.history[0]["role"] == "user"
                                        and isinstance(self.history[0]["content"], str)):
                self.history.pop(0)
        for _ in range(MAX_STEPS):
            resp = self.client.messages.create(
                model=self.cfg.model, max_tokens=1024, system=self._system(),
                tools=self.registry.schemas(), messages=self.history)
            self.history.append({"role": "assistant", "content": resp.content})
            calls = [b for b in resp.content if b.type == "tool_use"]
            if not calls:
                return "".join(b.text for b in resp.content if b.type == "text").strip()
            self.history.append({"role": "user", "content": [self._run_tool(b) for b in calls]})
        return "Не удалось завершить задачу за разумное число шагов."
