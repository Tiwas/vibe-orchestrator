const state = {
  lastEventId: 0,
  events: [],
  jobs: [],
  agents: [],
  dashboard: { current_work: [], priority_log: [] },
  suggestions: [],
  health: null,
};

const elements = {
  health: document.querySelector("#health"),
  form: document.querySelector("#job-form"),
  workPackage: document.querySelector("#work-package"),
  providerFamily: document.querySelector("#provider-family"),
  model: document.querySelector("#model"),
  priority: document.querySelector("#priority"),
  affected: document.querySelector("#affected"),
  suggestModelButton: document.querySelector("#suggest-model-button"),
  modelSuggestions: document.querySelector("#model-suggestions"),
  dashboard: document.querySelector("#dashboard"),
  agents: document.querySelector("#agents"),
  locks: document.querySelector("#locks"),
  review: document.querySelector("#review"),
  events: document.querySelector("#events"),
  refreshButton: document.querySelector("#refresh-button"),
  newJobButton: document.querySelector("#new-job-button"),
  summaryRunning: document.querySelector("#summary-running"),
  summaryQueued: document.querySelector("#summary-queued"),
  summaryAgents: document.querySelector("#summary-agents"),
  summaryEvents: document.querySelector("#summary-events"),
  agentCount: document.querySelector("#agent-count"),
  queueCount: document.querySelector("#queue-count"),
  reviewCount: document.querySelector("#review-count"),
};

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(`${response.status} ${text}`);
  }
  return response.json();
}

function splitAffected(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function loadHealth() {
  state.health = await api("/api/health");
  const repo = state.health.target_repo;
  const repoState = repo.is_git_repo ? "git" : "folder";
  elements.health.textContent = `${repoState} ${repo.path}`;
}

async function loadJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs;
}

async function loadDashboard() {
  state.dashboard = await api("/api/dashboard");
}

async function loadAgents() {
  const data = await api("/api/agents");
  state.agents = data.agents;
}

async function loadEvents() {
  const data = await api(`/api/events?after=${state.lastEventId}`);
  if (data.events.length > 0) {
    state.events = [...state.events, ...data.events].slice(-240);
    state.lastEventId = data.last_event_id;
  }
}

async function suggestModels() {
  const data = await api("/api/model-suggestions", {
    method: "POST",
    body: JSON.stringify({
      work_package: elements.workPackage.value,
      provider_family: elements.providerFamily.value || "auto",
      affected: splitAffected(elements.affected.value),
    }),
  });
  state.suggestions = data.suggestions;
  renderSuggestions();
}

function renderAll() {
  renderSummary();
  renderAgents();
  renderDashboard();
  renderLocks();
  renderReview();
  renderEvents();
}

function renderSummary() {
  const runningJobs = state.jobs.filter((job) => job.status === "running" || job.status === "paused");
  const queuedJobs = state.jobs.filter((job) => job.status === "pending" || job.status === "blocked");
  elements.summaryRunning.textContent = runningJobs.length;
  elements.summaryQueued.textContent = queuedJobs.length;
  elements.summaryAgents.textContent = state.agents.length;
  elements.summaryEvents.textContent = state.events.length;
  elements.agentCount.textContent = state.agents.length;
  elements.queueCount.textContent = state.dashboard.priority_log.length;
}

function renderAgents() {
  elements.agents.innerHTML = "";
  if (state.agents.length === 0) {
    elements.agents.append(empty("No agents running yet"));
    return;
  }

  const jobs = jobsById();
  for (const agent of state.agents) {
    const job = jobs.get(agent.job_id);
    const progress = progressForAgent(agent);
    const card = document.createElement("article");
    card.className = `agent-card ${statusClass(agent.status)}`;
    card.innerHTML = `
      <div class="agent-top">
        <span class="provider ${escapeHtml(agent.provider_family)}">${providerLabel(agent.provider_family)}</span>
        <div class="agent-id">
          <strong>${escapeHtml(shortId(agent.agent_id))}</strong>
          <small>${escapeHtml(agent.provider_family)} / ${escapeHtml(agent.model)}</small>
        </div>
        ${statusPill(agent.status)}
      </div>
      <p class="agent-job">${escapeHtml(job ? job.work_package : agent.job_id)}</p>
      <div class="progress-row">
        <span class="bar"><i style="width:${progress.percent}%"></i></span>
        <small>${escapeHtml(progress.label)}</small>
      </div>
      <div class="agent-meta">
        <span>${escapeHtml(job ? `P${job.priority}` : "P-")}</span>
        <span>${escapeHtml((job && job.affected && job.affected.join(", ")) || "no locks requested")}</span>
      </div>
      <div class="controls">
        ${controlButton(agent.agent_id, "sync", "Sync")}
        ${controlButton(agent.agent_id, "pause", "Pause")}
        ${controlButton(agent.agent_id, "resume", "Resume")}
        ${controlButton(agent.agent_id, "stop", "Stop", "danger")}
        ${controlButton(agent.agent_id, "restart", "Restart")}
        ${controlButton(agent.agent_id, "close", "Close")}
      </div>
      <form class="agent-message" data-agent-id="${escapeHtml(agent.agent_id)}">
        <input placeholder="Message ${escapeHtml(shortId(agent.agent_id))}">
        <button type="submit">Send</button>
      </form>
    `;
    elements.agents.append(card);
  }
}

function renderDashboard() {
  elements.dashboard.innerHTML = "";
  const current = state.dashboard.current_work || [];
  const priorityLog = state.dashboard.priority_log || [];
  const currentIds = new Set(current.map((job) => job.job_id));

  if (current.length === 0 && priorityLog.length === 0) {
    elements.dashboard.append(empty("No active or queued work"));
    return;
  }

  for (const job of current) {
    elements.dashboard.append(queueRow(job, "now"));
  }

  for (const job of priorityLog.filter((item) => !currentIds.has(item.job_id))) {
    elements.dashboard.append(queueRow(job, "priority"));
  }
}

function renderLocks() {
  elements.locks.innerHTML = "";
  const jobs = state.jobs
    .filter((job) => (job.affected || []).length > 0)
    .sort((a, b) => statusWeight(a.status) - statusWeight(b.status) || b.priority - a.priority);

  if (jobs.length === 0) {
    elements.locks.append(empty("No affected resources declared"));
    return;
  }

  for (const job of jobs.slice(0, 12)) {
    for (const lock of job.affected.slice(0, 4)) {
      const row = document.createElement("div");
      row.className = `lock-row ${statusClass(job.status)}`;
      row.innerHTML = `
        <span class="lock-state"></span>
        <span class="lock-key">${escapeHtml(lock)}</span>
        <span class="lock-mode">write</span>
        <span class="lock-owner">${escapeHtml(shortId(job.job_id))}</span>
      `;
      elements.locks.append(row);
    }
  }
}

function renderReview() {
  elements.review.innerHTML = "";
  const done = state.jobs.filter((job) => job.status === "done");
  elements.reviewCount.textContent = done.length;

  if (done.length === 0) {
    elements.review.append(empty("Completed jobs will appear here"));
    return;
  }

  for (const job of done.slice(0, 5)) {
    const item = document.createElement("article");
    item.className = "review-item";
    item.innerHTML = `
      <div class="review-top">
        <strong>${escapeHtml(shortId(job.job_id))}</strong>
        ${statusPill(job.status)}
      </div>
      <p>${escapeHtml(job.work_package)}</p>
      <small>${escapeHtml((job.affected || []).join(", ") || "no affected resources")}</small>
    `;
    elements.review.append(item);
  }
}

function renderSuggestions() {
  elements.modelSuggestions.innerHTML = "";
  if (state.suggestions.length === 0) return;

  for (const suggestion of state.suggestions) {
    const item = document.createElement("div");
    item.className = `suggestion ${suggestion.available ? "" : "unavailable"}`;
    item.innerHTML = `
      <div>
        <strong>${escapeHtml(suggestion.label)}</strong>
        <small>${escapeHtml(suggestion.provider_family)} / ${escapeHtml(suggestion.model)}</small>
        <p>${escapeHtml(suggestion.rationale)}</p>
        <small>${escapeHtml(suggestion.tradeoffs)}</small>
      </div>
      <button type="button" data-provider="${escapeHtml(suggestion.provider_family)}" data-model="${escapeHtml(suggestion.model)}">
        Use
      </button>
    `;
    elements.modelSuggestions.append(item);
  }
}

function renderEvents() {
  elements.events.innerHTML = "";
  if (state.events.length === 0) {
    elements.events.append(empty("No events yet"));
    return;
  }

  for (const event of [...state.events].reverse()) {
    const row = document.createElement("div");
    row.className = `event ${eventKind(event.event_type)}`;
    row.innerHTML = `
      <span class="event-time">${escapeHtml(formatTime(event.created_at))}</span>
      <span class="event-mark"></span>
      <strong>${escapeHtml(event.event_type)}</strong>
      <span>${escapeHtml(eventText(event))}</span>
      <code>${escapeHtml(event.source_id || event.job_id || "local")}</code>
    `;
    elements.events.append(row);
  }
}

function queueRow(job, section) {
  const row = document.createElement("article");
  row.className = `queue-row ${statusClass(job.status)}`;
  const agentLabel = (job.agents || []).map((agent) => `${shortId(agent.agent_id)} ${agent.status}`).join(", ");
  row.innerHTML = `
    <span class="queue-prio">P${job.priority}</span>
    <div class="queue-main">
      <div class="queue-title">${escapeHtml(job.work_package)}</div>
      <div class="queue-meta">
        <span>${escapeHtml(section)}</span>
        <span>${escapeHtml(job.provider_family)} / ${escapeHtml(job.model)}</span>
        <span>${escapeHtml(agentLabel || "unassigned")}</span>
      </div>
      <div class="queue-affect">${escapeHtml((job.affected || []).join(", ") || "no affected resources")}</div>
    </div>
    ${statusPill(job.status)}
  `;
  return row;
}

function controlButton(agentId, command, label, tone = "") {
  return `<button class="${tone}" type="button" data-agent-id="${escapeHtml(agentId)}" data-command="${command}">${label}</button>`;
}

function statusPill(status) {
  return `<span class="status-pill ${statusClass(status)}">${escapeHtml(status)}</span>`;
}

function progressForAgent(agent) {
  if (agent.status === "done" || agent.status === "closed") return { percent: 100, label: "complete" };
  if (agent.status === "paused") return { percent: 48, label: "paused" };
  if (agent.status === "starting") return { percent: 12, label: "starting" };
  if (agent.status === "stopped" || agent.status === "cancelled") return { percent: 100, label: agent.status };

  const latest = [...state.events]
    .reverse()
    .find((event) => event.source_id === agent.agent_id && event.event_type === "agent.message");
  const payload = latest && latest.payload && latest.payload.payload;
  if (payload && payload.step && payload.total_steps) {
    return {
      percent: Math.round((payload.step / payload.total_steps) * 100),
      label: `${payload.step}/${payload.total_steps}`,
    };
  }
  return { percent: agent.status === "running" ? 30 : 0, label: agent.status };
}

function eventText(event) {
  if (event.payload && event.payload.payload && event.payload.payload.text) {
    return event.payload.payload.text;
  }
  if (event.payload && event.payload.agent_id) return event.payload.agent_id;
  if (event.payload && event.payload.provider_family) return `${event.payload.provider_family} ${event.payload.model || ""}`;
  return JSON.stringify(event.payload);
}

function eventKind(type) {
  if (type.includes("failed") || type.includes("cancelled") || type.includes("stopped")) return "bad";
  if (type.includes("paused") || type.includes("waiting")) return "warn";
  if (type.includes("done") || type.includes("created")) return "good";
  if (type.includes("message")) return "message";
  return "neutral";
}

function statusClass(status) {
  if (status === "running") return "running";
  if (status === "paused" || status === "pending") return "paused";
  if (status === "done" || status === "closed") return "done";
  if (status === "failed" || status === "cancelled" || status === "stopped") return "bad";
  return "neutral";
}

function statusWeight(status) {
  return { running: 0, paused: 1, pending: 2, blocked: 3, done: 4 }[status] ?? 5;
}

function providerLabel(provider) {
  if (provider === "codex") return "CX";
  if (provider === "claude") return "CL";
  if (provider === "fake") return "FK";
  return provider.slice(0, 2).toUpperCase();
}

function jobsById() {
  return new Map(state.jobs.map((job) => [job.job_id, job]));
}

function shortId(value) {
  return String(value || "").replace(/^(agent|job)_/, "").slice(0, 8);
}

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function empty(text) {
  const div = document.createElement("div");
  div.className = "empty";
  div.textContent = text;
  return div;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function refreshAll() {
  await Promise.all([loadHealth(), loadJobs(), loadAgents(), loadDashboard(), loadEvents()]);
  renderAll();
}

async function createJob() {
  await api("/api/jobs", {
    method: "POST",
    body: JSON.stringify({
      work_package: elements.workPackage.value,
      provider_family: elements.providerFamily.value,
      model: elements.model.value,
      priority: Number(elements.priority.value || 50),
      affected: splitAffected(elements.affected.value),
    }),
  });
  elements.workPackage.value = "";
  elements.model.value = "";
  elements.affected.value = "";
  state.suggestions = [];
  renderSuggestions();
  await refreshAll();
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.model.value.trim()) {
    await suggestModels();
    return;
  }
  await createJob();
});

elements.suggestModelButton.addEventListener("click", async () => {
  await suggestModels();
});

elements.refreshButton.addEventListener("click", refreshAll);

elements.newJobButton.addEventListener("click", () => {
  document.querySelector("#create-job-panel").scrollIntoView({ behavior: "smooth", block: "start" });
  elements.workPackage.focus();
});

elements.modelSuggestions.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-model]");
  if (!button) return;
  elements.providerFamily.value = button.dataset.provider;
  elements.model.value = button.dataset.model;
  state.suggestions = [];
  renderSuggestions();
});

elements.agents.addEventListener("click", async (event) => {
  const button = event.target.closest("button[data-command]");
  if (!button) return;
  await api(`/api/agents/${button.dataset.agentId}/control`, {
    method: "POST",
    body: JSON.stringify({ command: button.dataset.command }),
  });
  await refreshAll();
});

elements.agents.addEventListener("submit", async (event) => {
  const form = event.target.closest(".agent-message");
  if (!form) return;
  event.preventDefault();
  const input = form.querySelector("input");
  if (!input.value.trim()) return;
  await api(`/api/agents/${form.dataset.agentId}/messages`, {
    method: "POST",
    body: JSON.stringify({ text: input.value }),
  });
  input.value = "";
  await refreshAll();
});

refreshAll().catch((error) => {
  elements.health.textContent = `Error: ${error.message}`;
});

setInterval(() => {
  refreshAll().catch((error) => {
    elements.health.textContent = `Error: ${error.message}`;
  });
}, 1200);
