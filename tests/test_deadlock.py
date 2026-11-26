"""Unit tests for modules/deadlock_management.py.

The main fixture is the Silberschatz state used in data/deadlock_sample.txt:
A=10, B=5, C=7, Available (3, 3, 2), and the five P0..P4 rows from the book.
Its safe sequence is P1 -> P3 -> P4 -> P0 -> P2 (verified by hand below).
"""

from __future__ import annotations

import unittest

from modules.deadlock_management import (
    BankersState,
    check_safety,
    detect_deadlock,
    load_deadlock_dataset,
    make_state,
    request_resources,
)

PIDS = ["P0", "P1", "P2", "P3", "P4"]
ALLOCATION = [
    [0, 1, 0],
    [2, 0, 0],
    [3, 0, 2],
    [2, 1, 1],
    [0, 0, 2],
]
MAXIMUM = [
    [7, 5, 3],
    [3, 2, 2],
    [9, 0, 2],
    [2, 2, 2],
    [4, 3, 3],
]
AVAILABLE = [3, 3, 2]


def sample_state() -> BankersState:
    return make_state(PIDS, ALLOCATION, MAXIMUM, AVAILABLE)


class StateTest(unittest.TestCase):
    """Derived matrices and validation."""

    def test_need_is_max_minus_allocation(self) -> None:
        state = sample_state()
        self.assertEqual(state.need, (
            (7, 4, 3), (1, 2, 2), (6, 0, 0), (0, 1, 1), (4, 3, 1),
        ))

    def test_total_resources(self) -> None:
        self.assertEqual(sample_state().total_resources, (10, 5, 7))

    def test_allocation_above_max_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exceeds its maximum"):
            make_state(["P1"], [[2, 0]], [[1, 0]], [0, 0])

    def test_dimension_errors(self) -> None:
        with self.assertRaises(ValueError):
            make_state(["P1"], [[0, 1]], [[1, 1]], [0, 0, 0])
        with self.assertRaises(ValueError):
            make_state(["P1"], [[0, 1]], [[1, 1]], [0])
        with self.assertRaises(ValueError):
            make_state(["P1", "P2"], [[0, 1]], [[1, 1], [1, 1]], [0, 0])

    def test_duplicate_and_empty_pids(self) -> None:
        with self.assertRaises(ValueError):
            make_state(["P1", "P1"], [[0], [0]], [[1], [1]], [0])
        with self.assertRaises(ValueError):
            make_state([], [], [], [0])

    def test_negative_values_rejected(self) -> None:
        with self.assertRaises(ValueError):
            make_state(["P1"], [[0]], [[1]], [-1])

    def test_non_integer_values_rejected(self) -> None:
        with self.assertRaises(TypeError):
            make_state(["P1"], [[0]], [[1]], [True])  # type: ignore[list-item]


class SafetyTest(unittest.TestCase):
    """Banker's safety algorithm on the textbook state."""

    def test_safe_sequence(self) -> None:
        result = check_safety(sample_state())
        self.assertTrue(result.safe)
        self.assertEqual(result.sequence, ["P1", "P3", "P4", "P0", "P2"])
        self.assertEqual(result.stuck, [])
        self.assertEqual(result.summary, "SAFE: P1 -> P3 -> P4 -> P0 -> P2")

    def test_work_trace_is_consistent(self) -> None:
        result = check_safety(sample_state())
        self.assertEqual(result.steps[0].work_before, (3, 3, 2))
        for step in result.steps:
            expected = tuple(a + b for a, b in zip(step.work_before, sample_state().allocation_of(step.pid)))
            self.assertEqual(step.work_after, expected)

    def test_each_process_finishes_once(self) -> None:
        result = check_safety(sample_state())
        self.assertEqual(sorted(result.sequence), sorted(PIDS))


class RequestTest(unittest.TestCase):
    """Banker's resource-request algorithm."""

    def test_granted_request(self) -> None:
        result = request_resources(sample_state(), "P1", (1, 0, 2))
        self.assertTrue(result.granted)
        self.assertIsNotNone(result.state)
        self.assertEqual(result.state.available, (2, 3, 0))
        self.assertEqual(result.state.allocation_of("P1"), (3, 0, 2))
        self.assertTrue(result.safety.safe)

    def test_request_that_would_leave_an_unsafe_state_is_refused(self) -> None:
        result = request_resources(sample_state(), "P4", (3, 3, 0))
        self.assertFalse(result.granted)
        self.assertIsNone(result.state)
        self.assertFalse(result.safety.safe)
        self.assertIn("unsafe", result.reason)

    def test_request_above_available_waits(self) -> None:
        # P2 may still ask for 6 of A, but only 3 are available.
        result = request_resources(sample_state(), "P2", (4, 0, 0))
        self.assertFalse(result.granted)
        self.assertIsNone(result.state)
        self.assertIsNone(result.safety)
        self.assertIn("must wait", result.reason)

    def test_request_above_need_is_an_input_error(self) -> None:
        with self.assertRaisesRegex(ValueError, "remaining need"):
            request_resources(sample_state(), "P1", (2, 0, 2))

    def test_wrong_vector_length(self) -> None:
        with self.assertRaises(ValueError):
            request_resources(sample_state(), "P1", (1, 0))

    def test_unknown_process(self) -> None:
        with self.assertRaises(ValueError):
            request_resources(sample_state(), "P9", (0, 0, 0))

    def test_zero_request_is_granted(self) -> None:
        result = request_resources(sample_state(), "P0", (0, 0, 0))
        self.assertTrue(result.granted)
        self.assertEqual(result.state, sample_state())


class DetectionTest(unittest.TestCase):
    """Deadlock detection, including an unsafe-but-not-deadlocked state."""

    def test_no_deadlock_in_safe_state(self) -> None:
        result = detect_deadlock(sample_state())
        self.assertEqual(result.deadlocked, [])
        self.assertEqual(result.summary, "NO DEADLOCK")
        self.assertEqual(len(result.order), 5)
        self.assertEqual(result.request_source, "Need (Max - Allocation)")

    def test_deadlocked_pair(self) -> None:
        # Two processes each hold one unit and each needs one more; none is free.
        state = make_state(["P1", "P2"], [[1], [1]], [[2], [2]], [0])
        result = detect_deadlock(state)
        self.assertEqual(result.deadlocked, ["P1", "P2"])
        self.assertEqual(result.order, [])
        self.assertEqual(result.summary, "DEADLOCK: P1, P2")

    def test_unsafe_state_without_an_actual_deadlock(self) -> None:
        # Safety says no sequence guarantees completion, but with the ACTUAL
        # requests (P1 asks for nothing) both processes can finish.
        state = make_state(["P1", "P2"], [[1], [1]], [[2], [2]], [0])
        self.assertFalse(check_safety(state).safe)
        result = detect_deadlock(state, requests=[[0], [1]])
        self.assertEqual(result.deadlocked, [])
        self.assertEqual(result.order, ["P1", "P2"])
        self.assertEqual(result.request_source, "supplied Request matrix")

    def test_request_above_need_in_supplied_matrix(self) -> None:
        state = make_state(["P1", "P2"], [[1], [1]], [[2], [2]], [0])
        with self.assertRaises(ValueError):
            detect_deadlock(state, requests=[[0], [3]])

    def test_wrong_request_dimensions(self) -> None:
        state = make_state(["P1", "P2"], [[1], [1]], [[2], [2]], [0])
        with self.assertRaises(ValueError):
            detect_deadlock(state, requests=[[0]])


class DatasetTest(unittest.TestCase):
    """Both provided datasets."""

    def test_sample_matches_the_textbook(self) -> None:
        state = load_deadlock_dataset("data/deadlock_sample.txt")
        self.assertEqual(list(state.pids), PIDS)
        self.assertEqual(state.available, (3, 3, 2))
        self.assertEqual(check_safety(state).safe, True)

    def test_unsafe_dataset_is_unsafe_and_deadlocked(self) -> None:
        state = load_deadlock_dataset("data/deadlock_unsafe.txt")
        self.assertFalse(check_safety(state).safe)
        self.assertNotEqual(detect_deadlock(state).deadlocked, [])

    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_deadlock_dataset("data/nope.txt")


if __name__ == "__main__":
    unittest.main()
