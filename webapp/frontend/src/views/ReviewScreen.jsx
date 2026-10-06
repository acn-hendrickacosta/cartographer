import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { addComment, approveDraft, getComments, getDraft, getPackDetail, publishDraft, rejectDraft } from '../api.js';

export default function ReviewScreen({ user }) {
  const { draftId } = useParams();
  const navigate = useNavigate();

  const [draft, setDraft] = useState(null);
  const [publishedContent, setPublishedContent] = useState(null); // null = no prior published version of this file
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    load();
  }, [draftId]); // eslint-disable-line react-hooks/exhaustive-deps

  async function load() {
    setError(null);
    try {
      const d = await getDraft(draftId);
      setDraft(d);
      const cs = await getComments(draftId);
      setComments(cs);
      try {
        const packDetail = await getPackDetail(d.pack_name, d.content_type);
        setPublishedContent(packDetail.files[d.file_name] ?? null);
      } catch {
        setPublishedContent(null); // pack/content type has no published version yet -- fine, this is a new file
      }
    } catch (e) {
      setError(e.message);
    }
  }

  const isOwnDraft = draft && user && draft.author_email === user.email;

  async function handleApprove() {
    setBusy(true);
    try {
      const updated = await approveDraft(draftId);
      setDraft(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleReject() {
    const comment = window.prompt('Reason for rejecting (required):');
    if (!comment || !comment.trim()) return;
    setBusy(true);
    try {
      const updated = await rejectDraft(draftId, comment);
      setDraft(updated);
      setComments(await getComments(draftId));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePublish() {
    if (!window.confirm(`Publish ${draft.pack_name} ${draft.content_type} v${draft.target_version}? This is immutable once published.`)) return;
    setBusy(true);
    try {
      const updated = await publishDraft(draftId);
      setDraft(updated);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddComment() {
    if (!newComment.trim()) return;
    await addComment(draftId, newComment);
    setNewComment('');
    setComments(await getComments(draftId));
  }

  if (error) return <div className="view active"><div className="empty">{error}</div></div>;
  if (!draft) return <div className="view active"><div className="empty">Loading…</div></div>;

  return (
    <div className="view active">
      <div className="view-header">
        <Link className="back-link" to="/review">&larr; Back to review queue</Link>
        <h2>{draft.pack_name} / {draft.file_name} <span className="mono-cell">v{draft.target_version}</span></h2>
        <p className="pack-meta">
          {draft.content_type} · by {draft.author_email} · state: {draft.state}
        </p>
      </div>

      <div className="diff-panes">
        <div className="diff-pane">
          <h3>Published</h3>
          <pre>{publishedContent ?? '(no published version of this file yet)'}</pre>
        </div>
        <div className="diff-pane">
          <h3>Draft</h3>
          <pre>{draft.content}</pre>
        </div>
      </div>

      <div className="comment-thread">
        <h3>Comments</h3>
        {comments.length === 0 && <p className="pack-meta">No comments yet.</p>}
        {comments.map((c) => (
          <div key={c.id} className="comment">
            <strong>{c.author_email}</strong> <span className="mono-cell">{c.created_at}</span>
            <p>{c.body}</p>
          </div>
        ))}
        <textarea value={newComment} onChange={(e) => setNewComment(e.target.value)} rows={3} placeholder="Add a comment…" />
        <button className="btn secondary" onClick={handleAddComment} disabled={!newComment.trim()}>Add comment</button>
      </div>

      {draft.state === 'IN_REVIEW' && (
        <div className="editor-actions">
          <button className="btn" onClick={handleApprove} disabled={busy || isOwnDraft} title={isOwnDraft ? "You cannot approve your own draft" : ''}>
            Approve
          </button>
          <button className="btn secondary" onClick={handleReject} disabled={busy || isOwnDraft}>Reject</button>
        </div>
      )}
      {draft.state === 'APPROVED' && (
        <div className="editor-actions">
          <button className="btn" onClick={handlePublish} disabled={busy}>Confirm publish</button>
        </div>
      )}
      {draft.state === 'PUBLISHED' && <div className="empty">Published. This draft is now historical -- the registry is the source of truth.</div>}
    </div>
  );
}
