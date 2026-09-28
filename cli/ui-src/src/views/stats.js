import { api } from '../api.js';
import { escapeHtml, errorBanner } from '../utils.js';

export function mountStats(container) {
  container.innerHTML = `
    <div class="view-header">
      <h2>Stats</h2>
      <p>Counts by type, for this project's local index.</p>
    </div>
    <div id="stats-content">${skeletonStats()}</div>
  `;
  loadStats();
}

function skeletonStats() {
  const bar = `<div class="skel" style="height:14px;margin-bottom:10px"></div>`;
  const card = `<div class="stats-card">${bar.repeat(4)}</div>`;
  return `<div class="stats-grid">${card}${card}</div>`;
}

function statRows(counts) {
  const entries = Object.entries(counts);
  if (!entries.length) return '<div class="empty" style="padding:14px">No data indexed yet</div>';
  const max = Math.max(...entries.map(([, c]) => c));
  return entries.sort((a, b) => b[1] - a[1]).map(([type, count]) => `
    <div class="stat-row">
      <span class="stat-label">${escapeHtml(type)}</span>
      <span class="stat-bar-track"><span class="stat-bar-fill" style="width:${max ? (count / max * 100) : 0}%"></span></span>
      <span class="stat-count">${count}</span>
    </div>`).join('');
}

export async function loadStats() {
  const el = document.getElementById('stats-content');
  if (!el) return;
  try {
    const data = await api.stats();
    const vdb = data.vdb || {};
    const kg = data.kg || {};
    const vdbTotal = Object.values(vdb).reduce((a, b) => a + b, 0);
    const kgTotal = Object.values(kg).reduce((a, b) => a + b, 0);
    el.innerHTML = `
      <div class="stats-grid">
        <div class="stats-card">
          <h3>Vector store</h3>
          <div class="stats-total">${vdbTotal} chunk${vdbTotal === 1 ? '' : 's'} total</div>
          ${statRows(vdb)}
        </div>
        <div class="stats-card">
          <h3>Knowledge graph</h3>
          <div class="stats-total">${kgTotal} node${kgTotal === 1 ? '' : 's'} total</div>
          ${statRows(kg)}
        </div>
      </div>`;
  } catch (err) {
    el.innerHTML = errorBanner('Failed to load stats', err);
  }
}
