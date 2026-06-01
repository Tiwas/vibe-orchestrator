# Vibe Orchestrator

Vibe Orchestrator is a local-first web orchestrator for coordinating multiple AI coding agents safely across different CLI providers and model families.

The first version focuses on a simple local setup:

- A web UI with AJAX polling.
- A backend service that manages jobs, locks, messages, agents, and events.
- SQLite as the operational queue and state store.
- JSONL as the append-only audit and export format.
- Local CLI adapters for tools such as Codex CLI and Claude CLI.
- Per-agent isolated workspaces so concurrent agents do not edit the same files directly.
- Queue-based bidirectional communication so users can pause, stop, restart, sync, or message individual agents.
- Model suggestions when the user leaves model selection blank.

See [PLAN.md](PLAN.md) for the implementation plan, risks, and future functionality.

## Local Development

Windows PowerShell:

```powershell
.\scripts\start-server.ps1
```

macOS/Linux/Git Bash:

```sh
./scripts/start-server.sh
```

Then open `http://127.0.0.1:8765`.

Useful options:

```powershell
.\scripts\start-server.ps1 -Port 9000 -NoInstall
```

```sh
./scripts/start-server.sh --port 9000 --no-install
```
