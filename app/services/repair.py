"""Step 7: one targeted repair attempt when the first mapping is malformed or invalid."""

from __future__ import annotations


def repair_messages(messages: list[dict[str, str]], previous_output: str, problems: list[str]) -> list[dict[str, str]]:
    listed = "\n".join(f"- {p}" for p in problems)
    return [
        *messages,
        {"role": "assistant", "content": previous_output or "(empty response)"},
        {
            "role": "user",
            "content": (
                "Your mapping had these problems:\n"
                f"{listed}\n\n"
                "Return a corrected JSON mapping in the same format, one entry per target property. "
                "Fix only what the problems describe. If a required value truly is not in the source, "
                "keep missing=true and value=null; do not invent it."
            ),
        },
    ]
