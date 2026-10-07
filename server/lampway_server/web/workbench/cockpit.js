// SPDX-FileCopyrightText: 2026 Lampway contributors
// SPDX-License-Identifier: GPL-3.0-or-later
// The cockpit page (facelift contract 10). The bearer arrives in the URL fragment (never sent to a server by the browser
// and never logged by one) and goes only into the Authorization header of this origin's own requests. Rows, the banner
// and what each row may offer come from /app/workbench/view: a pane Lampway did not create gets no input and no Stop.
"use strict";
const token = new URLSearchParams(location.hash.slice(1)).get("t") || "";
const H = { Authorization: "Bearer " + token, "Content-Type": "application/json" };
let selected = null;
let rows = [];

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;
  return e;
}

async function api(path, opts) {
  const r = await fetch(path, Object.assign({ headers: H }, opts || {}));
  const body = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(body.detail || ("HTTP " + r.status));
  return body;
}

function drawRows() {
  const nav = document.getElementById("sessions");
  nav.replaceChildren();
  for (const row of rows) {
    const line = el("div", "row" + (row.adopted ? "" : " unadopted") + (row.id === selected ? " selected" : ""));
    line.title = row.adopted ? (row.agent + ", " + row.folder) : "Not adopted: left running, never typed into";
    line.append(el("span", "spark " + row.spark), el("span", "", row.name), el("span", "", row.adopted ? "" : "not adopted"));
    if (row.adopted) line.onclick = () => { selected = row.id; drawRows(); drawHead(); poll(); };
    nav.append(line);
  }
}

function drawHead() {
  const head = document.getElementById("head");
  head.replaceChildren();
  const row = rows.find(r => r.id === selected);
  const form = document.getElementById("input");
  form.hidden = !(row && row.can_type);
  if (!row) return;
  head.append(el("strong", "", row.name), el("span", "", row.agent), el("span", "", row.folder));
  const sends = el("button", "", "Agent sends: " + (row.agent_sends ? "on" : "off"));
  sends.onclick = () => api("/app/workbench/sessions/" + row.id + "/agent-sends", { method: "POST", body: JSON.stringify({ on: !row.agent_sends }) }).then(refresh);
  head.append(sends);
  if (row.can_stop) {
    const stop = el("button", "stop", "Stop");
    stop.onclick = () => { if (confirm("Stop " + row.name + "? Its CLI is closed.")) api("/app/workbench/sessions/" + row.id + "/close", { method: "POST", body: JSON.stringify({ confirm: true }) }).then(refresh); };
    head.append(stop);
  }
}

async function poll() {
  if (!selected) return;
  try {
    const s = await api("/app/workbench/sessions/" + selected + "/screen");
    document.getElementById("screen").textContent = s.screen || "";
  } catch (e) { document.getElementById("screen").textContent = String(e.message || e); }
}

async function refresh() {
  try {
    const v = await api("/app/workbench/view");
    rows = v.rows || [];
    document.getElementById("server").textContent = v.server && v.server.running ? "herdr server: running" : "herdr server: not running";
    const b = document.getElementById("banner");
    b.hidden = !v.banner;
    if (v.banner) { b.textContent = v.banner.text; b.title = v.banner.tooltip; }
    drawRows(); drawHead();
  } catch (e) { document.getElementById("server").textContent = String(e.message || e); }
}

async function cards() {
  const list = document.getElementById("card-list");
  try {
    const out = await api("/app/cards");
    const items = (out.data || out).cards || (out.data || out).items || [];
    for (const card of items) {
      const li = el("li", "", card.title || card.id);
      li.onclick = async () => {
        const opened = await api("/app/cards/" + encodeURIComponent(card.id) + "/open");
        const frame = document.getElementById("card");
        frame.src = (opened.data || opened).url;   // the card on its own origin, sandboxed as mrmak 09 names it
        frame.hidden = false;
      };
      list.append(li);
    }
  } catch (e) { list.append(el("li", "", String(e.message || e))); }
}

document.getElementById("input").addEventListener("submit", ev => {
  ev.preventDefault();
  const box = document.getElementById("text");
  const refused = document.getElementById("refused");
  api("/app/workbench/sessions/" + selected + "/input", { method: "POST", body: JSON.stringify({ text: box.value, by: "user" }) })
    .then(() => { box.value = ""; refused.hidden = true; poll(); })
    .catch(e => { refused.textContent = String(e.message || e); refused.hidden = false; });
});
async function terminal() {
  // Contract 16's window is this cockpit's terminal; this page's pane stays the zero-install fallback.
  const box = document.getElementById("terminal");
  box.replaceChildren();
  try {
    const t = await api("/app/terminal");
    if (t.installed) {
      const open = el("button", "", t.window === "re-adopted" ? "The Lampway terminal is open" : "Open in the Lampway terminal");
      open.disabled = t.window === "re-adopted";
      open.onclick = () => api("/app/terminal/open", { method: "POST", body: JSON.stringify({}) }).then(terminal);
      box.append(open);
    } else {
      box.append(el("span", "", "The Lampway terminal is not installed: Get it in Blender's Sessions panel"));
    }
  } catch (e) { box.append(el("span", "", String(e.message || e))); }
}

refresh(); cards(); terminal();
setInterval(refresh, 5000);
setInterval(poll, 1000);
