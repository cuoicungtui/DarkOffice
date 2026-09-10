import { callJsonApi } from "/js/api.js";

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
      #strategy-surface select,#strategy-surface input{background:var(--color-panel);border:1px solid var(--color-border);color:inherit;border-radius:4px;padding:8px 10px}
      #strategy-surface button{background:transparent;color:inherit;border:1px solid var(--color-border);border-radius:4px;padding:8px 11px;cursor:pointer}
      #strategy-surface button:hover{background:var(--color-background-hover)}.strategy-controls{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
      .strategy-kpis{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin:22px 0}.strategy-kpi{border:1px solid var(--color-border);padding:14px}.strategy-kpi b{display:block;font-size:24px;margin-top:5px}.strategy-kpi small{opacity:.7}
      .strategy-grid{display:grid;grid-template-columns:minmax(0,2fr) minmax(280px,1fr);gap:18px}.strategy-panel{border:1px solid var(--color-border);background:var(--color-panel)}.strategy-panel h2{margin:0;padding:14px 16px;border-bottom:1px solid var(--color-border);font-size:16px}.strategy-body{padding:10px 16px}
      .strategy-row{padding:12px 0;border-bottom:1px solid var(--color-border)}.strategy-row:last-child{border:0}.strategy-row strong{display:block;font-size:14px}.strategy-meta{font-size:12px;opacity:.7;margin-top:4px}.strategy-bar{height:5px;background:var(--color-background-hover);margin-top:9px}.strategy-bar i{display:block;height:100%;background:var(--color-primary);max-width:100%}
      .strategy-map{padding:20px 16px;min-height:340px}.strategy-branch{margin-left:20px;border-left:1px solid var(--color-border);padding-left:14px}.strategy-node{padding:8px 0;display:flex;align-items:center;gap:8px}.strategy-kind{font-size:11px;text-transform:uppercase;opacity:.65;min-width:76px}.strategy-dot{height:8px;width:8px;border-radius:50%;background:var(--color-primary);flex:0 0 auto}.strategy-project{display:grid;grid-template-columns:1.4fr repeat(3,.6fr);gap:10px;padding:11px 0;border-bottom:1px solid var(--color-border);font-size:13px}.strategy-note{padding:18px 16px;opacity:.72;font-size:14px}.strategy-error{color:#d64a42;padding:12px 0}
      @media(max-width:800px){#strategy-surface .strategy-wrap{padding:18px}.strategy-head{align-items:flex-start;flex-direction:column}.strategy-kpis{grid-template-columns:repeat(2,minmax(0,1fr))}.strategy-grid{grid-template-columns:1fr}.strategy-project{grid-template-columns:1fr 1fr}}
    </style>
    <div class="strategy-wrap"><header class="strategy-head"><div><h1 id="strategy-title">Chiến lược</h1><p class="strategy-sub" id="strategy-subtitle">Kết quả và thực thi được quản lý ở hai lớp riêng.</p></div><div class="strategy-controls"><select id="strategy-view"><option value="dashboard">Dashboard</option><option value="map">Map</option><option value="cascade">Cascade</option></select><select id="strategy-filter"><option value="">Tất cả trạng thái</option><option value="on_track">Đúng hướng</option><option value="at_risk">Cần chú ý</option><option value="draft">Bản nháp</option></select><button type="button" id="strategy-sync" title="Đồng bộ Plane"><x-icon name="sync"></x-icon></button><button type="button" id="strategy-close" title="Quay lại chat"><x-icon name="close"></x-icon></button></div></header><div id="strategy-content" class="strategy-note">Đang tải...</div></div>`;
  document.querySelector("#right-panel")?.append(surface);
  const state={mode:"strategy",view:"dashboard",filter:"",data:null};
  const content=surface.querySelector("#strategy-content");
  const render=()=>{
    const data=state.data || {nodes:[],metrics:[],plane_objects:[],work_item_states:{},sync:{}};
    const nodes=state.filter ? data.nodes.filter((node)=>node.lifecycle===state.filter) : data.nodes;
    const projects=data.plane_objects.filter((item)=>item.kind==="project");
    const work=data.plane_objects.filter((item)=>item.kind==="work_item");
    document.querySelector("#strategy-title").textContent=state.mode==="strategy"?"Chiến lược":"Công việc dự án";
    document.querySelector("#strategy-subtitle").textContent=state.mode==="strategy"?"Kết quả đo lường không đồng nhất với tiến độ task từ Plane.":"Tổng quan theo project từ Plane; mở Plane khi cần xử lý task.";
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
  const load=async()=>{content.innerHTML='<div class="strategy-note">Đang tải...</div>';try{state.data=(await callJsonApi('/api/strategy',{action:'dashboard',filters:state.filter?{lifecycle:state.filter}:{}})).data;render()}catch(error){content.innerHTML=`<div class="strategy-error">${escape(error.message)}</div>`}};
  surface.querySelector('#strategy-view').addEventListener('change',(event)=>{state.view=event.target.value;render()});
  surface.querySelector('#strategy-filter').addEventListener('change',(event)=>{state.filter=event.target.value;load()});
  surface.querySelector('#strategy-close').addEventListener('click',()=>{surface.hidden=true});
  surface.querySelector('#strategy-sync').addEventListener('click',async()=>{await callJsonApi('/api/strategy',{action:'sync'});await load()});
  globalThis.DarkOfficeStrategy={open:async(mode)=>{state.mode=mode;surface.hidden=false;await load()}};
}

export default async function initStrategySurface() { mount(); }
