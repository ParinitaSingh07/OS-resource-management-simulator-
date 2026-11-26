"""
Memory Management module — OS Resource Management Simulator
===========================================================

Implements three contiguous memory-allocation strategies under two allocation
models, and accounts for the wasted space each one leaves behind:

    FIRST   First Fit   — use the first free block that is large enough
    BEST    Best Fit    — use the smallest free block that is large enough
    WORST   Worst Fit   — use the largest free block

Models:

    "fixed"    The memory is pre-divided into partitions of fixed size. A
               process is given ONE WHOLE partition, so the unused tail of that
               partition is wasted. This is where **internal fragmentation**
               comes from.

    "dynamic"  Partitions are free holes that can be split. A process takes
               exactly its size and the remainder becomes a new free hole, so
               internal fragmentation is zero by construction. Splitting is
               what produces **external fragmentation**: many holes that are
               each too small for a waiting process.

Metric definitions used here (one definition, both models):

    internal_frag  = sum(allocated_block_size - process_size)      (fixed only)
    external_frag  = free memory sitting in blocks smaller than the smallest
                     REJECTED process; i.e. memory that exists but cannot serve
                     the request that is waiting. No rejected process => 0,
                     because nothing is being blocked by the fragmentation.
    utilisation    = sum(process sizes that were placed) / total memory * 100

Design rules (from docs/PHASE1_SYSTEM_DESIGN.md):
  * Pure functions: ``(partitions, processes, model) -> MemoryResult``.
    No input(), no print(), no file paths.
  * All three algorithms return the same result type.
  * Tie-break: lowest block index, so results are deterministic (NFR-9).

Academic notes (concept, OS use, complexity, viva points) are in each
algorithm's docstring.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

__all__ = [
    "Block",
    "MemoryProcess",
    "MemoryAllocation",
    "MemoryResult",
    "MODELS",
    "ALGORITHMS",
    "first_fit",
    "best_fit",
    "worst_fit",
    "run_algorithm",
    "load_memory_dataset",
]

#: Allocation models accepted by every algorithm.
MODELS = ("fixed", "dynamic")


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class MemoryProcess:
    """A process asking for contiguous memory.

    Attributes:
        pid:  Process identifier, e.g. ``"P1"``.
        size: Memory required in allocation units (bytes here), must be > 0.
    """

    pid: str
    size: int


@dataclass
class Block:
    """One partition (fixed model) or one hole/allocated region (dynamic model).

    ``size`` is the block's current size, ``used`` is how many units of it the
    resident process actually needs, so ``size - used`` is internal
    fragmentation. ``pid is None`` means the block is free.

    In the dynamic model an allocated block's ``size`` equals its process size
    (the tail was split off into a separate free block), which is why internal
    fragmentation is zero there.
    """

    block_id: int
    size: int
    pid: str | None = None
    used: int = 0

    @property
    def is_free(self) -> bool:
        """True when no process occupies this block."""
        return self.pid is None

    @property
    def free_space(self) -> int:
        """Units inside this block that no process is using."""
        return self.size - self.used


@dataclass
class MemoryAllocation:
    """Outcome for one process.

    ``status`` is ``"ALLOCATED"`` or ``"REJECTED"``. ``reason`` explains a
    rejection (empty string when allocated).
    """

    pid: str
    size: int
    block_id: int | None
    allocated_size: int
    internal_frag: int
    status: str
    reason: str = ""


@dataclass
class MemoryResult:
    """Everything one algorithm produced for one dataset and model."""

    algorithm: str
    model: str
    allocations: list[MemoryAllocation]
    blocks: list[Block]
    total_memory: int
    usable_memory: int          # sum of process sizes actually placed
    allocated_memory: int       # sum of block sizes now occupied (reserved)
    free_memory: int            # sum of block sizes still free
    internal_frag: int
    external_frag: int
    stranded_blocks: int        # free blocks too small for the smallest rejected process
    rejected: list[str]
    utilisation: float          # usable_memory / total_memory * 100

    @property
    def allocated_count(self) -> int:
        """Number of processes that received memory."""
        return sum(1 for a in self.allocations if a.status == "ALLOCATED")

    @property
    def free_blocks(self) -> list[Block]:
        """The blocks that are currently free, in memory order."""
        return [b for b in self.blocks if b.is_free]


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def _check_size(value: object, what: str) -> int:
    """Return ``value`` if it is a positive integer, else raise.

    ``bool`` is rejected explicitly because Python treats it as an int and
    ``True`` as a size would be a silent bug.
    """
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{what} must be an integer (got {type(value).__name__})")
    if value <= 0:
        raise ValueError(f"{what} must be > 0 (got {value})")
    return value


def _validate(
    partitions: Sequence[int], processes: Sequence[MemoryProcess], model: str
) -> None:
    """Check everything the allocation loop relies on.

    Raises:
        ValueError: empty partition/process list, non-positive size, duplicate
                    pid, unknown model.
        TypeError:  a size that is not an integer, or a non-MemoryProcess item.
    """
    if model not in MODELS:
        raise ValueError(f"unknown allocation model {model!r}; choose from {', '.join(MODELS)}")
    if not isinstance(partitions, Sequence) or isinstance(partitions, (str, bytes)):
        raise TypeError("partitions must be a sequence of integers")
    if not isinstance(processes, Sequence) or isinstance(processes, (str, bytes)):
        raise TypeError("processes must be a sequence of MemoryProcess objects")
    if len(partitions) == 0:
        raise ValueError("partition list is empty; provide at least one partition")
    if len(processes) == 0:
        raise ValueError("process list is empty; provide at least one process")

    for i, size in enumerate(partitions):
        _check_size(size, f"partition {i} size ({size})")

    seen: set[str] = set()
    for p in processes:
        if not isinstance(p, MemoryProcess):
            raise TypeError(f"expected MemoryProcess, got {type(p).__name__}")
        if p.pid in seen:
            raise ValueError(f"duplicate process id {p.pid!r}")
        seen.add(p.pid)
        _check_size(p.size, f"{p.pid}: request size")


# ---------------------------------------------------------------------------
# Placement strategies
# ---------------------------------------------------------------------------
def _select_block(blocks: Sequence[Block], need: int, algorithm: str) -> int | None:
    """Pick the index of the block that should receive a process of ``need`` units.

    All three strategies only consider blocks that are free AND large enough.
    Ties are broken by the lowest block index so the result is deterministic.

    Returns:
        The chosen index, or ``None`` when no free block is large enough.
    """
    candidates = [i for i, b in enumerate(blocks) if b.is_free and b.size >= need]
    if not candidates:
        return None
    if algorithm == "FIRST":
        return candidates[0]
    if algorithm == "BEST":
        return min(candidates, key=lambda i: (blocks[i].size, blocks[i].block_id))
    return max(candidates, key=lambda i: (blocks[i].size, -blocks[i].block_id))


# ---------------------------------------------------------------------------
# Shared engine
# ---------------------------------------------------------------------------
def _allocate(
    partitions: Sequence[int],
    processes: Sequence[MemoryProcess],
    algorithm: str,
    model: str,
) -> MemoryResult:
    """Run one allocation strategy and assemble the metrics.

    The three public algorithms differ only in how the block is chosen, so the
    whole placement + accounting pass lives here once.
    """
    _validate(partitions, processes, model)

    total_memory = sum(partitions)
    blocks = [Block(block_id=i, size=size) for i, size in enumerate(partitions)]
    next_block_id = len(blocks)

    allocations: list[MemoryAllocation] = []
    rejected: list[str] = []
    rejected_sizes: list[int] = []       # requests that could have fitted somewhere

    for p in processes:
        if p.size > total_memory:                       # can never fit, whatever the holes
            allocations.append(
                MemoryAllocation(p.pid, p.size, None, 0, 0, "REJECTED",
                                 "request is larger than total memory")
            )
            rejected.append(p.pid)
            continue

        idx = _select_block(blocks, p.size, algorithm)
        if idx is None:
            allocations.append(
                MemoryAllocation(p.pid, p.size, None, 0, 0, "REJECTED",
                                 "no free block is large enough")
            )
            rejected.append(p.pid)
            rejected_sizes.append(p.size)
            continue

        block = blocks[idx]
        if model == "fixed":
            # The process gets the WHOLE partition; the tail is internal fragmentation.
            block.pid = p.pid
            block.used = p.size
            allocations.append(
                MemoryAllocation(p.pid, p.size, block.block_id,
                                 block.size, block.size - p.size, "ALLOCATED")
            )
        else:
            # Split the hole: the process takes exactly its size, remainder stays free.
            if block.size > p.size:
                blocks.insert(idx + 1, Block(next_block_id, block.size - p.size))
                next_block_id += 1
                block.size = p.size          # the allocated region holds exactly the process
            block.pid = p.pid
            block.used = p.size
            allocations.append(
                MemoryAllocation(p.pid, p.size, block.block_id,
                                 block.size, 0, "ALLOCATED")
            )

    # Renumber blocks in memory order, so the printed layout reads left to right
    # even after dynamic splitting has inserted holes in the middle of the list.
    old_to_new = {b.block_id: i for i, b in enumerate(blocks)}
    for i, b in enumerate(blocks):
        b.block_id = i
    for a in allocations:
        if a.block_id is not None:
            a.block_id = old_to_new[a.block_id]

    allocated_memory = sum(b.size for b in blocks if not b.is_free)
    free_memory = sum(b.size for b in blocks if b.is_free)
    usable_memory = sum(a.size for a in allocations if a.status == "ALLOCATED")
    internal_frag = sum(a.internal_frag for a in allocations)

    # External fragmentation: free memory that cannot serve the waiting request.
    threshold = min(rejected_sizes) if rejected_sizes else None
    if threshold is None:
        external_frag = 0
        stranded_blocks = 0
    else:
        stranded = [b for b in blocks if b.is_free and b.size < threshold]
        external_frag = sum(b.size for b in stranded)
        stranded_blocks = len(stranded)

    return MemoryResult(
        algorithm=algorithm,
        model=model,
        allocations=allocations,
        blocks=blocks,
        total_memory=total_memory,
        usable_memory=usable_memory,
        allocated_memory=allocated_memory,
        free_memory=free_memory,
        internal_frag=internal_frag,
        external_frag=external_frag,
        stranded_blocks=stranded_blocks,
        rejected=rejected,
        utilisation=(usable_memory / total_memory * 100.0) if total_memory else 0.0,
    )


# ---------------------------------------------------------------------------
# 1. First Fit
# ---------------------------------------------------------------------------
def first_fit(
    partitions: Sequence[int], processes: Sequence[MemoryProcess], model: str = "fixed"
) -> MemoryResult:
    """First Fit — allocate the FIRST free block that is large enough.

    Concept: scan memory from the lowest address; the first hole that can hold
    the process is used. If no hole is big enough, the process waits.

    OS use: the classic scheme in early UNIX and in many simple allocators,
    because it needs no search of the whole list.

    Working principle: ``blocks[i].size >= need`` for the smallest such ``i``.

    Complexity: O(n·m) time for n processes and m blocks, O(m) space.

    Advantage: fastest of the three — it stops at the first fit and leaves the
    big holes at the end untouched.
    Disadvantage: it fragments the *start* of memory into small holes over
    time, and later large requests may fail even though enough total memory is
    free (visible in the dynamic model below).
    """
    return _allocate(partitions, processes, "FIRST", model)


# ---------------------------------------------------------------------------
# 2. Best Fit
# ---------------------------------------------------------------------------
def best_fit(
    partitions: Sequence[int], processes: Sequence[MemoryProcess], model: str = "fixed"
) -> MemoryResult:
    """Best Fit — allocate the SMALLEST free block that is large enough.

    Concept: search all holes and pick the one whose size is closest to the
    request, so the leftover ("slack") is as small as possible.

    OS use: allocators that want to preserve large contiguous regions for
    later, e.g. some embedded/database buffer managers.

    Working principle: among free blocks with ``size >= need``, choose the
    minimum size (ties: lowest index).

    Complexity: O(n·m) time (a full scan per process), O(m) space.

    Advantage: wastes the least space per allocation, so it often fits more
    processes into the same memory — as the sample dataset shows.
    Disadvantage: it produces many tiny leftover holes that are useless for
    anything else, which is why Best Fit is the **worst** producer of external
    fragmentation in the long run.
    """
    return _allocate(partitions, processes, "BEST", model)


# ---------------------------------------------------------------------------
# 3. Worst Fit
# ---------------------------------------------------------------------------
def worst_fit(
    partitions: Sequence[int], processes: Sequence[MemoryProcess], model: str = "fixed"
) -> MemoryResult:
    """Worst Fit — allocate the LARGEST free block.

    Concept: always take the biggest hole, so the leftover is still big enough
    to be useful for another process.

    OS use: rarely used in practice; studied as the opposite extreme of Best
    Fit and used in some teaching allocators.

    Working principle: among free blocks with ``size >= need``, choose the
    maximum size (ties: lowest index).

    Complexity: O(n·m) time, O(m) space.

    Advantage: the remaining hole tends to stay large, so medium requests can
    still be satisfied after a big one.
    Disadvantage: it destroys the largest holes first; with a big process in
    the queue it can waste more space than First Fit (see internal
    fragmentation in the output) and it delays when large blocks become
    available.
    """
    return _allocate(partitions, processes, "WORST", model)


# ---------------------------------------------------------------------------
# Registry and dispatcher
# ---------------------------------------------------------------------------
#: Names accepted by the menu / comparison layer.
ALGORITHMS: dict[str, str] = {"FIRST": "First Fit", "BEST": "Best Fit", "WORST": "Worst Fit"}


def run_algorithm(
    name: str,
    partitions: Sequence[int],
    processes: Sequence[MemoryProcess],
    model: str = "fixed",
) -> MemoryResult:
    """Run one allocation algorithm by name.

    Args:
        name: ``FIRST``, ``BEST`` or ``WORST`` (case-insensitive).
        partitions: sizes of the memory partitions.
        processes: the requests, in arrival order.
        model: ``"fixed"`` or ``"dynamic"``.

    Raises:
        ValueError: unknown algorithm name.
    """
    key = name.strip().upper()
    if key not in ALGORITHMS:
        raise ValueError(
            f"unknown memory algorithm {name!r}; choose from {', '.join(ALGORITHMS)}"
        )
    func = {"FIRST": first_fit, "BEST": best_fit, "WORST": worst_fit}[key]
    return func(partitions, processes, model=model)


# ---------------------------------------------------------------------------
# Dataset loading
# ---------------------------------------------------------------------------
def load_memory_dataset(path: str | Path) -> tuple[list[int], list[MemoryProcess]]:
    """Load a dataset with one ``partitions`` line and one line per process.

    Format::

        # comment
        partitions 100 500 200 300 600
        P1 212
        P2 417

    The ``partitions`` keyword is case-insensitive; fields may be separated by
    spaces, tabs or commas. Errors report the 1-based line number.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"dataset file not found: {p}")

    partitions: list[int] | None = None
    processes: list[MemoryProcess] = []

    with p.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.split("#", 1)[0].strip()
            if not line:
                continue
            fields = line.replace(",", " ").replace(":", " ").split()
            if fields[0].lower() == "partitions":
                if partitions is not None:
                    raise ValueError(f"line {lineno}: 'partitions' given more than once")
                try:
                    partitions = [int(v) for v in fields[1:]]
                except ValueError:
                    raise ValueError(f"line {lineno}: partition sizes must be integers") from None
                if not partitions:
                    raise ValueError(f"line {lineno}: no partition sizes listed")
                continue
            if len(fields) != 2:
                raise ValueError(f"line {lineno}: expected 'pid size', got {len(fields)} field(s)")
            try:
                size = int(fields[1])
            except ValueError:
                raise ValueError(f"line {lineno}: size must be an integer") from None
            processes.append(MemoryProcess(pid=fields[0], size=size))

    if partitions is None:
        raise ValueError("dataset is missing its 'partitions ...' line")
    return partitions, processes


# ---------------------------------------------------------------------------
# Standalone demo:  python3 -m modules.memory_management
# ---------------------------------------------------------------------------
def _print_result(res: MemoryResult) -> None:
    """Minimal fixed-width report for the standalone demo."""
    print(f"  Algorithm: {res.algorithm}      model: {res.model.upper()}")
    header = f"{'PID':<6}{'REQ':>6}{'BLOCK':>7}{'ALLOC':>7}{'INT.FRAG':>10}{'STATUS':>11}"
    print("  " + header)
    print("  " + "-" * (len(header) + 6))
    for a in res.allocations:
        block = "-" if a.block_id is None else str(a.block_id)
        print(f"  {a.pid:<6}{a.size:>6}{block:>7}{a.allocated_size:>7}"
              f"{a.internal_frag:>10}{a.status:>11}")
    print("  " + "-" * (len(header) + 6))
    print(f"  Total memory: {res.total_memory}   reserved by blocks: {res.allocated_memory}"
          f"   free: {res.free_memory}")
    print(f"  Usable (placed process data): {res.usable_memory}  ->  utilisation "
          f"{res.utilisation:.2f}%")
    print(f"  Internal fragmentation: {res.internal_frag}   External fragmentation: "
          f"{res.external_frag} ({res.stranded_blocks} stranded block(s))")
    if res.rejected:
        reasons = ", ".join(
            f"{a.pid} ({a.reason})" for a in res.allocations if a.status == "REJECTED"
        )
        print(f"  Rejected: {reasons}")
    layout = "  ".join(
        f"[{b.block_id}:{b.size}{' FREE' if b.is_free else f' {b.pid}({b.used})'}]"
        for b in res.blocks
    )
    print(f"  Memory: {layout}")
    print()


def _demo() -> None:
    root = Path(__file__).resolve().parent.parent
    path = root / "data" / "memory_sample.txt"
    if not path.is_file():
        print(f"[skip] {path} not found")
        return

    partitions, processes = load_memory_dataset(path)
    print("=" * 78)
    print(f"Dataset: memory_sample.txt")
    print(f"  Partitions: {partitions}  (total {sum(partitions)})")
    print(f"  Processes : {[(p.pid, p.size) for p in processes]}  "
          f"(total {sum(p.size for p in processes)})")
    print("=" * 78)
    print()

    for model in MODELS:
        print(f"### MODEL: {model.upper()} PARTITIONS " + "#" * 40)
        print()
        for name in ALGORITHMS:
            _print_result(run_algorithm(name, partitions, processes, model=model))

    print("### EDGE CASE: request larger than total memory " + "#" * 29)
    oversized = [MemoryProcess("X1", 9999)]
    _print_result(first_fit(partitions, oversized))


if __name__ == "__main__":
    _demo()
