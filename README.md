# Vibe Orchestrator

Vibe Orchestrator is a local-first web orchestrator for coordinating multiple AI coding agents safely across different CLI providers and model families.

The first version focuses on a simple local setup:

- A web UI with AJAX polling.
- A backend service that manages jobs, locks, messages, agents, and events.
- Local CLI adapters for tools such as Codex CLI and Claude CLI.
- Per-agent isolated workspaces so concurrent agents do not edit the same files directly.
- Queue-based bidirectional communication so users can pause, stop, restart, sync, or message individual agents.

See [PLAN.md](PLAN.md) for the implementation plan, risks, and future functionality.
