const HAIR = [
  { value: 0, label: "None" },
  { value: 1, label: "Dreadlocks", sprite: "/assets/gostek/hair1.png" },
  { value: 2, label: "Punk", sprite: "/assets/gostek/hair2.png" },
  { value: 3, label: "Mr. T", sprite: "/assets/gostek/hair3.png" },
  { value: 4, label: "Normal", sprite: "/assets/gostek/hair4.png" },
];

const HEAD = [
  { value: 0, label: "None" },
  { value: 34, label: "Helmet", sprite: "/assets/gostek/helm.png" },
  { value: 124, label: "Hat", sprite: "/assets/gostek/kap.png" },
];

const CHAIN = [
  { value: 0, label: "None" },
  { value: 1, label: "Dog tags", sprite: "/assets/gostek/metal.png" },
  { value: 2, label: "Gold", sprite: "/assets/gostek/zloto.png" },
];

const SECONDARY = [
  { value: 0, label: "USSOCOM", icon: "/assets/guns/ussocom.png" },
  { value: 1, label: "Combat Knife", icon: "/assets/guns/knife.png" },
  { value: 2, label: "Chainsaw", icon: "/assets/guns/chainsaw.png" },
  { value: 3, label: "M72 LAW", icon: "/assets/guns/law.png" },
];

const TITLES = { play: "Play", demos: "Demos", shots: "Shots", local: "Local", soldier: "Soldier" };
const DEMO_TINY_BYTES = 500 * 1024;

const state = {
  view: "play",
  settings: {},
  servers: [],
  loading: false,
  search: "",
  filters: { empty: false, full: false, bots: false, private: false },
  join: null,
  joinPassword: "",
  maps: { selected: [], available: [] },
  mapQuery: "",
  demos: [],
  demoSearch: "",
  demoSelected: null,
  demoFilters: { tiny: true, lobby: true },
  shots: [],
  local: { server: false, client: false, log: "" },
  saveTimer: null,
  hydrating: false,
};

async function api(path, opts) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

function flagEmoji(iso) {
  if (!iso || iso.length !== 2) return "";
  const cc = iso.toUpperCase();
  return String.fromCodePoint(...[...cc].map((c) => 127397 + c.charCodeAt(0)));
}

function $(id) {
  return document.getElementById(id);
}

function parseNum(value) {
  const n = Number(String(value).trim().replace(",", "."));
  return Number.isFinite(n) ? n : 0;
}

function parseSoldatLink(text) {
  const raw = String(text || "").trim();
  const match = raw.match(/soldat:\/\/([^:/\s]+)(?::(\d+))?(?:\/(\S*))?/i);
  if (!match) return null;
  return {
    ip: match[1],
    port: match[2] || "23073",
    password: match[3] || "",
  };
}

function applySoldatLink(text) {
  const parsed = parseSoldatLink(text);
  if (!parsed) return null;
  $("direct-ip").value = parsed.ip;
  $("direct-port").value = parsed.port;
  $("direct-pass").value = parsed.password;
  return parsed;
}

function maybeSplitSoldatFields() {
  const blob = [$("direct-ip").value, $("direct-port").value, $("direct-pass").value].join(" ");
  if (!/soldat:\/\//i.test(blob) && !/soldat:\/\//i.test($("direct-ip").value)) return null;
  return applySoldatLink(blob) || applySoldatLink($("direct-ip").value);
}

function setView(name) {
  state.view = name;
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.view === name);
  });
  document.querySelectorAll(".view").forEach((el) => {
    el.classList.toggle("active", el.id === `view-${name}`);
  });
  $("page-title").textContent = TITLES[name];
  if (name === "play") {
    const n = state.servers.length;
    const players = state.servers.reduce((s, x) => s + (x.NumPlayers || 0), 0);
    $("page-meta").textContent = n ? `${n} servers · ${players} players` : "";
  } else if (name === "demos") {
    updateDemoMeta();
    loadDemos();
  } else if (name === "shots") {
    updateShotMeta();
    loadShots();
  } else if (name === "local") {
    $("page-meta").textContent = state.local.server ? "Server running" : "";
    fillPracticeMaps();
  } else {
    $("page-meta").textContent = "Changes save automatically";
  }
}

function setColor(part, hex) {
  const value = hex || "#8f8f8f";
  const input = $(`color-${part}`);
  const face = $(`face-${part}`);
  const code = $(`hex-${part}`);
  if (input) input.value = value;
  if (face) face.style.background = value;
  if (code) code.textContent = value.toUpperCase();
}

function applyHeader() {
  const s = state.settings;
  $("chip-name").textContent = s.cl_player_name || "—";
  $("chip-shirt").style.background = s.cl_player_shirt || "#8f8f8f";
  $("chip-pants").style.background = s.cl_player_pants || "#8f8f8f";
}

function renderToggles(containerId, options, current, key, useIcon) {
  const root = $(containerId);
  root.innerHTML = "";
  for (const opt of options) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "toggle" + (opt.value === current ? " on" : "");
    if (opt.sprite) {
      const img = document.createElement("img");
      img.src = opt.sprite;
      img.alt = "";
      btn.appendChild(img);
    } else if (useIcon && opt.icon) {
      const img = document.createElement("img");
      img.src = opt.icon;
      img.alt = "";
      btn.appendChild(img);
    }
    btn.appendChild(document.createTextNode(opt.label));
    btn.addEventListener("click", () => {
      state.settings[key] = opt.value;
      scheduleSave();
      renderSoldier();
    });
    root.appendChild(btn);
  }
}

function renderSoldier() {
  const s = state.settings;
  state.hydrating = true;
  $("player-name").value = s.cl_player_name || "";
  $("player-name").placeholder = s.cl_player_name || "Your nickname";
  setColor("skin", s.cl_player_skin || "#8f8f8f");
  setColor("shirt", s.cl_player_shirt || "#8f8f8f");
  setColor("pants", s.cl_player_pants || "#8f8f8f");
  setColor("hair", s.cl_player_hair || "#000000");
  setColor("jet", s.cl_player_jet || "#8f8f8f");
  $("sens").value = Number(s.cl_sensitivity ?? 0.37).toFixed(2);
  $("vol").value = String(s.snd_volume ?? 50);
  $("autorecord").checked = Number(s.cl_autorecord) === 1;
  renderToggles("hair-toggles", HAIR, s.cl_player_hairstyle, "cl_player_hairstyle");
  renderToggles("head-toggles", HEAD, s.cl_player_headstyle, "cl_player_headstyle");
  renderToggles("chain-toggles", CHAIN, s.cl_player_chainstyle, "cl_player_chainstyle");
  renderToggles("sec-toggles", SECONDARY, s.cl_player_secwep, "cl_player_secwep", true);
  applyHeader();
  setTimeout(() => {
    state.hydrating = false;
  }, 80);
}

function scheduleSave() {
  if (state.hydrating) return;
  const hint = $("save-hint");
  hint.textContent = "Saving…";
  hint.classList.remove("ok");
  clearTimeout(state.saveTimer);
  state.saveTimer = setTimeout(saveSettings, 350);
}

async function saveSettings() {
  try {
    state.settings = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(state.settings),
    });
    $("save-hint").textContent = "All changes saved";
    $("save-hint").classList.add("ok");
    applyHeader();
  } catch (err) {
    $("save-hint").textContent = `Could not save: ${err.message}`;
    $("save-hint").classList.remove("ok");
  }
}

function filteredServers() {
  return state.servers.filter((s) => {
    if (state.filters.empty && !(s.NumPlayers > 0)) return false;
    if (state.filters.full && s.NumPlayers >= s.MaxPlayers) return false;
    if (state.filters.bots && s.NumBots > 0) return false;
    if (state.filters.private && s.Private) return false;
    return true;
  });
}

function renderServers() {
  const rows = $("server-rows");
  const list = filteredServers();
  const n = state.servers.length;
  const players = state.servers.reduce((sum, x) => sum + (x.NumPlayers || 0), 0);
  if (state.view === "play") {
    $("page-meta").textContent = n ? `${n} servers · ${players} players` : "";
  }
  if (!list.length) {
    rows.innerHTML = `<tr><td class="empty" colspan="7">${
      state.loading ? "Loading servers…" : "No servers match."
    }</td></tr>`;
    return;
  }
  rows.innerHTML = "";
  for (const s of list) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td class="flag">${flagEmoji(s.Country)}</td>
      <td class="lock">${s.Private ? "🔒" : ""}</td>
      <td class="name"></td>
      <td></td>
      <td></td>
      <td></td>
      <td></td>`;
    tr.children[2].textContent = s.Name || "";
    tr.children[3].textContent = s.GameStyle || "";
    tr.children[4].textContent = `${s.NumPlayers ?? 0}/${s.MaxPlayers ?? 0}`;
    tr.children[5].textContent = s.CurrentMap || "";
    tr.children[6].textContent = `${s.IP}:${s.Port}`;
    tr.addEventListener("click", () => openJoin(s.IP, s.Port, "", s));
    rows.appendChild(tr);
  }
}

async function loadServers() {
  state.loading = true;
  renderServers();
  try {
    const data = await api("/api/servers");
    state.servers = data.Servers || data.servers || [];
  } catch (err) {
    state.servers = [];
    $("server-rows").innerHTML = `<tr><td class="empty" colspan="7">Lobby unavailable: ${err.message}</td></tr>`;
    state.loading = false;
    return;
  }
  state.loading = false;
  renderServers();
}

async function openJoin(ip, port, password, preview) {
  const link = parseSoldatLink(ip) || parseSoldatLink(`${ip}`);
  if (link) {
    ip = link.ip;
    port = link.port;
    password = link.password || password || "";
  }
  state.join = { ip, port, password: password || "", preview: preview || null, info: null, live: null };
  state.joinPassword = password || "";
  $("join-title").textContent = preview?.Name || `${ip}:${port}`;
  $("join-addr").textContent = `${ip}:${port}`;
  $("join-body").innerHTML = "<p class='empty'>Loading server info…</p>";
  $("join-overlay").classList.add("show");
  try {
    const data = await api(`/api/server?ip=${encodeURIComponent(ip)}&port=${encodeURIComponent(port)}`);
    state.join.info = data.info;
    state.join.live = data.live;
  } catch {
    /* still allow join */
  }
  renderJoin();
}

function renderJoin() {
  const j = state.join;
  if (!j) return;
  const info = j.info || j.preview || {};
  const live = j.live;
  $("join-title").textContent = info.Name || j.preview?.Name || `${j.ip}:${j.port}`;
  const needPass = !!(info.Private || j.preview?.Private);
  let html = `<dl class="kv">
    <dt>Players</dt><dd>${info.NumPlayers ?? live?.players_num ?? "?"} / ${info.MaxPlayers ?? "?"}</dd>
    <dt>Mode</dt><dd>${live?.game_mode || info.GameStyle || "—"}</dd>
    <dt>Map</dt><dd>${live?.map || info.CurrentMap || "—"}</dd>
    <dt>Time left</dt><dd>${live?.timeleft || "—"}</dd>
  </dl>`;
  if (live?.scores?.length >= 2 && live.game_mode === "Capture the Flag") {
    html += `<div class="scores">
      <div class="score alpha">Alpha ${live.scores[0]}</div>
      <div class="score bravo">Bravo ${live.scores[1]}</div>
    </div>`;
  }
  if (live?.players?.length) {
    html += `<table class="players"><thead><tr><th>Nick</th><th>Kills</th><th>Deaths</th><th>Ping</th></tr></thead><tbody>`;
    for (const p of live.players) {
      html += `<tr class="team-${p.team}"><td></td><td>${p.kills}</td><td>${p.deaths}</td><td>${p.ping}</td></tr>`;
    }
    html += `</tbody></table>`;
  } else if (!live) {
    html += `<p class="empty">Could not load live player list. You can still join.</p>`;
  }
  html += `<div class="field" style="margin-top:12px;max-width:240px">
    <label for="join-pass">Server password</label>
    <input id="join-pass" type="text" placeholder="${needPass ? "Required" : "If needed"}" value="">
  </div>`;
  $("join-body").innerHTML = html;
  const pass = $("join-pass");
  pass.value = state.joinPassword;
  pass.addEventListener("input", () => {
    state.joinPassword = pass.value;
  });
  const table = $("join-body").querySelector(".players tbody");
  if (table && live?.players) {
    [...table.rows].forEach((row, i) => {
      row.cells[0].textContent = live.players[i].name;
    });
  }
}

function closeJoin() {
  $("join-overlay").classList.remove("show");
  state.join = null;
}

async function doJoin(ip, port, password) {
  const link = parseSoldatLink(ip);
  if (link) {
    ip = link.ip;
    port = link.port;
    password = link.password || password || "";
  }
  await api("/api/join", {
    method: "POST",
    body: JSON.stringify({ ip, port, password }),
  });
  closeJoin();
  $("running-banner").classList.add("show");
}

function renderMaps() {
  const q = state.mapQuery.trim().toLowerCase();
  const selected = new Set(state.maps.selected);
  const names = state.maps.available.filter((n) => !q || n.toLowerCase().includes(q));
  const root = $("map-list");
  root.innerHTML = "";
  if (!names.length) {
    root.textContent = "No maps found.";
    return;
  }
  for (const name of names) {
    const row = document.createElement("label");
    row.className = "map-item";
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = selected.has(name);
    box.addEventListener("change", async () => {
      const set = new Set(state.maps.selected);
      if (box.checked) set.add(name);
      else set.delete(name);
      state.maps.selected = state.maps.available.filter((n) => set.has(n));
      await api("/api/maps", {
        method: "PUT",
        body: JSON.stringify({ selected: state.maps.selected }),
      });
    });
    row.appendChild(box);
    row.appendChild(document.createTextNode(name));
    root.appendChild(row);
  }
}

async function refreshLocal() {
  try {
    const st = await api("/api/local/status");
    state.local = st;
    $("server-log").textContent = st.log || (st.server ? "Server running…" : "Server is stopped.");
    $("running-banner").classList.toggle("show", !!st.client);
    if (state.view === "local") {
      $("page-meta").textContent = st.server ? "Server running" : "";
    }
  } catch {
    /* ignore */
  }
}

function bindSoldierInputs() {
  $("player-name").addEventListener("input", (e) => {
    state.settings.cl_player_name = e.target.value.slice(0, 24);
    applyHeader();
    scheduleSave();
  });
  const colorMap = {
    "color-skin": "cl_player_skin",
    "color-shirt": "cl_player_shirt",
    "color-pants": "cl_player_pants",
    "color-hair": "cl_player_hair",
    "color-jet": "cl_player_jet",
  };
  for (const [id, key] of Object.entries(colorMap)) {
    $(id).addEventListener("input", (e) => {
      state.settings[key] = e.target.value;
      setColor(id.replace("color-", ""), e.target.value);
      applyHeader();
      scheduleSave();
    });
  }
  $("autorecord").addEventListener("change", () => {
    state.settings.cl_autorecord = $("autorecord").checked ? 1 : 0;
    scheduleSave();
  });
  document.querySelectorAll("[data-step='sens'], [data-step='vol']").forEach((btn) => {
    btn.addEventListener("click", () => {
      const kind = btn.dataset.step;
      const dir = Number(btn.dataset.dir);
      if (kind === "sens") {
        const next = Math.min(1, Math.max(0, +(parseNum($("sens").value) + dir * 0.05).toFixed(2)));
        $("sens").value = next.toFixed(2);
        state.settings.cl_sensitivity = next;
      } else {
        const next = Math.min(100, Math.max(0, Math.round(parseNum($("vol").value) + dir)));
        $("vol").value = String(next);
        state.settings.snd_volume = next;
      }
      scheduleSave();
    });
  });
  $("sens").addEventListener("change", () => {
    let v = parseNum($("sens").value);
    v = Math.min(1, Math.max(0, +v.toFixed(2)));
    $("sens").value = v.toFixed(2);
    state.settings.cl_sensitivity = v;
    scheduleSave();
  });
  $("vol").addEventListener("change", () => {
    let v = parseNum($("vol").value);
    v = Math.min(100, Math.max(0, Math.round(v)));
    $("vol").value = String(v);
    state.settings.snd_volume = v;
    scheduleSave();
  });
}

function prettySize(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function parseDemoName(stem) {
  const match = stem.match(/^(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})_(.+)$/);
  if (!match) return { map: "—", recorded: null };
  const [, date, time, map] = match;
  const iso = `${date}T${time.replace(/-/g, ":")}`;
  return { map, recorded: iso };
}

function formatWhen(demo) {
  const parsed = parseDemoName(demo.name);
  const date = parsed.recorded ? new Date(parsed.recorded) : new Date(demo.mtime * 1000);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString();
}

function isLobbyDemo(demo) {
  return String(demo.name || "").toLowerCase() === "lobby";
}

function filteredDemos() {
  const q = state.demoSearch.trim().toLowerCase();
  return state.demos.filter((d) => {
    if (state.demoFilters.tiny && d.size < DEMO_TINY_BYTES) return false;
    if (state.demoFilters.lobby && isLobbyDemo(d)) return false;
    if (!q) return true;
    const parsed = parseDemoName(d.name);
    return `${d.name} ${d.file} ${parsed.map}`.toLowerCase().includes(q);
  });
}

function updateDemoMeta() {
  if (state.view !== "demos") return;
  const shown = filteredDemos().length;
  const total = state.demos.length;
  if (!total) {
    $("page-meta").textContent = "No demos";
    return;
  }
  $("page-meta").textContent =
    shown === total
      ? `${total} recording${total === 1 ? "" : "s"}`
      : `${shown} shown · ${total} total`;
}

function renderDemos() {
  const rows = $("demo-rows");
  const list = filteredDemos();
  updateDemoMeta();
  if (!list.length) {
    rows.innerHTML = `<tr><td class="empty" colspan="4">${
      state.demos.length ? "No demos match." : "No .sdm files in demos/"
    }</td></tr>`;
    return;
  }
  rows.innerHTML = "";
  for (const demo of list) {
    const parsed = parseDemoName(demo.name);
    const tr = document.createElement("tr");
    if (state.demoSelected === demo.file) tr.classList.add("selected");
    tr.innerHTML = `<td class="name"></td><td></td><td></td><td></td>`;
    tr.children[0].textContent = demo.name;
    tr.children[1].textContent = parsed.map;
    tr.children[2].textContent = formatWhen(demo);
    tr.children[3].textContent = prettySize(demo.size);
    tr.addEventListener("click", () => {
      state.demoSelected = demo.file;
      renderDemos();
    });
    tr.addEventListener("dblclick", () => playDemo(demo));
    rows.appendChild(tr);
  }
}

async function loadDemos() {
  try {
    const data = await api("/api/demos");
    state.demos = data.demos || [];
  } catch (err) {
    state.demos = [];
    $("demo-rows").innerHTML = `<tr><td class="empty" colspan="4">Could not list demos: ${err.message}</td></tr>`;
    return;
  }
  renderDemos();
}

async function playDemo(demo) {
  await api("/api/demo/play", {
    method: "POST",
    body: JSON.stringify({ name: demo.file }),
  });
  $("running-banner").classList.add("show");
}

function updateShotMeta() {
  if (state.view !== "shots") return;
  const n = state.shots.length;
  $("page-meta").textContent = n ? `${n} screenshot${n === 1 ? "" : "s"}` : "No screenshots";
}

function renderShots() {
  const grid = $("shots-grid");
  updateShotMeta();
  if (!state.shots.length) {
    grid.innerHTML = `<div class="empty">No screenshots in screens/</div>`;
    return;
  }
  grid.innerHTML = "";
  for (const shot of state.shots) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "shot-tile";
    const img = document.createElement("img");
    img.src = `/assets/screens/${encodeURIComponent(shot.file)}`;
    img.alt = shot.file;
    const cap = document.createElement("span");
    cap.textContent = shot.file;
    btn.appendChild(img);
    btn.appendChild(cap);
    btn.addEventListener("click", () => openShot(shot));
    grid.appendChild(btn);
  }
}

async function loadShots() {
  try {
    const data = await api("/api/screens");
    state.shots = data.screens || [];
  } catch (err) {
    state.shots = [];
    $("shots-grid").innerHTML = `<div class="empty">Could not list screenshots: ${err.message}</div>`;
    return;
  }
  renderShots();
}

function openShot(shot) {
  $("shot-full").src = `/assets/screens/${encodeURIComponent(shot.file)}`;
  $("shot-full").alt = shot.file;
  $("shot-caption").textContent = shot.file;
  $("shot-overlay").classList.add("show");
}

function closeShot() {
  $("shot-overlay").classList.remove("show");
  $("shot-full").src = "";
}

function fillPracticeMaps() {
  const sel = $("practice-map");
  if (!sel) return;
  const names = (state.maps.available || []).filter(
    (n) => String(n).toLowerCase() !== "lobby"
  );
  const previous = sel.value;
  sel.innerHTML = "";
  if (!names.length) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "No maps found";
    sel.appendChild(opt);
    return;
  }
  for (const name of names) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    sel.appendChild(opt);
  }
  const ctf = names.filter((n) => n.toLowerCase().startsWith("ctf_"));
  const selected = (state.maps.selected || []).filter((n) => names.includes(n));
  const preferred =
    (names.includes(previous) && previous) ||
    selected.find((n) => n.toLowerCase().startsWith("ctf_")) ||
    ctf[0] ||
    selected[0] ||
    names[0];
  sel.value = preferred;
}

function clampBots(id, delta) {
  const el = $(id);
  const next = Math.min(8, Math.max(0, Math.round(parseNum(el.value) + (delta || 0))));
  el.value = String(next);
  return next;
}

function bindChrome() {
  document.querySelectorAll(".nav-btn").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  document.querySelector(".sidebar .nick-chip")?.addEventListener("click", () => setView("soldier"));
  document.querySelectorAll(".chip[data-filter]").forEach((chip) => {
    chip.addEventListener("click", () => {
      const key = chip.dataset.filter;
      state.filters[key] = !state.filters[key];
      chip.classList.toggle("on", state.filters[key]);
      renderServers();
    });
  });
  $("refresh").addEventListener("click", loadServers);
  $("direct-join").addEventListener("click", () => {
    const link = maybeSplitSoldatFields();
    if (link) {
      openJoin(link.ip, link.port, link.password);
      return;
    }
    openJoin(
      $("direct-ip").value.trim(),
      $("direct-port").value.trim(),
      $("direct-pass").value
    );
  });
  ["direct-ip", "direct-port", "direct-pass"].forEach((id) => {
    $(id).addEventListener("paste", (e) => {
      const clip = ((e.clipboardData || window.clipboardData).getData("text") || "").trim();
      if (parseSoldatLink(clip)) {
        e.preventDefault();
        const link = applySoldatLink(clip);
        openJoin(link.ip, link.port, link.password);
        return;
      }
      setTimeout(() => {
        const link = maybeSplitSoldatFields();
        if (link) openJoin(link.ip, link.port, link.password);
      }, 0);
    });
    $(id).addEventListener("keydown", (e) => {
      if (e.key !== "Enter") return;
      e.preventDefault();
      $("direct-join").click();
    });
  });
  $("direct-ip").addEventListener("input", () => {
    if (/soldat:\/\//i.test($("direct-ip").value)) maybeSplitSoldatFields();
  });
  document.addEventListener("keydown", (e) => {
    if (!(e.ctrlKey || e.metaKey) || (e.key !== "v" && e.key !== "V")) return;
    if (["INPUT", "TEXTAREA"].includes((document.activeElement || {}).tagName)) return;
    navigator.clipboard.readText().then((text) => {
      const link = parseSoldatLink(text);
      if (!link) return;
      applySoldatLink(text);
      openJoin(link.ip, link.port, link.password);
    }).catch(() => {});
  });
  $("join-close").addEventListener("click", closeJoin);
  $("join-overlay").addEventListener("click", (e) => {
    if (e.target === $("join-overlay")) closeJoin();
  });
  $("shot-close").addEventListener("click", closeShot);
  $("shot-overlay").addEventListener("click", (e) => {
    if (e.target === $("shot-overlay")) closeShot();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if ($("shot-overlay").classList.contains("show")) {
      closeShot();
      return;
    }
    closeJoin();
  });
  $("join-go").addEventListener("click", () => {
    if (!state.join) return;
    doJoin(state.join.ip, state.join.port, state.joinPassword);
  });
  $("kill-client").addEventListener("click", async () => {
    await api("/api/client/stop", { method: "POST", body: "{}" });
    $("running-banner").classList.remove("show");
  });
  $("local-start").addEventListener("click", async () => {
    try {
      await api("/api/local/start", { method: "POST", body: "{}" });
      $("running-banner").classList.add("show");
    } catch (err) {
      $("server-log").textContent = `Could not start local: ${err.message}`;
    }
    refreshLocal();
  });
  $("local-stop").addEventListener("click", async () => {
    await api("/api/local/stop", { method: "POST", body: "{}" });
    refreshLocal();
  });
  $("local-join").addEventListener("click", () => doJoin("127.0.0.1", "23040", ""));
  $("map-search").addEventListener("input", (e) => {
    state.mapQuery = e.target.value;
    renderMaps();
  });
  $("demo-search").addEventListener("input", (e) => {
    state.demoSearch = e.target.value;
    renderDemos();
  });
  $("demo-refresh").addEventListener("click", loadDemos);
  $("demo-hide-tiny").addEventListener("click", () => {
    state.demoFilters.tiny = !state.demoFilters.tiny;
    $("demo-hide-tiny").classList.toggle("on", state.demoFilters.tiny);
    renderDemos();
  });
  $("demo-hide-lobby").addEventListener("click", () => {
    state.demoFilters.lobby = !state.demoFilters.lobby;
    $("demo-hide-lobby").classList.toggle("on", state.demoFilters.lobby);
    renderDemos();
  });
  document.querySelectorAll("[data-step='bots-alpha'], [data-step='bots-bravo']").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.step === "bots-alpha" ? "practice-bots-alpha" : "practice-bots-bravo";
      clampBots(id, Number(btn.dataset.dir));
    });
  });
  ["practice-bots-alpha", "practice-bots-bravo"].forEach((id) => {
    $(id).addEventListener("change", () => clampBots(id));
  });
  $("practice-start").addEventListener("click", async () => {
    const bots_alpha = clampBots("practice-bots-alpha");
    const bots_bravo = clampBots("practice-bots-bravo");
    const difficulty = parseNum($("practice-diff").value) || 100;
    const map = $("practice-map").value;
    try {
      await api("/api/local/start", {
        method: "POST",
        body: JSON.stringify({ practice: { map, bots_alpha, bots_bravo, difficulty } }),
      });
      $("running-banner").classList.add("show");
    } catch (err) {
      $("server-log").textContent = `Could not start practice: ${err.message}`;
    }
    refreshLocal();
  });
}

async function boot() {
  bindChrome();
  bindSoldierInputs();
  try {
    state.settings = await api("/api/settings");
  } catch {
    state.settings = {};
  }
  renderSoldier();
  setView("play");
  loadServers();
  try {
    state.maps = await api("/api/maps");
    renderMaps();
    fillPracticeMaps();
  } catch {
    /* ignore */
  }
  refreshLocal();
  loadDemos();
  loadShots();
  setInterval(refreshLocal, 2000);
}

boot();
