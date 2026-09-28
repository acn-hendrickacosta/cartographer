import { api } from './api.js';
import { escapeHtml } from './utils.js';

export const projectState = { workspace: '' };

export function initSidebar(onShow) {
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.nav-item').forEach(b => b.classList.remove('active'));
      document.querySelectorAll('.view').forEach(v => v.classList.remove('active'));
      btn.classList.add('active');
      const name = btn.dataset.view;
      document.getElementById('view-' + name).classList.add('active');
      onShow(name);
    });
  });

  loadProjectInfo();
}

async function loadProjectInfo() {
  const el = document.getElementById('project-info');
  try {
    const p = await api.project();
    projectState.workspace = p.workspace || '';
    el.innerHTML = `
      <div class="p-name">${escapeHtml(p.name || p.id || 'unknown')}</div>
      <div class="p-path" title="${escapeHtml(p.workspace || '')}">${escapeHtml(p.workspace || '')}</div>
      <span class="chip topology-${escapeHtml(p.topology || 'local')}">${escapeHtml(p.topology || 'local')}</span>
    `;
  } catch (err) {
    el.innerHTML = '<div class="p-name" style="color:var(--danger)">Failed to load project</div>';
  }
}
