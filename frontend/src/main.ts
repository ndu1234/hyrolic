import * as BUI from '@thatopen/ui';
import * as OBC from '@thatopen/components';
import * as THREE from 'three';

// ── DOM ──────────────────────────────────────────────────────
const select = document.getElementById('model-select') as HTMLSelectElement;
const status = document.getElementById('model-status') as HTMLSpanElement;
const treeDiv = document.getElementById('tree') as HTMLDivElement;
const propsDiv = document.getElementById('props') as HTMLDivElement;
const countEl = document.getElementById('elem-count') as HTMLSpanElement;
const viewportEl = document.getElementById('viewport') as any;
const btnFit = document.getElementById('btn-fit') as HTMLButtonElement;
const btnHide = document.getElementById('btn-hide') as HTMLButtonElement;
const btnIso = document.getElementById('btn-iso') as HTMLButtonElement;
const btnShow = document.getElementById('btn-show') as HTMLButtonElement;
const btnSection = document.getElementById('btn-section') as HTMLButtonElement;
const sectionSlider = document.getElementById('section-slider') as HTMLInputElement;
const sectionLabel = document.getElementById('section-label') as HTMLSpanElement;
const sectionBar = document.getElementById('section-bar') as HTMLDivElement;

// ── State ────────────────────────────────────────────────────
let components: OBC.Components;
let world: OBC.SimpleWorld;
let fragments: OBC.FragmentsManager;
let ifcLoader: OBC.IfcLoader;
let selectedMap: OBC.ModelIdMap | null = null;
let currentModel: import('@thatopen/fragments').FragmentsModel | null = null;
let sectionMode = false;
let sectionPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0);
let sectionHelper: THREE.PlaneHelper | null = null;
const HIGHLIGHT: any = { color: [0.96, 0.72, 0.1], opacity: 0.6, transparent: true };

// ── Init ─────────────────────────────────────────────────────
(async () => {
  try {
    components = new OBC.Components();
    const worlds = components.get(OBC.Worlds);
    world = worlds.create<OBC.SimpleScene, OBC.OrthoPerspectiveCamera, OBC.SimpleRenderer>();
    world.scene = new OBC.SimpleScene(components);
    world.scene.setup();
    (world.scene.three as THREE.Scene).background = new THREE.Color(0x0a0a0f);
    world.renderer = new OBC.SimpleRenderer(components, viewportEl);
    (world.renderer.three as THREE.WebGLRenderer).localClippingEnabled = true;
    world.camera = new OBC.OrthoPerspectiveCamera(components);
    await world.camera.controls?.setLookAt(20, 16, 20, 0, 0, 0);
    await components.init();
    components.get(OBC.Grids).create(world);

    // Fragments
    fragments = components.get(OBC.FragmentsManager);
    fragments.init(await OBC.FragmentsManager.getWorker());
    world.camera.controls?.addEventListener('update', () => fragments.core.update());
    world.onCameraChanged.add((camera) => {
      for (const [, model] of fragments.list) model.useCamera(camera.three);
      fragments.core.update(true);
    });
    fragments.list.onItemSet.add(({ value: model }) => {
      model.useCamera(world.camera.three as THREE.Camera);
      world.scene.three.add(model.object);
      fragments.core.update(true);
      buildTree(model);
    });

    // IFC loader
    ifcLoader = components.get(OBC.IfcLoader);
    await ifcLoader.setup({ autoSetWasm: false, wasm: { path: '/ifc/', absolute: true } });

    // Bind UI
    setupPicker();
    btnFit.onclick = fitModel;
    btnHide.onclick = hideSelected;
    btnIso.onclick = isolateSelected;
    btnShow.onclick = showAll;
    btnSection.onclick = toggleSection;
    sectionSlider.oninput = () => updateSection(parseFloat(sectionSlider.value));

    // Populate model list
    const res = await fetch('/api/bim-ifc-files');
    const { files } = await res.json();
    select.innerHTML = '<option value="">Select an IFC file…</option>';
    for (const f of files) {
      select.innerHTML += `<option value="${f.name}">${f.name.replace('.ifc','')} (${f.size_mb.toFixed(1)} MB)</option>`;
    }
    select.onchange = () => { if (select.value) loadIfc(`/ifc/${select.value}`); };
    status.textContent = 'Ready';
  } catch (err) {
    status.textContent = 'Init error: ' + (err as Error).message;
    console.error(err);
  }
})();

// ── Load IFC ─────────────────────────────────────────────────
async function loadIfc(url: string) {
  for (const [id] of fragments.list) await fragments.core.models.disposeModel?.(id);
  selectedMap = null; currentModel = null;
  treeDiv.innerHTML = '';
  propsDiv.innerHTML = '<div style="color:#475569;font-size:12px;text-align:center;padding:20px 0;">Click an element in the model to see its properties</div>';

  status.textContent = 'Loading IFC…';
  try {
    const file = await fetch(url);
    const buffer = new Uint8Array(await file.arrayBuffer());
    try {
      await ifcLoader.load(buffer, true, select.value, {
        processData: { progressCallback: (p: number) => {
          if (p > 0 && p < 1) status.textContent = `Loading… ${Math.round(p * 100)}%`;
        }},
      });
    } catch (loadErr: any) {
      if (loadErr?.message?.includes('Unsupported') || loadErr?.message?.includes('Schema') || loadErr?.toString?.()?.includes('-1')) {
        throw new Error('This IFC file uses an unsupported schema. Try the ELE or HVAC file instead (IFC2X3).');
      }
      throw loadErr;
    }
    for (const [, model] of fragments.list) { currentModel = model; break; }
    if (currentModel) {
      const count = (await currentModel.getLocalIds()).length;
      countEl.textContent = `${count} elements`;
    }
    status.textContent = `Loaded: ${select.value.replace('.ifc','')}`;
    fitModel();
  } catch (err) {
    status.textContent = 'Error: ' + (err as Error).message;
  }
}

// ── Click picker ─────────────────────────────────────────────
function setupPicker() {
  const canvas = viewportEl.querySelector('canvas')!;
  const mouse = new THREE.Vector2();
  let dx = 0, dy = 0;
  canvas.addEventListener('pointerdown', (e) => { dx = e.clientX; dy = e.clientY; });
  canvas.addEventListener('pointerup', async (e: PointerEvent) => {
    if (Math.abs(e.clientX - dx) + Math.abs(e.clientY - dy) > 5) return;
    const rect = canvas.getBoundingClientRect();
    mouse.x = ((e.clientX - rect.left) / rect.width) * 2 - 1;
    mouse.y = -((e.clientY - rect.top) / rect.height) * 2 + 1;
    const result = await fragments.raycast({
      camera: world.camera!.three as THREE.PerspectiveCamera, mouse, dom: canvas,
    });
    if (!result) { clearSelection(); return; }
    const map: OBC.ModelIdMap = { [result.fragments.uuid]: [result.itemId] };
    if (selectedMap) await fragments.resetHighlight(selectedMap);
    await fragments.highlight(HIGHLIGHT, map);
    selectedMap = map;
    // Properties
    const guids = await result.fragments.getGuidsByLocalIds([result.itemId]);
    const data = await result.fragments.getItemsData([result.itemId], { attributesDefault: true });
    const attr = data[0]?.attributes ?? [];
    const p: Record<string, string> = { expressId: String(result.itemId) };
    for (const a of attr) if (['Name','ObjectType','GlobalId','Description','Tag'].includes(a.name)) p[a.name] = String(a.value);
    p.guid = guids[0] ?? '—';
    propsDiv.innerHTML = '<div class="prop-group-title" style="font-size:10px;text-transform:uppercase;letter-spacing:0.08em;color:#64748b;margin-bottom:6px;">Selected Element</div>' +
      Object.entries(p).map(([k, v]) => `<div class="prop-row"><span class="prop-key">${esc(k)}</span><span class="prop-val">${esc(v)}</span></div>`).join('');
    // Highlight tree item
    highlightTreeItem(result.itemId);
  });
}

function clearSelection() {
  if (selectedMap) { fragments.resetHighlight(selectedMap); selectedMap = null; }
  propsDiv.innerHTML = '<div style="color:#475569;font-size:12px;text-align:center;padding:20px 0;">Click an element in the model to see its properties</div>';
}

// ── Model Tree ───────────────────────────────────────────────
async function buildTree(model: import('@thatopen/fragments').FragmentsModel) {
  const cats = await model.getItemsOfCategories(/./);
  let html = '<div class="tree-item" onclick="window.fitModel()"><span class="icon">🏗️</span><span class="label">' + esc(select.value.replace('.ifc','')) + '</span><span class="count">' + (await model.getLocalIds()).length + '</span></div><div class="tree-children">';
  for (const [cat, ids] of Object.entries(cats) as [string, number[]][]) {
    const catLabel = cat.replace(/^Ifc/, '').replace(/([A-Z])/g, ' $1').trim();
    html += `<div class="tree-item" data-ids="${ids.join(',')}" onclick="selectIds(event,'${ids.join(',')}')"><span class="icon">📐</span><span class="label">${esc(catLabel)}</span><span class="count">${ids.length}</span></div>`;
  }
  html += '</div>';
  treeDiv.innerHTML = html;
  (window as any).fitModel = fitModel;
  (window as any).selectIds = selectIds;
}

function selectIds(event: MouseEvent, idsStr: string) {
  if (!currentModel) return;
  const ids = idsStr.split(',').map(Number);
  const map: OBC.ModelIdMap = { [currentModel.uuid]: ids };
  if (selectedMap) fragments.resetHighlight(selectedMap);
  fragments.highlight(HIGHLIGHT, map);
  selectedMap = map;
  propsDiv.innerHTML = `<div class="prop-group-title" style="font-size:10px;text-transform:uppercase;color:#64748b;">${ids.length} elements selected</div>`;
  // Highlight the tree item
  const items = treeDiv.querySelectorAll('.tree-item');
  items.forEach(i => i.classList.remove('selected'));
  (event.currentTarget as HTMLElement).classList.add('selected');
}

function highlightTreeItem(itemId: number) {
  const items = treeDiv.querySelectorAll('.tree-item');
  items.forEach(i => {
    i.classList.remove('selected');
    const ids = (i as HTMLElement).dataset.ids;
    if (ids && ids.split(',').map(Number).includes(itemId)) i.classList.add('selected');
  });
}

// ── Hide / Isolate / Show All ────────────────────────────────
async function hideSelected() {
  if (!selectedMap || !currentModel) return;
  const ids = [...selectedMap.values()].flat();
  await currentModel.setVisible(ids, false);
  clearSelection();
}

async function isolateSelected() {
  if (!selectedMap || !currentModel) return;
  const ids = [...selectedMap.values()].flat();
  const allIds = await currentModel.getLocalIds();
  await currentModel.setVisible(allIds, false);
  await currentModel.setVisible(ids, true);
  clearSelection();
}

async function showAll() {
  if (!currentModel) return;
  await currentModel.resetVisible();
  clearSelection();
}

// ── Section Plane ────────────────────────────────────────────
function toggleSection() {
  sectionMode = !sectionMode;
  btnSection.classList.toggle('active', sectionMode);
  sectionBar.style.display = sectionMode ? 'flex' : 'none';
  const r = world.renderer!.three as THREE.WebGLRenderer;
  if (sectionMode) {
    r.clippingPlanes = [sectionPlane];
    if (!sectionHelper) {
      sectionHelper = new THREE.PlaneHelper(sectionPlane, 20, 0xfbbf24);
      world.scene.three.add(sectionHelper);
    }
    sectionHelper.visible = true;
  } else {
    r.clippingPlanes = [];
    if (sectionHelper) sectionHelper.visible = false;
  }
}

function updateSection(val: number) {
  sectionPlane.setConstant(val);
  sectionLabel.textContent = `${val.toFixed(1)} m`;
}

// ── Fit view ─────────────────────────────────────────────────
function fitModel() {
  const box = new THREE.Box3();
  for (const [, model] of fragments.list) box.expandByObject(model.object);
  if (!box.isEmpty()) {
    const c = box.getCenter(new THREE.Vector3());
    const s = box.getSize(new THREE.Vector3());
    const d = Math.max(s.x, s.y, s.z, 0.1);
    world.camera?.controls?.setLookAt(c.x + d, c.y + d * 0.7, c.z + d, c.x, c.y, c.z);
  }
}

function esc(s: string) { const d = document.createElement('div'); d.textContent = s ?? ''; return d.innerHTML; }