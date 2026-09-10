import { callJsonApi } from "/js/api.js";
import { frontendNotification } from "/js/shortcuts.js";

const escape = (value) => String(value ?? "").replace(/[&<>\"]/g, (ch) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;"})[ch]);

function nodeTree(nodes) {
  const byParent = new Map();
  for (const node of nodes) {
    const key = node.parent_id || "root";
    byParent.set(key, [...(byParent.get(key) || []), node]);
  }
  return byParent;
}

function progress(metric) {
  if (metric.current_value == null || metric.target == null || metric.baseline == null) return "Chưa đo";
  const distance = Number(metric.target) - Number(metric.baseline);
  if (!distance) return "100%";
  return `${Math.max(0, Math.min(100, Math.round(((Number(metric.current_value) - Number(metric.baseline)) / distance) * 100)))}%`;
}

function mount() {
  if (document.getElementById("strategy-surface")) return;
  const surface=document.createElement("section");
  surface.id="strategy-surface";
  surface.hidden=true;
  surface.innerHTML=`
    <style>
      #strategy-surface{position:absolute;inset:0;z-index:30;background:var(--color-background);overflow:auto;color:var(--color-text)}
      #strategy-surface .strategy-wrap{max-width:1320px;margin:0 auto;padding:26px 32px 56px}
      #strategy-surface .strategy-head{display:flex;gap:16px;align-items:center;justify-content:space-between;border-bottom:1px solid var(--color-border);padding:4px 0 20px}
      #strategy-surface h1{font-size:24px;margin:0;font-weight:650}.strategy-sub{margin:4px 0 0;opacity:.7;font-size:14px}
      #strategy-surface select,#strategy-surface input,#strategy-surface textarea{background:var(--color-panel);border:1px solid var(--color-border);color:inherit;border-radius:4px;padding:8px 10px}
      #strategy-surface button{background:transparent;color:inherit;border:1px solid var(--color-border);border-radius:4px;padding:8px 11px;cursor:pointer}
      #strategy-surface button:hover{background:var(--color-background-hover)}.strategy-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .strategy-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.strategy-kpi{border:1px solid var(--color-border);padding:14px}.strategy-kpi b{display:block;font-size:24px;margin-top:5px}.strategy-kpi small{opacity:.7}
      .strategy-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:18px}.strategy-panel{border:1px solid var(--color-border);background:var(--color-panel)}.strategy-panel h2{margin:0;padding:14px 16px;border-bottom:1px solid var(--color-border);font-size:16px}.strategy-body{padding:10px 16px}
      .strategy-row{padding:12px 0;border-bottom:1px solid var(--color-border)}.strategy-row:last-child{border:0}.strategy-row strong{display:block;font-size:14px}.strategy-meta{font-size:12px;opacity:.7;margin-top:4px}.strategy-bar{height:5px;background:var(--color-background-hover);margin-top:9px}.strategy-bar i{display:block;height:100%;background:var(--color-primary);max-width:100%}
      .strategy-map{padding:20px 16px;min-height:340px}.strategy-branch{margin-left:20px;border-left:1px solid var(--color-border);padding-left:14px}.strategy-node{padding:8px 0;display:flex;align-items:center;gap:8px}.strategy-kind{font-size:11px;text-transform:uppercase;opacity:.65;min-width:76px}.strategy-dot{height:8px;width:8px;border-radius:50%;background:var(--color-primary);flex:0 0 auto}.strategy-project{display:grid;grid-template-columns:1.4fr repeat(3,.6fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--color-border);font-size:13px}.strategy-note{padding:18px 16px;opacity:.72;font-size:14px}.strategy-error{color:#d64a42;padding:12px 0}
      #strategy-surface .strategy-dialog[hidden]{display:none}#strategy-surface .strategy-dialog{position:fixed;inset:0;z-index:1;display:grid;place-items:center;padding:20px;background:color-mix(in srgb,var(--color-background) 78%,transparent)}#strategy-surface .strategy-dialog-panel{width:min(540px,100%);padding:20px;border:1px solid var(--color-border);border-radius:6px;background:var(--color-panel);box-shadow:0 18px 44px rgba(0,0,0,.2)}#strategy-surface .strategy-dialog-panel h2{font-size:18px;margin:0 0 16px}#strategy-surface .strategy-form-grid{display:grid;gap:12px}#strategy-surface .strategy-form-grid label{display:grid;gap:5px;font-size:13px}#strategy-surface .strategy-form-grid textarea{min-height:74px;resize:vertical;font:inherit}.strategy-form-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:18px}.strategy-form-hint{font-size:12px;opacity:.7;margin:0}.strategy-form-error{font-size:13px;color:#d64a42;margin:0}
      @media(max-width:800px){#strategy-surface .strategy-wrap{padding:18px}.strategy-head{align-items:flex-start;flex-direction:column}.strategy-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.strategy-grid{grid-template-columns:1fr}.strategy-project{grid-template-columns:1fr 1fr}}
    </style>
    <div class="strategy-wrap"><header class="strategy-head"><div><h1 id="strategy-title">Chiến lược</h1><p class="strategy-sub" id="strategy-subtitle">Kết quả và thực thi được quản lý ở hai lớp riêng.</p></div><div class="strategy-controls"><select id="strategy-view"><option value="dashboard">Dashboard</option><option value="map">Map</option><option value="cascade">Cascade</option></select><select id="strategy-filter"><option value="">Tất cả trạng thái</option><option value="on_track">Đúng hướng</option><option value="at_risk">Cần chú ý</option><option value="draft">Bản nháp</option></select><button type="button" id="strategy-create" title="Tạo mục tiêu"><x-icon name="add"></x-icon></button><button type="button" id="strategy-sync" title="Đồng bộ Plane"><x-icon name="sync"></x-icon></button><button type="button" id="strategy-close" title="Quay lại chat"><x-icon name="close"></x-icon></button></div></header><div id="strategy-content" class="strategy-note">Đang tải...</div></div>
    <div id="strategy-create-dialog" class="strategy-dialog" hidden><form id="strategy-create-form" class="strategy-dialog-panel"><h2>Tạo mục tiêu chiến lược</h2><div class="strategy-form-grid"><label>Loại<select id="strategy-node-kind" required><option value="north_star">North Star</option><option value="pillar">Pillar</option><option value="objective">Objective</option><option value="key_result">Key Result</option><option value="initiative">Initiative</option></select></label><label>Tiêu đề<input id="strategy-node-title" required maxlength="240" autocomplete="off"></label><label>Thuộc nhánh<select id="strategy-node-parent"><option value="">Không có cha</option></select></label><label id="strategy-project-field">Plane project<select id="strategy-node-project"><option value="">Kế thừa từ nhánh cha</option></select></label><label>Trạng thái<select id="strategy-node-lifecycle"><option value="draft">Bản nháp</option><option value="on_track">Đúng hướng</option><option value="at_risk">Cần chú ý</option></select></label><label>Mô tả<textarea id="strategy-node-description"></textarea></label><p id="strategy-form-hint" class="strategy-form-hint"></p><p id="strategy-form-error" class="strategy-form-error" hidden></p></div><div class="strategy-form-actions"><button type="button" id="strategy-create-cancel">Hủy</button><button type="submit">Tạo</button></div></form></div>`;
  document.querySelector("#right-panel")?.append(surface);
  const state={mode:"strategy",view:"dashboard",filter:"",data:null};
  const content=surface.querySelector("#strategy-content");
  const createDialog=surface.querySelector("#strategy-create-dialog");
  const formError=surface.querySelector("#strategy-form-error");
  const nodeKind=surface.querySelector("#strategy-node-kind");
  const nodeParent=surface.querySelector("#strategy-node-parent");
  const nodeProject=surface.querySelector("#strategy-node-project");
  const projectField=surface.querySelector("#strategy-project-field");
  const formHint=surface.querySelector("#strategy-form-hint");
  const notify=(type,message)=>frontendNotification({type,message,frontendOnly:true});
  const refreshCreateForm=()=>{
    const data=state.data || {nodes:[],plane_objects:[]};
    const kind=nodeKind.value;
    const needsProject=["objective","initiative"].includes(kind);
    nodeParent.innerHTML=`<option value="">Không có cha</option>${data.nodes.map((node)=>`<option value="${escape(node.id)}">${escape(node.title)} (${escape(node.kind)})</option>`).join("")}`;
    nodeProject.innerHTML=`<option value="">Kế thừa từ nhánh cha</option>${data.plane_objects.filter((item)=>item.kind==="project").map((project)=>`<option value="${escape(project.remote_id)}">${escape(project.title)}</option>`).join("")}`;
    projectField.hidden=!needsProject;
    formHint.textContent=needsProject && !data.plane_objects.some((item)=>item.kind==="project") ? "Đồng bộ Plane trước để chọn project thực thi cho Objective hoặc Initiative." : needsProject ? "Project được kế thừa từ nhánh cha nếu không chọn tại đây." : "North Star, Pillar và Key Result không tạo work item Plane.";
  };
  const render=()=>{
    const data=state.data || {nodes:[],metrics:[],plane_objects:[],work_item_states:{},sync:{}};
    const nodes=state.filter ? data.nodes.filter((node)=>node.lifecycle===state.filter) : data.nodes;
    const projects=data.plane_objects.filter((item)=>item.kind==="project");
    const work=data.plane_objects.filter((item)=>item.kind==="work_item");
    document.querySelector("#strategy-title").textContent=state.mode==="strategy"?"Chiến lược":"Công việc dự án";
    document.querySelector("#strategy-subtitle").textContent=state.mode==="strategy"?"Kết quả đo lường không đồng nhất với tiến độ task từ Plane.":"Tổng quan theo project từ Plane; mở Plane khi cần xử lý task.";
    surface.querySelector("#strategy-create").hidden=state.mode!=="strategy";
    if (!nodes.length && !projects.length) { content.innerHTML=`<div class="strategy-note">Chưa có dữ liệu. Kết nối Plane trong môi trường runtime rồi chọn đồng bộ; các mục tiêu được tạo tại đây sẽ xuất hiện sau khi có dữ liệu thực.</div>`; return; }
    if (state.mode==="projects") {
      const rows=projects.map((project)=>{const items=work.filter((item)=>String(item.project_ref_id)===String(project.remote_id));const done=items.filter((item)=>["completed","done"].includes(item.state_group)).length;const pct=items.length?Math.round(done/items.length*100):null;return `<div class="strategy-project"><strong>${escape(project.title)}</strong><span>${items.length} work items</span><span>${pct==null?"Chưa có dữ liệu":pct+"% hoàn tất"}</span><a href="#" data-plane="${escape(project.remote_id)}">Mở Plane</a></div>`}).join("");
      content.innerHTML=`<div class="strategy-kpis"><div class="strategy-kpi"><small>Projects</small><b>${projects.length}</b></div><div class="strategy-kpi"><small>Work items</small><b>${work.length}</b></div><div class="strategy-kpi"><small>Modules</small><b>${data.plane_objects.filter(x=>x.kind==='module').length}</b></div><div class="strategy-kpi"><small>Cycles</small><b>${data.plane_objects.filter(x=>x.kind==='cycle').length}</b></div></div><div class="strategy-panel"><h2>${state.view==='map'?'Bản đồ project':'Tổng quan project'}</h2><div class="strategy-body">${rows||"Chưa có project đã đồng bộ."}</div></div>`;
      return;
    }
    const metrics=data.metrics.map((metric)=>`<div class="strategy-row"><strong>${escape(metric.name)}</strong><div class="strategy-meta">${escape(metric.unit)} · Check-in: ${metric.last_checkin_at||"chưa có"}</div><div class="strategy-bar"><i style="width:${progress(metric)}"></i></div><div class="strategy-meta">${progress(metric)}</div></div>`).join("");
    const tree=nodeTree(nodes); const draw=(parent,depth=0)=> (tree.get(parent)||[]).map((node)=>`<div class="strategy-branch" style="margin-left:${depth?14:0}px"><div class="strategy-node"><span class="strategy-dot"></span><span class="strategy-kind">${escape(node.kind)}</span><strong>${escape(node.title)}</strong><span class="strategy-meta">${escape(node.lifecycle)}</span></div>${draw(node.id,depth+1)}</div>`).join("");
    if(state.view==="dashboard") content.innerHTML=`<div class="strategy-kpis"><div class="strategy-kpi"><small>Mục tiêu</small><b>${nodes.filter(n=>n.kind==='objective').length}</b></div><div class="strategy-kpi"><small>Key Results</small><b>${nodes.filter(n=>n.kind==='key_result').length}</b></div><div class="strategy-kpi"><small>Cần chú ý</small><b>${nodes.filter(n=>n.lifecycle==='at_risk').length}</b></div><div class="strategy-kpi"><small>Đồng bộ chờ</small><b>${(data.sync.inbox_pending||0)+(data.sync.outbox_pending||0)}</b></div></div><div class="strategy-grid"><div class="strategy-panel"><h2>Mục tiêu theo dõi</h2><div class="strategy-body">${nodes.filter(n=>n.kind==='objective').map(n=>`<div class="strategy-row"><strong>${escape(n.title)}</strong><div class="strategy-meta">${escape(n.lifecycle)} · ${escape(n.owner_ref||'Chưa có owner')}</div></div>`).join("")||"<div class='strategy-note'>Chưa có Objective.</div>"}</div></div><div class="strategy-panel"><h2>Kết quả đo lường</h2><div class="strategy-body">${metrics||"<div class='strategy-note'>Chưa có Key Result được đo.</div>"}</div></div></div>`;
    else content.innerHTML=`<div class="strategy-panel"><h2>${state.view==='map'?'Bản đồ chiến lược':'Cascade mục tiêu'}</h2><div class="strategy-map">${draw('root')||"Chưa có nhánh chiến lược."}</div></div>`;
  };
  const load=async()=>{content.innerHTML='<div class="strategy-note">Đang tải...</div>';try{state.data=(await callJsonApi('/api/strategy',{action:'dashboard',filters:state.filter?{lifecycle:state.filter}:{}})).data;render()}catch(error){console.error('Strategy dashboard load failed',error);content.innerHTML='<div class="strategy-error">Không thể tải dữ liệu chiến lược. Hãy thử lại sau.</div>'}};
  surface.querySelector('#strategy-view').addEventListener('change',(event)=>{state.view=event.target.value;render()});
  surface.querySelector('#strategy-filter').addEventListener('change',(event)=>{state.filter=event.target.value;load()});
  surface.querySelector('#strategy-close').addEventListener('click',()=>{surface.hidden=true});
  surface.querySelector('#strategy-sync').addEventListener('click',async()=>{try{await callJsonApi('/api/strategy',{action:'sync'});await load();notify('success','Đã yêu cầu đồng bộ Plane.')}catch(error){console.error('Plane sync failed',error);notify('error','Không thể đồng bộ Plane.')}});
  surface.querySelector('#strategy-create').addEventListener('click',()=>{formError.hidden=true;refreshCreateForm();createDialog.hidden=false;surface.querySelector('#strategy-node-title').focus()});
  surface.querySelector('#strategy-create-cancel').addEventListener('click',()=>{createDialog.hidden=true});
  nodeKind.addEventListener('change',refreshCreateForm);
  surface.querySelector('#strategy-create-form').addEventListener('submit',async(event)=>{event.preventDefault();formError.hidden=true;const node={kind:nodeKind.value,title:surface.querySelector('#strategy-node-title').value.trim(),parent_id:nodeParent.value||null,plane_project_ref_id:nodeProject.value||null,lifecycle:surface.querySelector('#strategy-node-lifecycle').value,description:surface.querySelector('#strategy-node-description').value.trim()};try{await callJsonApi('/api/strategy',{action:'create_node',node});createDialog.hidden=true;event.currentTarget.reset();await load();notify('success','Đã tạo mục tiêu.')}catch(error){console.error('Strategy node create failed',error);formError.textContent=error?.message||'Không thể tạo mục tiêu.';formError.hidden=false;}});
  globalThis.DarkOfficeStrategy={open:async(mode)=>{state.mode=mode;surface.hidden=false;await load()}};
}

export default async function initStrategySurface() { mount(); }
