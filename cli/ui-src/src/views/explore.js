import { api } from '../api.js';
import { escapeHtml, debounce, errorBanner, chunkIdToNodeId } from '../utils.js';
import { createGraphPane, renderLegend } from '../graph.js';
import { mountTree } from '../tree.js';

const ARTIFACT_TYPE_CLASS = { doc: 'doc', code: 'code', spec: 'spec' };
let allResults = [];
let activeFilter = '';
let graphPane = null;
let treeMounted = false;

export function mountExplore(container) {
  container.innerHTML = `
    <div class="explore">
      <div class="explore-left">
        <div class="view-header">
          <h2>Explore</h2>
          <p>Search your knowledge base or browse the file tree, then follow anything into its graph neighborhood.</p>
        </div>
        <div class="mode-toggle" id="mode-toggle">
          <button class="mode-tab active" data-mode="search">Search</button>
          <button class="mode-tab" data-mode="browse">Browse</button>
        </div>
        <div id="mode-search">
          <div class="search-bar">
            <input id="search-input" type="text" placeholder="Search… ( / to focus)">
          </div>
          <div class="filter-chips" id="filter-chips">
            <button class="filter-chip active" data-type="">All</button>
            <button class="filter-chip" data-type="doc">Doc</button>
            <button class="filter-chip" data-type="code">Code</button>
            <button class="filter-chip" data-type="spec">Spec</button>
          </div>
          <div id="search-summary"></div>
          <div id="search-results" class="search-results"></div>
        </div>
        <div id="mode-browse" class="tree-panel" style="display:none"></div>
      </div>
      <div class="explore-right">
        <div class="graph-toolbar">
          <button id="graph-back" class="btn secondary" title="Back to the previous node"><span class="btn-icon">←</span>Back</button>
          <input id="graph-node-input" type="text" placeholder="Node ID — or click a result on the left">
          <select id="graph-depth">
            <option value="1">depth 1</option>
            <option value="2">depth 2</option>
            <option value="3">depth 3</option>
          </select>
          <button id="graph-load" class="btn">Load</button>
          <button id="graph-reset" class="btn secondary">Reset view</button>
        </div>
        <div class="graph-canvas-wrap">
          <svg id="graph-svg"></svg>
          <div id="graph-legend" class="legend-popover"></div>
        </div>
        <div id="node-detail"><span class="detail-hint">Click a node, or hover an edge, to see details.</span></div>
      </div>
    </div>
  `;

  const searchInput = container.querySelector('#search-input');
  const nodeInput = container.querySelector('#graph-node-input');
  const depthSel = container.querySelector('#graph-depth');
  const backBtn = container.querySelector('#graph-back');
  const svgEl = container.querySelector('#graph-svg');
  const detailEl = container.querySelector('#node-detail');
  const legendEl = container.querySelector('#graph-legend');

  renderLegend(legendEl);

  graphPane = createGraphPane({
    svgEl, detailEl, nodeInputEl: nodeInput, depthEl: depthSel, backBtn,
  });

  const searchPanel = container.querySelector('#mode-search');
  const browsePanel = container.querySelector('#mode-browse');
  container.querySelectorAll('.mode-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      container.querySelectorAll('.mode-tab').forEach(t => t.classList.remove('active'));
      tab.classList.add('active');
      const browsing = tab.dataset.mode === 'browse';
      searchPanel.style.display = browsing ? 'none' : '';
      browsePanel.style.display = browsing ? '' : 'none';
      if (browsing && !treeMounted) {
        treeMounted = true;
        mountTree(browsePanel, (nodeId) => graphPane.navigateTo(nodeId, { fresh: true }));
      }
    });
  });

  container.querySelector('#graph-load').addEventListener('click', () => {
    const id = nodeInput.value.trim();
    if (id) graphPane.navigateTo(id, { fresh: true });
  });
  nodeInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') container.querySelector('#graph-load').click();
  });
  container.querySelector('#graph-reset').addEventListener('click', () => graphPane.resetView());

  const runSearch = debounce(() => doSearch(searchInput.value.trim()), 300);
  searchInput.addEventListener('input', runSearch);
  searchInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') { clearFilters(); doSearch(searchInput.value.trim()); }
  });

  container.querySelectorAll('.filter-chip').forEach(chip => {
    chip.addEventListener('click', () => {
      container.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
      chip.classList.add('active');
      activeFilter = chip.dataset.type;
      renderResults();
    });
  });

  // Global "/" focuses search unless already typing somewhere.
  document.addEventListener('keydown', (e) => {
    if (e.key === '/' && document.activeElement.tagName !== 'INPUT') {
      e.preventDefault();
      searchInput.focus();
    }
  });
}

function clearFilters() {
  activeFilter = '';
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.toggle('active', c.dataset.type === ''));
}

async function doSearch(q) {
  const summary = document.getElementById('search-summary');
  const container = document.getElementById('search-results');
  if (!q) {
    summary.textContent = '';
    container.innerHTML = '';
    allResults = [];
    return;
  }
  container.innerHTML = skeletonCards(3);
  try {
    const data = await api.search(q, 20);
    allResults = data.results || [];
    renderResults(q);
  } catch (err) {
    summary.textContent = '';
    container.innerHTML = errorBanner('Search failed', err);
  }
}

function skeletonCards(n) {
  return Array.from({ length: n }).map(() => `<div class="skel" style="height:76px"></div>`).join('<div style="height:2px"></div>');
}

function renderResults(q) {
  const summary = document.getElementById('search-summary');
  const container = document.getElementById('search-results');
  const results = activeFilter ? allResults.filter(r => r.artifact_type === activeFilter) : allResults;

  if (allResults.length === 0) {
    summary.textContent = '';
    container.innerHTML = q ? `<div class="empty">No results for “${escapeHtml(q)}”.</div>` : '';
    return;
  }
  if (results.length === 0) {
    summary.textContent = `0 of ${allResults.length} results match this filter`;
    container.innerHTML = '<div class="empty">Nothing matches this filter.</div>';
    return;
  }
  summary.textContent = `${results.length} result${results.length === 1 ? '' : 's'}${activeFilter ? ` (filtered from ${allResults.length})` : ''}`;

  container.innerHTML = results.map((r, i) => {
    const score = r._distance !== undefined ? Math.max(0, 1 - r._distance) : null;
    const typeClass = ARTIFACT_TYPE_CLASS[r.artifact_type] || 'unknown';
    const text = escapeHtml(r.text || '');
    const isLong = (r.text || '').length > 220;
    return `
    <div class="result-card" data-idx="${i}" style="--i:${i}">
      <div class="meta">
        <span class="type-chip ${typeClass}">${escapeHtml(r.artifact_type || 'unknown')}</span>
        <span class="path">${escapeHtml(r.path || '')}</span>
        ${r.symbol ? '<span class="symbol">' + escapeHtml(r.symbol) + '</span>' : ''}
        ${score !== null ? `<span class="score-wrap"><span class="score-track"><span class="score-fill" style="width:${(score * 100).toFixed(0)}%"></span></span>${score.toFixed(2)}</span>` : ''}
      </div>
      <div class="text" id="text-${i}">${text}${isLong ? '<div class="text-fade"></div>' : ''}</div>
      ${isLong ? `<button class="show-more" data-idx="${i}">Show more</button>` : ''}
    </div>`;
  }).join('');

  container.querySelectorAll('.show-more').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const el = document.getElementById('text-' + btn.dataset.idx);
      el.classList.toggle('expanded');
      btn.textContent = el.classList.contains('expanded') ? 'Show less' : 'Show more';
    });
  });
  container.querySelectorAll('.result-card').forEach(card => {
    card.addEventListener('click', () => {
      const r = results[Number(card.dataset.idx)];
      container.querySelectorAll('.result-card').forEach(c => c.classList.remove('selected'));
      card.classList.add('selected');
      graphPane.navigateTo(chunkIdToNodeId(r.id || ''), { fresh: true });
    });
  });
}
