import { useEffect, useState } from 'react';
import { Navigate, Route, Routes } from 'react-router-dom';
import Sidebar from './components/Sidebar.jsx';
import PackList from './views/PackList.jsx';
import PackDetail from './views/PackDetail.jsx';
import VersionHistory from './views/VersionHistory.jsx';
import PackEditor from './views/PackEditor.jsx';
import ReviewQueue from './views/ReviewQueue.jsx';
import ReviewScreen from './views/ReviewScreen.jsx';
import AdminLayout from './views/AdminLayout.jsx';
import AdminUsers from './views/AdminUsers.jsx';
import AdminPacks from './views/AdminPacks.jsx';
import AdminTokens from './views/AdminTokens.jsx';
import { getMe, login } from './api.js';

function LoginForm({ onLoggedIn }) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError('');
    setSubmitting(true);
    try {
      const user = await login(email, password);
      onLoggedIn(user);
    } catch (err) {
      setError(err.message || 'login failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="view active">
      <div className="view-header">
        <h2>Cartographer Standards</h2>
        <p>Sign in to browse published standards, skills, and agents.</p>
      </div>
      <form onSubmit={handleSubmit} className="login-form">
        <label>
          Email
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            required
            autoComplete="username"
          />
        </label>
        <label>
          Password
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        {error && <p className="login-error">{error}</p>}
        <button className="btn" type="submit" disabled={submitting}>
          {submitting ? 'Signing in…' : 'Log in'}
        </button>
      </form>
    </div>
  );
}

export default function App() {
  // null = still checking, false = logged out, object = logged in user
  const [user, setUser] = useState(null);

  useEffect(() => {
    getMe().then(setUser).catch(() => setUser(false));
  }, []);

  if (user === null) {
    return (
      <>
        <div className="bg-glow" aria-hidden="true" />
        <main className="content"><div className="view active"><div className="empty">Loading…</div></div></main>
      </>
    );
  }

  if (user === false) {
    return (
      <>
        <div className="bg-glow" aria-hidden="true" />
        <main className="content">
          <LoginForm onLoggedIn={setUser} />
        </main>
      </>
    );
  }

  return (
    <>
      <div className="bg-glow" aria-hidden="true" />
      <Sidebar user={user} />
      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to="/standards" replace />} />
          {['standards', 'skills', 'agents'].map((contentType) => (
            <Route key={contentType} path={`/${contentType}`}>
              <Route index element={<PackList contentType={contentType} />} />
              <Route path=":name" element={<PackDetail contentType={contentType} user={user} />} />
              <Route path=":name/versions" element={<VersionHistory contentType={contentType} />} />
              <Route path=":name/drafts/new" element={<PackEditor contentType={contentType} />} />
              <Route path=":name/drafts/:draftId/edit" element={<PackEditor contentType={contentType} />} />
            </Route>
          ))}
          <Route path="/review" element={<ReviewQueue />} />
          <Route path="/review/:draftId" element={<ReviewScreen user={user} />} />
          {user.groups && user.groups.includes('Admin') && (
            <Route path="/admin" element={<AdminLayout />}>
              <Route index element={<Navigate to="users" replace />} />
              <Route path="users" element={<AdminUsers />} />
              <Route path="packs" element={<AdminPacks />} />
              <Route path="tokens" element={<AdminTokens />} />
            </Route>
          )}
        </Routes>
      </main>
    </>
  );
}
