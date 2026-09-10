import { callJsonApi } from "/js/api.js";
import { frontendNotification } from "/js/shortcuts.js";

const esc = (v) => String(v ?? "").replace(/[&<>\"]/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[c]);
const kind = {north_star:"Sao Bắc Cực",pillar:"Trụ cột",objective:"Mục tiêu",key_result:"Kết quả then chốt",initiative:"Sáng kiến"};
const life = {active:"Đang thực hiện",at_risk:"Cần chú ý",complete:"Hoàn thành",draft:"Bản nháp",on_track:"Đúng hướng"};
const state = {backlog:"Tồn đọng",cancelled:"Đã hủy",completed:"Hoàn thành",done:"Hoàn thành",in_progress:"Đang thực hiện",started:"Đang thực hiện",todo:"Cần làm"};
const label = (set, value) => set[value] || value || "Chưa xác định";
const tone = (value) => value === "at_risk" ? "risk" : ["complete","completed","done"].includes(value) ? "done" : "";

function json(item) { try { return JSON.parse(item.raw_json || "{}"); } catch { return {}; } }
function workParent(item) { const parent = json(item).parent; return typeof parent === "string" ? parent : parent?.id || ""; }
function children(items, parentFor) {
  const ids = new Set(items.map((item) => item.remote_id || item.id));
  return items.reduce((map, item) => {
    const parent = parentFor(item);
    const key = parent && ids.has(parent) ? parent : "root";
    map.set(key, [...(map.get(key) || []), item]);
    return map;
  }, new Map());
}
function levels(items, parentFor) {
  const byParent = children(items, parentFor), result = [], seen = new Set();
  let current = byParent.get("root") || [];
  while (current.length) {
    current = current.filter((item) => !seen.has(item.remote_id || item.id) && seen.add(item.remote_id || item.id));
    if (!current.length) break;
    result.push(current);
    current = current.flatMap((item) => byParent.get(item.remote_id || item.id) || []);
  }
  return result;
}
function map(items, parentFor, project = false) {
  const rows = levels(items, parentFor);
  if (!rows.length) return "<p class='empty'>Chưa có dữ liệu để vẽ bản đồ.</p>";
  return `<div class="map-scroll"><div class="strategy-map"><svg class="map-links" aria-hidden="true"></svg><div class="map">${rows.map((row, level) => `<section class="map-row"><p>${level === 0 ? (project ? "Dự án" : "Mục tiêu định hướng") : `Tầng ${level + 1}`}</p><div class="map-cards">${row.map((item) => {
    const progress = project ? item.state_group : item.lifecycle;
    const id = item.remote_id || item.id;
    const parent = parentFor(item) || "";
    return `<article class="card ${tone(progress)}" data-map-node="${esc(id)}" data-map-parent="${esc(parent)}"><div class="card-meta"><i class="dot ${tone(progress)}"></i><small>${esc(project ? "Công việc" : label(kind,item.kind))}</small></div><strong>${esc(item.title)}</strong><span>${esc(project ? label(state,progress) : label(life,progress))}</span></article>`;
  }).join("")}</div></section>`).join("")}</div></div></div>`;
}

function drawMapLinks(root) {
  root.querySelectorAll(".strategy-map").forEach((stage) => {
    const svg = stage.querySelector(".map-links");
    const nodes = new Map([...stage.querySelectorAll("[data-map-node]")].map((node) => [node.dataset.mapNode, node]));
    const width = stage.scrollWidth, height = stage.scrollHeight;
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("width", width);
    svg.setAttribute("height", height);
    svg.innerHTML = [...nodes.values()].flatMap((child) => {
      const parent = nodes.get(child.dataset.mapParent);
      if (!parent) return [];
      const x1 = parent.offsetLeft + parent.offsetWidth / 2;
      const y1 = parent.offsetTop + parent.offsetHeight;
      const x2 = child.offsetLeft + child.offsetWidth / 2;
      const y2 = child.offsetTop;
      const middle = y1 + Math.max(20, (y2 - y1) / 2);
      return [`<path d="M ${x1} ${y1} V ${middle} H ${x2} V ${y2}" />`];
    }).join("");
  });
}
function branch(item, byParent, project = false) {
  const id = item.remote_id || item.id, nested = byParent.get(id) || [], progress = project ? item.state_group : item.lifecycle;
  return `<details class="branch ${nested.length ? "" : "leaf"}" ${nested.length ? "open" : ""}><summary><i class="dot ${tone(progress)}"></i><small>${esc(project ? "Công việc" : label(kind,item.kind))}</small><strong>${esc(item.title)}</strong><em>${esc(project ? label(state,progress) : label(life,progress))}</em></summary>${nested.length ? `<div class="nested">${nested.map((child) => branch(child,byParent,project)).join("")}</div>` : ""}</details>`;
}
function cascade(items, parentFor, project = false) {
  const byParent = children(items, parentFor), roots = byParent.get("root") || [];
  return roots.length ? `<div class="cascade">${roots.map((item) => branch(item,byParent,project)).join("")}</div>` : "<p class='empty'>Chưa có dữ liệu phân cấp.</p>";
}

function mount() {
  if (document.querySelector("#strategy-surface")) return;
  const surface = document.createElement("section");
  surface.id = "strategy-surface"; surface.hidden = true;
  surface.innerHTML = `<style>
    #strategy-surface{position:absolute;inset:0;z-index:30;overflow:auto;background:var(--color-background);color:var(--color-text)}.wrap{max-width:1320px;margin:auto;padding:26px 32px 56px}.head{display:flex;justify-content:space-between;gap:16px;align-items:center;padding-bottom:20px;border-bottom:1px solid var(--color-border)}h1{font-size:24px;margin:0}.sub{margin:4px 0 0;opacity:.7;font-size:14px}.controls{display:flex;gap:8px;flex-wrap:wrap}select,button{background:var(--color-panel);border:1px solid var(--color-border);color:inherit;border-radius:4px;padding:8px 10px}.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:22px 0}.kpi,.panel{border:1px solid var(--color-border);background:var(--color-panel)}.kpi{padding:14px}.kpi b{display:block;font-size:24px}.panel h2{font-size:16px;margin:0;padding:14px 16px;border-bottom:1px solid var(--color-border)}.empty{padding:18px;opacity:.7}.map-scroll{padding:20px;overflow:auto;background:#f6f9fc}.strategy-map{position:relative;min-width:860px;padding:6px 14px 28px}.map-links{position:absolute;inset:0;z-index:0;overflow:visible;pointer-events:none}.map-links path{fill:none;stroke:#8ca4bd;stroke-width:1.25}.map{position:relative;z-index:1;display:grid;gap:28px}.map-row>p{margin:0 0 10px;font-size:11px;letter-spacing:.04em;text-transform:uppercase;text-align:center;opacity:.65}.map-cards{display:flex;justify-content:center;align-items:stretch;gap:22px;min-width:max-content}.card{width:212px;box-sizing:border-box;border:1px solid #d6dee7;border-top:3px solid var(--color-primary);border-radius:4px;padding:11px 12px;min-height:90px;background:var(--color-panel);box-shadow:0 3px 8px rgb(25 52 80 / .12)}.card.risk{border-top-color:#ca7a13}.card.done{border-top-color:#1a9b60}.card-meta{display:flex;align-items:center;gap:6px}.card small,.card strong,.card span{display:block}.card strong{font-size:13px;line-height:1.35;margin:8px 0 7px}.card small,.card span,.branch small,.branch em{font-size:11px;opacity:.68}.card span{font-weight:600}.cascade{padding:8px 16px 16px}.branch{border-left:1px solid var(--color-border);margin-left:2px;padding-left:12px}.branch summary{display:flex;gap:9px;align-items:center;padding:10px 0;cursor:pointer;list-style:none}.branch summary:before{content:"›";font-size:18px;width:12px}.branch[open]>summary:before{transform:rotate(90deg)}.branch.leaf summary{cursor:default}.branch.leaf summary:before{content:""}.branch small{min-width:115px;text-transform:uppercase}.branch strong{font-size:14px}.branch em{margin-left:auto;font-style:normal;white-space:nowrap}.nested{margin-left:12px}.dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--color-primary);flex:0 0 auto}.dot.risk{background:#ca7a13}.dot.done{background:#1a9b60}.project{padding:12px 16px;border-bottom:1px solid var(--color-border)}.project-grid{display:grid;grid-template-columns:1.4fr repeat(3,.7fr);gap:10px;font-size:13px}.project-block{border-bottom:1px solid var(--color-border)}.project-block h3{font-size:14px;margin:16px}.row{padding:12px 0;border-bottom:1px solid var(--color-border)}.row strong{display:block}.meta{font-size:12px;opacity:.7;margin-top:4px}#strategy-create-dialog[hidden]{display:none}#strategy-create-dialog{position:fixed;inset:0;z-index:2;display:grid;place-items:center;padding:20px;background:rgb(0 0 0 / .28)}.strategy-dialog-panel{display:grid;gap:12px;width:min(540px,100%);padding:20px;border:1px solid var(--color-border);border-radius:6px;background:var(--color-panel);box-shadow:0 18px 44px rgb(0 0 0 / .2)}.strategy-dialog-panel h2{margin:0;font-size:18px}.strategy-dialog-panel label{display:grid;gap:5px;font-size:13px}.strategy-dialog-panel input,.strategy-dialog-panel textarea{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--color-border);border-radius:4px;background:var(--color-background);color:inherit;font:inherit}.strategy-dialog-panel textarea{min-height:72px;resize:vertical}.strategy-dialog-panel p{margin:0;font-size:12px;opacity:.72}.strategy-dialog-panel #strategy-form-error{color:#d64a42;opacity:1}.form-actions{display:flex;justify-content:flex-end;gap:8px}@media(max-width:800px){.wrap{padding:18px}.head{align-items:flex-start;flex-direction:column}.kpis{grid-template-columns:repeat(2,1fr)}.project-grid{grid-template-columns:1fr 1fr}.strategy-map{min-width:700px}.card{width:185px}.map-cards{gap:14px}}
  </style><div class="wrap"><header class="head"><div><h1 id="title">Chiến lược</h1><p id="subtitle" class="sub">Kết quả đo lường và thực thi được quản lý ở hai lớp riêng.</p></div><div class="controls"><select id="view"><option value="dashboard">Bảng điều khiển</option><option value="map">Bản đồ</option><option value="cascade">Phân cấp</option></select><select id="filter"><option value="">Tất cả trạng thái</option><option value="on_track">Đúng hướng</option><option value="at_risk">Cần chú ý</option><option value="draft">Bản nháp</option></select><button id="sync" title="Đồng bộ Plane"><x-icon name="sync"></x-icon></button><button id="close" title="Quay lại chat"><x-icon name="close"></x-icon></button></div></header><div id="content" class="empty">Đang tải...</div></div>`;
  document.querySelector("#right-panel")?.append(surface);
  const createButton = document.createElement("button");
  createButton.id = "strategy-create";
  createButton.type = "button";
  createButton.title = "Tạo mục tiêu";
  createButton.innerHTML = "<x-icon name=\"add\"></x-icon>";
  surface.querySelector(".controls")?.prepend(createButton);
  const createDialog = document.createElement("div");
  createDialog.id = "strategy-create-dialog";
  createDialog.hidden = true;
  createDialog.innerHTML = `<form id="strategy-create-form" class="strategy-dialog-panel"><h2>Tạo mục tiêu chiến lược</h2><label>Loại<select id="strategy-node-kind"><option value="north_star">Sao Bắc Cực</option><option value="pillar">Trụ cột</option><option value="objective">Mục tiêu</option><option value="key_result">Kết quả then chốt</option><option value="initiative">Sáng kiến</option></select></label><label>Tiêu đề<input id="strategy-node-title" required maxlength="240" autocomplete="off"></label><label>Thuộc nhánh<select id="strategy-node-parent"><option value="">Không có cha</option></select></label><label id="strategy-project-field">Dự án Plane<select id="strategy-node-project"><option value="">Kế thừa từ nhánh cha</option></select></label><label>Trạng thái<select id="strategy-node-lifecycle"><option value="draft">Bản nháp</option><option value="on_track">Đúng hướng</option><option value="at_risk">Cần chú ý</option></select></label><label>Mô tả<textarea id="strategy-node-description"></textarea></label><p id="strategy-form-hint"></p><p id="strategy-form-error" hidden></p><div class="form-actions"><button type="button" id="strategy-create-cancel">Hủy</button><button type="submit">Tạo</button></div></form>`;
  surface.append(createDialog);
  const model = {mode:"strategy",view:"dashboard",filter:"",data:null};
  const content = surface.querySelector("#content");
  const nodeKind = surface.querySelector("#strategy-node-kind"), nodeParent = surface.querySelector("#strategy-node-parent"), nodeProject = surface.querySelector("#strategy-node-project"), projectField = surface.querySelector("#strategy-project-field"), formHint = surface.querySelector("#strategy-form-hint"), formError = surface.querySelector("#strategy-form-error");
  const refreshCreateForm = () => {
    const data = model.data || {nodes:[],plane_objects:[]};
    const needsProject = ["objective","initiative"].includes(nodeKind.value);
    nodeParent.innerHTML = `<option value="">Không có cha</option>${data.nodes.map((item) => `<option value="${esc(item.id)}">${esc(item.title)} (${esc(label(kind,item.kind))})</option>`).join("")}`;
    nodeProject.innerHTML = `<option value="">Kế thừa từ nhánh cha</option>${data.plane_objects.filter((item) => item.kind === "project").map((item) => `<option value="${esc(item.remote_id)}">${esc(item.title)}</option>`).join("")}`;
    projectField.hidden = !needsProject;
    formHint.textContent = needsProject ? "Chọn dự án Plane hoặc kế thừa từ nhánh cha." : "Loại này không tự tạo công việc Plane.";
  };
  const draw = () => {
    const data = model.data || {nodes:[],metrics:[],plane_objects:[],sync:{}};
    const nodes = model.filter ? data.nodes.filter((item) => item.lifecycle === model.filter) : data.nodes;
    const projects = data.plane_objects.filter((item) => item.kind === "project"), work = data.plane_objects.filter((item) => item.kind === "work_item");
    surface.querySelector("#title").textContent = model.mode === "strategy" ? "Chiến lược" : "Công việc dự án";
    surface.querySelector("#subtitle").textContent = model.mode === "strategy" ? "Kết quả đo lường không đồng nhất với tiến độ công việc từ Plane." : "Tổng quan theo dự án từ Plane; mở Plane khi cần xử lý công việc.";
    createButton.hidden = model.mode !== "strategy";
    if (model.mode === "strategy") {
      if (model.view === "map") { content.innerHTML = `<div class="panel"><h2>Bản đồ chiến lược</h2>${map(nodes,(item) => item.parent_id)}</div>`; requestAnimationFrame(() => drawMapLinks(content)); return; }
      if (model.view === "cascade") { content.innerHTML = `<div class="panel"><h2>Phân cấp mục tiêu</h2>${cascade(nodes,(item) => item.parent_id)}</div>`; return; }
      const objectives = nodes.filter((item) => item.kind === "objective");
      content.innerHTML = `<div class="kpis"><div class="kpi"><small>Mục tiêu</small><b>${objectives.length}</b></div><div class="kpi"><small>Kết quả then chốt</small><b>${nodes.filter((item) => item.kind === "key_result").length}</b></div><div class="kpi"><small>Cần chú ý</small><b>${nodes.filter((item) => item.lifecycle === "at_risk").length}</b></div><div class="kpi"><small>Đồng bộ chờ</small><b>${(data.sync.inbox_pending || 0) + (data.sync.outbox_pending || 0)}</b></div></div><div class="panel"><h2>Mục tiêu cần theo dõi</h2>${objectives.map((item) => `<div class="project"><strong>${esc(item.title)}</strong><div class="meta">${esc(label(life,item.lifecycle))}</div></div>`).join("") || "<p class='empty'>Chưa có mục tiêu.</p>"}</div>`; return;
    }
    const projectTrees = projects.map((project) => {
      const items = work.filter((item) => String(item.project_ref_id) === String(project.remote_id));
      const root = {...project,remote_id:"project-" + project.remote_id,state_group:"",title:project.title};
      const combined = [root,...items], parentFor = (item) => item.remote_id === root.remote_id ? "" : workParent(item) || root.remote_id;
      if (model.view === "map") return `<section class="project-block"><h3>${esc(project.title)}</h3>${map(combined,parentFor,true)}</section>`;
      if (model.view === "cascade") return `<section class="project-block">${cascade(combined,parentFor,true)}</section>`;
      const completed = items.filter((item) => ["completed","done"].includes(item.state_group)).length;
      return `<div class="project project-grid"><strong>${esc(project.title)}</strong><span>${items.length} công việc</span><span>${items.length ? Math.round(completed * 100 / items.length) + "% hoàn tất" : "Chưa có dữ liệu"}</span><span>${esc(project.synced_at || "Chưa đồng bộ")}</span></div>`;
    }).join("");
    const heading = model.view === "map" ? "Bản đồ công việc theo dự án" : model.view === "cascade" ? "Phân cấp công việc" : "Tổng quan theo dự án";
    content.innerHTML = `<div class="kpis"><div class="kpi"><small>Dự án</small><b>${projects.length}</b></div><div class="kpi"><small>Công việc</small><b>${work.length}</b></div><div class="kpi"><small>Nhóm công việc</small><b>${data.plane_objects.filter((item) => item.kind === "module").length}</b></div><div class="kpi"><small>Chu kỳ</small><b>${data.plane_objects.filter((item) => item.kind === "cycle").length}</b></div></div><div class="panel"><h2>${heading}</h2>${projectTrees || "<p class='empty'>Chưa có dự án đã đồng bộ.</p>"}</div>`;
    if (model.view === "map") requestAnimationFrame(() => drawMapLinks(content));
  };
  const load = async () => { content.innerHTML = "<p class='empty'>Đang tải...</p>"; try { model.data = (await callJsonApi("/api/strategy",{action:"dashboard",filters:model.filter ? {lifecycle:model.filter} : {}})).data; draw(); } catch (error) { console.error(error); content.innerHTML = "<p class='empty'>Không thể tải dữ liệu chiến lược.</p>"; } };
  surface.querySelector("#view").addEventListener("change",(event) => { model.view = event.target.value; draw(); });
  surface.querySelector("#filter").addEventListener("change",(event) => { model.filter = event.target.value; load(); });
  surface.querySelector("#close").addEventListener("click",() => { surface.hidden = true; });
  surface.querySelector("#sync").addEventListener("click",async () => { try { await callJsonApi("/api/strategy",{action:"sync"}); await load(); frontendNotification({type:"success",message:"Đã yêu cầu đồng bộ Plane.",frontendOnly:true}); } catch { frontendNotification({type:"error",message:"Không thể đồng bộ Plane.",frontendOnly:true}); } });
  createButton.addEventListener("click", () => { formError.hidden = true; refreshCreateForm(); createDialog.hidden = false; surface.querySelector("#strategy-node-title").focus(); });
  surface.querySelector("#strategy-create-cancel").addEventListener("click", () => { createDialog.hidden = true; });
  nodeKind.addEventListener("change", refreshCreateForm);
  surface.querySelector("#strategy-create-form").addEventListener("submit", async (event) => {
    event.preventDefault(); formError.hidden = true;
    const node = {kind:nodeKind.value,title:surface.querySelector("#strategy-node-title").value.trim(),parent_id:nodeParent.value || null,plane_project_ref_id:nodeProject.value || null,lifecycle:surface.querySelector("#strategy-node-lifecycle").value,description:surface.querySelector("#strategy-node-description").value.trim()};
    try { await callJsonApi("/api/strategy",{action:"create_node",node}); createDialog.hidden = true; event.currentTarget.reset(); await load(); frontendNotification({type:"success",message:"Đã tạo mục tiêu.",frontendOnly:true}); }
    catch (error) { formError.textContent = error?.message || "Không thể tạo mục tiêu."; formError.hidden = false; }
  });
  globalThis.DarkOfficeStrategy = {open:async (mode) => { model.mode = mode; surface.hidden = false; await load(); }};
}
export default async function initStrategySurface() { mount(); }
