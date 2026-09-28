export function escapeHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

export function errorBanner(title, err) {
  return `<div class="error-banner"><span class="err-icon">⚠</span><div><strong>${escapeHtml(title)}</strong><br>${escapeHtml(String(err))}</div></div>`;
}

// VDB chunk ids are "<artifact_id>#<ordinal>"; KG nodes are keyed by artifact_id alone.
export function chunkIdToNodeId(chunkId) {
  return chunkId.replace(/#\d+$/, '');
}
