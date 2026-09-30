import pytest

from app.models.internal import Quantity
from app.services.expressions import FormulaError, evaluate, referenced_ids

Q = {
    "q1": Quantity(id="q1", raw="$24.80/hr", value=24.8),
    "q2": Quantity(id="q2", raw="8x", value=8),
    "q3": Quantity(id="q3", raw="0.00082", value=0.00082),
    "q4": Quantity(id="q4", raw="N/A", value=None, kind="null"),
}


def test_whole_machine_price_split():
    assert evaluate("q1 / q2", Q) == pytest.approx(3.1)


def test_per_second_to_per_hour_with_named_constant():
    assert evaluate("q3 * SECONDS_PER_HOUR", Q) == pytest.approx(2.952)


def test_literals_and_parentheses():
    assert evaluate("(q1 + 0.2) / q2", Q) == pytest.approx(3.125)


def test_single_id_copies_value():
    assert evaluate("q2", Q) == 8


@pytest.mark.parametrize(
    "formula, message",
    [
        ("q9 / 2", "unknown quantity"),
        ("q4 * 2", "null value"),
        ("q1 / 0", "divides by zero"),
        ("__import__('os')", "unsupported"),
        ("q1 ** 2", "unsupported"),
        ("foo + 1", "unknown name"),
        ("q1 /", "not valid"),
    ],
)
def test_rejects_unsafe_or_broken_formulas(formula, message):
    with pytest.raises(FormulaError, match=message):
        evaluate(formula, Q)


def test_referenced_ids():
    assert referenced_ids("q10 / q2 + q2") == ["q2", "q10"]
