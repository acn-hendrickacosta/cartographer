import * as d3 from 'd3';
import { api } from './api.js';
import { escapeHtml } from './utils.js';

// Node types are whole-file/whole-doc nodes (module/doc/spec) or finer-grained
// nodes extracted from them (symbol/concept/stub). Keep in sync with the type
// strings written in ingestion/graph_extractor.py.
// A topographic map-legend palette (slate, forest, rust, teal, plum, gold)
// rather than generic SaaS indigo/neon — this is a mapping tool, so the
// categorical colors are drawn from that vernacular instead of a default hue wheel.
export const NODE_COLORS = {
  module:  { color: '#5b7ba8', label: 'Module — a source file' },
  doc:     { color: '#4f9d6e', label: 'Doc — a markdown/text file' },
  spec:    { color: '#c17a45', label: 'Spec — a spec/requirements file' },
  symbol:  { color: '#3f9c9c', label: 'Symbol — a function or class' },
  concept: { color: '#9a6bab', label: 'Concept — a named idea extracted from a doc' },
  stub:    { color: '#c2a53a', label: 'Stub — a referenced module/spec not yet ingested' },
};
export const DEFAULT_NODE_COLOR = '#75705f';

// Edge `type` values as written by graph_extractor.py. "relates_to" and other
// custom strings come from LLM-extracted doc relationships and aren't fixed.
export const EDGE_MEANINGS = {
  defines: 'file defines this symbol',
  calls: 'function/method calls another',
  imports: 'file imports a module',
  extends: 'class extends a parent class',
  implements_spec: 'file implements a spec/concept',
  depends_on: 'file depends on a concept',
};

const DEFAULT_DETAIL_HTML = '<span class="detail-hint">Click a node, or hover an edge, to see details.</span>';

export function renderLegend(el) {
  const nodeRows = Object.entries(NODE_COLORS).map(([, { color, label }]) =>
    `<div class="legend-row"><span class="swatch" style="background:${color}"></span>${escapeHtml(label)}</div>`
  ).join('');
  const edgeTerms = Object.entries(EDGE_MEANINGS).map(([type, meaning]) =>
    `<abbr title="${escapeHtml(meaning)}">${escapeHtml(type)}</abbr>`
  ).join('');
  el.innerHTML = `
    <div class="legend-title">Node types</div>
    ${nodeRows}
    <div class="legend-row"><span class="swatch" style="background:${DEFAULT_NODE_COLOR}"></span>Other</div>
    <div class="legend-title" style="margin-top:8px">Relationships</div>
    <div class="edge-terms">${edgeTerms}</div>
    <div class="legend-hint">Hover any edge in the graph for its exact relationship.</div>
  `;
}

/**
 * Owns one graph canvas: rendering, zoom/pan, hover/click detail, and a
 * back-navigable history stack so clicking through the graph feels like
 * browsing rather than repeatedly re-querying from scratch.
 */
export function createGraphPane({ svgEl, detailEl, nodeInputEl, depthEl, backBtn, onNavigate }) {
  const historyStack = [];
  let currentNodeId = null;
  let resetView = () => {};

  function updateBackButton() {
    backBtn.disabled = historyStack.length === 0;
  }

  async function loadGraph(nodeId) {
    const depth = depthEl.value;
    svgEl.innerHTML = '';
    detailEl.innerHTML = DEFAULT_DETAIL_HTML;

    try {
      const data = await api.graph(nodeId, depth);
      if (!data.nodes || data.nodes.length === 0) {
        svgEl.innerHTML = '<text x="20" y="40" fill="var(--text-faint)">No node found with that ID. Try a real ID from a search result.</text>';
        return;
      }
      renderD3(data);
    } catch (err) {
      svgEl.innerHTML = `<text x="20" y="40" fill="#f06868">Error: ${escapeHtml(String(err))}</text>`;
    }
  }

  function navigateTo(nodeId, { fresh = false } = {}) {
    if (fresh) {
      historyStack.length = 0;
    } else if (currentNodeId && currentNodeId !== nodeId) {
      historyStack.push(currentNodeId);
    }
    currentNodeId = nodeId;
    nodeInputEl.value = nodeId;
    updateBackButton();
    loadGraph(nodeId);
    if (onNavigate) onNavigate(nodeId);
  }

  function goBack() {
    if (!historyStack.length) return;
    currentNodeId = historyStack.pop();
    nodeInputEl.value = currentNodeId;
    updateBackButton();
    loadGraph(currentNodeId);
  }

  function renderD3(data) {
    const rect = svgEl.getBoundingClientRect();
    const w = rect.width || 700, h = rect.height || 400;
    const svg = d3.select(svgEl).attr('width', w).attr('height', h);
    const gRoot = svg.append('g');

    const zoom = d3.zoom().scaleExtent([0.15, 5]).on('zoom', (event) => gRoot.attr('transform', event.transform));
    svg.call(zoom);
    resetView = () => svg.transition().duration(300).call(zoom.transform, d3.zoomIdentity);

    const nodes = (data.nodes || []).map(n => ({ ...n }));
    // API returns edges as {src, dst, type}; forceLink's default accessors expect source/target.
    const edges = (data.edges || []).map(e => ({ source: e.src, target: e.dst, type: e.type }));

    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(edges).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-220))
      .force('center', d3.forceCenter(w / 2, h / 2));

    const link = gRoot.append('g').selectAll('line').data(edges).enter().append('line')
      .attr('stroke', '#3a3a5a').attr('stroke-width', 1.5);

    // Wider invisible line layered on top, so hovering near an edge (not just
    // the exact 1.5px center) still registers. Native SVG <title> tooltips are
    // unreliable across browsers, so hover/click write into the detail panel.
    const linkHit = gRoot.append('g').selectAll('line').data(edges).enter().append('line')
      .attr('stroke', 'transparent').attr('stroke-width', 10)
      .style('cursor', 'pointer')
      .on('mouseenter', (event, d) => {
        // forceLink() mutates d.source/d.target from id strings into node
        // object references as soon as the force is attached above.
        const srcId = d.source.id || d.source, dstId = d.target.id || d.target;
        const meaning = EDGE_MEANINGS[d.type] ? ` — ${EDGE_MEANINGS[d.type]}` : '';
        detailEl.innerHTML = `<div class="d-id">${escapeHtml(d.type || '')}${escapeHtml(meaning)}</div>` +
          `<div class="d-meta">${escapeHtml(srcId)}<br>&nbsp;&nbsp;→ ${escapeHtml(dstId)}</div>`;
      })
      .on('mouseleave', () => { detailEl.innerHTML = DEFAULT_DETAIL_HTML; });

    const node = gRoot.append('g').selectAll('circle').data(nodes).enter().append('circle')
      .attr('r', 8).attr('fill', d => (NODE_COLORS[d.type] || {}).color || DEFAULT_NODE_COLOR)
      .attr('stroke', '#ffffff33').attr('stroke-width', 1)
      .style('cursor', 'pointer')
      .on('mouseenter click', (event, d) => {
        const isCurrent = d.id === currentNodeId;
        detailEl.innerHTML = `<div class="d-id">${escapeHtml(d.id || '')}</div>` +
          `<div class="d-meta">type: ${escapeHtml(d.type || '')} &nbsp; scope: ${escapeHtml(d.scope || '')}<br>path: ${escapeHtml(d.path || '')}</div>` +
          (isCurrent ? '' : `<button class="btn secondary explore-from-btn" data-node-id="${escapeHtml(d.id || '')}">Explore from here<span class="btn-icon">→</span></button>`);
        const exploreBtn = detailEl.querySelector('.explore-from-btn');
        if (exploreBtn) exploreBtn.addEventListener('click', () => navigateTo(exploreBtn.dataset.nodeId));
      })
      .call(d3.drag()
        .on('start', (e, d) => { if (!e.active) sim.alphaTarget(0.3).restart(); d.fx = d.x; d.fy = d.y; })
        .on('drag', (e, d) => { d.fx = e.x; d.fy = e.y; })
        .on('end', (e, d) => { if (!e.active) sim.alphaTarget(0); d.fx = null; d.fy = null; })
      );

    const label = gRoot.append('g').selectAll('text').data(nodes).enter().append('text')
      .attr('font-size', 10).attr('fill', '#a0a0c0').attr('dy', -11)
      .text(d => (d.id || '').split(':').pop().split('/').pop().slice(0, 22));

    sim.on('tick', () => {
      link.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
          .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      linkHit.attr('x1', d => d.source.x).attr('y1', d => d.source.y)
             .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      node.attr('cx', d => d.x).attr('cy', d => d.y);
      label.attr('x', d => d.x).attr('y', d => d.y);
    });
  }

  backBtn.addEventListener('click', goBack);
  updateBackButton();

  return {
    navigateTo,
    resetView: () => resetView(),
  };
}
