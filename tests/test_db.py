from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_orchestrator.db import Store


class StoreTests(unittest.TestCase):
    def test_initialize_create_job_and_jsonl_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = Store(root / "orchestrator.sqlite", root / "logs" / "events.jsonl")
            store.initialize()

            job = store.create_job(
                work_package="Test job",
                provider_family="fake",
                model="fake",
                priority=10,
                affected=["file:README.md"],
            )

            self.assertEqual(job["status"], "pending")
            self.assertEqual(job["affected"], ["file:README.md"])
            self.assertTrue((root / "orchestrator.sqlite").exists())
            self.assertTrue((root / "logs" / "events.jsonl").exists())
            self.assertGreaterEqual(len(store.list_events()), 1)


if __name__ == "__main__":
    unittest.main()
