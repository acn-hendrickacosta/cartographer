// Thin fetch wrapper for the backend's JSON API (../backend/app/main.py).
// Same-origin in production (SPA is served by the same FastAPI app); the dev
// server proxies /api to a locally-running backend (see vite.config.js).

class ApiError extends Error {
  constructor(status, detail) {
    super(detail || `request failed with ${status}`);
    this.status = status;
  }
}

async function request(path, options = {}) {
  const resp = await fetch(path, {
    credentials: 'same-origin',
    headers: options.body ? { 'Content-Type': 'application/json' } : undefined,
    ...options,
  });
  if (!resp.ok) {
    let detail;
    try {
      detail = (await resp.json()).detail;
    } catch {
      detail = resp.statusText;
    }
    throw new ApiError(resp.status, detail);
  }
  if (resp.status === 204) return null;
  return resp.json();
}

export function getMe() {
  return request('/api/me');
}

export function login(email, password) {
  return request('/api/login', { method: 'POST', body: JSON.stringify({ email, password }) });
}

export function getPacks(contentType) {
  return request(`/api/packs?type=${encodeURIComponent(contentType)}`);
}

export function getPackDetail(name, contentType) {
  return request(`/api/packs/${encodeURIComponent(name)}/${encodeURIComponent(contentType)}`);
}

export function getPackVersions(name, contentType) {
  return request(`/api/packs/${encodeURIComponent(name)}/${encodeURIComponent(contentType)}/versions`);
}

// ---- SR.3: drafts, review, publish ----

export function createDraft(body) {
  return request('/api/drafts', { method: 'POST', body: JSON.stringify(body) });
}

export function getDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}`);
}

export function updateDraft(id, body) {
  return request(`/api/drafts/${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(body) });
}

export function discardDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}`, { method: 'DELETE' });
}

export function submitDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}/submit`, { method: 'POST' });
}

export function reviseDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}/revise`, { method: 'POST' });
}

export function getReviewQueue() {
  return request('/api/review-queue');
}

export function getComments(draftId) {
  return request(`/api/drafts/${encodeURIComponent(draftId)}/comments`);
}

export function addComment(draftId, body) {
  return request(`/api/drafts/${encodeURIComponent(draftId)}/comments`, { method: 'POST', body: JSON.stringify({ body }) });
}

export function approveDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}/approve`, { method: 'POST' });
}

export function rejectDraft(id, comment) {
  return request(`/api/drafts/${encodeURIComponent(id)}/reject`, { method: 'POST', body: JSON.stringify({ comment }) });
}

export function publishDraft(id) {
  return request(`/api/drafts/${encodeURIComponent(id)}/publish`, { method: 'POST' });
}

// ---- SR.4: admin ----

export function getAdminUsers() {
  return request('/api/admin/users');
}

export function setUserGroups(email, groups) {
  return request(`/api/admin/users/${encodeURIComponent(email)}`, { method: 'PATCH', body: JSON.stringify({ groups }) });
}

export function getAdminPacks() {
  return request('/api/admin/packs');
}

export function createPack(name) {
  return request('/api/admin/packs', { method: 'POST', body: JSON.stringify({ name }) });
}

export function deprecatePack(name) {
  return request(`/api/admin/packs/${encodeURIComponent(name)}/deprecate`, { method: 'POST' });
}

export function getAdminTokens() {
  return request('/api/admin/tokens');
}

export function issueToken(projectId) {
  return request('/api/admin/tokens', { method: 'POST', body: JSON.stringify({ project_id: projectId }) });
}

export function revokeToken(tokenHash) {
  return request(`/api/admin/tokens/${encodeURIComponent(tokenHash)}/revoke`, { method: 'POST' });
}

export { ApiError };
