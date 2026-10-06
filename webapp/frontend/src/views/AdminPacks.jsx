import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { createPack, deprecatePack, getAdminPacks } from '../api.js';

export default function AdminPacks() {
  const [packs, setPacks] = useState(null);
  const [error, setError] = useState(null);
  const [newName, setNewName] = useState('');
  const [busy, setBusy] = useState(false);

  function load() {
    getAdminPacks().then(setPacks).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function handleCreate(e) {
    e.preventDefault();
    if (!newName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const pack = await createPack(newName.trim());
      setPacks((prev) => [...prev, pack].sort((a, b) => a.name.localeCompare(b.name)));
      setNewName('');
    } catch (e2) {
      setError(e2.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDeprecate(name) {
    if (!window.confirm(`Deprecate pack '${name}'? New drafts against it will be rejected; existing content is unaffected.`)) return;
    setBusy(true);
    setError(null);
    try {
      const pack = await deprecatePack(name);
      setPacks((prev) => prev.map((p) => (p.name === pack.name ? pack : p)));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <form className="admin-create-form" onSubmit={handleCreate}>
        <input
          type="text"
          value={newName}
          onChange={(e) => setNewName(e.target.value)}
          placeholder="new-pack-name"
          disabled={busy}
        />
        <button className="btn" type="submit" disabled={busy || !newName.trim()}>Create pack</button>
      </form>

      {error && <div className="empty">{error}</div>}
      {!error && packs === null && <div className="empty">Loading…</div>}
      {!error && packs && packs.length > 0 && (
        <table>
          <thead>
            <tr><th>Name</th><th>Created</th><th>Status</th><th></th></tr>
          </thead>
          <tbody>
            {packs.map((p) => (
              <tr key={p.name}>
                <td>
                  <Link to={`/standards/${p.name}`}>{p.name}</Link>
                </td>
                <td className="mono-cell">{p.created_at}</td>
                <td>{p.deprecated_at ? <span className="chip">deprecated</span> : <span className="chip chip-toggle active">active</span>}</td>
                <td>
                  {!p.deprecated_at && (
                    <button className="btn secondary" onClick={() => handleDeprecate(p.name)} disabled={busy}>Deprecate</button>
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
