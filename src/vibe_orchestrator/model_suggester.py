from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelSuggestion:
    provider_family: str
    model: str
    label: str
    rationale: str
    tradeoffs: str
    confidence: float
    available: bool

    def as_dict(self) -> dict:
        return {
            "provider_family": self.provider_family,
            "model": self.model,
            "label": self.label,
            "rationale": self.rationale,
            "tradeoffs": self.tradeoffs,
            "confidence": self.confidence,
            "available": self.available,
        }


def suggest_models(
    *,
    work_package: str,
    provider_family: str,
    affected: list[str],
) -> list[dict]:
    provider = provider_family.strip().lower() or "auto"
    complexity = estimate_complexity(work_package, affected)

    suggestions: list[ModelSuggestion] = []
    if provider in {"auto", "fake"}:
        suggestions.append(
            ModelSuggestion(
                provider_family="fake",
                model="fake",
                label="Fake adapter",
                rationale="Best for validating queue, UI, messages, and event flow without invoking a real CLI.",
                tradeoffs="Does not perform real code changes.",
                confidence=0.95,
                available=True,
            )
        )

    if provider in {"auto", "codex"}:
        suggestions.append(
            ModelSuggestion(
                provider_family="codex",
                model="adapter-default",
                label="Codex adapter default",
                rationale=codex_rationale(complexity),
                tradeoffs="Requires a local Codex CLI adapter in a later version.",
                confidence=0.65 if complexity == "high" else 0.55,
                available=False,
            )
        )

    if provider in {"auto", "claude"}:
        suggestions.append(
            ModelSuggestion(
                provider_family="claude",
                model="adapter-default",
                label="Claude adapter default",
                rationale=claude_rationale(complexity),
                tradeoffs="Requires a local Claude CLI adapter in a later version.",
                confidence=0.65 if complexity == "analysis" else 0.55,
                available=False,
            )
        )

    suggestions.sort(key=lambda item: (item.available, item.confidence), reverse=True)
    return [item.as_dict() for item in suggestions]


def estimate_complexity(work_package: str, affected: list[str]) -> str:
    text = work_package.lower()
    if any(keyword in text for keyword in ["architecture", "orchestrator", "security", "concurrency", "locks"]):
        return "analysis"
    if any(keyword in text for keyword in ["refactor", "migration", "database", "scheduler"]):
        return "high"
    if len(affected) >= 5:
        return "high"
    if any(keyword in text for keyword in ["css", "copy", "docs", "readme"]):
        return "low"
    return "medium"


def codex_rationale(complexity: str) -> str:
    if complexity in {"high", "analysis"}:
        return "Good candidate when the task is code-heavy and should be grounded in repository edits and tests."
    if complexity == "low":
        return "Useful for small implementation or maintenance work once the Codex adapter is enabled."
    return "Balanced choice for normal coding tasks once the Codex adapter is enabled."


def claude_rationale(complexity: str) -> str:
    if complexity == "analysis":
        return "Good candidate when the task needs broad reasoning, tradeoff analysis, or careful planning."
    if complexity == "low":
        return "Useful for lightweight edits or documentation once the Claude adapter is enabled."
    return "Useful for mixed reasoning and implementation tasks once the Claude adapter is enabled."
