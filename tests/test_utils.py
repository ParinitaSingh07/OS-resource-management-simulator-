"""Unit tests for utils/validation.py, utils/logger.py and utils/report_generator.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from modules import cpu_scheduling as cpu
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

DATA = Path(__file__).resolve().parent.parent / "data"


class ParseIntTest(unittest.TestCase):
    def test_accepts_whitespace_and_commas(self) -> None:
        self.assertEqual(parse_int("  42 ", "burst"), 42)
        self.assertEqual(parse_int("1,000", "units"), 1000)

    def test_range_is_enforced(self) -> None:
        with self.assertRaisesRegex(ValueError, ">= 1"):
            parse_int("0", "burst", minimum=1)
        with self.assertRaisesRegex(ValueError, "<= 10"):
            parse_int("11", "priority", maximum=10)

    def test_rejects_non_numbers_and_empty(self) -> None:
        with self.assertRaisesRegex(ValueError, "whole number"):
            parse_int("abc", "burst")
        with self.assertRaisesRegex(ValueError, "empty"):
            parse_int("   ", "burst")

    def test_signed_values(self) -> None:
        self.assertEqual(parse_int("-5", "delta"), -5)
        with self.assertRaises(ValueError):
            parse_int("-1", "arrival", minimum=0)


class ParseListTest(unittest.TestCase):
    def test_mixed_separators(self) -> None:
        self.assertEqual(parse_int_list("1, 2:3 4", "values"), [1, 2, 3, 4])

    def test_empty_list(self) -> None:
        with self.assertRaises(ValueError):
            parse_int_list(" , ", "values")

    def test_element_range_names_the_position(self) -> None:
        with self.assertRaisesRegex(ValueError, "value 2"):
            parse_int_list("5 0", "partition sizes", 1)

    def test_pid_vector(self) -> None:
        self.assertEqual(parse_pid_vector("P1 1,0 2"), ("P1", [1, 0, 2]))

    def test_pid_vector_needs_values(self) -> None:
        with self.assertRaises(ValueError):
            parse_pid_vector("P1")


class ChooseTest(unittest.TestCase):
    def test_case_insensitive_and_canonical(self) -> None:
        self.assertEqual(choose("FIXED", ["fixed", "dynamic"]), "fixed")

    def test_rejects_unknown_option(self) -> None:
        with self.assertRaisesRegex(ValueError, "must be one of"):
            choose("paged", ["fixed", "dynamic"])


class DatasetDiscoveryTest(unittest.TestCase):
    def test_lists_every_sample(self) -> None:
        names = {p.name for p in list_datasets(DATA)}
        self.assertIn("cpu_sample.txt", names)
        self.assertIn("memory_sample.txt", names)
        self.assertIn("deadlock_sample.txt", names)
        self.assertIn("disk_sample.txt", names)
        self.assertIn("disk_sample2.txt", names)

    def test_prefix_filter(self) -> None:
        self.assertEqual(
            [p.name for p in list_datasets(DATA, "disk")],
            ["disk_sample.txt", "disk_sample2.txt"],
        )

    def test_missing_directory_is_empty(self) -> None:
        self.assertEqual(list_datasets(DATA / "missing"), [])

    def test_description_uses_first_comment(self) -> None:
        text = describe_dataset(DATA / "cpu_sample.txt")
        self.assertTrue(text.startswith("cpu_sample.txt — CPU scheduling"))


class LoggerTest(unittest.TestCase):
    def test_writes_file_and_keeps_entries(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = Logger(Path(tmp))
            logger.info("CPU", "FCFS avg waiting 11.40")
            logger.error("something failed")
            logger.close()

            self.assertIsNotNone(logger.path)
            assert logger.path is not None
            content = logger.path.read_text(encoding="utf-8")
            self.assertIn("[CPU     ] FCFS avg waiting 11.40", content)
            self.assertIn("[ERROR   ] something failed", content)
            self.assertTrue(logger.entries[0].endswith("session started"))
            self.assertIsNone(logger.file_error)

    def test_tail(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logger = Logger(Path(tmp))
            for i in range(5):
                logger.info("MENU", f"entry {i}")
            self.assertEqual(len(logger.tail(3)), 3)
            self.assertIn("entry 4", logger.tail(3)[-1])
            logger.close()


class FormattingTest(unittest.TestCase):
    def setUp(self) -> None:
        procs = cpu.load_processes(DATA / "cpu_sample.txt")
        self.cpu_results = {
            name: cpu.run_algorithm(name, procs, quantum=3) for name in cpu.ALGORITHMS
        }
        self.mem_results = {
            name: memory.run_algorithm(
                name, *memory.load_memory_dataset(DATA / "memory_sample.txt"), model="fixed"
            )
            for name in memory.ALGORITHMS
        }
        head, disk_size, requests = disk.load_disk_dataset(DATA / "disk_sample.txt")
        self.disk_results = {
            name: disk.run_algorithm(name, requests, head, disk_size, "up")
            for name in disk.ALGORITHMS
        }

    def test_cpu_tables(self) -> None:
        text = report.format_cpu_result(self.cpu_results["FCFS"])
        self.assertIn("Avg", text.replace("Averages", "Avg"))
        self.assertIn("Gantt", text)
        self.assertIn("P1", text)
        comparison = report.format_cpu_comparison(self.cpu_results)
        self.assertIn("lowest average waiting time", comparison)
        self.assertIn("FCFS", comparison)
        self.assertIn("SRTF", comparison)

    def test_memory_tables(self) -> None:
        text = report.format_memory_result(self.mem_results["FIRST"])
        self.assertIn("Utilisation", text)
        self.assertIn("REJECTED", text)
        comparison = report.format_memory_comparison(self.mem_results, "fixed")
        self.assertIn("Best on this dataset", comparison)

    def test_disk_tables(self) -> None:
        res = disk.fcfs([98, 183, 37, 122, 14, 124, 65, 67], 53)
        text = report.format_disk_result(res)
        self.assertIn("= 640 cylinders", text)
        self.assertIn("80.00", text)
        comparison = report.format_disk_comparison({"FCFS": res})
        self.assertIn("Lowest total movement", comparison)


class ChartAndPdfTest(unittest.TestCase):
    @unittest.skipUnless(report.charts_available(), "matplotlib not installed")
    def test_charts_are_written(self) -> None:
        procs = cpu.load_processes(DATA / "cpu_sample.txt")
        results = {n: cpu.run_algorithm(n, procs, quantum=3) for n in cpu.ALGORITHMS}
        with tempfile.TemporaryDirectory() as tmp:
            bar = report.save_cpu_comparison(results, Path(tmp) / "cpu.png")
            gantt = report.save_gantt(results["FCFS"], Path(tmp) / "gantt.png")
            for path in (bar, gantt):
                self.assertIsNotNone(path)
                assert path is not None
                self.assertGreater(path.stat().st_size, 1000)

    @unittest.skipUnless(report.charts_available(), "matplotlib not installed")
    def test_pdf_report_has_pdf_header_and_pages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = report.generate_pdf_report(
                [("Section one", ["line " * 20] * 80), ("Section two", ["short"])],
                Path(tmp) / "report.pdf",
            )
            data = path.read_bytes()
            self.assertTrue(data.startswith(b"%PDF"))
            self.assertGreater(len(data), 2000)

    def test_gantt_wrapping(self) -> None:
        lines = report.format_gantt([("P1", 0, 10), ("P2", 10, 20)], width=15)
        self.assertGreaterEqual(len(lines), 2)
        self.assertTrue(all(line.startswith("|") and line.endswith("|") for line in lines))


if __name__ == "__main__":
    unittest.main()
