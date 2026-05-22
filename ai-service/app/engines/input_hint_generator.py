"""Simple input hint generation for Java boolean conditions."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple


def generate_input_hints(condition: str, expected_value: Any) -> Tuple[Dict[str, Any], bool]:
    """Return best-effort input hints and whether human review is needed."""
    text = _strip_outer_parentheses(str(condition or "").strip())
    if not text:
        return {}, True

    expected = _as_bool(expected_value)
    hints, handled = _solve_condition(text, expected)
    return hints, not handled


def _solve_condition(condition: str, expected: bool) -> Tuple[Dict[str, Any], bool]:
    condition = _strip_outer_parentheses(condition)

    parts = _split_top_level(condition, "&&")
    if len(parts) > 1:
        if expected:
            merged: Dict[str, Any] = {}
            handled_any = False
            for part in parts:
                hints, handled = _solve_condition(part, True)
                merged.update(hints)
                handled_any = handled_any or handled
            return merged, handled_any
        hints, handled = _solve_condition(parts[-1], False)
        return hints, handled

    parts = _split_top_level(condition, "||")
    if len(parts) > 1:
        if expected:
            hints, handled = _solve_condition(parts[0], True)
            return hints, handled
        merged = {}
        handled_any = False
        for part in parts:
            hints, handled = _solve_condition(part, False)
            merged.update(hints)
            handled_any = handled_any or handled
        return merged, handled_any

    return _solve_atomic(condition, expected)


def _solve_atomic(condition: str, expected: bool) -> Tuple[Dict[str, Any], bool]:
    text = _strip_outer_parentheses(condition.strip())
    if text.startswith("!"):
        return _solve_atomic(text[1:].strip(), not expected)

    empty_match = re.fullmatch(r"([A-Za-z_][\w.]*)\.isEmpty\(\)", text)
    if empty_match:
        name = _last_name(empty_match.group(1))
        return {name: [] if expected else ["sample"]}, True

    equals_call = re.fullmatch(r"([A-Za-z_][\w.]*)\.equals\((\"[^\"]*\"|'[^']*'|[A-Za-z_][\w.]*)\)", text)
    if equals_call:
        name = _last_name(equals_call.group(1))
        value = _literal_value(equals_call.group(2))
        return {name: value if expected else _different_value(value)}, True

    literal_equals = re.fullmatch(r"(\"[^\"]*\"|'[^']*')\.equals\(([A-Za-z_][\w.]*)\)", text)
    if literal_equals:
        value = _literal_value(literal_equals.group(1))
        name = _last_name(literal_equals.group(2))
        return {name: value if expected else _different_value(value)}, True

    null_match = re.fullmatch(r"([A-Za-z_][\w.]*)\s*(==|!=)\s*null", text)
    if null_match:
        name = _last_name(null_match.group(1))
        op = null_match.group(2)
        is_null = (op == "==" and expected) or (op == "!=" and not expected)
        return {name: None if is_null else "sample"}, True

    string_match = re.fullmatch(r"([A-Za-z_][\w.]*)\s*(==|!=)\s*(\"[^\"]*\"|'[^']*')", text)
    if string_match:
        name = _last_name(string_match.group(1))
        op = string_match.group(2)
        value = _literal_value(string_match.group(3))
        equals = (op == "==" and expected) or (op == "!=" and not expected)
        return {name: value if equals else _different_value(value)}, True

    number_match = re.fullmatch(r"([A-Za-z_][\w.]*)\s*(>=|>|<=|<|==|!=)\s*(-?\d+(?:\.\d+)?)", text)
    if number_match:
        name = _last_name(number_match.group(1))
        op = number_match.group(2)
        number = _number_value(number_match.group(3))
        return {name: _number_hint(op, number, expected)}, True

    return {}, False


def _split_top_level(condition: str, operator: str) -> List[str]:
    parts: List[str] = []
    depth = 0
    quote = ""
    start = 0
    index = 0
    while index < len(condition):
        char = condition[index]
        if quote:
            if char == quote and condition[index - 1:index] != "\\":
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and condition.startswith(operator, index):
            parts.append(condition[start:index].strip())
            index += len(operator)
            start = index
            continue
        index += 1
    if parts:
        parts.append(condition[start:].strip())
    return [part for part in parts if part]


def _strip_outer_parentheses(text: str) -> str:
    value = text.strip()
    while value.startswith("(") and value.endswith(")") and _balanced(value[1:-1]):
        value = value[1:-1].strip()
    return value


def _balanced(text: str) -> bool:
    depth = 0
    quote = ""
    for index, char in enumerate(text):
        if quote:
            if char == quote and text[index - 1:index] != "\\":
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0 and not quote


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "t", "1", "yes"}


def _literal_value(value: str) -> Any:
    raw = str(value).strip()
    if (raw.startswith('"') and raw.endswith('"')) or (raw.startswith("'") and raw.endswith("'")):
        return raw[1:-1]
    return raw


def _different_value(value: Any) -> Any:
    if isinstance(value, str):
        if value == "admin":
            return "guest"
        if value == "123456":
            return "wrong"
        return f"not_{value}" if value else "sample"
    if isinstance(value, (int, float)):
        return value + 1
    return "sample"


def _number_value(value: str) -> Any:
    return float(value) if "." in value else int(value)


def _number_hint(op: str, number: Any, expected: bool) -> Any:
    if op == ">":
        return number + 1 if expected else number
    if op == ">=":
        return number if expected else number - 1
    if op == "<":
        return number - 1 if expected else number
    if op == "<=":
        return number if expected else number + 1
    if op == "==":
        return number if expected else number + 1
    if op == "!=":
        return number + 1 if expected else number
    return number


def _last_name(name: str) -> str:
    return str(name).split(".")[-1]
