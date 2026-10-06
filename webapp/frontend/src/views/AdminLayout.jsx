import { NavLink, Outlet } from 'react-router-dom';

const TABS = [
  { to: '/admin/users', label: 'Users' },
  { to: '/admin/packs', label: 'Packs' },
  { to: '/admin/tokens', label: 'Registry tokens' },
];

export default function AdminLayout() {
  return (
    <div className="view active">
      <div className="view-header">
        <h2>Admin</h2>
        <p>User roles, pack lifecycle, and registry token management</p>
      </div>
      <div className="admin-tabs">
        {TABS.map((t) => (
          <NavLink key={t.to} to={t.to} className={({ isActive }) => `admin-tab${isActive ? ' active' : ''}`}>
            {t.label}
          </NavLink>
        ))}
      </div>
      <Outlet />
    </div>
  );
}
