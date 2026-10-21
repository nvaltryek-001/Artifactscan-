from pathlib import Path

root = Path("frontend")
html_path = root / "index.html"
js_path = root / "static" / "app.js"
css_path = root / "static" / "styles.css"

html = html_path.read_text(encoding="utf-8")
js = js_path.read_text(encoding="utf-8")
css = css_path.read_text(encoding="utf-8")

marker = '<label for="photoFiles">Artifact photographs</label>'
if marker not in html:
    raise SystemExit("Could not find the photo upload section in index.html.")
if 'id="autoScanPanel"' in html or "AUTO_SCAN_MODULE_START" in js:
    raise SystemExit("Scanner patch appears to exist already. No files changed.")

panel = """
              <section id="autoScanPanel" class="auto-scan-panel">
                <h3>Automatic webcam scanner</h3>
                <p class="helper">Keep the object in view and rotate it slowly. The scanner captures when the view changes.</p>
                <video id="scanVideo" autoplay playsinline muted></video>
                <canvas id="scanCanvas" hidden></canvas>
                <div class="scan-progress-track"><div id="scanProgressBar"></div></div>
                <p id="scanStatus" class="job-message" aria-live="polite">Camera is off. Select an artifact first.</p>
                <div id="scanGallery" class="scan-gallery"></div>
                <div class="scan-actions">
                  <button type="button" id="scanStartButton" class="btn btn-gold full-width">Start automatic scan</button>
                  <button type="button" id="scanStopButton" class="btn btn-outline full-width" disabled>Stop &amp; save photos</button>
                  <button type="button" id="scanClearButton" class="btn btn-outline full-width">Clear captured photos</button>
                </div>
                <small class="helper">Adaptive capture: minimum 15 frames, maximum 60. Useful reconstruction views are not guaranteed by frame-change detection alone.</small>
              </section>
"""

html = html.replace(marker, panel + "\n              " + marker, 1)

js_module = r"""
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
"""

js += "\n\n" + js_module + "\n"

css_addition = r"""

/* Automatic webcam scanner */
.auto-scan-panel{margin:12px 0;padding:13px;border:1px solid #e0e7ef;border-radius:12px;background:#fbfcfe}
.auto-scan-panel h3{margin:0 0 7px;font-size:14px;color:#182c45}
.auto-scan-panel video{display:block;width:100%;max-height:330px;min-height:180px;object-fit:contain;background:#101e2b;border-radius:9px;margin:10px 0}
.scan-progress-track{height:7px;background:#e5ebf3;border-radius:99px;overflow:hidden}
#scanProgressBar{height:100%;width:0;background:#bd8730;transition:width .2s}
.scan-actions{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:10px 0}
.scan-actions #scanStartButton{grid-column:1/-1}
.scan-gallery{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:6px;margin:10px 0}
.scan-thumb{position:relative;aspect-ratio:1;overflow:hidden;border-radius:7px;background:#e8edf4}
.scan-thumb img{width:100%;height:100%;object-fit:cover}
.scan-thumb span{position:absolute;bottom:3px;right:4px;background:#101e2b;color:white;border-radius:4px;padding:1px 5px;font-size:10px}
@media(max-width:560px){.scan-actions{grid-template-columns:1fr}.scan-actions #scanStartButton{grid-column:auto}.scan-gallery{grid-template-columns:repeat(4,minmax(0,1fr))}}
"""

css += "\n" + css_addition + "\n"

for p in (html_path, js_path, css_path):
    backup = p.with_name(p.name + ".bak-autoscan")
    if backup.exists():
        raise SystemExit(f"Backup already exists: {backup}. No files changed.")
    backup.write_text(p.read_text(encoding="utf-8"), encoding="utf-8")

html_path.write_text(html, encoding="utf-8")
js_path.write_text(js, encoding="utf-8")
css_path.write_text(css, encoding="utf-8")

print("Automatic scanner added.")
print("Backups created with .bak-autoscan suffix.")
