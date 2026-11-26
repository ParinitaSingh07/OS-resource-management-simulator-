"""Unit tests for modules/disk_scheduling.py.

Textbook dataset (head 53, cylinders 0..199):
    requests 98 183 37 122 14 124 65 67
    FCFS  = 45+85+146+85+108+110+59+2                 = 640
    SSTF  = 12+2+30+23+84+24+2+59                     = 236
    SCAN up = 12+2+31+24+2+59+16(boundary)+162+23     = 331
    CSCAN up = 12+2+31+24+2+59+16(boundary)+14+23     = 183  (jump 199 not counted)
"""

from __future__ import annotations

import unittest

from modules.disk_scheduling import (
    ALGORITHMS,
    cscan,
    fcfs,
    load_disk_dataset,
    parse_disk_lines,
    run_algorithm,
    scan,
    sstf,
)

HEAD = 53
DISK = 200
REQUESTS = [98, 183, 37, 122, 14, 124, 65, 67]


class TextbookDatasetTest(unittest.TestCase):
    """The four totals quoted in the report."""

    def test_fcfs(self) -> None:
        res = fcfs(REQUESTS, HEAD, DISK)
        self.assertEqual(res.total_movement, 640)
        self.assertEqual([m.distance for m in res.movements],
                         [45, 85, 146, 85, 108, 110, 59, 2])
        self.assertEqual(res.order, REQUESTS)

    def test_sstf(self) -> None:
        res = sstf(REQUESTS, HEAD, DISK)
        self.assertEqual(res.total_movement, 236)
        self.assertEqual(res.order, [65, 67, 37, 14, 98, 122, 124, 183])

    def test_scan_up(self) -> None:
        res = scan(REQUESTS, HEAD, DISK, "up")
        self.assertEqual(res.total_movement, 331)
        self.assertEqual(res.order, [65, 67, 98, 122, 124, 183, 37, 14])
        boundary = [m for m in res.movements if m.is_boundary]
        self.assertEqual(len(boundary), 1)
        self.assertEqual((boundary[0].start, boundary[0].end), (183, 199))

    def test_scan_down(self) -> None:
        res = scan(REQUESTS, HEAD, DISK, "down")
        self.assertEqual(res.total_movement, 236)
        self.assertEqual(res.order, [37, 14, 65, 67, 98, 122, 124, 183])

    def test_cscan_up(self) -> None:
        res = cscan(REQUESTS, HEAD, DISK, "up")
        self.assertEqual(res.total_movement, 183)
        self.assertEqual(res.order, [65, 67, 98, 122, 124, 183, 14, 37])
        self.assertEqual(res.return_jump, 199)
        self.assertEqual(res.total_movement + res.return_jump, 382)

    def test_cscan_down(self) -> None:
        res = cscan(REQUESTS, HEAD, DISK, "down")
        self.assertEqual(res.total_movement, 187)
        self.assertEqual(res.return_jump, 199)

    def test_average_is_total_over_request_count(self) -> None:
        res = fcfs(REQUESTS, HEAD, DISK)
        self.assertAlmostEqual(res.average_movement, 80.0, places=2)
        self.assertAlmostEqual(cscan(REQUESTS, HEAD, DISK).average_movement, 22.88, places=2)


class SecondDatasetTest(unittest.TestCase):
    """data/disk_sample2.txt: head 100, 9 requests, different ranking."""

    HEAD2 = 100
    REQUESTS2 = [55, 58, 39, 18, 90, 160, 150, 38, 184]

    def test_totals(self) -> None:
        expected = {
            "FCFS": 498,
            "SSTF": 248,
            "SCAN": 280,
            "CSCAN": 189,
        }
        for name, total in expected.items():
            with self.subTest(algorithm=name):
                self.assertEqual(
                    run_algorithm(name, self.REQUESTS2, self.HEAD2, DISK, "up").total_movement,
                    total,
                )

    def test_load_from_file(self) -> None:
        head, disk_size, requests = load_disk_dataset("data/disk_sample2.txt")
        self.assertEqual((head, disk_size, requests), (self.HEAD2, DISK, self.REQUESTS2))


class InvariantTest(unittest.TestCase):
    """Properties that must hold for every algorithm and dataset."""

    def test_every_request_is_served_exactly_once(self) -> None:
        for name in ALGORITHMS:
            with self.subTest(algorithm=name):
                res = run_algorithm(name, REQUESTS, HEAD, DISK)
                self.assertEqual(sorted(res.order), sorted(REQUESTS))

    def test_total_equals_sum_of_distances(self) -> None:
        for name in ALGORITHMS:
            with self.subTest(algorithm=name):
                res = run_algorithm(name, REQUESTS, HEAD, DISK)
                self.assertEqual(res.total_movement, sum(m.distance for m in res.movements))

    def test_head_path_starts_at_head(self) -> None:
        for name in ALGORITHMS:
            with self.subTest(algorithm=name):
                self.assertEqual(run_algorithm(name, REQUESTS, HEAD, DISK).positions[0], HEAD)

    def test_duplicate_requests_are_both_served(self) -> None:
        res = sstf([20, 20, 80], 50, DISK)
        self.assertEqual(res.order.count(20), 2)
        self.assertEqual(res.total_movement, 30 + 0 + 60)

    def test_head_inside_the_queue(self) -> None:
        res = fcfs([10], 10, DISK)
        self.assertEqual(res.movements, [])
        self.assertEqual(res.total_movement, 0)

    def test_sstf_tie_picks_smaller_cylinder(self) -> None:
        res = sstf([40, 60], 50, DISK)
        self.assertEqual(res.order, [40, 60])


class ValidationTest(unittest.TestCase):
    """Invalid datasets raise instead of producing a schedule."""

    def test_empty_requests(self) -> None:
        with self.assertRaises(ValueError):
            fcfs([], HEAD, DISK)

    def test_request_outside_disk(self) -> None:
        for bad in (-1, 200):
            with self.subTest(cylinder=bad), self.assertRaises(ValueError):
                fcfs([bad], HEAD, DISK)

    def test_head_outside_disk(self) -> None:
        with self.assertRaises(ValueError):
            fcfs([10], 200, DISK)

    def test_bad_disk_size(self) -> None:
        with self.assertRaises(ValueError):
            fcfs([0], 0, 1)

    def test_unknown_direction(self) -> None:
        with self.assertRaises(ValueError):
            scan(REQUESTS, HEAD, DISK, "left")

    def test_bool_is_not_an_integer(self) -> None:
        with self.assertRaises(TypeError):
            fcfs([True], HEAD, DISK)  # type: ignore[list-item]

    def test_unknown_algorithm(self) -> None:
        with self.assertRaises(ValueError):
            run_algorithm("LOOK", REQUESTS, HEAD, DISK)


class ParserTest(unittest.TestCase):
    """parse_disk_lines accepts the documented forms."""

    def test_multiline_requests_and_defaults(self) -> None:
        head, disk_size, requests = parse_disk_lines([
            "# comment",
            "head 10",
            "requests 5, 20",
            "30 40",
        ])
        self.assertEqual((head, disk_size, requests), (10, 200, [5, 20, 30, 40]))

    def test_missing_head(self) -> None:
        with self.assertRaisesRegex(ValueError, "head"):
            parse_disk_lines(["requests 1 2"])

    def test_missing_requests(self) -> None:
        with self.assertRaisesRegex(ValueError, "request cylinders"):
            parse_disk_lines(["head 1"])

    def test_bad_request_line(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_disk_lines(["head 1", "requests 5 x"])

    def test_missing_file(self) -> None:
        with self.assertRaises(FileNotFoundError):
            load_disk_dataset("data/nope.txt")


if __name__ == "__main__":
    unittest.main()
