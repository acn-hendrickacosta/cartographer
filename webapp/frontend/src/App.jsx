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
import { getMe } from './api.js';

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
          <div className="view active">
            <div className="view-header">
              <h2>Cartographer Standards</h2>
              <p>Sign in to browse published standards, skills, and agents.</p>
            </div>
            <a className="btn" href="/login">Log in</a>
          </div>
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
