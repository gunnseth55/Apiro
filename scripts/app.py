#!/usr/bin/env python3
"""
scripts/app.py
==============
A minimal FastAPI web interface for Apiro.

Run with:
  venv/bin/uvicorn scripts.app:app --reload --port 8000

Features:
  - Dark mode card interface for clinical input findings.
  - Runs real-time Apiro Traversal (stub-free) on Llama 3.1 & ChromaDB.
  - Renders the interactive D3.js force-directed belief graph dynamically on completion.
  - Node inspector panel in the web UI.
"""

import sys
import logging
import time
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts.investigate import build_components, parse_findings_to_seeds
from apiro.graph.belief_graph import BeliefGraph

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("apiro_app")

app = FastAPI(title="Apiro AI Detective")

# Initialize shared components once on startup
logger.info("Initializing Apiro components...")
try:
    traversal, expander, entropy_engine, doc_count = build_components()
    logger.info(f"Apiro ready. ChromaDB contains {doc_count:,} documents.")
except Exception as e:
    logger.error(f"Failed to initialize Apiro components: {e}")
    traversal, expander, entropy_engine, doc_count = None, None, None, 0


class InvestigationRequest(BaseModel):
    findings: str
    max_depth: int = 5
    real_entropy: bool = False


# ---------------------------------------------------------------------------
# HTML + CSS + JS Frontend
# ---------------------------------------------------------------------------

INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Apiro AI Clinical Detective</title>
<style>
  :root {
    --bg: #090b11;
    --surface: #131625;
    --border: #222538;
    --text: #f1f5f9;
    --muted: #64748b;
    --accent: #6366f1;
    --accent-hover: #4f46e5;
    --success: #10b981;
    --danger: #ef4444;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    display: flex;
    flex-direction: column;
    height: 100vh;
    overflow: hidden;
  }
  header {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  header h1 {
    font-size: 18px;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: -0.025em;
  }
  header .tagline {
    font-size: 11px;
    color: var(--muted);
    margin-top: 2px;
  }
  #main-layout {
    flex: 1;
    display: flex;
    overflow: hidden;
  }
  /* Left Panel: Input & Findings */
  #input-panel {
    width: 380px;
    background: var(--surface);
    border-right: 1px solid var(--border);
    padding: 24px;
    display: flex;
    flex-direction: column;
    gap: 20px;
    overflow-y: auto;
  }
  .form-group {
    display: flex;
    flex-direction: column;
    gap: 8px;
  }
  label {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }
  textarea {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 6px;
    color: var(--text);
    padding: 12px;
    font-size: 13px;
    line-height: 1.5;
    resize: none;
    height: 120px;
    outline: none;
    transition: border-color 0.15s ease;
  }
  textarea:focus {
    border-color: var(--accent);
  }
  .input-hint {
    font-size: 10px;
    color: var(--muted);
    line-height: 1.4;
  }
  button {
    background: var(--accent);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 12px;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    transition: background 0.15s ease;
  }
  button:hover {
    background: var(--accent-hover);
  }
  button:disabled {
    background: var(--border);
    color: var(--muted);
    cursor: not-allowed;
  }
  .toggle-container {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 12px;
  }
  /* Middle Panel: Visualizer viewport */
  #viewport-panel {
    flex: 1;
    position: relative;
    background: var(--bg);
  }
  svg {
    width: 100%;
    height: 100%;
    cursor: grab;
  }
  svg:active { cursor: grabbing; }
  /* Right Panel: Inspector & Differential */
  #inspector-panel {
    width: 320px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  .inspector-section {
    padding: 20px;
    border-bottom: 1px solid var(--border);
  }
  .inspector-section:last-child {
    border-bottom: none;
    flex: 1;
    overflow-y: auto;
  }
  .section-title {
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 12px;
  }
  #synthesis-list {
    padding-left: 18px;
    font-size: 13px;
    line-height: 1.8;
  }
  #synthesis-list li:first-child {
    color: #a5f3fc;
    font-weight: 700;
  }
  #node-detail .field {
    margin-bottom: 12px;
  }
  #node-detail .label {
    font-size: 9px;
    text-transform: uppercase;
    color: var(--muted);
    margin-bottom: 2px;
  }
  #node-detail .value {
    font-size: 12px;
    color: var(--text);
    word-break: break-word;
  }
  .domain-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 9px;
    font-weight: 600;
    color: #fff;
  }
  .entropy-bar-container {
    height: 6px;
    background: var(--border);
    border-radius: 3px;
    overflow: hidden;
    margin-top: 4px;
  }
  .entropy-bar {
    height: 100%;
    border-radius: 3px;
  }
  .tag {
    display: inline-block;
    padding: 2px 6px;
    border-radius: 4px;
    font-size: 9px;
    font-weight: 600;
    margin: 2px 2px 0 0;
  }
  .tag.rabbit-hole { background: #7f1d1d; color: #fca5a5; }
  .tag.seed { background: #1e3a5f; color: #93c5fd; }
  /* Link / node CSS styles */
  .link {
    stroke: #2e324e;
    stroke-width: 1.5px;
    stroke-opacity: 0.7;
    fill: none;
  }
  .link.contradiction {
    stroke: var(--danger);
    stroke-width: 2px;
    stroke-dasharray: 4,3;
  }
  .node circle {
    stroke-width: 2px;
    cursor: pointer;
    transition: all 0.15s ease;
  }
  .node circle:hover {
    stroke-width: 3.5px;
  }
  .node.rabbit-hole circle {
    stroke-dasharray: 4,3;
    opacity: 0.5;
  }
  .node.selected circle {
    stroke: #fff !important;
    stroke-width: 3.5px;
  }
  .node text {
    font-size: 8px;
    fill: #94a3b8;
    pointer-events: none;
    text-anchor: middle;
    dominant-baseline: central;
  }
  .node .depth-badge {
    font-size: 6px;
    fill: rgba(255,255,255,0.4);
  }
  /* Overlay & loaders */
  #loader-overlay {
    position: absolute;
    top: 0; left: 0; right: 0; bottom: 0;
    background: rgba(9,11,17,0.85);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
    z-index: 50;
    backdrop-filter: blur(4px);
    display: none;
  }
  .spinner {
    width: 40px;
    height: 40px;
    border: 3px solid var(--border);
    border-top: 3px solid var(--accent);
    border-radius: 50%;
    animation: spin 1s linear infinite;
  }
  @keyframes spin {
    0% { transform: rotate(0deg); }
    100% { transform: rotate(360deg); }
  }
  #loader-text {
    font-size: 13px;
    color: var(--text);
  }
  /* Tooltip */
  #tooltip {
    position: absolute;
    background: rgba(19,22,37,0.95);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 11px;
    pointer-events: none;
    max-width: 250px;
    line-height: 1.4;
    display: none;
    z-index: 100;
  }
</style>
</head>
<body>
<header>
  <div>
    <h1>Apiro Clinical Detective</h1>
    <div class="tagline">Cognitive Belief-Graph Uncertainty Engine &bull; ChromaDB {doc_count} docs</div>
  </div>
</header>
<div id="main-layout">
  <div id="input-panel">
    <div class="form-group">
      <label>Clinical Findings</label>
      <textarea id="findings-input" placeholder="Paste patient symptoms, labs, vitals here... e.g. 45yo male, chest pain, troponin 2.1, ST elevation V3-V5"></textarea>
      <div class="input-hint">Provide detailed history, symptoms, or lab findings separated by commas.</div>
    </div>
    <div class="form-group">
      <label>Max Graph Depth</label>
      <input type="number" id="depth-input" value="5" min="2" max="8" style="background:var(--bg);border:1px solid var(--border);color:var(--text);padding:8px;border-radius:6px;font-size:13px;outline:none;">
    </div>
    <div class="toggle-container">
      <input type="checkbox" id="real-entropy-input">
      <label for="real-entropy-input" style="cursor:pointer;text-transform:none;">Real-time seed entropy (slower)</label>
    </div>
    <button id="run-btn" onclick="startInvestigation()">Run Detective</button>
  </div>
  
  <div id="viewport-panel">
    <svg id="svg"></svg>
    <div id="loader-overlay">
      <div class="spinner"></div>
      <div id="loader-text">Analyzing clinical findings...</div>
    </div>
    <div id="tooltip"></div>
  </div>
  
  <div id="inspector-panel">
    <div class="inspector-section">
      <div class="section-title">Top Differential Diagnoses</div>
      <ol id="synthesis-list">
        <li style="color: var(--muted); list-style: none;">Run investigation to generate differential.</li>
      </ol>
    </div>
    <div class="inspector-section">
      <div class="section-title">Node Inspector</div>
      <div id="node-detail">
        <div style="color: var(--muted); text-align:center; padding-top: 30px;">Click nodes to view metadata.</div>
      </div>
    </div>
  </div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const DOMAIN_COLORS = {domain_colors};

function entropyColor(h) {
  h = Math.max(0, Math.min(1, h));
  if (h < 0.5) {
    const t = h * 2;
    return `rgb(${Math.round(t*60)},${Math.round(t*100)},${Math.round(140 + t*80)})`;
  } else {
    const t = (h - 0.5) * 2;
    return `rgb(${Math.round(180 + t*75)},${Math.round(100*(1-t))},${Math.round(220*(1-t))})`;
  }
}

let svg = d3.select('#svg');
let g = svg.append('g');
svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

let simulation = null;

function renderGraph(graphData) {
  g.selectAll('*').remove();
  
  const nodeMap = {};
  graphData.nodes.forEach(n => nodeMap[n.id] = n);

  const nodes = graphData.nodes.map(n => ({
    ...n,
    color: n.is_rabbit_hole ? '#374151' : entropyColor(n.entropy_score),
    radius: n.depth === 0 ? 20 : Math.max(10, 16 - n.depth * 2),
  }));

  const linkSet = new Set();
  const links = [];
  nodes.forEach(n => {
    if (n.parent_id && nodeMap[n.parent_id]) {
      const key = n.parent_id + '->' + n.id;
      if (!linkSet.has(key)) {
        linkSet.add(key);
        links.push({ source: n.parent_id, target: n.id, contradiction: false });
      }
    }
  });
  if (graphData.edges) {
    graphData.edges.forEach(e => {
      const key = e.parent_id + '->' + e.child_id;
      if (!linkSet.has(key)) {
        linkSet.add(key);
        links.push({ source: e.parent_id, target: e.child_id, contradiction: e.contradiction_flag || false });
      }
    });
  }

  const width = document.getElementById('viewport-panel').clientWidth;
  const height = document.getElementById('viewport-panel').clientHeight;

  simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(d => 80 + d.target.depth * 10))
    .force('charge', d3.forceManyBody().strength(-200))
    .force('center', d3.forceCenter(width / 2, height / 2))
    .force('collision', d3.forceCollide().radius(d => d.radius + 6));

  const link = g.append('g')
    .selectAll('line')
    .data(links)
    .join('line')
    .attr('class', d => 'link' + (d.contradiction ? ' contradiction' : ''));

  const nodeG = g.append('g')
    .selectAll('.node')
    .data(nodes)
    .join('g')
    .attr('class', d => 'node' + (d.is_rabbit_hole ? ' rabbit-hole' : ''))
    .call(d3.drag()
      .on('start', (e, d) => { if (!e.active) simulation.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
      .on('drag',  (e, d) => { d.fx=e.x; d.fy=e.y; })
      .on('end',   (e, d) => { if (!e.active) simulation.alphaTarget(0); d.fx=null; d.fy=null; }));

  nodeG.append('circle')
    .attr('r', d => d.radius)
    .attr('fill', d => d.color)
    .attr('stroke', d => d.is_rabbit_hole ? '#9ca3af' : d3.color(d.color).darker(0.5).toString());

  nodeG.append('text')
    .attr('dy', -4)
    .text(d => d.domain ? d.domain.slice(0, 4).toUpperCase() : '');

  nodeG.append('text')
    .attr('class', 'depth-badge')
    .attr('dy', 6)
    .text(d => `H=${d.entropy_score.toFixed(2)}`);

  const tooltip = document.getElementById('tooltip');
  nodeG.on('mouseover', (e, d) => {
    tooltip.style.display = 'block';
    tooltip.innerHTML = `<b>${d.domain || 'unknown'}</b> | depth ${d.depth} | H=${d.entropy_score.toFixed(3)}<br>
      <span style="color:#94a3b8">${d.claim}</span>`;
  }).on('mousemove', e => {
    tooltip.style.left = (e.pageX + 12) + 'px';
    tooltip.style.top  = (e.pageY - 20) + 'px';
  }).on('mouseout', () => { tooltip.style.display = 'none'; });

  let selected = null;
  nodeG.on('click', (e, d) => {
    e.stopPropagation();
    if (selected) d3.select(selected).classed('selected', false);
    selected = e.currentTarget;
    d3.select(selected).classed('selected', true);

    const tags = [];
    if (d.depth === 0) tags.push('<span class="tag seed">SEED</span>');
    if (d.is_rabbit_hole) tags.push('<span class="tag rabbit-hole">RABBIT HOLE</span>');

    const domColor = DOMAIN_COLORS[d.domain] || '#6b7280';
    const barPct = Math.round(d.entropy_score * 100);
    const barColor = d.is_rabbit_hole ? '#4b5563' : entropyColor(d.entropy_score);

    document.getElementById('node-detail').innerHTML = `
      <div class="field">
        <div class="label">Node ID</div>
        <div class="value" style="font-family:monospace;color:#94a3b8">${d.id}</div>
      </div>
      <div class="field">
        <div class="label">Claim</div>
        <div class="value">${d.claim}</div>
      </div>
      <div class="field">
        <div class="label">Domain</div>
        <span class="domain-pill" style="background:${domColor}">${d.domain || 'unknown'}</span>
      </div>
      <div class="field">
        <div class="label">Entropy Score</div>
        <div class="value">${d.entropy_score.toFixed(4)} nats</div>
        <div class="entropy-bar-container">
          <div class="entropy-bar" style="width:${barPct}%;background:${barColor}"></div>
        </div>
      </div>
      <div class="field">
        <div class="label">Depth</div>
        <div class="value">${d.depth}</div>
      </div>
      ${d.parent_id ? `<div class="field"><div class="label">Parent</div><div class="value" style="font-family:monospace;color:#94a3b8">${d.parent_id}</div></div>` : ''}
    `;
  });

  simulation.on('tick', () => {
    link
      .attr('x1', d => d.source.x)
      .attr('y1', d => d.source.y)
      .attr('x2', d => d.target.x)
      .attr('y2', d => d.target.y);
    nodeG.attr('transform', d => `translate(${d.x},${d.y})`);
  });
}

function startInvestigation() {
  const findings = document.getElementById('findings-input').value.strip;
  const maxDepth = parseInt(document.getElementById('depth-input').value);
  const realEnt  = document.getElementById('real-entropy-input').checked;

  if (!findings) {
    alert("Please enter clinical findings.");
    return;
  }

  document.getElementById('loader-overlay').style.display = 'flex';
  document.getElementById('run-btn').disabled = true;

  fetch('/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      findings: document.getElementById('findings-input').value,
      max_depth: maxDepth,
      real_entropy: realEnt
    })
  })
  .then(resp => {
    if (!resp.ok) throw new Error("Investigation traversal failed.");
    return resp.json();
  })
  .then(data => {
    document.getElementById('loader-overlay').style.display = 'none';
    document.getElementById('run-btn').disabled = false;
    
    // Render synthesis
    const listEl = document.getElementById('synthesis-list');
    listEl.innerHTML = '';
    if (data.synthesis && data.synthesis.length > 0) {
      data.synthesis.forEach(dx => {
        const li = document.createElement('li');
        li.innerText = dx;
        listEl.appendChild(li);
      });
    } else {
      listEl.innerHTML = '<li style="color:var(--muted)">No synthesis generated</li>';
    }

    // Render graph
    renderGraph(data);
  })
  .catch(err => {
    document.getElementById('loader-overlay').style.display = 'none';
    document.getElementById('run-btn').disabled = false;
    alert(err.message);
  });
}
</script>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse)
def get_index():
    if not traversal:
        return HTMLResponse(
            "<h3>Apiro engine not initialized. Please ensure Ollama is running and run build_corpus first.</h3>",
            status_code=500
        )
    return INDEX_HTML.replace("{doc_count}", f"{doc_count:,}")\
                     .replace("{domain_colors}", json.dumps(DOMAIN_COLORS))


@app.post("/run")
def run_investigation(req: InvestigationRequest):
    if not traversal:
        raise HTTPException(status_code=500, detail="Apiro engine not initialized")

    t0 = time.time()
    try:
        # Parse seeds using our demographic-preserving logic
        ee = entropy_engine if req.real_entropy else None
        seeds = parse_findings_to_seeds(req.findings, entropy_engine=ee)
        if not seeds:
            raise HTTPException(status_code=400, detail="Could not parse any valid findings")

        # Run traversal
        graph = BeliefGraph()
        result = traversal.run(
            seed_nodes=seeds,
            graph=graph,
            max_depth=req.max_depth,
            case_name="api_run",
        )
        elapsed = time.time() - t0

        # Export graph data
        nodes_list = []
        for n in graph.nodes.values():
            nodes_list.append({
                "id": n.id,
                "claim": n.claim,
                "domain": n.domain,
                "entropy_score": n.entropy_score,
                "resolved": n.resolved,
                "is_rabbit_hole": n.is_rabbit_hole,
                "depth": n.depth,
                "parent_id": n.parent_id,
            })

        edges_list = []
        for e in graph.edges:
            edges_list.append({
                "parent_id": e.parent_id,
                "child_id": e.child_id,
                "contradiction_flag": e.contradiction_flag,
            })

        return {
            "synthesis": result.synthesis or [],
            "nodes": nodes_list,
            "edges": edges_list,
            "duration": elapsed,
            "stop_reason": result.stop_reason
        }

    except Exception as e:
        logger.error(f"Error during API investigation: {e}")
        raise HTTPException(status_code=500, detail=str(e))
