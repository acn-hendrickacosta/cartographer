import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getPacks } from '../api.js';

const LABELS = { standards: 'Standards Packs', skills: 'Skills', agents: 'Agents' };

export default function PackList({ contentType }) {
  const [packs, setPacks] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setPacks(null);
    setError(null);
    getPacks(contentType).then(setPacks).catch((e) => setError(e.message));
  }, [contentType]);

  return (
    <div className="view active">
      <div className="view-header">
        <h2>{LABELS[contentType]}</h2>
        <p>Published {contentType} available to cartographer stack add</p>
      </div>
      {error && <div className="empty">{error}</div>}
      {!error && packs === null && <div className="empty">Loading…</div>}
      {!error && packs && packs.length === 0 && <div className="empty">No packs published yet.</div>}
      {!error && packs && packs.length > 0 && (
        <table>
          <thead>
            <tr><th>Pack</th><th>Latest version</th></tr>
          </thead>
          <tbody>
            {packs.map((pack) => (
              <tr key={pack.name}>
                <td><Link to={`/${contentType}/${pack.name}`}>{pack.name}</Link></td>
                <td className="mono-cell">{pack.version}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
