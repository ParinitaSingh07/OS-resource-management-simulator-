"""
Input validation helpers — OS Resource Management Simulator
===========================================================

``main.py`` is the ONLY module that talks to the keyboard. It reads raw text
and hands it to these functions, which either return a clean Python value or
raise a ``ValueError`` with a message that can be shown to the user as-is.

Keeping the parsing here means:
  * every prompt validates the same way (no duplicated ``try: int(...)``),
  * the parsing rules are unit-testable without faking stdin,
  * the algorithm modules still do their own defensive validation, because a
    library must not trust its caller.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from pathlib import Path

__all__ = [
    "parse_int",
    "parse_int_list",
    "parse_pid_vector",
    "choose",
    "list_datasets",
    "describe_dataset",
]


def parse_int(text: str, name: str, minimum: int | None = None, maximum: int | None = None) -> int:
    """Convert ``text`` to an int and check its range.

    Args:
        text: raw text from the user.
        name: what the number is, used in the error message ("burst time").
        minimum: smallest accepted value (inclusive), or None.
        maximum: largest accepted value (inclusive), or None.

    Raises:
        ValueError: empty text, not an integer, or outside the range.

    Example:
        >>> parse_int(" 42 ", "burst", 1, 100)
        42
    """
    cleaned = text.strip().replace(",", "")
    if not cleaned:
        raise ValueError(f"{name} is empty; enter a whole number")
    try:
        value = int(cleaned)
    except ValueError:
        raise ValueError(f"{name} must be a whole number (got {text.strip()!r})") from None
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum} (got {value})")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum} (got {value})")
    return value


def parse_int_list(
    text: str,
    name: str,
    minimum: int | None = None,
    maximum: int | None = None,
) -> list[int]:
    """Parse a list of integers separated by spaces, commas, tabs or colons.

    Raises:
        ValueError: the list is empty or one field is not an int in range.
    """
    fields = text.replace(",", " ").replace(":", " ").split()
    if not fields:
        raise ValueError(f"{name} is empty; enter at least one number")
    return [parse_int(f, f"{name} value {i + 1}", minimum, maximum) for i, f in enumerate(fields)]


def parse_pid_vector(text: str, name: str = " resource vector") -> tuple[str, list[int]]:
    """Parse ``P1 1 0 2`` into ``("P1", [1, 0, 2])``.

    Used by the deadlock menu for a resource request: the first field is the
    process id, the rest are the per-resource units.
    """
    fields = text.replace(",", " ").split()
    if len(fields) < 2:
        raise ValueError(f"{name} needs a process id followed by resource values")
    pid = fields[0]
    values = [parse_int(f, f"{name} value {i + 1}", 0) for i, f in enumerate(fields[1:])]
    return pid, values


def choose(text: str, options: Sequence[str], name: str = "choice") -> str:
    """Validate a menu answer against ``options`` (case-insensitive).

    Returns the canonical spelling from ``options`` so callers can compare
    against a single form.

    Raises:
        ValueError: the answer is not one of the options.
    """
    cleaned = text.strip().lower()
    for option in options:
        if cleaned == option.lower():
            return option
    raise ValueError(f"{name} must be one of: {', '.join(options)}")


def list_datasets(directory: Path, prefix: str = "") -> list[Path]:
    """Return the ``*.txt`` datasets in ``directory``, sorted by name.

    ``prefix`` filters by filename start (``"cpu"``, ``"memory"``, ...).
    """
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob(f"{prefix}*.txt") if p.is_file())


def describe_dataset(path: Path) -> str:
    """A short label for a dataset file: its name and first comment line.

    The header comment of each file states what the data demonstrates, which
    makes the menu self-documenting.
    """
    header = ""
    try:
        with path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                line = raw.strip()
                if line.startswith("#"):
                    header = line.lstrip("#").strip()
                    break
    except OSError:
        pass
    return f"{path.name} — {header}" if header else path.name
