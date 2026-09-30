"""Safe evaluation of the arithmetic formulas the model proposes.

A formula may only reference quantity ids from the annotator (q1, q2, ...), the named
conversion constants below, and numeric literals, combined with + - * / and parentheses.
"""

from __future__ import annotations

import ast
import re

from app.models.internal import Quantity

CONSTANTS: dict[str, float] = {
    "SECONDS_PER_MINUTE": 60,
    "SECONDS_PER_HOUR": 3600,
    "SECONDS_PER_DAY": 86400,
    "MINUTES_PER_HOUR": 60,
    "HOURS_PER_DAY": 24,
    "HOURS_PER_WEEK": 168,
    "HOURS_PER_MONTH": 730,
    "HOURS_PER_YEAR": 8760,
    "DAYS_PER_YEAR": 365,
    "MONTHS_PER_YEAR": 12,
    "THOUSAND": 1_000,
    "MILLION": 1_000_000,
    "BILLION": 1_000_000_000,
    "MB_PER_GB": 1000,
    "GB_PER_TB": 1000,
    "MIB_PER_GIB": 1024,
    "GIB_PER_TIB": 1024,
    "PERCENT": 0.01,
}

_QID = re.compile(r"^q\d+$")


class FormulaError(ValueError):
    pass


def referenced_ids(formula: str) -> list[str]:
    return sorted(set(re.findall(r"\bq\d+\b", formula)), key=lambda s: int(s[1:]))


def evaluate(formula: str, quantities: dict[str, Quantity]) -> float:
    try:
        tree = ast.parse(formula.strip(), mode="eval")
    except SyntaxError as exc:
        raise FormulaError(f"formula {formula!r} is not valid arithmetic") from exc
    return _eval(tree.body, quantities, formula)


def _eval(node: ast.AST, quantities: dict[str, Quantity], formula: str) -> float:
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div)):
        left = _eval(node.left, quantities, formula)
        right = _eval(node.right, quantities, formula)
        if isinstance(node.op, ast.Add):
            return left + right
        if isinstance(node.op, ast.Sub):
            return left - right
        if isinstance(node.op, ast.Mult):
            return left * right
        if right == 0:
            raise FormulaError(f"formula {formula!r} divides by zero")
        return left / right
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        value = _eval(node.operand, quantities, formula)
        return -value if isinstance(node.op, ast.USub) else value
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
        return float(node.value)
    if isinstance(node, ast.Name):
        if node.id in CONSTANTS:
            return float(CONSTANTS[node.id])
        if _QID.match(node.id):
            quantity = quantities.get(node.id)
            if quantity is None:
                raise FormulaError(f"formula {formula!r} references unknown quantity {node.id}")
            if quantity.value is None:
                raise FormulaError(f"formula {formula!r} uses {node.id}, which is a null value in the source")
            return float(quantity.value)
        raise FormulaError(f"formula {formula!r} uses unknown name {node.id!r}")
    raise FormulaError(f"formula {formula!r} contains an unsupported expression")
