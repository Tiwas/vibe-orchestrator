from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from .db import Store


@dataclass
class RuntimeState:
    stop_agents: set[str] = field(default_factory=set)
    paused_agents: set[str] = field(default_factory=set)
    tasks: dict[str, asyncio.Task] = field(default_factory=dict)


class FakeAgentRuntime:
    def __init__(self, store: Store):
        self.store = store
        self.state = RuntimeState()

    def start_job(self, job: dict) -> dict:
        agent = self.store.create_agent(
            job_id=job["job_id"],
            provider_family=job["provider_family"],
            model=job["model"],
        )
        self.store.update_job_status(job["job_id"], "running", {"agent_id": agent["agent_id"]})
        task = asyncio.create_task(
            self._run(agent["agent_id"], job["job_id"], job["work_package"], job.get("affected", []))
        )
        self.state.tasks[agent["agent_id"]] = task
        task.add_done_callback(lambda _: self.state.tasks.pop(agent["agent_id"], None))
        return agent

    async def control(self, agent_id: str, command: str) -> dict:
        agent = self.store.get_agent(agent_id)
        normalized = command.lower().strip()
        self.store.append_message(
            agent_id=agent_id,
            job_id=agent["job_id"],
            direction="orchestrator_to_agent",
            message_type="control",
            payload={"command": normalized},
        )

        if normalized == "pause":
            self.state.paused_agents.add(agent_id)
            self.store.update_agent_status(agent_id, "paused")
            self.store.update_job_status(agent["job_id"], "paused", {"agent_id": agent_id})
        elif normalized == "resume":
            self.state.paused_agents.discard(agent_id)
            self.store.update_agent_status(agent_id, "running")
            self.store.update_job_status(agent["job_id"], "running", {"agent_id": agent_id})
        elif normalized == "stop":
            self.state.stop_agents.add(agent_id)
        elif normalized == "sync":
            self.store.append_message(
                agent_id=agent_id,
                job_id=agent["job_id"],
                direction="agent_to_user",
                message_type="status",
                payload={"text": "Fake agent sync acknowledged."},
            )
        elif normalized == "restart":
            task = self.state.tasks.get(agent_id)
            if task:
                task.cancel()
            self.state.stop_agents.discard(agent_id)
            self.state.paused_agents.discard(agent_id)
            self.store.update_agent_status(agent_id, "restarted")
            self.store.update_job_status(agent["job_id"], "pending", {"previous_agent_id": agent_id})
            job = self.store.get_job(agent["job_id"])
            new_agent = self.start_job(job)
            return {"status": "restarted", "agent": new_agent}
        elif normalized == "close":
            self.store.update_agent_status(agent_id, "closed")
        else:
            return {"status": "ignored", "command": normalized}

        return {"status": "accepted", "command": normalized}

    async def _run(self, agent_id: str, job_id: str, work_package: str, affected: list[str]) -> None:
        self.store.update_agent_status(agent_id, "running")
        self.store.append_message(
            agent_id=agent_id,
            job_id=job_id,
            direction="agent_to_user",
            message_type="status",
            payload={"text": f"Fake agent started: {work_package}"},
        )

        steps = [
            "Reading work package",
            "Checking expected resources",
            "Planning changes",
            "Simulating implementation",
            "Preparing result summary",
        ]
        discovered_resources = infer_touched_resources(work_package, affected)

        try:
            for index, step in enumerate(steps, start=1):
                while agent_id in self.state.paused_agents:
                    await asyncio.sleep(0.4)

                if agent_id in self.state.stop_agents:
                    self.store.update_agent_status(agent_id, "stopped")
                    self.store.update_job_status(job_id, "cancelled", {"agent_id": agent_id})
                    self.store.append_message(
                        agent_id=agent_id,
                        job_id=job_id,
                        direction="agent_to_user",
                        message_type="status",
                        payload={"text": "Fake agent stopped before completion."},
                    )
                    return

                self.store.append_message(
                    agent_id=agent_id,
                    job_id=job_id,
                    direction="agent_to_user",
                    message_type="status",
                    payload={"text": step, "step": index, "total_steps": len(steps)},
                )
                if index in {2, 4} and discovered_resources:
                    resource = discovered_resources.pop(0)
                    self.store.add_touched_resource(job_id, resource, agent_id=agent_id)
                    self.store.append_message(
                        agent_id=agent_id,
                        job_id=job_id,
                        direction="agent_to_user",
                        message_type="status",
                        payload={"text": f"Touched resource: {resource}"},
                    )
                await asyncio.sleep(0.6)

            self.store.append_message(
                agent_id=agent_id,
                job_id=job_id,
                direction="agent_to_user",
                message_type="result",
                payload={"text": "Fake agent completed successfully.", "diff_ready": False},
            )
            self.store.update_agent_status(agent_id, "done")
            self.store.update_job_status(job_id, "done", {"agent_id": agent_id})
        except asyncio.CancelledError:
            self.store.update_agent_status(agent_id, "cancelled")
            self.store.update_job_status(job_id, "cancelled", {"agent_id": agent_id})
            raise
        finally:
            self.state.stop_agents.discard(agent_id)
            self.state.paused_agents.discard(agent_id)


def infer_touched_resources(work_package: str, affected: list[str]) -> list[str]:
    if affected:
        return list(dict.fromkeys(affected))

    text = work_package.lower()
    resources = []
    if any(keyword in text for keyword in ["ui", "frontend", "web", "browser", "css"]):
        resources.append("area:web-ui")
    if any(keyword in text for keyword in ["db", "database", "sqlite", "queue", "lock"]):
        resources.append("area:orchestrator-state")
    if any(keyword in text for keyword in ["plan", "todo", "docs", "readme"]):
        resources.append("file:PLAN.md")
    if not resources:
        resources.append("area:implementation")
    return resources
