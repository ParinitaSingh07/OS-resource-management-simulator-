# Phase 1 — System Design and Planning
## OS Resource Management Simulator (Python + Bash)

| Item | Detail |
|---|---|
| Project title | OS Resource Management Simulator |
| Course | Operating Systems — Capstone Project (100 marks, 5 phases × 20) |
| Author | BTech CSE student |
| Language | Python 3 (3.10+), Bash |
| Libraries | Matplotlib (charts), `unittest` (testing); NumPy/Pandas **not required** |
| Interface | Terminal menu-driven application |
| Document status | Phase 1 deliverable (design frozen, pending student confirmation) |
| Date | 20 November 2026 |

---

## 1. Problem Statement

Operating-system resource management is taught as a set of separate theories: CPU scheduling
algorithms, contiguous memory allocation strategies, deadlock avoidance/detection, and disk head
scheduling. Students usually meet each one as an isolated numerical exercise on paper. This makes
three things hard to see:

1. **How the algorithms actually behave on the same input** — for example, why SJF gives a lower
   average waiting time than FCFS on a given process set, or why Best Fit can leave memory in a
   worse state than First Fit.
2. **How metrics are derived** — completion time, turnaround time, waiting time and response time
   are easy to define and easy to get wrong when calculated by hand.
3. **How OS concepts fit together as one resource-management system** rather than four unrelated
   chapters.

There is no single, small, dependency-light tool that (a) simulates all four resource-management
areas, (b) computes the textbook metrics automatically, (c) compares algorithms on identical
datasets, (d) visualises the results, and (e) can be demonstrated live in a viva.

**Therefore:** build an integrated, terminal-based **OS Resource Management Simulator** in Python
that simulates the four resource-management modules, computes and visualises their performance
metrics, compares algorithms on shared datasets, logs every run, and is verifiable through an
automated test suite and Bash tooling.

> Important scope statement: this is a **simulation for academic study**. It is not an operating
> system, does not touch real hardware, and does not schedule real processes. All "resources"
> (CPU time, memory blocks, resource instances, disk cylinders) are numbers supplied by the user.

---

## 2. Objectives

| ID | Objective | Verified by |
|---|---|---|
| O1 | Implement FCFS, SJF, SRTF, Priority and Round Robin CPU scheduling with a common metrics model | Module 1 + unit tests (Phase 4) |
| O2 | Implement First Fit, Best Fit and Worst Fit contiguous memory allocation with fragmentation accounting | Module 2 + unit tests |
| O3 | Implement Banker's safety algorithm, Banker's resource-request algorithm and deadlock detection | Module 3 + unit tests |
| O4 | Implement FCFS, SSTF, SCAN and C-SCAN disk scheduling with per-request seek distances | Module 4 + unit tests |
| O5 | Integrate all modules behind one menu with custom dataset entry | `main.py` + demonstration |
| O6 | Produce comparison tables and labelled charts for identical datasets | Module 5 + `outputs/` |
| O7 | Validate all input and never crash on bad data | `utils/validation.py` + negative tests |
| O8 | Log every simulation run with timestamps to a file | `utils/logger.py` + `outputs/logs/` |
| O9 | Provide meaningful Bash automation (setup, run, test, clean) | `scripts/*.sh` |
| O10 | Deliver complete documentation, test evidence and a PDF report | `README.md`, `docs/`, `report.pdf` |

---

## 3. Scope

### 3.1 In scope

* Four simulation modules: CPU scheduling, memory management, deadlock management, disk scheduling.
* Five CPU algorithms, three memory algorithms, Banker's + detection, four disk algorithms.
* Metric computation per module (Section 6) and cross-algorithm comparison.
* Terminal menu with manual dataset entry, built-in demo datasets, and results displayed on screen.
* Charts saved as PNG under `outputs/charts/`, textual reports under `outputs/reports/`.
* Session logging under `outputs/logs/`.
* `unittest` suite covering valid, invalid, boundary and edge-case inputs.
* Bash scripts: `run.sh`, `setup.sh`, `test.sh`, `clean.sh` (Git Bash / WSL compatible).
* Documentation: README, per-algorithm theory, test-case documentation, PDF report.

### 3.2 Out of scope (explicitly excluded)

* Real process/thread creation, `fork`, signals, kernel interaction, or hardware access.
* Multi-core / multi-processor scheduling, real-time scheduling (EDF, Rate Monotonic).
* Paging, segmentation, virtual memory, page replacement, TLB simulation.
* Distributed deadlock, wait-for-graph cycle detection across processes (we use matrix-based detection).
* GUI, web front-end, database, user accounts.
* Any third-party service or framework (no Flask/Django/pandas/numpy).

Stating the exclusions is part of the design: a marker can see that the boundary was chosen
deliberately, not accidentally.

---

## 4. Users and Use Cases

| Actor | Use case |
|---|---|
| Student (author) | Enter a dataset, run every algorithm, compare, export charts for the report |
| Examiner / viva panel | Pick a module from the menu, supply a small dataset live, question the output |
| Future student | Run `./scripts/setup.sh`, `./scripts/run.sh`, read the README |

Primary use case (happy path):
**start app → choose module → choose algorithm (or "compare all") → enter data or pick demo
dataset → view results table → view chart → optionally export → return to menu → exit**
(every step logged).

---

## 5. Functional Requirements

Requirement IDs are used later in the traceability matrix (Section 13) and in Phase 4 test cases.

### FR-1 — Application shell and menu

| ID | Requirement |
|---|---|
| FR-1.1 | On start, display a menu: `1 CPU Scheduling`, `2 Memory Management`, `3 Deadlock Management`, `4 Disk Scheduling`, `5 Performance Analysis`, `6 View Execution Logs`, `7 Exit`. |
| FR-1.2 | An invalid menu choice prints a clear error and re-displays the menu without crashing. |
| FR-1.3 | Every sub-menu returns to the main menu; `7` exits cleanly with a farewell message. |
| FR-1.4 | Non-numeric menu input (e.g. `abc`) is rejected with a message, not a traceback. |
| FR-1.5 | `Ctrl+C` / `Ctrl+D` at any prompt exits the program cleanly after logging. |

### FR-2 — Module 1: CPU Scheduling

| ID | Requirement |
|---|---|
| FR-2.1 | Accept a process table: process ID, arrival time, burst time, and priority for Priority Scheduling. |
| FR-2.2 | Support algorithms: FCFS, SJF (non-preemptive), SRTF (preemptive), Priority (non-preemptive), Round Robin (user-supplied time quantum). |
| FR-2.3 | Compute per process: completion, turnaround, waiting and response time; and aggregate: average waiting, average turnaround, average response, CPU utilisation, throughput, total idle time. |
| FR-2.4 | Produce a Gantt chart (Matplotlib) showing execution segments, including idle gaps. |
| FR-2.5 | Handle idle CPU intervals correctly (no process arrived yet). |
| FR-2.6 | Round Robin must handle burst times that are not multiples of the quantum, and processes arriving mid-quantum. |
| FR-2.7 | Support "compare all five algorithms" on one dataset, producing a comparison table and a grouped bar chart. |

### FR-3 — Module 2: Memory Management

| ID | Requirement |
|---|---|
| FR-3.1 | Accept total/partition sizes and process sizes (custom or demo dataset). |
| FR-3.2 | Support First Fit, Best Fit, Worst Fit under a selectable allocation model (fixed partitions or dynamic partitions — Section 9.3). |
| FR-3.3 | Report, per process: allocated block/partition, allocated size, remaining size, and whether it is allocated or rejected. |
| FR-3.4 | Report allocated blocks, unallocated blocks, internal fragmentation, external fragmentation, unallocated processes, memory utilisation. |
| FR-3.5 | Reject a process with a clear message when it cannot fit; continue allocating the rest (do not abort the run). |
| FR-3.6 | Reject a process whose size exceeds total memory with an explanatory message. |
| FR-3.7 | Produce a horizontal block-layout chart (used vs free vs internal fragmentation). |
| FR-3.8 | Support "compare all three algorithms" with a comparison table and chart. |

### FR-4 — Module 3: Deadlock Management

| ID | Requirement |
|---|---|
| FR-4.1 | Accept Allocation matrix, Maximum matrix (or a claim matrix) and Available vector, with dimension checks (n processes × m resource types). |
| FR-4.2 | Derive and display the Need matrix (`Need = Max − Allocation`). |
| FR-4.3 | Run the Banker's safety algorithm; report safe/unsafe and, if safe, a safe sequence. |
| FR-4.4 | Run the Banker's resource-request algorithm for an optional request vector; grant/deny with the reason. |
| FR-4.5 | Run deadlock detection on the current state and list deadlocked processes plus the work vector at the point of failure. |
| FR-4.6 | Reject malformed input: `Allocation > Max`, negative entries, mismatched dimensions, `Available` length ≠ number of resource types. |
| FR-4.7 | Display the state as a formatted table (matrices + vectors) and save a state report. |

### FR-5 — Module 4: Disk Scheduling

| ID | Requirement |
|---|---|
| FR-5.1 | Accept initial head position, disk cylinder range (`0..max_cylinder`), request queue and direction (for SCAN/C-SCAN). |
| FR-5.2 | Support FCFS, SSTF, SCAN, C-SCAN. |
| FR-5.3 | Report the service order, each request's seek distance, total head movement and average seek distance. |
| FR-5.4 | Reject requests outside the cylinder range, negative cylinders, duplicate handling policy, and an empty queue. |
| FR-5.5 | Produce a head-movement line chart (x = service order, y = cylinder) and a comparison bar chart. |
| FR-5.6 | Support "compare all four algorithms" on the same dataset. |

### FR-6 — Module 5: Performance Analysis

| ID | Requirement |
|---|---|
| FR-6.1 | Run all algorithms of a chosen module on the same dataset and build a comparison table. |
| FR-6.2 | Export the comparison table as a text/Markdown report and a CSV file under `outputs/reports/`. |
| FR-6.3 | Generate labelled comparison charts under `outputs/charts/`. |
| FR-6.4 | Print written observations (which algorithm won, by how much, and why), generated from the data rather than hard-coded. |
| FR-6.5 | Handle a module with no comparable metric gracefully (e.g. deadlock module reports safe/unsafe outcome instead of a speed comparison). |

### FR-7 — Cross-cutting requirements

| ID | Requirement |
|---|---|
| FR-7.1 | All numeric input is validated; invalid input is re-prompted with a specific message. |
| FR-7.2 | Every simulation run is logged: timestamp, module, algorithm, input summary, key results. |
| FR-7.3 | `6 View Execution Logs` shows the most recent log lines from `outputs/logs/`. |
| FR-7.4 | All generated artefacts are written only under `outputs/` and `screenshots/`. |
| FR-7.5 | The app runs from the repository root and also via `scripts/run.sh` from any directory. |
| FR-7.6 | Missing Matplotlib is handled: charts are skipped with a warning, tables still print. |

---

## 6. Non-Functional Requirements

| ID | Category | Requirement | How it is satisfied |
|---|---|---|---|
| NFR-1 | Correctness | Metrics must match hand calculation on textbook datasets (e.g. Silberschatz example) | Verified in Phase 4 tests with hand-computed expected values |
| NFR-2 | Robustness | No unhandled exception for any user-entered input, including empty, negative, huge, or non-numeric values | Central validators + top-level `try/except` in menu loop |
| NFR-3 | Usability | Plain-text tables aligned in an 80-column terminal; every prompt states expected format | Formatting helpers in `utils/report_generator.py` |
| NFR-4 | Performance | Any single simulation on ≤ 100 processes finishes in < 1 s on a normal laptop | Algorithms are O(n²) worst case at most, n small |
| NFR-5 | Maintainability | One file per module, no duplicated metric code, type hints + docstrings | Shared result dataclasses, shared metric functions |
| NFR-6 | Portability | Runs on Windows (Git Bash / WSL), Linux and macOS; Python ≥ 3.10 | Only standard library + Matplotlib; scripts use POSIX shell |
| NFR-7 | Testability | Pure functions separable from the menu so they can be unit-tested without stdin | All logic in `modules/`, menu in `main.py` |
| NFR-8 | Observability | Every run leaves a timestamped log line; failures log the reason | `utils/logger.py` |
| NFR-9 | Determinism | Same input → same output (no randomness anywhere) | No RNG used; tie-breaks documented (Section 9.1) |
| NFR-10 | Academic integrity | No fabricated results; all numbers in the report come from real runs | Evidence captured from actual terminal output |

---

## 7. System Architecture (summary)

Full diagrams are in [`docs/PHASE1_ARCHITECTURE.md`](PHASE1_ARCHITECTURE.md). Layered view:

```
┌───────────────────────────────────────────────────────────────┐
│ Presentation layer      main.py  (menu, prompts, tables)       │
├───────────────────────────────────────────────────────────────┤
│ Application layer       modules/*.py  (algorithms + metrics)   │
│                         performance_analysis.py (comparisons)  │
├───────────────────────────────────────────────────────────────┤
│ Support layer           utils/validation.py, logger.py,        │
│                         report_generator.py (tables, charts)   │
├───────────────────────────────────────────────────────────────┤
│ Data layer              data/ (demo datasets, CSV)             │
│                         outputs/ (charts, reports, logs)       │
└───────────────────────────────────────────────────────────────┘
                          ▲
        Bash tooling: scripts/{setup,run,test,clean}.sh
```

**Design principles actually applied**

1. **Algorithms are pure functions.** `fcfs(processes)` takes data and returns a result object; it
   never calls `input()` or `print()`. This is what makes automated testing possible (NFR-7).
2. **One result contract per module.** Every CPU algorithm returns the same structure, so the
   comparison module does not need special cases.
3. **Single responsibility per file.** `validation.py` only validates, `logger.py` only logs,
   `report_generator.py` only formats/writes, `main.py` only talks to the user.
4. **No hidden global state.** Each run builds its own objects; logs are append-only files.

---

## 8. Module Descriptions

### 8.1 Module 1 — CPU Scheduling (`modules/cpu_scheduling.py`)

* **Purpose:** decide the order in which ready processes get the CPU and measure the cost of that
  order.
* **Input:** list of processes `{pid, arrival, burst, priority}` + algorithm + optional quantum.
* **Algorithms:** FCFS (arrival order), SJF (shortest burst next, non-preemptive), SRTF (shortest
  remaining time, preemptive), Priority (non-preemptive), Round Robin (fixed quantum, cyclic).
* **Output:** per-process table + aggregates + Gantt segments `[(pid, start, end)]`.
* **Key idea:** simulate a clock. At each decision point, pick one process by the algorithm's rule,
  run it until it finishes or is preempted, record a Gantt segment, advance the clock. The clock
  starts at the **first arrival**, so the timeline never opens with an IDLE gap and
  `sum(IDLE segments) == idle_time` for every algorithm and dataset.

### 8.2 Module 2 — Memory Management (`modules/memory_management.py`)

* **Purpose:** place processes of given sizes into contiguous memory partitions and quantify the
  wasted space that results.
* **Input:** partition sizes (or total memory + fixed partition size), process sizes, algorithm,
  allocation model.
* **Algorithms:** First Fit (first partition large enough), Best Fit (smallest partition large
  enough), Worst Fit (largest partition).
* **Output:** allocation table, allocated/unallocated blocks, internal fragmentation, external
  fragmentation, utilisation, block-layout chart.

### 8.3 Module 3 — Deadlock Management (`modules/deadlock_management.py`)

* **Purpose:** decide whether a resource-allocation state is safe (Banker's), process a resource
  request safely, and detect an already-deadlocked state.
* **Input:** `Allocation` matrix (n × m), `Max` matrix (n × m), `Available` vector (m), optional
  `Request` matrix.
* **Algorithms:** Banker's safety algorithm, Banker's resource-request algorithm, deadlock
  detection algorithm.
* **Output:** Need matrix, safe/unsafe verdict, safe sequence, request verdict, deadlocked process
  list, step trace of the work vector.

### 8.4 Module 4 — Disk Scheduling (`modules/disk_scheduling.py`)

* **Purpose:** order disk requests to minimise total head movement (seek distance).
* **Input:** request queue, initial head, max cylinder, direction.
* **Algorithms:** FCFS, SSTF, SCAN (elevator, bounce at the ends), C-SCAN (one-way sweep with a
  return jump).
* **Output:** service order, seek distance per request, total and average head movement, movement
  chart.

### 8.5 Module 5 — Performance Analysis (`modules/performance_analysis.py`)

* **Purpose:** the "analysis" phase in code — run every algorithm of a module on one dataset, build
  the comparison table, compute the winner and percentage differences, write reports/CSV, draw
  charts.
* **Depends on:** Modules 1–4 (imports their functions; contains no algorithm of its own).

### 8.6 Support modules (`utils/`)

| File | Responsibility |
|---|---|
| `validation.py` | Typed prompts and validators: `parse_int`, `parse_float`, `prompt_int`, `prompt_positive_int`, `prompt_non_negative_int`, `prompt_int_list`, `validate_processes`, `validate_matrices`, `validate_disk_input`. Raises `ValidationError` with a human-readable reason. |
| `logger.py` | Creates `outputs/logs/session_<timestamp>.log`; `log_event(module, algorithm, message)`, `log_error(...)`, `get_recent_logs(n)`. Timestamped, append-only, one line per event. |
| `report_generator.py` | Table rendering (fixed-width), text/Markdown/CSV report writing, chart generation with Matplotlib (Gantt, memory layout, disk movement, grouped comparison bars), safe no-Matplotlib fallback, creation of `outputs/` subfolders. |

---

## 9. Input / Output Workflow, Assumptions, and Conventions

### 9.1 Global conventions (must match the code exactly)

| Item | Decision | Why |
|---|---|---|
| Process IDs | Strings such as `P1`, auto-generated if the user only gives numbers | Readable Gantt charts |
| Time unit | Abstract "time units" (integers) | No real clock is involved |
| Priority numbering | **Smaller number = higher priority** (1 is highest) | Classic Unix/`nice` convention; stated in every prompt |
| Tie-breaking | CPU: earlier arrival, then input order (the order the processes were entered). Disk SSTF ties: smaller cylinder. Memory: lowest partition index | Determinism (NFR-9) is required for reproducible tests |
| Idle CPU | Represented as a Gantt segment `("IDLE", start, end)`; the clock starts at the first arrival, so the IDLE segments sum to `idle_time` | So utilisation can be computed exactly and the chart matches the metric |
| Response time | First time the process gets the CPU − arrival | Standard definition |
| CPU utilisation | `busy_time / (max(completion) − min(arrival)) × 100` | Denominator is the observed schedule span |
| Throughput | `n / schedule_span` processes per time unit, also shown per 100 time units | Both forms are readable |
| Round Robin | Quantum ≥ 1; a new arrival is queued before the preempted process is re-queued | Standard textbook ordering |
| Empty input | Rejected before any algorithm runs | Prevents meaningless averages |

### 9.2 Memory model assumptions (explicit, because fragmentation is definition-sensitive)

Two allocation models are supported; the user picks one and the report states which was used.

**Model A — Fixed partitions (default for "internal fragmentation" demonstration).**
Memory is pre-divided into partitions of the given sizes. A process is given one whole partition
that is large enough (partition ≥ process size). Then:

* internal fragmentation = Σ (partition_size − process_size) over allocated processes;
* a partition partly used is *not* reusable by another process (no splitting), so the wasted tail
  can never be handed to anyone else;
* external fragmentation = Σ sizes of **free partitions smaller than the smallest rejected
  process** (plus a count of such partitions) — memory that exists but cannot serve the request
  that is waiting. If no process was rejected, external fragmentation is reported as 0, because
  no pending request is being blocked.

**Model B — Dynamic partitions (variable partitions, splitting enabled).**

* A chosen free partition is split: the process takes exactly its size, the remainder becomes a new
  free partition (so internal fragmentation = 0 by construction, and we say so);
* external fragmentation uses the **same definition as Model A** — free holes smaller than the
  smallest rejected process — so the two models can be compared directly. Splitting is what makes
  this number grow: many small holes that individually cannot hold the waiting process.

"Rejected" throughout means a process that arrived but found no block large enough (a request
larger than total memory is reported separately and never counts as fragmentation).

Both models are computed by the same three placement strategies; only the placement/splitting step
differs. This is the honest way to satisfy "internal and external fragmentation where applicable"
without inventing numbers.

### 9.3 Deadlock assumptions

* Single instance-per-type is **not** assumed: `Available[j]` and matrix columns are counts of
  instances, so multiple instances per resource type are supported (Banker's requirement).
* `Need = Max − Allocation`; input is rejected if `Allocation[i][j] > Max[i][j]`.
* Banker's safety algorithm is run on the *current* state (before granting any request) and again
  after a hypothetical grant.
* Deadlock **detection** uses `Request` (outstanding requests). If the user supplies no `Request`
  matrix, detection falls back to `Request = Need` — i.e. "every process still wants everything it
  may ever claim". This fallback is printed on screen so the result is never ambiguous.
* A state can be *unsafe* yet not *deadlocked*: the report states this distinction explicitly.

### 9.4 Disk assumptions

* Cylinders are integers in `[0, max_cylinder]`; the head starts inside that range.
* Seek distance = `|cylinder_now − cylinder_next|`; total head movement = sum of distances.
* SCAN: travel to the requested end of the disk in the chosen direction (serving requests on the
  way), then reverse and serve the rest. The reversal itself costs the distance actually travelled.
* C-SCAN: travel to the high end serving requests, then jump back to cylinder 0 **without counting
  the jump** (the standard textbook convention), then continue upward. This convention is printed
  in the result so the total is never ambiguous.
* Duplicate requests are kept (each is a separate I/O operation).

### 9.5 End-to-end input/output workflow

```
User keystrokes
      │
      ▼
main.py menu loop ──► validation.py  (parse + range checks, re-prompt on error)
      │                                   │
      │                          ValidationError ──► message + retry
      ▼
prompt dataset (manual entry)  or  data/*.txt demo dataset
      │
      ▼
choose algorithm / "compare all"
      │
      ▼
modules/<module>.py  ──►  result object (per-item rows + aggregates + timeline)
      │                                   │
      │                                   ├──► report_generator.render_table()  → screen
      │                                   ├──► report_generator.save_report()   → outputs/reports/
      │                                   ├──► report_generator.plot_*()        → outputs/charts/*.png
      │                                   └──► logger.log_event()               → outputs/logs/*.log
      ▼
menu loop again (until Exit)
```

**Artefacts produced by one comparison run** (e.g. CPU, 5 processes):

```
outputs/reports/cpu_comparison_20261120_143012.txt
outputs/reports/cpu_comparison_20261120_143012.csv
outputs/charts/cpu_comparison_avg_waiting_20261120_143012.png
outputs/charts/cpu_comparison_avg_turnaround_20261120_143012.png
outputs/charts/cpu_gantt_rr_20261120_143012.png
outputs/logs/session_20261120_143005.log
```

---

## 10. Data Structures

All are `@dataclass` objects (or plain dicts for tiny cases) — chosen because they give named
fields, readable `repr` for debugging, and free equality for tests.

### 10.1 CPU

```python
@dataclass
class Process:
    pid: str
    arrival: int
    burst: int
    priority: int = 0          # smaller = higher priority

@dataclass
class ProcessResult:
    pid: str
    arrival: int
    burst: int
    completion: int
    turnaround: int            # completion - arrival
    waiting: int               # turnaround - burst
    response: int              # first_cpu_time - arrival

@dataclass
class CpuScheduleResult:
    algorithm: str
    quantum: int | None
    rows: list[ProcessResult]
    gantt: list[tuple[str, int, int]]   # (pid | "IDLE", start, end)
    avg_waiting: float
    avg_turnaround: float
    avg_response: float
    cpu_utilisation: float              # percent
    throughput: float                   # processes per time unit
    total_time: int
    idle_time: int
```

Why a `gantt` list of segments rather than a per-process start/end? Because preemptive algorithms
(SRTF, RR) run a process in several slices, and idle gaps must be visible. Segments are the only
representation that covers all five algorithms.

### 10.2 Memory

```python
@dataclass
class Block:              # a partition
    block_id: int
    size: int
    pid: str | None = None      # None => free
    used: int = 0

@dataclass
class MemoryAllocation:   # one process's outcome
    pid: str
    size: int
    block_id: int | None
    allocated_size: int
    internal_frag: int
    status: str               # "ALLOCATED" | "REJECTED"

@dataclass
class MemoryResult:
    algorithm: str
    model: str                # "fixed" | "dynamic"
    allocations: list[MemoryAllocation]
    blocks: list[Block]
    total_memory: int
    allocated_memory: int
    free_memory: int
    internal_frag: int
    external_frag: int
    stranded_blocks: int
    rejected: list[str]
    utilisation: float        # percent
```

### 10.3 Deadlock

```python
@dataclass
class DeadlockState:
    processes: list[str]
    resources: list[str]
    allocation: list[list[int]]
    maximum: list[list[int]]
    available: list[int]

@dataclass
class SafetyResult:
    safe: bool
    sequence: list[str]
    steps: list[dict]        # per-step work vector + finished process
    need: list[list[int]]

@dataclass
class DetectionResult:
    deadlocked: list[str]
    finished: list[str]
    steps: list[dict]
```

### 10.4 Disk

```python
@dataclass
class DiskRequest:
    cylinder: int
    pid: str | None = None

@dataclass
class DiskResult:
    algorithm: str
    order: list[int]
    seek_distances: list[int]
    total_movement: int
    avg_seek: float
    initial_head: int
    direction: str
```

### 10.5 Persistence format

Datasets live in `data/` as simple text files (`.txt` / `.csv`) with a commented header, e.g.
`data/cpu_sample.txt`:

```
# pid arrival burst priority
P1 0 8 3
P2 1 4 1
P3 2 9 4
P4 3 5 2
```

Plain text (not a database) because it is inspectable, editable in VS Code, diff-friendly, and needs
no dependency.

---

## 11. Algorithm Selection and Justification

The five CPU, three memory, two deadlock and four disk algorithms are the ones named in the
syllabus and in the assignment. Selection and complexity:

| Module | Algorithm | Type | Time complexity | Space | Why included / what it demonstrates |
|---|---|---|---|---|---|
| CPU | FCFS | Non-preemptive | O(n log n) (sort) + O(n) | O(n) | Baseline; convoy effect |
| CPU | SJF | Non-preemptive | O(n²) simple / O(n log n) heap | O(n) | Provably minimal average waiting time (non-preemptive) |
| CPU | SRTF | Preemptive | O(n²) simple / O(n log n) heap | O(n) | Preemption; best average waiting time overall |
| CPU | Priority | Non-preemptive | O(n²) | O(n) | Starvation, need for ageing |
| CPU | Round Robin | Preemptive | O(n + total_burst/quantum) | O(n) | Fairness, quantum trade-off, response time |
| Mem | First Fit | Contiguous | O(n·m) | O(n+m) | Fast, low overhead; leaves large tail holes |
| Mem | Best Fit | Contiguous | O(n·m) | O(n+m) | Smallest leftover → many tiny unusable holes |
| Mem | Worst Fit | Contiguous | O(n·m) | O(n+m) | Largest leftover → keeps big holes available |
| Dead | Banker's safety | Avoidance | O(n²·m) | O(n·m) | Safe sequence, conservative guarantee |
| Dead | Banker's request | Avoidance | O(n²·m) | O(n·m) | Grant/deny decision with rollback |
| Dead | Detection | Detection | O(n²·m) | O(n·m) | Deadlocked set + recovery input |
| Disk | FCFS | Fair | O(n) | O(n) | Baseline, large movement |
| Disk | SSTF | Greedy | O(n²) / O(n log n) heap | O(n) | Shortest seek, starvation |
| Disk | SCAN | Elevator | O(n log n) | O(n) | Bounded wait, sweep |
| Disk | C-SCAN | Circular sweep | O(n log n) | O(n) | Uniform wait, return jump |

**Why these metrics** (mathematical basis, used verbatim in Phase 2 code):

| Metric | Formula |
|---|---|
| Completion time `CT` | clock value when the process's last slice ends |
| Turnaround time `TAT` | `CT − AT` |
| Waiting time `WT` | `TAT − BT` = total time spent in the ready queue |
| Response time `RT` | `(first CPU allocation) − AT` |
| Average WT | `(Σ WTᵢ) / n` |
| Average TAT | `(Σ TATᵢ) / n` |
| CPU utilisation | `busy / (CT_max − AT_min) × 100 %` |
| Throughput | `n / (CT_max − AT_min)` |
| Internal fragmentation | `Σ (allocated_block_size − process_size)` |
| Memory utilisation | `Σ allocated process sizes / total memory × 100 %` |
| Banker's safety test | ∃ ordering where `Needᵢ ≤ Work`, then `Work += Allocationᵢ` |
| Total head movement | `Σ |cᵢ − cᵢ₋₁|` |
| Average seek | `total_movement / number_of_requests` |

---

## 12. Implementation Plan (Phases 2–5)

| Phase | Marks | Deliverables in this repository | Verification |
|---|---|---|---|
| 1. Design (done) | 20 | `docs/PHASE1_SYSTEM_DESIGN.md`, `docs/PHASE1_ARCHITECTURE.md`, folder skeleton | Reviewed with student |
| 2. Core implementation | 20 | `modules/cpu_scheduling.py`, `modules/memory_management.py`, `modules/deadlock_management.py`, `modules/disk_scheduling.py`, `utils/*.py`, `main.py`, `scripts/*.sh`, `requirements.txt`, demo data | Every algorithm run on demo data; output shown |
| 3. Analysis & comparison | 20 | `modules/performance_analysis.py`, comparison tables, PNG charts, `docs/PHASE3_ANALYSIS.md` | Real runs on shared datasets |
| 4. Testing & reliability | 20 | `tests/test_*.py`, `docs/PHASE4_TEST_REPORT.md` | `./scripts/test.sh` with real output |
| 5. Documentation & demo | 20 | `README.md`, `docs/PHASE5_ALGORITHM_GUIDE.md`, screenshots of real runs, `report.pdf`, `.gitignore` | Walkthrough + commit |

**Sequencing rule I will follow:** finish and execute one module before starting the next; never
report a phase as done without having run the code.

**Planned demo datasets (Phase 2/3)**

| Dataset | Content | Purpose |
|---|---|---|
| `data/cpu_sample.txt` | 5 processes, staggered arrivals | Textbook-like comparison |
| `data/cpu_convoy.txt` | 1 long + 4 short processes | Show FCFS convoy effect |
| `data/memory_sample.txt` | partitions 100,500,200,300,600; processes 212,417,112,426 | Classic fragmentation example |
| `data/deadlock_sample.txt` | 5 processes, 3 resource types (Silberschatz-style) | Known safe sequence check |
| `data/disk_sample.txt` | requests 98,183,37,122,14,124,65,67; head 53 | Classic 640-movement example |

The disk dataset is the standard textbook example, which is useful because total head movement can
be verified by hand: FCFS = 640.

---

## 13. Traceability Matrix (requirement → design → test)

| Requirement group | Module file | Planned test ids (Phase 4) |
|---|---|---|
| FR-1 menu | `main.py` | T-MENU-01…05 |
| FR-2 CPU | `modules/cpu_scheduling.py` | T-CPU-01…20 |
| FR-3 Memory | `modules/memory_management.py` | T-MEM-01…14 |
| FR-4 Deadlock | `modules/deadlock_management.py` | T-DLK-01…12 |
| FR-5 Disk | `modules/disk_scheduling.py` | T-DSK-01…14 |
| FR-6 Performance | `modules/performance_analysis.py` | T-PERF-01…06 |
| FR-7.1/7.2/7.3 | `utils/validation.py`, `utils/logger.py` | T-VAL-01…16, T-LOG-01…03 |
| NFR-1 correctness | all modules | hand-computed expected values |
| NFR-6 portability | `scripts/*.sh` | manual run on Git Bash/WSL |

---

## 14. Risk Register

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Metric definitions drift between code and report | Loses marks for inconsistency | Medium | Section 9 conventions are the contract; metrics computed in one helper per module |
| Round Robin off-by-one on mid-quantum arrivals | Wrong waiting times | Medium | Tested against hand calculation, explicit test `T-CPU-…` |
| Fragmentation numbers look "wrong" without a stated model | Viva challenge | Medium | Two models, both defined in Section 9.2 and printed with results |
| Matplotlib unavailable on examiner's machine | No charts | Low | Graceful fallback (FR-7.6); charts already exported as PNG in `screenshots/` |
| `report.pdf` generation needs a tool | Phase 5 gap | Medium | Try `reportlab`; otherwise generate PDF from Markdown with a documented, dependency-free path |
| Bash scripts fail on Windows | Setup friction | Medium | POSIX-only syntax, no GNU-only flags, tested under `bash`; README documents Git Bash/WSL |
| Scope creep (GUI, DB, extra algorithms) | Project unfinished | Medium | Section 3.2 exclusion list is binding |

---

## 15. Phase 1 Deliverables Checklist

- [x] Problem statement
- [x] Objectives (O1–O10)
- [x] Scope, including explicit exclusions
- [x] Functional requirements (FR-1 … FR-7, 44 requirements)
- [x] Non-functional requirements (NFR-1 … NFR-10)
- [x] System architecture (layered diagram + principles)
- [x] Module descriptions (4 modules + analysis + support)
- [x] Input/output workflow with artefact list
- [x] Data structures (dataclasses + persistence format)
- [x] Algorithm selection with complexity justification
- [x] Metric formulas
- [x] Implementation plan mapped to the 5 phases and 100 marks
- [x] Traceability matrix and risk register
- [x] Folder skeleton created on disk
- [ ] Student confirmation to begin Phase 2

---

*Next phase, on your confirmation: build `modules/cpu_scheduling.py` and run it before moving on.*
