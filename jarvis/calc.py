"""Калькулятор по-русски без интернета: «сколько будет 15 процентов от 2300», «два плюс два»."""
import ast
import operator
import re

from .ruparse import NUM, to_int

OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv,
       ast.USub: operator.neg, ast.UAdd: operator.pos}
WORD_OPS = [(r"умножить\s+на|помножить\s+на|умноженное\s+на", "*"), (r"разделить\s+на|поделить\s+на", "/"),
            (r"плюс", "+"), (r"минус", "-"), (r"\bна\b", " ")]
NUMBER = r"\d+(?:[.,]\d+)?"


def _safe_eval(node):
    if isinstance(node, ast.Expression):
        return _safe_eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_safe_eval(node.left), _safe_eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in OPS:
        return OPS[type(node.op)](_safe_eval(node.operand))
    raise ValueError("недопустимое выражение")


def _fmt(x: float) -> str:
    x = round(x, 6)
    if x == int(x):
        return str(int(x))
    return f"{x:.6f}".rstrip("0").rstrip(".").replace(".", ",")


def _digits(text: str) -> str:
    """Числа словами → цифры, запятая → точка."""
    text = re.sub(rf"\b{NUM}", lambda m: str(to_int(m.group(0))), text)
    return re.sub(r"(\d),(\d)", r"\1.\2", text)


def evaluate(text: str) -> str | None:
    """Результат вычисления строкой или None, если это не арифметика."""
    low = text.lower().replace("ё", "е")
    low = re.sub(r"^(?:сколько\s+будет|сколько|посчитай|вычисли|реши|чему\s+равно)\s*", "", low).strip(" ?!.")
    low = _digits(low)
    pct = re.fullmatch(rf"({NUMBER})\s+процент\w*\s+от\s+({NUMBER})", low)
    if pct:
        return _fmt(float(pct.group(1)) / 100 * float(pct.group(2)))
    for pat, sym in WORD_OPS:
        low = re.sub(pat, sym, low)
    low = low.replace("×", "*").replace("х", "*").replace("÷", "/").replace(":", "/")
    low = re.sub(r"\s+", "", low)
    if not low or not re.fullmatch(r"[\d+\-*/().]+", low) or not re.search(r"\d", low) \
            or not re.search(r"[+\-*/]", low.lstrip("-+")):
        return None
    try:
        return _fmt(_safe_eval(ast.parse(low, mode="eval")))
    except (ValueError, SyntaxError, ZeroDivisionError):
        return None
