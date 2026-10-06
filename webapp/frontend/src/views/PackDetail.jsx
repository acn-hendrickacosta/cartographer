import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiError, getPackDetail } from '../api.js';

export default function PackDetail({ contentType, user }) {
  const { name } = useParams();
  const [detail, setDetail] = useState(null);
  const [notFound, setNotFound] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    setDetail(null);
    setNotFound(false);
    setError(null);
    getPackDetail(name, contentType)
      .then(setDetail)
      .catch((e) => {
        if (e instanceof ApiError && e.status === 404) {
          setNotFound(true); // no published version of this type yet -- still a valid place to start a first draft
        } else {
          setError(e.message);
        }
      });
  }, [name, contentType]);

  const isAuthor = user && user.groups && user.groups.includes('Author');

  if (error) {
    return (
      <div className="view active">
        <Link className="back-link" to={`/${contentType}`}>&larr; Back to {contentType}</Link>
        <div className="empty">{error}</div>
      </div>
    );
  }

  if (notFound) {
    return (
      <div className="view active">
        <div className="view-header">
          <Link className="back-link" to={`/${contentType}`}>&larr; Back to {contentType}</Link>
          <h2>{name}</h2>
          <p>No published {contentType} for this pack yet.</p>
        </div>
        {isAuthor && (
          <Link className="btn" to={`/${contentType}/${name}/drafts/new`}>+ New file</Link>
        )}
      </div>
    );
  }

  if (!detail) {
    return <div className="view active"><div className="empty">Loading…</div></div>;
  }

  const files = Object.entries(detail.files).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="view active">
      <div className="view-header">
        <Link className="back-link" to={`/${contentType}`}>&larr; Back to {contentType}</Link>
        <h2>{detail.name} <span className="mono-cell">v{detail.version}</span></h2>
        {detail.metadata && (
          <p className="pack-meta">
            Published {detail.metadata.published_at} by {detail.metadata.published_by}
            <span className="changelog"> {detail.metadata.changelog}</span>
          </p>
        )}
        <p><Link to={`/${contentType}/${name}/versions`}>Version history &rarr;</Link></p>
        {isAuthor && (
          <p><Link className="btn secondary" to={`/${contentType}/${name}/drafts/new`}>+ New file</Link></p>
        )}
      </div>

      <div className="file-list">
        {files.length === 0 && <div className="empty">No {contentType} published for this pack.</div>}
        {files.map(([filename, content]) => (
          <FileCard key={filename} filename={filename} content={content} contentType={contentType} name={name} canEdit={isAuthor} />
        ))}
      </div>
    </div>
  );
}

function FileCard({ filename, content, contentType, name, canEdit }) {
  return (
    <details className="file-card">
      <summary>
        {filename}
        {canEdit && (
          <Link
            className="btn secondary edit-link"
            to={`/${contentType}/${name}/drafts/new?file=${encodeURIComponent(filename)}`}
            onClick={(e) => e.stopPropagation()}
          >
            Edit
          </Link>
        )}
      </summary>
      <pre>{content}</pre>
    </details>
  );
}
