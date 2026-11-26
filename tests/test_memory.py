"""Unit tests for modules/memory_management.py.

The sample dataset's expected values were calculated by hand:

    partitions 100 500 200 300 600   (total 1700)
    P1 212, P2 417, P3 112, P4 426   (741 units requested)

FIXED model (whole partition is reserved):
    FIRST  P1->500 (288), P2->600 (183), P3->200 (88), P4 rejected
           internal 559, free 400, external 400 (blocks 100 and 300 are stranded)
    BEST   P1->300 (88), P2->500 (83), P3->200 (88), P4->600 (174)
           internal 433, free 100, external 0, utilisation 1167/1700
    WORST  P1->600 (388), P2->500 (83), P3->300 (188), P4 rejected
           internal 659, free 300, external 300
"""

from __future__ import annotations

import unittest

from modules.memory_management import (
    MemoryProcess,
    best_fit,
    first_fit,
    load_memory_dataset,
    run_algorithm,
    worst_fit,
)

PARTITIONS = [100, 500, 200, 300, 600]
PROCESSES = [MemoryProcess("P1", 212), MemoryProcess("P2", 417),
             MemoryProcess("P3", 112), MemoryProcess("P4", 426)]


class FixedModelTest(unittest.TestCase):
    """Whole-partition allocation, where internal fragmentation is created."""

    def test_first_fit(self) -> None:
        res = first_fit(PARTITIONS, PROCESSES, model="fixed")
        self.assertEqual([a.block_id for a in res.allocations], [1, 4, 2, None])
        self.assertEqual([a.status for a in res.allocations],
                         ["ALLOCATED", "ALLOCATED", "ALLOCATED", "REJECTED"])
        self.assertEqual(res.allocated_memory, 1300)
        self.assertEqual(res.usable_memory, 741)
        self.assertEqual(res.internal_frag, 559)
        self.assertEqual(res.free_memory, 400)
        self.assertEqual(res.external_frag, 400)
        self.assertEqual(res.stranded_blocks, 2)
        self.assertAlmostEqual(res.utilisation, 43.59, places=2)
        self.assertEqual(res.rejected, ["P4"])

    def test_best_fit_places_everything(self) -> None:
        res = best_fit(PARTITIONS, PROCESSES, model="fixed")
        self.assertEqual([a.block_id for a in res.allocations], [3, 1, 2, 4])
        self.assertEqual(res.allocated_count, 4)
        self.assertEqual(res.internal_frag, 433)
        self.assertEqual(res.free_memory, 100)
        self.assertEqual(res.external_frag, 0)
        self.assertAlmostEqual(res.utilisation, 68.65, places=2)

    def test_worst_fit_takes_the_largest_hole(self) -> None:
        res = worst_fit(PARTITIONS, PROCESSES, model="fixed")
        self.assertEqual([a.block_id for a in res.allocations], [4, 1, 3, None])
        self.assertEqual(res.internal_frag, 659)
        self.assertEqual(res.free_memory, 300)
        self.assertEqual(res.external_frag, 300)
        self.assertEqual(res.stranded_blocks, 2)

    def test_fragmentation_identity(self) -> None:
        """total = reserved + free, and reserved = usable + internal fragmentation."""
        for name in ("FIRST", "BEST", "WORST"):
            with self.subTest(algorithm=name):
                res = run_algorithm(name, PARTITIONS, PROCESSES, model="fixed")
                self.assertEqual(res.allocated_memory + res.free_memory, res.total_memory)
                self.assertEqual(res.usable_memory + res.internal_frag, res.allocated_memory)


class DynamicModelTest(unittest.TestCase):
    """Splitting holes: no internal fragmentation, external fragmentation possible."""

    def test_first_fit_dynamic(self) -> None:
        res = first_fit(PARTITIONS, PROCESSES, model="dynamic")
        self.assertEqual(res.internal_frag, 0)
        self.assertEqual(res.free_memory, 959)
        self.assertEqual(res.external_frag, 959)
        self.assertEqual(res.rejected, ["P4"])
        self.assertAlmostEqual(res.utilisation, 43.59, places=2)

    def test_best_fit_dynamic(self) -> None:
        res = best_fit(PARTITIONS, PROCESSES, model="dynamic")
        self.assertEqual(res.internal_frag, 0)
        self.assertEqual(res.free_memory, 533)
        self.assertEqual(res.external_frag, 0)       # nothing was rejected
        self.assertEqual(res.allocated_count, 4)
        self.assertAlmostEqual(res.utilisation, 68.65, places=2)

    def test_worst_fit_dynamic(self) -> None:
        res = worst_fit(PARTITIONS, PROCESSES, model="dynamic")
        self.assertEqual(res.free_memory, 959)
        self.assertEqual(res.external_frag, 959)
        self.assertEqual(res.rejected, ["P4"])

    def test_allocated_block_holds_exactly_the_request(self) -> None:
        res = first_fit(PARTITIONS, PROCESSES, model="dynamic")
        for allocation in res.allocations:
            if allocation.status == "ALLOCATED":
                self.assertEqual(allocation.allocated_size, allocation.size)
                self.assertEqual(allocation.internal_frag, 0)

    def test_total_memory_conserved(self) -> None:
        for name in ("FIRST", "BEST", "WORST"):
            with self.subTest(algorithm=name):
                res = run_algorithm(name, PARTITIONS, PROCESSES, model="dynamic")
                self.assertEqual(sum(b.size for b in res.blocks), res.total_memory)


class TieBreakTest(unittest.TestCase):
    """Equal-sized holes are always filled from the lowest address."""

    def test_equal_blocks_pick_lowest_index(self) -> None:
        for name in ("FIRST", "BEST", "WORST"):
            with self.subTest(algorithm=name):
                res = run_algorithm(name, [100, 100], [MemoryProcess("P1", 50)])
                self.assertEqual(res.allocations[0].block_id, 0)


class EdgeCaseTest(unittest.TestCase):
    """Degenerate inputs and error paths."""

    def test_request_larger_than_total_memory(self) -> None:
        res = first_fit(PARTITIONS, [MemoryProcess("X", 9999)])
        self.assertEqual(res.rejected, ["X"])
        self.assertEqual(res.allocations[0].reason, "request is larger than total memory")
        self.assertEqual(res.external_frag, 0)       # nothing is "stranded" by holes
        self.assertEqual(res.utilisation, 0.0)

    def test_process_exactly_fills_a_partition(self) -> None:
        res = first_fit([256], [MemoryProcess("P1", 256)])
        self.assertEqual(res.internal_frag, 0)
        self.assertAlmostEqual(res.utilisation, 100.0)

    def test_empty_inputs(self) -> None:
        with self.assertRaises(ValueError):
            first_fit([], PROCESSES)
        with self.assertRaises(ValueError):
            first_fit(PARTITIONS, [])

    def test_invalid_sizes(self) -> None:
        with self.assertRaises(ValueError):
            first_fit([0, 100], PROCESSES)
        with self.assertRaises(ValueError):
            first_fit(PARTITIONS, [MemoryProcess("P1", 0)])
        with self.assertRaises(TypeError):
            first_fit([True, 100], PROCESSES)  # type: ignore[list-item]

    def test_duplicate_pid(self) -> None:
        with self.assertRaises(ValueError):
            first_fit(PARTITIONS, [MemoryProcess("P1", 10), MemoryProcess("P1", 20)])

    def test_unknown_model_and_algorithm(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("FIRST", PARTITIONS, PROCESSES, model="paged")
        with self.assertRaises(ValueError):
            run_algorithm("NEXT", PARTITIONS, PROCESSES)


class DatasetTest(unittest.TestCase):
    """The sample file and the parser."""

    def test_sample_dataset(self) -> None:
        partitions, processes = load_memory_dataset("data/memory_sample.txt")
        self.assertEqual(partitions, PARTITIONS)
        self.assertEqual([(p.pid, p.size) for p in processes],
                         [("P1", 212), ("P2", 417), ("P3", 112), ("P4", 426)])

    def test_missing_partitions_line(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_text("P1 100\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "partitions"):
                load_memory_dataset(path)

    def test_bad_number_reports_line(self) -> None:
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.txt"
            path.write_text("partitions 100 200\nP1 abc\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "line 2"):
                load_memory_dataset(path)

    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_memory_dataset("data/nope.txt")


if __name__ == "__main__":
    unittest.main()
