# Vibe Orchestrator TODO

This TODO is the execution checklist for [PLAN.md](PLAN.md). `PLAN.md` is the architectural source of truth; this file is the condensed implementation track.

## Current Decisions

- One local orchestrator process for v0.1.
- Multiple local agent processes can be spawned by that one orchestrator.
- SQLite is the operational queue and state store.
- JSONL is the append-only audit, transcript, and export format.
- Web UI uses AJAX/fetch polling.
- Agents run in isolated workspaces, preferably Git worktrees.
- The active queue is not file-based.
- No distributed/team orchestration in v0.1.
- No remote SSH sessions in v0.1.
- No automatic merge in v0.1.

## Version Track

### v0.1 - Local Skeleton and Fake Agent

Goal: prove the core loop with minimal dependencies and no real AI CLI complexity.

- [x] Create Python package skeleton.
- [x] Add FastAPI backend.
- [x] Add SQLite bootstrap with WAL mode.
- [x] Add JSONL event mirroring.
- [x] Add tables for jobs, agents, locks, messages, events, and workspaces.
- [x] Add `/api/health`.
- [x] Add AJAX event polling with `GET /api/events?after=<event_id>`.
- [x] Add dashboard endpoint for current work and prioritized job log.
- [x] Add job creation endpoint.
- [x] Add job list endpoint.
- [x] Add model suggestion endpoint for blank model selection.
- [x] Add simple web UI for job creation and event display.
- [x] Add UI panel for current work and prioritized job log.
- [x] Add UI flow for model suggestions with rationale and user choice.
- [x] Add fake agent adapter that emits progress messages.
- [x] Add message endpoint for user-to-agent messages.
- [x] Add basic control endpoint for pause, stop, restart, sync, and close.
- [x] Add unit tests for database bootstrap and lock compatibility.

Exit criteria:

- A user can start the server locally.
- A user can create a fake job in the browser.
- The fake agent emits progress events.
- The UI updates without page reloads.
- SQLite contains the operational state.
- JSONL contains append-only event records.

### v0.2 - Lock Manager and Scheduler

Goal: make queue selection and locking explicit.

- [ ] Implement lock compatibility rules.
- [ ] Derive initial locks from `affected`.
- [ ] Add job priority handling.
- [ ] Add job lease fields and lifecycle transitions.
- [ ] Add stale lease detection.
- [ ] Add scheduler loop.
- [ ] Show active locks in UI.
- [ ] Block conflicting jobs.

Exit criteria:

- Two jobs with conflicting locks do not run at the same time.
- Non-conflicting jobs can run concurrently.
- Stale locks can be recovered manually or automatically.

### v0.3 - Workspace Isolation

Goal: run each job in a separate filesystem workspace.

- [ ] Add target project configuration.
- [ ] Record `base_commit` for every job.
- [ ] Create one branch per job.
- [ ] Create one Git worktree per job.
- [ ] Run fake adapter inside assigned worktree.
- [ ] Collect final diff.
- [ ] Validate diff against granted locks.
- [ ] Add workspace cleanup.

Exit criteria:

- Agent work never mutates the canonical checkout directly.
- Each job has an inspectable worktree and branch.
- The orchestrator can show the final diff.

### v0.4 - Real CLI Adapters

Goal: integrate actual local agent CLIs while keeping the orchestrator provider-neutral.

- [ ] Add adapter interface.
- [ ] Add subprocess runner.
- [ ] Add Codex CLI adapter.
- [ ] Add Claude CLI adapter.
- [ ] Detect installed CLI tools.
- [ ] Detect basic authentication readiness where possible.
- [ ] Route jobs by provider family and model.
- [ ] Capture stdout and stderr into messages/events.
- [ ] Implement soft stop and hard stop.

Exit criteria:

- The same job lifecycle works with fake, Codex, and Claude adapters.
- Missing or unauthenticated CLIs are reported in the UI.

### v0.5 - Review, Evidence, and Manual Merge

Goal: make results reviewable and traceable.

- [ ] Generate per-job evidence bundle.
- [ ] Export job messages and events as JSONL.
- [ ] Export transcript as Markdown.
- [ ] Export final diff as patch.
- [ ] Add commit trailer metadata.
- [ ] Add manual approval step.
- [ ] Add optional merge command owned by orchestrator.

Exit criteria:

- A completed job can be reviewed from UI artifacts.
- The final commit can reference the job, agent, base commit, and evidence bundle.

### v0.6 - Hardening

Goal: make local use reliable.

- [ ] Improve process cleanup.
- [ ] Add heartbeat handling.
- [ ] Add crash recovery.
- [ ] Add better restart behavior.
- [ ] Add config file.
- [ ] Add audit export command.
- [ ] Add more tests.

Exit criteria:

- The orchestrator can recover from common local failures without corrupting state.

## Future Functionality

These are intentionally out of v0.1.

- Multiple orchestrator processes.
- Team mode with shared database.
- Postgres backend.
- Remote SSH sessions.
- Remote runner daemon.
- Multi-user authentication.
- Role-based approvals.
- Symbol-level locks.
- Test-impact locks.
- GitHub issue and pull request integration.
- Policy-as-code command filtering.
- Container sandboxing.

## Immediate Next Step

Continue with v0.2 by making queue scheduling and lock arbitration explicit.
