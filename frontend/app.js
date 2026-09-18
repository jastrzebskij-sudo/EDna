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
  } else if (id === "gameplay") {
    renderGameplay(panel);
  } else if (id === "ships") {
    renderShips(panel);
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

// Fixed color-per-category map, shared across every chart in the report
// (functional-requirements.md 1.2). Ambient is excluded from activity-mix
// views by default, but keeping a color here costs nothing and covers any
// future tab that lists it anyway.
const CATEGORY_COLORS = {
  "Combat": "#ff2b2b",
  "Exploration (transit)": "#3fa9ff",
  "Exploration (deep)": "#7a5cff",
  "Trading": "#ff8000",
  "Mining": "#c98a3a",
  "Social": "#ff6fae",
  "Passengers/Missions": "#35d4b0",
  "Engineering": "#ffcc00",
  "Colonisation": "#35d47a",
  "Travel": "#7d93a8",
  "Ship management": "#995000",
  "Powerplay": "#b03fff",
  "Ambient": "#4a453f",
  "Other": "#6b625a",
};

if (window.Chart) {
  Chart.defaults.color = "#b8ada0";
  Chart.defaults.font.family = '"Titillium Web", system-ui, sans-serif';
  Chart.defaults.borderColor = "rgba(255, 128, 0, 0.12)";
}

// Draws dashed vertical lines + rotated labels at known game-update dates.
// monthLabels are 'YYYY-MM' strings matching the chart's x-axis categories.
function referenceLinesPlugin(monthLabels, gameUpdates) {
  return {
    id: "refLines",
    afterDraw(chart) {
      const { ctx, chartArea, scales } = chart;
      if (!chartArea) return;
      const xScale = scales.x;
      ctx.save();
      gameUpdates.forEach((u) => {
        const idx = monthLabels.indexOf(u.date.slice(0, 7));
        if (idx === -1) return;
        const x = xScale.getPixelForValue(idx);
        ctx.strokeStyle = "rgba(255, 204, 0, 0.4)";
        ctx.setLineDash([4, 3]);
        ctx.beginPath();
        ctx.moveTo(x, chartArea.top);
        ctx.lineTo(x, chartArea.bottom);
        ctx.stroke();

        ctx.save();
        ctx.translate(x + 3, chartArea.top + 4);
        ctx.rotate(Math.PI / 2);
        ctx.fillStyle = "#ffcc00";
        ctx.font = '10px "Titillium Web", sans-serif';
        ctx.fillText(u.label, 0, 0);
        ctx.restore();
      });
      ctx.restore();
    },
  };
}

// A log-scale axis with only power-of-ten tick labels -- Chart.js's default
// 1,2,3...9 x 10^n minor-tick labels overlap into unreadable clutter once a
// chart has 20+ bars (fleet usage, distance-per-ship).
function logAxis(titleText) {
  return {
    type: "logarithmic",
    afterBuildTicks: (axis) => {
      axis.ticks = axis.ticks.filter((t) => {
        const log = Math.log10(t.value);
        return Math.abs(log - Math.round(log)) < 1e-9;
      });
    },
    title: { display: true, text: titleText },
  };
}

function chartCanvas(container, height) {
  const wrap = document.createElement("div");
  wrap.style.position = "relative";
  wrap.style.height = (height || 320) + "px";
  const canvas = document.createElement("canvas");
  wrap.appendChild(canvas);
  container.appendChild(wrap);
  return canvas;
}

let gameplayData = null;
let gameplayCharts = [];

function renderGameplay(panel) {
  panel.innerHTML = `<div class="panel"><p>Loading gameplay data&hellip;</p></div>`;
  fetch("/api/gameplay")
    .then((r) => r.json())
    .then((data) => {
      gameplayData = data;
      panel.innerHTML = "";
      renderMonthlyFrequency(panel, data);
      renderHeatmap(panel, data);
      renderActivityMix(panel, data);
      renderSessionHistogram(panel, data);
      renderEventTrendExplorer(panel, data);
    })
    .catch((e) => {
      panel.innerHTML = `<div class="panel"><p>Couldn't reach /api/gameplay -- ${e}</p></div>`;
    });
}

function renderMonthlyFrequency(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Monthly Play Frequency &amp; Playtime</h2>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div);
  const labels = data.monthly.map((r) => r.month);
  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Sessions",
          data: data.monthly.map((r) => r.sessions),
          backgroundColor: "rgba(255, 128, 0, 0.55)",
          yAxisID: "y",
        },
        {
          type: "line",
          label: "Hours played",
          data: data.monthly.map((r) => r.hours),
          borderColor: "#3fa9ff",
          backgroundColor: "#3fa9ff",
          yAxisID: "y1",
          tension: 0.2,
          pointRadius: 1,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { ticks: { maxRotation: 0, autoSkip: true } },
        y: { position: "left", title: { display: true, text: "Sessions" } },
        y1: {
          position: "right",
          title: { display: true, text: "Hours" },
          grid: { drawOnChartArea: false },
        },
      },
    },
    plugins: [referenceLinesPlugin(labels, data.game_updates)],
  });
  gameplayCharts.push(chart);
}

function renderHeatmap(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Session-Start Heatmap</h2><p>Day of week &times; hour of day, all years combined.</p>`;
  panel.appendChild(div);

  const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
  const grid = {};
  let max = 0;
  data.heatmap.forEach((r) => {
    grid[`${r.dow}-${r.hour}`] = r.n;
    if (r.n > max) max = r.n;
  });

  const table = document.createElement("div");
  table.className = "heatmap";
  table.style.gridTemplateColumns = `40px repeat(24, 1fr)`;

  table.appendChild(document.createElement("div"));
  for (let h = 0; h < 24; h++) {
    const cell = document.createElement("div");
    cell.className = "heatmap-axis";
    cell.textContent = h % 3 === 0 ? h : "";
    table.appendChild(cell);
  }
  for (let d = 0; d < 7; d++) {
    const label = document.createElement("div");
    label.className = "heatmap-axis";
    label.textContent = DAYS[d];
    table.appendChild(label);
    for (let h = 0; h < 24; h++) {
      const n = grid[`${d}-${h}`] || 0;
      const cell = document.createElement("div");
      cell.className = "heatmap-cell";
      const alpha = max ? 0.06 + 0.85 * (n / max) : 0.06;
      cell.style.background = n ? `rgba(255, 128, 0, ${alpha})` : "rgba(255,255,255,0.02)";
      cell.title = `${DAYS[d]} ${h}:00 -- ${n} session${n === 1 ? "" : "s"}`;
      table.appendChild(cell);
    }
  }
  div.appendChild(table);
}

function renderActivityMix(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Fleet-Wide Activity Mix Over Time</h2><p>Monthly share of events by category (Ambient excluded). Hover a month for the full breakdown.</p>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div, 380);

  const months = [...new Set(data.activity_mix.map((r) => r.month))].sort();
  const categories = [...new Set(data.activity_mix.map((r) => r.category))];
  const byMonth = {};
  data.activity_mix.forEach((r) => {
    byMonth[r.month] = byMonth[r.month] || {};
    byMonth[r.month][r.category] = r.n;
  });
  const monthTotals = {};
  months.forEach((m) => {
    monthTotals[m] = Object.values(byMonth[m] || {}).reduce((a, b) => a + b, 0);
  });

  const datasets = categories.map((cat) => ({
    label: cat,
    data: months.map((m) => {
      const total = monthTotals[m];
      const n = (byMonth[m] || {})[cat] || 0;
      return total ? +((n / total) * 100).toFixed(2) : 0;
    }),
    backgroundColor: CATEGORY_COLORS[cat] || "#888",
    stack: "mix",
  }));

  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels: months, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, ticks: { maxRotation: 0, autoSkip: true } },
        y: { stacked: true, max: 100, title: { display: true, text: "% of events" } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%`,
          },
        },
      },
    },
    plugins: [referenceLinesPlugin(months, data.game_updates)],
  });
  gameplayCharts.push(chart);
}

function renderSessionHistogram(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Session-Length Distribution</h2><p>Valid sessions only (0&ndash;12h).</p>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div, 260);

  const buckets = {};
  data.histogram.forEach((r) => (buckets[r.bucket] = r.n));
  const labels = [];
  const counts = [];
  for (let b = 1; b <= 12; b++) {
    labels.push(`${b - 1}-${b}h`);
    counts.push(buckets[b] || 0);
  }

  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels,
      datasets: [{ label: "Sessions", data: counts, backgroundColor: "rgba(255, 128, 0, 0.55)" }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { y: { title: { display: true, text: "Sessions" } } },
    },
  });
  gameplayCharts.push(chart);
}

function renderEventTrendExplorer(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Per-Event-Type Monthly Trend</h2>`;

  const select = document.createElement("select");
  select.className = "ed-select";
  data.top_events.forEach((e) => {
    const opt = document.createElement("option");
    opt.value = e.event;
    opt.textContent = `${e.event} (${e.n.toLocaleString()})`;
    select.appendChild(opt);
  });
  div.appendChild(select);
  panel.appendChild(div);

  const canvas = chartCanvas(div, 280);
  let chart = null;

  function load(eventName) {
    fetch(`/api/gameplay/event-trend?event=${encodeURIComponent(eventName)}`)
      .then((r) => r.json())
      .then((trend) => {
        const labels = trend.monthly.map((r) => r.month);
        const counts = trend.monthly.map((r) => r.n);
        if (chart) chart.destroy();
        chart = new Chart(canvas, {
          type: "line",
          data: {
            labels,
            datasets: [
              {
                label: eventName,
                data: counts,
                borderColor: "#ff8000",
                backgroundColor: "rgba(255, 128, 0, 0.15)",
                fill: true,
                tension: 0.2,
                pointRadius: 1,
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: { x: { ticks: { maxRotation: 0, autoSkip: true } } },
          },
          plugins: [referenceLinesPlugin(labels, data.game_updates)],
        });
        gameplayCharts.push(chart);
      });
  }

  select.onchange = () => load(select.value);
  load(select.value);
}

// Mirrors the backend's REAL_SHIP_FILTER (app/main.py) for the one place
// filtering has to happen client-side: coverage concentration, which is
// computed here from the unfiltered category_by_ship data (see the comment
// on that query in main.py for why it's shared, unfiltered, across three
// features but only coverage needs the real-ship exclusion applied to it).
function isRealShip(name) {
  if (name === "Unknown ship (before first Loadout)") return false;
  const n = name.toLowerCase();
  return !["testbuggy", "utilitysuit", "explorationsuit", "tacticalsuit"].some((s) => n.includes(s));
}

function renderEdTable(container, columns, rows) {
  const wrap = document.createElement("div");
  wrap.className = "ed-table-wrap";
  const table = document.createElement("table");
  table.className = "ed-table";
  const thead = document.createElement("thead");
  thead.innerHTML = "<tr>" + columns.map((c) => `<th>${c.label}</th>`).join("") + "</tr>";
  table.appendChild(thead);
  const tbody = document.createElement("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = columns.map((c) => `<td>${c.render ? c.render(row) : (row[c.key] ?? "")}</td>`).join("");
    tbody.appendChild(tr);
  });
  table.appendChild(tbody);
  wrap.appendChild(table);
  container.appendChild(wrap);
}

let cachedGameUpdates = null;
function loadGameUpdates() {
  if (cachedGameUpdates) return Promise.resolve(cachedGameUpdates);
  return fetch("/api/game-updates")
    .then((r) => r.json())
    .then((d) => (cachedGameUpdates = d));
}

let shipsData = null;

function renderShips(panel) {
  panel.innerHTML = `<div class="panel"><p>Loading ship data&hellip;</p></div>`;
  Promise.all([fetch("/api/ships").then((r) => r.json()), loadGameUpdates()]).then(([data, updates]) => {
    shipsData = data;
    panel.innerHTML = "";
    renderFleetUsage(panel, data);
    renderDistance(panel, data);
    renderIdleShips(panel, data);
    renderCoverage(panel, data);
    renderKillsDeaths(panel, data);
    renderComposition(panel, data);
    renderPerShipMix(panel, data, updates);
    renderFitVsUsage(panel, data);
  }).catch((e) => {
    panel.innerHTML = `<div class="panel"><p>Couldn't reach /api/ships -- ${e}</p></div>`;
  });
}

// Category with the most events for a ship, computed from the shared,
// unfiltered category_by_ship rows (functional-requirements.md doesn't
// restrict "dominant category" to real ships -- it's used purely for
// chart coloring here).
function dominantCategories(data) {
  const byShip = {};
  data.category_by_ship.forEach((r) => {
    byShip[r.ship] = byShip[r.ship] || {};
    byShip[r.ship][r.category] = r.n;
  });
  const dominant = {};
  Object.entries(byShip).forEach(([ship, cats]) => {
    let best = null, bestN = -1;
    Object.entries(cats).forEach(([cat, n]) => { if (n > bestN) { best = cat; bestN = n; } });
    dominant[ship] = best;
  });
  return dominant;
}

function renderFleetUsage(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Fleet Usage Overview</h2><p>Real flight-hours per ship (not raw event count -- see the walkthrough). Log scale. Colored by each ship's dominant activity.</p>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div, Math.max(240, data.flight.length * 22));

  const dominant = dominantCategories(data);
  const rows = [...data.flight].sort((a, b) => b.flight_hours - a.flight_hours);

  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.ship),
      datasets: [{
        label: "Flight hours",
        data: rows.map((r) => r.flight_hours),
        backgroundColor: rows.map((r) => CATEGORY_COLORS[dominant[r.ship]] || "#888"),
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: logAxis("Hours (log scale)") },
    },
  });
  gameplayCharts.push(chart);
}

function renderDistance(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Distance Traveled per Ship</h2><p>Total light-years jumped, from FSDJump's own JumpDist field. Log scale.</p>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div, Math.max(220, data.distance.length * 22));

  const rows = [...data.distance].sort((a, b) => b.light_years - a.light_years);
  const chart = new Chart(canvas, {
    type: "bar",
    data: {
      labels: rows.map((r) => r.ship),
      datasets: [{
        label: "Light-years",
        data: rows.map((r) => r.light_years),
        backgroundColor: "rgba(63, 169, 255, 0.6)",
      }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: { x: logAxis("Light-years (log scale)") },
    },
  });
  gameplayCharts.push(chart);
}

function renderIdleShips(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Idle-Ship Check</h2><p>Sorted longest-untouched first. A starting point for what to sell/store/repurpose, not a verdict.</p>`;
  panel.appendChild(div);

  const flightByShip = Object.fromEntries(data.flight.map((r) => [r.ship, r]));
  const distByShip = Object.fromEntries(data.distance.map((r) => [r.ship, r]));
  const dominant = dominantCategories(data);
  const now = new Date(data.dataset_now);

  const rows = data.last_active.map((r) => {
    const flight = flightByShip[r.ship] || { flight_hours: 0, trips: 0 };
    const dist = distByShip[r.ship] || { light_years: 0 };
    const daysIdle = (now - new Date(r.last_active)) / 86400000;
    return {
      ship: r.ship,
      days_idle: daysIdle,
      flight_hours: flight.flight_hours,
      avg_hours_trip: flight.trips ? flight.flight_hours / flight.trips : 0,
      light_years: dist.light_years,
      dominant: dominant[r.ship] || "--",
      last_active: r.last_active,
    };
  }).sort((a, b) => b.days_idle - a.days_idle);

  renderEdTable(div, [
    { label: "Ship", key: "ship" },
    { label: "Days Idle", render: (r) => r.days_idle.toFixed(0) },
    { label: "Flight Hrs", render: (r) => r.flight_hours.toFixed(1) },
    { label: "Avg Hrs/Trip", render: (r) => r.avg_hours_trip.toFixed(2) },
    { label: "Light-years", render: (r) => r.light_years.toLocaleString(undefined, { maximumFractionDigits: 0 }) },
    { label: "Dominant Activity", key: "dominant" },
    { label: "Last Active", render: (r) => r.last_active.slice(0, 10) },
  ], rows);
}

function renderCoverage(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Activity Coverage</h2><p>Which ship dominates each activity category, and how concentrated that is. Below 25% share is flagged as spread across the fleet rather than owned by one ship.</p>`;
  panel.appendChild(div);

  const byCategory = {};
  data.category_by_ship.forEach((r) => {
    if (!isRealShip(r.ship)) return;
    byCategory[r.category] = byCategory[r.category] || {};
    byCategory[r.category][r.ship] = r.n;
  });

  const THRESHOLD = 0.25;
  const rows = Object.entries(byCategory).map(([category, ships]) => {
    const total = Object.values(ships).reduce((a, b) => a + b, 0);
    let topShip = null, topN = -1;
    Object.entries(ships).forEach(([ship, n]) => { if (n > topN) { topShip = ship; topN = n; } });
    const share = total ? topN / total : 0;
    return { category, top_ship: topShip, share, flagged: share < THRESHOLD };
  }).sort((a, b) => b.share - a.share);

  renderEdTable(div, [
    { label: "Category", key: "category" },
    { label: "Top Ship", key: "top_ship" },
    { label: "Concentration", render: (r) => (r.share * 100).toFixed(1) + "%" },
    { label: "Note", render: (r) => (r.flagged ? '<span class="ed-flag-review">No dedicated ship</span>' : "") },
  ], rows);
}

function renderKillsDeaths(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Kills &amp; Deaths by Ship</h2><p>Ship-combat only (vehicle_state == SHIP). "Excluded" = same event, earned/suffered in an SRV or on foot instead.</p>`;
  panel.appendChild(div);

  const killsExcluded = Object.fromEntries(data.kills_excluded.map((r) => [r.ship, r.n]));
  const killRows = [...data.kills]
    .map((r) => ({ ...r, total: r.npc_kills + r.player_kills, excluded: killsExcluded[r.ship] || 0 }))
    .sort((a, b) => b.total - a.total);

  const h3a = document.createElement("h3");
  h3a.textContent = "Kills";
  h3a.style.cssText = "font-family:var(--ed-font-display);color:var(--ed-orange-dim);font-size:0.85em;text-transform:uppercase;letter-spacing:0.05em;margin-top:20px;";
  div.appendChild(h3a);
  renderEdTable(div, [
    { label: "Ship", key: "ship" },
    { label: "NPC", key: "npc_kills" },
    { label: "Player", key: "player_kills" },
    { label: "Excluded (SRV/foot)", key: "excluded" },
  ], killRows);

  const deathsByShip = {};
  data.deaths.forEach((r) => {
    deathsByShip[r.ship] = deathsByShip[r.ship] || { NPC: 0, Player: 0, "Self/Accident": 0 };
    deathsByShip[r.ship][r.opponent_type] = r.n;
  });
  const deathsExcluded = Object.fromEntries(data.deaths_excluded.map((r) => [r.ship, r.n]));
  const deathRows = Object.entries(deathsByShip).map(([ship, d]) => ({
    ship, npc: d.NPC, player: d.Player, self: d["Self/Accident"],
    total: d.NPC + d.Player + d["Self/Accident"],
    excluded: deathsExcluded[ship] || 0,
  })).sort((a, b) => b.total - a.total);

  const h3b = document.createElement("h3");
  h3b.textContent = "Deaths";
  h3b.style.cssText = h3a.style.cssText;
  div.appendChild(h3b);
  renderEdTable(div, [
    { label: "Ship", key: "ship" },
    { label: "NPC", key: "npc" },
    { label: "Player", key: "player" },
    { label: "Self/Accident", key: "self" },
    { label: "Excluded (SRV/foot)", key: "excluded" },
  ], deathRows);
}

function renderComposition(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Activity Composition by Ship</h2><p>Top 20 ships by event volume. Share of events by category.</p>`;
  panel.appendChild(div);
  const canvas = chartCanvas(div, 380);

  const top20 = data.ship_list.slice(0, 20).map((r) => r.ship);
  const byShip = {};
  data.category_by_ship.forEach((r) => {
    if (!top20.includes(r.ship)) return;
    byShip[r.ship] = byShip[r.ship] || {};
    byShip[r.ship][r.category] = r.n;
  });
  const categories = [...new Set(data.category_by_ship.map((r) => r.category))];
  const totals = Object.fromEntries(top20.map((s) => [s, Object.values(byShip[s] || {}).reduce((a, b) => a + b, 0)]));

  const datasets = categories.map((cat) => ({
    label: cat,
    data: top20.map((s) => {
      const n = (byShip[s] || {})[cat] || 0;
      return totals[s] ? +((n / totals[s]) * 100).toFixed(2) : 0;
    }),
    backgroundColor: CATEGORY_COLORS[cat] || "#888",
    stack: "mix",
  }));

  const chart = new Chart(canvas, {
    type: "bar",
    data: { labels: top20, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        x: { stacked: true, ticks: { maxRotation: 45, minRotation: 45, autoSkip: false, font: { size: 9 } } },
        y: { stacked: true, max: 100, title: { display: true, text: "% of events" } },
      },
      plugins: {
        legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%` } },
      },
    },
  });
  gameplayCharts.push(chart);
}

function renderPerShipMix(panel, data, gameUpdates) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Per-Ship Activity Mix Over Time</h2>`;

  const select = document.createElement("select");
  select.className = "ed-select";
  data.ship_list.forEach((r) => {
    const opt = document.createElement("option");
    opt.value = r.ship;
    opt.textContent = `${r.ship} (${r.n.toLocaleString()})`;
    select.appendChild(opt);
  });
  div.appendChild(select);
  panel.appendChild(div);

  const canvas = chartCanvas(div, 340);
  let chart = null;

  function load(ship) {
    fetch(`/api/ships/mix?ship=${encodeURIComponent(ship)}`)
      .then((r) => r.json())
      .then((res) => {
        const months = [...new Set(res.monthly.map((r) => r.month))].sort();
        const categories = [...new Set(res.monthly.map((r) => r.category))];
        const byMonth = {};
        res.monthly.forEach((r) => {
          byMonth[r.month] = byMonth[r.month] || {};
          byMonth[r.month][r.category] = r.n;
        });
        const totals = Object.fromEntries(months.map((m) => [m, Object.values(byMonth[m] || {}).reduce((a, b) => a + b, 0)]));
        const datasets = categories.map((cat) => ({
          label: cat,
          data: months.map((m) => {
            const n = (byMonth[m] || {})[cat] || 0;
            return totals[m] ? +((n / totals[m]) * 100).toFixed(2) : 0;
          }),
          backgroundColor: CATEGORY_COLORS[cat] || "#888",
          stack: "mix",
        }));
        if (chart) chart.destroy();
        chart = new Chart(canvas, {
          type: "bar",
          data: { labels: months, datasets },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: { mode: "index", intersect: false },
            scales: {
              x: { stacked: true, ticks: { maxRotation: 0, autoSkip: true } },
              y: { stacked: true, max: 100, title: { display: true, text: "% of events" } },
            },
            plugins: {
              legend: { position: "bottom", labels: { boxWidth: 12, font: { size: 10 } } },
              tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y}%` } },
            },
          },
          plugins: [referenceLinesPlugin(months, gameUpdates)],
        });
        gameplayCharts.push(chart);
      });
  }

  select.onchange = () => load(select.value);
  load(select.value);
}

function renderFitVsUsage(panel, data) {
  const div = document.createElement("div");
  div.className = "panel";
  div.innerHTML = `<h2>Fit-vs-Usage Findings</h2><p>Modules on each ship's most recent Loadout, cross-checked against that ship's own logged usage. Not an optimal-fit calculator -- flags a mismatch, shows the raw evidence, nothing more.</p>`;
  panel.appendChild(div);

  const rows = [...data.fit_findings].sort((a, b) => a.ship.localeCompare(b.ship));
  renderEdTable(div, [
    { label: "Ship", key: "ship" },
    { label: "Role", key: "role" },
    { label: "Slot", key: "slot" },
    { label: "Item", render: (r) => `<code>${r.item}</code>` },
    {
      label: "Severity",
      render: (r) => `<span class="${r.severity.startsWith("Likely") ? "ed-flag-unnecessary" : "ed-flag-review"}">${r.severity}</span>`,
    },
    { label: "Evidence", key: "reason" },
  ], rows);

  if (data.fit_clean_ships.length) {
    const note = document.createElement("p");
    note.className = "ed-note";
    note.textContent = "No flags raised for: " + [...data.fit_clean_ships].sort().join(", ");
    div.appendChild(note);
  }
}

function tabIdFromHash() {
  const h = location.hash.replace(/^#/, "");
  return TABS.some((t) => t.id === h) ? h : "overview";
}

activateTab(tabIdFromHash());
