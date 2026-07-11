"""Observability-Dashboard (eigener Port, nur Präsentation).

Serviert eine Single-Page-Ansicht, die per SSE die Live-Trace-Events des
Agenten-Flows empfängt und als laufende Linie darstellt:
Chat-Eingabe → Orchestrator → Agent → Tools/RAG → Output.

Läuft im selben Prozess wie das Backend (teilt den In-Process-Event-Bus), aber
auf einem eigenen Port. Wird via Env OBSERVABILITY_ENABLED=1 aus der Lifespan
gestartet und ist bewusst KEIN Teil der eigentlichen API.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

from app.observability import trace_bus

dashboard_app = FastAPI(title="Agent Flow — Live", docs_url=None, redoc_url=None)


@dashboard_app.get("/events")
async def events():
    async def stream():
        # Kommentar-Ping öffnet den Stream sofort
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
    --bg:#0b0e17; --panel:#141926; --panel2:#1b2233; --border:#26304a;
    --text:#e8ecf5; --muted:#8b97b3; --accent:#6ea8fe; --accent2:#8b5cf6;
    --ok:#34d399; --warn:#fbbf24; --err:#f87171; --rag:#38bdf8; --moodle:#f59e0b;
  }
  *{box-sizing:border-box}
  body{margin:0;background:radial-gradient(1200px 600px at 50% -10%,#182036,var(--bg));
    color:var(--text);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;}
  header{padding:16px 22px;display:flex;align-items:center;gap:12px;border-bottom:1px solid var(--border)}
  header h1{font-size:16px;margin:0;font-weight:650;letter-spacing:.3px}
  .live{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--muted)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--err);box-shadow:0 0 0 0 rgba(248,113,113,.6)}
  .dot.on{background:var(--ok);animation:pulse 1.6s infinite}
  @keyframes pulse{0%{box-shadow:0 0 0 0 rgba(52,211,153,.5)}70%{box-shadow:0 0 0 8px rgba(52,211,153,0)}100%{box-shadow:0 0 0 0 rgba(52,211,153,0)}}
  .wrap{padding:26px 22px;max-width:1200px;margin:0 auto}
  .trace{font-size:12px;color:var(--muted);margin-bottom:18px}
  .flow{display:flex;align-items:stretch;gap:0;margin:10px 0 26px}
  .stage{flex:1;min-width:0;background:var(--panel);border:1px solid var(--border);border-radius:14px;
    padding:14px;transition:.25s;position:relative;opacity:.55}
  .stage.active{opacity:1;border-color:var(--accent);box-shadow:0 0 0 1px var(--accent),0 8px 30px rgba(110,168,254,.15);transform:translateY(-2px)}
  .stage.done{opacity:1}
  .stage .k{font-size:11px;text-transform:uppercase;letter-spacing:.8px;color:var(--muted)}
  .stage .t{font-weight:650;margin:6px 0 2px;font-size:14px}
  .stage .d{font-size:12px;color:var(--muted);word-break:break-word;min-height:32px}
  .conn{width:46px;display:flex;align-items:center;justify-content:center;position:relative}
  .conn .bar{height:3px;width:100%;background:var(--border);border-radius:3px;overflow:hidden;position:relative}
  .conn .bar::after{content:"";position:absolute;inset:0;width:40%;border-radius:3px;
    background:linear-gradient(90deg,transparent,var(--accent),transparent);transform:translateX(-120%);opacity:0}
  .conn.run .bar::after{animation:run 1s linear infinite;opacity:1}
  @keyframes run{to{transform:translateX(260%)}}
  .agents{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 22px}
  .chip{font-size:12px;padding:4px 10px;border-radius:999px;border:1px solid var(--border);
    background:var(--panel2);color:var(--muted);display:inline-flex;gap:6px;align-items:center}
  .chip.on{color:var(--text);border-color:var(--accent);background:rgba(110,168,254,.12)}
  .chip .s{width:7px;height:7px;border-radius:50%;background:var(--muted)}
  .chip.on .s{background:var(--ok)}
  .logwrap{background:var(--panel);border:1px solid var(--border);border-radius:14px;overflow:hidden}
  .logwrap h2{margin:0;padding:12px 16px;font-size:12px;text-transform:uppercase;letter-spacing:.8px;
    color:var(--muted);border-bottom:1px solid var(--border)}
  .log{max-height:44vh;overflow:auto;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12.5px}
  .row{display:flex;gap:10px;padding:8px 16px;border-bottom:1px solid rgba(38,48,74,.5);align-items:baseline}
  .row:last-child{border-bottom:none}
  .row .ts{color:var(--muted);white-space:nowrap}
  .row .badge{padding:1px 7px;border-radius:6px;font-size:11px;font-weight:600;white-space:nowrap}
  .row .lbl{font-weight:600}
  .row .det{color:var(--muted);word-break:break-word}
  .b-chat{background:rgba(110,168,254,.15);color:var(--accent)}
  .b-orchestrator{background:rgba(139,92,246,.16);color:#b79bff}
  .b-agent{background:rgba(52,211,153,.15);color:var(--ok)}
  .b-rag{background:rgba(56,189,248,.15);color:var(--rag)}
  .b-moodle{background:rgba(245,158,11,.16);color:var(--moodle)}
  .b-output{background:rgba(232,236,245,.12);color:var(--text)}
  .b-error{background:rgba(248,113,113,.18);color:var(--err)}
  .empty{color:var(--muted);padding:22px 16px}
</style>
</head>
<body>
<header>
  <h1>🔎 Agent Flow — Live</h1>
  <span class="live"><span id="conn" class="dot"></span><span id="conntext">verbinde…</span></span>
</header>
<div class="wrap">
  <div class="trace">Aktueller Trace: <b id="trace">–</b> · Stelle im Chat eine Frage, um den Flow zu sehen.</div>

  <div class="flow" id="flow">
    <div class="stage" data-stage="0"><div class="k">1 · Eingabe</div><div class="t">Chat</div><div class="d" id="s0"></div></div>
    <div class="conn" data-conn="1"><div class="bar"></div></div>
    <div class="stage" data-stage="1"><div class="k">2 · Supervisor</div><div class="t">Orchestrator</div><div class="d" id="s1"></div></div>
    <div class="conn" data-conn="2"><div class="bar"></div></div>
    <div class="stage" data-stage="2"><div class="k">3 · Spezial-Agent</div><div class="t" id="s2t">Agent</div><div class="d" id="s2"></div></div>
    <div class="conn" data-conn="3"><div class="bar"></div></div>
    <div class="stage" data-stage="3"><div class="k">4 · Tools / RAG</div><div class="t">Werkzeuge</div><div class="d" id="s3"></div></div>
    <div class="conn" data-conn="4"><div class="bar"></div></div>
    <div class="stage" data-stage="4"><div class="k">5 · Ergebnis</div><div class="t">Output</div><div class="d" id="s4"></div></div>
  </div>

  <div class="agents" id="agents">
    <span class="chip" data-agent="tutor"><span class="s"></span>Tutor</span>
    <span class="chip" data-agent="moodle"><span class="s"></span>Moodle-QA</span>
    <span class="chip" data-agent="evaluator"><span class="s"></span>Evaluator</span>
    <span class="chip" data-agent="planner"><span class="s"></span>Planner</span>
    <span class="chip" data-agent="career"><span class="s"></span>Career</span>
    <span class="chip" data-agent="curriculum"><span class="s"></span>Curriculum</span>
  </div>

  <div class="logwrap">
    <h2>Event-Log</h2>
    <div class="log" id="log"><div class="empty">Noch keine Events. Warte auf eine Chat-Anfrage…</div></div>
  </div>
</div>

<script>
const AGENT_NODES = ["tutor","moodle","evaluator","planner","career","curriculum"];
let currentTrace = null;

function stageOf(ev){
  if(ev.type==="chat_input") return 0;
  if(ev.node==="orchestrator") return 1;
  if(ev.type==="agent_start"||ev.type==="agent_end"){ return AGENT_NODES.includes(ev.node)?2:1; }
  if(ev.type==="rag"||ev.type==="moodle"||ev.type==="tool") return 3;
  if(ev.node==="output"||ev.type==="output"||ev.type==="done") return 4;
  return null;
}
function badgeClass(ev){
  if(ev.type==="error") return "b-error";
  if(ev.node==="chat") return "b-chat";
  if(ev.node==="orchestrator") return "b-orchestrator";
  if(ev.node==="rag") return "b-rag";
  if(ev.node==="moodle") return "b-moodle";
  if(ev.node==="output") return "b-output";
  if(AGENT_NODES.includes(ev.node)) return "b-agent";
  return "b-output";
}
function resetFlow(){
  document.querySelectorAll(".stage").forEach(s=>s.classList.remove("active","done"));
  document.querySelectorAll(".conn").forEach(c=>c.classList.remove("run"));
  document.querySelectorAll(".chip").forEach(c=>c.classList.remove("on"));
  ["s0","s1","s2","s3","s4"].forEach(id=>document.getElementById(id).textContent="");
  document.getElementById("s2t").textContent="Agent";
}
function activateStage(idx, label, detail){
  const stages=document.querySelectorAll(".stage");
  stages.forEach((s,i)=>{ const n=+s.dataset.stage;
    if(n<idx) s.classList.add("done"); if(n===idx){s.classList.add("active");} else {s.classList.remove("active");}
  });
  // Konnektor zur aktiven Stufe kurz "laufen" lassen
  document.querySelectorAll(".conn").forEach(c=>c.classList.remove("run"));
  const conn=document.querySelector('.conn[data-conn="'+idx+'"]');
  if(conn){ conn.classList.add("run"); }
  const d=document.getElementById("s"+idx);
  if(d && (label||detail)) d.textContent = detail? (label? label+" — "+detail : detail) : label;
}
function addLog(ev){
  const log=document.getElementById("log");
  const empty=log.querySelector(".empty"); if(empty) empty.remove();
  const row=document.createElement("div"); row.className="row";
  const t=new Date(ev.ts*1000).toLocaleTimeString("de-DE");
  row.innerHTML=`<span class="ts">${t}</span>`+
    `<span class="badge ${badgeClass(ev)}">${ev.node}</span>`+
    `<span class="lbl">${escapeHtml(ev.label||ev.type)}</span>`+
    (ev.detail?`<span class="det">${escapeHtml(ev.detail)}</span>`:"");
  log.insertBefore(row, log.firstChild);
  while(log.children.length>200) log.removeChild(log.lastChild);
}
function escapeHtml(s){return (s||"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

function handle(ev){
  if(ev.type==="chat_input" && ev.trace_id!==currentTrace){ currentTrace=ev.trace_id; resetFlow();
    document.getElementById("trace").textContent=ev.trace_id||"–"; }
  const idx=stageOf(ev);
  if(idx!==null) activateStage(idx, ev.label, ev.detail);
  if(idx===2 && ev.type==="agent_start"){ document.getElementById("s2t").textContent=ev.label||"Agent"; }
  if(AGENT_NODES.includes(ev.node)){ const chip=document.querySelector('.chip[data-agent="'+ev.node+'"]'); if(chip) chip.classList.add("on"); }
  if(ev.type==="done"){ document.querySelectorAll(".stage").forEach(s=>s.classList.add("done")); document.querySelectorAll(".conn").forEach(c=>c.classList.remove("run")); }
  addLog(ev);
}

function connect(){
  const es=new EventSource("/events");
  const dot=document.getElementById("conn"), txt=document.getElementById("conntext");
  es.onopen=()=>{dot.classList.add("on");txt.textContent="live";};
  es.onerror=()=>{dot.classList.remove("on");txt.textContent="getrennt – reconnect…";};
  es.onmessage=(e)=>{ try{ handle(JSON.parse(e.data)); }catch(_){} };
}
connect();
</script>
</body>
</html>
"""
