async function getJson(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

export const api = {
  project: () => getJson('/api/project'),
  search: (q, k = 20) => getJson('/api/search?q=' + encodeURIComponent(q) + '&k=' + k),
  graph: (nodeId, depth) => getJson('/api/graph?node_id=' + encodeURIComponent(nodeId) + '&depth=' + depth),
  files: () => getJson('/api/files'),
  registry: () => getJson('/api/registry'),
  stats: () => getJson('/api/stats'),
};
