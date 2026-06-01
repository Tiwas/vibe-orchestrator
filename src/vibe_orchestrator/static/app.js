const state = {
  lastEventId: 0,
  events: [],
  jobs: [],
  agents: [],
  dashboard: { current_work: [], priority_log: [] },
  suggestions: [],
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
  jobs: document.querySelector("#jobs"),
  agents: document.querySelector("#agents"),
  events: document.querySelector("#events"),
  refreshButton: document.querySelector("#refresh-button"),
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

function formatTime(value) {
  if (!value) return "";
  return new Date(value).toLocaleTimeString();
}

function splitAffected(value) {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

async function loadHealth() {
  const health = await api("/api/health");
  elements.health.textContent = `${health.status} - repo: ${health.target_repo.path} - SQLite: ${health.db_path}`;
}

async function loadJobs() {
  const data = await api("/api/jobs");
  state.jobs = data.jobs;
  renderJobs();
}

async function loadDashboard() {
  const data = await api("/api/dashboard");
  state.dashboard = data;
  renderDashboard();
}

async function loadAgents() {
  const data = await api("/api/agents");
  state.agents = data.agents;
  renderAgents();
}

async function loadEvents() {
  const data = await api(`/api/events?after=${state.lastEventId}`);
  if (data.events.length > 0) {
    state.events = [...state.events, ...data.events].slice(-200);
    state.lastEventId = data.last_event_id;
    renderEvents();
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

function renderJobs() {
  elements.jobs.innerHTML = "";
  if (state.jobs.length === 0) {
    elements.jobs.append(empty("No jobs yet"));
    return;
  }
  for (const job of state.jobs) {
    const card = document.createElement("article");
    card.className = "item";
    card.innerHTML = `
      <div class="item-header">
        <strong>${escapeHtml(job.status)}</strong>
        <span>${escapeHtml(job.provider_family)} / ${escapeHtml(job.model)}</span>
      </div>
      <p>${escapeHtml(job.work_package)}</p>
      <small>${escapeHtml(job.job_id)} - priority ${job.priority}</small>
      <small>${escapeHtml((job.affected || []).join(", ") || "no affected resources")}</small>
    `;
    elements.jobs.append(card);
  }
}

function renderDashboard() {
  elements.dashboard.innerHTML = "";
  const current = state.dashboard.current_work || [];
  const queued = state.dashboard.priority_log || [];

  if (current.length === 0 && queued.length === 0) {
    elements.dashboard.append(empty("No active or queued work"));
    return;
  }

  for (const job of current) {
    elements.dashboard.append(dashboardItem(job, "Now"));
  }

  for (const job of queued.filter((item) => !current.some((active) => active.job_id === item.job_id))) {
    elements.dashboard.append(dashboardItem(job, "Priority"));
  }
}

function dashboardItem(job, label) {
  const card = document.createElement("article");
  card.className = "item";
  const agents = (job.agents || []).map((agent) => `${agent.agent_id} ${agent.status}`).join(", ");
  card.innerHTML = `
    <div class="item-header">
      <strong>${escapeHtml(label)} - P${job.priority}</strong>
      <span>${escapeHtml(job.status)}</span>
    </div>
    <p>${escapeHtml(job.work_package)}</p>
    <small>${escapeHtml(job.provider_family)} / ${escapeHtml(job.model)}</small>
    <small>${escapeHtml(agents || "no agent assigned")}</small>
  `;
  return card;
}

function renderAgents() {
  elements.agents.innerHTML = "";
  if (state.agents.length === 0) {
    elements.agents.append(empty("No agents yet"));
    return;
  }
  for (const agent of state.agents) {
    const card = document.createElement("article");
    card.className = "item";
    card.innerHTML = `
      <div class="item-header">
        <strong>${escapeHtml(agent.status)}</strong>
        <span>${escapeHtml(agent.provider_family)} / ${escapeHtml(agent.model)}</span>
      </div>
      <small>${escapeHtml(agent.agent_id)}</small>
      <small>job ${escapeHtml(agent.job_id)}</small>
      <div class="controls">
        ${controlButton(agent.agent_id, "sync")}
        ${controlButton(agent.agent_id, "pause")}
        ${controlButton(agent.agent_id, "resume")}
        ${controlButton(agent.agent_id, "stop")}
        ${controlButton(agent.agent_id, "restart")}
        ${controlButton(agent.agent_id, "close")}
      </div>
      <form class="agent-message" data-agent-id="${escapeHtml(agent.agent_id)}">
        <input placeholder="Message agent">
        <button type="submit">Send</button>
      </form>
    `;
    elements.agents.append(card);
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

function controlButton(agentId, command) {
  return `<button type="button" data-agent-id="${escapeHtml(agentId)}" data-command="${command}">${command}</button>`;
}

function renderEvents() {
  elements.events.innerHTML = "";
  for (const event of [...state.events].reverse()) {
    const row = document.createElement("div");
    row.className = "event";
    row.innerHTML = `
      <span>${event.event_id}</span>
      <span>${formatTime(event.created_at)}</span>
      <strong>${escapeHtml(event.event_type)}</strong>
      <code>${escapeHtml(JSON.stringify(event.payload))}</code>
    `;
    elements.events.append(row);
  }
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
}

elements.form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!elements.model.value.trim()) {
    await suggestModels();
    return;
  }
  await createJob();
});

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

elements.suggestModelButton.addEventListener("click", async () => {
  await suggestModels();
});

elements.refreshButton.addEventListener("click", refreshAll);

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
