"""Observability-Dashboard (eigener Port, nur Präsentation).

Serviert eine Single-Page-Ansicht, die per SSE die Live-Trace-Events empfängt und
den Agenten-Flow als Flowchart zeichnet: Chat-Eingabe → Orchestrator →
(verzweigt zu) den aufgerufenen Spezial-Agents → Output. Über jeder Kachel steht
der Name (Chat-Eingabe, Orchestrator, Agent …), IN der Kachel stehen die Details.
Die Kacheln sind echtes HTML (passen sich dem Inhalt an); nur die Verbindungslinien
liegen als SVG darüber. Darunter ein chronologisches Event-Log.

Läuft im selben Prozess wie das Backend (teilt den In-Process-Event-Bus), aber auf
einem eigenen Port. Wird via Env OBSERVABILITY_ENABLED=1 gestartet und ist bewusst
KEIN Teil der eigentlichen API.
"""

from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.observability import trace_bus

dashboard_app = FastAPI(title="Agent Flow — Live", docs_url=None, redoc_url=None)


@dashboard_app.get("/events")
async def events():
    async def stream():
        yield ": connected\n\n"
        async for event in trace_bus.subscribe():
            yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@dashboard_app.get("/recent")
async def recent():
    return JSONResponse(trace_bus.recent_events())


@dashboard_app.get("/")
async def index():
    return HTMLResponse(_PAGE)


_PAGE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Agent Flow — Live</title>
<style>
  :root{
    --bg:#f4f6f9; --panel:#ffffff; --text:#1f2633; --muted:#6b7280;
    --line:#c3ccd8; --accent:#2563eb; --ok:#059669; --err:#dc2626;
  }
  *{box-sizing:border-box}
  *,*::before,*::after{border-style:none !important}
  body{margin:0;background:var(--bg);color:var(--text);
    font:13px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  header{padding:13px 22px;display:flex;align-items:center;gap:12px;background:var(--panel);
    box-shadow:0 1px 3px rgba(16,24,40,.06)}
  header h1{font-size:15px;margin:0;font-weight:650}
  .live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--err)}
  .dot.on{background:var(--ok);animation:pulse 1.6s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(5,150,105,.4)}70%{box-shadow:0 0 0 7px rgba(5,150,105,0)}100%{box-shadow:0 0 0 0 rgba(5,150,105,0)}}
  .wrap{padding:16px 22px;max-width:1180px;margin:0 auto}
  .trace{font-size:12px;color:var(--muted);margin-bottom:10px}
  .trace b{color:var(--text)}
  .chartbox{overflow-x:auto;border-radius:14px;background:var(--panel);padding:6px 4px;
    box-shadow:0 1px 3px rgba(16,24,40,.06)}

  /* Flow: HTML-Kacheln + SVG-Linien darüber */
  #chart{position:relative}
  #wires{position:absolute;top:0;left:0;z-index:0;pointer-events:none;overflow:visible}
  .flow{position:relative;z-index:1;display:flex;flex-direction:column;align-items:center;
    gap:44px;padding:14px 16px 20px}
  .lvl{display:flex;justify-content:center;width:100%}
  .lvl.agents{gap:24px;flex-wrap:wrap}
  .node{width:248px;--c:var(--muted);--cardbg:#eef1f5}

  .nlabel{display:flex;align-items:center;gap:7px;margin:0 0 5px 3px;
    font-size:11px;font-weight:600;letter-spacing:.2px;color:var(--c)}
  .st{font-size:10px;font-weight:600;padding:1px 6px;border-radius:20px}
  .st.run{color:var(--accent);background:rgba(37,99,235,.1)}
  .st.done{color:var(--ok);background:rgba(5,150,105,.1)}
  .st.err{color:var(--err);background:rgba(220,38,38,.1)}

  .card{position:relative;background:var(--cardbg);border-radius:10px;padding:9px 26px 9px 11px;
    cursor:pointer;transition:box-shadow .12s;min-height:38px}
  .card:hover{box-shadow:0 0 0 2px color-mix(in srgb,var(--c) 45%,transparent)}
  .card.active{box-shadow:0 0 0 2px var(--c)}
  .chev{position:absolute;top:8px;right:9px;font-size:9px;color:var(--muted);line-height:1}
  .detail{font-size:12px;font-weight:400;line-height:1.4;color:var(--text);
    overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical}
  .card.open .detail{-webkit-line-clamp:unset}
  .detail.res{margin-top:4px;color:color-mix(in srgb,var(--c) 70%,var(--text))}
  .sub{font-size:11px;color:var(--muted);margin-top:3px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .card.open .sub{white-space:normal}
  .placeholder{color:var(--muted);font-style:italic}

  /* Typ-Farben (Fläche + Label) — auf .node, damit Label + Kachel sie erben */
  .t-chat{--c:#2563eb;--cardbg:#e8f0fe}
  .t-orch{--c:#7c3aed;--cardbg:#efe9fd}
  .t-out{--c:#0891b2;--cardbg:#d7f4fa}
  .n-tutor{--c:#059669;--cardbg:#d6f5e6}
  .n-moodle{--c:#d97706;--cardbg:#fdeecf}
  .n-evaluator{--c:#9333ea;--cardbg:#f1e6fe}
  .n-planner{--c:#0284c7;--cardbg:#dbeffc}
  .n-career{--c:#e11d48;--cardbg:#ffe0e6}
  .n-curriculum{--c:#db2777;--cardbg:#fce3f0}

  .wire{fill:none;stroke:var(--line);stroke-width:1.6}
  .wire.on{stroke:var(--accent);stroke-width:2;stroke-dasharray:6 5;animation:dash 1s linear infinite}
  @keyframes dash{to{stroke-dashoffset:-22}}

  /* Event-Log */
  .logwrap{margin-top:18px;background:var(--panel);border-radius:12px;overflow:hidden;
    box-shadow:0 1px 3px rgba(16,24,40,.06)}
  .logwrap h2{margin:0;padding:10px 15px;font-size:11px;text-transform:uppercase;
    letter-spacing:.7px;color:var(--muted);background:#f8fafc}
  .log{max-height:30vh;overflow:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
  .lrow{display:flex;gap:10px;padding:5px 15px;align-items:baseline}
  .lrow:nth-child(even){background:#f8fafc}
  .lrow .ts{color:var(--muted);white-space:nowrap}
  .lrow .badge{padding:1px 7px;border-radius:6px;font-size:10.5px;font-weight:600;white-space:nowrap}
  .lrow .lbl{font-weight:600}
  .lrow .det{color:var(--muted);word-break:break-word}
  .b-chat{background:#e8f0fe;color:#2563eb}
  .b-orchestrator{background:#efe9fd;color:#7c3aed}
  .b-tutor{background:#d6f5e6;color:#059669}
  .b-moodle{background:#fdeecf;color:#b45309}
  .b-evaluator{background:#f1e6fe;color:#9333ea}
  .b-planner{background:#dbeffc;color:#0284c7}
  .b-career{background:#ffe0e6;color:#e11d48}
  .b-curriculum{background:#fce3f0;color:#db2777}
  .b-rag{background:#dbeffc;color:#0284c7}
  .b-output,.b-action{background:#e5e9f0;color:#374151}
  .b-error{background:#fde2e1;color:#dc2626}
  .empty{color:var(--muted);padding:16px}
</style>
</head>
<body>
<header>
  <h1>🔎 Agent Flow — Live</h1>
  <span class="live"><span id="conn" class="dot"></span><span id="conntext">verbinde…</span></span>
</header>
<div class="wrap">
  <div class="trace">Aktueller Ablauf: <b id="trace">–</b> · Stelle im Chat eine Frage oder löse eine Aktion aus.</div>
  <div class="chartbox">
    <div id="chart">
      <svg id="wires" xmlns="http://www.w3.org/2000/svg"></svg>
      <div class="flow" id="flow"></div>
    </div>
  </div>

  <div class="logwrap">
    <h2>Event-Log</h2>
    <div class="log" id="log"><div class="empty">Warte auf Events…</div></div>
  </div>
</div>

<script>
const AGENT_NODES=["tutor","moodle","evaluator","planner","career","curriculum"];
let currentTrace=null;
let S = { input:"", orch:{detail:"",active:false,done:false,err:false}, out:{text:"",active:false}, cards:[] };
const EXP={};  // aufgeklappte Kacheln (id -> true)
function toggle(id){ EXP[id]=!EXP[id]; render(); }

function esc(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}
function fmtTs(ts){return new Date(ts*1000).toLocaleTimeString("de-DE");}
function reset(){ S={input:"",orch:{detail:"",active:false,done:false,err:false},out:{text:"",active:false},cards:[]}; render(); }
function lastRunning(node){ for(let i=S.cards.length-1;i>=0;i--){ if(S.cards[i].status==="running"&&(!node||S.cards[i].node===node)) return S.cards[i]; } return null; }

// Eine Kachel: Name-Label OBEN, Details IN der Kachel.
function nodeHtml(id, typeCls, label, statusHtml, detailHtml, active, hasMore){
  const open=!!EXP[id];
  return `<div class="node ${typeCls}" data-id="${id}">`+
    `<div class="nlabel">${label}${statusHtml||""}</div>`+
    `<div class="card${open?" open":""}${active?" active":""}"${hasMore?` onclick="toggle('${id}')"`:""}>`+
      (hasMore?`<span class="chev">${open?"▲":"▼"}</span>`:"")+detailHtml+
    `</div></div>`;
}

function agentNode(c,i){
  const id="c"+i, open=!!EXP[id];
  const dur=c.endTs?Math.max(0,Math.round(c.endTs-c.startTs))+" s":"";
  const st=c.status==="running"?`<span class="st run">läuft</span>`
    :(c.status==="error"?`<span class="st err">Fehler</span>`:`<span class="st done">✓ ${dur}</span>`);
  const subsArr=(c.subs||[]).slice(open?0:-2);
  const subs=subsArr.map(s=>`<div class="sub">· ${esc(s.text)}</div>`).join("");
  let detail=c.request?`<div class="detail">${esc(c.request)}</div>`:"";
  if(open&&c.result) detail+=`<div class="detail res">→ ${esc(c.result)}</div>`;
  detail+=subs;
  const hasMore=!!(c.result || (c.subs&&c.subs.length>2) || (c.request&&c.request.length>72));
  return nodeHtml(id,"n-"+c.node,esc(c.label),st,detail,c.status==="running",hasMore);
}

function render(){
  const flow=document.getElementById("flow");
  // Chat
  const inTxt=S.input?`<div class="detail">${esc(S.input)}</div>`:`<div class="detail placeholder">—</div>`;
  let html=`<div class="lvl">`+nodeHtml("chat","t-chat","Chat-Eingabe","",inTxt,false,(S.input||"").length>72)+`</div>`;
  // Orchestrator
  const od=S.orch.err?"Fehler bei der Verarbeitung":(S.orch.detail||(S.orch.active?"entscheidet…":(S.orch.done?"fertig":"—")));
  const ost=S.orch.active?`<span class="st run">läuft</span>`:(S.orch.done?`<span class="st done">✓</span>`:"");
  html+=`<div class="lvl">`+nodeHtml("orch","t-orch","Orchestrator",ost,`<div class="detail${S.orch.detail||S.orch.done?"":" placeholder"}">${esc(od)}</div>`,S.orch.active,(od||"").length>72)+`</div>`;
  // Agents (Verzweigung)
  if(S.cards.length){
    html+=`<div class="lvl agents">`+S.cards.map(agentNode).join("")+`</div>`;
  }
  // Output — zeigt IMMER die finale Antwort (auch wenn kein Agent lief)
  const outTxt=S.out.text?`<div class="detail">${esc(S.out.text)}</div>`
    :`<div class="detail placeholder">${S.out.active?"…":"—"}</div>`;
  const oust=S.out.active&&S.out.text?`<span class="st done">✓</span>`:"";
  html+=`<div class="lvl">`+nodeHtml("out","t-out","Output",oust,outTxt,S.out.active&&!S.out.text,(S.out.text||"").length>72)+`</div>`;
  flow.innerHTML=html;
  drawWires();
}

function drawWires(){
  const chart=document.getElementById("chart"), svg=document.getElementById("wires");
  if(!chart) return;
  const base=chart.getBoundingClientRect();
  const W=chart.clientWidth, H=chart.clientHeight;
  const cb=id=>{const el=document.querySelector(`.node[data-id="${id}"] .card`); if(!el)return null;
    const r=el.getBoundingClientRect(); return {x:r.left-base.left+r.width/2, top:r.top-base.top, bot:r.bottom-base.top};};
  const path=(a,b,on)=>{ if(!a||!b)return ""; const my=(a.bot+b.top)/2;
    return `<path class="wire${on?" on":""}" d="M${a.x},${a.bot} C ${a.x},${my} ${b.x},${my} ${b.x},${b.top}" marker-end="url(#aw)"/>`;};
  const chat=cb("chat"), orch=cb("orch"), out=cb("out");
  let p=path(chat,orch,true);
  if(S.cards.length){
    S.cards.forEach((c,i)=>{ const a=cb("c"+i); p+=path(orch,a,c.status==="running"); p+=path(a,out,c.status!=="running"); });
  }else{
    p+=path(orch,out,S.out.active);
  }
  const defs=`<defs><marker id="aw" markerWidth="8" markerHeight="8" refX="6" refY="4" orient="auto"><path d="M0,0 L7,4 L0,8 z" fill="var(--line)"/></marker></defs>`;
  svg.setAttribute("viewBox",`0 0 ${W} ${H}`);
  svg.setAttribute("width",W); svg.setAttribute("height",H);
  svg.innerHTML=defs+p;
}
window.addEventListener("resize",drawWires);

function addLog(ev){
  const log=document.getElementById("log"); const e=log.querySelector(".empty"); if(e)e.remove();
  const badge="b-"+(AGENT_NODES.includes(ev.node)?ev.node:(ev.type==="error"?"error":ev.node));
  const row=document.createElement("div"); row.className="lrow";
  row.innerHTML=`<span class="ts">${fmtTs(ev.ts)}</span><span class="badge ${badge}">${esc(ev.node)}</span>`+
    `<span class="lbl">${esc(ev.label||ev.type)}</span>`+(ev.detail?`<span class="det">${esc(ev.detail)}</span>`:"");
  log.insertBefore(row,log.firstChild);
  while(log.children.length>250) log.removeChild(log.lastChild);
}

function route(ev){
  if(ev.type==="chat_input"){ S.input=ev.detail||ev.label; render(); return; }
  if(ev.node==="orchestrator"){
    if(ev.type==="agent_start"){ S.orch.active=true; }
    else if(ev.type==="route"){ S.orch.detail=ev.label; }
    else if(ev.type==="agent_end"){ S.orch.active=false; S.orch.done=true; }
    else if(ev.type==="error"){ S.orch.err=true; S.orch.detail=ev.label; S.orch.active=false; }
    render(); return;
  }
  if(ev.type==="output"||ev.type==="done"){ S.out.active=true; if(ev.detail) S.out.text=ev.detail; render(); return; }
  if(AGENT_NODES.includes(ev.node)&&ev.type==="agent_start"){
    S.cards.push({seq:ev.seq,node:ev.node,label:ev.label,request:ev.detail,status:"running",startTs:ev.ts,subs:[]}); render(); return;
  }
  if(AGENT_NODES.includes(ev.node)&&ev.type==="agent_end"){
    const c=lastRunning(ev.node); if(c){c.status="done";c.endTs=ev.ts; if(ev.detail)c.result=ev.detail;} render(); return;
  }
  if(AGENT_NODES.includes(ev.node)&&ev.type==="error"){
    const c=lastRunning(ev.node); if(c){c.status="error";c.endTs=ev.ts;} render(); return;
  }
  if(["rag","tool","moodle"].includes(ev.type)){
    const c=lastRunning(null); if(c){ c.subs.push({text:(ev.label||"")+(ev.detail?" · "+ev.detail:"")}); render(); }
  }
}

function handle(ev){
  if(ev.type==="chat_input"&&ev.trace_id!==currentTrace){ currentTrace=ev.trace_id; reset(); document.getElementById("trace").textContent=ev.trace_id||"–"; }
  route(ev); addLog(ev);
}

function connect(){
  const es=new EventSource("/events");
  const d=document.getElementById("conn"), t=document.getElementById("conntext");
  es.onopen=()=>{d.classList.add("on");t.textContent="live";};
  es.onerror=()=>{d.classList.remove("on");t.textContent="getrennt – reconnect…";};
  es.onmessage=(e)=>{ try{ handle(JSON.parse(e.data)); }catch(_){} };
}
render(); connect();
</script>
</body>
</html>
"""
