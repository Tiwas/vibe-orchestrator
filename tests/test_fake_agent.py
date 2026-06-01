from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_orchestrator.db import Store
from vibe_orchestrator.fake_agent import FakeAgentRuntime


class FakeAgentTests(unittest.IsolatedAsyncioTestCase):
    async def test_fake_agent_discovers_touched_resources_when_affected_is_blank(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            store = Store(root / "orchestrator.sqlite", root / "logs" / "events.jsonl")
            store.initialize()
            runtime = FakeAgentRuntime(store)
            job = store.create_job(
                work_package="Update web UI and sqlite queue",
                provider_family="fake",
                model="fake",
                priority=10,
                affected=[],
            )

            agent = runtime.start_job(job)
            await runtime.state.tasks[agent["agent_id"]]

            updated = store.get_job(job["job_id"])
            self.assertEqual(updated["affected"], [])
            self.assertEqual(updated["status"], "done")
            self.assertEqual(updated["touched"], ["area:web-ui", "area:orchestrator-state"])


if __name__ == "__main__":
    unittest.main()
