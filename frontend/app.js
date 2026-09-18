// Tab list -- order matches functional-requirements.md section 2.
const TABS = [
  { id: "overview",     label: "Overview" },
  { id: "gameplay",     label: "Gameplay Analysis" },
  { id: "ships",        label: "Ship Profile Analysis" },
  { id: "play-patterns", label: "Play Patterns" },
  { id: "combat",       label: "Combat Analysis" },
  { id: "economy",      label: "Economy Analysis" },
  { id: "exploration",  label: "Exploration Deep Dive" },
  { id: "surface",      label: "Surface Activity" },
  { id: "spotlights",   label: "Session Spotlights" },
];

const sidebar = document.getElementById("tabList");
const main = document.getElementById("main");
const buttons = {};
const panels = {};

TABS.forEach((tab) => {
  const btn = document.createElement("button");
  btn.className = "tab-btn";
  btn.textContent = tab.label;
  btn.onclick = () => activateTab(tab.id);
  sidebar.appendChild(btn);
  buttons[tab.id] = btn;

  const panel = document.createElement("div");
  panel.style.display = "none";
  main.appendChild(panel);
  panels[tab.id] = panel;
});

let loaded = {};

function activateTab(id) {
  Object.entries(buttons).forEach(([tid, b]) => b.classList.toggle("active", tid === id));
  Object.entries(panels).forEach(([tid, p]) => (p.style.display = tid === id ? "block" : "none"));
  history.replaceState(null, "", "#" + id);
  if (!loaded[id]) {
    renderTab(id);
    loaded[id] = true;
  }
}

function renderTab(id) {
  const panel = panels[id];
  if (id === "overview") {
    renderOverview(panel);
  } else {
    const tab = TABS.find((t) => t.id === id);
    panel.innerHTML = `
      <div class="panel">
        <h2>${tab.label}</h2>
        <p class="coming-soon">&#9888; Not built yet -- this tab is a placeholder.</p>
      </div>
    `;
  }
}

function renderOverview(panel) {
  panel.innerHTML = `<div class="panel"><h2>Dataset Overview</h2><div class="stat-row" id="stat-row">Loading...</div></div>`;
  fetch("/api/overview")
    .then((r) => r.json())
    .then((d) => {
      document.getElementById("stat-row").innerHTML = `
        <div><div class="stat">${d.sessions.toLocaleString()}</div><div class="stat-label">Sessions</div></div>
        <div><div class="stat">${d.events.toLocaleString()}</div><div class="stat-label">Events</div></div>
        <div><div class="stat">${d.ships.toLocaleString()}</div><div class="stat-label">Ships</div></div>
      `;
    })
    .catch((e) => {
      document.getElementById("stat-row").textContent = "Couldn't reach /api/overview -- " + e;
    });
}

function tabIdFromHash() {
  const h = location.hash.replace(/^#/, "");
  return TABS.some((t) => t.id === h) ? h : "overview";
}

activateTab(tabIdFromHash());
