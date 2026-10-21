const API_BASE = window.location.origin;
const $ = (id) => document.getElementById(id);
const state = { artifacts: [], readiness: null, jobs: [], selectedArtifact: "" };

function escapeHTML(value) {
  return String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[c]);
}
function first(obj, keys, fallback = "") {
  for (const key of keys) {
    if (obj && obj[key] !== undefined && obj[key] !== null && obj[key] !== "") return obj[key];
  }
  return fallback;
}
async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const type = response.headers.get("content-type") || "";
  const data = type.includes("application/json")
    ? await response.json()
    : await response.text();
  if (!response.ok) {
    const rawDetail = data && typeof data === "object" ? (data.detail || data.message || data) : data;
    throw new Error(rawDetail == null ? `Request failed (${response.status})` : (typeof rawDetail === "string" ? rawDetail : JSON.stringify(rawDetail)));
  }
  return data;
}
function setText(id, value) {
  const el = $(id);
  if (el) el.textContent = value;
}
function setSystem(prefix, label, good) {
  const detail = $(`${prefix}Detail`);
  const dot = $(`${prefix}StatusDot`);
  if (detail) {
    detail.textContent = label;
    detail.className = good ? "ok" : "warn";
  }
  if (dot) dot.className = `status-dot ${good ? "" : "warn"}`;
}
function normalizeList(data) {
  if (Array.isArray(data)) return data;
  if (!data || typeof data !== "object") return [];
  for (const key of ["artifacts", "items", "results", "data"]) {
    if (Array.isArray(data[key])) return data[key];
  }
  return [];
}
function artifactId(item) {
  return String(first(item, ["id", "artifact_id", "uuid", "_id"], ""));
}
function artifactName(item) {
  return String(first(item, ["name", "title", "artifact_name", "object_name"], "Untitled artifact"));
}
function artifactCategory(item) {
  return String(first(item, ["category", "artifact_type", "type", "classification"], "Uncategorized"));
}
function imageFor(item) {
  return first(item, ["thumbnail_url", "image_url", "preview_url", "image"], "");
}
function dateFor(item) {
  const raw = first(item, ["created_at", "createdAt", "date_created", "created"]);
  if (!raw) return "Date not recorded";
  const d = new Date(raw);
  return Number.isNaN(d.getTime()) ? String(raw) : d.toLocaleDateString(undefined, {year:"numeric",month:"short",day:"numeric"});
}
function imageMarkup(item) {
  const url = imageFor(item);
  if (url && /^https?:\/\//i.test(url)) {
    return `<img loading="lazy" src="${escapeHTML(url)}" alt="${escapeHTML(artifactName(item))}" onerror="this.style.display='none'">`;
  }
  return `<div class="artifact-placeholder"><span>◇</span></div>`;
}
function renderArtifacts(items = state.artifacts) {
  const grid = $("artifactGrid");
  if (!items.length) {
    grid.innerHTML = `<div class="empty-state">No artifacts found in the database yet.<br>Register your first artifact to start the digital collection.</div>`;
  } else {
    grid.innerHTML = items.slice(0, 8).map(item => {
      const id = artifactId(item);
      return `<article class="artifact-card">
        ${imageMarkup(item)}
        <div class="artifact-info"><strong title="${escapeHTML(artifactName(item))}">${escapeHTML(artifactName(item))}</strong>
        <small>${escapeHTML(artifactCategory(item))}</small>
        <small class="artifact-id">${escapeHTML(id ? `ID: ${id}` : dateFor(item))}</small>
        </div></article>`;
    }).join("");
  }
  const select = $("artifactSelect");
  const previous = select.value;
  select.innerHTML = `<option value="">Choose an artifact…</option>` + state.artifacts.map(item => {
    const id = artifactId(item);
    return id ? `<option value="${escapeHTML(id)}">${escapeHTML(artifactName(item))}</option>` : "";
  }).join("");
  const validPrevious = state.artifacts.some(x => artifactId(x) === previous);
  const selectedId = validPrevious
    ? previous
    : (state.artifacts.length ? artifactId(state.artifacts[0]) : "");
  select.value = selectedId;
  state.selectedArtifact = selectedId;
  setText("totalArtifacts", String(state.artifacts.length));
  setText("activityCollection", `${state.artifacts.length} artifact record(s) returned by the backend.`);
  renderCategories(items);
}
function renderCategories(items) {
  const counts = {};
  items.forEach(item => {
    const cat = artifactCategory(item);
    counts[cat] = (counts[cat] || 0) + 1;
  });
  const entries = Object.entries(counts).sort((a,b) => b[1]-a[1]).slice(0,5);
  const colors = ["#4386fa","#f16e72","#ffc66c","#48c6a0","#a16be8"];
  const total = items.length;
  if (!total) {
    $("categoryChart").innerHTML = `<div class="empty-state">Category analytics will appear when artifacts exist.</div>`;
    return;
  }
  let cursor = 0;
  const stops = entries.map((entry,i) => {
    const start = cursor; cursor += entry[1]/total*100;
    return `${colors[i]} ${start}% ${cursor}%`;
  }).join(",");
  $("categoryChart").innerHTML = `<div class="donut" style="background:conic-gradient(${stops})"><div class="donut-center"><strong>${total}</strong><small>Artifacts</small></div></div>
    <div class="legend">${entries.map((entry,i)=>`<div class="legend-row"><span class="legend-dot" style="background:${colors[i]}"></span><span title="${escapeHTML(entry[0])}">${escapeHTML(entry[0])}</span><strong>${Math.round(entry[1]/total*100)}%</strong></div>`).join("")}</div>`;
}
async function loadReadiness() {
  try {
    const data = await api("/api/readiness");
    state.readiness = data;
    setText("apiStatus", "API Online");
    $("apiDot").className = "online-dot";
    setText("apiDetail", "Online");
    $("apiDetail").className = "ok";
    $("apiStatusDot").className = "status-dot";
    const values = data.components || data.services || data;
    const component = (...keys) => {
      for (const key of keys) if (values[key] !== undefined) return values[key];
      return null;
    };
    const healthy = v => v === true || v === "ok" || v === "available" || v === "connected" || v === "ready";
    const db = component("database", "db");
    const colmap = component("colmap", "reconstruction");
    const classifier = component("classifier", "ai_classifier");
    setSystem("db", db == null ? "Status unknown" : healthy(db) ? "Connected" : typeof db === "object" ? JSON.stringify(db) : String(db), healthy(db));
    setSystem("colmap", colmap == null ? "Status unknown" : healthy(colmap) ? "Available" : typeof colmap === "object" ? String(colmap.status || colmap.runtime || "Check required") : String(colmap), healthy(colmap));
    setSystem("classifier", classifier == null ? "Integration pending" : healthy(classifier) ? "Available" : typeof classifier === "object" ? String(classifier.status || "Integration pending") : String(classifier), healthy(classifier));
    setText("readinessMessage", "Readiness is based on the backend response; unknown fields are not assumed healthy.");
    setText("classifierSummary", healthy(classifier) ? "Backend reports available" : "Integration pending");
    setText("activityClassifier", healthy(classifier) ? "Backend reports classifier available; verify actual inference." : "Classifier inference is not confirmed available.");
  } catch (error) {
    setText("apiStatus", "API unavailable");
    $("apiDot").className = "status-dot warn";
    setText("apiDetail", "Connection failed");
    $("apiDetail").className = "warn";
    $("apiStatusDot").className = "status-dot warn";
    setText("readinessMessage", `Could not read readiness: ${error.message}`);
  }
}
async function loadArtifacts() {
  try {
    const data = await api("/api/artifacts");
    state.artifacts = normalizeList(data);
    renderArtifacts();
    setText("collectionCaption", `${state.artifacts.length} record(s) loaded from the backend`);
    setText("lastUpdated", `Updated ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    $("artifactGrid").innerHTML = `<div class="empty-state">Could not load artifacts.<br>${escapeHTML(error.message)}<br>Check that the FastAPI backend is running.</div>`;
    $("categoryChart").innerHTML = `<div class="empty-state">Analytics unavailable until the API responds.</div>`;
    setText("totalArtifacts", "—");
    setText("collectionMessage", "The frontend is loaded, but the artifact endpoint did not return data.");
  }
}
async function loadJobs() {
  // The existing API exposes individual job status, but may not expose a jobs list.
  // Do not invent a job count.
  setText("totalJobs", "—");
  setText("classifierCount", "—");
}
async function refreshAll() {
  $("refreshButton").textContent = "…";
  await Promise.all([loadReadiness(), loadArtifacts(), loadJobs()]);
  $("refreshButton").textContent = "↻";
}
function openRegister() {
  $("registerMessage").textContent = "";
  $("registerDialog").showModal();
}
function showPage(page) {
  document.querySelectorAll(".nav-item").forEach(btn => btn.classList.toggle("active", btn.dataset.page === page));
  if (window.innerWidth <= 850) $("mainNav").parentElement.classList.remove("open");
  if (page === "Artifact Collection") $("globalSearch").focus();
  if (page === "Capture Studio") $("photoFiles").click();
  if (page === "3D Reconstruction") $("artifactSelect").focus();
  if (page === "AI Classification") {
    $("jobMessage").textContent = "The backend's classification endpoint must be checked for an artifact before displaying predictions. No prediction is fabricated.";
  }
  if (page !== "Overview") {
    setText("collectionMessage", `${page}: this dashboard foundation is ready. We will implement this workspace next using verified backend capabilities.`);
  } else setText("collectionMessage", "");
}
document.addEventListener("click", event => {
  const nav = event.target.closest("[data-page]");
  if (nav) showPage(nav.dataset.page);
  const action = event.target.closest("[data-action]")?.dataset.action;
  if (action === "register") openRegister();
  if (action === "capture" || action === "upload") $("photoFiles").click();
});
$("refreshButton").addEventListener("click", refreshAll);
$("mobileMenu").addEventListener("click", () => document.querySelector(".sidebar").classList.toggle("open"));
$("closeDialog").addEventListener("click", () => $("registerDialog").close());
$("cancelDialog").addEventListener("click", () => $("registerDialog").close());
$("globalSearch").addEventListener("input", e => {
  const q = e.target.value.trim().toLowerCase();
  renderArtifacts(state.artifacts.filter(item =>
    artifactName(item).toLowerCase().includes(q) ||
    artifactCategory(item).toLowerCase().includes(q) ||
    artifactId(item).toLowerCase().includes(q)
  ));
});
document.addEventListener("keydown", event => {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k") {
    event.preventDefault(); $("globalSearch").focus();
  }
});
$("registerForm").addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true; button.textContent = "Saving…";
  const payload = {
    title: $("artifactName").value.trim(),
    category: $("artifactCategory").value.trim(),
    description: $("artifactDescription").value.trim()
  };
  try {
    const result = await api("/api/artifacts", {
      method:"POST", headers:{"Content-Type":"application/json"}, body:JSON.stringify(payload)
    });
    $("registerMessage").textContent = "Artifact registration request succeeded.";
    $("registerMessage").className = "inline-message";
    $("registerDialog").close();
    $("registerForm").reset();
    await loadArtifacts();
    setText("collectionMessage", `Artifact registered. ${JSON.stringify(result).slice(0,180)}`);
  } catch (error) {
    $("registerMessage").textContent = `Registration failed: ${error.message}. The backend may expect different field names; we will align the form with its schema.`;
    $("registerMessage").className = "inline-message";
  } finally {
    button.disabled = false; button.textContent = "Save artifact";
  }
});
$("artifactSelect").addEventListener("change", event => {
  state.selectedArtifact = event.target.value;
  setText("jobMessage", state.selectedArtifact ? "Artifact selected. Upload at least three photos of the same object." : "Select an artifact to get started.");
});
$("uploadButton").addEventListener("click", async () => {
  const id = $("artifactSelect").value;
  const files = $("photoFiles").files;
  const msg = $("jobMessage");
  if (!id) { msg.textContent = "Select an artifact first."; msg.className = "job-message error"; return; }
  if (!files.length) { msg.textContent = "Choose one or more image files first."; msg.className = "job-message error"; return; }
  const form = new FormData();
  for (const file of files) form.append("files", file);
  $("uploadButton").disabled = true;
  msg.textContent = `Uploading ${files.length} photo(s)…`; msg.className = "job-message";
  try {
    const result = await api(`/api/artifacts/${encodeURIComponent(id)}/images`, {method:"POST",body:form});
    msg.textContent = `Upload succeeded: ${JSON.stringify(result).slice(0,350)}`;
    msg.className = "job-message success";
    setText("totalImages", "—");
  } catch (error) {
    msg.textContent = `Upload failed: ${error.message}`;
    msg.className = "job-message error";
  } finally { $("uploadButton").disabled = false; }
});
$("reconstructButton").addEventListener("click", async () => {
  const id = $("artifactSelect").value;
  const msg = $("jobMessage");
  if (!id) { msg.textContent = "Select an artifact first."; msg.className = "job-message error"; return; }
  $("reconstructButton").disabled = true;
  msg.textContent = "Submitting reconstruction job…"; msg.className = "job-message";
  try {
    const result = await api(`/api/artifacts/${encodeURIComponent(id)}/reconstructions`, {method:"POST"});
    const jobId = first(result, ["job_id", "id", "jobId"], "");
    msg.textContent = `Reconstruction submitted. ${JSON.stringify(result).slice(0,280)}`;
    msg.className = "job-message success";
    if (jobId) {
      setText("viewerState", `Job ${jobId}`);
      pollJob(jobId);
    }
  } catch (error) {
    msg.textContent = `Reconstruction failed: ${error.message}. Upload at least three photos first.`;
    msg.className = "job-message error";
  } finally { $("reconstructButton").disabled = false; }
});
async function pollJob(jobId) {
  const msg = $("jobMessage");
  for (let attempt=0; attempt<8; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 2500));
    try {
      const data = await api(`/api/jobs/${encodeURIComponent(jobId)}`);
      msg.textContent = `Job status: ${JSON.stringify(data).slice(0,350)}`;
      const status = String(first(data, ["status", "state"], "")).toLowerCase();
      if (["completed","complete","failed","error","succeeded"].includes(status)) {
        if (["completed","complete","succeeded"].includes(status)) msg.className = "job-message success";
        return;
      }
    } catch (error) {
      msg.textContent = `Job submitted, but status polling failed: ${error.message}`;
      return;
    }
  }
}
refreshAll();




/* AUTO_SCAN_MODULE_START */
(() => {
  const video = $("scanVideo");
  const canvas = $("scanCanvas");
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  const startButton = $("scanStartButton");
  const stopButton = $("scanStopButton");
  const clearButton = $("scanClearButton");
  const status = $("scanStatus");
  const gallery = $("scanGallery");
  const progress = $("scanProgressBar");

  let stream = null;
  let scanning = false;
  let captured = [];
  let previousFrame = null;
  let lastCaptureAt = 0;
  let lastChangeAt = 0;
  let scanStartedAt = 0;

  const MIN_PHOTOS = 15;
  const MAX_PHOTOS = 60;
  const MAX_SCAN_MS = 180000;
  const NO_CHANGE_STOP_MS = 12000;
  const CAPTURE_INTERVAL_MS = 1200;
  const CHANGE_THRESHOLD = 11;

  function scanMessage(text, kind = "") {
    status.textContent = text;
    status.className = `job-message ${kind}`.trim();
  }

  function renderGallery() {
    gallery.replaceChildren();
    captured.forEach((item, index) => {
      const wrapper = document.createElement("div");
      wrapper.className = "scan-thumb";
      const img = document.createElement("img");
      img.src = item.url;
      img.alt = `Captured view ${index + 1}`;
      const label = document.createElement("span");
      label.textContent = String(index + 1);
      wrapper.append(img, label);
      gallery.append(wrapper);
    });
    progress.style.width = `${captured.length / MAX_PHOTOS * 100}%`;
  }

  function frameDifference(a, b) {
    if (!a || !b || a.length !== b.length) return Infinity;
    let total = 0;
    for (let i = 0; i < a.length; i += 4) {
      total += Math.abs(a[i] - b[i]);
      total += Math.abs(a[i + 1] - b[i + 1]);
      total += Math.abs(a[i + 2] - b[i + 2]);
    }
    return total / (a.length / 4 * 3);
  }

  function readFrame() {
    const w = 32;
    const h = 24;
    canvas.width = w;
    canvas.height = h;
    ctx.drawImage(video, 0, 0, w, h);
    return ctx.getImageData(0, 0, w, h).data;
  }

  async function captureFrame() {
    const width = video.videoWidth;
    const height = video.videoHeight;
    if (!width || !height) return false;

    canvas.width = width;
    canvas.height = height;
    ctx.drawImage(video, 0, 0, width, height);

    const blob = await new Promise(resolve =>
      canvas.toBlob(resolve, "image/jpeg", 0.92)
    );
    if (!blob) return false;

    const url = URL.createObjectURL(blob);
    captured.push({
      blob,
      url,
      name: `webcam_scan_${String(captured.length + 1).padStart(3, "0")}.jpg`
    });
    renderGallery();
    scanMessage(`Captured ${captured.length}/${MAX_PHOTOS} photos. Rotate the object slowly to expose a new side.`);
    return true;
  }

  async function uploadCaptured() {
    const artifactId = $("artifactSelect").value;
    if (!artifactId) {
      scanMessage("Select an artifact before saving photos.", "error");
      return;
    }
    if (captured.length < MIN_PHOTOS) {
      scanMessage(`Only ${captured.length} photos captured. Capture at least ${MIN_PHOTOS} before uploading.`, "error");
      return;
    }

    startButton.disabled = true;
    stopButton.disabled = true;
    scanMessage(`Uploading ${captured.length} captured photos…`);

    const form = new FormData();
    captured.forEach(item => form.append("files", item.blob, item.name));

    try {
      const result = await api(
        `/api/artifacts/${encodeURIComponent(artifactId)}/images`,
        { method: "POST", body: form }
      );
      scanMessage(`Saved ${result.uploaded ?? captured.length} photos to the selected artifact. You can now start reconstruction.`, "success");
      $("jobMessage").textContent = "Webcam photos uploaded. Start reconstruction when ready.";
      $("jobMessage").className = "job-message success";
    } catch (error) {
      scanMessage(`Upload failed: ${error.message}. Captured photos remain available here; retry after checking the API.`, "error");
    } finally {
      startButton.disabled = false;
      stopButton.disabled = true;
    }
  }

  async function stopScan(save = true) {
    scanning = false;
    stopButton.disabled = true;
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      stream = null;
    }
    video.srcObject = null;

    if (save && captured.length >= MIN_PHOTOS) {
      await uploadCaptured();
    } else if (captured.length < MIN_PHOTOS) {
      scanMessage(`Scan stopped with ${captured.length} photos. Need at least ${MIN_PHOTOS}; try rotating more slowly with good lighting.`, "error");
      startButton.disabled = false;
    }
  }

  async function runScanLoop() {
    while (scanning) {
      const now = Date.now();

      if (captured.length >= MAX_PHOTOS) {
        scanMessage(`Reached ${MAX_PHOTOS} photos. Finishing the scan.`);
        await stopScan(true);
        return;
      }

      if (now - scanStartedAt > MAX_SCAN_MS) {
        scanMessage("Reached the 3-minute scan limit.");
        await stopScan(true);
        return;
      }

      try {
        const frame = readFrame();
        const difference = frameDifference(previousFrame, frame);

        if (previousFrame === null || difference >= CHANGE_THRESHOLD) {
          lastChangeAt = now;
          if (now - lastCaptureAt >= CAPTURE_INTERVAL_MS) {
            if (await captureFrame()) lastCaptureAt = now;
          }
        }

        previousFrame = new Uint8ClampedArray(frame);

        if (now - lastChangeAt >= NO_CHANGE_STOP_MS) {
          scanMessage("The view has not changed for 12 seconds. Finishing the scan.");
          await stopScan(true);
          return;
        }
      } catch (error) {
        scanMessage(`Capture error: ${error.message}`, "error");
        await stopScan(false);
        return;
      }

      await new Promise(resolve => setTimeout(resolve, 350));
    }
  }

  startButton.addEventListener("click", async () => {
    if (!$("artifactSelect").value) {
      scanMessage("Select an artifact before starting the webcam.", "error");
      return;
    }

    if (!navigator.mediaDevices?.getUserMedia) {
      scanMessage("Camera access is unavailable. Use localhost or HTTPS in a supported browser.", "error");
      return;
    }

    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "environment", width: { ideal: 1920 }, height: { ideal: 1080 } },
        audio: false
      });
      video.srcObject = stream;
      await video.play();

      captured.forEach(item => URL.revokeObjectURL(item.url));
      captured = [];
      previousFrame = null;
      lastCaptureAt = 0;
      lastChangeAt = Date.now();
      scanStartedAt = Date.now();
      renderGallery();

      scanning = true;
      startButton.disabled = true;
      stopButton.disabled = false;
      scanMessage("Scanning… rotate the object slowly in front of the camera.");
      runScanLoop();
    } catch (error) {
      if (stream) stream.getTracks().forEach(track => track.stop());
      stream = null;
      scanMessage(`Could not open webcam: ${error.message}. Check browser camera permission.`, "error");
      startButton.disabled = false;
    }
  });

  stopButton.addEventListener("click", () => stopScan(true));

  clearButton.addEventListener("click", async () => {
    if (scanning) await stopScan(false);
    captured.forEach(item => URL.revokeObjectURL(item.url));
    captured = [];
    previousFrame = null;
    renderGallery();
    scanMessage("Captured photos cleared. Start a new scan when ready.");
    startButton.disabled = false;
    stopButton.disabled = true;
  });

  $("artifactSelect").addEventListener("change", () => {
    if (scanning) stopScan(false);
  });

  window.addEventListener("beforeunload", () => {
    if (stream) stream.getTracks().forEach(track => track.stop());
    captured.forEach(item => URL.revokeObjectURL(item.url));
  });
})();
/* AUTO_SCAN_MODULE_END */

