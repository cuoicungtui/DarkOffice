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
function projectProgress(items) {
  const parentIds = new Set(items.map(workParent).filter(Boolean));
  const leaves = items.filter((item) => !parentIds.has(item.remote_id) && item.state_group !== "cancelled");
  const completed = leaves.filter((item) => ["completed", "done"].includes(item.state_group)).length;
  return {total:leaves.length, completed, percent:leaves.length ? Math.round(completed * 100 / leaves.length) : null};
}
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
    #strategy-surface{position:absolute;inset:0;z-index:30;overflow:auto;background:var(--color-background);color:var(--color-text)}#strategy-surface .wrap{max-width:1320px;margin:auto;padding:26px 32px 56px}#strategy-surface .head{display:flex;justify-content:space-between;gap:16px;align-items:center;padding-bottom:20px;border-bottom:1px solid var(--color-border)}#strategy-surface h1{font-size:24px;margin:0}#strategy-surface .sub{margin:4px 0 0;opacity:.7;font-size:14px}#strategy-surface .controls{display:flex;gap:8px;flex-wrap:wrap}#strategy-surface select,#strategy-surface button{background:var(--color-panel);border:1px solid var(--color-border);color:inherit;border-radius:4px;padding:8px 10px}#strategy-surface .kpis{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:22px 0}#strategy-surface .kpi,#strategy-surface .panel{border:1px solid var(--color-border);background:var(--color-panel)}#strategy-surface .panel{display:block;flex:none;min-width:0;width:100%;box-sizing:border-box}#strategy-surface .kpi{padding:14px}#strategy-surface .kpi b{display:block;font-size:24px}#strategy-surface .panel h2{font-size:16px;margin:0;padding:14px 16px;border-bottom:1px solid var(--color-border)}#strategy-surface .empty{padding:18px;opacity:.7}#strategy-surface .strategy-summary-header{display:flex;justify-content:space-between;gap:20px;align-items:center;padding:16px;border-bottom:1px solid var(--color-border);background:color-mix(in srgb,var(--color-primary) 6%,var(--color-panel))}#strategy-surface .strategy-summary-header small,#strategy-surface .strategy-summary-row small{display:block;font-size:12px;opacity:.68}#strategy-surface .strategy-summary-header h2{border:0;padding:2px 0 0}#strategy-surface .strategy-summary-source{font-size:12px;opacity:.72;text-align:right}#strategy-surface .strategy-summary-row{display:grid;grid-template-columns:minmax(230px,1.45fr) minmax(190px,1.1fr) minmax(110px,.55fr) minmax(130px,.6fr);gap:18px;align-items:center;padding:15px 16px;border-bottom:1px solid var(--color-border);font-size:13px}#strategy-surface .strategy-summary-row:last-child{border-bottom:0}#strategy-surface .strategy-summary-row strong{display:block;font-size:14px;line-height:1.35}#strategy-surface .strategy-summary-progress{display:grid;gap:3px}#strategy-surface .strategy-summary-progress b{font-size:18px;color:var(--color-primary)}#strategy-surface .strategy-summary-progress b.no-data{font-size:13px;color:inherit}#strategy-surface .strategy-summary-count{font-size:13px;white-space:nowrap}#strategy-surface .map-scroll{padding:20px;overflow:auto;background:#f6f9fc}#strategy-surface .strategy-map{position:relative;min-width:860px;padding:6px 14px 28px}#strategy-surface .map-links{position:absolute;inset:0;z-index:0;overflow:visible;pointer-events:none}#strategy-surface .map-links path{fill:none;stroke:#8ca4bd;stroke-width:1.25}#strategy-surface .map{position:relative;z-index:1;display:grid;gap:28px}#strategy-surface .map-row>p{margin:0 0 10px;font-size:11px;letter-spacing:.04em;text-transform:uppercase;text-align:center;opacity:.65}#strategy-surface .map-cards{display:flex;justify-content:center;align-items:stretch;gap:22px;min-width:max-content}#strategy-surface .card{width:212px;box-sizing:border-box;border:1px solid #d6dee7;border-top:3px solid var(--color-primary);border-radius:4px;padding:11px 12px;min-height:90px;background:var(--color-panel);box-shadow:0 3px 8px rgb(25 52 80 / .12)}#strategy-surface .card.risk{border-top-color:#ca7a13}#strategy-surface .card.done{border-top-color:#1a9b60}#strategy-surface .card-meta{display:flex;align-items:center;gap:6px}#strategy-surface .card small,#strategy-surface .card strong,#strategy-surface .card span{display:block}#strategy-surface .card strong{font-size:13px;line-height:1.35;margin:8px 0 7px}#strategy-surface .card small,#strategy-surface .card span,#strategy-surface .branch small,#strategy-surface .branch em{font-size:11px;opacity:.68}#strategy-surface .card span{font-weight:600}#strategy-surface .cascade{padding:8px 16px 16px}#strategy-surface .branch{border-left:1px solid var(--color-border);margin-left:2px;padding-left:12px}#strategy-surface .branch summary{display:flex;gap:9px;align-items:center;padding:10px 0;cursor:pointer;list-style:none}#strategy-surface .branch summary:before{content:"›";font-size:18px;width:12px}#strategy-surface .branch[open]>summary:before{transform:rotate(90deg)}#strategy-surface .branch.leaf summary{cursor:default}#strategy-surface .branch.leaf summary:before{content:""}#strategy-surface .branch small{min-width:115px;text-transform:uppercase}#strategy-surface .branch strong{font-size:14px}#strategy-surface .branch em{margin-left:auto;font-style:normal;white-space:nowrap}#strategy-surface .nested{margin-left:12px}#strategy-surface .dot{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--color-primary);flex:0 0 auto}#strategy-surface .dot.risk{background:#ca7a13}#strategy-surface .dot.done{background:#1a9b60}#strategy-surface .project-row{padding:12px 16px;border-bottom:1px solid var(--color-border)}#strategy-surface .project-grid{display:grid;grid-template-columns:minmax(220px,1.5fr) minmax(180px,1fr) minmax(130px,.65fr) minmax(130px,.65fr);gap:12px;align-items:center;font-size:13px}#strategy-surface .project-block{border-bottom:1px solid var(--color-border)}#strategy-surface .project-block h3{font-size:14px;margin:16px}#strategy-surface .row{padding:12px 0;border-bottom:1px solid var(--color-border)}#strategy-surface .row strong{display:block}#strategy-surface .meta{font-size:12px;opacity:.7;margin-top:4px}#strategy-create-dialog[hidden]{display:none}#strategy-create-dialog{position:fixed;inset:0;z-index:2;display:grid;place-items:center;padding:20px;background:rgb(0 0 0 / .28)}#strategy-surface .strategy-dialog-panel{display:grid;gap:12px;width:min(540px,100%);padding:20px;border:1px solid var(--color-border);border-radius:6px;background:var(--color-panel);box-shadow:0 18px 44px rgb(0 0 0 / .2)}#strategy-surface .strategy-dialog-panel h2{margin:0;font-size:18px}#strategy-surface .strategy-dialog-panel label{display:grid;gap:5px;font-size:13px}#strategy-surface .strategy-dialog-panel input,#strategy-surface .strategy-dialog-panel textarea{width:100%;box-sizing:border-box;padding:8px 10px;border:1px solid var(--color-border);border-radius:4px;background:var(--color-background);color:inherit;font:inherit}#strategy-surface .strategy-dialog-panel textarea{min-height:72px;resize:vertical}#strategy-surface .strategy-dialog-panel p{margin:0;font-size:12px;opacity:.72}#strategy-surface .strategy-dialog-panel #strategy-form-error{color:#d64a42;opacity:1}#strategy-surface .form-actions{display:flex;justify-content:flex-end;gap:8px}@media(max-width:800px){#strategy-surface .wrap{padding:18px}#strategy-surface .head{align-items:flex-start;flex-direction:column}#strategy-surface .kpis{grid-template-columns:1fr}#strategy-surface .strategy-summary-header{align-items:flex-start;flex-direction:column}#strategy-surface .strategy-summary-source{text-align:left}#strategy-surface .strategy-summary-row,#strategy-surface .project-grid{grid-template-columns:1fr 1fr;gap:12px}#strategy-surface .strategy-map{min-width:700px}#strategy-surface .card{width:185px}#strategy-surface .map-cards{gap:14px}}@media(max-width:520px){#strategy-surface .strategy-summary-row,#strategy-surface .project-grid{grid-template-columns:1fr}#strategy-surface .strategy-summary-count{white-space:normal}}
  </style><div class="wrap"><header class="head"><div><h1 id="title">Chiến lược</h1><p id="subtitle" class="sub">Mục tiêu được đo bằng tiến độ dự án thực thi trên Plane.</p></div><div class="controls"><select id="view"><option value="dashboard">Bảng điều khiển</option><option value="map">Bản đồ</option><option value="cascade">Phân cấp</option></select><button id="sync" title="Đồng bộ Plane"><x-icon name="sync"></x-icon></button><button id="close" title="Quay lại chat"><x-icon name="close"></x-icon></button></div></header><div id="content" class="empty">Đang tải...</div></div>`;
  document.querySelector("#right-panel")?.append(surface);
  surface.querySelector("style").textContent += "#strategy-surface .strategy-summary-row{grid-template-columns:minmax(230px,1.45fr) minmax(190px,1.1fr) minmax(110px,.55fr) minmax(130px,.6fr) 38px}#strategy-surface .strategy-project-link{width:36px;height:36px;padding:0;display:grid;place-items:center}#strategy-create-dialog[hidden],#strategy-project-link-dialog[hidden]{display:none}#strategy-create-dialog,#strategy-project-link-dialog{position:fixed;inset:0;z-index:40;display:grid;place-items:center;padding:20px;overflow:auto;background:rgb(0 0 0 / .28)}#strategy-surface .strategy-dialog-panel{max-height:calc(100dvh - 40px);overflow:auto}#strategy-surface .strategy-dialog-panel #strategy-project-link-error{color:#d64a42;opacity:1}";
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
  const projectLinkDialog = document.createElement("div");
  projectLinkDialog.id = "strategy-project-link-dialog";
  projectLinkDialog.hidden = true;
  projectLinkDialog.innerHTML = `<form id="strategy-project-link-form" class="strategy-dialog-panel"><h2>Liên kết dự án Plane</h2><p id="strategy-project-link-title"></p><label>Dự án Plane<select id="strategy-project-link-select" required></select></label><p id="strategy-project-link-error" hidden></p><div class="form-actions"><button type="button" id="strategy-project-link-cancel">Hủy</button><button type="submit">Lưu liên kết</button></div></form>`;
  surface.append(projectLinkDialog);
  const model = {mode:"strategy",view:"dashboard",data:null};
  let linkedObjective = null;
  const content = surface.querySelector("#content");
  const projectLinkSelect = surface.querySelector("#strategy-project-link-select"), projectLinkTitle = surface.querySelector("#strategy-project-link-title"), projectLinkError = surface.querySelector("#strategy-project-link-error");
  const nodeKind = surface.querySelector("#strategy-node-kind"), nodeParent = surface.querySelector("#strategy-node-parent"), nodeProject = surface.querySelector("#strategy-node-project"), projectField = surface.querySelector("#strategy-project-field"), formHint = surface.querySelector("#strategy-form-hint"), formError = surface.querySelector("#strategy-form-error");
  const refreshCreateForm = () => {
    const data = model.data || {nodes:[],plane_objects:[]};
    const needsProject = ["objective","initiative"].includes(nodeKind.value);
    const northStarExists = data.nodes.some((item) => item.kind === "north_star");
    const northStarOption = nodeKind.querySelector('option[value="north_star"]');
    northStarOption.disabled = northStarExists;
    if (northStarExists && nodeKind.value === "north_star") nodeKind.value = "pillar";
    nodeParent.innerHTML = `<option value="">Không có cha</option>${data.nodes.map((item) => `<option value="${esc(item.id)}">${esc(item.title)} (${esc(label(kind,item.kind))})</option>`).join("")}`;
    nodeProject.innerHTML = `<option value="">Chọn dự án Plane</option>${data.plane_objects.filter((item) => item.kind === "project").map((item) => `<option value="${esc(item.remote_id)}">${esc(item.title)}</option>`).join("")}`;
    projectField.hidden = !needsProject;
    formHint.textContent = nodeKind.value === "objective" ? "Mỗi mục tiêu phải có một dự án Plane riêng. Tiến độ dự án là tiến độ của mục tiêu." : needsProject ? "Chọn dự án Plane hoặc kế thừa dự án của mục tiêu cha." : northStarExists ? "Hệ thống chỉ có một Sao Bắc Cực." : "Loại này không tự tạo công việc Plane.";
  };
  const draw = () => {
    const data = model.data || {nodes:[],metrics:[],plane_objects:[],sync:{}};
    const nodes = data.nodes;
    const projects = data.plane_objects.filter((item) => item.kind === "project"), work = data.plane_objects.filter((item) => item.kind === "work_item");
    surface.querySelector("#title").textContent = model.mode === "strategy" ? "Chiến lược" : "Công việc dự án";
    surface.querySelector("#subtitle").textContent = model.mode === "strategy" ? "Mục tiêu được đo bằng tiến độ dự án thực thi trên Plane." : "Tổng quan theo dự án từ Plane; mở Plane khi cần xử lý công việc.";
    createButton.hidden = model.mode !== "strategy";
    if (model.mode === "strategy") {
      if (model.view === "map") { content.innerHTML = `<div class="panel"><h2>Bản đồ chiến lược</h2>${map(nodes,(item) => item.parent_id)}</div>`; requestAnimationFrame(() => drawMapLinks(content)); return; }
      if (model.view === "cascade") { content.innerHTML = `<div class="panel"><h2>Phân cấp mục tiêu</h2>${cascade(nodes,(item) => item.parent_id)}</div>`; return; }
      const objectives = nodes.filter((item) => item.kind === "objective");
      const projectsById = new Map(projects.map((item) => [String(item.remote_id),item]));
      const rows = objectives.map((objective) => {
        const project = projectsById.get(String(objective.plane_project_ref_id));
        const progress = project ? projectProgress(work.filter((item) => String(item.project_ref_id) === String(project.remote_id))) : {total:0,percent:null};
        return {objective,project,progress};
      });
      const known = rows.filter((row) => row.progress.percent !== null);
      const average = known.length ? Math.round(known.reduce((sum,row) => sum + row.progress.percent,0) / known.length) : null;
      const northStar = nodes.find((item) => item.kind === "north_star");
      content.innerHTML = `<div class="kpis"><div class="kpi"><small>Mục tiêu</small><b>${objectives.length}</b></div><div class="kpi"><small>Dự án liên kết</small><b>${new Set(rows.map((row) => row.objective.plane_project_ref_id).filter(Boolean)).size}</b></div><div class="kpi"><small>Tiến độ dự án</small><b>${average === null ? "-" : `${average}%`}</b></div></div><div class="panel"><div class="strategy-summary-header"><div><small>Sao Bắc Cực</small><h2>${northStar ? esc(northStar.title) : "Mục tiêu và dự án thực thi"}</h2></div><div class="strategy-summary-source">Tiến độ được tính từ công việc lá đã hoàn thành trên Plane.</div></div>${rows.map((row) => `<div class="strategy-summary-row"><div><strong>${esc(row.objective.title)}</strong><small>Mục tiêu</small></div><div><strong>${esc(row.project?.title || "Chưa liên kết dự án Plane")}</strong><small>Dự án thực thi</small></div><div class="strategy-summary-progress"><b class="${row.progress.percent === null ? "no-data" : ""}">${row.progress.percent === null ? "Chưa có dữ liệu" : `${row.progress.percent}%`}</b><small>Hoàn thành</small></div><div class="strategy-summary-count">${row.progress.total} công việc</div><button type="button" class="strategy-project-link" data-node-id="${esc(row.objective.id)}" title="Đổi dự án Plane"><x-icon name="link"></x-icon></button></div>`).join("") || "<p class='empty'>Chưa có mục tiêu liên kết dự án.</p>"}</div>`; return;
    }
    const projectTrees = projects.map((project) => {
      const items = work.filter((item) => String(item.project_ref_id) === String(project.remote_id));
      const root = {...project,remote_id:"project-" + project.remote_id,state_group:"",title:project.title};
      const combined = [root,...items], parentFor = (item) => item.remote_id === root.remote_id ? "" : workParent(item) || root.remote_id;
      if (model.view === "map") return `<section class="project-block"><h3>${esc(project.title)}</h3>${map(combined,parentFor,true)}</section>`;
      if (model.view === "cascade") return `<section class="project-block">${cascade(combined,parentFor,true)}</section>`;
      const progress = projectProgress(items);
      return `<div class="project-row project-grid"><strong>${esc(project.title)}</strong><span>${progress.total} công việc</span><span>${progress.percent === null ? "Chưa có dữ liệu" : `${progress.percent}% hoàn tất`}</span><span>${esc(project.synced_at || "Chưa đồng bộ")}</span></div>`;
    }).join("");
    const heading = model.view === "map" ? "Bản đồ công việc theo dự án" : model.view === "cascade" ? "Phân cấp công việc" : "Tổng quan theo dự án";
    content.innerHTML = `<div class="kpis"><div class="kpi"><small>Dự án</small><b>${projects.length}</b></div><div class="kpi"><small>Công việc</small><b>${work.length}</b></div><div class="kpi"><small>Nhóm công việc</small><b>${data.plane_objects.filter((item) => item.kind === "module").length}</b></div><div class="kpi"><small>Chu kỳ</small><b>${data.plane_objects.filter((item) => item.kind === "cycle").length}</b></div></div><div class="panel"><h2>${heading}</h2>${projectTrees || "<p class='empty'>Chưa có dự án đã đồng bộ.</p>"}</div>`;
    if (model.view === "map") requestAnimationFrame(() => drawMapLinks(content));
  };
  const load = async () => { content.innerHTML = "<p class='empty'>Đang tải...</p>"; try { model.data = (await callJsonApi("/api/strategy",{action:"dashboard"})).data; draw(); } catch (error) { console.error(error); content.innerHTML = "<p class='empty'>Không thể tải dữ liệu chiến lược.</p>"; } };
  surface.querySelector("#view").addEventListener("change",(event) => { model.view = event.target.value; draw(); });
  surface.querySelector("#close").addEventListener("click",() => { surface.hidden = true; });
  surface.querySelector("#sync").addEventListener("click",async () => { try { await callJsonApi("/api/strategy",{action:"sync"}); await load(); frontendNotification({type:"success",message:"Đã yêu cầu đồng bộ Plane.",frontendOnly:true}); } catch { frontendNotification({type:"error",message:"Không thể đồng bộ Plane.",frontendOnly:true}); } });
  createButton.addEventListener("click", () => { formError.hidden = true; refreshCreateForm(); createDialog.hidden = false; surface.querySelector("#strategy-node-title").focus(); });
  surface.querySelector("#strategy-create-cancel").addEventListener("click", () => { createDialog.hidden = true; });
  surface.querySelector("#strategy-project-link-cancel").addEventListener("click", () => { projectLinkDialog.hidden = true; });
  content.addEventListener("click", (event) => {
    const button = event.target.closest(".strategy-project-link");
    if (!button) return;
    linkedObjective = (model.data?.nodes || []).find((node) => node.id === button.dataset.nodeId) || null;
    if (!linkedObjective) return;
    const occupied = new Set((model.data?.nodes || []).filter((node) => node.kind === "objective" && node.id !== linkedObjective.id).map((node) => String(node.plane_project_ref_id)).filter(Boolean));
    const projects = (model.data?.plane_objects || []).filter((item) => item.kind === "project" && (!occupied.has(String(item.remote_id)) || String(item.remote_id) === String(linkedObjective.plane_project_ref_id)));
    projectLinkSelect.innerHTML = projects.map((item) => `<option value="${esc(item.remote_id)}">${esc(item.title)}</option>`).join("");
    projectLinkSelect.value = String(linkedObjective.plane_project_ref_id || "");
    projectLinkTitle.textContent = linkedObjective.title;
    projectLinkError.hidden = true;
    projectLinkDialog.hidden = false;
  });
  surface.querySelector("#strategy-project-link-form").addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!linkedObjective || !projectLinkSelect.value) return;
    projectLinkError.hidden = true;
    try {
      await callJsonApi("/api/strategy", {action:"update_node", id:linkedObjective.id, node:{plane_project_ref_id:projectLinkSelect.value,version:linkedObjective.version}});
      projectLinkDialog.hidden = true;
      await load();
      frontendNotification({type:"success",message:"Đã liên kết dự án Plane.",frontendOnly:true});
    } catch (error) {
      projectLinkError.textContent = error?.message || "Không thể lưu liên kết dự án.";
      projectLinkError.hidden = false;
    }
  });
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
