"""
CPU Scheduling module — OS Resource Management Simulator
========================================================

Implements five CPU scheduling algorithms and computes the standard
performance metrics for each:

    FCFS      First Come First Serve        (non-preemptive, arrival order)
    SJF       Shortest Job First            (non-preemptive, shortest burst)
    SRTF      Shortest Remaining Time First (preemptive SJF)
    PRIORITY  Priority Scheduling           (non-preemptive, smaller number = higher priority)
    RR        Round Robin                   (preemptive, fixed time quantum)

Design rules (from docs/PHASE1_SYSTEM_DESIGN.md):
  * Every algorithm is a PURE FUNCTION: ``processes -> CpuScheduleResult``.
    No input(), no print(), no file paths. This keeps the logic unit-testable.
  * All five return the SAME result type, so comparison code has no special cases.
  * Metrics use one formula sheet only:
        completion  = clock value when the process's last slice ends
        turnaround  = completion - arrival
        waiting     = turnaround - burst
        response    = first_cpu_time - arrival
        utilisation = busy_time / (max(completion) - min(arrival)) * 100
        throughput  = number_of_processes / (max(completion) - min(arrival))
  * Ties are broken by earlier arrival, then by the order the processes were
    supplied. Python's ``min``/``sorted`` are stable, so the input order wins
    automatically for equal keys — no explicit index is needed.

Time is an abstract integer "time unit"; no real clock is involved.

Academic notes (concept, OS use, complexity) are in the docstrings of each
algorithm, because that is what a viva will ask about.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "IDLE",
    "DEFAULT_QUANTUM",
    "Process",
    "ProcessResult",
    "CpuScheduleResult",
    "fcfs",
    "sjf",
    "srtf",
    "priority_scheduling",
    "round_robin",
    "run_algorithm",
    "ALGORITHMS",
    "load_processes",
    "parse_process_lines",
]

#: Label used in the Gantt timeline for intervals where the CPU had no runnable process.
IDLE = "IDLE"

#: Time slice used by Round Robin when the caller does not supply one.
DEFAULT_QUANTUM = 4


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Process:
    """One process submitted to the scheduler.

    Attributes:
        pid:      Process identifier, e.g. ``"P1"``.
        arrival:  Arrival time in the ready queue (>= 0).
        burst:    Total CPU time required (> 0).
        priority: Smaller number means HIGHER priority (1 is the highest).
                  Ignored by FCFS, SJF, SRTF and Round Robin.
    """

    pid: str
    arrival: int
    burst: int
    priority: int = 0


@dataclass
class ProcessResult:
    """Per-process outcome of one schedule."""

    pid: str
    arrival: int
    burst: int
    priority: int
    completion: int
    turnaround: int
    waiting: int
    response: int


@dataclass
class CpuScheduleResult:
    """Everything one algorithm produced, in one object.

    ``gantt`` is a list of ``(pid, start, end)`` segments, where ``pid`` may be
    ``IDLE``. Segments (not one start/end pair per process) are used because
    preemptive algorithms (SRTF, RR) give a process several slices and because
    idle gaps must be visible for CPU utilisation to be exact.
    """

    algorithm: str
    quantum: int | None
    rows: list[ProcessResult]
    gantt: list[tuple[str, int, int]]
    avg_waiting: float
    avg_turnaround: float
    avg_response: float
    cpu_utilisation: float
    throughput: float
    total_time: int
    idle_time: int


# ---------------------------------------------------------------------------
# Validation (defensive: the menu validates too, but the module must not trust it)
# ---------------------------------------------------------------------------
def _validate(processes: Sequence[Process]) -> None:
    """Check the invariants every algorithm relies on.

    Raises:
        TypeError:  a non-Process object was passed.
        ValueError: empty list, duplicate pid, negative arrival/priority,
                    or a non-positive burst.

    The module raises instead of printing because it has no UI responsibility;
    the caller decides how to show the message.
    """
    if not isinstance(processes, Sequence) or isinstance(processes, (str, bytes)):
        raise TypeError("processes must be a sequence of Process objects")
    if len(processes) == 0:
        raise ValueError("process list is empty; provide at least one process")

    seen: set[str] = set()
    for p in processes:
        if not isinstance(p, Process):
            raise TypeError(f"expected Process, got {type(p).__name__}")
        if p.pid in seen:
            raise ValueError(f"duplicate process id {p.pid!r}")
        seen.add(p.pid)
        if p.burst <= 0:
            raise ValueError(f"{p.pid}: burst time must be > 0 (got {p.burst})")
        if p.arrival < 0:
            raise ValueError(f"{p.pid}: arrival time must be >= 0 (got {p.arrival})")
        if p.priority < 0:
            raise ValueError(f"{p.pid}: priority must be >= 0 (got {p.priority})")


# ---------------------------------------------------------------------------
# Shared result assembly
# ---------------------------------------------------------------------------
def _build_result(
    algorithm: str,
    processes: Sequence[Process],
    completion: dict[str, int],
    first_start: dict[str, int],
    gantt: list[tuple[str, int, int]],
    quantum: int | None = None,
) -> CpuScheduleResult:
    """Turn raw schedule bookkeeping into the public result object.

    Calculating the aggregates in ONE place guarantees that FCFS, SJF, SRTF,
    Priority and Round Robin all use identical formulas.
    """
    rows: list[ProcessResult] = []
    for p in processes:
        ct = completion[p.pid]
        tat = ct - p.arrival
        rows.append(
            ProcessResult(
                pid=p.pid,
                arrival=p.arrival,
                burst=p.burst,
                priority=p.priority,
                completion=ct,
                turnaround=tat,
                waiting=tat - p.burst,
                response=first_start[p.pid] - p.arrival,
            )
        )

    n = len(rows)
    first_arrival = min(p.arrival for p in processes)
    last_completion = max(completion.values())
    total_time = last_completion - first_arrival          # schedule span
    busy_time = sum(p.burst for p in processes)           # CPU is busy exactly this long
    idle_time = total_time - busy_time

    return CpuScheduleResult(
        algorithm=algorithm,
        quantum=quantum,
        rows=rows,
        gantt=list(gantt),
        avg_waiting=sum(r.waiting for r in rows) / n,
        avg_turnaround=sum(r.turnaround for r in rows) / n,
        avg_response=sum(r.response for r in rows) / n,
        cpu_utilisation=(busy_time / total_time * 100.0) if total_time else 0.0,
        throughput=(n / total_time) if total_time else 0.0,
        total_time=total_time,
        idle_time=idle_time,
    )


def _append_segment(gantt: list[tuple[str, int, int]], pid: str, start: int, end: int) -> None:
    """Append a Gantt segment, merging it with the previous one if contiguous and equal.

    Merging keeps the timeline readable: two consecutive 3-unit slices of the
    same process would otherwise appear as two boxes.
    """
    if end <= start:
        return
    if gantt and gantt[-1][0] == pid and gantt[-1][2] == start:
        old_pid, old_start, _old_end = gantt[-1]
        gantt[-1] = (old_pid, old_start, end)
        return
    gantt.append((pid, start, end))


def _next_ready(procs: Sequence[Process], done: Sequence[bool], clock: int) -> list[int]:
    """Indices of unfinished processes that have arrived by ``clock``, in input order.

    Returning them in input order is what makes the tie-break (earlier arrival,
    then input order) fall out of ``min``'s stable behaviour.
    """
    return [i for i, p in enumerate(procs) if not done[i] and p.arrival <= clock]


def _run_non_preemptive(
    processes: Sequence[Process],
    algorithm: str,
    key: Callable[[Process], tuple],
) -> CpuScheduleResult:
    """Shared engine for FCFS, SJF and Priority (all non-preemptive).

    The loop never assumes a process is available: if the CPU is idle because
    every remaining process arrives later, the clock jumps forward and an IDLE
    segment is recorded. ``key`` ranks the ready processes; because the ready
    list is in input order and ``min`` keeps the first minimum, equal keys are
    resolved by the order the processes were supplied.

    The clock starts at the FIRST ARRIVAL, not at 0. Before any process has
    arrived the CPU is simply not part of the observed schedule, so the Gantt
    timeline never opens with an IDLE segment. This keeps ``gantt`` and
    ``idle_time`` consistent, because ``_build_result`` measures the schedule
    span from the first arrival and therefore counts only the idle time that
    happens BETWEEN arrivals (the wait for the first process is not idle time
    of a running system).
    """
    _validate(processes)
    procs = list(processes)
    n = len(procs)
    done = [False] * n
    completion: dict[str, int] = {}
    first_start: dict[str, int] = {}
    gantt: list[tuple[str, int, int]] = []

    clock = min(p.arrival for p in procs)   # timeline starts when work can exist
    for _ in range(n):
        ready = _next_ready(procs, done, clock)

        if not ready:                                    # CPU would idle until the next arrival
            next_arrival = min(procs[i].arrival for i in range(n) if not done[i])
            _append_segment(gantt, IDLE, clock, next_arrival)
            clock = next_arrival
            ready = _next_ready(procs, done, clock)

        idx = min(ready, key=lambda i: key(procs[i]))
        p = procs[idx]
        start = clock
        clock += p.burst
        completion[p.pid] = clock
        first_start[p.pid] = start
        _append_segment(gantt, p.pid, start, clock)
        done[idx] = True

    return _build_result(algorithm, procs, completion, first_start, gantt)


# ---------------------------------------------------------------------------
# 1. FCFS
# ---------------------------------------------------------------------------
def fcfs(processes: Sequence[Process]) -> CpuScheduleResult:
    """First Come First Serve — run processes in arrival order.

    Concept: the ready queue is a simple FIFO. A process that arrives first
    gets the CPU first and runs to completion.

    OS use: batch systems, printer queues, simple embedded schedulers; the
    baseline against which other algorithms are measured.

    Working principle: each dispatch picks the earliest-arrived ready process
    (equal arrival times are served in input order) and runs it to completion,
    jumping the clock forward when the CPU idles.

    Complexity: O(n^2) with a linear scan per dispatch (O(n log n) if the input
    is pre-sorted), O(n) space.

    Advantage: simplest possible, no starvation (everyone is served in turn).
    Disadvantage: the **convoy effect** — one long process delays every short
    process behind it, so average waiting time can be very poor.
    """
    return _run_non_preemptive(processes, "FCFS", key=lambda p: (p.arrival,))


# ---------------------------------------------------------------------------
# 2. SJF (non-preemptive)
# ---------------------------------------------------------------------------
def sjf(processes: Sequence[Process]) -> CpuScheduleResult:
    """Shortest Job First (non-preemptive) — run the shortest ready burst next.

    Concept: among the processes currently in the ready queue, the one with the
    smallest burst time runs to completion.

    OS use: long-term/medium-term scheduling of batch jobs where burst times
    are known or estimated (e.g. from historical averages).

    Working principle: at each dispatch point, pick ``min(burst)`` among the
    arrived-and-unfinished processes; if none has arrived, idle until the next
    arrival. Equal bursts are broken by earlier arrival, then input order.

    Complexity: O(n^2) with a linear scan per dispatch, O(n log n) with a heap,
    O(n) space.

    Advantage: **provably minimum average waiting time** for a given set of
    non-preemptive processes.
    Disadvantage: burst times are rarely known in advance; long jobs can
    starve because short jobs keep overtaking them.
    """
    return _run_non_preemptive(processes, "SJF", key=lambda p: (p.burst, p.arrival))


# ---------------------------------------------------------------------------
# 3. SRTF (preemptive SJF)
# ---------------------------------------------------------------------------
def srtf(processes: Sequence[Process]) -> CpuScheduleResult:
    """Shortest Remaining Time First — preemptive version of SJF.

    Concept: whenever a new process arrives, compare its burst with the
    *remaining* time of the running process; if the newcomer is shorter, it
    preempts the CPU immediately.

    OS use: interactive systems that favour short jobs (and modern Linux's
    CFS approximates the same idea through virtual runtime).

    Working principle: run the process with the smallest remaining time until
    it finishes **or** a new process arrives — whichever is sooner — then
    re-dispatch. Equal remaining times are broken by earlier arrival, then
    input order.

    Complexity: O(n^2) with a linear scan per dispatch (a heap gives
    O(n log n)), O(n) space.

    Advantage: lowest possible average waiting time among the five algorithms
    on typical datasets.
    Disadvantage: context-switch overhead from frequent preemption and
    starvation of long processes.
    """
    _validate(processes)
    procs = list(processes)
    remaining = {p.pid: p.burst for p in procs}

    completion: dict[str, int] = {}
    first_start: dict[str, int] = {}
    gantt: list[tuple[str, int, int]] = []

    clock = min(p.arrival for p in procs)

    while len(completion) < len(procs):
        ready = [p for p in procs if p.arrival <= clock and remaining[p.pid] > 0]

        if not ready:                                    # nothing runnable yet
            next_arrival = min(p.arrival for p in procs if remaining[p.pid] > 0)
            _append_segment(gantt, IDLE, clock, next_arrival)
            clock = next_arrival
            continue

        # smallest remaining time, ties resolved by arrival then input order
        current = min(ready, key=lambda p: (remaining[p.pid], p.arrival))

        # Run only until the next arrival so a shorter newcomer can preempt.
        future_arrivals = [p.arrival for p in procs if p.arrival > clock and remaining[p.pid] > 0]
        next_arrival = min(future_arrivals) if future_arrivals else None
        run_for = remaining[current.pid]
        if next_arrival is not None:
            run_for = min(run_for, next_arrival - clock)

        first_start.setdefault(current.pid, clock)

        _append_segment(gantt, current.pid, clock, clock + run_for)
        clock += run_for
        remaining[current.pid] -= run_for

        if remaining[current.pid] == 0:
            completion[current.pid] = clock

    return _build_result("SRTF", procs, completion, first_start, gantt)


# ---------------------------------------------------------------------------
# 4. Priority (non-preemptive)
# ---------------------------------------------------------------------------
def priority_scheduling(processes: Sequence[Process]) -> CpuScheduleResult:
    """Priority Scheduling (non-preemptive) — highest priority ready process runs.

    Concept: every process carries a priority; the ready process with the
    highest priority (smallest number here) is dispatched, and runs to
    completion.

    OS use: real-time systems, Windows thread priorities, Unix ``nice`` values.

    Working principle: identical to SJF but the selection key is ``priority``
    instead of ``burst``. Equal priorities are broken by earlier arrival, then
    input order.

    Complexity: O(n^2) time, O(n) space.

    Advantage: important work is not delayed by unimportant work.
    Disadvantage: **starvation** of low-priority processes — the classic cure
    is ageing (gradually raising the priority of waiting processes).
    """
    return _run_non_preemptive(
        processes, "PRIORITY", key=lambda p: (p.priority, p.arrival)
    )


# ---------------------------------------------------------------------------
# 5. Round Robin
# ---------------------------------------------------------------------------
def _enqueue_arrivals(
    queue: deque[Process], procs: Sequence[Process], start: int, clock: int
) -> int:
    """Append every process that has arrived by ``clock`` to ``queue``.

    Args:
        queue: the ready queue, modified in place.
        procs: processes sorted by arrival time.
        start: index in ``procs`` of the first process not yet queued.
        clock: current time.

    Returns:
        The new "first not yet queued" index.
    """
    i = start
    while i < len(procs) and procs[i].arrival <= clock:
        queue.append(procs[i])
        i += 1
    return i


def round_robin(processes: Sequence[Process], quantum: int = DEFAULT_QUANTUM) -> CpuScheduleResult:
    """Round Robin — cyclic execution with a fixed time quantum.

    Concept: the ready queue is a circle. Each process gets at most ``quantum``
    time units; if it is not finished, it goes to the back of the queue.

    OS use: time-sharing and interactive systems (the classic UNIX scheduler);
    the basis of most desktop schedulers.

    Working principle: run the head of the queue for ``min(quantum, remaining)``
    time, enqueue any processes that arrived during that slice, then re-enqueue
    the preempted process behind them. The clock starts at the first arrival
    (same rule as the non-preemptive engine), so the timeline has no leading
    IDLE gap and ``sum(IDLE segments) == idle_time``.

    Complexity: O(n + total_burst / quantum) dispatches, O(n) space.

    Advantage: **fairness** and excellent response time — no process waits
    long for its first slice, so there is no starvation.
    Disadvantage: throughput and average waiting time depend heavily on the
    quantum: too small means constant context switching, too large degenerates
    into FCFS.

    Args:
        quantum: time slice length, must be >= 1.

    Note: equal arrival times are queued in input order, and a process arriving
    exactly at the end of a slice is queued *before* the preempted process
    (standard textbook ordering).
    """
    _validate(processes)
    if not isinstance(quantum, int) or isinstance(quantum, bool):
        raise TypeError("quantum must be an integer")
    if quantum < 1:
        raise ValueError(f"quantum must be >= 1 (got {quantum})")

    # A stable sort keeps the input order for equal arrival times.
    procs = sorted(processes, key=lambda p: p.arrival)
    n = len(procs)
    remaining = {p.pid: p.burst for p in procs}
    completion: dict[str, int] = {}
    first_start: dict[str, int] = {}
    gantt: list[tuple[str, int, int]] = []

    queue: deque[Process] = deque()
    clock = procs[0].arrival                    # procs is sorted by arrival
    next_i = _enqueue_arrivals(queue, procs, 0, clock)

    while queue or next_i < n:
        if not queue:                                    # CPU idle until next arrival
            idle_start = clock
            clock = procs[next_i].arrival
            _append_segment(gantt, IDLE, idle_start, clock)
            next_i = _enqueue_arrivals(queue, procs, next_i, clock)
            continue

        current = queue.popleft()
        start = clock
        run_for = min(quantum, remaining[current.pid])
        clock += run_for
        remaining[current.pid] -= run_for

        # Arrivals during this slice are queued before the preempted process.
        next_i = _enqueue_arrivals(queue, procs, next_i, clock)

        first_start.setdefault(current.pid, start)
        _append_segment(gantt, current.pid, start, clock)

        if remaining[current.pid] > 0:
            queue.append(current)
        else:
            completion[current.pid] = clock

    return _build_result("RR", procs, completion, first_start, gantt, quantum=quantum)


# ---------------------------------------------------------------------------
# Registry and dispatcher
# ---------------------------------------------------------------------------
#: Names accepted by the menu / comparison layer.
ALGORITHMS: dict[str, Callable[..., CpuScheduleResult]] = {
    "FCFS": fcfs,
    "SJF": sjf,
    "SRTF": srtf,
    "PRIORITY": priority_scheduling,
    "RR": round_robin,
}


def run_algorithm(
    name: str, processes: Sequence[Process], quantum: int = DEFAULT_QUANTUM
) -> CpuScheduleResult:
    """Run one algorithm by name. Used by ``main.py`` and the comparison module.

    Args:
        name: one of ``FCFS, SJF, SRTF, PRIORITY, RR`` (case-insensitive).
        processes: the dataset.
        quantum: only used by RR.

    Raises:
        ValueError: unknown algorithm name.
    """
    key = name.strip().upper()
    if key not in ALGORITHMS:
        raise ValueError(
            f"unknown CPU algorithm {name!r}; choose from {', '.join(ALGORITHMS)}"
        )
    if key == "RR":
        return round_robin(processes, quantum=quantum)
    return ALGORITHMS[key](processes)


# ---------------------------------------------------------------------------
# Dataset loading (used by the demo below and later by main.py)
# ---------------------------------------------------------------------------
def parse_process_lines(lines: Iterable[str]) -> list[Process]:
    """Parse lines of ``pid arrival burst [priority]`` into Process objects.

    Blank lines and ``#`` comments are ignored. Fields may be separated by
    spaces, tabs or commas. Errors report the 1-based line number so a typo in
    a data file is easy to find.
    """
    processes: list[Process] = []
    for lineno, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.replace(",", " ").split()
        if len(fields) not in (3, 4):
            raise ValueError(
                f"line {lineno}: expected 'pid arrival burst [priority]', got {len(fields)} field(s)"
            )
        pid = fields[0]
        try:
            arrival = int(fields[1])
            burst = int(fields[2])
            priority = int(fields[3]) if len(fields) == 4 else 0
        except ValueError:
            raise ValueError(f"line {lineno}: arrival, burst and priority must be integers") from None
        processes.append(Process(pid=pid, arrival=arrival, burst=burst, priority=priority))
    return processes


def load_processes(path: str | Path) -> list[Process]:
    """Load a process dataset from a text file (see :func:`parse_process_lines`)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"dataset file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return parse_process_lines(fh)


# ---------------------------------------------------------------------------
# Standalone demo:  python3 -m modules.cpu_scheduling
# ---------------------------------------------------------------------------
def _format_gantt(gantt: Sequence[tuple[str, int, int]]) -> str:
    """Render the timeline as ``| P1 0-4 | IDLE 4-6 | ... |`` on one line."""
    return " | ".join(f"{pid} {start}-{end}" for pid, start, end in gantt)


def _print_result(res: CpuScheduleResult) -> None:
    """Minimal fixed-width table for the standalone demo (the app uses
    ``utils/report_generator.py`` instead)."""
    header = f"{'PID':<6}{'AT':>4}{'BT':>4}{'PRI':>5}{'CT':>5}{'TAT':>5}{'WT':>5}{'RT':>5}"
    print(f"  Algorithm: {res.algorithm}" + (f"  (quantum = {res.quantum})" if res.quantum else ""))
    print("  " + header)
    print("  " + "-" * len(header))
    for r in res.rows:
        print(
            f"  {r.pid:<6}{r.arrival:>4}{r.burst:>4}{r.priority:>5}"
            f"{r.completion:>5}{r.turnaround:>5}{r.waiting:>5}{r.response:>5}"
        )
    print("  " + "-" * len(header))
    print(f"  Avg Waiting: {res.avg_waiting:.2f}   Avg Turnaround: {res.avg_turnaround:.2f}"
          f"   Avg Response: {res.avg_response:.2f}")
    print(f"  CPU Utilisation: {res.cpu_utilisation:.2f}%   Throughput: {res.throughput:.4f} proc/unit"
          f"   Span: {res.total_time}   Idle: {res.idle_time}")
    print(f"  Gantt: {_format_gantt(res.gantt)}")


def _demo() -> None:
    root = Path(__file__).resolve().parent.parent
    for filename, quantum in (("cpu_sample.txt", 3), ("cpu_convoy.txt", 4)):
        path = root / "data" / filename
        if not path.is_file():
            print(f"[skip] {path} not found")
            continue
        processes = load_processes(path)
        print("=" * 78)
        print(f"Dataset: {filename}   ({len(processes)} processes, total burst "
              f"{sum(p.burst for p in processes)})")
        print("=" * 78)
        for name in ALGORITHMS:
            _print_result(run_algorithm(name, processes, quantum=quantum))
            print()
        print()


if __name__ == "__main__":
    _demo()
