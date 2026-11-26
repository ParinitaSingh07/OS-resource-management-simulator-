/* ==========================================================================
   OS Resource Management Simulator — web GUI logic
   --------------------------------------------------------------------------
   The browser never computes scheduling or allocation itself: every number on
   this page comes from a POST to webapp/server.py, which calls the same Python
   modules the terminal menu uses. This file only builds requests, then turns
   the JSON back into cards, tables, Gantt bars, memory maps and seek paths.
   ========================================================================== */

(() => {
  "use strict";

  /* ---------------------------------------------------------------- state */
  const state = {
    meta: null,
    deadlockAction: "safety",
  };

  const PALETTE = [
    "#4e79a7", "#f28e2b", "#59a14f", "#e15759", "#76b7b2",
    "#edc948", "#b07aa1", "#ff9da7", "#9c755f", "#bab0ac",
  ];
  const IDLE_COLOUR = "#d9d9d9";

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const esc = (value) =>
    String(value).replace(/[&<>"']/g, (ch) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
    }[ch]));

  const fmt = (value, digits = 2) =>
    Number.isFinite(Number(value)) ? Number(value).toFixed(digits) : "—";

  const colourFor = (pid, index) =>
    PALETTE[(index >= 0 ? index : Math.abs(hash(pid))) % PALETTE.length];

  function hash(text) {
    let h = 0;
    for (let i = 0; i < text.length; i += 1) h = (h * 31 + text.charCodeAt(i)) | 0;
    return h;
  }

  /* ------------------------------------------------------------- API calls */
  async function api(path, body) {
    const options = body
      ? { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }
      : {};
    const response = await fetch(path, options);
    let payload;
    try {
      payload = await response.json();
    } catch {
      throw new Error(`server returned ${response.status} (not JSON)`);
    }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.error || `request failed (${response.status})`);
    }
    return payload.data;
  }

  /* --------------------------------------------------------- UI fragments */
  function statCard(label, value, unit = "", tone = "") {
    return `<div class="stat ${tone}">
      <div class="k">${esc(label)}</div>
      <div class="v">${esc(value)}${unit ? `<small>${esc(unit)}</small>` : ""}</div>
    </div>`;
  }

  function statRow(items) {
    return `<div class="stat-row">${items.map((i) => statCard(...i)).join("")}</div>`;
  }

  function table(headers, rows, numericFrom = 99) {
    const head = headers
      .map((h, i) => `<th class="${i >= numericFrom ? "num" : ""}">${esc(h)}</th>`)
      .join("");
    const body = rows
      .map((row) => `<tr>${row
        .map((cell, i) => `<td class="${i >= numericFrom ? "num" : ""}">${cell}</td>`)
        .join("")}</tr>`)
      .join("");
    return `<div class="table-wrap"><table><thead><tr>${head}</tr></thead><tbody>${body}</tbody></table></div>`;
  }

  function card(title, bodyHtml, hint = "") {
    return `<section class="card">
      <div class="res-card-head"><h3>${esc(title)}</h3>${hint ? `<span class="hint">${esc(hint)}</span>` : ""}</div>
      ${bodyHtml}
    </section>`;
  }

  function ganttHtml(gantt, total) {
    if (!gantt.length) return "";
    const span = Math.max(total, 1);
    const pids = [...new Set(gantt.map((g) => g.pid))].filter((p) => p !== "IDLE");
    const colourOf = (pid) =>
      pid === "IDLE" ? IDLE_COLOUR : colourFor(pid, pids.indexOf(pid));

    const segments = gantt
      .map((g) => {
        const width = ((g.end - g.start) / span) * 100;
        const label = width > 4 ? esc(g.pid) : "";
        return `<div class="gantt-seg ${g.pid === "IDLE" ? "idle" : ""}"
          style="width:${width}%;background:${colourOf(g.pid)}"
          title="${esc(g.pid)} · ${g.start} → ${g.end} (${g.end - g.start})">
          <span>${label}</span></div>`;
      })
      .join("");

    const ticks = [0, Math.round(span / 2), span]
      .map((t) => `<span>${t}</span>`)
      .join("");

    const legend = gantt.length
      ? `<div class="gantt-legend">${pids
          .map((pid) => `<span class="legend-item">
            <span class="swatch" style="background:${colourOf(pid)}"></span>${esc(pid)}</span>`)
          .join("")}<span class="legend-item">
            <span class="swatch" style="background:repeating-linear-gradient(45deg,#1d2b42 0 3px,#16223a 3px 6px)"></span>idle</span>
        </div>`
      : "";

    return `<div class="gantt">
      <div class="gantt-track">${segments}</div>
      <div class="gantt-axis">${ticks}</div>
      ${legend}
    </div>`;
  }

  // One bar, scaled against a caller-supplied maximum so that every row in a
  // comparison uses the SAME axis (otherwise every algorithm looks full width).
  function barLine(value, max, className) {
    const numeric = Number(value) || 0;
    const pct = max > 0 ? (numeric / max) * 100 : 0;
    return `<div class="bar-line">
      <div class="bar-fill ${className}" style="width:${Math.max(pct, 1.5)}%"></div>
      <span class="bar-val">${fmt(numeric)}</span>
    </div>`;
  }

  function comparisonHtml(results, keys, labels) {
    const best = keys.map((key) => {
      let winner = results[0];
      results.forEach((r) => {
        if (Number(r[key]) < Number(winner[key])) winner = r;
      });
      return winner;
    });
    const maxima = keys.map((key) =>
      Math.max(...results.map((r) => Number(r[key]) || 0), 0.001));

    return `<div class="bar-key">
        ${keys.map((key, i) => `<span class="legend-item">
          <span class="swatch" style="background:${i === 0 ? "#38bdf8" : "#a78bfa"}"></span>${esc(labels[i])}</span>`).join("")}
      </div>
      <div class="bars">
        ${results.map((r) => `<div class="bar-row">
          <div class="bar-name">${esc(r.label)}</div>
          <div class="bar-track">
            ${barLine(r[keys[0]], maxima[0], "wait")}
            ${barLine(r[keys[1]], maxima[1], "turn")}
          </div>
        </div>`).join("")}
      </div>
      <p class="muted small" style="margin-top:12px">
        Lowest ${esc(labels[0])}: <span class="pick">${esc(best[0].label)}</span>
        &nbsp;·&nbsp; Lowest ${esc(labels[1])}: <span class="pick">${esc(best[1].label)}</span>
      </p>`;
  }

  /* ------------------------------------------------------------- run/status */
  async function runWith(button, statusEl, fn) {
    button.disabled = true;
    statusEl.className = "status";
    statusEl.textContent = "Running…";
    try {
      await fn();
      statusEl.className = "status good";
      statusEl.textContent = "Done.";
    } catch (error) {
      statusEl.className = "status bad";
      statusEl.textContent = error.message;
    } finally {
      button.disabled = false;
    }
  }

  function payloadFrom(kind, prefix) {
    const useText = $(`#${prefix}-use-text`).checked;
    const body = {};
    if (useText) body.text = $(`#${prefix}-text`).value;
    else body.dataset = $(`#${prefix}-dataset`).value;
    return body;
  }

  /* ------------------------------------------------------------------ CPU */
  async function runCpu() {
    const body = payloadFrom("cpu", "cpu");
    body.algorithm = $("#cpu-algorithm").value;
    body.quantum = Number($("#cpu-quantum").value) || 4;

    const data = await api("/api/cpu", body);
    const results = data.results;
    const single = results.length === 1;
    const out = [];

    if (!single) {
      out.push(card(
        "Comparison",
        comparisonHtml(results, ["avg_waiting", "avg_turnaround"], ["avg waiting", "avg turnaround"]) +
          table(
            ["Algorithm", "Avg waiting", "Avg turnaround", "Avg response", "CPU util %", "Throughput"],
            results.map((r) => [
              esc(r.label),
              fmt(r.avg_waiting),
              fmt(r.avg_turnaround),
              fmt(r.avg_response),
              fmt(r.cpu_utilisation),
              fmt(r.throughput, 3),
            ]),
            1,
          ),
        `${data.processes} processes · quantum ${data.quantum}`,
      ));
    }

    results.forEach((res, index) => {
      const stats = statRow([
        ["Avg waiting", fmt(res.avg_waiting), "units", "accent"],
        ["Avg turnaround", fmt(res.avg_turnaround), "units"],
        ["Avg response", fmt(res.avg_response), "units"],
        ["CPU utilisation", fmt(res.cpu_utilisation), "%", "good"],
        ["Throughput", fmt(res.throughput, 3), "/unit"],
        ["Total time", String(res.total_time), "units"],
        ["Idle time", String(res.idle_time), "units"],
      ]);

      const rows = res.rows.map((r) => [
        esc(r.pid), r.arrival, r.burst, r.priority, r.completion,
        r.turnaround, r.waiting, r.response,
      ]);

      const processTable = table(
        ["PID", "Arrival", "Burst", "Priority", "Completion", "Turnaround", "Waiting", "Response"],
        rows,
        1,
      );

      const hint = res.name === "RR" ? `quantum ${res.quantum}` : res.label;
      const inner = `${stats}<div class="divider"></div>${ganttHtml(res.gantt, res.total_time)}${processTable}`;

      if (single) {
        out.push(card(`${res.label} result`, inner, hint));
      } else {
        out.push(`<details class="card" ${index === 0 ? "open" : ""}>
          <summary class="res-card-head" style="cursor:pointer;list-style:none">
            <h3>${esc(res.label)}</h3><span class="hint">${esc(hint)} · avg wait ${fmt(res.avg_waiting)}</span>
          </summary>
          <div class="divider"></div>${inner}
        </details>`);
      }
    });

    $("#cpu-results").innerHTML = out.join("");
  }

  /* --------------------------------------------------------------- Memory */
  function memoryMap(blocks) {
    const total = blocks.reduce((sum, b) => sum + b.size, 0) || 1;
    return `<div class="mem-map">${blocks
      .map((b) => {
        const width = Math.max((b.size / total) * 100, 7);
        if (b.free) {
          return `<div class="mem-block free" style="width:${width}%"
            title="Block ${b.block_id} · free · ${b.size} units">
            <b>free</b><small>B${b.block_id} · ${b.size}</small></div>`;
        }
        const colour = colourFor(b.pid, -1);
        return `<div class="mem-block used" style="width:${width}%;background:${colour}"
          title="Block ${b.block_id} · ${b.pid} uses ${b.used} of ${b.size}">
          <b>${esc(b.pid)}</b><small>${b.size} u${b.used < b.size ? ` · ${b.size - b.used} waste` : ""}</small></div>`;
      })
      .join("")}</div>`;
  }

  async function runMemory() {
    const body = payloadFrom("mem", "mem");
    body.model = $("#mem-model").value;
    body.algorithm = $("#mem-algorithm").value;

    const data = await api("/api/memory", body);
    const results = data.results;
    const single = results.length === 1;
    const out = [];

    if (!single) {
      const maxUtil = Math.max(...results.map((r) => r.utilisation));
      const best = results.filter((r) => r.utilisation === maxUtil).map((r) => r.label).join(" / ");
      const maxInt = Math.max(...results.map((r) => r.internal_frag), 0.001);
      const maxExt = Math.max(...results.map((r) => r.external_frag), 0.001);
      out.push(card(
        "Comparison",
        `<div class="bars">${results.map((r) => `<div class="bar-row">
            <div class="bar-name">${esc(r.label)}</div>
            <div class="bar-track">
              ${barLine(r.internal_frag, maxInt, "wait")}
              ${barLine(r.external_frag, maxExt, "turn")}
            </div>
          </div>`).join("")}
        </div>
        <div class="bar-key">
          <span class="legend-item"><span class="swatch" style="background:#38bdf8"></span>internal fragmentation</span>
          <span class="legend-item"><span class="swatch" style="background:#a78bfa"></span>external fragmentation</span>
        </div>
        <p class="muted small" style="margin-top:12px">
          Highest utilisation: <span class="pick">${esc(best)}</span> at ${fmt(maxUtil)}%
        </p>` +
        table(
          ["Algorithm", "Placed", "Rejected", "Internal frag", "External frag", "Utilisation %"],
          results.map((r) => [
            esc(r.label),
            r.allocated_count,
            r.rejected.length,
            r.internal_frag,
            r.external_frag,
            fmt(r.utilisation),
          ]),
          1,
        ),
        `${data.model} model · ${data.partitions.length} partitions`,
      ));
    }

    results.forEach((res, index) => {
      const stats = statRow([
        ["Utilisation", fmt(res.utilisation), "%", "good"],
        ["Placed", `${res.allocated_count}/${res.allocations.length}`, "processes"],
        ["Internal frag", String(res.internal_frag), "units"],
        ["External frag", String(res.external_frag), "units"],
        ["Free memory", String(res.free_memory), "units"],
        ["Rejected", String(res.rejected.length), res.rejected.length ? "processes" : "", res.rejected.length ? "bad" : ""],
      ]);

      const allocTable = table(
        ["Process", "Requested", "Block", "Allocated", "Internal frag", "Status"],
        res.allocations.map((a) => [
          esc(a.pid),
          a.size,
          a.block_id === null ? "—" : `B${a.block_id}`,
          a.allocated_size,
          a.internal_frag,
          a.status === "ALLOCATED"
            ? `<span class="tag ok">allocated</span>`
            : `<span class="tag no">rejected</span>`,
        ]),
        1,
      );

      const rejectedNote = res.rejected.length
        ? `<p class="muted small" style="margin-top:10px">Rejected: ${res.rejected.map(esc).join(", ")}
           ${res.stranded_blocks ? `· ${res.stranded_blocks} free block(s) stranded` : ""}</p>`
        : "";

      const inner = `${stats}<div class="divider"></div>${memoryMap(res.blocks)}${allocTable}${rejectedNote}`;

      if (single) {
        out.push(card(`${res.label} result`, inner, `${res.model} model`));
      } else {
        out.push(`<details class="card" ${index === 0 ? "open" : ""}>
          <summary class="res-card-head" style="cursor:pointer;list-style:none">
            <h3>${esc(res.label)}</h3>
            <span class="hint">utilisation ${fmt(res.utilisation)}%</span>
          </summary>
          <div class="divider"></div>${inner}
        </details>`);
      }
    });

    $("#mem-results").innerHTML = out.join("");
  }

  /* ------------------------------------------------------------- Deadlock */
  function matrixTable(state) {
    const rows = state.pids.map((pid, i) => [
      esc(pid),
      state.allocation[i].join(" "),
      state.maximum[i].join(" "),
      state.need[i].join(" "),
    ]);
    return table(["Process", "Allocation", "Max", "Need"], rows) +
      `<p class="muted small" style="margin-top:10px">
        Available: <code>${state.available.join(" ")}</code>
        &nbsp;·&nbsp; Total resources: <code>${state.total.join(" ")}</code>
      </p>`;
  }

  function stepsTable(steps, kind) {
    if (kind === "safety") {
      return table(
        ["#", "Process", "Work before", "Need", "Work after"],
        steps.map((s, i) => [
          i + 1, esc(s.pid), s.work_before.join(" "), s.need.join(" "), s.work_after.join(" "),
        ]),
        2,
      );
    }
    return table(
      ["#", "Process", "Work before", "Request", "Work after"],
      steps.map((s, i) => [
        i + 1, esc(s.pid), s.work_before.join(" "), s.request.join(" "), s.work_after.join(" "),
      ]),
      2,
    );
  }

  function sequenceHtml(list) {
    if (!list.length) return "";
    return `<div class="sequence">${list
      .map((pid) => `<span class="seq-node">${esc(pid)}</span>`)
      .join('<span class="seq-arrow">→</span>')}</div>`;
  }

  async function runDeadlock() {
    const body = payloadFrom("dl", "dl");
    body.action = state.deadlockAction;
    if (body.action === "request") {
      body.pid = $("#dl-pid").value;
      body.request = $("#dl-vector").value
        .split(/[\s,]+/)
        .filter(Boolean)
        .map(Number);
      if (body.request.some((v) => !Number.isFinite(v))) {
        throw new Error("the request vector must be integers, e.g. 1 0 2");
      }
    }

    const data = await api("/api/deadlock", body);
    const out = [card("System state", matrixTable(data.state), `${data.state.pids.length} processes · ${data.state.available.length} resource types`)];

    if (data.action === "safety") {
      const safety = data.safety;
      out.unshift(card(
        safety.safe ? "Verdict — safe state" : "Verdict — unsafe state",
        `<div class="verdict ${safety.safe ? "safe" : "unsafe"}">
          <span class="icon">${safety.safe ? "✓" : "!"}</span>
          <div><strong>${esc(safety.summary)}</strong><br />
          <span class="muted small">${safety.safe
            ? "Every process can finish, so the current state cannot deadlock."
            : "No ordering lets every process finish; a deadlock is possible."}</span></div>
        </div>
        ${safety.safe ? sequenceHtml(safety.sequence) : ""}
        ${safety.steps.length ? `<div class="divider"></div>${stepsTable(safety.steps, "safety")}` : ""}
        ${safety.stuck.length ? `<p class="muted small" style="margin-top:10px">Stuck processes: ${safety.stuck.map(esc).join(", ")}</p>` : ""}`,
        "Banker's safety algorithm",
      ));
    } else if (data.action === "request") {
      const req = data.request;
      out.unshift(card(
        `Request — ${req.pid} asks for (${req.request.join(", ")})`,
        `<div class="verdict ${req.granted ? "safe" : "unsafe"}">
          <span class="icon">${req.granted ? "✓" : "×"}</span>
          <div><strong>${req.granted ? "GRANTED" : "REFUSED"}</strong><br />
          <span class="muted small">${esc(req.reason)}</span></div>
        </div>
        ${req.safety ? `<div class="divider"></div>
          <p class="muted small">Safety check of the resulting state: <strong>${esc(req.safety.summary)}</strong></p>
          ${req.safety.safe ? sequenceHtml(req.safety.sequence) : ""}
          ${req.safety.steps.length ? stepsTable(req.safety.steps, "safety") : ""}` : ""}`,
        "Resource-request algorithm",
      ));
      if (req.state) {
        out.push(card("State after the grant", matrixTable(req.state), "granted request applied"));
      }
    } else {
      const det = data.detection;
      out.unshift(card(
        det.deadlocked.length ? "Verdict — deadlock detected" : "Verdict — no deadlock",
        `<div class="verdict ${det.deadlocked.length ? "unsafe" : "safe"}">
          <span class="icon">${det.deadlocked.length ? "!" : "✓"}</span>
          <div><strong>${esc(det.summary)}</strong><br />
          <span class="muted small">Request matrix source: ${esc(det.request_source)}</span></div>
        </div>
        ${det.order.length ? `<p class="muted small" style="margin-top:12px">Processes that can finish:</p>${sequenceHtml(det.order)}` : ""}
        ${det.deadlocked.length ? `<p class="muted small" style="margin-top:10px">Deadlocked: ${det.deadlocked.map(esc).join(", ")}</p>` : ""}
        ${det.steps.length ? `<div class="divider"></div>${stepsTable(det.steps, "detect")}` : ""}`,
        "Deadlock detection algorithm",
      ));
    }

    $("#dl-results").innerHTML = out.join("");
  }

  /* ----------------------------------------------------------------- Disk */
  function diskChart(res) {
    const sequence = res.sequence;
    const size = Math.max(res.disk_size - 1, 1);
    const left = 58;
    const right = 34;
    const top = 26;
    const step = 30;
    const width = 900;
    const height = top * 2 + Math.max(sequence.length - 1, 1) * step;
    const inner = width - left - right;
    const x = (cylinder) => left + (cylinder / size) * inner;
    const y = (i) => top + i * step;

    const points = sequence.map((c, i) => `${x(c)},${y(i)}`).join(" ");
    const stroke = res.name === "CSCAN" ? "#a78bfa" : "#38bdf8";

    const nodes = sequence.map((c, i) => {
      const isHead = i === 0;
      const movement = i > 0 ? res.movements[i - 1] : null;
      const boundary = movement && movement.is_boundary;
      const fill = isHead ? "#34d399" : boundary ? "#fbbf24" : "#0b1220";
      const strokeNode = isHead ? "#34d399" : boundary ? "#fbbf24" : stroke;
      return `<circle cx="${x(c)}" cy="${y(i)}" r="5" fill="${fill}" stroke="${strokeNode}" stroke-width="2" />
        <text x="${x(c) + 10}" y="${y(i) + 4}" font-size="10.5" font-family="monospace"
          fill="${isHead ? "#a8f0cd" : "#c9dcf5"}">${isHead ? `head ${c}` : `${c}${boundary ? " (boundary)" : ""}`}</text>
        ${movement ? `<text x="${x(c) - 6}" y="${y(i) - 10}" text-anchor="end" font-size="9.5"
          font-family="monospace" fill="#7d94b6">+${movement.distance}</text>` : ""}`;
    }).join("");

    const axis = `<line x1="${left}" y1="${height - 12}" x2="${left + inner}" y2="${height - 12}"
        stroke="#22314b" stroke-width="1" />
      <text x="${left}" y="${height - 1}" font-size="9.5" fill="#7d94b6" font-family="monospace">0</text>
      <text x="${left + inner}" y="${height - 1}" font-size="9.5" fill="#7d94b6"
        text-anchor="end" font-family="monospace">${size}</text>`;

    return `<div class="disk-chart">
      <svg viewBox="0 0 ${width} ${height}" role="img"
        aria-label="Seek path for ${esc(res.label)}">
        <polyline points="${points}" fill="none" stroke="${stroke}" stroke-width="2"
          stroke-linejoin="round" opacity="0.85" />
        ${nodes}${axis}
      </svg>
    </div>`;
  }

  async function runDisk() {
    const body = payloadFrom("disk", "disk");
    body.algorithm = $("#disk-algorithm").value;
    body.direction = $("#disk-direction").value;

    const data = await api("/api/disk", body);
    const results = data.results;
    const single = results.length === 1;
    const out = [];

    if (!single) {
      const min = Math.min(...results.map((r) => r.total_movement));
      const maxTotal = Math.max(...results.map((r) => r.total_movement), 0.001);
      out.push(card(
        "Comparison",
        `<div class="bars">${results.map((r) => `<div class="bar-row">
            <div class="bar-name">${esc(r.label)}</div>
            <div class="bar-track">${barLine(r.total_movement, maxTotal, "wait")}</div>
          </div>`).join("")}
        </div>
        <p class="muted small" style="margin-top:12px">
          Shortest total movement: <span class="pick">${esc(results.find((r) => r.total_movement === min).label)}</span>
          (${min} cylinders)
        </p>` +
        table(
          ["Algorithm", "Total movement", "Average / request", "Boundary travel", "C-SCAN jump"],
          results.map((r) => [
            esc(r.label),
            r.total_movement,
            fmt(r.average_movement),
            r.movements.filter((m) => m.is_boundary).length,
            r.return_jump ? `${r.return_jump} (not counted)` : "—",
          ]),
          1,
        ),
        `head ${data.head} · ${data.disk_size} cylinders · direction ${data.direction}`,
      ));
    }

    results.forEach((res, index) => {
      const stats = statRow([
        ["Total movement", String(res.total_movement), "cyl", "accent"],
        ["Average / request", fmt(res.average_movement), "cyl"],
        ["Requests", String(res.request_count), ""],
        ["Seek steps", String(res.movements.length), ""],
        ["C-SCAN jump", res.return_jump ? String(res.return_jump) : "—", res.return_jump ? "recorded" : ""],
        ["Charged path", String(res.charged_movement), "cyl"],
      ]);

      const movementTable = table(
        ["#", "From", "To", "Distance", "Note"],
        res.movements.map((m, i) => [
          i + 1, m.start, m.end, m.distance,
          m.is_boundary ? `<span class="tag warn">boundary</span>` : "request",
        ]),
        1,
      );

      const inner = `${stats}<div class="divider"></div>${diskChart(res)}${movementTable}
        <p class="muted small" style="margin-top:10px">
          Served order: <code>${res.order.join(" → ")}</code>
        </p>`;

      const hint = res.direction ? `direction ${res.direction}` : "direction-independent";
      if (single) {
        out.push(card(`${res.label} result`, inner, hint));
      } else {
        out.push(`<details class="card" ${index === 0 ? "open" : ""}>
          <summary class="res-card-head" style="cursor:pointer;list-style:none">
            <h3>${esc(res.label)}</h3>
            <span class="hint">${esc(hint)} · ${res.total_movement} cylinders</span>
          </summary>
          <div class="divider"></div>${inner}
        </details>`);
      }
    });

    $("#disk-results").innerHTML = out.join("");
  }

  /* ------------------------------------------------------------ navigation */
  const VIEWS = {
    overview: ["Overview", "Four OS subsystems, one simulator — CPU, memory, deadlock and disk."],
    cpu: ["CPU Scheduling", "FCFS, SJF, SRTF, Priority and Round Robin on the same process set."],
    memory: ["Memory Management", "First, Best and Worst Fit across fixed and dynamic partitions."],
    deadlock: ["Deadlock Management", "Banker's safety, resource requests and deadlock detection."],
    disk: ["Disk Scheduling", "FCFS, SSTF, SCAN and C-SCAN head movement."],
  };

  function showView(name) {
    if (!VIEWS[name]) return;
    $$(".view").forEach((v) => v.classList.toggle("is-active", v.id === `view-${name}`));
    $$(".nav-item").forEach((b) => b.classList.toggle("is-active", b.dataset.view === name));
    $("#page-title").textContent = VIEWS[name][0];
    $("#page-sub").textContent = VIEWS[name][1];
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  /* ------------------------------------------------------------------ init */
  function fillSelect(select, items, labeler) {
    select.innerHTML = items
      .map((item) => `<option value="${esc(item.name || item)}">${esc(labeler(item))}</option>`)
      .join("");
  }

  function syncEditor(prefix, kind) {
    const list = state.meta.datasets[kind];
    const select = $(`#${prefix}-dataset`);
    const textarea = $(`#${prefix}-text`);
    const pick = () => {
      const found = list.find((d) => d.name === select.value);
      if (found) textarea.value = found.text;
      $(`#${prefix}-use-text`).checked = false;
    };
    select.onchange = pick;
    pick();
    textarea.oninput = () => { $(`#${prefix}-use-text`).checked = true; };
  }

  async function init() {
    const pill = $("#server-pill");
    try {
      state.meta = await api("/api/meta");
      pill.className = "pill ok";
      pill.innerHTML = `<span class="dot"></span> backend connected`;
    } catch (error) {
      pill.className = "pill err";
      pill.innerHTML = `<span class="dot"></span> backend unreachable`;
      console.error(error);
      return;
    }

    fillSelect($("#cpu-dataset"), state.meta.datasets.cpu, (d) => d.name);
    fillSelect($("#mem-dataset"), state.meta.datasets.memory, (d) => d.name);
    fillSelect($("#dl-dataset"), state.meta.datasets.deadlock, (d) => d.name);
    fillSelect($("#disk-dataset"), state.meta.datasets.disk, (d) => d.name);

    syncEditor("cpu", "cpu");
    syncEditor("mem", "memory");
    syncEditor("dl", "deadlock");
    syncEditor("disk", "disk");

    $("#cpu-quantum").value = state.meta.cpu.default_quantum;

    // Deadlock: pick the process list from the selected dataset text.
    const fillPids = () => {
      const pids = [];
      $("#dl-text").value.split("\n").forEach((line) => {
        const match = line.trim().match(/^(P[\w-]+)\s/);
        if (match && !/^(processes|resources|available|allocation|max)$/i.test(match[1])) {
          if (!pids.includes(match[1])) pids.push(match[1]);
        }
      });
      const select = $("#dl-pid");
      if (pids.length) select.innerHTML = pids.map((p) => `<option>${esc(p)}</option>`).join("");
    };
    $("#dl-dataset").addEventListener("change", fillPids);
    $("#dl-text").addEventListener("input", fillPids);
    fillPids();

    $("#dl-action").addEventListener("click", (event) => {
      const button = event.target.closest(".seg");
      if (!button) return;
      state.deadlockAction = button.dataset.action;
      $$(".seg", $("#dl-action")).forEach((b) => b.classList.toggle("is-active", b === button));
      $("#dl-request-fields").classList.toggle("hidden", state.deadlockAction !== "request");
    });

    $$(".nav-item").forEach((button) =>
      button.addEventListener("click", () => showView(button.dataset.view)));
    $$("[data-goto]").forEach((node) =>
      node.addEventListener("click", () => showView(node.dataset.goto)));

    $("#cpu-run").addEventListener("click", (e) =>
      runWith(e.currentTarget, $("#cpu-status"), runCpu));
    $("#mem-run").addEventListener("click", (e) =>
      runWith(e.currentTarget, $("#mem-status"), runMemory));
    $("#dl-run").addEventListener("click", (e) =>
      runWith(e.currentTarget, $("#dl-status"), runDeadlock));
    $("#disk-run").addEventListener("click", (e) =>
      runWith(e.currentTarget, $("#disk-status"), runDisk));

    const clock = () => {
      $("#foot-clock").textContent = new Date().toLocaleString();
    };
    clock();
    setInterval(clock, 30000);

    showView("overview");
  }

  document.addEventListener("DOMContentLoaded", init);
})();
