/* ArtifactScan AI — single-page workspace.
 * Every number and status shown here comes from the backend API;
 * nothing is simulated in the browser. */
"use strict";

const $ = id => document.getElementById(id);
const state = { artifacts: [], readiness: null, summary: null, settings: null, route: "overview", detailId: null, viewers: {}, pending: [] };
const esc = v => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
const fmtBytes = b => b < 1024 ? `${b} B` : b < 1048576 ? `${(b / 1024).toFixed(1)} KB` : b < 1073741824 ? `${(b / 1048576).toFixed(1)} MB` : `${(b / 1073741824).toFixed(2)} GB`;
const fmtDate = s => { if (!s) return "—"; const d = new Date(s); return isNaN(d) ? s : d.toLocaleString(undefined, { year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }); };
const fmtNum = n => (n ?? 0).toLocaleString();
const PALETTE = ["#397cf6", "#d0904a", "#21a77a", "#9860ec", "#f16e72", "#2bb3c0", "#b9a04a", "#71809a"];

async function api(path, options = {}) {
  const res = await fetch(path, options);
  const type = res.headers.get("content-type") || "";
  const data = type.includes("application/json") ? await res.json() : await res.text();
  if (!res.ok) {
    let detail = data && typeof data === "object" ? data.detail : data;
    if (Array.isArray(detail)) detail = detail.map(d => `${(d.loc || []).slice(-1)[0]}: ${d.msg}`).join("; ");
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

function toast(text, kind = "") {
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = text;
  $("toasts").append(el);
  setTimeout(() => el.classList.add("show"), 10);
  setTimeout(() => { el.classList.remove("show"); setTimeout(() => el.remove(), 300); }, 4200);
}

function message(id, text, kind = "") { const el = $(id); if (el) { el.textContent = text; el.className = `job-message ${kind}`.trim(); } }

function viewer(key, hostId, opts) {
  if (!state.viewers[key]) state.viewers[key] = new PointCloudViewer($(hostId), opts);
  return state.viewers[key];
}

/* ---------------------------------------------------------------- routing */
const ROUTES = ["overview", "collection", "artifact", "capture", "reconstruction", "classification", "analytics", "reports", "settings"];

function parseRoute() {
  const [, name = "overview", arg = ""] = (location.hash || "#/overview").split("/");
  return { name: ROUTES.includes(name) ? name : "overview", arg: decodeURIComponent(arg) };
}

async function render() {
  const { name, arg } = parseRoute();
  state.route = name;
  document.querySelectorAll(".view").forEach(v => { v.hidden = v.dataset.view !== name; });
  document.querySelectorAll(".nav-item").forEach(a => a.classList.toggle("active", a.dataset.route === (name === "artifact" ? "collection" : name)));
  $("sidebar").classList.remove("open");
  window.scrollTo({ top: 0 });
  try {
    if (name === "overview") renderOverview();
    if (name === "collection") renderCollection();
    if (name === "artifact") await renderDetail(arg);
    if (name === "capture") renderCapture(arg);
    if (name === "reconstruction") await renderReconstruction(arg);
    if (name === "classification") await renderClassification(arg);
    if (name === "analytics") renderAnalytics();
    if (name === "reports") renderReports();
    if (name === "settings") renderSettings();
  } catch (err) { toast(err.message, "error"); }
}

/* ---------------------------------------------------------------- data */
async function loadAll() {
  $("refreshButton").classList.add("spin");
  const results = await Promise.allSettled([
    api("/api/readiness"), api("/api/artifacts"), api("/api/reports/summary"), api("/api/settings"),
  ]);
  $("refreshButton").classList.remove("spin");
  const [ready, arts, summary, settings] = results;
  if (ready.status === "fulfilled") { state.readiness = ready.value; renderReadiness(); }
  else apiDown(ready.reason);
  if (arts.status === "fulfilled") state.artifacts = arts.value;
  if (summary.status === "fulfilled") state.summary = summary.value;
  if (settings.status === "fulfilled") state.settings = settings.value;
  fillArtifactSelects();
  $("lastUpdated").textContent = `Updated ${new Date().toLocaleTimeString()}`;
  render();
}

function apiDown(err) {
  $("apiStatus").textContent = "API unavailable"; $("apiDot").className = "status-dot warn";
  $("sideStatus").textContent = "Backend offline"; $("sideDot").className = "status-dot warn";
  $("readinessMessage").textContent = `Could not reach the backend: ${err?.message || err}`;
}

function renderReadiness() {
  const r = state.readiness;
  $("apiStatus").textContent = "API online"; $("apiDot").className = "online-dot";
  $("sideStatus").textContent = `Connected · v${r.version}`; $("sideDot").className = "online-dot";
  $("versionLabel").textContent = `v${r.version}`;
  const set = (p, label, good) => {
    $(`${p}Detail`).textContent = label; $(`${p}Detail`).className = good ? "ok" : "warn";
    $(`${p}StatusDot`).className = `status-dot ${good ? "" : "warn"}`;
  };
  set("api", "Online", true);
  set("db", r.database ? "SQLite connected" : "Not initialised", r.database);
  const engine = { colmap: "COLMAP (native)", docker: "COLMAP (Docker)", opencv: "Built-in OpenCV SfM" }[r.reconstruction_engine_selected];
  set("colmap", engine || "No engine available", !!engine);
  set("classifier", r.classifier ? "Model loaded on demand" : "Not trained yet", r.classifier);
  if (state.settings) $("maxUpload").textContent = state.settings.max_upload_mb;
}

function fillArtifactSelects() {
  const opts = `<option value="">Choose an artifact…</option>` + state.artifacts.map(a =>
    `<option value="${esc(a.id)}">${esc(a.title)} · ${a.image_count} photo${a.image_count === 1 ? "" : "s"}</option>`).join("");
  document.querySelectorAll(".artifact-select").forEach(sel => {
    const prev = sel.value; sel.innerHTML = opts;
    if (state.artifacts.some(a => a.id === prev)) sel.value = prev;
  });
  const cats = [...new Set(state.artifacts.map(a => a.category))].sort();
  $("categoryList").innerHTML = cats.map(c => `<option value="${esc(c)}">`).join("");
  const filter = $("categoryFilter"), prev = filter.value;
  filter.innerHTML = `<option value="">All categories</option>` + cats.map(c => `<option>${esc(c)}</option>`).join("");
  filter.value = cats.includes(prev) ? prev : "";
}

/* ---------------------------------------------------------------- shared renderers */
function artifactCard(a) {
  const img = a.thumbnail_url
    ? `<img loading="lazy" src="${esc(a.thumbnail_url)}" alt="${esc(a.title)}">`
    : `<div class="artifact-placeholder"><span>◇</span><small>No photos yet</small></div>`;
  const badge = a.latest_job_status ? `<span class="pill ${esc(a.latest_job_status)}">3D ${esc(a.latest_job_status)}</span>` : "";
  return `<a class="artifact-card" href="#/artifact/${esc(a.id)}">${img}${badge}
    <div class="artifact-info"><strong title="${esc(a.title)}">${esc(a.title)}</strong>
      <small>${esc(a.category)}${a.period ? " · " + esc(a.period) : ""}</small>
      <small class="artifact-id">${a.image_count} photo${a.image_count === 1 ? "" : "s"} · ${esc(a.review_status || "draft")}</small></div></a>`;
}

function emptyCollection() {
  return `<div class="empty-state">No artifacts yet.<br>Register your first artifact to start the digital collection.<br><button class="btn btn-gold btn-small" data-action="register" style="margin-top:10px">＋ Register artifact</button></div>`;
}

function donut(host, entries) {
  const total = entries.reduce((s, e) => s + e[1], 0);
  if (!total) { host.innerHTML = `<div class="empty-state">Category analytics appear once artifacts exist.</div>`; return; }
  let cur = 0;
  const stops = entries.map((e, i) => { const s = cur; cur += e[1] / total * 100; return `${PALETTE[i % PALETTE.length]} ${s}% ${cur}%`; }).join(",");
  host.innerHTML = `<div class="donut" style="background:conic-gradient(${stops})"><div class="donut-center"><strong>${total}</strong><small>Artifacts</small></div></div>
    <div class="legend">${entries.map((e, i) => `<div class="legend-row"><span class="legend-dot" style="background:${PALETTE[i % PALETTE.length]}"></span><span title="${esc(e[0])}">${esc(e[0])}</span><strong>${Math.round(e[1] / total * 100)}%</strong></div>`).join("")}</div>`;
}

function bars(host, rows, { unit = "", max = null, color = null } = {}) {
  if (!rows.length) { host.innerHTML = `<div class="empty-state">No data yet.</div>`; return; }
  const top = max ?? Math.max(...rows.map(r => r[1]), 1);
  host.innerHTML = rows.map(([label, value], i) => `<div class="bar-row"><span title="${esc(label)}">${esc(label)}</span>
    <div class="bar-track"><div class="bar-fill" style="width:${Math.max(2, value / top * 100)}%;background:${color || PALETTE[i % PALETTE.length]}"></div></div>
    <strong>${fmtNum(value)}${unit}</strong></div>`).join("");
}

function jobStatusPill(s) { return `<span class="pill ${esc(s)}">${esc(s)}</span>`; }

function eventText(e) {
  const d = e.details || {};
  const map = {
    created: e.entity_type === "artifact" ? `Registered “${d.title}”` : `Prediction “${d.label}”`,
    updated: `Updated ${(d.fields || []).filter(f => f !== "updated_at").join(", ")}`,
    deleted: `Deleted “${d.title}”`,
    images_uploaded: `Uploaded ${d.count} photo${d.count === 1 ? "" : "s"}`,
    image_deleted: "Removed a photo",
    queued: `Queued ${d.engine} reconstruction (${d.images} photos)`,
    completed: `Reconstruction finished · ${fmtNum(d.points)} points`,
    failed: `Reconstruction failed`,
    reviewed: `Reviewed label “${d.label}”`,
    exported: `Exported ${e.entity_id} (${d.rows} rows)`,
    package_exported: "Exported preservation package",
  };
  return map[e.action] || `${e.entity_type} ${e.action}`;
}
const EVENT_ICON = { created: ["gold", "＋"], images_uploaded: ["blue", "↥"], queued: ["orange", "◇"], completed: ["green", "✓"], failed: ["red", "!"], reviewed: ["purple", "✳"], updated: ["blue", "✎"], deleted: ["red", "✕"] };

/* ---------------------------------------------------------------- overview */
function renderOverview() {
  const s = state.summary;
  const a = state.artifacts;
  $("overviewGrid").innerHTML = a.length ? a.slice(0, 8).map(artifactCard).join("") : emptyCollection();
  if (s) {
    $("totalArtifacts").textContent = fmtNum(s.artifacts);
    $("reviewedSummary").textContent = `${s.reviewed_artifacts} reviewed · ${s.artifacts - s.reviewed_artifacts} draft`;
    $("totalImages").textContent = fmtNum(s.images);
    $("imageBytes").textContent = `${fmtBytes(s.image_bytes)} of originals`;
    $("totalJobs").textContent = fmtNum(s.jobs_total);
    $("jobSummary").textContent = Object.entries(s.jobs).map(([k, v]) => `${v} ${k}`).join(" · ") || "None submitted yet";
    $("totalPoints").textContent = fmtNum(s.points_reconstructed);
    donut($("categoryChart"), s.categories.slice(0, 6).map(c => [c.category, c.count]));
    $("activityList").innerHTML = s.recent_events.length ? s.recent_events.slice(0, 6).map(e => {
      const [c, i] = EVENT_ICON[e.action] || ["blue", "•"];
      return `<div class="activity-item"><span class="activity-marker ${c}">${i}</span><div><strong>${esc(eventText(e))}</strong><p>${esc(e.entity_type)} · ${esc(fmtDate(e.created_at))}</p></div></div>`;
    }).join("") : `<div class="empty-state">No activity yet.</div>`;
  }
  loadLatestModel(viewer("overview", "overviewViewerHost", { emptyText: "Run a reconstruction to see the latest model here." }));
}

async function loadLatestModel(v, artifactId = "") {
  try {
    const jobs = await api(`/api/jobs?status=completed&limit=1${artifactId ? `&artifact_id=${encodeURIComponent(artifactId)}` : ""}`);
    if (jobs.length && jobs[0].model_url) {
      if (v.loadedJob !== jobs[0].id) {
        await v.load(jobs[0].model_url, jobs[0].cameras_url, jobs[0].artifact_title || "Sparse point cloud");
        v.loadedJob = jobs[0].id;
      }
    } else { v.clear(); v.loadedJob = null; }
  } catch (err) { v.clear(`Viewer error: ${err.message}`); }
}

/* ---------------------------------------------------------------- collection */
function renderCollection() {
  const q = $("globalSearch").value.trim().toLowerCase();
  const cat = $("categoryFilter").value;
  const list = state.artifacts.filter(a => (!cat || a.category === cat) &&
    (!q || `${a.title} ${a.category} ${a.id} ${a.material} ${a.period} ${a.origin}`.toLowerCase().includes(q)));
  $("collectionCaption").textContent = q || cat
    ? `${list.length} of ${state.artifacts.length} records match${q ? ` “${q}”` : ""}${cat ? ` in ${cat}` : ""}.`
    : `${state.artifacts.length} record${state.artifacts.length === 1 ? "" : "s"} in your database.`;
  $("collectionGrid").innerHTML = state.artifacts.length
    ? (list.map(artifactCard).join("") || `<div class="empty-state">No artifacts match this search.</div>`)
    : emptyCollection();
}

/* ---------------------------------------------------------------- detail */
const META_FIELDS = [
  ["title", "Title", "input"], ["category", "Category", "input"], ["period", "Period", "input"], ["material", "Material", "input"],
  ["origin", "Origin", "input"], ["dimensions", "Dimensions", "input"], ["creator", "Creator / maker", "input"], ["condition", "Condition", "input"],
  ["description", "Description", "textarea"], ["provenance", "Provenance", "textarea"], ["rights", "Rights statement", "input"], ["license_url", "License URL", "input"],
];

async function renderDetail(id) {
  state.detailId = id;
  const a = await api(`/api/artifacts/${encodeURIComponent(id)}`);
  $("detailTitle").textContent = a.title;
  $("detailMeta").innerHTML = `${esc(a.category)} · ID <code>${esc(a.id)}</code> · created ${esc(fmtDate(a.created_at))}`;
  $("detailReview").textContent = a.review_status || "draft";
  $("detailReport").href = `/api/artifacts/${a.id}/report`;
  $("detailPackage").href = `/api/artifacts/${a.id}/package`;
  $("detailCapture").href = `#/capture/${a.id}`;
  $("detailForm").innerHTML = META_FIELDS.map(([k, label, kind]) => `<label class="${kind === "textarea" ? "span-2" : ""}">${label}
      ${kind === "textarea" ? `<textarea name="${k}" rows="3">${esc(a[k])}</textarea>` : `<input name="${k}" value="${esc(a[k])}">`}</label>`).join("") +
    `<label>Review status<select name="review_status">${["draft", "in_review", "reviewed"].map(s => `<option ${a.review_status === s ? "selected" : ""}>${s}</option>`).join("")}</select></label>
     <div class="form-actions span-2"><span class="helper">Last updated ${esc(fmtDate(a.updated_at || a.created_at))}</span><button class="btn btn-gold" type="submit">Save changes</button></div>`;
  $("detailImages").innerHTML = a.assets.length ? a.assets.map(img => `<figure class="thumb">
      <a href="${esc(img.url)}" target="_blank" rel="noopener"><img loading="lazy" src="${esc(img.thumbnail_url)}" alt="${esc(img.original_filename || "photo")}"></a>
      <figcaption title="SHA-256 ${esc(img.checksum)}">${esc(img.width)}×${esc(img.height)}</figcaption>
      <button class="thumb-del" data-del-image="${esc(img.id)}" title="Remove photo" aria-label="Remove photo">✕</button></figure>`).join("")
    : `<div class="empty-state">No photographs yet. <a href="#/capture/${esc(a.id)}">Add photos</a>.</div>`;
  $("detailJobs").innerHTML = a.jobs.length ? a.jobs.slice(0, 4).map(j => `<div class="job-row">${jobStatusPill(j.status)}
      <span>${esc(j.engine || "")} · ${esc(fmtDate(j.created_at))}</span><span class="job-msg" title="${esc(j.message)}">${esc(j.message)}</span>
      ${j.model_url ? `<a class="text-button" href="${esc(j.model_url)}" download>⇩ PLY</a>` : ""}</div>`).join("")
    : `<p class="helper">No reconstructions yet. At least 3 photographs are needed.</p>`;
  const v = viewer("detail", "detailViewerHost", { emptyText: "No completed reconstruction for this artifact yet." });
  const done = a.jobs.find(j => j.model_url);
  if (done) { if (v.loadedJob !== done.id) { await v.load(done.model_url, done.cameras_url, a.title); v.loadedJob = done.id; } }
  else { v.clear(); v.loadedJob = null; }
  $("detailPredictions").innerHTML = predictionList(a.predictions);
}

function predictionList(preds) {
  if (!preds.length) return `<p class="helper">No predictions stored. Predictions require a trained classifier.</p>`;
  return preds.map(p => `<div class="prediction">
    <div class="prediction-head"><strong>${esc(p.predicted_label)}</strong>${jobStatusPill(p.status)}<small>${esc(p.model_version)} · ${esc(fmtDate(p.created_at))}</small></div>
    ${(p.scores || []).map(s => `<div class="bar-row"><span>${esc(s.label)}</span><div class="bar-track"><div class="bar-fill" style="width:${s.score * 100}%"></div></div><strong>${(s.score * 100).toFixed(1)}%</strong></div>`).join("")}
    <form class="review-form" data-review="${esc(p.id)}"><input name="label" placeholder="Expert-confirmed label" value="${esc(p.reviewer_label)}" required><button class="btn btn-outline btn-small">Save review</button></form>
  </div>`).join("");
}

/* ---------------------------------------------------------------- capture */
function renderCapture(arg) {
  if (arg && state.artifacts.some(a => a.id === arg)) $("captureArtifact").value = arg;
  renderPending();
}

function renderPending() {
  $("pendingGallery").innerHTML = state.pending.map((p, i) => `<figure class="thumb"><img src="${p.url}" alt=""><figcaption>${esc(fmtBytes(p.file.size))}</figcaption>
    <button class="thumb-del" data-del-pending="${i}" aria-label="Remove">✕</button></figure>`).join("");
  $("uploadButton").textContent = state.pending.length ? `Upload ${state.pending.length} photo${state.pending.length === 1 ? "" : "s"}` : "Upload photos";
}

function addPending(files) {
  for (const file of files) {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) { toast(`${file.name}: only JPEG, PNG and WEBP are supported`, "error"); continue; }
    state.pending.push({ file, url: URL.createObjectURL(file) });
  }
  renderPending();
}

async function uploadPending() {
  const id = $("captureArtifact").value;
  if (!id) return message("uploadMessage", "Select an artifact first.", "error");
  if (!state.pending.length) return message("uploadMessage", "Add one or more photographs first.", "error");
  const form = new FormData();
  state.pending.forEach(p => form.append("files", p.file, p.file.name));
  $("uploadButton").disabled = true;
  message("uploadMessage", `Uploading ${state.pending.length} photo(s)…`);
  try {
    const r = await api(`/api/artifacts/${encodeURIComponent(id)}/images`, { method: "POST", body: form });
    state.pending.forEach(p => URL.revokeObjectURL(p.url)); state.pending = [];
    renderPending();
    message("uploadMessage", `Saved ${r.uploaded} photo(s) with SHA-256 checksums.`, "success");
    toast(`${r.uploaded} photo(s) uploaded`, "success");
    await loadAll();
  } catch (err) { message("uploadMessage", `Upload failed: ${err.message}`, "error"); }
  finally { $("uploadButton").disabled = false; }
}

/* ---------------------------------------------------------------- reconstruction */
let pollTimer = null;
const STAGE_ORDER = ["preparing", "features", "matching", "registration", "mapping", "bundle_adjustment", "export", "validation", "completed"];

function updateStepper(job) {
  const idx = STAGE_ORDER.indexOf(job?.stage === "mapping" ? "registration" : job?.stage === "export" ? "validation" : job?.stage);
  document.querySelectorAll("#jobStepper li").forEach(li => {
    const i = STAGE_ORDER.indexOf(li.dataset.stage);
    li.className = !job ? "" : job.status === "completed" ? "done" : i < idx ? "done" : i === idx ? (job.status === "failed" ? "failed" : "active") : "";
  });
}

async function renderReconstruction(arg) {
  if (arg && state.artifacts.some(a => a.id === arg)) $("reconArtifact").value = arg;
  const r = state.readiness;
  if (r) {
    const e = r.reconstruction_engines;
    [...$("engineSelect").options].forEach(o => { if (o.value !== "auto") { o.disabled = !e[o.value]; o.textContent = o.textContent.replace(/ \(unavailable\)$/, "") + (e[o.value] ? "" : " (unavailable)"); } });
    $("engineHelp").textContent = `Auto uses: ${{ colmap: "native COLMAP", docker: "COLMAP in Docker", opencv: "the built-in OpenCV engine" }[r.reconstruction_engine_selected] || "nothing — no engine installed"}.`;
  }
  const v = viewer("recon", "reconViewerHost", { emptyText: "Choose an artifact with a completed job, or start one." });
  await refreshJobs();
  const id = $("reconArtifact").value;
  if (id) await loadLatestModel(v, id); else await loadLatestModel(v);
}

async function refreshJobs() {
  const jobs = await api("/api/jobs?limit=50");
  $("jobsTable").innerHTML = `<thead><tr><th>Status</th><th>Artifact</th><th>Engine</th><th>Cameras</th><th>Points</th><th>Reproj. error</th><th>Time</th><th>Started</th><th></th></tr></thead><tbody>` +
    (jobs.length ? jobs.map(j => `<tr><td>${jobStatusPill(j.status)}</td><td><a href="#/artifact/${esc(j.artifact_id)}">${esc(j.artifact_title || "—")}</a></td>
      <td>${esc(j.engine)}</td><td>${j.stats.images_registered != null ? `${j.stats.images_registered}/${j.stats.images_input}` : "—"}</td>
      <td>${j.stats.points != null ? fmtNum(j.stats.points) : "—"}</td>
      <td>${j.stats.mean_reprojection_error_px != null ? j.stats.mean_reprojection_error_px.toFixed(2) + " px" : "—"}</td>
      <td>${j.stats.seconds != null ? j.stats.seconds.toFixed(0) + " s" : "—"}</td><td>${esc(fmtDate(j.created_at))}</td>
      <td class="nowrap"><button class="text-button" data-show-job="${esc(j.id)}">Log</button>${j.model_url ? ` <button class="text-button" data-view-job="${esc(j.id)}">View</button> <a class="text-button" href="${esc(j.model_url)}" download>⇩</a>` : ""}</td></tr>`).join("")
      : `<tr><td colspan="9" class="helper">No jobs yet.</td></tr>`) + "</tbody>";
  return jobs;
}

async function showJob(jobId) {
  const [job, log] = await Promise.all([api(`/api/jobs/${jobId}`), api(`/api/jobs/${jobId}/logs?tail=60`)]);
  updateStepper(job);
  message("jobMessage", job.message, job.status === "failed" ? "error" : job.status === "completed" ? "success" : "");
  const box = $("jobLog");
  box.textContent = log.lines.map(l => l.replace(/^\S+\s+/, "")).join("\n") || "Waiting for first log line…";
  box.scrollTop = box.scrollHeight;
  return job;
}

async function startReconstruction() {
  const id = $("reconArtifact").value;
  if (!id) return message("jobMessage", "Select an artifact first.", "error");
  $("reconstructButton").disabled = true;
  try {
    const r = await api(`/api/artifacts/${encodeURIComponent(id)}/reconstructions`, {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ engine: $("engineSelect").value }),
    });
    toast(`Reconstruction queued with ${r.engine}`, "success");
    pollJob(r.job_id);
  } catch (err) { message("jobMessage", `Could not start: ${err.message}`, "error"); $("reconstructButton").disabled = false; }
}

function pollJob(jobId) {
  clearTimeout(pollTimer);
  const tick = async () => {
    try {
      const job = await showJob(jobId);
      if (job.status === "completed" || job.status === "failed") {
        $("reconstructButton").disabled = false;
        await refreshJobs();
        if (job.model_url) {
          await viewer("recon", "reconViewerHost").load(job.model_url, job.cameras_url, "Sparse point cloud");
          viewer("recon", "reconViewerHost").loadedJob = job.id;
          toast(`Reconstruction complete · ${fmtNum(job.stats.points)} points`, "success");
        } else toast("Reconstruction failed — see the job log", "error");
        loadAll();
        return;
      }
    } catch (err) { message("jobMessage", `Status polling failed: ${err.message}`, "error"); }
    pollTimer = setTimeout(tick, 1500);
  };
  tick();
}

/* ---------------------------------------------------------------- classification */
async function renderClassification(arg) {
  if (arg && state.artifacts.some(a => a.id === arg)) $("clfArtifact").value = arg;
  const st = await api("/api/classifier");
  $("clfBadge").textContent = st.available ? "available" : "unavailable";
  $("clfBadge").className = `soft-badge ${st.available ? "ok" : "warn"}`;
  message("clfStatus", st.available ? `Model ${st.model_version} is installed. Scores are uncalibrated suggestions that need expert review.` : `${st.reason} No prediction is ever fabricated.`, st.available ? "success" : "");
  $("classifyButton").disabled = !st.available;
  const m = st.metrics;
  $("clfMetrics").innerHTML = m ? `<table class="data-table compact"><tr><th>Dataset</th><td>${esc(m.dataset)}</td></tr><tr><th>Classes</th><td>${esc((m.classes || []).join(", "))}</td></tr>
    <tr><th>Train / validation images</th><td>${esc(m.train_images)} / ${esc(m.validation_images)}</td></tr><tr><th>Best validation macro-F1</th><td>${(m.best_validation_macro_f1 ?? 0).toFixed(3)}</td></tr>
    <tr><th>Caution</th><td>${esc(m.caution)}</td></tr></table>` : "";
  await loadPredictions();
}

async function loadPredictions() {
  const id = $("clfArtifact").value;
  if (!id) { $("clfPredictions").innerHTML = ""; return; }
  const a = await api(`/api/artifacts/${encodeURIComponent(id)}`);
  $("clfPredictions").innerHTML = predictionList(a.predictions);
}

/* ---------------------------------------------------------------- analytics */
function renderAnalytics() {
  const s = state.summary, arts = state.artifacts;
  if (!s) return;
  bars($("chartCategories"), s.categories.map(c => [c.category, c.count]));
  const fields = [["description", "Description"], ["period", "Period"], ["material", "Material"], ["origin", "Origin"], ["dimensions", "Dimensions"], ["provenance", "Provenance"], ["rights", "Rights"]];
  bars($("chartCompleteness"), arts.length ? fields.map(([k, l]) => [l, Math.round(arts.filter(a => (a[k] || "").trim()).length / arts.length * 100)]) : [], { unit: "%", max: 100, color: "#ad741d" });
  const days = s.uploads_by_day.slice(-14);
  const top = Math.max(1, ...days.map(d => d.count));
  $("chartUploads").innerHTML = days.length ? days.map(d => `<div class="col"><span class="col-val">${d.count}</span><div class="col-bar" style="height:${d.count / top * 100}%"></div><small>${esc(d.day.slice(5))}</small></div>`).join("")
    : `<div class="empty-state">No uploads yet.</div>`;
  bars($("chartJobs"), Object.entries(s.jobs), {});
  loadDataset();
}

const ds = { offset: 0, limit: 24 };
let dsTimer;
async function loadDataset() {
  const split = $("datasetSplit").value, q = $("datasetSearch").value.trim();
  try {
    const d = await api(`/api/dataset?split=${split}&q=${encodeURIComponent(q)}&limit=${ds.limit}&offset=${ds.offset}`);
    $("datasetSummary").textContent = `${d.source} · ${d.split} split · ${fmtNum(d.total)} records${q ? ` matching “${q}”` : ""}`;
    $("datasetCards").innerHTML = d.items.map(it => `<article class="dataset-card">
      <a href="${esc(it.object_url)}" target="_blank" rel="noopener noreferrer"><img src="${esc(it.image_url)}" loading="lazy" alt="${esc(it.title || it.label)}"></a>
      <div class="dataset-card-body"><h3>${esc(it.title || "Untitled object")}</h3><p><b>Label</b> ${esc(it.label || "—")}</p><p><b>Object</b> ${esc(it.object_id || "—")}</p></div></article>`).join("")
      || `<div class="empty-state">No matching records.</div>`;
    $("datasetPage").textContent = d.total ? `${d.offset + 1}–${Math.min(d.offset + ds.limit, d.total)} of ${fmtNum(d.total)}` : "";
    $("datasetPrevious").disabled = d.offset === 0; $("datasetNext").disabled = d.offset + ds.limit >= d.total;
  } catch (err) {
    $("datasetSummary").textContent = `Reference dataset not installed. ${err.message}`;
    $("datasetCards").innerHTML = ""; $("datasetPage").textContent = "";
    $("datasetPrevious").disabled = $("datasetNext").disabled = true;
  }
}

/* ---------------------------------------------------------------- reports */
function renderReports() {
  $("exportTable").innerHTML = `<thead><tr><th>Artifact</th><th>Category</th><th>Photos</th><th>Review</th><th>3D</th><th>Exports</th></tr></thead><tbody>` +
    (state.artifacts.length ? state.artifacts.map(a => `<tr><td><a href="#/artifact/${esc(a.id)}">${esc(a.title)}</a></td><td>${esc(a.category)}</td><td>${a.image_count}</td>
      <td>${esc(a.review_status)}</td><td>${a.latest_job_status ? jobStatusPill(a.latest_job_status) : "—"}</td>
      <td class="nowrap"><a class="text-button" href="/api/artifacts/${esc(a.id)}/report" target="_blank" rel="noopener">Report</a> ·
      <a class="text-button" href="/api/artifacts/${esc(a.id)}/record.json" target="_blank" rel="noopener">JSON</a> ·
      <a class="text-button" href="/api/artifacts/${esc(a.id)}/package">Package ⇩</a></td></tr>`).join("")
      : `<tr><td colspan="6" class="helper">No artifacts yet.</td></tr>`) + "</tbody>";
  const ev = state.summary?.recent_events || [];
  $("auditTable").innerHTML = `<thead><tr><th>When</th><th>Entity</th><th>Event</th></tr></thead><tbody>` +
    (ev.length ? ev.map(e => `<tr><td class="nowrap">${esc(fmtDate(e.created_at))}</td><td>${esc(e.entity_type)} <code>${esc(e.entity_id.slice(0, 8))}</code></td><td>${esc(eventText(e))}</td></tr>`).join("")
      : `<tr><td colspan="3" class="helper">No events yet.</td></tr>`) + "</tbody>";
}

/* ---------------------------------------------------------------- settings */
function renderSettings() {
  const r = state.readiness, s = state.settings;
  const ok = v => v ? `<span class="pill completed">available</span>` : `<span class="pill failed">unavailable</span>`;
  if (r) $("readinessTable").innerHTML = `<tbody>
    <tr><th>API</th><td>${ok(r.api)}</td></tr><tr><th>Database</th><td>${ok(r.database)}</td></tr>
    <tr><th>COLMAP (native)</th><td>${ok(r.reconstruction_engines.colmap)}</td></tr><tr><th>COLMAP (Docker)</th><td>${ok(r.reconstruction_engines.docker)}</td></tr>
    <tr><th>Built-in OpenCV SfM</th><td>${ok(r.reconstruction_engines.opencv)}</td></tr><tr><th>Engine used by “auto”</th><td>${esc(r.reconstruction_engine_selected || "none")}</td></tr>
    <tr><th>AI classifier</th><td>${ok(r.classifier)}<div class="helper">${esc(r.classifier_note)}</div></td></tr>
    <tr><th>Reference dataset</th><td>${ok(r.dataset)}</td></tr></tbody>`;
  if (s) $("settingsTable").innerHTML = `<tbody>
    <tr><th>Version</th><td>${esc(s.version)}</td></tr><tr><th>Engine preference</th><td><code>${esc(s.reconstruction_engine_preference)}</code></td></tr>
    <tr><th>COLMAP binary</th><td><code>${esc(s.colmap_binary)}</code></td></tr><tr><th>COLMAP Docker image</th><td><code>${esc(s.colmap_docker_image)}</code></td></tr>
    <tr><th>Job timeout</th><td>${esc(s.reconstruction_timeout_s)} s</td></tr><tr><th>Upload limit</th><td>${esc(s.max_upload_mb)} MB × ${esc(s.max_files_per_request)} files</td></tr>
    <tr><th>Min. photos for 3D</th><td>${esc(s.min_reconstruction_images)}</td></tr><tr><th>CORS origins</th><td>${esc(s.cors_origins.join(", ") || "same-origin only")}</td></tr>
    <tr><th>Storage used</th><td>${esc(fmtBytes(s.storage_bytes))}</td></tr><tr><th>API docs</th><td><a class="text-button" href="/docs" target="_blank" rel="noopener">/docs ↗</a></td></tr></tbody>`;
}

/* ---------------------------------------------------------------- events */
function openRegister() { $("registerForm").reset(); $("registerMessage").textContent = ""; $("registerDialog").showModal(); }

document.addEventListener("click", async e => {
  const t = e.target;
  if (t.closest("[data-action=register]")) { e.preventDefault(); openRegister(); }
  const delImg = t.closest("[data-del-image]");
  if (delImg && confirmDelete("Remove this photo? Its file is deleted from storage.")) {
    try { await api(`/api/artifacts/${state.detailId}/images/${delImg.dataset.delImage}`, { method: "DELETE" }); toast("Photo removed"); await loadAll(); }
    catch (err) { toast(err.message, "error"); }
  }
  const delPending = t.closest("[data-del-pending]");
  if (delPending) { const [p] = state.pending.splice(+delPending.dataset.delPending, 1); URL.revokeObjectURL(p.url); renderPending(); }
  const showJ = t.closest("[data-show-job]");
  if (showJ) { try { await showJob(showJ.dataset.showJob); } catch (err) { toast(err.message, "error"); } }
  const viewJ = t.closest("[data-view-job]");
  if (viewJ) {
    const job = await api(`/api/jobs/${viewJ.dataset.viewJob}`);
    const v = viewer("recon", "reconViewerHost"); await v.load(job.model_url, job.cameras_url, job.artifact_title || "Sparse point cloud"); v.loadedJob = job.id;
    window.scrollTo({ top: 0, behavior: "smooth" });
  }
});

// Native confirm() is avoided so the app also works in kiosk/automation contexts.
function confirmDelete(text) { return window.__skipConfirm || window.confirm(text); }

document.addEventListener("submit", async e => {
  const review = e.target.closest("[data-review]");
  if (review) {
    e.preventDefault();
    try {
      await api(`/api/predictions/${review.dataset.review}/review`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ reviewer_label: review.label.value }) });
      toast("Expert label saved", "success"); render();
    } catch (err) { toast(err.message, "error"); }
  }
});

$("registerForm").addEventListener("submit", async e => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(e.target).entries());
  $("registerSubmit").disabled = true;
  try {
    const r = await api("/api/artifacts", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    $("registerDialog").close();
    toast(`“${payload.title}” registered`, "success");
    await loadAll();
    location.hash = `#/artifact/${r.id}`;
  } catch (err) { $("registerMessage").textContent = `Registration failed: ${err.message}`; }
  finally { $("registerSubmit").disabled = false; }
});
$("closeDialog").addEventListener("click", () => $("registerDialog").close());
$("cancelDialog").addEventListener("click", () => $("registerDialog").close());

$("detailForm").addEventListener("submit", async e => {
  e.preventDefault();
  const payload = Object.fromEntries(new FormData(e.target).entries());
  try {
    await api(`/api/artifacts/${state.detailId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
    toast("Record saved", "success"); await loadAll();
  } catch (err) { toast(`Save failed: ${err.message}`, "error"); }
});
$("detailDelete").addEventListener("click", async () => {
  if (!confirmDelete("Delete this artifact, its photos and its 3D outputs? This cannot be undone.")) return;
  try { await api(`/api/artifacts/${state.detailId}`, { method: "DELETE" }); toast("Artifact deleted"); location.hash = "#/collection"; await loadAll(); }
  catch (err) { toast(err.message, "error"); }
});
$("detailReconstruct").addEventListener("click", () => { location.hash = `#/reconstruction/${state.detailId}`; });

$("dropZone").addEventListener("click", () => $("photoFiles").click());
$("dropZone").addEventListener("keydown", e => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); $("photoFiles").click(); } });
$("photoFiles").addEventListener("change", e => { addPending(e.target.files); e.target.value = ""; });
["dragenter", "dragover"].forEach(ev => $("dropZone").addEventListener(ev, e => { e.preventDefault(); $("dropZone").classList.add("over"); }));
["dragleave", "drop"].forEach(ev => $("dropZone").addEventListener(ev, e => { e.preventDefault(); $("dropZone").classList.remove("over"); }));
$("dropZone").addEventListener("drop", e => addPending(e.dataTransfer.files));
$("clearPending").addEventListener("click", () => { state.pending.forEach(p => URL.revokeObjectURL(p.url)); state.pending = []; renderPending(); });
$("uploadButton").addEventListener("click", uploadPending);

$("reconstructButton").addEventListener("click", startReconstruction);
$("reconArtifact").addEventListener("change", () => { const id = $("reconArtifact").value; loadLatestModel(viewer("recon", "reconViewerHost"), id); });
$("classifyButton").addEventListener("click", async () => {
  const id = $("clfArtifact").value;
  if (!id) return message("clfResult", "Select an artifact first.", "error");
  try {
    const r = await api(`/api/artifacts/${encodeURIComponent(id)}/classifications`, { method: "POST" });
    message("clfResult", `Suggested “${r.predicted_label}” from ${r.images_used} image(s). Needs expert review.`, "success");
    await loadPredictions();
  } catch (err) { message("clfResult", err.message, "error"); }
});
$("clfArtifact").addEventListener("change", loadPredictions);

$("datasetSplit").addEventListener("change", () => { ds.offset = 0; loadDataset(); });
$("datasetSearch").addEventListener("input", () => { clearTimeout(dsTimer); dsTimer = setTimeout(() => { ds.offset = 0; loadDataset(); }, 250); });
$("datasetPrevious").addEventListener("click", () => { ds.offset = Math.max(0, ds.offset - ds.limit); loadDataset(); });
$("datasetNext").addEventListener("click", () => { ds.offset += ds.limit; loadDataset(); });

$("searchForm").addEventListener("submit", e => { e.preventDefault(); location.hash = "#/collection"; renderCollection(); });
$("globalSearch").addEventListener("input", () => { if (state.route !== "collection") location.hash = "#/collection"; else renderCollection(); });
$("categoryFilter").addEventListener("change", renderCollection);
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); $("globalSearch").focus(); } });
$("refreshButton").addEventListener("click", loadAll);
$("mobileMenu").addEventListener("click", () => $("sidebar").classList.toggle("open"));
window.addEventListener("hashchange", render);

loadAll();

/* ================================================================ webcam auto-scan */
(() => {
  const video = $("scanVideo"), canvas = $("scanCanvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const startButton = $("scanStartButton"), stopButton = $("scanStopButton"), clearButton = $("scanClearButton");
  const status = $("scanStatus"), gallery = $("scanGallery"), progress = $("scanProgressBar");
  const select = () => $("captureArtifact").value;

  let stream = null, scanning = false, captured = [], previousFrame = null;
  let lastCaptureAt = 0, lastChangeAt = 0, scanStartedAt = 0;
  const MIN_PHOTOS = 15, MAX_PHOTOS = 60, MAX_SCAN_MS = 180000, NO_CHANGE_STOP_MS = 12000, CAPTURE_INTERVAL_MS = 1200, CHANGE_THRESHOLD = 11;

  const scanMessage = (text, kind = "") => { status.textContent = text; status.className = `job-message ${kind}`.trim(); };

  function renderGallery() {
    gallery.replaceChildren();
    captured.forEach((item, index) => {
      const w = document.createElement("div"); w.className = "scan-thumb";
      const img = document.createElement("img"); img.src = item.url; img.alt = `Captured view ${index + 1}`;
      const label = document.createElement("span"); label.textContent = String(index + 1);
      w.append(img, label); gallery.append(w);
    });
    progress.style.width = `${captured.length / MAX_PHOTOS * 100}%`;
  }

  function frameDifference(a, b) {
    if (!a || !b || a.length !== b.length) return Infinity;
    let total = 0;
    for (let i = 0; i < a.length; i += 4) total += Math.abs(a[i] - b[i]) + Math.abs(a[i + 1] - b[i + 1]) + Math.abs(a[i + 2] - b[i + 2]);
    return total / (a.length / 4 * 3);
  }

  function readFrame() { canvas.width = 32; canvas.height = 24; ctx.drawImage(video, 0, 0, 32, 24); return ctx.getImageData(0, 0, 32, 24).data; }

  async function captureFrame() {
    const { videoWidth: w, videoHeight: h } = video;
    if (!w || !h) return false;
    canvas.width = w; canvas.height = h; ctx.drawImage(video, 0, 0, w, h);
    const blob = await new Promise(r => canvas.toBlob(r, "image/jpeg", 0.92));
    if (!blob) return false;
    captured.push({ blob, url: URL.createObjectURL(blob), name: `webcam_scan_${String(captured.length + 1).padStart(3, "0")}.jpg` });
    renderGallery();
    scanMessage(`Captured ${captured.length}/${MAX_PHOTOS} photos. Rotate the object slowly to expose a new side.`);
    return true;
  }

  async function uploadCaptured() {
    const artifactId = select();
    if (!artifactId) return scanMessage("Select an artifact before saving photos.", "error");
    if (captured.length < MIN_PHOTOS) return scanMessage(`Only ${captured.length} photos captured. Capture at least ${MIN_PHOTOS} before uploading.`, "error");
    startButton.disabled = stopButton.disabled = true;
    scanMessage(`Uploading ${captured.length} captured photos…`);
    const form = new FormData();
    captured.forEach(item => form.append("files", item.blob, item.name));
    try {
      const result = await api(`/api/artifacts/${encodeURIComponent(artifactId)}/images`, { method: "POST", body: form });
      scanMessage(`Saved ${result.uploaded} photos. You can now start a reconstruction.`, "success");
      loadAll();
    } catch (err) { scanMessage(`Upload failed: ${err.message}. Captured photos remain here; retry after checking the API.`, "error"); }
    finally { startButton.disabled = false; stopButton.disabled = true; }
  }

  async function stopScan(save = true) {
    scanning = false; stopButton.disabled = true;
    if (stream) { stream.getTracks().forEach(t => t.stop()); stream = null; }
    video.srcObject = null;
    if (save && captured.length >= MIN_PHOTOS) await uploadCaptured();
    else if (captured.length < MIN_PHOTOS) { scanMessage(`Scan stopped with ${captured.length} photos. Need at least ${MIN_PHOTOS}; rotate more slowly with good lighting.`, "error"); startButton.disabled = false; }
  }

  async function loop() {
    while (scanning) {
      const now = Date.now();
      if (captured.length >= MAX_PHOTOS) { scanMessage(`Reached ${MAX_PHOTOS} photos.`); return stopScan(true); }
      if (now - scanStartedAt > MAX_SCAN_MS) { scanMessage("Reached the 3-minute scan limit."); return stopScan(true); }
      try {
        const frame = readFrame();
        if (previousFrame === null || frameDifference(previousFrame, frame) >= CHANGE_THRESHOLD) {
          lastChangeAt = now;
          if (now - lastCaptureAt >= CAPTURE_INTERVAL_MS && await captureFrame()) lastCaptureAt = now;
        }
        previousFrame = new Uint8ClampedArray(frame);
        if (now - lastChangeAt >= NO_CHANGE_STOP_MS) { scanMessage("The view has not changed for 12 seconds. Finishing the scan."); return stopScan(true); }
      } catch (err) { scanMessage(`Capture error: ${err.message}`, "error"); return stopScan(false); }
      await new Promise(r => setTimeout(r, 350));
    }
  }

  startButton.addEventListener("click", async () => {
    if (!select()) return scanMessage("Select an artifact before starting the webcam.", "error");
    if (!navigator.mediaDevices?.getUserMedia) return scanMessage("Camera access is unavailable. Use localhost or HTTPS in a supported browser.", "error");
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } }, audio: false });
      video.srcObject = stream; await video.play();
      captured.forEach(i => URL.revokeObjectURL(i.url)); captured = []; previousFrame = null;
      lastCaptureAt = 0; lastChangeAt = scanStartedAt = Date.now(); renderGallery();
      scanning = true; startButton.disabled = true; stopButton.disabled = false;
      scanMessage("Scanning… rotate the object slowly in front of the camera.");
      loop();
    } catch (err) {
      if (stream) stream.getTracks().forEach(t => t.stop()); stream = null;
      scanMessage(`Could not open webcam: ${err.message}. Check browser camera permission.`, "error"); startButton.disabled = false;
    }
  });
  stopButton.addEventListener("click", () => stopScan(true));
  clearButton.addEventListener("click", async () => {
    if (scanning) await stopScan(false);
    captured.forEach(i => URL.revokeObjectURL(i.url)); captured = []; previousFrame = null; renderGallery();
    scanMessage("Captured photos cleared. Start a new scan when ready."); startButton.disabled = false; stopButton.disabled = true;
  });
  $("captureArtifact").addEventListener("change", () => { if (scanning) stopScan(false); });
  window.addEventListener("beforeunload", () => { if (stream) stream.getTracks().forEach(t => t.stop()); captured.forEach(i => URL.revokeObjectURL(i.url)); });
})();
