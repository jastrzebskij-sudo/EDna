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

function tabIdFromHash() {
  const h = location.hash.replace(/^#/, "");
  return TABS.some((t) => t.id === h) ? h : "overview";
}

activateTab(tabIdFromHash());
