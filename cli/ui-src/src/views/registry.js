import { api } from '../api.js';
import { escapeHtml, errorBanner } from '../utils.js';
import { projectState } from '../sidebar.js';

function skeletonTable() {
  const row = `<div class="skel" style="height:32px;margin-bottom:6px"></div>`;
  return `<div>${row.repeat(3)}</div>`;
}

export function mountRegistry(container) {
  container.innerHTML = `
    <div class="view-header">
      <h2>Registry</h2>
      <p>All Cartographer projects registered on this machine.</p>
    </div>
    <div id="registry-content">${skeletonTable()}</div>
  `;
  loadRegistry();
}

export async function loadRegistry() {
  const el = document.getElementById('registry-content');
  if (!el) return;
  try {
    const data = await api.registry();
    if (!data.projects || data.projects.length === 0) {
      el.innerHTML = '<div class="empty">No projects registered on this machine yet.</div>';
      return;
    }
    el.innerHTML = `<table>
      <tr><th>Name</th><th>Topology</th><th>Tenant</th><th>Location</th></tr>
      ${data.projects.map(p => `<tr class="${p.location === projectState.workspace ? 'current-row' : ''}">
        <td>${escapeHtml(p.name || '')} ${p.location === projectState.workspace ? '<span class="chip">current</span>' : ''}</td>
        <td><span class="chip topology-${escapeHtml(p.topology || 'local')}">${escapeHtml(p.topology || '')}</span></td>
        <td>${escapeHtml(p.tenant || '')}</td>
        <td class="mono-cell">${escapeHtml(p.location || '')}</td>
      </tr>`).join('')}
    </table>`;
  } catch (err) {
    el.innerHTML = errorBanner('Failed to load registry', err);
  }
}
