"""Ответ, который нужно озвучить на нескольких языках (новости на языке источника, перевод)."""


class Spoken(str):
    """Строка-ответ с разбивкой по языкам: parts = [(язык, текст), ...]. Для консоли — обычный текст."""

    def __new__(cls, parts):
        parts = [(lang, text) for lang, text in parts if text]
        obj = super().__new__(cls, " ".join(text for _, text in parts))
        obj.parts = parts
        return obj


class Urgent(str):
    """Оповещение, которое «не беспокоить» не глушит (будильник, таймер)."""
