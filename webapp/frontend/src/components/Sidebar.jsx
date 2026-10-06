import { NavLink } from 'react-router-dom';

const NAV_ITEMS = [
  {
    to: '/standards',
    label: 'Standards',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20" />
        <path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2z" />
      </svg>
    ),
  },
  {
    to: '/skills',
    label: 'Skills',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="7" />
        <path d="M12 8v4l2.5 2.5" />
      </svg>
    ),
  },
  {
    to: '/agents',
    label: 'Agents',
    icon: (
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="4" y="7" width="16" height="13" rx="2" />
        <path d="M9 7V4h6v3M9 14h.01M15 14h.01" />
      </svg>
    ),
  },
];

const REVIEW_NAV_ITEM = {
  to: '/review',
  label: 'Review queue',
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  ),
};

const ADMIN_NAV_ITEM = {
  to: '/admin',
  label: 'Admin',
  icon: (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  ),
};

export default function Sidebar({ user }) {
  const isReviewer = user && user.groups && user.groups.includes('Reviewer');
  const isAdmin = user && user.groups && user.groups.includes('Admin');
  let navItems = NAV_ITEMS;
  if (isReviewer) navItems = [...navItems, REVIEW_NAV_ITEM];
  if (isAdmin) navItems = [...navItems, ADMIN_NAV_ITEM];

  return (
    <aside className="sidebar">
      <div className="brand">
        <div className="brand-mark">C</div>
        <div className="brand-name">Standards</div>
      </div>

      {user && (
        <div className="project-info">
          <div className="p-name">{user.email}</div>
          <div className="p-path">registry access</div>
          {user.groups && user.groups.length > 0 ? (
            user.groups.map((g) => (
              <span key={g} className={`chip${g === 'Admin' ? ' role-admin' : ''}`}>{g}</span>
            ))
          ) : (
            <span className="chip">no role</span>
          )}
        </div>
      )}

      <nav className="side-nav">
        {navItems.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          >
            {item.icon}
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="sidebar-footer">
        standards registry
        {user && (
          <>
            <br />
            <a href="/logout">Log out</a>
          </>
        )}
      </div>
    </aside>
  );
}
