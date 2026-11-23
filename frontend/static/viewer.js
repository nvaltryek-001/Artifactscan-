/* ArtifactScan point cloud viewer — dependency-free canvas renderer.
 *
 * Loads a PLY (binary little/big endian or ASCII) plus an optional
 * cameras.json, aligns the model so "up" matches the photographer's up
 * direction, and renders with a per-pixel depth buffer. Drag to orbit,
 * scroll to zoom, double-click to reset.
 */
(function () {
  "use strict";

  const TYPES = {
    char: ["getInt8", 1], int8: ["getInt8", 1], uchar: ["getUint8", 1], uint8: ["getUint8", 1],
    short: ["getInt16", 2], int16: ["getInt16", 2], ushort: ["getUint16", 2], uint16: ["getUint16", 2],
    int: ["getInt32", 4], int32: ["getInt32", 4], uint: ["getUint32", 4], uint32: ["getUint32", 4],
    float: ["getFloat32", 4], float32: ["getFloat32", 4], double: ["getFloat64", 8], float64: ["getFloat64", 8],
  };

  function parsePLY(buffer) {
    const bytes = new Uint8Array(buffer);
    const marker = "end_header";
    let headerEnd = -1;
    for (let i = 0; i < Math.min(bytes.length, 65536) - marker.length; i++) {
      let ok = true;
      for (let k = 0; k < marker.length; k++) if (bytes[i + k] !== marker.charCodeAt(k)) { ok = false; break; }
      if (ok) { headerEnd = i + marker.length; break; }
    }
    if (headerEnd < 0) throw new Error("Not a PLY file");
    while (bytes[headerEnd] === 13 || bytes[headerEnd] === 10) { headerEnd++; if (bytes[headerEnd - 1] === 10) break; }
    const header = new TextDecoder().decode(bytes.slice(0, headerEnd)).split(/\r?\n/);
    let format = "ascii", count = 0, inVertex = false;
    const props = [];
    for (const line of header) {
      const p = line.trim().split(/\s+/);
      if (p[0] === "format") format = p[1];
      else if (p[0] === "element") { inVertex = p[1] === "vertex"; if (inVertex) count = parseInt(p[2], 10); }
      else if (p[0] === "property" && inVertex) {
        if (p[1] === "list") throw new Error("List properties in vertex element are not supported");
        props.push({ type: p[1], name: p[2] });
      }
    }
    const idx = n => props.findIndex(p => p.name === n);
    const ix = idx("x"), iy = idx("y"), iz = idx("z");
    const ir = idx("red") >= 0 ? idx("red") : idx("r");
    const ig = idx("green") >= 0 ? idx("green") : idx("g");
    const ib = idx("blue") >= 0 ? idx("blue") : idx("b");
    if (ix < 0 || iy < 0 || iz < 0) throw new Error("PLY has no x/y/z properties");
    const pos = new Float32Array(count * 3);
    const col = new Uint8Array(count * 3).fill(200);

    if (format === "ascii") {
      const body = new TextDecoder().decode(bytes.slice(headerEnd)).split(/\r?\n/);
      for (let i = 0; i < count; i++) {
        const v = body[i].trim().split(/\s+/).map(Number);
        pos[i * 3] = v[ix]; pos[i * 3 + 1] = v[iy]; pos[i * 3 + 2] = v[iz];
        if (ir >= 0) { col[i * 3] = v[ir]; col[i * 3 + 1] = v[ig]; col[i * 3 + 2] = v[ib]; }
      }
    } else {
      const little = format === "binary_little_endian";
      const view = new DataView(buffer, headerEnd);
      const offsets = []; let stride = 0;
      for (const p of props) { offsets.push(stride); stride += TYPES[p.type][1]; }
      const read = (row, k) => {
        const [fn] = TYPES[props[k].type];
        return fn === "getInt8" || fn === "getUint8" ? view[fn](row + offsets[k]) : view[fn](row + offsets[k], little);
      };
      for (let i = 0; i < count; i++) {
        const row = i * stride;
        pos[i * 3] = read(row, ix); pos[i * 3 + 1] = read(row, iy); pos[i * 3 + 2] = read(row, iz);
        if (ir >= 0) { col[i * 3] = read(row, ir); col[i * 3 + 1] = read(row, ig); col[i * 3 + 2] = read(row, ib); }
      }
    }
    return { count, pos, col };
  }

  const v3 = {
    sub: (a, b) => [a[0] - b[0], a[1] - b[1], a[2] - b[2]],
    dot: (a, b) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2],
    cross: (a, b) => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]],
    norm: a => { const l = Math.hypot(a[0], a[1], a[2]) || 1; return [a[0] / l, a[1] / l, a[2] / l]; },
  };

  function median(arr) { const s = Float64Array.from(arr).sort(); return s[Math.floor(s.length / 2)]; }

  class PointCloudViewer {
    constructor(host, opts = {}) {
      this.host = host;
      this.opts = opts;
      host.classList.add("pcv-host");
      host.innerHTML = `
        <div class="pcv-top"><span>MODEL VIEWER</span><span class="pcv-state">No model loaded</span></div>
        <div class="pcv-stage">
          <canvas class="pcv-canvas"></canvas>
          <div class="pcv-empty"><div class="wire-cube">◇</div><strong>${opts.emptyTitle || "Your 3D model will appear here"}</strong>
            <p>${opts.emptyText || "Upload overlapping photos and run a reconstruction."}</p></div>
        </div>
        <div class="pcv-bar">
          <span class="pcv-info">Drag to orbit · scroll to zoom</span>
          <span class="pcv-tools">
            <label><input type="checkbox" class="pcv-cams" checked> cameras</label>
            <label><input type="checkbox" class="pcv-spin" ${opts.autoRotate === false ? "" : "checked"}> spin</label>
            <a class="pcv-download" hidden download>⇩ PLY</a>
          </span>
        </div>`;
      this.canvas = host.querySelector("canvas");
      this.ctx = this.canvas.getContext("2d");
      this.state = host.querySelector(".pcv-state");
      this.empty = host.querySelector(".pcv-empty");
      this.info = host.querySelector(".pcv-info");
      this.camsBox = host.querySelector(".pcv-cams");
      this.spinBox = host.querySelector(".pcv-spin");
      this.download = host.querySelector(".pcv-download");
      this.yaw = 0.6; this.pitch = 0.55; this.zoom = 1;
      this.points = null; this.cameras = []; this.camRadius = 0;
      this._bind();
      this._resize();
      new ResizeObserver(() => { this._resize(); this.draw(); }).observe(host);
    }

    _bind() {
      let drag = null;
      this.canvas.addEventListener("pointerdown", e => { drag = [e.clientX, e.clientY]; this.canvas.setPointerCapture(e.pointerId); this.spinBox.checked = false; });
      this.canvas.addEventListener("pointermove", e => {
        if (!drag) return;
        this.yaw += (e.clientX - drag[0]) * 0.01;
        this.pitch = Math.max(-1.5, Math.min(1.5, this.pitch + (e.clientY - drag[1]) * 0.01));
        drag = [e.clientX, e.clientY]; this.draw();
      });
      this.canvas.addEventListener("pointerup", () => { drag = null; });
      this.canvas.addEventListener("wheel", e => {
        e.preventDefault();
        this.zoom = Math.max(0.3, Math.min(6, this.zoom * (e.deltaY < 0 ? 1.1 : 0.9))); this.draw();
      }, { passive: false });
      this.canvas.addEventListener("dblclick", () => { this.yaw = 0.6; this.pitch = 0.55; this.zoom = 1; this.draw(); });
      this.camsBox.addEventListener("change", () => this.draw());
      const tick = () => {
        if (this.points && this.spinBox.checked && this.host.offsetParent !== null) { this.yaw += 0.006; this.draw(); }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    }

    _resize() {
      const r = this.canvas.parentElement.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      this.canvas.width = Math.max(10, Math.round(r.width * dpr));
      this.canvas.height = Math.max(10, Math.round(r.height * dpr));
      this.canvas.style.width = r.width + "px"; this.canvas.style.height = r.height + "px";
      this.dpr = dpr;
    }

    clear(message) {
      this.points = null; this.cameras = [];
      this.empty.hidden = false;
      this.state.textContent = message || "No model loaded";
      this.download.hidden = true;
      this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }

    async load(plyUrl, camerasUrl, label) {
      this.state.textContent = "Loading model…";
      const res = await fetch(plyUrl);
      if (!res.ok) throw new Error(`Model download failed (${res.status})`);
      const ply = parsePLY(await res.arrayBuffer());
      let cams = [];
      if (camerasUrl) {
        try { const c = await fetch(camerasUrl); if (c.ok) cams = (await c.json()).cameras || []; } catch (_) { /* optional */ }
      }
      this._prepare(ply, cams);
      this.empty.hidden = true;
      this.state.textContent = label || "Sparse point cloud";
      this.info.textContent = `${ply.count.toLocaleString()} points · ${cams.length} cameras`;
      this.download.href = plyUrl; this.download.hidden = false;
      this.draw();
    }

    _prepare(ply, cams) {
      const n = ply.count;
      const xs = new Float64Array(n), ys = new Float64Array(n), zs = new Float64Array(n);
      for (let i = 0; i < n; i++) { xs[i] = ply.pos[i * 3]; ys[i] = ply.pos[i * 3 + 1]; zs[i] = ply.pos[i * 3 + 2]; }
      const center = [median(xs), median(ys), median(zs)];

      // Up = average photographer "up" (image -y axis) in world coordinates.
      let up = [0, -1, 0];
      if (cams.length) {
        const s = [0, 0, 0];
        for (const c of cams) { const R = c.rotation; s[0] -= R[1][0]; s[1] -= R[1][1]; s[2] -= R[1][2]; }
        up = v3.norm(s);
      }
      let fwd = Math.abs(up[0]) < 0.9 ? [1, 0, 0] : [0, 0, 1];
      const right = v3.norm(v3.cross(fwd, up));
      fwd = v3.norm(v3.cross(up, right));
      this.basis = { center, right, up, fwd };

      const dists = new Float64Array(n);
      const local = new Float32Array(n * 3);
      for (let i = 0; i < n; i++) {
        const d = [xs[i] - center[0], ys[i] - center[1], zs[i] - center[2]];
        local[i * 3] = v3.dot(d, right); local[i * 3 + 1] = v3.dot(d, up); local[i * 3 + 2] = v3.dot(d, fwd);
        dists[i] = Math.hypot(d[0], d[1], d[2]);
      }
      const sorted = Float64Array.from(dists).sort();
      const radius = sorted[Math.floor(sorted.length * 0.9)] || 1;
      // Drop far outliers so they do not dominate the framing.
      const keep = [];
      for (let i = 0; i < n; i++) if (dists[i] < radius * 3) keep.push(i);
      this.points = { n: keep.length, pos: new Float32Array(keep.length * 3), col: new Uint8Array(keep.length * 3) };
      keep.forEach((src, k) => {
        for (let c = 0; c < 3; c++) { this.points.pos[k * 3 + c] = local[src * 3 + c] / radius; this.points.col[k * 3 + c] = ply.col[src * 3 + c]; }
      });
      this.camRadius = 0;
      this.cameras = cams.map(c => {
        const d = v3.sub(c.center, center);
        const p = [v3.dot(d, right) / radius, v3.dot(d, up) / radius, v3.dot(d, fwd) / radius];
        this.camRadius = Math.max(this.camRadius, Math.hypot(p[0], p[1], p[2]));
        return p;
      });
    }

    draw() {
      const { ctx, canvas } = this;
      const W = canvas.width, H = canvas.height;
      if (!this.points) return;
      const img = ctx.createImageData(W, H);
      const buf = img.data;
      const depth = new Float32Array(W * H).fill(Infinity);
      const cy = Math.cos(this.yaw), sy = Math.sin(this.yaw), cp = Math.cos(this.pitch), sp = Math.sin(this.pitch);
      const dist = Math.max(3.2, this.camRadius * 1.5) / this.zoom;
      const f = Math.min(W, H) * 1.05;
      const size = Math.max(1, Math.round(1.6 * this.dpr * Math.sqrt(this.zoom)));
      const { pos, col, n } = this.points;
      const project = (x, y, z) => {
        const x1 = cy * x + sy * z, z1 = -sy * x + cy * z;
        const y2 = cp * y - sp * z1, z2 = sp * y + cp * z1;
        const zc = dist - z2;
        return [W / 2 + f * x1 / zc, H / 2 - f * y2 / zc, zc];
      };
      for (let i = 0; i < n; i++) {
        const [px, py, zc] = project(pos[i * 3], pos[i * 3 + 1], pos[i * 3 + 2]);
        if (zc <= 0.05) continue;
        const x0 = Math.round(px), y0 = Math.round(py);
        const shade = Math.max(0.55, Math.min(1.1, 1.35 - zc * 0.18));
        for (let dy = 0; dy < size; dy++) {
          const yy = y0 + dy; if (yy < 0 || yy >= H) continue;
          for (let dx = 0; dx < size; dx++) {
            const xx = x0 + dx; if (xx < 0 || xx >= W) continue;
            const k = yy * W + xx;
            if (zc >= depth[k]) continue;
            depth[k] = zc;
            buf[k * 4] = Math.min(255, col[i * 3] * shade); buf[k * 4 + 1] = Math.min(255, col[i * 3 + 1] * shade);
            buf[k * 4 + 2] = Math.min(255, col[i * 3 + 2] * shade); buf[k * 4 + 3] = 255;
          }
        }
      }
      ctx.clearRect(0, 0, W, H);
      ctx.putImageData(img, 0, 0);
      if (this.camsBox.checked && this.cameras.length) {
        ctx.strokeStyle = "rgba(216,180,110,.85)"; ctx.fillStyle = "rgba(216,180,110,.9)";
        ctx.lineWidth = this.dpr;
        const pts = this.cameras.map(c => project(c[0], c[1], c[2]));
        ctx.beginPath();
        let pen = false;
        pts.forEach(([x, y, z]) => { if (z > 0.3) { pen ? ctx.lineTo(x, y) : ctx.moveTo(x, y); pen = true; } else pen = false; });
        ctx.setLineDash([3 * this.dpr, 4 * this.dpr]); ctx.stroke(); ctx.setLineDash([]);
        const o = project(0, 0, 0);
        for (const [x, y, z] of pts) {
          if (z <= 0.3) continue;
          ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + (o[0] - x) * 0.12, y + (o[1] - y) * 0.12); ctx.stroke();
          ctx.beginPath(); ctx.arc(x, y, 2.6 * this.dpr, 0, Math.PI * 2); ctx.fill();
        }
      }
    }
  }

  window.PointCloudViewer = PointCloudViewer;
  window.parsePLY = parsePLY;
})();
