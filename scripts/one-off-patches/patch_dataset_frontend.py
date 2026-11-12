from pathlib import Path

p = Path("frontend/index.html")
s = p.read_text(encoding="utf-8")

if 'id="museumDatasetGallery"' in s:
    raise SystemExit("Dataset gallery already exists. No changes made.")

anchor = "</main>"
if anchor not in s:
    raise SystemExit("Could not find closing main tag.")

section = r'''
<section class="dataset-panel" id="museumDatasetGallery">
  <div class="dataset-heading">
    <div>
      <span class="eyebrow">REAL SOURCE DATA</span>
      <h2>Museum Dataset Explorer</h2>
      <p>Browse verified image files and metadata from the downloaded iMet subset.</p>
    </div>
    <a href="https://huggingface.co/datasets/timm/imet-open-access"
       target="_blank" rel="noopener noreferrer">Dataset source ↗</a>
  </div>

  <div class="dataset-controls">
    <label>Split
      <select id="datasetSplit">
        <option value="train">Training images</option>
        <option value="validation">Validation images</option>
      </select>
    </label>
    <label>Search title or label
      <input id="datasetSearch" type="search" placeholder="Search real dataset records...">
    </label>
    <button id="datasetLoad" type="button">Load records</button>
  </div>

  <p id="datasetSummary" role="status">Loading dataset metadata...</p>
  <div id="datasetCards" class="dataset-cards"></div>
  <div class="dataset-pagination">
    <button id="datasetPrevious" type="button" class="secondary">Previous</button>
    <span id="datasetPage">Page 1</span>
    <button id="datasetNext" type="button" class="secondary">Next</button>
  </div>
  <p class="dataset-disclaimer">
    Dataset examples are separate from your registered artifacts.
    Original object information belongs to the source collection.
  </p>
</section>

<style>
.dataset-panel{margin:28px 0;padding:24px;background:var(--panel,#fff);
  border:1px solid var(--line,#ddd);border-radius:18px}
.dataset-heading,.dataset-controls,.dataset-pagination{
  display:flex;gap:16px;justify-content:space-between;align-items:end;flex-wrap:wrap}
.dataset-heading h2{margin:8px 0}
.dataset-controls{margin:20px 0}
.dataset-controls label{flex:1;min-width:170px}
.dataset-controls input,.dataset-controls select{width:100%;margin-top:7px}
.dataset-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(190px,1fr));gap:16px}
.dataset-card{min-width:0;overflow:hidden;border:1px solid var(--line,#ddd);border-radius:13px}
.dataset-card img{width:100%;height:180px;object-fit:contain;background:#f1f0ec;display:block}
.dataset-card-body{padding:12px}
.dataset-card h3{font-size:14px;line-height:1.4;margin:0 0 8px}
.dataset-card p{font-size:12px;overflow-wrap:anywhere}
.dataset-card a{font-size:12px}
.dataset-pagination{justify-content:center;margin-top:20px}
.dataset-disclaimer{font-size:12px;opacity:.75;margin-top:16px}
@media(max-width:600px){.dataset-panel{padding:15px}.dataset-heading{align-items:start}}
</style>

<script>
(() => {
  const $ = id => document.getElementById(id);
  const state = { split: "train", offset: 0, limit: 24, total: 0, items: [] };

  const esc = value => String(value ?? "").replace(/[&<>"']/g, c => ({
    "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;"
  })[c]);

  async function load() {
    const split = $("datasetSplit").value;
    const search = $("datasetSearch").value.trim().toLowerCase();
    state.split = split;
    $("datasetSummary").textContent = "Loading verified dataset records...";
    $("datasetCards").innerHTML = "";

    try {
      const response = await fetch(
        `/api/dataset?split=${encodeURIComponent(split)}&limit=100&offset=0`
      );
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Dataset API request failed");

      state.total = data.total;
      state.items = data.items || [];
      const filtered = state.items.filter(item =>
        `${item.title} ${item.label} ${item.object_id}`.toLowerCase().includes(search)
      );

      const start = state.offset;
      const visible = filtered.slice(start, start + state.limit);

      $("datasetSummary").textContent =
        `${data.source} · ${data.split} split · ${data.total} available records` +
        (search ? ` · ${filtered.length} matches in the loaded page of records` : "");

      $("datasetCards").innerHTML = visible.map(item => `
        <article class="dataset-card">
          <a href="${esc(item.object_url)}" target="_blank" rel="noopener noreferrer">
            <img src="${esc(item.image_url)}" loading="lazy"
              alt="${esc(item.title || item.label || "Museum object image")}">
          </a>
          <div class="dataset-card-body">
            <h3>${esc(item.title || "Untitled object")}</h3>
            <p><strong>Label:</strong> ${esc(item.label || "Not provided")}</p>
            <p><strong>Object ID:</strong> ${esc(item.object_id || "Not provided")}</p>
            <a href="${esc(item.object_url)}" target="_blank" rel="noopener noreferrer">
              View source record ↗
            </a>
          </div>
        </article>`).join("") ||
        "<p>No matching records on this page. Try another search or page.</p>";

      $("datasetPage").textContent = `Loaded ${start + 1}–${Math.min(start + state.limit, filtered.length)} of ${filtered.length} matches`;
      $("datasetPrevious").disabled = start === 0;
      $("datasetNext").disabled = start + state.limit >= filtered.length;
    } catch (error) {
      $("datasetSummary").textContent = `Dataset unavailable: ${error.message}`;
      $("datasetCards").innerHTML = "";
    }
  }

  $("datasetLoad").addEventListener("click", () => { state.offset = 0; load(); });
  $("datasetSplit").addEventListener("change", () => { state.offset = 0; load(); });
  $("datasetSearch").addEventListener("input", () => { state.offset = 0; load(); });
  $("datasetPrevious").addEventListener("click", () => {
    state.offset = Math.max(0, state.offset - state.limit); load();
  });
  $("datasetNext").addEventListener("click", () => {
    state.offset += state.limit; load();
  });
  load();
})();
</script>
'''

s = s.replace(anchor, section + "\n" + anchor, 1)
p.write_text(s, encoding="utf-8")
print("Added dataset gallery to the existing dashboard.")
