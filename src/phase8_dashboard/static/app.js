/**
 * AeroPulse AI — Interactive Dashboard Application Logic
 * Integrates Chart.js visualizations, Live ML Inference, and DuckDB OLAP Console.
 */

// Global chart registry to prevent canvas reuse errors
const charts = {};

// Preset SQL Queries for OLAP Console
const SQL_PRESETS = {
  preset1: `-- Top 10 Flight Routes with Highest Total Delay Minutes
SELECT 
    r.route_name as Route,
    count(*) as Flights,
    sum(f.arr_del15) as Delayed_Flights,
    round(sum(f.arr_del15) * 100.0 / count(*), 2) as Delay_Rate_Pct,
    round(sum(CASE WHEN f.arr_delay > 0 THEN f.arr_delay ELSE 0 END), 0) as Total_Delay_Minutes,
    round(avg(f.arr_delay), 2) as Avg_Delay_Minutes
FROM fact_flights f
JOIN dim_route r ON f.route_key = r.route_key
WHERE f.cancelled = 0 AND f.diverted = 0
GROUP BY r.route_name
ORDER BY Total_Delay_Minutes DESC
LIMIT 10;`,

  preset2: `-- Carrier Performance Rollup by Quarter
SELECT 
    d.quarter as Quarter,
    c.carrier_name as Airline,
    count(*) as Flights,
    round(sum(f.arr_del15) * 100.0 / count(*), 2) as Delay_Rate_Pct,
    round(avg(f.arr_delay), 2) as Avg_Arr_Delay,
    round(sum(f.cancelled) * 100.0 / count(*), 2) as Cancel_Rate_Pct
FROM fact_flights f
JOIN dim_carrier c ON f.carrier_key = c.carrier_key
JOIN dim_date d ON f.date_key = d.date_key
WHERE f.cancelled = 0
GROUP BY d.quarter, c.carrier_name
ORDER BY d.quarter, Flights DESC
LIMIT 15;`,

  preset3: `-- Top 10 Airports with Highest Surface Taxi Friction & NAS Impact
SELECT 
    a.iata_code as Airport,
    a.city_name as City,
    count(*) as Departures,
    round(avg(f.taxi_out), 2) as Avg_Taxi_Out_Mins,
    round(avg(f.dep_delay), 2) as Avg_Dep_Delay_Mins,
    round(sum(f.arr_del15) * 100.0 / count(*), 2) as Delay_Rate_Pct
FROM fact_flights f
JOIN dim_airport a ON f.origin_key = a.airport_key
WHERE f.cancelled = 0 AND f.diverted = 0
GROUP BY a.iata_code, a.city_name
HAVING count(*) >= 25000
ORDER BY Avg_Taxi_Out_Mins DESC
LIMIT 10;`,

  preset4: `-- Delay Causation Decomposition by Carrier
SELECT 
    c.carrier_code as Carrier,
    round(sum(f.carrier_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 1) as Carrier_Share_Pct,
    round(sum(f.late_aircraft_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 1) as Late_Aircraft_Share_Pct,
    round(sum(f.nas_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 1) as NAS_Share_Pct,
    round(sum(f.weather_delay) * 100.0 / nullif(sum(f.carrier_delay + f.weather_delay + f.nas_delay + f.security_delay + f.late_aircraft_delay), 0), 1) as Weather_Share_Pct
FROM fact_flights f
JOIN dim_carrier c ON f.carrier_key = c.carrier_key
WHERE f.arr_del15 = 1
GROUP BY c.carrier_code
ORDER BY count(*) DESC;`
};

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupHourSlider();
  setupPredictor();
  setupSQLConsole();
  loadAllData();
});

// Tab Switching
function setupTabs() {
  const tabBtns = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTab = btn.getAttribute("data-tab");

      tabBtns.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));

      btn.classList.add("active");
      const activeContent = document.getElementById(`tab-${targetTab}`);
      if (activeContent) {
        activeContent.classList.add("active");
      }

      // Re-render charts when visible to prevent layout glitches
      window.dispatchEvent(new Event("resize"));
    });
  });
}

// Departure Hour Slider Sync
function setupHourSlider() {
  const slider = document.getElementById("pred-hour");
  const label = document.getElementById("pred-hour-label");
  if (slider && label) {
    slider.addEventListener("input", (e) => {
      const h = parseInt(e.target.value);
      const period = h >= 12 ? "PM" : "AM";
      const h12 = h % 12 === 0 ? 12 : h % 12;
      label.textContent = `${h.toString().padStart(2, "0")}:00 (${h12}:00 ${period})`;
    });
  }
}

// Load All Backend Data
async function loadAllData() {
  try {
    const [overviewRes, edaRes, olapRes, miningRes, mlRes] = await Promise.all([
      fetch("/api/overview").then(r => r.json()),
      fetch("/api/eda").then(r => r.json()),
      fetch("/api/olap").then(r => r.json()),
      fetch("/api/mining").then(r => r.json()),
      fetch("/api/ml_metrics").then(r => r.json())
    ]);

    renderOverview(overviewRes, edaRes);
    renderEDA(edaRes);
    renderWarehouse(olapRes);
    renderMining(miningRes);
    renderMLMetrics(mlRes);

  } catch (err) {
    console.error("Error loading dashboard data:", err);
  }
}

// 1. Render Overview
function renderOverview(overview, eda) {
  if (overview.status_summary) {
    const s = overview.status_summary;
    document.getElementById("kpi-total-flights").textContent = s.total.toLocaleString();
    document.getElementById("kpi-completed-flights").textContent = Math.round(s.completed_count).toLocaleString();
    document.getElementById("kpi-ontime-rate").textContent = (100 - overview.delay_summary.delayed_15_pct).toFixed(2) + "%";
    document.getElementById("kpi-delay-rate").textContent = overview.delay_summary.delayed_15_pct + "%";
    document.getElementById("kpi-cancel-rate").textContent = s.cancel_pct + "%";
  }

  // Delay Causes Chart
  const causes = overview.delay_causes || {};
  const causeLabels = Object.keys(causes);
  const causeValues = causeLabels.map(k => causes[k].pct);
  const causeColors = ["#8b5cf6", "#3b82f6", "#06b6d4", "#f59e0b", "#f43f5e"];

  renderChart("chart-delay-causes", {
    type: "doughnut",
    data: {
      labels: causeLabels,
      datasets: [{
        data: causeValues,
        backgroundColor: causeColors,
        borderWidth: 0,
        hoverOffset: 6
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false }
      },
      cutout: "68%"
    }
  });

  // Legend Items
  const legendContainer = document.getElementById("cause-legend");
  if (legendContainer) {
    legendContainer.innerHTML = causeLabels.map((k, i) => `
      <div class="cause-legend-item">
        <div class="legend-badge">
          <span class="legend-color-dot" style="background:${causeColors[i]}"></span>
          <span>${k}</span>
        </div>
        <div class="legend-val">${causes[k].pct}%</div>
        <div class="legend-sub">${(causes[k].minutes / 1e6).toFixed(1)}M mins</div>
      </div>
    `).join("");
  }

  // Monthly Seasonality Curve
  if (eda.monthly_trends) {
    const months = eda.monthly_trends.map(m => m.month_name.substring(0, 3));
    const delayRates = eda.monthly_trends.map(m => m.delay_rate_pct);
    const flightVols = eda.monthly_trends.map(m => Math.round(m.total_flights / 1000));

    renderChart("chart-monthly-trend", {
      type: "line",
      data: {
        labels: months,
        datasets: [
          {
            label: "Delay Rate (%)",
            data: delayRates,
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.1)",
            fill: true,
            tension: 0.4,
            yAxisID: "y"
          },
          {
            label: "Volume (k Flights)",
            data: flightVols,
            borderColor: "rgba(148, 163, 184, 0.4)",
            borderDash: [5, 5],
            tension: 0.4,
            yAxisID: "y1"
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
          y: { 
            grid: { color: "rgba(255,255,255,0.05)" }, 
            ticks: { color: "#06b6d4", callback: v => v + "%" },
            title: { display: true, text: "Delay Rate", color: "#06b6d4" }
          },
          y1: {
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: { color: "#94a3b8" },
            title: { display: true, text: "Flights (Thousands)", color: "#94a3b8" }
          }
        },
        plugins: {
          legend: { labels: { color: "#f8fafc" } }
        }
      }
    });
  }
}

// 2. Render EDA
function renderEDA(eda) {
  // Carrier Comparison Bar Chart
  if (eda.carrier_performance) {
    const carriers = eda.carrier_performance.map(c => c.carrier);
    const delayRates = eda.carrier_performance.map(c => c.delay_rate_pct);
    const avgDelays = eda.carrier_performance.map(c => c.avg_arr_delay_min);

    renderChart("chart-carrier-performance", {
      type: "bar",
      data: {
        labels: carriers,
        datasets: [
          {
            label: "Arrival Delay Rate (%)",
            data: delayRates,
            backgroundColor: "rgba(6, 182, 212, 0.75)",
            borderRadius: 6
          },
          {
            label: "Avg Arrival Delay (min)",
            data: avgDelays,
            backgroundColor: "rgba(139, 92, 246, 0.75)",
            borderRadius: 6
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#f8fafc" } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } }
        },
        plugins: {
          legend: { labels: { color: "#f8fafc" } }
        }
      }
    });
  }

  // Hourly Curve
  if (eda.hourly_trends) {
    const hours = eda.hourly_trends.map(h => `${h.dep_hour.toString().padStart(2, "0")}:00`);
    const hourlyRates = eda.hourly_trends.map(h => h.delay_rate_pct);

    renderChart("chart-hourly-curve", {
      type: "line",
      data: {
        labels: hours,
        datasets: [{
          label: "Delay Probability (%)",
          data: hourlyRates,
          borderColor: "#f59e0b",
          backgroundColor: "rgba(245, 158, 11, 0.15)",
          fill: true,
          tension: 0.35,
          pointRadius: 3
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8", maxTicksLimit: 12 } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#f59e0b", callback: v => v + "%" } }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  // Day of Week Pattern
  if (eda.day_of_week_trends) {
    const days = eda.day_of_week_trends.map(d => d.day_name.substring(0, 3));
    const dowRates = eda.day_of_week_trends.map(d => d.delay_rate_pct);

    renderChart("chart-dow-pattern", {
      type: "bar",
      data: {
        labels: days,
        datasets: [{
          label: "Delay Rate (%)",
          data: dowRates,
          backgroundColor: dowRates.map(v => v > 22.0 ? "rgba(244, 63, 94, 0.8)" : "rgba(59, 130, 246, 0.75)"),
          borderRadius: 6
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
          y: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8", callback: v => v + "%" } }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  // Top Origin Airports Table
  if (eda.top_airports) {
    const tbody = document.querySelector("#table-top-airports tbody");
    if (tbody) {
      tbody.innerHTML = eda.top_airports.map(a => {
        let riskBadge = `<span class="badge-chip">Moderate</span>`;
        if (a.delay_rate_pct >= 25.0) {
          riskBadge = `<span class="badge-chip" style="background:rgba(244,63,94,0.15);color:#fb7185;border-color:rgba(244,63,94,0.3)">High Congestion</span>`;
        } else if (a.delay_rate_pct < 19.0) {
          riskBadge = `<span class="badge-chip" style="background:rgba(16,185,129,0.15);color:#34d399;border-color:rgba(16,185,129,0.3)">Fluid Flow</span>`;
        }

        return `
          <tr>
            <td><strong>${a.airport_code}</strong></td>
            <td>${a.city}, ${a.state}</td>
            <td>${a.total_departures.toLocaleString()}</td>
            <td><strong>${a.delay_rate_pct}%</strong></td>
            <td>${a.avg_dep_delay_min} m</td>
            <td>${a.avg_arr_delay_min} m</td>
            <td>${riskBadge}</td>
          </tr>
        `;
      }).join("");
    }
  }
}

// 3. Render Warehouse & OLAP
function renderWarehouse(olap) {
  if (olap.route_pareto) {
    const tbody = document.querySelector("#table-route-pareto tbody");
    if (tbody) {
      tbody.innerHTML = olap.route_pareto.slice(0, 15).map(r => `
        <tr>
          <td><span class="badge-chip">#${r.delay_rank}</span></td>
          <td><strong>${r.route_name}</strong></td>
          <td>${r.distance_group}</td>
          <td>${r.total_flights.toLocaleString()}</td>
          <td>${r.delay_rate_pct}%</td>
          <td><strong class="text-amber">${Math.round(r.total_delay_mins).toLocaleString()} m</strong></td>
          <td>${r.avg_arr_delay_min} m</td>
          <td><span class="badge-chip badge-cyan">${r.cumulative_delay_pct}%</span></td>
        </tr>
      `).join("");
    }
  }
}

// 4. Render Data Mining
function renderMining(mining) {
  const tableBody = document.querySelector("#table-association-rules tbody");
  const sortSelect = document.getElementById("select-rule-sort");

  function displayRules(sortBy = "lift") {
    if (!mining.association_rules || !tableBody) return;

    let rules = [...mining.association_rules];
    if (sortBy === "lift") {
      rules.sort((a, b) => b.lift - a.lift);
    } else if (sortBy === "confidence") {
      rules.sort((a, b) => b.confidence - a.confidence);
    } else if (sortBy === "support") {
      rules.sort((a, b) => b.support - a.support);
    }

    tableBody.innerHTML = rules.slice(0, 20).map(r => {
      let riskTag = `<span class="badge-chip">Elevated</span>`;
      if (r.lift >= 2.2) {
        riskTag = `<span class="badge-chip" style="background:rgba(244,63,94,0.15);color:#fb7185;border-color:rgba(244,63,94,0.3)">Severe Vulnerability</span>`;
      } else if (r.lift >= 1.8) {
        riskTag = `<span class="badge-chip" style="background:rgba(245,158,11,0.15);color:#fbbf24;border-color:rgba(245,158,11,0.3)">High Delay Likelihood</span>`;
      }

      return `
        <tr>
          <td><code>${r.antecedent.join(" AND ")}</code></td>
          <td><span class="text-white">${r.consequent.join(", ")}</span></td>
          <td><strong>${(r.confidence * 100).toFixed(1)}%</strong></td>
          <td><strong class="text-purple">${r.lift.toFixed(2)}x</strong></td>
          <td>${(r.support * 100).toFixed(2)}%</td>
          <td>${r.matched_flights.toLocaleString()}</td>
          <td>${riskTag}</td>
        </tr>
      `;
    }).join("");
  }

  if (sortSelect) {
    sortSelect.addEventListener("change", (e) => displayRules(e.target.value));
  }
  displayRules("lift");

  // Render K-Means Clusters
  const clustersContainer = document.getElementById("clusters-container");
  if (clustersContainer && mining.clustering_analysis && mining.clustering_analysis.cluster_profiles) {
    clustersContainer.innerHTML = mining.clustering_analysis.cluster_profiles.map(cp => `
      <div class="cluster-card">
        <div class="cluster-card-header">
          <span class="cluster-title">${cp.cluster_name}</span>
          <span class="cluster-badge">${cp.airport_count} Hubs</span>
        </div>
        <p class="cluster-desc">${cp.description}</p>
        <div class="cluster-stats-row">
          <span>Mean Arrival Delay Rate:</span>
          <strong class="text-white">${cp.centroid_metrics.arr_delay_rate}%</strong>
        </div>
        <div class="cluster-stats-row">
          <span>Mean Departure Taxi-Out:</span>
          <strong class="text-white">${cp.centroid_metrics.avg_taxi_out} min</strong>
        </div>
        <div class="cluster-stats-row">
          <span>NAS Ground Delay Impact:</span>
          <strong class="text-white">${cp.centroid_metrics.avg_nas_delay} min</strong>
        </div>
        <div class="cluster-airports">
          Sample Hubs: <code>${cp.sample_airports.join(", ")}</code>
        </div>
      </div>
    `).join("");
  }
}

// 5. Render ML Metrics & ROC Curve
function renderMLMetrics(ml) {
  // Feature Importances
  if (ml.feature_importances) {
    const features = ml.feature_importances.map(f => f.feature);
    const scores = ml.feature_importances.map(f => f.importance);

    renderChart("chart-feature-importance", {
      type: "bar",
      data: {
        labels: features,
        datasets: [{
          label: "Importance (ROC-AUC Impact)",
          data: scores,
          backgroundColor: "rgba(139, 92, 246, 0.8)",
          borderRadius: 6
        }]
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { color: "rgba(255,255,255,0.05)" }, ticks: { color: "#94a3b8" } },
          y: { grid: { display: false }, ticks: { color: "#f8fafc" } }
        },
        plugins: {
          legend: { display: false }
        }
      }
    });
  }

  // ROC Curve
  if (ml.roc_curve) {
    const fprs = ml.roc_curve.map(p => p.fpr);
    const tprs = ml.roc_curve.map(p => p.tpr);

    renderChart("chart-roc-curve", {
      type: "line",
      data: {
        labels: fprs,
        datasets: [
          {
            label: "HistGradientBoosting (AUC = 0.612)",
            data: tprs,
            borderColor: "#06b6d4",
            backgroundColor: "rgba(6, 182, 212, 0.1)",
            fill: true,
            tension: 0.2
          },
          {
            label: "Random Baseline (AUC = 0.50)",
            data: fprs,
            borderColor: "rgba(148, 163, 184, 0.4)",
            borderDash: [4, 4],
            pointRadius: 0
          }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { title: { display: true, text: "False Positive Rate (1 - Specificity)", color: "#94a3b8" }, ticks: { color: "#94a3b8" } },
          y: { title: { display: true, text: "True Positive Rate (Sensitivity)", color: "#94a3b8" }, ticks: { color: "#94a3b8" } }
        },
        plugins: {
          legend: { labels: { color: "#f8fafc" } }
        }
      }
    });
  }
}

// 6. Interactive Flight Delay Predictor Simulator
function setupPredictor() {
  const form = document.getElementById("prediction-form");
  if (!form) return;

  form.addEventListener("submit", async (e) => {
    e.preventDefault();

    const carrier = document.getElementById("pred-carrier").value;
    const origin = document.getElementById("pred-origin").value;
    const dest = document.getElementById("pred-dest").value;
    const month = parseInt(document.getElementById("pred-month").value);
    const dow = parseInt(document.getElementById("pred-dow").value);
    const hour = parseInt(document.getElementById("pred-hour").value);

    const btn = document.getElementById("btn-predict");
    btn.innerHTML = "Computing ML Inference...";
    btn.disabled = true;

    try {
      const resp = await fetch("/api/predict", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          carrier,
          origin,
          dest,
          month,
          day_of_week: dow,
          day_of_month: 15,
          dep_hour: hour
        })
      });

      const data = await resp.json();

      // Update Gauge
      const prob = data.delay_probability;
      const gaugeCircle = document.getElementById("gauge-circle");
      const probText = document.getElementById("res-probability");
      const badge = document.getElementById("res-risk-badge");

      probText.textContent = `${prob}%`;
      badge.textContent = data.risk_tier;
      badge.style.backgroundColor = `${data.risk_color}22`;
      badge.style.borderColor = data.risk_color;
      badge.style.color = data.risk_color;

      const deg = Math.round((prob / 100) * 360);
      gaugeCircle.style.background = `conic-gradient(${data.risk_color} ${deg}deg, rgba(255, 255, 255, 0.05) ${deg}deg)`;

      // Update Stats
      document.getElementById("res-delay-mins").textContent = `~${data.expected_delay_minutes} min`;
      document.getElementById("res-distance").textContent = `${Math.round(data.distance_miles)} mi`;
      document.getElementById("res-duration").textContent = `${Math.round(data.flight_duration_min)} min`;
      document.getElementById("res-binary-class").textContent = data.predicted_delay ? "Delayed (≥15m)" : "On-Time Arrival";
      document.getElementById("res-binary-class").style.color = data.predicted_delay ? "#fb7185" : "#34d399";

      // Render Primary Root Cause Spotlight
      const spotlightBox = document.getElementById("primary-cause-spotlight");
      if (spotlightBox && data.primary_cause) {
        document.getElementById("spotlight-title").textContent = data.primary_cause.name;
        document.getElementById("spotlight-desc").textContent = data.primary_cause.description;
        document.getElementById("spotlight-impact").textContent = `${data.primary_cause.percentage}% (${data.primary_cause.minutes} mins)`;
        spotlightBox.style.display = "block";
      }

      // Render Detailed Cause Decomposition Progress Bars
      const barsContainer = document.getElementById("causes-bars-container");
      if (barsContainer && data.causes_breakdown) {
        barsContainer.innerHTML = data.causes_breakdown.map(c => `
          <div class="cause-bar-item">
            <div class="cause-bar-label-row">
              <span class="cause-bar-name">
                <span class="legend-color-dot" style="background:${c.color}"></span>
                ${c.cause}
              </span>
              <div class="cause-bar-metrics">
                <span class="cause-bar-pct" style="color:${c.color}">${c.percentage}%</span>
                <span class="cause-bar-mins">(~${c.est_minutes} min)</span>
              </div>
            </div>
            <div class="cause-bar-track">
              <div class="cause-bar-fill" style="width:${c.percentage}%;background:${c.color}"></div>
            </div>
            <div class="cause-bar-explain">${c.explanation}</div>
          </div>
        `).join("");
      }

      // Update Risk Factors
      const factorList = document.getElementById("res-risk-factors");
      if (data.risk_factors && data.risk_factors.length > 0) {
        factorList.innerHTML = data.risk_factors.map(f => `<li>${f}</li>`).join("");
      } else {
        factorList.innerHTML = `<li>Favorable conditions across route.</li>`;
      }

      // Render Mitigation Tip
      const mitigationBox = document.getElementById("mitigation-box");
      const mitigationText = document.getElementById("mitigation-text");
      if (mitigationBox && mitigationText && data.mitigation_tip) {
        mitigationText.textContent = data.mitigation_tip;
        mitigationBox.style.display = "flex";
      }

    } catch (err) {
      console.error("Predict error:", err);
    } finally {
      btn.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2v4"/><path d="M12 18v4"/><path d="M4.93 4.93l2.83 2.83"/><path d="M16.24 16.24l2.83 2.83"/><path d="M2 12h4"/><path d="M18 12h4"/><path d="M4.93 19.07l2.83-2.83"/><path d="M16.24 7.76l2.83-2.83"/></svg> Predict Flight Delay Risk`;
      btn.disabled = false;
    }
  });

  // Trigger initial prediction for default values
  setTimeout(() => {
    form.dispatchEvent(new Event("submit"));
  }, 500);
}

// 7. Interactive SQL OLAP Console
function setupSQLConsole() {
  const select = document.getElementById("select-sql-preset");
  const input = document.getElementById("sql-query-input");
  const runBtn = document.getElementById("btn-run-query");
  const resultsArea = document.getElementById("sql-results-container");
  const timeBadge = document.getElementById("sql-execution-time");

  if (!input || !runBtn) return;

  // Set default query
  input.value = SQL_PRESETS["preset1"];

  if (select) {
    select.addEventListener("change", (e) => {
      if (SQL_PRESETS[e.target.value]) {
        input.value = SQL_PRESETS[e.target.value];
      }
    });
  }

  runBtn.addEventListener("click", async () => {
    const query = input.value.trim();
    if (!query) return;

    runBtn.disabled = true;
    runBtn.textContent = "Executing...";
    resultsArea.innerHTML = `<div class="placeholder-text">Running query against 7,079,081 rows in DuckDB...</div>`;

    try {
      const resp = await fetch("/api/query", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query })
      });

      const res = await resp.json();

      if (res.error) {
        resultsArea.innerHTML = `<div style="padding:1.5rem;color:#fb7185;">Error: ${res.error}</div>`;
        timeBadge.textContent = "Failed";
      } else {
        timeBadge.textContent = `Executed in ${res.execution_ms} ms (${res.total_returned} rows)`;

        if (!res.rows || res.rows.length === 0) {
          resultsArea.innerHTML = `<div class="placeholder-text">Query returned 0 rows.</div>`;
        } else {
          const cols = res.columns;
          const tableHtml = `
            <table class="data-table">
              <thead>
                <tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr>
              </thead>
              <tbody>
                ${res.rows.map(r => `
                  <tr>${cols.map(c => `<td>${r[c] !== null ? r[c] : "NULL"}</td>`).join("")}</tr>
                `).join("")}
              </tbody>
            </table>
          `;
          resultsArea.innerHTML = tableHtml;
        }
      }
    } catch (err) {
      resultsArea.innerHTML = `<div style="padding:1.5rem;color:#fb7185;">Network or execution error: ${err}</div>`;
      timeBadge.textContent = "Error";
    } finally {
      runBtn.disabled = false;
      runBtn.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="5 3 19 12 5 21 5 3"/></svg> Execute OLAP Query`;
    }
  });
}

// Helper: Safely Create or Replace Chart.js instance
function renderChart(canvasId, config) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  if (charts[canvasId]) {
    charts[canvasId].destroy();
  }

  charts[canvasId] = new Chart(canvas, config);
}
