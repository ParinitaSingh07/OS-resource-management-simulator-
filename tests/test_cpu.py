"""Unit tests for modules/cpu_scheduling.py.

These tests use the sample dataset (data/cpu_sample.txt) and several small
hand-computed schedules. Every expected value below was calculated by hand,
not copied from the program's own output.
"""

from __future__ import annotations

import unittest

from modules.cpu_scheduling import (
    DEFAULT_QUANTUM,
    IDLE,
    Process,
    load_processes,
    parse_process_lines,
    round_robin,
    run_algorithm,
)

SAMPLE = [
    Process("P1", 0, 8, 3),
    Process("P2", 1, 4, 1),
    Process("P3", 2, 9, 4),
    Process("P4", 3, 5, 2),
    Process("P5", 4, 2, 5),
]

#: Verified averages for the sample dataset (see docs/PHASE1_SYSTEM_DESIGN.md).
EXPECTED = {
    "FCFS": (11.40, 17.00),
    "SJF": (8.20, 13.80),
    "SRTF": (6.60, 12.20),
    "PRIORITY": (10.60, 16.20),
    "RR": (14.60, 20.20),          # quantum 3
}


class SampleMetricsTest(unittest.TestCase):
    """The published averages for all five algorithms."""

    def test_averages_match_hand_calculation(self) -> None:
        for name, (avg_waiting, avg_turnaround) in EXPECTED.items():
            with self.subTest(algorithm=name):
                res = run_algorithm(name, SAMPLE, quantum=3)
                self.assertAlmostEqual(res.avg_waiting, avg_waiting, places=2)
                self.assertAlmostEqual(res.avg_turnaround, avg_turnaround, places=2)

    def test_fcfs_completion_order(self) -> None:
        res = run_algorithm("FCFS", SAMPLE)
        self.assertEqual([r.pid for r in res.rows], ["P1", "P2", "P3", "P4", "P5"])
        self.assertEqual([r.completion for r in res.rows], [8, 12, 21, 26, 28])

    def test_sjf_picks_shortest_burst_first(self) -> None:
        res = run_algorithm("SJF", SAMPLE)
        # At t=0 only P1 has arrived, so P1 runs to 8. Then, among the ready
        # processes, P5 (2) -> P2 (4) -> P4 (5) -> P3 (9).
        self.assertEqual([r.pid for r in res.rows], ["P1", "P2", "P3", "P4", "P5"])
        self.assertEqual([p for p, _, _ in res.gantt], ["P1", "P5", "P2", "P4", "P3"])

    def test_gantt_gives_every_process_its_whole_burst(self) -> None:
        # A process may appear in several segments (SRTF, RR), but the segments
        # for one pid must add up to exactly its burst time.
        for name in EXPECTED:
            with self.subTest(algorithm=name):
                res = run_algorithm(name, SAMPLE, quantum=3)
                busy = {p.pid: 0 for p in SAMPLE}
                for pid, start, end in res.gantt:
                    if pid != IDLE:
                        busy[pid] += end - start
                self.assertEqual(busy, {p.pid: p.burst for p in SAMPLE})

    def test_gantt_segments_are_contiguous(self) -> None:
        for name in EXPECTED:
            with self.subTest(algorithm=name):
                gantt = run_algorithm(name, SAMPLE, quantum=3).gantt
                for previous, current in zip(gantt, gantt[1:]):
                    self.assertEqual(previous[2], current[1])

    def test_idle_segments_sum_to_idle_time(self) -> None:
        gap = [Process("A", 0, 3), Process("B", 7, 2), Process("C", 9, 4)]
        res = run_algorithm("FCFS", gap)
        idle = sum(end - start for pid, start, end in res.gantt if pid == IDLE)
        self.assertEqual(idle, res.idle_time)
        self.assertEqual(res.idle_time, 4)
        self.assertEqual(res.total_time, 13)
        self.assertAlmostEqual(res.cpu_utilisation, 9 / 13 * 100, places=2)
        self.assertEqual(res.gantt, [("A", 0, 3), (IDLE, 3, 7), ("B", 7, 9), ("C", 9, 13)])

    def test_clock_starts_at_first_arrival(self) -> None:
        late = [Process("P1", 5, 4)]
        for name in ("FCFS", "SJF", "SRTF", "PRIORITY", "RR"):
            with self.subTest(algorithm=name):
                res = run_algorithm(name, late, quantum=2)
                self.assertEqual(res.gantt, [("P1", 5, 9)])
                self.assertEqual(res.idle_time, 0)
                self.assertEqual(res.total_time, 4)
                self.assertAlmostEqual(res.cpu_utilisation, 100.0, places=2)

    def test_turnaround_and_waiting_relations(self) -> None:
        for name in EXPECTED:
            with self.subTest(algorithm=name):
                res = run_algorithm(name, SAMPLE, quantum=3)
                for r in res.rows:
                    self.assertEqual(r.turnaround, r.completion - r.arrival)
                    self.assertEqual(r.waiting, r.turnaround - r.burst)
                    self.assertGreaterEqual(r.response, 0)


class AlgorithmBehaviourTest(unittest.TestCase):
    """Small cases that pin down the documented tie-break and preemption rules."""

    def test_priority_one_is_highest_and_ties_use_arrival(self) -> None:
        procs = [Process("A", 2, 3, 1), Process("B", 0, 3, 1), Process("C", 0, 1, 5)]
        res = run_algorithm("PRIORITY", procs)
        # A and B both have priority 1: B arrived first, so B then A; C last.
        self.assertEqual([p for p, _, _ in res.gantt], ["B", "A", "C"])

    def test_srtf_preempts_for_a_shorter_newcomer(self) -> None:
        procs = [Process("Long", 0, 10), Process("Short", 1, 1)]
        res = run_algorithm("SRTF", procs)
        self.assertEqual(res.gantt[0], ("Long", 0, 1))
        self.assertEqual(res.gantt[1], ("Short", 1, 2))
        self.assertEqual(res.rows[0].completion, 11)

    def test_round_robin_slices(self) -> None:
        procs = [Process("P1", 0, 5), Process("P2", 0, 3)]
        res = round_robin(procs, quantum=2)
        # P1 0-2, P2 2-4, P1 4-6, P2 6-7, P1 7-8
        self.assertEqual(
            res.gantt,
            [("P1", 0, 2), ("P2", 2, 4), ("P1", 4, 6), ("P2", 6, 7), ("P1", 7, 8)],
        )
        self.assertEqual(res.avg_turnaround, (8 + 7) / 2)
        self.assertEqual(res.quantum, 2)

    def test_round_robin_default_quantum(self) -> None:
        res = round_robin([Process("P1", 0, 20)])
        self.assertEqual(res.quantum, DEFAULT_QUANTUM)
        # Consecutive slices of the same process are merged into one box.
        self.assertEqual(res.gantt, [("P1", 0, 20)])
        self.assertEqual(res.total_time, 20)
        self.assertEqual(res.avg_turnaround, 20)

    def test_single_process(self) -> None:
        res = run_algorithm("FCFS", [Process("Solo", 0, 7)])
        self.assertEqual((res.avg_waiting, res.avg_turnaround, res.avg_response), (0, 7, 0))
        self.assertAlmostEqual(res.throughput, 1 / 7, places=4)


class ValidationTest(unittest.TestCase):
    """Invalid input must raise, never produce a meaningless schedule."""

    def test_empty_process_list(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("FCFS", [])

    def test_duplicate_pid(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("FCFS", [Process("P1", 0, 2), Process("P1", 1, 2)])

    def test_zero_or_negative_burst(self) -> None:
        for burst in (0, -3):
            with self.subTest(burst=burst), self.assertRaises(ValueError):
                run_algorithm("SJF", [Process("P1", 0, burst)])

    def test_negative_arrival(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("FCFS", [Process("P1", -1, 2)])

    def test_quantum_must_be_positive_integer(self) -> None:
        with self.assertRaises(ValueError):
            round_robin([Process("P1", 0, 2)], quantum=0)
        with self.assertRaises(TypeError):
            round_robin([Process("P1", 0, 2)], quantum=1.5)  # type: ignore[arg-type]

    def test_unknown_algorithm(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("LIFO", SAMPLE)

    def test_non_process_item(self) -> None:
        with self.assertRaises(TypeError):
            run_algorithm("FCFS", [("P1", 0, 2)])  # type: ignore[list-item]


class DatasetTest(unittest.TestCase):
    """The parser and the sample file."""

    def test_parse_ignores_comments_and_blank_lines(self) -> None:
        text = ["# header", "", "P1 0 5 2   # inline", "P2,1,3"]
        procs = parse_process_lines(text)
        self.assertEqual(procs, [Process("P1", 0, 5, 2), Process("P2", 1, 3, 0)])

    def test_parse_reports_bad_line_numbers(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_process_lines(["# ok", "P1 0"])
        with self.assertRaisesRegex(ValueError, "line 1"):
            parse_process_lines(["P1 x 3"])

    def test_sample_file_loads_five_processes(self) -> None:
        procs = load_processes("data/cpu_sample.txt")
        self.assertEqual(len(procs), 5)
        self.assertEqual(procs[0], Process("P1", 0, 8, 3))

    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_processes("data/does_not_exist.txt")


if __name__ == "__main__":
    unittest.main()
