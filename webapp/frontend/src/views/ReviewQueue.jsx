import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { getReviewQueue } from '../api.js';

export default function ReviewQueue() {
  const [drafts, setDrafts] = useState(null);
  const [error, setError] = useState(null);

  useEffect(() => {
    getReviewQueue().then(setDrafts).catch((e) => setError(e.message));
  }, []);

  return (
    <div className="view active">
      <div className="view-header">
        <h2>Review queue</h2>
        <p>Drafts submitted for review, across all packs and content types</p>
      </div>
      {error && <div className="empty">{error}</div>}
      {!error && drafts === null && <div className="empty">Loading…</div>}
      {!error && drafts && drafts.length === 0 && <div className="empty">Nothing pending review.</div>}
      {!error && drafts && drafts.length > 0 && (
        <table>
          <thead>
            <tr><th>Pack</th><th>Type</th><th>File</th><th>Version</th><th>Author</th><th>Submitted</th></tr>
          </thead>
          <tbody>
            {drafts.map((d) => (
              <tr key={d.id}>
                <td><Link to={`/review/${d.id}`}>{d.pack_name}</Link></td>
                <td>{d.content_type}</td>
                <td className="mono-cell">{d.file_name}</td>
                <td className="mono-cell">{d.target_version}</td>
                <td>{d.author_email}</td>
                <td className="mono-cell">{d.updated_at}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
