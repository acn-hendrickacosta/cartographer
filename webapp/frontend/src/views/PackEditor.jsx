import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { createDraft, discardDraft, getDraft, getPackDetail, submitDraft, updateDraft } from '../api.js';

/** Handles both "start a new draft" (no draftId in the URL, ?file=<existing
 * filename> optional to prefill from the published version) and "resume an
 * existing draft" (draftId in the URL). One component because the editing
 * UI itself -- content textarea, version field, save/submit/discard -- is
 * identical either way; only how it's first populated differs. */
export default function PackEditor({ contentType }) {
  const { name, draftId } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();

  const [draft, setDraft] = useState(null); // null while loading; {id, ...} once a draft exists (even unsaved)
  const [fileName, setFileName] = useState(searchParams.get('file') || '');
  const [content, setContent] = useState('');
  const [targetVersion, setTargetVersion] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setError(null);
    if (draftId) {
      getDraft(draftId)
        .then((d) => {
          setDraft(d);
          setFileName(d.file_name);
          setContent(d.content);
          setTargetVersion(d.target_version);
        })
        .catch((e) => setError(e.message));
      return;
    }
    // New draft: prefill from the existing published file, if one was picked.
    const existingFile = searchParams.get('file');
    if (existingFile) {
      getPackDetail(name, contentType)
        .then((detail) => {
          setContent(detail.files[existingFile] || '');
          const [major, minor, patch] = (detail.version || '0.0.0').split('.').map(Number);
          setTargetVersion(`${major}.${minor}.${patch + 1}`);
        })
        .catch((e) => setError(e.message));
    } else {
      setTargetVersion('1.0.0');
    }
  }, [draftId, name, contentType]); // eslint-disable-line react-hooks/exhaustive-deps

  // Returns the current (possibly newly-created) draft -- callers need this
  // value directly rather than reading back `draft` state, since a state
  // update from setDraft() isn't visible in the same closure until the next
  // render (handleSubmit calling handleSave() and then checking `draft`
  // would still see the stale pre-save value for a brand-new draft).
  async function handleSave() {
    setBusy(true);
    setError(null);
    try {
      let result;
      if (draft) {
        result = await updateDraft(draft.id, { content, target_version: targetVersion });
      } else {
        result = await createDraft({
          pack_name: name, content_type: contentType, file_name: fileName,
          target_version: targetVersion, content,
        });
        navigate(`/${contentType}/${name}/drafts/${result.id}/edit`, { replace: true });
      }
      setDraft(result);
      return result;
    } catch (e) {
      setError(e.message);
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit() {
    setBusy(true);
    setError(null);
    try {
      const saved = await handleSave();
      if (!saved) return;
      await submitDraft(saved.id);
      navigate(`/${contentType}/${name}`);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDiscard() {
    if (!draft) {
      navigate(`/${contentType}/${name}`);
      return;
    }
    if (!window.confirm('Discard this draft?')) return;
    await discardDraft(draft.id);
    navigate(`/${contentType}/${name}`);
  }

  const locked = draft && draft.state !== 'DRAFT';

  return (
    <div className="view active">
      <div className="view-header">
        <Link className="back-link" to={`/${contentType}/${name}`}>&larr; Back to {name}</Link>
        <h2>Edit {fileName || '(new file)'} <span className="mono-cell">{contentType}</span></h2>
        {draft && <p className="pack-meta">State: {draft.state}</p>}
      </div>

      {error && <div className="empty">{error}</div>}

      {!draftId && (
        <label>
          File name
          <input type="text" value={fileName} onChange={(e) => setFileName(e.target.value)} disabled={!!draft}
                 placeholder={contentType === 'skills' ? 'my-skill/SKILL.md' : 'my-file.md'} />
        </label>
      )}
      <label>
        Target version
        <input type="text" value={targetVersion} onChange={(e) => setTargetVersion(e.target.value)} disabled={locked} />
      </label>
      <textarea
        className="editor-textarea"
        value={content}
        onChange={(e) => setContent(e.target.value)}
        disabled={locked}
        rows={24}
      />

      <div className="editor-actions">
        <button className="btn secondary" onClick={handleSave} disabled={busy || locked || !fileName}>Save</button>
        <button className="btn" onClick={handleSubmit} disabled={busy || locked || !fileName}>Submit for review</button>
        <button className="btn secondary" onClick={handleDiscard} disabled={busy || locked}>Discard draft</button>
      </div>
    </div>
  );
}
