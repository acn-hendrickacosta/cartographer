import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { getPackVersions } from '../api.js';

export default function VersionHistory({ contentType }) {
  const { name } = useParams();
  const [versions, setVersions] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    setVersions(null);
    setError(null);
    getPackVersions(name, contentType).then(setVersions).catch((e) => setError(e.message));
  }, [name, contentType]);

  return (
    <div className="view active">
      <div className="view-header">
        <Link className="back-link" to={`/${contentType}/${name}`}>&larr; Back to {name}</Link>
        <h2>{name}: version history</h2>
      </div>
      {error && <div className="empty">{error}</div>}
      {!error && versions === null && <div className="empty">Loading…</div>}
      {!error && versions && (
        <table>
          <thead>
            <tr><th>Version</th><th>Published at</th><th>Published by</th><th>Changelog</th></tr>
          </thead>
          <tbody>
            {versions.map((v) => (
              <tr key={v.version}>
                <td className="mono-cell">{v.version}</td>
                <td className="mono-cell">{v.metadata?.published_at}</td>
                <td>{v.metadata?.published_by}</td>
                <td>{v.metadata?.changelog}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
