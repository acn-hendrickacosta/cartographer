import { api } from './api.js';
import { escapeHtml } from './utils.js';
import { NODE_COLORS, DEFAULT_NODE_COLOR } from './graph.js';

// Whole-file nodes (module/doc/spec) laid out as a directory tree — a second
// way into the graph besides "already know what to search for."
export async function mountTree(container, onSelectFile) {
  container.innerHTML = `
    <input id="tree-filter" type="text" placeholder="Filter files…">
    <div id="tree-root" class="file-tree"></div>
  `;
  const filterInput = container.querySelector('#tree-filter');
  const root = container.querySelector('#tree-root');
  const expanded = new Set();
  let allFiles = [];

  root.innerHTML = '<div class="empty">Loading…</div>';

  root.addEventListener('click', (e) => {
    const dir = e.target.closest('.tree-dir');
    if (dir) {
      const path = dir.dataset.path;
      if (expanded.has(path)) expanded.delete(path); else expanded.add(path);
      draw(filterInput.value.trim().toLowerCase());
      return;
    }
    const file = e.target.closest('.tree-file');
    if (file) onSelectFile(file.dataset.nodeId);
  });

  filterInput.addEventListener('input', () => draw(filterInput.value.trim().toLowerCase()));

  try {
    const data = await api.files();
    allFiles = data.files || [];
    draw('');
  } catch (err) {
    root.innerHTML = '<div class="empty">Failed to load files.</div>';
  }

  function draw(filter) {
    const files = filter ? allFiles.filter(f => f.path.toLowerCase().includes(filter)) : allFiles;
    if (!files.length) {
      root.innerHTML = `<div class="empty">No files match “${escapeHtml(filter)}”.</div>`;
      return;
    }
    const tree = buildTree(files);
    root.innerHTML = renderChildren(tree, 0, !!filter, expanded);
  }
}

function buildTree(files) {
  const root = { children: new Map(), file: null };
  for (const f of files) {
    const parts = f.path.split('/');
    let node = root;
    parts.forEach((part, i) => {
      if (!node.children.has(part)) node.children.set(part, { name: part, children: new Map(), file: null });
      node = node.children.get(part);
      if (i === parts.length - 1) node.file = f;
    });
  }
  return root;
}

function renderChildren(node, depth, forceOpen, expanded, ancestors = []) {
  const entries = [...node.children.values()].sort((a, b) => {
    const aDir = !a.file, bDir = !b.file;
    if (aDir !== bDir) return aDir ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
  return entries.map(child => {
    const path = [...ancestors, child.name].join('/');
    if (child.file) {
      const color = (NODE_COLORS[child.file.type] || {}).color || DEFAULT_NODE_COLOR;
      return `<div class="tree-row tree-file" style="padding-left:${depth * 16 + 10}px" data-node-id="${escapeHtml(child.file.id)}" title="${escapeHtml(child.file.path)}">
        <span class="tree-dot" style="background:${color}"></span>${escapeHtml(child.name)}
      </div>`;
    }
    const open = forceOpen || expanded.has(path);
    return `<div class="tree-row tree-dir" style="padding-left:${depth * 16 + 10}px" data-path="${escapeHtml(path)}">
      <span class="tree-chevron ${open ? 'open' : ''}">›</span>${escapeHtml(child.name)}
    </div>
    ${open ? renderChildren(child, depth + 1, forceOpen, expanded, [...ancestors, child.name]) : ''}`;
  }).join('');
}
