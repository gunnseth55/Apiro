#!/usr/bin/env python3
"""
scripts/visualize_graph.py
===========================
Generate an interactive HTML belief-graph visualization from a traversal
graph JSON exported by BeliefGraph.export_json().

USAGE:
  venv/bin/python scripts/visualize_graph.py data/graph_investigate.json
  venv/bin/python scripts/visualize_graph.py data/graph_investigate.json --out viz.html
  venv/bin/python scripts/visualize_graph.py data/graph_investigate.json --open

OUTPUT:
  A self-contained HTML file (no external dependencies) with:
    - Force-directed belief graph (D3.js v7, inlined via CDN)
    - Nodes colored by entropy score (blue=low, red=high)
    - Rabbit-hole nodes shown with dashed border and muted color
    - Domain badges on each node
    - Click any node to see full claim text + metadata in sidebar
"""

import argparse
import json
import os
import sys
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DOMAIN_COLORS = {
    "pathophysiology": "#6366f1",   # indigo
    "pharmacology":    "#f59e0b",   # amber
    "genetics":        "#10b981",   # emerald
    "imaging":         "#3b82f6",   # blue
    "lab":             "#8b5cf6",   # violet
    "treatment":       "#06b6d4",   # cyan
    "comorbidity":     "#f97316",   # orange
    "unknown":         "#6b7280",   # grey
}


def entropy_to_rgb(h: float) -> str:
    """Map entropy 0..1 to a CSS color (blue → yellow → red)."""
    h = max(0.0, min(1.0, h))
    if h < 0.5:
        r = int(h * 2 * 220)
        g = int(h * 2 * 180)
        b = 220
    else:
        t = (h - 0.5) * 2
        r = 220
        g = int((1 - t) * 180)
        b = int((1 - t) * 220)
    return f"rgb({r},{g},{b})"


def load_graph(path: str) -> dict:
    with open(path) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# HTML template
# ---------------------------------------------------------------------------

HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Apiro Belief Graph — __CASE_NAME__</title>
<style>
  :root {
    --bg: #0f1117;
    --surface: #1a1d2e;
    --border: #2a2d3e;
    --text: #e2e8f0;
    --muted: #64748b;
    --accent: #6366f1;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Inter', 'Segoe UI', sans-serif;
    display: flex;
    height: 100vh;
    overflow: hidden;
  }
  #graph-container {
    flex: 1;
    position: relative;
    overflow: hidden;
  }
  svg {
    width: 100%;
    height: 100%;
    cursor: grab;
  }
  svg:active { cursor: grabbing; }
  .link {
    stroke: #334155;
    stroke-width: 1.5px;
    stroke-opacity: 0.7;
    fill: none;
  }
  .link.contradiction {
    stroke: #ef4444;
    stroke-width: 2px;
    stroke-dasharray: 5,3;
  }
  .node circle {
    stroke-width: 2.5px;
    cursor: pointer;
    transition: all 0.15s ease;
    filter: drop-shadow(0 2px 6px rgba(0,0,0,0.4));
  }
  .node circle:hover {
    stroke-width: 4px;
    filter: drop-shadow(0 4px 12px rgba(99,102,241,0.5));
  }
  .node.rabbit-hole circle {
    stroke-dasharray: 5,3;
    opacity: 0.45;
  }
  .node.selected circle {
    stroke: #fff !important;
    stroke-width: 4px;
    filter: drop-shadow(0 0 16px rgba(255,255,255,0.6));
  }
  .node text {
    font-size: 9px;
    fill: #cbd5e1;
    pointer-events: none;
    text-anchor: middle;
    dominant-baseline: central;
  }
  .node .depth-badge {
    font-size: 7px;
    fill: rgba(255,255,255,0.5);
  }
  /* Sidebar */
  #sidebar {
    width: 340px;
    background: var(--surface);
    border-left: 1px solid var(--border);
    display: flex;
    flex-direction: column;
    overflow: hidden;
  }
  #sidebar-header {
    padding: 16px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
    font-weight: 600;
    color: var(--accent);
    letter-spacing: 0.05em;
    text-transform: uppercase;
  }
  #node-detail {
    padding: 16px;
    flex: 1;
    overflow-y: auto;
    font-size: 12px;
    line-height: 1.6;
  }
  #node-detail .field { margin-bottom: 12px; }
  #node-detail .label {
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--muted);
    margin-bottom: 3px;
  }
  #node-detail .value {
    color: var(--text);
    word-break: break-word;
  }
  .entropy-bar-container {
    height: 8px;
    background: var(--border);
    border-radius: 4px;
    overflow: hidden;
    margin-top: 4px;
  }
  .entropy-bar {
    height: 100%;
    border-radius: 4px;
  }
  .domain-pill {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 12px;
    font-size: 10px;
    font-weight: 600;
    color: #fff;
  }
  .tag {
    display: inline-block;
    padding: 2px 7px;
    border-radius: 4px;
    font-size: 10px;
    margin: 2px 2px 0 0;
  }
  .tag.rabbit-hole { background: #7f1d1d; color: #fca5a5; }
  .tag.contradiction { background: #7c2d12; color: #fdba74; }
  .tag.seed { background: #1e3a5f; color: #93c5fd; }
  /* Stats strip */
  #stats {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
  }
  .stat { text-align: center; }
  .stat .n {
    font-size: 20px;
    font-weight: 700;
    color: var(--accent);
  }
  .stat .l {
    font-size: 9px;
    color: var(--muted);
    text-transform: uppercase;
  }
  /* Legend */
  #legend {
    padding: 10px 16px;
    border-top: 1px solid var(--border);
    font-size: 10px;
    color: var(--muted);
  }
  .legend-row { display: flex; align-items: center; gap: 6px; margin-bottom: 5px; }
  .legend-dot {
    width: 12px; height: 12px; border-radius: 50%; flex-shrink: 0;
  }
  /* Synthesis */
  #synthesis {
    padding: 12px 16px;
    border-top: 1px solid var(--border);
  }
  #synthesis .syn-title {
    font-size: 10px;
    color: var(--muted);
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin-bottom: 8px;
  }
  #synthesis ol {
    padding-left: 16px;
    font-size: 12px;
    line-height: 1.8;
  }
  #synthesis li { color: var(--text); }
  #synthesis li:first-child { color: #a5f3fc; font-weight: 600; }
  /* Tooltip */
  #tooltip {
    position: absolute;
    background: rgba(15,17,23,0.92);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 11px;
    pointer-events: none;
    max-width: 280px;
    line-height: 1.5;
    display: none;
    z-index: 100;
  }
  #title-bar {
    position: absolute;
    top: 12px;
    left: 12px;
    background: rgba(26,29,46,0.85);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 14px;
    font-size: 12px;
    font-weight: 600;
    color: var(--accent);
    backdrop-filter: blur(6px);
  }
  #instructions {
    position: absolute;
    bottom: 12px;
    left: 12px;
    font-size: 10px;
    color: var(--muted);
  }
</style>
</head>
<body>
<div id="graph-container">
  <svg id="svg"></svg>
  <div id="title-bar">Apiro Belief Graph &mdash; __CASE_NAME__</div>
  <div id="tooltip"></div>
  <div id="instructions">Scroll to zoom &nbsp;|&nbsp; Drag to pan &nbsp;|&nbsp; Click node for detail</div>
</div>
<div id="sidebar">
  <div id="sidebar-header">Node Inspector</div>
  <div id="node-detail">
    <div style="color: var(--muted); font-size: 12px; margin-top: 20px; text-align:center;">
      Click any node to inspect it.
    </div>
  </div>
  <div id="synthesis">
    <div class="syn-title">Top Differential Diagnoses</div>
    <ol id="synthesis-list">
      __SYNTHESIS_HTML__
    </ol>
  </div>
  <div id="stats">
    __STATS_HTML__
  </div>
  <div id="legend">
    <div class="legend-row"><div class="legend-dot" style="background:#1d4ed8"></div> Low entropy (certain)</div>
    <div class="legend-row"><div class="legend-dot" style="background:#dc2626"></div> High entropy (uncertain)</div>
    <div class="legend-row"><div class="legend-dot" style="background:#6b7280; opacity:0.45; border: 1.5px dashed #9ca3af"></div> Rabbit-hole (pruned)</div>
  </div>
</div>

<script src="https://d3js.org/d3.v7.min.js"></script>
<script>
const GRAPH_DATA = __GRAPH_JSON__;

const DOMAIN_COLORS = __DOMAIN_COLORS_JSON__;

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

// Build nodes and links from graph data
const nodeMap = {};
GRAPH_DATA.nodes.forEach(n => nodeMap[n.id] = n);

const nodes = GRAPH_DATA.nodes.map(n => ({
  ...n,
  color: n.is_rabbit_hole ? '#374151' : entropyColor(n.entropy_score),
  radius: n.depth === 0 ? 22 : Math.max(10, 18 - n.depth * 2),
}));

// Build edges from parent_id relationships + any explicit edges
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
if (GRAPH_DATA.edges) {
  GRAPH_DATA.edges.forEach(e => {
    const key = e.parent_id + '->' + e.child_id;
    if (!linkSet.has(key)) {
      linkSet.add(key);
      links.push({ source: e.parent_id, target: e.child_id,
                    contradiction: e.contradiction_flag || false });
    }
  });
}

const svg = d3.select('#svg');
const width  = document.getElementById('graph-container').clientWidth;
const height = document.getElementById('graph-container').clientHeight;

const g = svg.append('g');

// Zoom + pan
svg.call(d3.zoom().scaleExtent([0.2, 4]).on('zoom', e => g.attr('transform', e.transform)));

// Force simulation
const sim = d3.forceSimulation(nodes)
  .force('link', d3.forceLink(links).id(d => d.id).distance(d => 90 + d.target.depth * 10))
  .force('charge', d3.forceManyBody().strength(-260))
  .force('center', d3.forceCenter(width / 2, height / 2))
  .force('collision', d3.forceCollide().radius(d => d.radius + 8));

// Links
const link = g.append('g')
  .selectAll('line')
  .data(links)
  .join('line')
  .attr('class', d => 'link' + (d.contradiction ? ' contradiction' : ''));

// Arrow marker for contradiction links
svg.append('defs').append('marker')
  .attr('id', 'arrow-red')
  .attr('markerWidth', 8).attr('markerHeight', 8)
  .attr('refX', 14).attr('refY', 3)
  .attr('orient', 'auto')
  .append('path').attr('d', 'M0,0 L0,6 L8,3 z').attr('fill', '#ef4444');

// Nodes
const nodeG = g.append('g')
  .selectAll('.node')
  .data(nodes)
  .join('g')
  .attr('class', d => 'node' + (d.is_rabbit_hole ? ' rabbit-hole' : ''))
  .call(d3.drag()
    .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; })
    .on('drag',  (e, d) => { d.fx=e.x; d.fy=e.y; })
    .on('end',   (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }));

nodeG.append('circle')
  .attr('r', d => d.radius)
  .attr('fill', d => d.color)
  .attr('stroke', d => {
    if (d.is_rabbit_hole) return '#9ca3af';
    return d3.color(d.color).darker(0.5).toString();
  });

// Domain initial label
nodeG.append('text')
  .attr('dy', -4)
  .text(d => d.domain ? d.domain.slice(0, 4).toUpperCase() : '');

// Entropy value label
nodeG.append('text')
  .attr('class', 'depth-badge')
  .attr('dy', 8)
  .text(d => `H=${d.entropy_score.toFixed(2)}`);

// Tooltip
const tooltip = document.getElementById('tooltip');
nodeG.on('mouseover', (e, d) => {
  tooltip.style.display = 'block';
  tooltip.innerHTML = `<b>${d.domain || 'unknown'}</b> | depth ${d.depth} | H=${d.entropy_score.toFixed(3)}<br>
    <span style="color:#94a3b8">${d.claim.slice(0, 120)}${d.claim.length>120?'...':''}</span>`;
}).on('mousemove', e => {
  tooltip.style.left = (e.pageX + 12) + 'px';
  tooltip.style.top  = (e.pageY - 20) + 'px';
}).on('mouseout', () => { tooltip.style.display = 'none'; });

// Click -> sidebar
let selected = null;
nodeG.on('click', (e, d) => {
  e.stopPropagation();
  if (selected) d3.select(selected).classed('selected', false);
  selected = e.currentTarget;
  d3.select(selected).classed('selected', true);

  const tags = [];
  if (d.depth === 0)       tags.push('<span class="tag seed">SEED</span>');
  if (d.is_rabbit_hole)    tags.push('<span class="tag rabbit-hole">RABBIT HOLE</span>');

  const domColor = DOMAIN_COLORS[d.domain] || '#6b7280';
  const barPct   = Math.round(d.entropy_score * 100);
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
    ${d.parent_id ? `<div class="field"><div class="label">Parent</div>
      <div class="value" style="font-family:monospace;color:#94a3b8">${d.parent_id}</div></div>` : ''}
    <div class="field">
      <div class="label">Status</div>
      <div>${tags.join(' ') || '<span class="tag" style="background:#134e4a;color:#6ee7b7">ACTIVE</span>'}</div>
    </div>
  `;
});

sim.on('tick', () => {
  link
    .attr('x1', d => d.source.x)
    .attr('y1', d => d.source.y)
    .attr('x2', d => d.target.x)
    .attr('y2', d => d.target.y);
  nodeG.attr('transform', d => `translate(${d.x},${d.y})`);
});
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Stats helpers
# ---------------------------------------------------------------------------

def make_stats_html(nodes: list[dict], synthesis: list[str]) -> str:
    total    = len(nodes)
    seeds    = sum(1 for n in nodes if n.get("depth", 0) == 0)
    rabbits  = sum(1 for n in nodes if n.get("is_rabbit_hole"))
    avg_ent  = sum(n.get("entropy_score", 0) for n in nodes) / max(1, total)

    items = [
        (total,          "Nodes"),
        (seeds,          "Seeds"),
        (rabbits,        "Pruned"),
        (f"{avg_ent:.2f}", "Avg H"),
    ]
    parts = []
    for val, label in items:
        parts.append(
            f'<div class="stat"><div class="n">{val}</div><div class="l">{label}</div></div>'
        )
    return "\n".join(parts)


def make_synthesis_html(synthesis: list[str]) -> str:
    if not synthesis:
        return "<li style='color:var(--muted)'>(no synthesis)</li>"
    return "\n".join(f"<li>{dx}</li>" for dx in synthesis)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Visualize an Apiro belief graph as an interactive HTML file."
    )
    parser.add_argument("graph_json", help="Path to graph JSON (e.g. data/graph_investigate.json)")
    parser.add_argument("--out",  default=None, help="Output HTML path (default: <graph>.html)")
    parser.add_argument("--open", action="store_true", help="Open in browser after generating")
    args = parser.parse_args()

    graph_path = args.graph_json
    if not os.path.exists(graph_path):
        print(f"[-] File not found: {graph_path}")
        sys.exit(1)

    data = load_graph(graph_path)
    nodes     = data.get("nodes", [])
    synthesis = data.get("synthesis", [])

    case_name = Path(graph_path).stem.replace("graph_", "").replace("_", " ").title()

    out_path = args.out or str(Path(graph_path).with_suffix(".html"))

    # Prepare template values
    graph_json_str    = json.dumps(data)
    domain_colors_str = json.dumps(DOMAIN_COLORS)
    synthesis_html    = make_synthesis_html(synthesis)
    stats_html        = make_stats_html(nodes, synthesis)

    html = HTML_TEMPLATE.replace("__CASE_NAME__", case_name)\
                        .replace("__GRAPH_JSON__", graph_json_str)\
                        .replace("__DOMAIN_COLORS_JSON__", domain_colors_str)\
                        .replace("__SYNTHESIS_HTML__", synthesis_html)\
                        .replace("__STATS_HTML__", stats_html)

    with open(out_path, "w") as f:
        f.write(html)

    print(f"[+] Visualization saved: {out_path}")
    print(f"    Nodes: {len(nodes)}")
    print(f"    Open with: xdg-open {out_path}")

    if args.open:
        webbrowser.open(f"file://{os.path.abspath(out_path)}")


if __name__ == "__main__":
    main()
