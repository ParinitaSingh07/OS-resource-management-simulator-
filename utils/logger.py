"""
Execution logger — OS Resource Management Simulator
===================================================

Every action the simulator performs is written to

    outputs/logs/session_YYYYMMDD_HHMMSS.log

and also kept in memory so menu option 6 ("View Execution Logs") can show the
current session without reading the file back.

Why a logger and not ``print`` calls?
  * menu output is for the user, the log is evidence for the report;
  * each entry carries a timestamp and a category, so a session can be
    reconstructed later;
  * a failing log file must never crash the simulator, so file errors are
    caught and reported once.

The logger writes in append mode and flushes every line, so a crash preserves
everything logged before it.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

__all__ = ["Logger"]

#: Categories used by ``main.py`` — free-form, but these keep the log readable.
CATEGORIES = ("START", "MENU", "CPU", "MEMORY", "DEADLOCK", "DISK", "CHART", "REPORT", "ERROR", "END")


class Logger:
    """Session logger writing to both a file and an in-memory list.

    Attributes:
        path:       the log file (None when the file could not be opened).
        entries:    every line logged this session, in order.
        file_error: message describing a file problem, or None.

    Example:
        >>> log = Logger(Path("outputs/logs"))
        >>> log.info("CPU", "FCFS avg waiting = 11.40")
    """

    def __init__(self, log_dir: Path, filename_prefix: str = "session") -> None:
        self.entries: list[str] = []
        self.file_error: str | None = None
        self.path: Path | None = None
        self._fh = None

        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.path = log_dir / f"{filename_prefix}_{stamp}.log"
            self._fh = self.path.open("a", encoding="utf-8")
        except OSError as exc:                       # read-only folder, permissions, ...
            self.file_error = f"could not open a log file in {log_dir}: {exc}"

        self.info("START", "OS Resource Management Simulator session started")

    # -- writing ---------------------------------------------------------
    def log(self, category: str, message: str) -> None:
        """Write one entry: ``HH:MM:SS [CATEGORY] message``."""
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"{stamp} [{category.upper():<8}] {message}"
        self.entries.append(line)
        if self._fh is not None:
            try:
                self._fh.write(line + "\n")
                self._fh.flush()
            except OSError as exc:                   # disk full, closed file, ...
                self.file_error = f"log file write failed: {exc}"
                self._fh = None

    def info(self, category: str, message: str) -> None:
        """Alias for :meth:`log`, reads better at call sites."""
        self.log(category, message)

    def error(self, message: str) -> None:
        """Record an error (category ``ERROR``)."""
        self.log("ERROR", message)

    def section(self, title: str) -> None:
        """Record a visual separator and the title of a new section."""
        self.log("MENU", f"--- {title} ---")

    # -- reading ---------------------------------------------------------
    def tail(self, count: int = 20) -> list[str]:
        """The last ``count`` entries (all of them when fewer exist)."""
        return self.entries[-count:] if count > 0 else []

    def close(self) -> None:
        """Flush and close the log file."""
        self.info("END", f"session finished with {len(self.entries)} log entries")
        if self._fh is not None:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None

    def __enter__(self) -> "Logger":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
