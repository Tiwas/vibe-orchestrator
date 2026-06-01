from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_orchestrator.locks import LockRequest, locks_conflict


class LockConflictTests(unittest.TestCase):
    def test_read_read_does_not_conflict(self) -> None:
        left = LockRequest("file", "src/app.py", "read")
        right = LockRequest("file", "src/app.py", "read")

        self.assertFalse(locks_conflict(left, right))

    def test_same_file_write_conflicts(self) -> None:
        left = LockRequest("file", "src/app.py", "write")
        right = LockRequest("file", "src/app.py", "read")

        self.assertTrue(locks_conflict(left, right))

    def test_directory_write_conflicts_with_child_file(self) -> None:
        left = LockRequest("dir", "src", "write")
        right = LockRequest("file", "src/app.py", "write")

        self.assertTrue(locks_conflict(left, right))

    def test_different_area_does_not_conflict(self) -> None:
        left = LockRequest("area", "scheduler", "write")
        right = LockRequest("area", "ui", "write")

        self.assertFalse(locks_conflict(left, right))


if __name__ == "__main__":
    unittest.main()
