"""
Deadlock Management module — OS Resource Management Simulator
=============================================================

Implements the three classic deadlock algorithms built on one shared state:

    SAFETY    Banker's safety algorithm  — is the current state safe?
    REQUEST   Banker's resource-request  — may a request be granted now?
    DETECT    Deadlock detection         — which processes are deadlocked?

Notation (Silberschatz):
    n = number of processes, m = number of resource types
    Allocation[i]  resources currently held by process i
    Max[i]         maximum claim process i announced at start-up
    Need[i]        Max[i] - Allocation[i]      (what i may still ask for)
    Available      resources currently free
    Work           a running copy of Available, used by SAFETY and DETECT
    Finish[i]      True once process i is known to be able to complete

Core invariant (checked at load time):
    Allocation[i][j] <= Max[i][j] for every i, j.

Design rules (from docs/PHASE1_SYSTEM_DESIGN.md):
  * Pure functions: no input(), no print(), no file paths.
  * Results are dataclasses carrying a step-by-step trace of ``Work``, so the
    report can print exactly how a verdict was reached (needed for viva).
  * Invalid input (wrong dimensions, negative counts, allocation above the
    maximum claim) raises ValueError / TypeError instead of returning a
    meaningless verdict; the menu decides how to display the message.

A deadlock is a set of processes each waiting for a resource held by another
member of the set. Banker's algorithm avoids deadlock by refusing requests that
would leave no safe sequence; detection asks the same question about an
*existing* state, where the outstanding requests are already fixed.

Academic notes are in each function's docstring.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "BankersState",
    "SafetyStep",
    "SafetyResult",
    "RequestResult",
    "DetectionStep",
    "DetectionResult",
    "make_state",
    "check_safety",
    "request_resources",
    "detect_deadlock",
    "parse_deadlock_lines",
    "load_deadlock_dataset",
]

#: Resource-type labels used when a dataset does not name them.
DEFAULT_RESOURCES = ("A", "B", "C", "D", "E", "F", "G", "H")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
Vector = tuple[int, ...]
Matrix = tuple[Vector, ...]


@dataclass(frozen=True)
class BankersState:
    """One resource-allocation state.

    Attributes:
        pids:      Process identifiers, in the order rows are indexed.
        allocation: ``allocation[i][j]`` = units of resource j held by process i.
        maximum:   ``maximum[i][j]``    = maximum claim of process i for resource j.
        available: ``available[j]``     = units of resource j currently free.

    ``need`` is derived, never stored, so the three matrices can never drift
    apart (Need = Max - Allocation by definition).
    """

    pids: tuple[str, ...]
    allocation: Matrix
    maximum: Matrix
    available: Vector

    @property
    def need(self) -> Matrix:
        """``Max - Allocation`` for every process and resource type."""
        return tuple(
            tuple(mx - al for mx, al in zip(max_row, alloc_row))
            for alloc_row, max_row in zip(self.allocation, self.maximum)
        )

    @property
    def resource_count(self) -> int:
        """Number of resource types (``m``)."""
        return len(self.available)

    @property
    def total_resources(self) -> Vector:
        """Total units of each resource in the system (Available + all allocated)."""
        return tuple(
            self.available[j] + sum(row[j] for row in self.allocation)
            for j in range(self.resource_count)
        )

    def allocation_of(self, pid: str) -> Vector:
        """The Allocation row of ``pid``."""
        return self.allocation[self._index(pid)]

    def _index(self, pid: str) -> int:
        try:
            return self.pids.index(pid)
        except ValueError:
            raise ValueError(
                f"unknown process {pid!r}; known processes: {', '.join(self.pids)}"
            ) from None


@dataclass
class SafetyStep:
    """One successful iteration of the safety loop (one process can finish)."""

    pid: str
    work_before: Vector
    need: Vector
    work_after: Vector


@dataclass
class SafetyResult:
    """Verdict of the safety algorithm plus the trace that produced it.

    ``sequence`` is a safe sequence when ``safe`` is True, otherwise empty.
    ``stuck`` lists the processes that could not finish; for an unsafe state it
    is the deadlocked set implied by the remaining claims.
    """

    safe: bool
    sequence: list[str]
    steps: list[SafetyStep]
    stuck: list[str]

    @property
    def summary(self) -> str:
        """One-line human-readable verdict, e.g. ``SAFE: P1 -> P3 -> ...``."""
        if self.safe:
            return "SAFE: " + " -> ".join(self.sequence)
        return "UNSAFE: no safe sequence; stuck processes: " + ", ".join(self.stuck)


@dataclass
class RequestResult:
    """Verdict of the resource-request algorithm.

    ``state`` is the state *after* a granted request (None when refused), and
    ``safety`` is the safety check of that would-be state (None when the request
    was refused before any check, i.e. it simply exceeds what is available).
    """

    pid: str
    request: Vector
    granted: bool
    reason: str
    state: BankersState | None
    safety: SafetyResult | None


@dataclass
class DetectionStep:
    """One successful iteration of the detection loop."""

    pid: str
    work_before: Vector
    request: Vector
    work_after: Vector


@dataclass
class DetectionResult:
    """Which processes are deadlocked, and the trace proving it.

    ``requests`` is the matrix that was actually used (``request_source`` says
    whether it came from the dataset or from Need), so the report can print the
    exact input behind the verdict.
    """

    deadlocked: list[str]
    order: list[str]
    steps: list[DetectionStep]
    requests: Matrix
    request_source: str

    @property
    def summary(self) -> str:
        """One-line verdict, e.g. ``DEADLOCK: P1, P2`` or ``NO DEADLOCK``."""
        if self.deadlocked:
            return "DEADLOCK: " + ", ".join(self.deadlocked)
        return "NO DEADLOCK"


# ---------------------------------------------------------------------------
# Validation and construction
# ---------------------------------------------------------------------------
def _as_vector(values: Sequence[int], what: str) -> Vector:
    """Convert to a tuple of non-negative ints, naming ``what`` in errors."""
    if isinstance(values, (str, bytes)) or not isinstance(values, Sequence):
        raise TypeError(f"{what} must be a sequence of integers")
    out: list[int] = []
    for v in values:
        if not isinstance(v, int) or isinstance(v, bool):
            raise TypeError(f"{what} must contain integers only (got {v!r})")
        if v < 0:
            raise ValueError(f"{what} must not contain negative values (got {v})")
        out.append(v)
    return tuple(out)


def make_state(
    pids: Sequence[str],
    allocation: Sequence[Sequence[int]],
    maximum: Sequence[Sequence[int]],
    available: Sequence[int],
) -> BankersState:
    """Build a validated :class:`BankersState`.

    Args:
        pids: unique process identifiers, one per matrix row.
        allocation: n x m matrix of currently held resources.
        maximum: n x m matrix of announced maximum claims.
        available: m free units per resource type.

    Raises:
        TypeError:  wrong container types or non-integer entries.
        ValueError: empty input, duplicate pid, wrong dimensions, or
                    ``allocation[i][j] > maximum[i][j]`` (impossible state).
    """
    pid_list = list(pids)
    if not pid_list:
        raise ValueError("process list is empty; provide at least one process")
    if len(set(pid_list)) != len(pid_list):
        raise ValueError("process ids must be unique")
    if any(not isinstance(pid, str) or not pid for pid in pid_list):
        raise TypeError("process ids must be non-empty strings")

    avail = _as_vector(available, "available")
    if not avail:
        raise ValueError("available vector is empty; provide at least one resource type")
    m = len(avail)
    n = len(pid_list)

    alloc_rows = [_as_vector(row, f"allocation row for {pid}") for pid, row in zip(pid_list, allocation)]
    max_rows = [_as_vector(row, f"max row for {pid}") for pid, row in zip(pid_list, maximum)]

    if len(alloc_rows) != n or len(max_rows) != n:
        raise ValueError(
            f"expected {n} rows in both allocation and max, "
            f"got {len(alloc_rows)} and {len(max_rows)}"
        )
    for pid, arow, mrow in zip(pid_list, alloc_rows, max_rows):
        if len(arow) != m or len(mrow) != m:
            raise ValueError(
                f"{pid}: expected {m} resource columns, got {len(arow)} in allocation "
                f"and {len(mrow)} in max"
            )
        for j, (held, claim) in enumerate(zip(arow, mrow)):
            if held > claim:
                raise ValueError(
                    f"{pid}: allocation of resource {j} ({held}) exceeds its maximum "
                    f"claim ({claim}) — the state is impossible"
                )

    return BankersState(
        pids=tuple(pid_list),
        allocation=tuple(alloc_rows),
        maximum=tuple(max_rows),
        available=avail,
    )


def _validate(state: BankersState) -> None:
    """Re-check a state that the caller may have built by hand."""
    if not isinstance(state, BankersState):
        raise TypeError(f"expected BankersState, got {type(state).__name__}")
    rebuilt = make_state(state.pids, state.allocation, state.maximum, state.available)
    if rebuilt != state:                       # defensive: catches hand-edited tuples
        raise ValueError("inconsistent BankersState")


def _leq(a: Sequence[int], b: Sequence[int]) -> bool:
    """True when every component of ``a`` is <= the matching component of ``b``."""
    return all(x <= y for x, y in zip(a, b))


def _add(a: Sequence[int], b: Sequence[int]) -> Vector:
    """Component-wise sum of two resource vectors."""
    return tuple(x + y for x, y in zip(a, b))


def _sub(a: Sequence[int], b: Sequence[int]) -> Vector:
    """Component-wise difference of two resource vectors."""
    return tuple(x - y for x, y in zip(a, b))


# ---------------------------------------------------------------------------
# 1. Banker's safety algorithm
# ---------------------------------------------------------------------------
def check_safety(state: BankersState) -> SafetyResult:
    """Banker's safety algorithm — decide whether ``state`` is safe.

    Concept: a state is **safe** if there exists an ordering of ALL processes
    such that each one can obtain its remaining need from the resources that
    are free plus the resources released by the processes before it. If such an
    ordering exists, the system can promise every process eventual completion,
    so no deadlock can occur if allocations follow the Max claims.

    Algorithm (Silberschatz, "Deadlock Avoidance"):
        1. Work = Available; Finish[i] = False for all i.
        2. Find an i with Finish[i] == False and Need[i] <= Work.
           If there is none, go to step 4.
        3. Work = Work + Allocation[i]; Finish[i] = True; record i; repeat 2.
        4. Safe if Finish[i] == True for all i, otherwise unsafe.

    Working principle here: each pass scans the processes in index order and
    grants the first one whose need fits, then continues from the next index;
    further passes catch processes that only became satisfiable later (the
    vector Work only grows). The resulting sequence is *a* safe sequence — the
    safe sequence is generally not unique.

    Complexity: O(n^2 * m) time (n passes over n processes, each comparison
    costs m), O(n + m) extra space.

    Viva point: "safe" does not mean "no deadlock right now" — it means the
    system can still guarantee completion. Banker's never lets the state become
    unsafe, so it never deadlocks; that costs it concurrency (it may refuse a
    request that would have worked out fine in practice).
    """
    _validate(state)
    n = len(state.pids)
    need = state.need

    work = list(state.available)
    finish = [False] * n
    sequence: list[str] = []
    steps: list[SafetyStep] = []

    progressed = True
    while progressed:
        progressed = False
        for i in range(n):
            if finish[i] or not _leq(need[i], work):
                continue
            before = tuple(work)
            work = list(_add(work, state.allocation[i]))
            finish[i] = True
            sequence.append(state.pids[i])
            steps.append(SafetyStep(state.pids[i], before, need[i], tuple(work)))
            progressed = True

    safe = all(finish)
    stuck = [state.pids[i] for i in range(n) if not finish[i]]
    return SafetyResult(safe=safe, sequence=sequence, steps=steps, stuck=stuck)


# ---------------------------------------------------------------------------
# 2. Banker's resource-request algorithm
# ---------------------------------------------------------------------------
def request_resources(state: BankersState, pid: str, request: Sequence[int]) -> RequestResult:
    """Banker's resource-request algorithm — may ``pid`` be given ``request``?

    Textbook rules (Silberschatz), in order:
        1. If Request_i > Need_i  -> error: the process exceeded its claim.
        2. If Request_i <= Available -> pretend to allocate and check safety:
              Available -= Request_i
              Allocation_i += Request_i
              Need_i -= Request_i
           If the resulting state is safe, grant; otherwise restore and make the
           process wait.
        3. If Request_i > Available, the process must wait (resources are held
           by others).  This module also runs the safety check in that case, so
           the report can show whether waiting is enough or the state is
           already unsafe.

    Args:
        state:   current state.
        pid:     process making the request.
        request: m resource units requested, non-negative.

    Returns:
        :class:`RequestResult`; ``granted`` is True only when the request fits
        the claim, fits Available, and leaves a safe state.

    Raises:
        ValueError: unknown pid, wrong vector length, request above the
                    process's remaining need, or a state that fails validation.

    Complexity: O(n^2 * m) — dominated by the safety check.

    Viva point: refusing a request is not a failure of the algorithm; it is the
    avoidance mechanism working. The refused request is retried later, when
    other processes have released resources.
    """
    _validate(state)
    idx = state._index(pid)
    need = state.need[idx]
    req = _as_vector(request, f"request of {pid}")

    if len(req) != state.resource_count:
        raise ValueError(
            f"{pid}: request must have {state.resource_count} component(s), got {len(req)}"
        )
    if not _leq(req, need):
        raise ValueError(
            f"{pid}: request {req} exceeds the remaining need {need} "
            f"(a process may not exceed its maximum claim)"
        )

    if not _leq(req, state.available):
        return RequestResult(
            pid=pid,
            request=req,
            granted=False,
            reason=(
                f"request {req} exceeds available {state.available}; "
                f"{pid} must wait until enough resources are released"
            ),
            state=None,
            safety=None,
        )

    # Pretend to satisfy the request, then ask whether the result is safe.
    trial_alloc = list(state.allocation)
    trial_alloc[idx] = _add(trial_alloc[idx], req)
    trial = BankersState(
        pids=state.pids,
        allocation=tuple(trial_alloc),
        maximum=state.maximum,
        available=_sub(state.available, req),
    )
    safety = check_safety(trial)

    if safety.safe:
        return RequestResult(
            pid=pid,
            request=req,
            granted=True,
            reason=f"granted: the resulting state is safe ({safety.summary})",
            state=trial,
            safety=safety,
        )
    return RequestResult(
        pid=pid,
        request=req,
        granted=False,
        reason=(
            f"denied: granting {req} to {pid} would leave the system unsafe "
            f"({safety.summary}); the request is rolled back"
        ),
        state=None,
        safety=safety,
    )


# ---------------------------------------------------------------------------
# 3. Deadlock detection
# ---------------------------------------------------------------------------
def detect_deadlock(
    state: BankersState, requests: Sequence[Sequence[int]] | None = None
) -> DetectionResult:
    """Deadlock detection — which processes can never finish?

    Concept: unlike Banker's, this algorithm runs on a state that already
    exists. ``Request[i]`` is what process i is waiting for *right now*, not its
    whole future claim, so it is far more permissive than the safety check.

    Algorithm (Silberschatz, "Deadlock Detection"):
        1. Work = Available.
           Finish[i] = True for processes holding nothing (they cannot be
           waiting for a resource they do not hold), else False.
        2. Find i with Finish[i] == False and Request[i] <= Work.
           If none, go to step 4.
        3. Work = Work + Allocation[i]; Finish[i] = True; repeat 2.
        4. Any process with Finish[i] == False is deadlocked.

    Args:
        state:    current state (Allocation, Max, Available).
        requests: n x m outstanding requests. When omitted, ``Request = Need``
                  is used — the textbook fallback that answers "if every process
                  asked for everything it may still ask for, would it deadlock?".

    Returns:
        :class:`DetectionResult` with the deadlocked processes, the order in
        which the others could finish, and the Work trace.

    Raises:
        ValueError: wrong request dimensions or a request above the process's
                    remaining need.

    Complexity: O(n^2 * m) time, O(n + m) space.

    Viva point: with single instances of each resource type, detection is a
    cycle in the wait-for graph; with multiple instances (as here) it is this
    reduction instead, because a cycle alone is not sufficient for deadlock.
    """
    _validate(state)
    n = len(state.pids)
    m = state.resource_count

    if requests is None:
        req_matrix: Matrix = state.need
        source = "Need (Max - Allocation)"
    else:
        rows = [_as_vector(row, f"request row for {pid}") for pid, row in zip(state.pids, requests)]
        if len(rows) != n:
            raise ValueError(f"expected {n} request rows, got {len(rows)}")
        for pid, row, need in zip(state.pids, rows, state.need):
            if len(row) != m:
                raise ValueError(f"{pid}: request row must have {m} component(s), got {len(row)}")
            if not _leq(row, need):
                raise ValueError(f"{pid}: outstanding request {row} exceeds its remaining need {need}")
        req_matrix = tuple(rows)
        source = "supplied Request matrix"

    work = list(state.available)
    finish = [all(units == 0 for units in row) for row in state.allocation]
    order: list[str] = []
    steps: list[DetectionStep] = []

    progressed = True
    while progressed:
        progressed = False
        for i in range(n):
            if finish[i] or not _leq(req_matrix[i], work):
                continue
            before = tuple(work)
            work = list(_add(work, state.allocation[i]))
            finish[i] = True
            order.append(state.pids[i])
            steps.append(DetectionStep(state.pids[i], before, req_matrix[i], tuple(work)))
            progressed = True

    deadlocked = [state.pids[i] for i in range(n) if not finish[i]]
    return DetectionResult(
        deadlocked=deadlocked,
        order=order,
        steps=steps,
        requests=req_matrix,
        request_source=source,
    )


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def parse_deadlock_lines(lines: Iterable[str]) -> BankersState:
    """Parse a Banker's dataset from text.

    Format (``#`` starts a comment; commas are treated as spaces)::

        processes P0 P1 P2 P3 P4
        resources A B C
        available 3 3 2

        allocation
        P0 0 1 0
        ...

        max
        P0 7 5 3
        ...

    ``processes`` and ``resources`` are optional labels; rows are matched to
    processes by pid, so the row order inside a section does not matter.
    Errors report the 1-based line number.
    """
    pids: list[str] = []
    resource_names: list[str] = []
    available: list[int] | None = None
    sections: dict[str, dict[str, list[int]]] = {"allocation": {}, "max": {}}
    section: str | None = None

    for lineno, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.replace(",", " ").replace(":", " ").split()
        key = fields[0].lower()

        if key == "processes":
            pids = fields[1:]
            if not pids:
                raise ValueError(f"line {lineno}: 'processes' needs at least one pid")
            continue
        if key == "resources":
            resource_names = fields[1:]
            continue
        if key == "available":
            try:
                available = [int(v) for v in fields[1:]]
            except ValueError:
                raise ValueError(f"line {lineno}: available values must be integers") from None
            if not available:
                raise ValueError(f"line {lineno}: 'available' needs at least one value")
            continue
        if key in ("allocation", "max"):
            section = key
            if len(fields) > 1:                    # allow "allocation P0 0 1 0" on one line
                _store_row(sections[section], fields[1:], lineno, section)
            continue

        if section is None:
            raise ValueError(
                f"line {lineno}: expected 'processes', 'resources', 'available', "
                f"'allocation' or 'max' first, got {fields[0]!r}"
            )
        _store_row(sections[section], fields, lineno, section)

    if available is None:
        raise ValueError("dataset is missing the 'available' line")
    if not pids:
        raise ValueError("dataset is missing the 'processes' line")
    m = len(available)
    if resource_names and len(resource_names) != m:
        raise ValueError(
            f"'resources' lists {len(resource_names)} name(s) but 'available' has {m} value(s)"
        )

    def matrix_for(name: str) -> list[list[int]]:
        rows = sections[name]
        missing = [pid for pid in pids if pid not in rows]
        extra = [pid for pid in rows if pid not in pids]
        if missing or extra:
            detail = []
            if missing:
                detail.append(f"missing rows for {', '.join(missing)}")
            if extra:
                detail.append(f"unknown process id(s) {', '.join(extra)}")
            raise ValueError(f"'{name}' section: " + "; ".join(detail))
        return [rows[pid] for pid in pids]

    return make_state(pids, matrix_for("allocation"), matrix_for("max"), available)


def _store_row(target: dict[str, list[int]], fields: Sequence[str], lineno: int, section: str) -> None:
    """Store one ``pid v1 v2 ...`` row, validating the numbers."""
    if len(fields) < 2:
        raise ValueError(f"line {lineno}: expected 'pid' followed by resource values")
    pid = fields[0]
    try:
        values = [int(v) for v in fields[1:]]
    except ValueError:
        raise ValueError(f"line {lineno}: resource values must be integers") from None
    if pid in target:
        raise ValueError(f"line {lineno}: duplicate row for {pid} in '{section}'")
    target[pid] = values


def load_deadlock_dataset(path: str | Path) -> BankersState:
    """Load a Banker's dataset from a text file (see :func:`parse_deadlock_lines`)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"dataset file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return parse_deadlock_lines(fh)


# ---------------------------------------------------------------------------
# Standalone demo:  python3 modules/deadlock_management.py
# ---------------------------------------------------------------------------
def _fmt(values: Sequence[int]) -> str:
    """``(3, 3, 2)`` — compact vector for the trace tables."""
    return "(" + ", ".join(str(v) for v in values) + ")"


def _print_state(state: BankersState) -> None:
    """Print Allocation, Max and the derived Need in one aligned table."""
    need = state.need
    header = f"  {'PID':<5}{'Allocation':>14}{'Max':>14}{'Need':>14}"
    print(header)
    print("  " + "-" * (len(header) - 2))
    for i, pid in enumerate(state.pids):
        print(f"  {pid:<5}{_fmt(state.allocation[i]):>14}{_fmt(state.maximum[i]):>14}{_fmt(need[i]):>14}")
    print("  " + "-" * (len(header) - 2))
    print(f"  Available: {_fmt(state.available)}    Total resources: {_fmt(state.total_resources)}")


def _demo() -> None:
    root = Path(__file__).resolve().parent.parent
    sample = root / "data" / "deadlock_sample.txt"
    unsafe = root / "data" / "deadlock_unsafe.txt"

    if sample.is_file():
        state = load_deadlock_dataset(sample)
        print("=" * 78)
        print(f"Dataset: deadlock_sample.txt   ({len(state.pids)} processes, "
              f"{state.resource_count} resource types)")
        print("=" * 78)
        _print_state(state)

        print("\n  -- Banker's safety algorithm --")
        safety = check_safety(state)
        work_header = f"  {'PID':<5}{'Work':>12}{'Need':>12}{'Work + Allocation':>22}"
        print(work_header)
        print("  " + "-" * (len(work_header) - 2))
        for step in safety.steps:
            print(f"  {step.pid:<5}{_fmt(step.work_before):>12}{_fmt(step.need):>12}"
                  f"{_fmt(step.work_after):>22}")
        print("  " + "-" * (len(work_header) - 2))
        print(f"  Verdict: {safety.summary}")

        print("\n  -- Banker's resource-request algorithm --")
        for pid, req in (("P1", (1, 0, 2)), ("P4", (3, 3, 0))):
            result = request_resources(state, pid, req)
            print(f"  {pid} requests {_fmt(req)}: {'GRANTED' if result.granted else 'REFUSED'}")
            print(f"    {result.reason}")

        print("\n  -- Deadlock detection (Request = Need) --")
        detection = detect_deadlock(state)
        for step in detection.steps:
            print(f"  {step.pid:<5} Work {_fmt(step.work_before)} + Alloc"
                  f" -> {_fmt(step.work_after)}   (Request {_fmt(step.request)} <= Work)")
        print(f"  Finish order: {' -> '.join(detection.order) if detection.order else '(none)'}")
        print(f"  Verdict: {detection.summary}")
        print()

    if unsafe.is_file():
        state = load_deadlock_dataset(unsafe)
        print("=" * 78)
        print(f"Dataset: deadlock_unsafe.txt   ({len(state.pids)} processes, "
              f"{state.resource_count} resource types)")
        print("=" * 78)
        _print_state(state)
        safety = check_safety(state)
        print(f"\n  Safety verdict: {safety.summary}")
        detection = detect_deadlock(state)
        print(f"  Detection (Request = Need): {detection.summary}")
        print(f"    Finish order: {' -> '.join(detection.order) if detection.order else '(none)'}")
        print(f"    Work trace: {len(detection.steps)} process(es) could finish;"
              f" the rest can never proceed")


if __name__ == "__main__":
    _demo()
