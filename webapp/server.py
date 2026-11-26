#!/usr/bin/env python3
"""
Web GUI backend for the OS Resource Management Simulator
========================================================

The terminal application (``main.py``) and this GUI are two front ends over the
*same* engines: nothing is re-implemented here. This module only

    1. parses a JSON request from the browser,
    2. hands the data to ``modules/cpu_scheduling.py``,
       ``modules/memory_management.py``, ``modules/deadlock_management.py`` or
       ``modules/disk_scheduling.py``,
    3. serialises the dataclass results back to JSON.

It uses the Python standard library only (``http.server``), so the GUI adds no
new dependency to ``requirements.txt``. Charts are drawn in the browser with
CSS/SVG, which is why no Matplotlib work happens on this side.

Run it with::

    python3 webapp/server.py                 # http://127.0.0.1:8000
    python3 webapp/server.py --port 9000
    python3 webapp/server.py --host 0.0.0.0  # reachable from another machine

API
---
GET  /api/meta          dataset catalogue, algorithm names, limits
POST /api/cpu           {dataset|text, algorithm, quantum}
POST /api/memory        {dataset|text, model, algorithm}
POST /api/deadlock      {dataset|text, action, pid?, request?}
POST /api/disk          {dataset|text, algorithm, direction}

Every POST answers ``{"ok": true, "data": ...}`` or, on bad input,
``{"ok": false, "error": "..."}`` with HTTP 400.
"""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

# The project root is the parent of webapp/, so `python3 webapp/server.py`
# works from any working directory.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = Path(__file__).resolve().parent / "static"
DATA_DIR = PROJECT_ROOT / "data"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from modules import cpu_scheduling as cpu            # noqa: E402
from modules import deadlock_management as deadlock  # noqa: E402
from modules import disk_scheduling as disk          # noqa: E402
from modules import memory_management as memory      # noqa: E402

CPU_LABELS = {
    "FCFS": "FCFS",
    "SJF": "SJF",
    "SRTF": "SRTF",
    "PRIORITY": "Priority",
    "RR": "Round Robin",
}
MEMORY_LABELS = {"FIRST": "First Fit", "BEST": "Best Fit", "WORST": "Worst Fit"}
DISK_LABELS = {"FCFS": "FCFS", "SSTF": "SSTF", "SCAN": "SCAN", "CSCAN": "C-SCAN"}

MAX_BODY_BYTES = 256 * 1024


# ---------------------------------------------------------------------------
# Dataset handling
# ---------------------------------------------------------------------------
def dataset_path(name: str) -> Path:
    """Resolve a dataset *name* to a file inside ``data/`` (no path traversal)."""
    if not isinstance(name, str) or not name.strip():
        raise ValueError("dataset name is empty")
    candidate = (DATA_DIR / name.strip()).resolve()
    if candidate.parent != DATA_DIR.resolve() or not candidate.is_file():
        raise ValueError(f"unknown dataset {name!r}; pick one of the files in data/")
    return candidate


def dataset_catalogue() -> dict[str, list[dict[str, str]]]:
    """Every dataset, grouped by the subsystem that reads it."""
    groups: dict[str, list[dict[str, str]]] = {
        "cpu": [], "memory": [], "deadlock": [], "disk": [],
    }
    # Textbook samples first (so a picker opens on the sample dataset), then the
    # alternative workloads, each group alphabetically.
    files = sorted(
        DATA_DIR.glob("*.txt"),
        key=lambda p: (0 if "sample" in p.stem else 1, p.name),
    )
    for path in files:
        if path.name.startswith("cpu"):
            kind = "cpu"
        elif path.name.startswith("memory"):
            kind = "memory"
        elif path.name.startswith("deadlock"):
            kind = "deadlock"
        elif path.name.startswith("disk"):
            kind = "disk"
        else:
            continue
        text = path.read_text(encoding="utf-8")
        first_comment = next(
            (ln.lstrip("# ").strip() for ln in text.splitlines() if ln.startswith("#")),
            path.stem,
        )
        groups[kind].append(
            {"name": path.name, "note": first_comment, "text": text}
        )
    return groups


def source_text(payload: dict) -> str:
    """The dataset text: the browser's editor content, else the chosen file."""
    text = payload.get("text")
    if isinstance(text, str) and text.strip():
        return text
    name = payload.get("dataset")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("pick a dataset or paste one into the editor")
    return dataset_path(name).read_text(encoding="utf-8")


def algorithm_list(payload: dict, known: dict[str, str]) -> list[str]:
    """``ALL`` expands to every algorithm; otherwise validate one name."""
    requested = str(payload.get("algorithm", "ALL")).strip().upper()
    if requested in ("ALL", ""):
        return list(known)
    if requested not in known:
        raise ValueError(
            f"unknown algorithm {requested!r}; choose ALL or {', '.join(known)}"
        )
    return [requested]


def _as_int(payload: dict, key: str, default: int, low: int, high: int) -> int:
    raw = payload.get(key, default)
    if isinstance(raw, bool):
        raise ValueError(f"{key} must be an integer")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"{key} must be an integer") from None
    if not low <= value <= high:
        raise ValueError(f"{key} must be between {low} and {high}")
    return value


# ---------------------------------------------------------------------------
# Serialisers: dataclass -> JSON-ready dict
# ---------------------------------------------------------------------------
def cpu_result_dict(res: cpu.CpuScheduleResult) -> dict:
    return {
        "name": res.algorithm,
        "label": CPU_LABELS.get(res.algorithm, res.algorithm),
        "quantum": res.quantum,
        "rows": [
            {
                "pid": r.pid,
                "arrival": r.arrival,
                "burst": r.burst,
                "priority": r.priority,
                "completion": r.completion,
                "turnaround": r.turnaround,
                "waiting": r.waiting,
                "response": r.response,
            }
            for r in res.rows
        ],
        "gantt": [{"pid": p, "start": s, "end": e} for p, s, e in res.gantt],
        "avg_waiting": round(res.avg_waiting, 2),
        "avg_turnaround": round(res.avg_turnaround, 2),
        "avg_response": round(res.avg_response, 2),
        "cpu_utilisation": round(res.cpu_utilisation, 2),
        "throughput": round(res.throughput, 3),
        "total_time": res.total_time,
        "idle_time": res.idle_time,
    }


def memory_result_dict(res: memory.MemoryResult) -> dict:
    return {
        "name": res.algorithm,
        "label": MEMORY_LABELS.get(res.algorithm, res.algorithm),
        "model": res.model,
        "allocations": [
            {
                "pid": a.pid,
                "size": a.size,
                "block_id": a.block_id,
                "allocated_size": a.allocated_size,
                "internal_frag": a.internal_frag,
                "status": a.status,
                "reason": a.reason,
            }
            for a in res.allocations
        ],
        "blocks": [
            {
                "block_id": b.block_id,
                "size": b.size,
                "pid": b.pid,
                "used": b.used,
                "free": b.is_free,
            }
            for b in res.blocks
        ],
        "total_memory": res.total_memory,
        "usable_memory": res.usable_memory,
        "allocated_memory": res.allocated_memory,
        "free_memory": res.free_memory,
        "internal_frag": res.internal_frag,
        "external_frag": res.external_frag,
        "stranded_blocks": res.stranded_blocks,
        "rejected": res.rejected,
        "allocated_count": res.allocated_count,
        "utilisation": round(res.utilisation, 2),
    }


def state_dict(state: deadlock.BankersState) -> dict:
    return {
        "pids": list(state.pids),
        "allocation": [list(row) for row in state.allocation],
        "maximum": [list(row) for row in state.maximum],
        "need": [list(row) for row in state.need],
        "available": list(state.available),
        "total": list(state.total_resources),
    }


def safety_dict(safety: deadlock.SafetyResult | None) -> dict | None:
    if safety is None:
        return None
    return {
        "safe": safety.safe,
        "sequence": list(safety.sequence),
        "stuck": list(safety.stuck),
        "summary": safety.summary,
        "steps": [
            {
                "pid": s.pid,
                "work_before": list(s.work_before),
                "need": list(s.need),
                "work_after": list(s.work_after),
            }
            for s in safety.steps
        ],
    }


def detection_dict(result: deadlock.DetectionResult) -> dict:
    return {
        "deadlocked": list(result.deadlocked),
        "order": list(result.order),
        "summary": result.summary,
        "request_source": result.request_source,
        "requests": [list(row) for row in result.requests],
        "steps": [
            {
                "pid": s.pid,
                "work_before": list(s.work_before),
                "request": list(s.request),
                "work_after": list(s.work_after),
            }
            for s in result.steps
        ],
    }


def disk_result_dict(res: disk.DiskResult) -> dict:
    requests = len(res.requests)
    return {
        "name": res.algorithm,
        "label": DISK_LABELS.get(res.algorithm, res.algorithm),
        "head": res.head,
        "disk_size": res.disk_size,
        "direction": res.direction,
        "order": list(res.order),
        "requests": list(res.requests),
        "movements": [
            {
                "start": m.start,
                "end": m.end,
                "distance": m.distance,
                "is_boundary": m.is_boundary,
            }
            for m in res.movements
        ],
        "total_movement": res.total_movement,
        "average_movement": round(res.total_movement / requests, 2) if requests else 0.0,
        "request_count": requests,
        "return_jump": res.return_jump,
        "charged_movement": res.total_movement + res.return_jump,
        "sequence": [res.head] + [m.end for m in res.movements],
    }


# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------
def api_meta() -> dict:
    return {
        "datasets": dataset_catalogue(),
        "cpu": {
            "algorithms": [{"key": k, "label": v} for k, v in CPU_LABELS.items()],
            "default_quantum": cpu.DEFAULT_QUANTUM,
        },
        "memory": {
            "algorithms": [{"key": k, "label": v} for k, v in MEMORY_LABELS.items()],
            "models": ["fixed", "dynamic"],
        },
        "deadlock": {"actions": ["safety", "request", "detect"]},
        "disk": {
            "algorithms": [{"key": k, "label": v} for k, v in DISK_LABELS.items()],
            "directions": list(disk.DIRECTIONS),
        },
    }


def api_cpu(payload: dict) -> dict:
    processes = cpu.parse_process_lines(source_text(payload).splitlines())
    if not processes:
        raise ValueError("the dataset contains no processes")
    quantum = _as_int(payload, "quantum", cpu.DEFAULT_QUANTUM, 1, 1000)
    results = [
        cpu_result_dict(cpu.run_algorithm(name, processes, quantum))
        for name in algorithm_list(payload, CPU_LABELS)
    ]
    return {"quantum": quantum, "processes": len(processes), "results": results}


def api_memory(payload: dict) -> dict:
    model = str(payload.get("model", "fixed")).strip().lower()
    if model not in ("fixed", "dynamic"):
        raise ValueError("model must be 'fixed' or 'dynamic'")

    text = source_text(payload)
    # The memory module owns its file format, so parse through it rather than
    # duplicating the grammar here.
    import tempfile

    tmp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".txt", delete=False, encoding="utf-8"
        ) as tmp:
            tmp.write(text)
            tmp_name = tmp.name
        partitions, processes = memory.load_memory_dataset(tmp_name)
    finally:
        if tmp_name:
            Path(tmp_name).unlink(missing_ok=True)

    results = [
        memory_result_dict(memory.run_algorithm(name, partitions, processes, model))
        for name in algorithm_list(payload, MEMORY_LABELS)
    ]
    return {
        "model": model,
        "partitions": list(partitions),
        "processes": [{"pid": p.pid, "size": p.size} for p in processes],
        "results": results,
    }


def api_deadlock(payload: dict) -> dict:
    state = deadlock.parse_deadlock_lines(source_text(payload).splitlines())
    action = str(payload.get("action", "safety")).strip().lower()
    response: dict = {"action": action, "state": state_dict(state)}

    if action == "safety":
        response["safety"] = safety_dict(deadlock.check_safety(state))
    elif action == "request":
        pid = payload.get("pid")
        if not isinstance(pid, str) or pid not in state.pids:
            raise ValueError(f"pick a process; known processes: {', '.join(state.pids)}")
        raw = payload.get("request")
        if not isinstance(raw, list) or not raw:
            raise ValueError("enter the request vector, e.g. 1 0 2")
        if len(raw) != state.resource_count:
            raise ValueError(
                f"the request needs {state.resource_count} values "
                f"(one per resource type), got {len(raw)}"
            )
        try:
            vector = [int(v) for v in raw]
        except (TypeError, ValueError):
            raise ValueError("request values must be integers") from None
        result = deadlock.request_resources(state, pid, vector)
        response["request"] = {
            "pid": result.pid,
            "request": list(result.request),
            "granted": result.granted,
            "reason": result.reason,
            "state": state_dict(result.state) if result.state else None,
            "safety": safety_dict(result.safety),
        }
    elif action == "detect":
        response["detection"] = detection_dict(deadlock.detect_deadlock(state))
    else:
        raise ValueError("action must be safety, request or detect")
    return response


def api_disk(payload: dict) -> dict:
    head, disk_size, requests = disk.parse_disk_lines(source_text(payload).splitlines())
    direction = str(payload.get("direction", "up")).strip().lower()
    if direction not in disk.DIRECTIONS:
        raise ValueError("direction must be 'up' or 'down'")

    results = []
    for name in algorithm_list(payload, DISK_LABELS):
        if name in ("SCAN", "CSCAN"):
            res = disk.run_algorithm(name, requests, head, disk_size, direction)
        else:
            res = disk.run_algorithm(name, requests, head, disk_size)
        results.append(disk_result_dict(res))

    return {
        "head": head,
        "disk_size": disk_size,
        "requests": list(requests),
        "direction": direction,
        "results": results,
    }


ROUTES = {
    "/api/cpu": api_cpu,
    "/api/memory": api_memory,
    "/api/deadlock": api_deadlock,
    "/api/disk": api_disk,
}


# ---------------------------------------------------------------------------
# HTTP plumbing
# ---------------------------------------------------------------------------
class Handler(BaseHTTPRequestHandler):
    server_version = "OSSimulatorGUI/1.0"

    # -- helpers ----------------------------------------------------------
    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: dict) -> None:
        self._send(
            status,
            json.dumps(payload).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _read_json(self) -> dict:
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            raise ValueError("invalid Content-Length") from None
        if length <= 0:
            return {}
        if length > MAX_BODY_BYTES:
            raise ValueError("request body is too large")
        raw = self.rfile.read(length)
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ValueError("request body must be JSON") from None
        if not isinstance(parsed, dict):
            raise ValueError("request body must be a JSON object")
        return parsed

    def log_message(self, fmt: str, *args) -> None:  # noqa: D401 - quieter console
        sys.stderr.write("  %s\n" % (fmt % args))

    # -- static files -----------------------------------------------------
    def _serve_static(self, path: str) -> None:
        relative = "index.html" if path in ("/", "") else path.lstrip("/")
        if relative.startswith("static/"):
            relative = relative[len("static/"):]
        candidate = (STATIC_DIR / unquote(relative)).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            self._json(403, {"ok": False, "error": "forbidden"})
            return
        if not candidate.is_file():
            self._json(404, {"ok": False, "error": f"not found: {path}"})
            return
        types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "text/javascript; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
        }
        self._send(200, candidate.read_bytes(), types.get(candidate.suffix, "application/octet-stream"))

    # -- verbs ------------------------------------------------------------
    def do_GET(self) -> None:  # noqa: N802 - http.server naming
        path = urlparse(self.path).path
        if path == "/api/meta":
            self._json(200, {"ok": True, "data": api_meta()})
            return
        if path.startswith("/api/"):
            self._json(404, {"ok": False, "error": f"no such endpoint: {path}"})
            return
        self._serve_static(path)

    do_HEAD = do_GET

    def do_POST(self) -> None:  # noqa: N802 - http.server naming
        path = urlparse(self.path).path
        handler = ROUTES.get(path)
        if handler is None:
            self._json(404, {"ok": False, "error": f"no such endpoint: {path}"})
            return
        try:
            payload = self._read_json()
            data = handler(payload)
        except (ValueError, TypeError, FileNotFoundError) as exc:
            self._json(400, {"ok": False, "error": str(exc)})
            return
        except Exception as exc:  # unexpected: report, do not leak a traceback
            traceback.print_exc()
            self._json(500, {"ok": False, "error": f"internal error: {exc}"})
            return
        self._json(200, {"ok": True, "data": data})


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    shown = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    print("=" * 66)
    print("  OS Resource Management Simulator — web GUI")
    print("=" * 66)
    print(f"  Serving {STATIC_DIR}")
    print(f"  Open     http://{shown}:{port}/")
    print("  Stop with Ctrl+C")
    print()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n  Server stopped.")
    finally:
        httpd.server_close()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve the OS Resource Management Simulator web GUI."
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="port (default 8000)")
    args = parser.parse_args(argv)
    serve(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
