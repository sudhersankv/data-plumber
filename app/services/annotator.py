"""Step 2: find candidate values in the source, in code, before the model sees it.

Every number the model may use is listed here with an id (q1, q2, ...). The model must
cite these ids in formulas, so arithmetic is recomputed from exact parsed values instead
of trusting the model's own math.
"""

from __future__ import annotations

import re
from typing import Any

from app.models.internal import ParsedSource, Quantity

NULL_SENTINELS = {"n/a", "na", "none", "null", "nil", "-", "--", "—", "unknown", "tbd", "?", ""}

_NUM = r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|\.\d+"
_SUFFIX = {"k": 1e3, "thousand": 1e3, "m": 1e6, "mn": 1e6, "million": 1e6, "b": 1e9, "bn": 1e9, "billion": 1e9}
_TIME_UNITS = {
    "second": ("seconds", "second", "secs", "sec", "s"),
    "minute": ("minutes", "minute", "mins", "min"),
    "hour": ("hours", "hour", "hrs", "hr", "h"),
    "day": ("days", "day"),
    "week": ("weeks", "week", "wk"),
    "month": ("months", "month", "mo"),
    "year": ("years", "year", "yr"),
}
_TIME_ALT = "|".join(sorted((a for alts in _TIME_UNITS.values() for a in alts), key=len, reverse=True))
_ITEM_ALT = "gpu|card|unit|instance|node|machine|server|seat|user|device"

_MONEY = re.compile(
    rf"(?P<cur>US\$|\$|USD\s?)\s?(?P<num>{_NUM})\s*(?P<suffix>thousand|million|billion|mn|bn|[kmb](?![a-z]))?",
    re.IGNORECASE,
)
_PER_TAIL = re.compile(
    rf"^\s*(?:/|per\s+|an?\s+|each\s+)(?:(?P<item>{_ITEM_ALT})s?\s*(?:[-/]\s*|\s+|per\s+))?(?P<per>{_TIME_ALT})\b",
    re.IGNORECASE,
)
_COUNT_X_SIZE = re.compile(
    rf"(?<![\w.])(?P<count>\d+)\s*[x×]\s*(?P<num>{_NUM})\s*(?P<unit>TiB|TB|GiB|GB|MiB|MB)\b", re.IGNORECASE
)
_COUNT_X_WORD = re.compile(r"(?<![\w.])(?P<count>\d+)\s*[x×]\s*(?=[A-Za-z])", re.IGNORECASE)
_SIZE = re.compile(rf"(?<![\w.])(?P<num>{_NUM})\s*(?P<unit>TiB|TB|GiB|GB|MiB|MB)\b", re.IGNORECASE)
_EMBEDDED_SIZE = re.compile(rf"(?<=[-_])(?P<num>{_NUM})(?P<unit>TiB|TB|GiB|GB|MiB|MB)\b", re.IGNORECASE)
_BARE_NUM = re.compile(rf"(?<![\w.,])(?P<num>{_NUM})(?![\w.])")

_WORD_UNITS = {
    w: i
    for i, w in enumerate(
        "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen "
        "fifteen sixteen seventeen eighteen nineteen".split()
    )
}
_WORD_TENS = {w: (i + 2) * 10 for i, w in enumerate("twenty thirty forty fifty sixty seventy eighty ninety".split())}
_WORD_SCALES = {"thousand": 1_000, "million": 1_000_000, "billion": 1_000_000_000}
_NUMBER_WORDS = set(_WORD_UNITS) | set(_WORD_TENS) | set(_WORD_SCALES) | {"hundred", "dozen"}

_QUALIFIERS = [
    ("floor", re.compile(r"(starting\s+at|starts\s+at|starting\s+from|from|as\s+low\s+as|minimum|min\.?)\s*$", re.IGNORECASE)),
    ("ceiling", re.compile(r"(up\s+to|maximum|max\.?|at\s+most)\s*$", re.IGNORECASE)),
    ("approximate", re.compile(r"(~|≈|approx\.?|approximately|about|around|roughly|circa|ca\.)\s*$", re.IGNORECASE)),
    ("estimate", re.compile(r"(est\.?|estimated)\s*$", re.IGNORECASE)),
]


def _to_float(num: str) -> float:
    return float(num.replace(",", ""))


def _time_unit(token: str) -> str:
    token = token.lower()
    for canonical, alts in _TIME_UNITS.items():
        if token in alts:
            return canonical
    return token


def _qualifiers(text: str, start: int) -> list[str]:
    window = text[max(0, start - 24) : start]
    window = re.split(r"[,;|\n(]", window)[-1]
    return [name for name, pattern in _QUALIFIERS if pattern.search(window)]


class _Collector:
    def __init__(self) -> None:
        self.items: list[Quantity] = []

    def add(self, **kwargs: Any) -> None:
        self.items.append(Quantity(id=f"q{len(self.items) + 1}", **kwargs))


def _scan_string(text: str, path: str, out: _Collector) -> None:
    if text.strip().lower() in NULL_SENTINELS:
        out.add(raw=text, value=None, path=path, kind="null")
        return

    taken: list[tuple[int, int]] = []

    def free(a: int, b: int) -> bool:
        return all(b <= s or a >= e for s, e in taken)

    for m in _MONEY.finditer(text):
        if not free(m.start(), m.end()):
            continue
        value = _to_float(m.group("num"))
        suffix = (m.group("suffix") or "").lower()
        if suffix:
            value *= _SUFFIX[suffix]
        end = m.end()
        per = item = None
        tail = _PER_TAIL.match(text[end:])
        if tail:
            per = _time_unit(tail.group("per"))
            item = tail.group("item").lower() if tail.group("item") else None
            end += tail.end()
        out.add(
            raw=text[m.start() : end].strip(),
            value=value,
            path=path,
            kind="money",
            unit="USD",
            per=per,
            per_item=item,
            qualifiers=_qualifiers(text, m.start()),
        )
        taken.append((m.start(), end))

    for m in _COUNT_X_SIZE.finditer(text):
        if not free(m.start(), m.end()):
            continue
        quals = _qualifiers(text, m.start())
        out.add(raw=m.group(0), value=float(m.group("count")), path=path, kind="count", qualifiers=quals)
        out.add(
            raw=m.group(0),
            value=_to_float(m.group("num")),
            path=path,
            kind="size",
            unit=m.group("unit").upper().replace("IB", "iB"),
            per_item="each",
            qualifiers=quals,
        )
        taken.append((m.start(), m.end()))

    for m in _COUNT_X_WORD.finditer(text):
        if free(m.start(), m.end()):
            out.add(raw=m.group(0).strip(), value=float(m.group("count")), path=path, kind="count")
            taken.append((m.start(), m.end()))

    for pattern in (_SIZE, _EMBEDDED_SIZE):
        for m in pattern.finditer(text):
            if free(m.start(), m.end()):
                out.add(
                    raw=m.group(0),
                    value=_to_float(m.group("num")),
                    path=path,
                    kind="size",
                    unit=m.group("unit").upper().replace("IB", "iB"),
                    qualifiers=_qualifiers(text, m.start()),
                )
                taken.append((m.start(), m.end()))

    for m in _BARE_NUM.finditer(text):
        if free(m.start(), m.end()):
            out.add(raw=m.group(0), value=_to_float(m.group("num")), path=path, qualifiers=_qualifiers(text, m.start()))
            taken.append((m.start(), m.end()))

    for start, end, value in _number_word_runs(text):
        if free(start, end):
            out.add(raw=text[start:end], value=value, path=path, qualifiers=_qualifiers(text, start))
            taken.append((start, end))


def _number_word_runs(text: str) -> list[tuple[int, int, float]]:
    """Find spelled-out numbers such as 'two hundred' or 'twenty-five thousand'."""
    runs: list[tuple[int, int, float]] = []
    words = list(re.finditer(r"[A-Za-z]+", text))
    i = 0
    while i < len(words):
        if words[i].group(0).lower() not in _NUMBER_WORDS - {"hundred", "thousand", "million", "billion"}:
            i += 1
            continue
        j = i
        tokens: list[str] = []
        while j < len(words):
            word = words[j].group(0).lower()
            gap = text[words[j - 1].end() : words[j].start()] if j > i else ""
            if j > i and not re.fullmatch(r"[\s-]*", gap):
                break
            if word in _NUMBER_WORDS:
                tokens.append(word)
                j += 1
            elif word == "and" and j + 1 < len(words) and words[j + 1].group(0).lower() in _NUMBER_WORDS and tokens:
                j += 1
            else:
                break
        value = _words_to_number(tokens)
        if value is not None:
            runs.append((words[i].start(), words[j - 1].end(), value))
        i = j
    return runs


def _words_to_number(tokens: list[str]) -> float | None:
    total = current = 0
    for word in tokens:
        if word in _WORD_UNITS:
            current += _WORD_UNITS[word]
        elif word in _WORD_TENS:
            current += _WORD_TENS[word]
        elif word == "dozen":
            current = (current or 1) * 12
        elif word == "hundred":
            current = (current or 1) * 100
        elif word in _WORD_SCALES:
            total += (current or 1) * _WORD_SCALES[word]
            current = 0
    return float(total + current) if tokens else None


def _walk(value: Any, path: str, out: _Collector) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _walk(child, f"{path}.{key}" if path else str(key), out)
    elif isinstance(value, list):
        for i, child in enumerate(value):
            _walk(child, f"{path}[{i}]", out)
    elif isinstance(value, bool):
        return
    elif isinstance(value, (int, float)):
        out.add(raw=str(value), value=float(value), path=path)
    elif value is None:
        out.add(raw="null", value=None, path=path, kind="null")
    elif isinstance(value, str):
        _scan_string(value, path, out)


def annotate(source: ParsedSource, instructions: str | None = None) -> list[Quantity]:
    out = _Collector()
    if source.content_type == "text":
        _scan_string(source.text, "", out)
    else:
        _walk(source.value, "", out)
    if instructions and instructions.strip():
        _scan_string(instructions, "instructions", out)
        out.items = [q for q in out.items if not (q.path == "instructions" and q.kind == "null")]
    return out.items
