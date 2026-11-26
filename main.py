#!/usr/bin/env python3
"""
OS Resource Management Simulator — integrated terminal application
==================================================================

A single menu drives the four subsystems:

    1  CPU Scheduling       FCFS, SJF, SRTF, Priority, Round Robin
    2  Memory Management    First Fit, Best Fit, Worst Fit (fixed / dynamic)
    3  Deadlock Management  Banker's safety, resource request, detection
    4  Disk Scheduling      FCFS, SSTF, SCAN, C-SCAN
    5  Performance Analysis comparison tables + charts for all four
    6  View Execution Logs  entries of the current session
    7  Exit

Design: this is the ONLY file that reads the keyboard or prints application
output. Every algorithm lives in ``modules/`` as a pure function, validation
of raw text lives in ``utils/validation.py``, formatting/charts live in
``utils/report_generator.py`` and the session log in ``utils/logger.py``.

Command line:
    python3 main.py            interactive menu
    python3 main.py --report   rebuild report.pdf from real runs, then exit
    python3 main.py --help     show this help
"""

from __future__ import annotations

import datetime
import platform
import subprocess
import sys
from pathlib import Path

from modules import cpu_scheduling as cpu
from modules import deadlock_management as deadlock
from modules import disk_scheduling as disk
from modules import memory_management as memory
from utils import report_generator as report
from utils.logger import Logger
from utils.validation import (
    choose,
    describe_dataset,
    list_datasets,
    parse_int,
    parse_int_list,
    parse_pid_vector,
)

# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "outputs"
CHART_DIR = OUTPUT_DIR / "charts"
LOG_DIR = OUTPUT_DIR / "logs"
REPORT_DIR = OUTPUT_DIR / "reports"
REPORT_PATH = ROOT / "report.pdf"

CUSTOM = "<custom>"
BACK = "<back>"
RULE = "=" * 78


# ---------------------------------------------------------------------------
# Small input helpers (the only place in the project that calls input())
# ---------------------------------------------------------------------------
def ask(prompt: str, default: str | None = None) -> str:
    """Read one line; an empty answer returns ``default`` (or "")."""
    suffix = f" [{default}]" if default is not None else ""
    try:
        raw = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:                               # piped input ended
        print()
        return default if default is not None else ""
    if not raw:
        return default if default is not None else ""
    return raw


def ask_int(
    prompt: str, default: int | None = None, minimum: int | None = None, maximum: int | None = None
) -> int:
    """Ask until the answer is an integer in range."""
    default_text = str(default) if default is not None else None
    while True:
        raw = ask(prompt, default_text)
        try:
            return parse_int(raw, prompt, minimum, maximum)
        except ValueError as exc:
            print(f"    ! {exc}")


def ask_choice(prompt: str, options: list[str], default: str | None = None) -> str:
    """Ask until the answer matches one of ``options`` (case-insensitive)."""
    while True:
        raw = ask(f"{prompt} ({'/'.join(options)})", default)
        try:
            return choose(raw, options, prompt)
        except ValueError as exc:
            print(f"    ! {exc}")


def ask_yes_no(prompt: str, default: bool = False) -> bool:
    """Ask a yes/no question; returns ``default`` on an empty answer."""
    answer = ask(f"{prompt} (y/n)", "y" if default else "n").strip().lower()
    return answer.startswith("y")


def pause() -> None:
    """Wait for Enter so long output is readable before the menu redraws."""
    try:
        input("\n  Press Enter to continue...")
    except EOFError:
        print()


def heading(title: str) -> None:
    """Print a bordered section title."""
    print()
    print(RULE)
    print(title)
    print(RULE)


# ---------------------------------------------------------------------------
# Dataset selection and custom entry
# ---------------------------------------------------------------------------
def choose_dataset(prefix: str, label: str) -> Path | str | None:
    """Let the user pick one of the sample datasets or type a custom one.

    Returns:
        A :class:`Path` for a file, ``CUSTOM`` to enter data by hand, or
        ``None`` when the user chooses to go back.
    """
    files = list_datasets(DATA_DIR, prefix)
    print(f"\n  {label} datasets:")
    if files:
        for i, path in enumerate(files, start=1):
            print(f"   {i}) {describe_dataset(path)}")
    else:
        print("   (no dataset files found in data/)")
    print("   0) back to the main menu")
    print("   c) enter a custom dataset now")

    while True:
        raw = ask("Choose").strip().lower()
        if raw in ("0", "b", "back"):
            return None
        if raw in ("c", "custom"):
            return CUSTOM
        try:
            index = parse_int(raw, "dataset number", 1, len(files)) if files else None
        except ValueError:
            index = None
        if index is not None:
            return files[index - 1]
        print("    ! enter a listed number, 0 to go back, or c for custom input")


def _prompt_cpu_processes() -> list[cpu.Process]:
    """Read a process table from the keyboard."""
    count = ask_int("Number of processes", 5, 1, 100)
    processes: list[cpu.Process] = []
    seen: set[str] = set()
    for i in range(count):
        pid = ask(f"Process {i + 1} id", f"P{i + 1}")
        while not pid or pid in seen:
            pid = ask(f"Process {i + 1} id (must be new)", f"P{i + 1}")
        seen.add(pid)
        arrival = ask_int(f"{pid} arrival time", 0, 0)
        burst = ask_int(f"{pid} burst time", 1, 1)
        priority = ask_int(f"{pid} priority (1 = highest)", 1, 0)
        processes.append(cpu.Process(pid, arrival, burst, priority))
    return processes


def _prompt_memory_problem() -> tuple[list[int], list[memory.MemoryProcess]]:
    """Read partition sizes and process requests from the keyboard."""
    while True:
        raw = ask("Partition sizes (space separated)", "100 500 200 300 600")
        try:
            partitions = parse_int_list(raw, "partition sizes", 1)
            break
        except ValueError as exc:
            print(f"    ! {exc}")
    count = ask_int("Number of processes", 4, 1, 100)
    processes: list[memory.MemoryProcess] = []
    seen: set[str] = set()
    for i in range(count):
        pid = ask(f"Process {i + 1} id", f"P{i + 1}")
        while not pid or pid in seen:
            pid = ask(f"Process {i + 1} id (must be new)", f"P{i + 1}")
        seen.add(pid)
        size = ask_int(f"{pid} memory request", 200, 1)
        processes.append(memory.MemoryProcess(pid, size))
    return partitions, processes


def _prompt_disk_problem() -> tuple[int, int, list[int]]:
    """Read head, disk size and the request queue from the keyboard."""
    while True:
        disk_size = ask_int("Number of cylinders", disk.DEFAULT_DISK_SIZE, 2)
        head = ask_int("Current head cylinder", 53, 0, disk_size - 1)
        raw = ask("Requested cylinders (space separated)", "98 183 37 122 14 124 65 67")
        try:
            requests = parse_int_list(raw, "requests", 0, disk_size - 1)
            return head, disk_size, requests
        except ValueError as exc:
            print(f"    ! {exc}")


def _prompt_deadlock_state() -> deadlock.BankersState:
    """Read a Banker's state (pids, available, allocation and max rows)."""
    count = ask_int("Number of processes", 3, 1, 20)
    resources = ask_int("Number of resource types", 2, 1, len(deadlock.DEFAULT_RESOURCES))
    names = list(deadlock.DEFAULT_RESOURCES[:resources])
    print(f"    resource types: {', '.join(names)}")

    pids: list[str] = []
    for i in range(count):
        pid = ask(f"Process {i + 1} id", f"P{i + 1}")
        while not pid or pid in pids:
            pid = ask(f"Process {i + 1} id (must be new)", f"P{i + 1}")
        pids.append(pid)

    while True:
        raw = ask(f"Available ({len(names)} values)", " ".join(["0"] * len(names)))
        try:
            available = parse_int_list(raw, "available vector", 0)
            if len(available) != len(names):
                raise ValueError(f"available needs {len(names)} value(s)")
            break
        except ValueError as exc:
            print(f"    ! {exc}")

    allocation: list[list[int]] = []
    maximum: list[list[int]] = []
    for pid in pids:
        while True:
            raw = ask(f"{pid} allocation", " ".join(["0"] * len(names)))
            try:
                row = parse_int_list(raw, f"{pid} allocation", 0)
                if len(row) != len(names):
                    raise ValueError(f"{pid} allocation needs {len(names)} value(s)")
                allocation.append(row)
                break
            except ValueError as exc:
                print(f"    ! {exc}")
        while True:
            raw = ask(f"{pid} maximum claim", " ".join(str(v + 1) for v in allocation[-1]))
            try:
                row = parse_int_list(raw, f"{pid} max", 0)
                if len(row) != len(names):
                    raise ValueError(f"{pid} max needs {len(names)} value(s)")
                maximum.append(row)
                break
            except ValueError as exc:
                print(f"    ! {exc}")

    return deadlock.make_state(pids, allocation, maximum, available)


# ---------------------------------------------------------------------------
# Chart helper
# ---------------------------------------------------------------------------
def save_chart(logger: Logger, label: str, func, *args, **kwargs) -> Path | None:
    """Call a chart function, logging success or failure, never crashing."""
    if not report.charts_available():
        return None
    try:
        path = func(*args, **kwargs)
    except Exception as exc:                       # a chart must never end the session
        logger.error(f"chart {label} failed: {exc}")
        print(f"    ! chart {label} could not be drawn: {exc}")
        return None
    if path is not None:
        logger.info("CHART", f"saved {path.name}")
        print(f"    chart saved: outputs/charts/{path.name}")
    return path


# ---------------------------------------------------------------------------
# 1. CPU scheduling
# ---------------------------------------------------------------------------
def cpu_menu(logger: Logger) -> None:
    """Choose a CPU dataset, run all five algorithms, compare and chart."""
    heading("CPU SCHEDULING")
    source = choose_dataset("cpu", "CPU")
    if source is None:
        return
    if source == CUSTOM:
        processes = _prompt_cpu_processes()
        label = "custom input"
    else:
        processes = cpu.load_processes(source)
        label = source.name

    quantum = ask_int("Round Robin time quantum", cpu.DEFAULT_QUANTUM, 1)
    logger.section(f"CPU scheduling on {label}")
    logger.info("CPU", f"{len(processes)} processes, quantum={quantum}, "
                       f"total burst={sum(p.burst for p in processes)}")

    results = {name: cpu.run_algorithm(name, processes, quantum=quantum) for name in cpu.ALGORITHMS}

    for res in results.values():
        heading(f"{label} — {res.algorithm}"
                + (f" (quantum {res.quantum})" if res.quantum is not None else ""))
        print(report.format_cpu_result(res))
        logger.info(
            "CPU",
            f"{res.algorithm}: avgWT={res.avg_waiting:.2f} avgTAT={res.avg_turnaround:.2f} "
            f"avgRT={res.avg_response:.2f} util={res.cpu_utilisation:.2f}% "
            f"throughput={res.throughput:.4f} span={res.total_time}",
        )
        save_chart(logger, f"gantt-{res.algorithm}", report.save_gantt, res,
                   CHART_DIR / f"gantt_{res.algorithm.lower()}.png", f"{res.algorithm} — {label}")

    heading(f"{label} — COMPARISON")
    print(report.format_cpu_comparison(results))
    save_chart(logger, "cpu-comparison", report.save_cpu_comparison, results,
               CHART_DIR / "cpu_comparison.png", f"CPU comparison — {label}")
    pause()


# ---------------------------------------------------------------------------
# 2. Memory management
# ---------------------------------------------------------------------------
def memory_menu(logger: Logger) -> None:
    """Choose a memory dataset and model, run the three fit strategies."""
    heading("MEMORY MANAGEMENT")
    source = choose_dataset("memory", "Memory")
    if source is None:
        return
    if source == CUSTOM:
        partitions, processes = _prompt_memory_problem()
        label = "custom input"
    else:
        partitions, processes = memory.load_memory_dataset(source)
        label = source.name

    model = ask_choice("Allocation model", list(memory.MODELS), "fixed")
    logger.section(f"Memory management on {label} ({model} model)")
    logger.info("MEMORY", f"partitions={partitions} total={sum(partitions)} "
                          f"requests={[p.size for p in processes]} model={model}")

    results = {
        name: memory.run_algorithm(name, partitions, processes, model=model)
        for name in memory.ALGORITHMS
    }
    for res in results.values():
        heading(f"{label} — {res.algorithm} ({model})")
        print(report.format_memory_result(res))
        logger.info(
            "MEMORY",
            f"{res.algorithm}/{model}: placed={res.allocated_count}/{len(res.allocations)} "
            f"util={res.utilisation:.2f}% int={res.internal_frag} ext={res.external_frag} "
            f"free={res.free_memory}",
        )

    heading(f"{label} — COMPARISON ({model})")
    print(report.format_memory_comparison(results, model))
    save_chart(logger, "memory-comparison", report.save_memory_comparison, results,
               CHART_DIR / f"memory_{model}_comparison.png", model)
    pause()


# ---------------------------------------------------------------------------
# 3. Deadlock management
# ---------------------------------------------------------------------------
def deadlock_menu(logger: Logger) -> None:
    """Load a Banker's state, run safety + detection, then try a request."""
    heading("DEADLOCK MANAGEMENT")
    source = choose_dataset("deadlock", "Deadlock")
    if source is None:
        return
    if source == CUSTOM:
        state = _prompt_deadlock_state()
        label = "custom input"
    else:
        state = deadlock.load_deadlock_dataset(source)
        label = source.name

    logger.section(f"Deadlock management on {label}")
    logger.info("DEADLOCK", f"processes={list(state.pids)} available={state.available}")

    heading(f"{label} — RESOURCE STATE")
    print(report.format_deadlock_state(state))

    heading(f"{label} — BANKER'S SAFETY ALGORITHM")
    safety = deadlock.check_safety(state)
    print(report.format_safety(safety))
    logger.info("DEADLOCK", f"safety: {safety.summary}")

    heading(f"{label} — DEADLOCK DETECTION")
    detection = deadlock.detect_deadlock(state)
    print(report.format_detection(detection))
    logger.info("DEADLOCK", f"detection: {detection.summary}")

    if ask_yes_no("Test a resource request with Banker's algorithm", default=False):
        heading(f"{label} — RESOURCE REQUEST")
        while True:
            raw = ask("Request as 'PID v1 v2 ...'", f"{state.pids[0]} "
                      + " ".join(["0"] * state.resource_count))
            try:
                pid, vector = parse_pid_vector(raw, "resource request")
                result = deadlock.request_resources(state, pid, vector)
                print(report.format_request(result))
                logger.info("DEADLOCK", f"request {pid} {vector}: "
                                        f"{'GRANTED' if result.granted else 'REFUSED'}")
                if result.granted and ask_yes_no("Adopt the granted state for another request?"):
                    state = result.state
                break
            except ValueError as exc:
                print(f"    ! {exc}")
                if not ask_yes_no("Try another request", default=True):
                    break
    pause()


# ---------------------------------------------------------------------------
# 4. Disk scheduling
# ---------------------------------------------------------------------------
def disk_menu(logger: Logger) -> None:
    """Choose a disk dataset, run all four algorithms, compare and chart."""
    heading("DISK SCHEDULING")
    source = choose_dataset("disk", "Disk")
    if source is None:
        return
    if source == CUSTOM:
        head, disk_size, requests = _prompt_disk_problem()
        label = "custom input"
    else:
        head, disk_size, requests = disk.load_disk_dataset(source)
        label = source.name

    direction = ask_choice("Sweep direction for SCAN / C-SCAN", list(disk.DIRECTIONS), "up")
    logger.section(f"Disk scheduling on {label} (head {head}, direction {direction})")
    logger.info("DISK", f"head={head} disk_size={disk_size} requests={requests} direction={direction}")

    results = {
        name: disk.run_algorithm(name, requests, head, disk_size, direction)
        for name in disk.ALGORITHMS
    }
    for res in results.values():
        heading(f"{label} — {disk.ALGORITHMS[res.algorithm]}")
        print(report.format_disk_result(res))
        logger.info(
            "DISK",
            f"{res.algorithm}: total={res.total_movement} avg={res.average_movement:.2f} "
            f"jump={res.return_jump} order={res.order}",
        )

    heading(f"{label} — COMPARISON")
    print(report.format_disk_comparison(results))
    save_chart(logger, "disk-comparison", report.save_disk_comparison, results,
               CHART_DIR / "disk_comparison.png")
    save_chart(logger, "disk-paths", report.save_disk_paths, results,
               CHART_DIR / "disk_paths.png", head)
    pause()


# ---------------------------------------------------------------------------
# 5. Performance analysis (all four modules, sample datasets)
# ---------------------------------------------------------------------------
def performance_menu(logger: Logger) -> None:
    """Run every subsystem on its sample dataset and compare the results."""
    heading("PERFORMANCE ANALYSIS — ALL FOUR SUBSYSTEMS")
    quantum = cpu.DEFAULT_QUANTUM
    logger.section("Performance analysis across all subsystems")

    # --- CPU ------------------------------------------------------------
    cpu_path = DATA_DIR / "cpu_sample.txt"
    print(f"\nCPU — dataset {cpu_path.name}, Round Robin quantum {quantum}")
    processes = cpu.load_processes(cpu_path)
    cpu_results = {
        name: cpu.run_algorithm(name, processes, quantum=quantum) for name in cpu.ALGORITHMS
    }
    print(report.format_cpu_comparison(cpu_results))
    logger.info("CPU", f"comparison: {[(n, round(r.avg_waiting, 2)) for n, r in cpu_results.items()]}")
    save_chart(logger, "cpu-comparison", report.save_cpu_comparison, cpu_results,
               CHART_DIR / "cpu_comparison.png", "CPU comparison — cpu_sample.txt")

    # --- Memory ---------------------------------------------------------
    mem_path = DATA_DIR / "memory_sample.txt"
    partitions, mem_processes = memory.load_memory_dataset(mem_path)
    for model in memory.MODELS:
        print(f"\nMEMORY — dataset {mem_path.name}, model {model}")
        mem_results = {
            name: memory.run_algorithm(name, partitions, mem_processes, model=model)
            for name in memory.ALGORITHMS
        }
        print(report.format_memory_comparison(mem_results, model))
        logger.info("MEMORY", f"{model}: {[(n, round(r.utilisation, 2)) for n, r in mem_results.items()]}")
        save_chart(logger, f"memory-{model}", report.save_memory_comparison, mem_results,
                   CHART_DIR / f"memory_{model}_comparison.png", model)

    # --- Deadlock -------------------------------------------------------
    dl_path = DATA_DIR / "deadlock_sample.txt"
    state = deadlock.load_deadlock_dataset(dl_path)
    safety = deadlock.check_safety(state)
    detection = deadlock.detect_deadlock(state)
    print(f"\nDEADLOCK — dataset {dl_path.name}")
    print(f"  Safety    : {safety.summary}")
    print(f"  Detection : {detection.summary}")
    logger.info("DEADLOCK", f"performance: {safety.summary}; {detection.summary}")

    # --- Disk -----------------------------------------------------------
    disk_path = DATA_DIR / "disk_sample.txt"
    head, disk_size, requests = disk.load_disk_dataset(disk_path)
    print(f"\nDISK — dataset {disk_path.name}, head {head}, direction up")
    disk_results = {
        name: disk.run_algorithm(name, requests, head, disk_size, "up") for name in disk.ALGORITHMS
    }
    print(report.format_disk_comparison(disk_results))
    logger.info("DISK", "comparison: "
                f"{[(n, r.total_movement) for n, r in disk_results.items()]}")
    save_chart(logger, "disk-comparison", report.save_disk_comparison, disk_results,
               CHART_DIR / "disk_comparison.png")
    save_chart(logger, "disk-paths", report.save_disk_paths, disk_results,
               CHART_DIR / "disk_paths.png", head)

    if not report.charts_available():
        print(f"\n  ! charts skipped: {report.matplotlib_error() or 'matplotlib not installed'}")
    print(f"\n  Charts are in outputs/charts/. Run 'python3 main.py --report' for report.pdf.")
    pause()


# ---------------------------------------------------------------------------
# 6. Execution logs
# ---------------------------------------------------------------------------
def logs_menu(logger: Logger) -> None:
    """Show the current session's log entries and the log file location."""
    heading("EXECUTION LOGS")
    if logger.path is not None:
        print(f"  Log file: {logger.path.relative_to(ROOT) if logger.path.is_relative_to(ROOT) else logger.path}")
    if logger.file_error:
        print(f"  ! {logger.file_error}")
    files = sorted(LOG_DIR.glob("*.log")) if LOG_DIR.is_dir() else []
    print(f"  Log files in outputs/logs/: {len(files)}")
    print(f"  Entries this session: {len(logger.entries)}")
    print("\n  Last 30 entries:")
    for line in logger.tail(30):
        print("   " + line)
    pause()


# ---------------------------------------------------------------------------
# PDF report
# ---------------------------------------------------------------------------
def build_pdf_report(logger: Logger) -> Path | None:
    """Rebuild ``report.pdf`` from freshly executed algorithms and real tests."""
    heading("BUILDING report.pdf")
    logger.section("PDF report generation")
    sections: list[tuple[str, list[str]]] = []

    sections.append((
        "1. Project overview",
        [
            "OS Resource Management Simulator",
            "B.Tech CSE Operating Systems capstone project",
            "",
            f"Generated: {platform.node() or 'local machine'} on "
            + datetime.datetime.now().strftime("%d %B %Y, %H:%M"),
            f"Python {platform.python_version()} | matplotlib "
            + report.matplotlib_version(),
            "",
            "Subsystems implemented:",
            "  CPU scheduling      FCFS, SJF, SRTF, Priority, Round Robin",
            "  Memory management   First Fit, Best Fit, Worst Fit (fixed + dynamic models)",
            "  Deadlock management Banker's safety, resource request, deadlock detection",
            "  Disk scheduling     FCFS, SSTF, SCAN, C-SCAN",
            "",
            "All numbers in this report are produced by running the algorithms on the",
            "datasets in data/ during this build. Nothing is typed in by hand.",
        ],
    ))

    # CPU ---------------------------------------------------------------
    processes = cpu.load_processes(DATA_DIR / "cpu_sample.txt")
    quantum = cpu.DEFAULT_QUANTUM
    cpu_results = {n: cpu.run_algorithm(n, processes, quantum=quantum) for n in cpu.ALGORITHMS}
    cpu_lines = [
        f"Dataset: cpu_sample.txt ({len(processes)} processes, quantum {quantum})",
        "Columns: AT arrival, BT burst, PRI priority, CT completion, TAT turnaround,",
        "WT waiting, RT response. All times are integer time units.",
        "",
    ]
    for res in cpu_results.values():
        cpu_lines.append(report.format_cpu_result(res))
        cpu_lines.append("")
    cpu_lines.append("Comparison")
    cpu_lines.append(report.format_cpu_comparison(cpu_results))
    sections.append(("2. CPU scheduling", cpu_lines))

    # Memory ------------------------------------------------------------
    partitions, mem_processes = memory.load_memory_dataset(DATA_DIR / "memory_sample.txt")
    mem_lines = [
        f"Dataset: memory_sample.txt — partitions {partitions} (total {sum(partitions)})",
        f"Requests: {[(p.pid, p.size) for p in mem_processes]}",
        "",
        "Internal fragmentation = sum(block size - process size) in the fixed model.",
        "External fragmentation = free memory in blocks smaller than the smallest",
        "rejected request (0 when nothing was rejected).",
        "",
    ]
    for model in memory.MODELS:
        mem_results = {
            n: memory.run_algorithm(n, partitions, mem_processes, model=model)
            for n in memory.ALGORITHMS
        }
        mem_lines.append(f"Model: {model}")
        for res in mem_results.values():
            mem_lines.append(report.format_memory_result(res))
            mem_lines.append("")
        mem_lines.append(report.format_memory_comparison(mem_results, model))
        mem_lines.append("")
    sections.append(("3. Memory management", mem_lines))

    # Deadlock ----------------------------------------------------------
    state = deadlock.load_deadlock_dataset(DATA_DIR / "deadlock_sample.txt")
    safety = deadlock.check_safety(state)
    detection = deadlock.detect_deadlock(state)
    request_lines = []
    for pid, vector in (("P1", (1, 0, 2)), ("P4", (3, 3, 0))):
        try:
            request_lines.append(report.format_request(deadlock.request_resources(state, pid, vector)))
        except ValueError as exc:
            request_lines.append(f"{pid}: rejected input — {exc}")
    sections.append((
        "4. Deadlock management",
        [
            "Dataset: deadlock_sample.txt (Silberschatz P0-P4; A=10, B=5, C=7; Available 3 3 2)",
            "",
            report.format_deadlock_state(state),
            "",
            "Banker's safety algorithm",
            report.format_safety(safety),
            "",
            "Banker's resource-request algorithm",
            *request_lines,
            "",
            "Deadlock detection (Request = Need fallback)",
            report.format_detection(detection),
        ],
    ))

    # Disk --------------------------------------------------------------
    head, disk_size, requests = disk.load_disk_dataset(DATA_DIR / "disk_sample.txt")
    disk_results = {
        n: disk.run_algorithm(n, requests, head, disk_size, "up") for n in disk.ALGORITHMS
    }
    disk_lines = [
        f"Dataset: disk_sample.txt — head {head}, {disk_size} cylinders",
        f"Requests: {requests}",
        "",
    ]
    for res in disk_results.values():
        disk_lines.append(report.format_disk_result(res))
        disk_lines.append("")
    disk_lines.append(report.format_disk_comparison(disk_results))
    sections.append(("5. Disk scheduling", disk_lines))

    # Tests -------------------------------------------------------------
    test_lines: list[str] = []
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "unittest", "discover", "-s", "tests", "-v"],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
        output = (proc.stdout + proc.stderr).strip().splitlines()
        test_lines.append("Command: python3 -m unittest discover -s tests -v")
        test_lines.append(f"Exit status: {proc.returncode}")
        test_lines.append("")
        test_lines.extend(output[-26:])
        logger.info("REPORT", f"unittest exit status {proc.returncode}")
    except Exception as exc:
        test_lines.append(f"Tests could not be run: {exc}")
        logger.error(f"report test run failed: {exc}")
    sections.append(("6. Verification — unit test output", test_lines))

    sections.append((
        "7. Assumptions and limitations",
        [
            "CPU: the clock starts at the first arrival, so sum(IDLE segments) equals",
            "     idle_time and CPU utilisation is exact. Priority 1 is the highest.",
            "     Ties are broken by arrival time, then by input order.",
            "",
            "Memory: fixed model gives a process a whole partition (internal",
            "        fragmentation); dynamic model splits holes and merges nothing",
            "        (external fragmentation). Both use the definitions above.",
            "",
            "Deadlock: Need is derived as Max - Allocation. A request above Need is",
            "          rejected as invalid input, not as a deadlock verdict.",
            "",
            "Disk: C-SCAN's return jump is recorded separately and not counted in",
            "      the total movement; the charged value is printed alongside.",
            "",
            "Charts need matplotlib; without it the simulator still prints every table.",
        ],
    ))

    try:
        path = report.generate_pdf_report(sections, REPORT_PATH)
    except RuntimeError as exc:
        logger.error(f"PDF generation failed: {exc}")
        print(f"  ! {exc}")
        return None
    logger.info("REPORT", f"wrote {path.name} with {len(sections)} sections")
    print(f"  report.pdf written to the project root ({path.name}).")
    return path


# ---------------------------------------------------------------------------
# Menu
# ---------------------------------------------------------------------------
MENU = """
  1) CPU Scheduling        FCFS, SJF, SRTF, Priority, Round Robin
  2) Memory Management     First Fit, Best Fit, Worst Fit (fixed/dynamic)
  3) Deadlock Management   Banker's safety, request algorithm, detection
  4) Disk Scheduling       FCFS, SSTF, SCAN, C-SCAN
  5) Performance Analysis  compare all four subsystems + charts
  6) View Execution Logs   this session's entries and log file
  7) Exit
"""


def banner(logger: Logger) -> None:
    """Print the application header once per session."""
    print(RULE)
    print("                     OS RESOURCE MANAGEMENT SIMULATOR")
    print("                  B.Tech CSE Operating Systems Capstone")
    print(RULE)
    charts = "available" if report.charts_available() else "unavailable (text output only)"
    print(f"  datasets: {len(list_datasets(DATA_DIR))} file(s) in data/"
          f"   charts: {charts}   log: {logger.path.name if logger.path else 'disabled'}")
    print(f"  report.pdf: {'present' if REPORT_PATH.is_file() else 'not built yet'}")


def interactive(logger: Logger) -> None:
    """Main menu loop; returns when the user chooses Exit."""
    banner(logger)
    actions = {
        "1": ("CPU Scheduling", cpu_menu),
        "2": ("Memory Management", memory_menu),
        "3": ("Deadlock Management", deadlock_menu),
        "4": ("Disk Scheduling", disk_menu),
        "5": ("Performance Analysis", performance_menu),
        "6": ("Execution Logs", logs_menu),
    }
    while True:
        print(MENU)
        try:
            choice = ask("Select an option", "7").strip().lower()
        except KeyboardInterrupt:
            print("\n  Interrupted — exiting.")
            break

        if choice in ("7", "q", "quit", "exit"):
            print("\n  Session ended. Log file: "
                  + (str(logger.path.relative_to(ROOT)) if logger.path else "disabled"))
            break

        entry = actions.get(choice)
        if entry is None:
            print("  ! enter a number from 1 to 7")
            continue

        title, handler = entry
        logger.info("MENU", f"selected {choice} ({title})")
        try:
            handler(logger)
        except (ValueError, TypeError, FileNotFoundError, RuntimeError) as exc:
            logger.error(f"{title}: {exc}")
            print(f"\n  ! {exc}")
            pause()
        except KeyboardInterrupt:
            print("\n  (cancelled — back to the menu)")
            logger.info("MENU", f"{title} cancelled by the user")


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit status."""
    args = list(sys.argv[1:] if argv is None else argv)

    if "--help" in args or "-h" in args:
        print(__doc__)
        return 0

    logger = Logger(LOG_DIR)
    if logger.file_error:
        print(f"  ! {logger.file_error}")
    try:
        if "--report" in args:
            print(RULE)
            print("  Building report.pdf from real algorithm runs and test results")
            print(RULE)
            return 0 if build_pdf_report(logger) else 1
        interactive(logger)
        return 0
    except KeyboardInterrupt:
        print("\n  Interrupted.")
        return 130
    finally:
        logger.close()


if __name__ == "__main__":
    raise SystemExit(main())
