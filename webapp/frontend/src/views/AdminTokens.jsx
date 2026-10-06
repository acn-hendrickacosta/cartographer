import { useEffect, useState } from 'react';
import { getAdminTokens, issueToken, revokeToken } from '../api.js';

export default function AdminTokens() {
  const [tokens, setTokens] = useState(null);
  const [error, setError] = useState(null);
  const [projectId, setProjectId] = useState('');
  const [busy, setBusy] = useState(false);
  const [issued, setIssued] = useState(null); // raw token value, shown once

  function load() {
    getAdminTokens().then(setTokens).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function handleIssue(e) {
    e.preventDefault();
    if (!projectId.trim()) return;
    setBusy(true);
    setError(null);
    setIssued(null);
    try {
      const { token } = await issueToken(projectId.trim());
      setIssued(token);
      setProjectId('');
      load();
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleRevoke(tokenHash) {
    if (!window.confirm('Revoke this token? Any CLI using it will immediately lose registry access.')) return;
    setBusy(true);
    setError(null);
    try {
      await revokeToken(tokenHash);
      load();
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="admin-create-form" onSubmit={handleIssue}>
        <input
          type="text"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          placeholder="project id"
          disabled={busy}
        />
        <button className="btn" type="submit" disabled={busy || !projectId.trim()}>Issue token</button>
      </form>

      {issued && (
        <div className="empty" style={{ borderStyle: 'solid' }}>
          Copy this token now -- it will not be shown again:
          <pre className="mono-cell">{issued}</pre>
        </div>
      )}

      {error && <div className="empty">{error}</div>}
      {!error && tokens === null && <div className="empty">Loading…</div>}
      {!error && tokens && tokens.length === 0 && <div className="empty">No tokens issued yet.</div>}
      {!error && tokens && tokens.length > 0 && (
        <table>
          <thead>
            <tr><th>Project</th><th>Created</th><th>Last used</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {tokens.map((t) => (
              <tr key={t.token_hash}>
                <td>{t.project_id}</td>
                <td className="mono-cell">{t.created_at}</td>
                <td className="mono-cell">{t.last_used_at || '—'}</td>
                <td>{t.revoked_at ? <span className="chip">revoked</span> : <span className="chip chip-toggle active">active</span>}</td>
                <td>
                  {!t.revoked_at && (
                    <button className="btn secondary" onClick={() => handleRevoke(t.token_hash)} disabled={busy}>Revoke</button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
