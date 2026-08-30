"""Terminal presentation for DevFlow.

DevFlow's output is dense: findings, layered evidence, import chains, git
history, confidence levels.  Presented as flat text it is unreadable, and the
developer cannot tell an observed fact from an inference -- which is the one
distinction the whole product rests on.

This module is presentation only.  It never computes a finding, never reorders
one, and never introduces a fact.  Standard library only.

Colour is disabled automatically when stdout is not a terminal, when NO_COLOR
is set, or when TERM=dumb, so piped and redirected output stays clean.
"""

from __future__ import annotations

import os
import shutil
import sys
from typing import Iterable, Optional, Sequence

# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_CODES = {
    "bold": "\033[1m",
    "dim": "\033[2m",
    "red": "\033[31m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "blue": "\033[34m",
    "magenta": "\033[35m",
    "cyan": "\033[36m",
    "grey": "\033[90m",
    "bright_red": "\033[91m",
    "bright_yellow": "\033[93m",
}


def colour_enabled(stream=None) -> bool:
    """Whether ANSI colour should be emitted."""
    if os.environ.get("NO_COLOR") is not None:
        return False
    if os.environ.get("DEVFLOW_NO_COLOR", "").strip().lower() in ("1", "true", "yes"):
        return False
    if os.environ.get("TERM", "") == "dumb":
        return False
    target = stream if stream is not None else sys.stdout
    try:
        return bool(target.isatty())
    except Exception:  # noqa: BLE001
        return False


def paint(text: str, *styles: str, stream=None) -> str:
    """Wrap ``text`` in ANSI styles, or return it unchanged when colour is off."""
    if not styles or not colour_enabled(stream):
        return text
    prefix = "".join(_CODES.get(style, "") for style in styles)
    return f"{prefix}{text}{_RESET}" if prefix else text


def terminal_width(default: int = 80) -> int:
    try:
        width = shutil.get_terminal_size((default, 24)).columns
    except Exception:  # noqa: BLE001
        return default
    return max(60, min(width, 110))


# ---------------------------------------------------------------------------
# Severity and evidence vocabulary
# ---------------------------------------------------------------------------

_SEVERITY_STYLE = {
    "critical": ("bright_red", "bold"),
    "high": ("red", "bold"),
    "medium": ("yellow",),
    "low": ("cyan",),
}

# Evidence markers encode the product's central distinction: a filled marker is
# something the repository proves, a hollow one is something DevFlow derived,
# and a question mark is interpretation.
_EVIDENCE_MARKS = {
    "DIRECT_EVIDENCE": ("*", "green", "observed fact"),
    "DERIVED_RELATIONSHIP": ("o", "cyan", "derived relationship"),
    "INFERENCE": ("?", "yellow", "interpretation"),
}


def severity_badge(severity: Optional[str]) -> str:
    label = (severity or "unrated").upper()
    styles = _SEVERITY_STYLE.get((severity or "").lower(), ("grey",))
    return paint(f" {label:8}", *styles)


def evidence_mark(evidence_type: Optional[str]) -> tuple[str, str]:
    """Return (painted marker, plain human label) for an evidence type."""
    mark, colour, label = _EVIDENCE_MARKS.get(
        str(evidence_type or "").upper(), ("-", "grey", "unclassified")
    )
    return paint(mark, colour), label


# ---------------------------------------------------------------------------
# Layout primitives
# ---------------------------------------------------------------------------


def rule(title: str = "", width: Optional[int] = None) -> str:
    total = width or terminal_width()
    if not title:
        return paint("-" * total, "grey")
    prefix = f"-- {title} "
    return paint(prefix + "-" * max(0, total - len(prefix)), "grey")


def heading(text: str) -> str:
    return paint(text.upper(), "bold")


def wrap(text: str, indent: int = 2, width: Optional[int] = None) -> list[str]:
    """Word-wrap ``text`` to the terminal width with a hanging indent."""
    import textwrap

    total = (width or terminal_width()) - indent
    collapsed = " ".join((text or "").split())
    if not collapsed:
        return []
    pad = " " * indent
    return [pad + line for line in textwrap.wrap(collapsed, width=max(20, total))]


def field(label: str, value: str, label_width: int = 20) -> str:
    """A label/value row. Long labels get a single space rather than colliding."""
    padded = label.ljust(label_width) if len(label) < label_width else label + " "
    return f"  {paint(padded, 'grey')}{value}"


def bullet(text: str, marker: str = "-", indent: int = 2) -> list[str]:
    lines = wrap(text, indent=indent + len(marker) + 1)
    if not lines:
        return []
    first = lines[0]
    lines[0] = " " * indent + marker + first[indent + len(marker) :]
    return lines


# ---------------------------------------------------------------------------
# Tree rendering (blast radius)
# ---------------------------------------------------------------------------


def tree(
    root: str,
    children_of,
    *,
    max_depth: int = 2,
    max_children: int = 6,
    annotate=None,
) -> list[str]:
    """Render a dependency tree with box-drawing connectors.

    ``children_of(path)`` returns the next level; ``annotate(path, depth)``
    returns an optional trailing note.  Truncation is reported rather than
    hidden, so the developer always knows the tree is partial.
    """
    lines = [paint(root, "bold")]
    seen = {root}

    def walk(node: str, depth: int, prefix: str) -> None:
        if depth >= max_depth:
            return
        children = [c for c in children_of(node) if c not in seen]
        shown = children[:max_children]
        hidden = len(children) - len(shown)
        for index, child in enumerate(shown):
            seen.add(child)
            last = index == len(shown) - 1 and hidden == 0
            connector = "`- " if last else "|- "
            note = annotate(child, depth) if annotate else ""
            suffix = f"  {paint(note, 'grey')}" if note else ""
            lines.append(f"{prefix}{paint(connector, 'grey')}{child}{suffix}")
            walk(child, depth + 1, prefix + ("   " if last else "|  "))
        if hidden > 0:
            lines.append(f"{prefix}{paint(f'`- ... {hidden} more', 'grey')}")

    walk(root, 0, "")
    return lines


# ---------------------------------------------------------------------------
# Status vocabulary
# ---------------------------------------------------------------------------

_STATUS_STYLE = {
    "resolved": ("green", "bold"),
    "validated": ("green", "bold"),
    "passed": ("green",),
    "partially_resolved": ("yellow",),
    "not_resolved": ("red",),
    "validation_failed": ("bright_red", "bold"),
    "failed": ("red", "bold"),
    "rejected": ("grey",),
    "pending": ("grey",),
}


def status_badge(status: Optional[str]) -> str:
    key = str(status or "unknown").lower()
    styles = _STATUS_STYLE.get(key, ("grey",))
    return paint(key.replace("_", " ").upper(), *styles)


def check(ok: bool) -> str:
    return paint("PASS", "green", "bold") if ok else paint("FAIL", "red", "bold")


def emit(lines: Iterable[str]) -> None:
    for line in lines:
        print(line)


# ---------------------------------------------------------------------------
# Document structure
# ---------------------------------------------------------------------------


def title(text: str, subtitle: str = "") -> list[str]:
    """A command's opening banner."""
    lines = ["", paint(text, "bold")]
    if subtitle:
        lines.append(paint(f"  {subtitle}", "grey"))
    lines.append(rule())
    return lines


def section(text: str, note: str = "") -> list[str]:
    """A titled section break with breathing room above it."""
    header = paint(text.upper(), "bold")
    if note:
        header += "  " + paint(note, "grey")
    return ["", header, paint("-" * min(terminal_width(), 72), "grey")]


def visible_length(text: str) -> int:
    """Character width ignoring ANSI escape sequences."""
    out, index = 0, 0
    while index < len(text):
        if text[index] == "\033":
            end = text.find("m", index)
            if end == -1:
                break
            index = end + 1
            continue
        out += 1
        index += 1
    return out


def pad(text: str, width: int, align: str = "left") -> str:
    """Pad to ``width`` counting only visible characters."""
    gap = max(0, width - visible_length(text))
    if align == "right":
        return " " * gap + text
    return text + " " * gap


def table(
    rows: Sequence[Sequence[str]],
    *,
    headers: Optional[Sequence[str]] = None,
    aligns: Optional[Sequence[str]] = None,
    indent: int = 2,
    gap: int = 2,
) -> list[str]:
    """Render aligned columns.

    Widths are measured on visible characters, so coloured cells line up.
    Columns are never truncated: a finding id or a file path stays complete
    even if it makes the row wide.
    """
    if not rows:
        return []
    columns = max(len(row) for row in rows)
    if headers:
        columns = max(columns, len(headers))
    aligns = list(aligns or []) + ["left"] * (columns - len(aligns or []))

    widths = [0] * columns
    considered = list(rows) + ([list(headers)] if headers else [])
    for row in considered:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], visible_length(str(cell)))

    pad_left = " " * indent
    separator = " " * gap
    out: list[str] = []

    if headers:
        head = separator.join(
            pad(paint(str(cell).upper(), "grey"), widths[i], aligns[i])
            for i, cell in enumerate(headers)
        )
        out.append(pad_left + head.rstrip())

    for row in rows:
        cells = [
            pad(str(cell), widths[i], aligns[i]) for i, cell in enumerate(row)
        ]
        out.append(pad_left + separator.join(cells).rstrip())
    return out


def steps(items: Sequence[str], *, start: int = 1) -> list[str]:
    """A numbered next-step list."""
    return [
        f"  {paint(f'{start + index}.', 'grey')} {item}" for index, item in enumerate(items)
    ]


def command_hint(command: str, note: str = "") -> str:
    """A runnable command the developer can copy."""
    line = f"  {paint('$', 'grey')} {paint(command, 'cyan')}"
    return f"{line}  {paint(note, 'grey')}" if note else line


def note(text: str, tone: str = "grey") -> list[str]:
    return wrap(text, indent=2) and [paint(line, tone) for line in wrap(text, indent=2)]


def progress(step: int, total: int, label: str) -> str:
    """A single pipeline step, printed as it completes."""
    marker = paint("ok", "green")
    counter = paint(f"[{step}/{total}]", "grey")
    return f"  {counter} {marker}  {label}"


def kv_block(pairs: Sequence[tuple[str, str]], label_width: int = 20) -> list[str]:
    return [field(label, value, label_width) for label, value in pairs]


def blank() -> str:
    return ""


def legend(entries: Sequence[tuple[str, str]]) -> str:
    """A compact key so markers are never unexplained."""
    parts = [f"{mark} {paint(label, 'grey')}" for mark, label in entries]
    return "  " + paint("key: ", "grey") + paint(" | ", "grey").join(parts)
