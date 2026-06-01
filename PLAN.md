# Vibe Orchestrator Plan

## 1. Goal

Build a local-first web orchestrator that can launch and coordinate multiple AI agents across different model providers and CLI tools.

The system should make it possible to run agents in parallel without letting them overwrite or corrupt each other's work. It should also give the user a live web interface for monitoring each agent, sending messages, pausing, stopping, restarting, syncing, and reviewing final results.

The first version should be deliberately simple: one local orchestrator process, one local database, local CLI agents, AJAX-based UI updates, and conservative locking.

## 2. Core Principles

- Local-first: users should be able to use locally installed CLIs without needing direct API accounts.
- Provider-neutral: Codex CLI, Claude CLI, and future agent CLIs should be accessed through adapters.
- Isolated execution: each agent should work in its own workspace, worktree, or clone.
- Orchestrator-controlled merge: agents should not directly commit or merge into the main workspace.
- Advisory plus enforced safety: locks guide scheduling, while isolated workspaces prevent direct collisions.
- Full auditability: jobs, messages, locks, commands, outputs, and lifecycle events should be recorded.
- Human control: every running agent should have a visible control surface in the web UI.

## 3. Initial Architecture

```text
Browser UI
  |
  | AJAX polling / commands
  v
Backend service
  |
  | SQLite
  v
Persistent queues and event log
  |
  | subprocess / PTY adapters
  v
Local CLI agents
  |
  | isolated workspaces
  v
Target project repositories
```

Recommended first stack:

- Backend: Python with FastAPI.
- Database: SQLite.
- Frontend: server-rendered HTML plus small JavaScript modules using `fetch`.
- Agent process handling: Python `asyncio.subprocess` initially, optional PTY support later.
- Source isolation: Git worktrees where available, otherwise temporary clones or copied workspaces.

## 4. Main Components

### 4.1 Web UI

The UI should expose:

- Job queue.
- Active agents.
- Lock queue.
- Provider health.
- Recent events.
- Per-agent transcript windows.
- Controls for pause, stop, restart, sync, close, and manual message.

All UI refreshes should use AJAX:

- `GET /api/events?after=<event_id>` for incremental updates.
- `GET /api/agents/{agent_id}` for detailed agent state.
- `GET /api/jobs/{job_id}` for job details.
- `POST /api/agents/{agent_id}/messages` for user messages.
- `POST /api/agents/{agent_id}/control` for pause, stop, restart, sync, and close.

The first version can use polling every 1-2 seconds while a tab is active, with slower polling when idle.

### 4.2 Backend Service

The backend owns:

- Job scheduling.
- Lock arbitration.
- Agent process lifecycle.
- Message delivery.
- Event logging.
- Workspace preparation.
- Result collection.
- Diff and merge review.

The backend should not depend on one specific AI provider.

### 4.3 Agent Adapters

Each CLI provider should be wrapped by an adapter:

```text
AgentAdapter
  detect_installation()
  detect_auth()
  list_supported_models()
  spawn(job, workspace)
  send_message(agent_id, message)
  read_output(agent_id)
  soft_stop(agent_id)
  hard_stop(agent_id)
  restart(agent_id)
```

Initial adapters:

- `CodexCliAdapter`
- `ClaudeCliAdapter`

Future adapters:

- Gemini CLI.
- Aider.
- Custom local model runners.
- Remote SSH adapters.

### 4.4 Job Queue

Jobs represent work that should be performed by an agent.

Suggested fields:

```text
job_id
status: pending | leased | running | paused | blocked | done | failed | cancelled
provider_family: codex | claude | other
model: gpt-* | opus | haiku | sonnet | other
work_package
priority
affected
created_by
lease_owner_orchestrator
lease_expires_at
created_at
updated_at
```

Example:

```text
agent_id: null
work_package: "Implement lock conflict detection"
priority: 50
affected: ["file:orchestrator/locks.py", "area:scheduler"]
model: "gpt-5"
provider_family: "codex"
```

### 4.5 Lock Queue

Locks represent claimed resources.

Suggested fields:

```text
lock_id
job_id
agent_id
resource_type: file | dir | area | symbol | test | repo
resource_key
mode: read | write
status: requested | granted | released | expired | denied
ttl_seconds
heartbeat_at
created_at
updated_at
```

Initial resource types:

- `file:<path>`
- `dir:<path>`
- `area:<logical-area>`
- `repo:<repo-id>`

Initial lock rules:

- Read/read is compatible.
- Read/write is a conflict.
- Write/write is a conflict.
- Directory write conflicts with file writes below that directory.
- Area write conflicts with the same area.
- Repo write conflicts with everything in that repo.

The lock system should be conservative. If the orchestrator is unsure, it should block or widen the lock instead of allowing unsafe concurrency.

### 4.6 Message Queue

Messages support bidirectional communication between the user, orchestrator, and agents.

Suggested fields:

```text
message_id
agent_id
job_id
direction: user_to_agent | agent_to_user | orchestrator_to_agent | agent_to_orchestrator
type: chat | control | status | stdout | stderr | lock_request | sync_request | result
payload_json
ack_status: pending | delivered | acknowledged | failed
created_at
updated_at
```

Control message examples:

```json
{ "command": "pause" }
{ "command": "stop", "mode": "soft" }
{ "command": "stop", "mode": "hard" }
{ "command": "restart" }
{ "command": "sync" }
{ "command": "request_status" }
```

The agent prompt should instruct every agent to check the message buffer regularly. However, the orchestrator must not rely only on model compliance. External process controls are still required.

### 4.7 Event Log

The event log is append-only and drives the UI.

Suggested fields:

```text
event_id
source_type: orchestrator | scheduler | agent | user | adapter
source_id
event_type
payload_json
created_at
```

Useful event types:

- `job.created`
- `job.leased`
- `job.started`
- `job.paused`
- `job.completed`
- `job.failed`
- `lock.requested`
- `lock.granted`
- `lock.denied`
- `lock.released`
- `agent.spawned`
- `agent.output`
- `agent.message`
- `agent.stopped`
- `workspace.created`
- `workspace.diff_ready`
- `merge.ready_for_review`

## 5. Agent Lifecycle

1. User creates a job in the web UI.
2. Backend validates the request.
3. Scheduler selects jobs matching the current orchestrator's supported providers and models.
4. Backend derives lock requests from `affected`.
5. Lock manager grants or blocks locks.
6. Backend creates an isolated workspace.
7. Backend starts the correct CLI adapter.
8. Adapter launches the agent subprocess.
9. Agent output is streamed into the message queue and event log.
10. UI polls events and updates the agent transcript.
11. User can send control messages at any time.
12. Agent finishes and reports completion.
13. Backend collects diff and result metadata.
14. Backend runs validation checks.
15. User reviews and accepts, rejects, or asks for follow-up work.
16. Locks are released.
17. Agent window can be closed and workspace can be cleaned up.

## 6. Safety Model

### 6.1 Request Sanity Check

Before a job is accepted, validate:

- The work package is not asking for destructive filesystem changes outside the target project.
- The job does not request credential theft, secret dumping, malware behavior, or bypassing access controls.
- `affected` is present or can be derived.
- The requested model/provider is available.
- The target repo/workspace exists.

Risky jobs should be marked `needs_review` instead of being started automatically.

### 6.2 Runtime Safety

At runtime:

- Run each agent in its own workspace.
- Restrict working directory.
- Avoid passing unnecessary environment variables.
- Capture stdout and stderr.
- Track process IDs and child processes where possible.
- Prefer soft stop first, hard stop if the agent ignores control messages.

### 6.3 Merge Safety

Agents should not merge directly.

The orchestrator should:

- Compare final diff against granted locks.
- Flag edits outside the allowed affected resources.
- Run configured checks.
- Present diff to the user.
- Merge only after policy approval.

## 7. Multiple Orchestrators

The design should support multiple orchestrators later.

Example:

```text
Claude orchestrator:
  handles provider_family=claude
  handles models=opus, sonnet, haiku

Codex orchestrator:
  handles provider_family=codex
  handles models=gpt-*
```

Every orchestrator should register:

```text
orchestrator_id
hostname
supported_provider_families
supported_models
status
heartbeat_at
```

SQLite is sufficient for a single local orchestrator. For multiple orchestrators on the same machine, SQLite can still work if leases are simple. For multiple machines, use Postgres or another network-safe database.

## 8. Remote SSH Sessions

Remote SSH execution should be future functionality, not part of the first MVP.

Goal:

- Allow the local web orchestrator to start and manage agents on remote machines over SSH.
- Support remote machines that already have Codex CLI, Claude CLI, or other agent tools installed and authenticated.
- Stream remote output back into the local message queue and web UI.

Proposed architecture:

```text
Local web UI
  |
Local orchestrator
  |
SSH transport
  |
Remote runner
  |
Remote CLI agent
```

Two possible approaches:

### 8.1 SSH Command Mode

The local orchestrator runs commands over SSH directly:

```text
ssh user@host "vibe-agent-runner --job-id ..."
```

Pros:

- Simpler deployment.
- No always-on remote daemon.
- Works well for short sessions.

Cons:

- Harder process supervision.
- Harder reconnect behavior.
- More fragile for long-running agents.

### 8.2 Remote Runner Daemon

Install a lightweight remote runner service:

```text
vibe-remote-runner
```

The local orchestrator connects over SSH port forwarding or a secure tunnel.

Pros:

- Better lifecycle management.
- Easier status polling.
- Easier reconnection.
- Cleaner process cleanup.

Cons:

- Requires installation.
- More security surface.
- More configuration.

Recommended path:

1. Start with SSH command mode.
2. Add remote runner daemon only after local orchestration is stable.

Remote SSH safety requirements:

- Never copy local credentials by default.
- Do not assume remote and local filesystem paths match.
- Require explicit remote workspace configuration.
- Verify remote CLI installation and authentication.
- Use SSH keys managed by the user's OS, not stored by the orchestrator.
- Keep separate lock namespaces per repo and host.
- Record remote host, remote path, command, and session ID in the event log.

Remote session data model additions:

```text
remote_host_id
hostname
ssh_alias
workspace_root
supported_provider_families
supported_models
status
heartbeat_at
```

```text
agent_session_id
agent_id
execution_mode: local | ssh_command | remote_runner
host_id
remote_pid
remote_workspace
started_at
ended_at
```

## 9. MVP Scope

The first version should include:

- Local FastAPI backend.
- SQLite database.
- Basic web UI.
- Job queue.
- Message queue.
- Event log.
- Conservative lock queue.
- One target project at a time.
- One local orchestrator process.
- Codex CLI adapter.
- Claude CLI adapter if the local CLI behavior is straightforward.
- Per-agent transcript windows.
- Pause, stop, restart, sync, and close controls.
- Isolated workspaces using Git worktrees.
- Diff collection after completion.

The MVP should not include:

- Distributed orchestration.
- Remote SSH sessions.
- Automatic complex merges.
- Role-based access control.
- Multi-user authentication.
- Fine-grained symbol locks.
- Cloud-hosted agents.

## 10. Suggested Milestones

### Milestone 1: Project Skeleton

- Create FastAPI app.
- Create SQLite schema.
- Add migrations or simple schema bootstrap.
- Add static web UI shell.
- Add `/api/health`.
- Add provider health checks.

### Milestone 2: Queues and Events

- Implement job queue.
- Implement message queue.
- Implement event log.
- Add AJAX event polling.
- Add job creation UI.

### Milestone 3: Local Agent Runner

- Implement generic adapter interface.
- Add basic subprocess runner.
- Add per-agent transcript capture.
- Add soft stop and hard stop.
- Add agent status UI.

### Milestone 4: CLI Provider Adapters

- Add Codex CLI adapter.
- Add Claude CLI adapter.
- Detect installation and login state.
- Route jobs by provider family and model.

### Milestone 5: Locks

- Add lock table.
- Add lock compatibility rules.
- Derive locks from `affected`.
- Block conflicting jobs.
- Show active locks in UI.

### Milestone 6: Workspace Isolation

- Create per-agent Git worktrees.
- Run agents only inside their assigned workspace.
- Collect diffs after completion.
- Show diff summary in UI.

### Milestone 7: Review and Merge

- Validate diff against locks.
- Run configured checks.
- Present result for review.
- Apply accepted changes back to main workspace.

### Milestone 8: Hardening

- Improve process cleanup.
- Add heartbeat and stale lease recovery.
- Add better restart behavior.
- Add audit export.
- Add configuration file.

## 11. Future Functionality

Potential future functionality:

- Remote SSH sessions.
- Remote runner daemon.
- Multiple orchestrators using Postgres.
- Multi-repo support.
- Multi-user web access.
- Authentication and permissions.
- Role-based approval gates.
- Symbol-level locks using language servers.
- Test-level locks and test impact analysis.
- Dependency graph based lock inference.
- Built-in patch review UI.
- Auto-generated task splitting.
- Agent-to-agent handoff.
- Shared context summaries.
- Long-term memory per project.
- Cost and runtime tracking.
- Model preference policies.
- Provider failover.
- Automatic benchmark tasks for adapter health.
- Browser-based terminal transcript playback.
- Plugin system for custom providers.
- Plugin system for custom sanity checks.
- Integration with GitHub issues and pull requests.
- Integration with local IDEs.
- Snapshot and rollback support.
- Policy-as-code for allowed commands.
- Sandboxed execution using containers where practical.

## 12. Main Barriers and Possible Solutions

### Barrier: CLI tools are not stable APIs

Codex CLI, Claude CLI, and other tools may change flags, prompts, output formats, or auth behavior.

Possible solutions:

- Keep all provider-specific behavior in adapters.
- Add adapter health checks.
- Store detected CLI version.
- Write integration tests per adapter.
- Support manual override commands in config.

### Barrier: Agents may ignore message-buffer instructions

Models may forget or deprioritize instructions to check messages.

Possible solutions:

- Keep work packages small.
- Inject frequent reminders into prompts.
- Use external process control for stop/restart.
- Add timeout-based sync checks.
- Treat cooperative polling as helpful, not sufficient.

### Barrier: Parallel edits can conflict

Locks reduce risk, but cannot fully prevent a CLI process from writing files.

Possible solutions:

- Run every agent in its own workspace.
- Validate final diff against locks.
- Merge only through orchestrator.
- Prefer conservative locks.

### Barrier: Pause is difficult across platforms

Suspending subprocesses differs between Windows, macOS, and Linux.

Possible solutions:

- Implement soft pause first via message queue.
- Add hard stop and restart before true OS-level pause.
- Add platform-specific pause later where reliable.

### Barrier: Users may not have API accounts

The system should still work for users who only have local CLI tools.

Possible solutions:

- Use local CLI authentication.
- Detect whether a CLI is installed and logged in.
- Do not require API keys in orchestrator config.
- Show setup instructions per provider in the UI.

### Barrier: AJAX polling can become noisy

Many agents can generate many events.

Possible solutions:

- Use cursor-based event polling.
- Batch events.
- Slow polling for inactive tabs.
- Add long-polling later if needed.
- Keep WebSocket as a later optimization, not the MVP default.

### Barrier: Remote SSH sessions add security risk

Remote execution increases the risk of credential exposure and process leaks.

Possible solutions:

- Start with local-only execution.
- Use SSH agent and OS-managed keys.
- Never store private keys.
- Require explicit remote workspace configuration.
- Track remote sessions and PIDs.
- Keep remote session support behind an explicit feature flag initially.

## 13. Open Design Decisions

- Should the first UI use a small frontend framework or plain JavaScript?
- Should the database schema use Alembic migrations from day one?
- Should Git worktree be mandatory for project targets?
- How much command filtering should happen before the first working prototype?
- Should merge approval be manual-only in MVP?
- Should adapter definitions be Python classes only, or partly config-driven?

Recommended initial decisions:

- Use plain JavaScript for the first UI.
- Use SQLite with a simple schema bootstrap first.
- Prefer Git worktrees and fail clearly if unavailable.
- Keep command filtering conservative but simple.
- Make merge approval manual-only.
- Implement adapters as Python classes first.

## 14. Initial Repository Layout

```text
vibe-orchestrator/
  README.md
  PLAN.md
  pyproject.toml
  src/
    vibe_orchestrator/
      __init__.py
      app.py
      db.py
      scheduler.py
      locks.py
      messages.py
      events.py
      workspace.py
      adapters/
        __init__.py
        base.py
        codex_cli.py
        claude_cli.py
      static/
        app.js
        styles.css
      templates/
        index.html
  tests/
    test_locks.py
    test_scheduler.py
```

## 15. Recommended First Implementation

Start by implementing only the following:

1. FastAPI app with `/`, `/api/health`, and `/api/events`.
2. SQLite schema for jobs, messages, locks, agents, and events.
3. Job creation endpoint and UI form.
4. Fake agent adapter that emits test messages.
5. Real subprocess runner after the fake adapter is stable.
6. Codex CLI adapter.
7. Claude CLI adapter.
8. Lock compatibility rules.
9. Git worktree workspace isolation.
10. Diff summary after completion.

This gives a useful vertical slice before solving every hard orchestration problem.
