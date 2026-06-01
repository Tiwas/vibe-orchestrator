from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from vibe_orchestrator.model_suggester import suggest_models


class ModelSuggesterTests(unittest.TestCase):
    def test_fake_suggestion_is_available(self) -> None:
        suggestions = suggest_models(
            work_package="Validate the queue and UI",
            provider_family="fake",
            affected=[],
        )

        self.assertEqual(suggestions[0]["provider_family"], "fake")
        self.assertTrue(suggestions[0]["available"])

    def test_auto_suggestion_includes_rationale(self) -> None:
        suggestions = suggest_models(
            work_package="Refactor scheduler locks",
            provider_family="auto",
            affected=["area:scheduler"],
        )

        self.assertTrue(all(item["rationale"] for item in suggestions))


if __name__ == "__main__":
    unittest.main()
