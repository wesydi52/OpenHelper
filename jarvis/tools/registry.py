"""Реестр инструментов, которые Claude может вызывать."""
from dataclasses import dataclass
from typing import Callable


@dataclass
class Tool:
    name: str
    description: str
    properties: dict
    required: list
    func: Callable
    confirm: bool = False  # требовать подтверждения пользователя

    def schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {"type": "object", "properties": self.properties,
                             "required": self.required},
        }


class Registry:
    def __init__(self):
        self.tools: dict[str, Tool] = {}

    def add(self, name, description, properties=None, required=None, confirm=False):
        def deco(func):
            self.tools[name] = Tool(name, description, properties or {}, required or [],
                                    func, confirm)
            return func
        return deco

    def schemas(self) -> list:
        return [t.schema() for t in self.tools.values()]

    def get(self, name: str) -> Tool | None:
        return self.tools.get(name)


def S(description: str, type_: str = "string", **extra) -> dict:
    """Короткая запись для описания параметра."""
    return {"type": type_, "description": description, **extra}
