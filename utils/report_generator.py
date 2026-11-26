"""
Report generator — OS Resource Management Simulator
===================================================

Two jobs, both kept out of the algorithm modules so those stay pure:

1. **Terminal tables** — turn a result dataclass into aligned text.
2. **Artefacts** — save Matplotlib charts to ``outputs/charts/`` and build the
   multi-page PDF report (``report.pdf``) from real, freshly computed results.

Matplotlib is imported defensively. If it is missing (a lab machine without
the package), every chart function returns ``None`` and the simulator keeps
working with text output only — it never crashes because a chart could not be
drawn. ``charts_available()`` tells the menu which situation it is in.

Chart files are written with the Agg backend, which needs no display, so the
same code works over SSH and inside the Bash scripts.
"""

from __future__ import annotations

import textwrap
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from modules.cpu_scheduling import CpuScheduleResult, IDLE
from modules.deadlock_management import (
    BankersState,
    DetectionResult,
    RequestResult,
    SafetyResult,
)
from modules.disk_scheduling import DiskResult
from modules.memory_management import MemoryResult

__all__ = [
    "charts_available",
    "format_cpu_result",
    "format_cpu_comparison",
    "format_gantt",
    "format_memory_result",
    "format_memory_comparison",
    "format_deadlock_state",
    "format_safety",
    "format_detection",
    "format_request",
    "format_disk_result",
    "format_disk_comparison",
    "save_cpu_comparison",
    "save_gantt",
    "save_memory_comparison",
    "save_disk_comparison",
    "save_disk_paths",
    "generate_pdf_report",
    "matplotlib_version",
]

# ---------------------------------------------------------------------------
# Matplotlib, imported so that a missing install is not fatal
# ---------------------------------------------------------------------------
try:                                        # pragma: no cover - depends on the machine
    import matplotlib

    matplotlib.use("Agg")                   # file-only backend, no display needed
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    _MPL_AVAILABLE = True
    _MPL_ERROR = ""
except Exception as exc:                    # pragma: no cover
    plt = None
    PdfPages = None
    _MPL_AVAILABLE = False
    _MPL_ERROR = str(exc)

#: Colour per process, cycled; IDLE always grey.
_PALETTE = (
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
)
_IDLE_COLOUR = "#d9d9d9"


def charts_available() -> bool:
    """True when Matplotlib could be imported, so charts can be saved."""
    return _MPL_AVAILABLE


def matplotlib_error() -> str:
    """Why Matplotlib is unavailable (empty string when it works)."""
    return _MPL_ERROR


def matplotlib_version() -> str:
    """Matplotlib version string, or ``"not installed"`` when unavailable."""
    if not _MPL_AVAILABLE:
        return "not installed"
    import matplotlib

    return matplotlib.__version__


# ---------------------------------------------------------------------------
# Shared formatting helpers
# ---------------------------------------------------------------------------
def _rule(width: int = 78, char: str = "-") -> str:
    return char * width


def _title(text: str, width: int = 78) -> str:
    """A centred section title with rules above and below."""
    return f"{_rule(width, '=')}\n{text}\n{_rule(width, '=')}"


def _fmt_num(value: float, decimals: int = 2) -> str:
    """Fixed-width number, avoiding ``-0.00`` for tiny negatives."""
    if abs(value) < 10 ** (-(decimals + 1)):
        value = 0.0
    return f"{value:.{decimals}f}"


# ---------------------------------------------------------------------------
# CPU tables
# ---------------------------------------------------------------------------
def format_gantt(
    gantt: Sequence[tuple[str, int, int]], width: int = 96
) -> list[str]:
    """Render the timeline as wrapped lines of ``| P1 0-8 | IDLE 8-10 | ...``.

    Segments are joined until a line would exceed ``width`` characters, so a
    long Round Robin schedule stays readable in a terminal.
    """
    lines: list[str] = []
    current = ""
    for pid, start, end in gantt:
        piece = f"| {pid} {start}-{end} "
        if current and len(current) + len(piece) + 1 > width:
            lines.append(current + "|")
            current = piece
        else:
            current += piece
    if current:
        lines.append(current + "|")
    return lines or ["(empty schedule)"]


def format_cpu_result(res: CpuScheduleResult) -> str:
    """Full table + aggregates + Gantt for one CPU schedule."""
    label = res.algorithm + (f"  (quantum = {res.quantum})" if res.quantum is not None else "")
    out = [f"Algorithm : {label}"]
    header = f"{'PID':<6}{'AT':>4}{'BT':>4}{'PRI':>5}{'CT':>5}{'TAT':>5}{'WT':>5}{'RT':>5}"
    out.append("  " + header)
    out.append("  " + _rule(len(header)))
    for r in res.rows:
        out.append(
            f"  {r.pid:<6}{r.arrival:>4}{r.burst:>4}{r.priority:>5}"
            f"{r.completion:>5}{r.turnaround:>5}{r.waiting:>5}{r.response:>5}"
        )
    out.append("  " + _rule(len(header)))
    out.append(
        f"  Averages  : waiting {_fmt_num(res.avg_waiting)}   "
        f"turnaround {_fmt_num(res.avg_turnaround)}   response {_fmt_num(res.avg_response)}"
    )
    out.append(
        f"  CPU       : utilisation {_fmt_num(res.cpu_utilisation)}%   "
        f"throughput {_fmt_num(res.throughput, 4)} proc/unit   "
        f"span {res.total_time}   idle {res.idle_time}"
    )
    out.append("  Gantt     :")
    out.extend("    " + line for line in format_gantt(res.gantt))
    return "\n".join(out)


def format_cpu_comparison(results: dict[str, CpuScheduleResult]) -> str:
    """One row per algorithm; the best average waiting time is marked ``<--``."""
    header = (
        f"{'ALGORITHM':<11}{'AVG WT':>9}{'AVG TAT':>9}{'AVG RT':>9}"
        f"{'CPU %':>9}{'THR/PU':>9}{'SPAN':>7}{'IDLE':>7}"
    )
    out = [header, _rule(len(header))]
    best = min(results.values(), key=lambda r: r.avg_waiting).algorithm
    for res in results.values():
        mark = "  <-- lowest average waiting time" if res.algorithm == best else ""
        out.append(
            f"{res.algorithm:<11}{_fmt_num(res.avg_waiting):>9}"
            f"{_fmt_num(res.avg_turnaround):>9}{_fmt_num(res.avg_response):>9}"
            f"{_fmt_num(res.cpu_utilisation):>9}{_fmt_num(res.throughput, 4):>9}"
            f"{res.total_time:>7}{res.idle_time:>7}{mark}"
        )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Memory tables
# ---------------------------------------------------------------------------
def format_memory_result(res: MemoryResult) -> str:
    """Allocation table, totals, fragmentation and the final memory layout."""
    out = [f"Algorithm : {res.algorithm}    model: {res.model.upper()}"]
    header = (
        f"{'PID':<6}{'REQ':>6}{'BLOCK':>7}{'ALLOC':>7}"
        f"{'INT.FRAG':>10}{'STATUS':>11}   REASON"
    )
    out.append("  " + header)
    out.append("  " + _rule(len(header)))
    for a in res.allocations:
        block = "-" if a.block_id is None else str(a.block_id)
        out.append(
            f"  {a.pid:<6}{a.size:>6}{block:>7}{a.allocated_size:>7}"
            f"{a.internal_frag:>10}{a.status:>11}   {a.reason}"
        )
    out.append("  " + _rule(len(header)))
    out.append(
        f"  Memory    : total {res.total_memory}   reserved by blocks {res.allocated_memory}"
        f"   free {res.free_memory}"
    )
    out.append(
        f"  Placed    : {res.usable_memory} units of process data in "
        f"{res.allocated_count}/{len(res.allocations)} process(es)"
    )
    out.append(
        f"  Fragments : internal {res.internal_frag}   external {res.external_frag}"
        f" ({res.stranded_blocks} stranded block(s))"
    )
    out.append(f"  Utilisation: {_fmt_num(res.utilisation)}%")
    layout = "  ".join(
        f"[{b.block_id}:{b.size}{' FREE' if b.is_free else f' {b.pid}({b.used})'}]"
        for b in res.blocks
    )
    out.append("  Layout    : " + layout)
    return "\n".join(out)


def format_memory_comparison(results: dict[str, MemoryResult], model: str) -> str:
    """Compare the three placement strategies for one model."""
    header = (
        f"{'ALGORITHM':<11}{'PLACED':>8}{'UTIL %':>9}{'INT.FRAG':>10}"
        f"{'EXT.FRAG':>10}{'FREE':>8}{'REJECTED':>10}"
    )
    out = [f"Model: {model.upper()} partitions", header, _rule(len(header))]
    for res in results.values():
        out.append(
            f"{res.algorithm:<11}{res.allocated_count:>8}{_fmt_num(res.utilisation):>9}"
            f"{res.internal_frag:>10}{res.external_frag:>10}{res.free_memory:>8}"
            f"{len(res.rejected):>10}"
        )
    best = max(results.values(), key=lambda r: (r.allocated_count, r.utilisation))
    out.append(
        f"Best on this dataset: {best.algorithm} "
        f"({best.allocated_count} placed, {_fmt_num(best.utilisation)}% utilisation)"
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Deadlock tables
# ---------------------------------------------------------------------------
def _vec(values: Sequence[int]) -> str:
    return "(" + ", ".join(str(v) for v in values) + ")"


def format_deadlock_state(state: BankersState) -> str:
    """Allocation, Max, derived Need and Available in one table."""
    need = state.need
    header = f"{'PID':<6}{'Allocation':>16}{'Max':>16}{'Need':>16}"
    out = [header, _rule(len(header))]
    for i, pid in enumerate(state.pids):
        out.append(
            f"{pid:<6}{_vec(state.allocation[i]):>16}"
            f"{_vec(state.maximum[i]):>16}{_vec(need[i]):>16}"
        )
    out.append(_rule(len(header)))
    out.append(f"Available: {_vec(state.available)}    Total resources: {_vec(state.total_resources)}")
    return "\n".join(out)


def format_safety(safety: SafetyResult) -> str:
    """Work trace of the safety algorithm and its verdict."""
    header = f"{'PID':<6}{'Work':>14}{'Need':>14}{'Work + Allocation':>22}"
    out = [header, _rule(len(header))]
    for step in safety.steps:
        out.append(
            f"{step.pid:<6}{_vec(step.work_before):>14}{_vec(step.need):>14}"
            f"{_vec(step.work_after):>22}"
        )
    out.append(_rule(len(header)))
    out.append(f"Verdict: {safety.summary}")
    return "\n".join(out)


def format_request(result: RequestResult) -> str:
    """Verdict of one resource request, with the reason on the next line."""
    verdict = "GRANTED" if result.granted else "REFUSED"
    return f"{result.pid} requests {_vec(result.request)}: {verdict}\n  {result.reason}"


def format_detection(detection: DetectionResult) -> str:
    """Work trace of detection, the finish order and the deadlocked set."""
    header = f"{'PID':<6}{'Work':>14}{'Request':>14}{'Work + Allocation':>22}"
    out = [f"Request source: {detection.request_source}", header, _rule(len(header))]
    for step in detection.steps:
        out.append(
            f"{step.pid:<6}{_vec(step.work_before):>14}{_vec(step.request):>14}"
            f"{_vec(step.work_after):>22}"
        )
    out.append(_rule(len(header)))
    out.append(f"Finish order: {' -> '.join(detection.order) if detection.order else '(none)'}")
    out.append(f"Verdict: {detection.summary}")
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Disk tables
# ---------------------------------------------------------------------------
def format_disk_result(res: DiskResult) -> str:
    """Per-request arithmetic, total, average and the head path."""
    label = res.algorithm + (f"  (direction = {res.direction})" if res.direction else "")
    out = [f"Algorithm : {label}"]
    header = f"{'#':<4}{'MOVE':>16}{'DIST':>7}   NOTE"
    out.append("  " + header)
    out.append("  " + _rule(len(header) + 4))
    for i, m in enumerate(res.movements, start=1):
        note = "boundary" if m.is_boundary else ""
        out.append(f"  {i:<4}{f'{m.start} -> {m.end}':>16}{m.distance:>7}   {note}")
    out.append("  " + _rule(len(header) + 4))
    out.append(f"  Served order  : {', '.join(str(c) for c in res.order)}")
    out.append(f"  Head path     : {res.sequence_text}")
    out.append(
        "  Total movement: "
        + " + ".join(str(m.distance) for m in res.movements)
        + f" = {res.total_movement} cylinders"
    )
    out.append(
        f"  Average       : {res.total_movement} / {len(res.requests)} requests"
        f" = {_fmt_num(res.average_movement)} cylinders"
    )
    if res.return_jump:
        out.append(
            f"  C-SCAN jump   : {res.return_jump} cylinders (not counted; "
            f"charged path = {res.total_movement + res.return_jump})"
        )
    return "\n".join(out)


def format_disk_comparison(results: dict[str, DiskResult]) -> str:
    """Total and average movement per algorithm, best marked."""
    header = f"{'ALGORITHM':<11}{'TOTAL':>8}{'AVG/REQ':>10}{'REQUESTS':>10}{'JUMP':>8}"
    out = [header, _rule(len(header))]
    for res in results.values():
        out.append(
            f"{res.algorithm:<11}{res.total_movement:>8}"
            f"{_fmt_num(res.average_movement):>10}{len(res.requests):>10}"
            f"{res.return_jump:>8}"
        )
    best = min(results.values(), key=lambda r: r.total_movement)
    out.append(
        f"Lowest total movement: {best.algorithm} ({best.total_movement} cylinders). "
        f"C-SCAN's jump is excluded above; add it for the charged path."
    )
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def _new_figure(figsize: tuple[float, float] = (8.0, 4.5)):
    """Create a figure, or ``None`` when Matplotlib is unavailable."""
    if not _MPL_AVAILABLE:
        return None
    fig, ax = plt.subplots(figsize=figsize)
    return fig, ax


def _save(fig, path: Path) -> Path | None:
    """Save and close a figure, creating the folder if needed."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        fig.tight_layout()
        fig.savefig(path, dpi=150)
        return path
    finally:
        plt.close(fig)


def save_cpu_comparison(
    results: dict[str, CpuScheduleResult], path: Path, title: str = "CPU scheduling comparison"
) -> Path | None:
    """Grouped bar chart of average waiting and turnaround time per algorithm."""
    created = _new_figure()
    if created is None:
        return None
    fig, ax = created
    names = list(results)
    waiting = [results[n].avg_waiting for n in names]
    turnaround = [results[n].avg_turnaround for n in names]
    x = range(len(names))
    width = 0.38
    bars1 = ax.bar([i - width / 2 for i in x], waiting, width, label="Avg waiting", color="#4e79a7")
    bars2 = ax.bar([i + width / 2 for i in x], turnaround, width, label="Avg turnaround", color="#f28e2b")
    for bars in (bars1, bars2):
        for bar in bars:
            ax.annotate(
                f"{bar.get_height():.2f}",
                (bar.get_x() + bar.get_width() / 2, bar.get_height()),
                textcoords="offset points", xytext=(0, 3), ha="center", fontsize=7.5,
            )
    ax.set_xticks(list(x))
    ax.set_xticklabels(names)
    ax.set_ylabel("time units")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    ax.legend()
    return _save(fig, path)


def save_gantt(
    res: CpuScheduleResult, path: Path, title: str | None = None
) -> Path | None:
    """Horizontal timeline: one row, one coloured bar per Gantt segment."""
    created = _new_figure((9.0, 2.6))
    if created is None:
        return None
    fig, ax = created
    pids = sorted({pid for pid, _, _ in res.gantt if pid != IDLE})
    colours = {pid: _PALETTE[i % len(_PALETTE)] for i, pid in enumerate(pids)}
    for pid, start, end in res.gantt:
        colour = _IDLE_COLOUR if pid == IDLE else colours.get(pid, "#999999")
        ax.broken_barh([(start, end - start)], (0, 1), facecolors=colour,
                       edgecolors="black", linewidth=0.6,
                       hatch="//" if pid == IDLE else None)
        if end - start >= 1:
            ax.text((start + end) / 2, 0.5, pid, ha="center", va="center", fontsize=8)
    ax.set_xlim(0, max(end for _, _, end in res.gantt) if res.gantt else 1)
    ax.set_ylim(0, 1)
    ax.set_yticks([])
    ax.set_xlabel("time")
    ax.set_title(title or f"Gantt chart — {res.algorithm}")
    ax.grid(axis="x", alpha=0.3)
    return _save(fig, path)


def save_memory_comparison(
    results: dict[str, MemoryResult], path: Path, model: str
) -> Path | None:
    """Two panels: fragmentation in units, and utilisation in percent."""
    if not _MPL_AVAILABLE:
        return None
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9.0, 4.2))
    names = list(results)
    internal = [results[n].internal_frag for n in names]
    external = [results[n].external_frag for n in names]
    x = range(len(names))
    width = 0.38
    ax1.bar([i - width / 2 for i in x], internal, width, label="Internal", color="#4e79a7")
    ax1.bar([i + width / 2 for i in x], external, width, label="External", color="#e15759")
    ax1.set_xticks(list(x))
    ax1.set_xticklabels(names)
    ax1.set_ylabel("units")
    ax1.set_title(f"Fragmentation ({model} model)")
    ax1.grid(axis="y", alpha=0.3)
    ax1.legend()

    bars = ax2.bar(names, [results[n].utilisation for n in names], color="#59a14f")
    for bar in bars:
        ax2.annotate(
            f"{bar.get_height():.2f}%",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points", xytext=(0, 3), ha="center", fontsize=8,
        )
    ax2.set_ylabel("utilisation %")
    ax2.set_ylim(0, 105)
    ax2.set_title("Memory utilisation")
    ax2.grid(axis="y", alpha=0.3)
    return _save(fig, path)


def save_disk_comparison(results: dict[str, DiskResult], path: Path) -> Path | None:
    """Bar chart of total head movement per algorithm."""
    created = _new_figure()
    if created is None:
        return None
    fig, ax = created
    names = list(results)
    values = [results[n].total_movement for n in names]
    bars = ax.bar(names, values, color=["#4e79a7", "#f28e2b", "#59a14f", "#e15759"][: len(names)])
    for bar in bars:
        ax.annotate(
            f"{int(bar.get_height())}",
            (bar.get_x() + bar.get_width() / 2, bar.get_height()),
            textcoords="offset points", xytext=(0, 3), ha="center", fontsize=9,
        )
    ax.set_ylabel("total head movement (cylinders)")
    ax.set_title("Disk scheduling comparison")
    ax.grid(axis="y", alpha=0.3)
    return _save(fig, path)


def save_disk_paths(
    results: dict[str, DiskResult], path: Path, head: int
) -> Path | None:
    """Head position versus service step: shows each algorithm's seek pattern."""
    created = _new_figure((9.0, 4.5))
    if created is None:
        return None
    fig, ax = created
    for i, (name, res) in enumerate(results.items()):
        positions = [head] + [m.end for m in res.movements]
        ax.plot(range(len(positions)), positions, marker="o", markersize=3,
                linewidth=1.3, label=f"{name} ({res.total_movement})",
                color=_PALETTE[i % len(_PALETTE)])
    ax.set_xlabel("service step")
    ax.set_ylabel("cylinder")
    ax.set_title("Head movement path")
    ax.grid(alpha=0.3)
    ax.legend(title="algorithm (total)", fontsize=8)
    return _save(fig, path)


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------
def generate_pdf_report(
    sections: Sequence[tuple[str, Sequence[str]]],
    path: Path,
    title: str = "OS Resource Management Simulator — Project Report",
    width: int = 108,
    lines_per_page: int = 58,
) -> Path:
    """Write a multi-page, monospace PDF from ``(heading, lines)`` sections.

    The content is whatever the caller passes — ``main.py`` passes real numbers
    from freshly executed algorithms, so the PDF can never contain invented
    results. Long lines are wrapped and long sections continue onto a new page
    with ``(continued)`` in the header.

    Raises:
        RuntimeError: Matplotlib is unavailable, so no PDF can be produced.
    """
    if not _MPL_AVAILABLE:
        raise RuntimeError(
            "matplotlib is required to build the PDF report: "
            f"{_MPL_ERROR or 'not installed'}. Run setup.sh or pip install -r requirements.txt"
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%d %B %Y, %H:%M")

    # Flatten sections into pages of wrapped text, keeping headings visible.
    pages: list[tuple[str, list[str]]] = []
    for heading, lines in sections:
        wrapped: list[str] = []
        for block in lines:
            # A section element may itself be a multi-line table (all the
            # format_* helpers return one string with newlines). Split those
            # first, otherwise textwrap would re-flow the whole table into a
            # paragraph and destroy the column alignment.
            for line in str(block).splitlines() or [""]:
                wrapped.extend(
                    textwrap.wrap(
                        line,
                        width=width,
                        replace_whitespace=False,
                        drop_whitespace=False,
                    )
                    or [""]
                )
        if not wrapped:
            wrapped = [""]
        # Leave room for the page header and footer.
        capacity = lines_per_page - 2
        chunks = [wrapped[i:i + capacity] for i in range(0, len(wrapped), capacity)]
        for n, chunk in enumerate(chunks):
            suffix = "" if n == 0 else " (continued)"
            pages.append((heading + suffix, chunk))

    with PdfPages(path) as pdf:
        for number, (heading, lines) in enumerate(pages, start=1):
            fig = plt.figure(figsize=(8.27, 11.69))       # A4 portrait
            fig.text(0.06, 0.965, heading, fontsize=12, weight="bold", va="top")
            fig.text(0.06, 0.94, _rule(96, "-"), fontsize=8, family="monospace", va="top")
            fig.text(
                0.06, 0.915, "\n".join(lines),
                fontsize=7.4, family="monospace", va="top", linespacing=1.25,
            )
            fig.text(0.06, 0.035, title, fontsize=7, color="#555555")
            fig.text(0.94, 0.035, f"page {number}/{len(pages)}", fontsize=7,
                     color="#555555", ha="right")
            fig.text(0.06, 0.05, f"generated {stamp}", fontsize=6.5, color="#777777")
            pdf.savefig(fig)
            plt.close(fig)

        info = pdf.infodict()
        info["Title"] = title
        info["Author"] = "OS Resource Management Simulator"
        info["Subject"] = "CPU scheduling, memory management, deadlock and disk scheduling"
        info["CreationDate"] = datetime.now()

    return path
