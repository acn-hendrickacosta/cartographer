import { useEffect, useState } from 'react';
import { getAdminUsers, setUserGroups } from '../api.js';
import { ROLES } from './roles.js';

export default function AdminUsers() {
  const [users, setUsers] = useState(null);
  const [error, setError] = useState(null);
  const [busyEmail, setBusyEmail] = useState(null);

  function load() {
    getAdminUsers().then(setUsers).catch((e) => setError(e.message));
  }

  useEffect(load, []);

  async function toggleRole(user, role) {
    const groups = user.groups.includes(role)
      ? user.groups.filter((g) => g !== role)
      : [...user.groups, role];
    setBusyEmail(user.email);
    setError(null);
    try {
      const updated = await setUserGroups(user.email, groups);
      setUsers((prev) => prev.map((u) => (u.email === updated.email ? updated : u)));
    } catch (e) {
      setError(e.message);
    } finally {
      setBusyEmail(null);
    }
  }

  if (error) return <div className="empty">{error}</div>;
  if (users === null) return <div className="empty">Loading…</div>;
  if (users.length === 0) return <div className="empty">No users found.</div>;

  return (
    <table>
      <thead>
        <tr><th>Email</th><th>Roles</th></tr>
      </thead>
      <tbody>
        {users.map((u) => (
          <tr key={u.email}>
            <td>{u.email}</td>
            <td>
              {ROLES.map((role) => (
                <button
                  key={role}
                  className={`chip chip-toggle${u.groups.includes(role) ? ' active' : ''}${role === 'Admin' ? ' role-admin' : ''}`}
                  onClick={() => toggleRole(u, role)}
                  disabled={busyEmail === u.email}
                >
                  {role}
                </button>
              ))}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
