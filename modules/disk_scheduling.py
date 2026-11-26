"""
Disk Scheduling module — OS Resource Management Simulator
=========================================================

Implements the four disk-head scheduling algorithms from the syllabus:

    FCFS    First Come First Serve   — serve requests in arrival order
    SSTF    Shortest Seek Time First — serve the nearest cylinder next
    SCAN    Elevator algorithm       — sweep to the end, then reverse
    CSCAN   Circular SCAN            — sweep to the end, jump back, sweep again

Model used here:

    * The disk has ``disk_size`` cylinders numbered ``0 .. disk_size - 1``.
    * ``head`` is the cylinder the head sits on when the queue is read.
    * A *movement* is one head move from the current cylinder to the next
      served cylinder. Its length in cylinders is that movement's seek cost.
    * ``total_movement`` is the sum of all movement lengths (total seek
      distance). ``average_movement`` is ``total_movement / number of
      requests``, i.e. the average seek distance per request.

Convention for the circular algorithms (stated so the marks do not depend on
an unstated assumption):

    * SCAN and C-SCAN travel all the way to the last cylinder (or cylinder 0
      when moving down) even if no request sits there, because that is what a
      real elevator does. That boundary travel IS counted in the total and is
      shown with the note ``boundary``.
    * C-SCAN's fast return from the last cylinder to cylinder 0 is a seek that
      is not part of the sweep, so it is recorded separately in
      ``return_jump`` and is NOT counted in ``total_movement``. Both numbers
      are printed, so a marker who prefers to count it can see the value.

Design rules (from docs/PHASE1_SYSTEM_DESIGN.md):
  * Pure functions: ``(requests, head, ...) -> DiskResult``. No input(), no
    print(), no file paths.
  * All four algorithms return the same result type, so the comparison layer
    has no special cases.
  * Tie-break: SSTF picks the smallest cylinder when two are equally far
    (deterministic, NFR-9). Equal cylinders in the request list are served in
    the order supplied.
  * Invalid input raises ValueError / TypeError; the menu displays the message.

Academic notes (concept, OS use, complexity, viva point) are in each
algorithm's docstring.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Movement",
    "DiskResult",
    "ALGORITHMS",
    "DEFAULT_DISK_SIZE",
    "DIRECTIONS",
    "fcfs",
    "sstf",
    "scan",
    "cscan",
    "run_algorithm",
    "parse_disk_lines",
    "load_disk_dataset",
]

#: Cylinders 0..199 unless a dataset says otherwise (the textbook range).
DEFAULT_DISK_SIZE = 200

#: Head travel directions accepted by SCAN / C-SCAN.
DIRECTIONS = ("up", "down")

#: A scheduled stop: the cylinder and what happened there.
#:   "request" — a request was served (goes into ``order``)
#:   "travel"  — counted head travel to an end-of-disk turning point
#:   "jump"    — an uncounted reposition (C-SCAN's fast return)
Stop = tuple[int, str]


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Movement:
    """One head movement.

    Attributes:
        start:    cylinder the head left.
        end:      cylinder it arrived at.
        distance: ``abs(end - start)`` — the seek cost of this movement.
        is_boundary: True when ``end`` is an end-of-disk turning point that was
                     not itself a request (SCAN bounce / end of a C-SCAN sweep).
    """

    start: int
    end: int
    distance: int
    is_boundary: bool = False


@dataclass
class DiskResult:
    """Everything one disk algorithm produced for one dataset.

    ``order`` is the sequence of cylinders actually served (duplicates kept),
    ``movements`` is the full head path including boundary travel, and
    ``return_jump`` is C-SCAN's uncounted jump back to cylinder 0 (0 for the
    other algorithms).
    """

    algorithm: str
    head: int
    disk_size: int
    direction: str | None
    order: list[int]
    movements: list[Movement]
    return_jump: int
    requests: list[int]

    @property
    def total_movement(self) -> int:
        """Total seek distance in cylinders (boundary travel included)."""
        return sum(m.distance for m in self.movements)

    @property
    def request_movements(self) -> list[Movement]:
        """Only the movements that ended on a requested cylinder."""
        return [m for m in self.movements if not m.is_boundary]

    @property
    def average_movement(self) -> float:
        """Average seek distance per request: ``total_movement / len(requests)``."""
        return self.total_movement / len(self.requests) if self.requests else 0.0

    @property
    def positions(self) -> list[int]:
        """Head path as cylinder numbers, starting at the initial head."""
        return [self.head] + [m.end for m in self.movements]

    @property
    def sequence_text(self) -> str:
        """``53 -> 65 -> 67 -> ...`` for quick printing."""
        return " -> ".join(str(c) for c in self.positions)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _check_int(value: object, what: str, low: int, high: int) -> int:
    """Return ``value`` if it is an int in ``[low, high]``, else raise.

    ``bool`` is rejected on purpose: ``True`` would silently pass as 1.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{what} must be an integer (got {type(value).__name__})")
    if value < low or value > high:
        raise ValueError(f"{what} must be between {low} and {high} (got {value})")
    return value


def _validate(
    requests: Sequence[int],
    head: int,
    disk_size: int,
    direction: str | None = None,
) -> list[int]:
    """Validate a disk dataset and return the requests as a plain list.

    Raises:
        TypeError:  requests not a sequence of ints, or a bool passed as an int.
        ValueError: empty request list, a cylinder outside the disk, a head
                    outside the disk, a disk smaller than 2 cylinders, or an
                    unknown direction.
    """
    if not isinstance(disk_size, int) or isinstance(disk_size, bool):
        raise TypeError("disk_size must be an integer")
    if disk_size < 2:
        raise ValueError(f"disk_size must be >= 2 cylinders (got {disk_size})")
    _check_int(head, "head position", 0, disk_size - 1)

    if not isinstance(requests, Sequence) or isinstance(requests, (str, bytes)):
        raise TypeError("requests must be a sequence of integers")
    if len(requests) == 0:
        raise ValueError("request list is empty; provide at least one cylinder")
    for i, cylinder in enumerate(requests):
        _check_int(cylinder, f"request {i} ({cylinder})", 0, disk_size - 1)

    if direction is not None and direction not in DIRECTIONS:
        raise ValueError(
            f"unknown direction {direction!r}; choose from {', '.join(DIRECTIONS)}"
        )
    return list(requests)


# ---------------------------------------------------------------------------
# Result assembly
# ---------------------------------------------------------------------------
def _build_result(
    algorithm: str,
    requests: Sequence[int],
    head: int,
    disk_size: int,
    stops: Sequence[Stop],
    direction: str | None = None,
    return_jump: int = 0,
) -> DiskResult:
    """Turn a list of scheduled stops into the public result.

    Starting from ``head``, every stop becomes one :class:`Movement` except a
    ``"jump"`` stop, which repositions the head without adding seek distance
    (C-SCAN's fast return). Only ``"request"`` stops are added to ``order``.
    """
    movements: list[Movement] = []
    order: list[int] = []
    position = head
    for cylinder, kind in stops:
        if kind == "jump":                       # teleport: no distance recorded
            position = cylinder
            continue
        if cylinder != position:
            movements.append(
                Movement(position, cylinder, abs(cylinder - position), kind != "request")
            )
            position = cylinder
        if kind == "request":
            order.append(cylinder)
    return DiskResult(
        algorithm=algorithm,
        head=head,
        disk_size=disk_size,
        direction=direction,
        order=order,
        movements=movements,
        return_jump=return_jump,
        requests=list(requests),
    )


# ---------------------------------------------------------------------------
# 1. FCFS
# ---------------------------------------------------------------------------
def fcfs(
    requests: Sequence[int], head: int, disk_size: int = DEFAULT_DISK_SIZE
) -> DiskResult:
    """FCFS — serve the requests in the order they arrived.

    Concept: the queue is served front to back, exactly like a FIFO queue in
    memory management. No reordering happens, so the disk head follows the
    arrival pattern across the surface.

    OS use: the simplest policy, and the only one that is inherently fair
    (no starvation). Real systems use it for very light or sequential loads.

    Working principle: seek from the current position to request 1, then from
    request 1 to request 2, and so on. Total seek = sum of consecutive
    absolute differences.

    Complexity: O(n) time, O(n) space to record the trace.

    Advantage: fair, trivial to implement, no starvation.
    Disadvantage: ignores locality, so the head zig-zags and total seek
    distance is usually the largest of the four — the sample dataset shows
    640 cylinders versus 236 for SSTF.
    """
    reqs = _validate(requests, head, disk_size)
    return _build_result("FCFS", reqs, head, disk_size, [(c, "request") for c in reqs])


# ---------------------------------------------------------------------------
# 2. SSTF
# ---------------------------------------------------------------------------
def sstf(
    requests: Sequence[int], head: int, disk_size: int = DEFAULT_DISK_SIZE
) -> DiskResult:
    """SSTF — always serve the request closest to the current head position.

    Concept: shortest seek time first. At every step the head moves to the
    nearest pending cylinder, which is the disk analogue of SJF.

    OS use: common in older disk controllers and in teaching; real drives
    approximate it with elevator variants because pure SSTF starves far-away
    requests.

    Working principle: repeatedly pick ``min(pending, key=(|c - position|, c))``.
    The smallest-cylinder tie-break keeps the output deterministic when two
    requests are equally far away.

    Complexity: O(n^2) time (a scan of the pending list per request), O(n) space.

    Advantage: the shortest total seek distance of the four on most workloads;
    on the sample it is 236 cylinders.
    Disadvantage: **starvation** — a stream of nearby requests can postpone a
    far cylinder indefinitely. Also the head can keep reversing direction,
    which costs rotational latency in a real drive.
    """
    reqs = _validate(requests, head, disk_size)
    pending = list(reqs)
    position = head
    stops: list[Stop] = []

    while pending:
        # nearest first, then smallest cylinder for a deterministic tie-break
        chosen = min(pending, key=lambda c: (abs(c - position), c))
        stops.append((chosen, "request"))
        position = chosen
        pending.remove(chosen)          # removes one occurrence only

    return _build_result("SSTF", reqs, head, disk_size, stops)


# ---------------------------------------------------------------------------
# 3. SCAN (elevator)
# ---------------------------------------------------------------------------
def scan(
    requests: Sequence[int],
    head: int,
    disk_size: int = DEFAULT_DISK_SIZE,
    direction: str = "up",
) -> DiskResult:
    """SCAN — sweep in one direction, then reverse at the end of the disk.

    Concept: like an elevator. The head keeps moving in one direction and
    serves every request it passes; when it reaches the last cylinder it
    reverses and serves the rest on the way back.

    OS use: the classic elevator algorithm, the basis of real disk firmware
    (with LOOK/C-LOOK variants that turn around at the last request instead of
    the disk edge).

    Working principle (``direction="up"``):
        serve all requests >= head in ascending order, travel to
        ``disk_size - 1``, then serve the remaining requests in descending
        order. ``direction="down"`` mirrors this through cylinder 0.

    Complexity: O(n log n) time (one sort), O(n) space.

    Advantage: much less head movement than FCFS (331 vs 640 on the sample)
    and no starvation — every request is served within one sweep.
    Disadvantage: the head always travels to the disk edge even when the last
    request is far from it, and cylinders near the middle are visited more
    often than cylinders near the edges (the classic SCAN unfairness).
    """
    reqs = _validate(requests, head, disk_size, direction)
    above = sorted(c for c in reqs if c >= head)
    below = sorted((c for c in reqs if c < head), reverse=True)
    stops: list[Stop] = []

    if direction == "up":
        first, rest = above, below
        boundary = disk_size - 1
    else:
        first, rest = below, above
        boundary = 0

    for cylinder in first:
        stops.append((cylinder, "request"))

    if rest:
        # Travel to the edge, then reverse. The edge itself is not a request.
        stops.append((boundary, "travel"))
        for cylinder in rest:
            stops.append((cylinder, "request"))

    return _build_result("SCAN", reqs, head, disk_size, stops, direction=direction)


# ---------------------------------------------------------------------------
# 4. C-SCAN (circular SCAN)
# ---------------------------------------------------------------------------
def cscan(
    requests: Sequence[int],
    head: int,
    disk_size: int = DEFAULT_DISK_SIZE,
    direction: str = "up",
) -> DiskResult:
    """C-SCAN — sweep one way, jump back to the start, sweep again.

    Concept: circular SCAN. The head only serves requests while moving in one
    direction. When it reaches the end it returns to cylinder 0 (or the far
    end when moving down) without serving anything on the return trip, then
    continues in the same direction. The return is a fast seek, not a sweep.

    OS use: modern disk firmware and some RAID controllers; it gives a more
    uniform wait time than SCAN because no cylinder gets "double" service near
    the edges.

    Working principle (``direction="up"``):
        serve requests >= head ascending, travel to ``disk_size - 1``, jump to
        0 (not counted), serve the remaining requests ascending.

    Complexity: O(n log n) time (one sort), O(n) space.

    Advantage: uniform service — the gap between two visits to a cylinder is
    roughly constant, unlike SCAN where the middle is favoured.
    Disadvantage: the return jump is wasted work. On the sample it costs 199
    cylinders of "free" travel, so the counted movement (183) looks better
    than the real head path (382 if the jump is charged).
    """
    reqs = _validate(requests, head, disk_size, direction)
    above = sorted(c for c in reqs if c >= head)
    below_ascending = sorted(c for c in reqs if c < head)
    stops: list[Stop] = []

    if direction == "up":
        first, rest, boundary, restart = above, below_ascending, disk_size - 1, 0
    else:
        first = list(reversed(below_ascending))
        rest = list(reversed(above))
        boundary, restart = 0, disk_size - 1

    for cylinder in first:
        stops.append((cylinder, "request"))

    return_jump = 0
    if rest:
        # End of the sweep: travel to the edge (counted), then fast-return (not).
        stops.append((boundary, "travel"))
        return_jump = abs(restart - boundary)
        stops.append((restart, "jump"))
        for cylinder in rest:
            stops.append((cylinder, "request"))

    return _build_result(
        "CSCAN", reqs, head, disk_size, stops, direction=direction, return_jump=return_jump
    )


# ---------------------------------------------------------------------------
# Registry and dispatcher
# ---------------------------------------------------------------------------
#: Names accepted by the menu and the comparison layer.
ALGORITHMS: dict[str, str] = {
    "FCFS": "FCFS",
    "SSTF": "SSTF",
    "SCAN": "SCAN",
    "CSCAN": "C-SCAN",
}


def run_algorithm(
    name: str,
    requests: Sequence[int],
    head: int,
    disk_size: int = DEFAULT_DISK_SIZE,
    direction: str = "up",
) -> DiskResult:
    """Run one disk algorithm by name.

    Args:
        name: ``FCFS``, ``SSTF``, ``SCAN`` or ``CSCAN`` (case-insensitive).
        requests: requested cylinder numbers, in arrival order.
        head: current head cylinder.
        disk_size: number of cylinders on the disk.
        direction: ``"up"`` or ``"down"``; only SCAN and C-SCAN use it.

    Raises:
        ValueError: unknown algorithm name.
    """
    key = name.strip().upper()
    if key not in ALGORITHMS:
        raise ValueError(
            f"unknown disk algorithm {name!r}; choose from {', '.join(ALGORITHMS)}"
        )
    if key == "FCFS":
        return fcfs(requests, head, disk_size)
    if key == "SSTF":
        return sstf(requests, head, disk_size)
    if key == "SCAN":
        return scan(requests, head, disk_size, direction)
    return cscan(requests, head, disk_size, direction)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def parse_disk_lines(lines: Iterable[str]) -> tuple[int, int, list[int]]:
    """Parse a disk dataset into ``(head, disk_size, requests)``.

    Format (``#`` starts a comment; commas and colons act as spaces):::

        head 53
        disk_size 200
        requests 98 183 37 122 14 124 65 67

    ``requests`` may be spread over several lines, and a bare line of numbers
    is appended to the request list. ``disk_size`` defaults to 200. Errors
    report the 1-based line number.
    """
    head: int | None = None
    disk_size = DEFAULT_DISK_SIZE
    requests: list[int] = []

    for lineno, raw in enumerate(lines, start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.replace(",", " ").replace(":", " ").split()
        key = fields[0].lower()

        if key == "head":
            if len(fields) != 2:
                raise ValueError(f"line {lineno}: 'head' needs exactly one cylinder")
            try:
                head = int(fields[1])
            except ValueError:
                raise ValueError(f"line {lineno}: head must be an integer") from None
            continue

        if key in ("disk_size", "cylinders"):
            if len(fields) != 2:
                raise ValueError(f"line {lineno}: '{key}' needs exactly one number")
            try:
                disk_size = int(fields[1])
            except ValueError:
                raise ValueError(f"line {lineno}: disk size must be an integer") from None
            continue

        values = fields[1:] if key == "requests" else fields
        if not values:
            raise ValueError(f"line {lineno}: no request cylinders listed")
        try:
            requests.extend(int(v) for v in values)
        except ValueError:
            raise ValueError(f"line {lineno}: request cylinders must be integers") from None

    if head is None:
        raise ValueError("dataset is missing the 'head' line")
    if not requests:
        raise ValueError("dataset is missing its request cylinders")
    _validate(requests, head, disk_size)
    return head, disk_size, requests


def load_disk_dataset(path: str | Path) -> tuple[int, int, list[int]]:
    """Load a disk dataset from a text file (see :func:`parse_disk_lines`)."""
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"dataset file not found: {p}")
    with p.open("r", encoding="utf-8") as fh:
        return parse_disk_lines(fh)


# ---------------------------------------------------------------------------
# Standalone demo:  python3 modules/disk_scheduling.py
# ---------------------------------------------------------------------------
def _print_result(res: DiskResult) -> None:
    """Print the per-request arithmetic, the totals and the head path."""
    label = res.algorithm + (f"  (direction = {res.direction})" if res.direction else "")
    print(f"  Algorithm: {label}")
    header = f"{'#':<4}{'MOVE':>16}{'DIST':>7}   {'NOTE':<10}"
    print("  " + header)
    print("  " + "-" * (len(header) + 8))
    step = 0
    for m in res.movements:
        step += 1
        note = "boundary" if m.is_boundary else ""
        print(f"  {step:<4}{f'{m.start} -> {m.end}':>16}{m.distance:>7}   {note:<10}")
    print("  " + "-" * (len(header) + 8))
    print(f"  Served order : {', '.join(str(c) for c in res.order)}")
    print(f"  Head path    : {res.sequence_text}")
    print(f"  Total movement = {' + '.join(str(m.distance) for m in res.movements)}"
          f" = {res.total_movement} cylinders")
    print(f"  Average per request = {res.total_movement} / {len(res.requests)}"
          f" = {res.average_movement:.2f} cylinders")
    if res.return_jump:
        print(f"  C-SCAN return jump: {res.return_jump} cylinders (recorded, not counted"
              f" in the total; charged path would be {res.total_movement + res.return_jump})")


def _demo() -> None:
    root = Path(__file__).resolve().parent.parent
    for filename in ("disk_sample.txt", "disk_sample2.txt"):
        path = root / "data" / filename
        if not path.is_file():
            print(f"[skip] {path} not found")
            continue
        head, disk_size, requests = load_disk_dataset(path)
        print("=" * 78)
        print(f"Dataset: {filename}   (head {head}, {disk_size} cylinders, "
              f"{len(requests)} requests)")
        print(f"  Requests: {requests}")
        print("=" * 78)
        print()
        # FCFS and SSTF ignore direction, so print them once.
        for name in ("FCFS", "SSTF"):
            _print_result(run_algorithm(name, requests, head, disk_size))
            print()
        # SCAN and C-SCAN are direction-sensitive: one block per direction.
        for direction in DIRECTIONS:
            for name in ("SCAN", "CSCAN"):
                _print_result(run_algorithm(name, requests, head, disk_size, direction))
                print()
        print()


if __name__ == "__main__":
    _demo()
