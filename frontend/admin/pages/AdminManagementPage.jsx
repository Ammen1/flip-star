import { useState, useEffect } from 'react';
import { Shield, UserPlus, UserMinus, Search } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';

export function AdminManagementPage({ theme }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });
  const [search, setSearch] = useState('');

  useEffect(() => {
    loadUsers();
  }, [search]);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/admin/users/?search=${search}`);
      setUsers(response.users);
    } catch (error) {
      console.error('Failed to load users:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleAdmin = async (userId, currentStatus) => {
    setAlertModal({
      isOpen: true,
      title: `${currentStatus ? 'Revoke' : 'Grant'} Admin Privileges`,
      message: `Are you sure you want to ${currentStatus ? 'revoke' : 'grant'} admin privileges for this user?`,
      type: 'warning',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(`/admin/users/${userId}/update/`, {
            method: 'PATCH',
            body: JSON.stringify({ is_staff: !currentStatus })
          });
          loadUsers();
          setAlertModal({ ...alertModal, isOpen: false });
        } catch (error) {
          console.error('Failed to update admin status:', error);
          setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to update admin status', type: 'error' });
        }
      }
    });
  };

  const handleToggleSuperuser = async (userId, currentStatus) => {
    setAlertModal({
      isOpen: true,
      title: `${currentStatus ? 'Revoke' : 'Grant'} Superuser Privileges`,
      message: `Are you sure you want to ${currentStatus ? 'revoke' : 'grant'} superuser privileges for this user?`,
      type: 'warning',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(`/admin/users/${userId}/update/`, {
            method: 'PATCH',
            body: JSON.stringify({ is_superuser: !currentStatus })
          });
          loadUsers();
          setAlertModal({ ...alertModal, isOpen: false });
        } catch (error) {
          console.error('Failed to update superuser status:', error);
          setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to update superuser status', type: 'error' });
        }
      }
    });
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          margin: 0,
          fontSize: 32,
          fontWeight: 700,
          color: theme.txt,
          marginBottom: 8,
        }}>
          Admin Management
        </h1>
        <p style={{
          margin: 0,
          fontSize: 16,
          color: theme.sub,
        }}>
          Manage admin users and permissions
        </p>
      </div>

      {/* Search */}
      <div style={{
        marginBottom: 24,
        position: 'relative',
        maxWidth: 400,
      }}>
        <Search size={20} style={{
          position: 'absolute',
          left: 16,
          top: '50%',
          transform: 'translateY(-50%)',
          color: theme.sub,
        }} />
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search users..."
          style={{
            width: '100%',
            padding: '12px 16px 12px 48px',
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            fontSize: 14,
            outline: 'none',
          }}
        />
      </div>

      {/* Admin Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 24,
        marginBottom: 32,
      }}>
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: theme.sub, marginBottom: 8 }}>
            Total Admins
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: theme.pri }}>
            {users.filter(u => u.is_staff).length}
          </div>
        </div>
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{ fontSize: 14, fontWeight: 600, color: theme.sub, marginBottom: 8 }}>
            Superusers
          </div>
          <div style={{ fontSize: 32, fontWeight: 700, color: theme.red }}>
            {users.filter(u => u.is_superuser).length}
          </div>
        </div>
      </div>

      {/* Users List */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
          Loading users...
        </div>
      ) : (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          border: `1px solid ${theme.border}`,
          overflow: 'hidden',
        }}>
          <table style={{ width: '100%', borderCollapse: 'collapse' }}>
            <thead>
              <tr style={{ background: theme.bg }}>
                <th style={headerStyle}>User</th>
                <th style={headerStyle}>Email</th>
                <th style={headerStyle}>Status</th>
                <th style={headerStyle}>Permissions</th>
                <th style={headerStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {users.map((user, index) => (
                <tr key={user.id} style={{
                  borderTop: index > 0 ? `1px solid ${theme.border}` : 'none',
                }}>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                      <div style={{
                        width: 40,
                        height: 40,
                        borderRadius: '50%',
                        background: user.is_staff ? theme.pri + '30' : theme.sub + '20',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 18,
                      }}>
                        {user.is_staff ? '👑' : '👤'}
                      </div>
                      <div>
                        <div style={{
                          fontSize: 14,
                          fontWeight: 600,
                          color: theme.txt,
                        }}>
                          {user.username}
                        </div>
                      </div>
                    </div>
                  </td>
                  <td style={cellStyle}>
                    <div style={{ fontSize: 13, color: theme.txt }}>
                      {user.email}
                    </div>
                  </td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      {user.is_staff && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          background: theme.pri + '20',
                          color: theme.pri,
                        }}>
                          Admin
                        </span>
                      )}
                      {user.is_superuser && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          background: theme.red + '20',
                          color: theme.red,
                        }}>
                          Superuser
                        </span>
                      )}
                      {!user.is_staff && !user.is_superuser && (
                        <span style={{
                          padding: '4px 8px',
                          borderRadius: 4,
                          fontSize: 11,
                          fontWeight: 600,
                          background: theme.sub + '20',
                          color: theme.sub,
                        }}>
                          Regular User
                        </span>
                      )}
                    </div>
                  </td>
                  <td style={cellStyle}>
                    <div style={{ fontSize: 13, color: theme.sub }}>
                      {user.is_superuser ? 'Full Access' : user.is_staff ? 'Admin Access' : 'No Admin Access'}
                    </div>
                  </td>
                  <td style={cellStyle}>
                    <div style={{ display: 'flex', gap: 8 }}>
                      <button
                        onClick={() => handleToggleAdmin(user.id, user.is_staff)}
                        style={{
                          padding: '6px 12px',
                          background: user.is_staff ? theme.orange + '15' : theme.pri + '15',
                          border: 'none',
                          borderRadius: 6,
                          color: user.is_staff ? theme.orange : theme.pri,
                          fontSize: 12,
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        {user.is_staff ? <UserMinus size={14} /> : <UserPlus size={14} />}
                        {user.is_staff ? 'Revoke Admin' : 'Make Admin'}
                      </button>
                      {user.is_staff && (
                        <button
                          onClick={() => handleToggleSuperuser(user.id, user.is_superuser)}
                          style={{
                            padding: '6px 12px',
                            background: user.is_superuser ? theme.red + '15' : theme.purple + '15',
                            border: 'none',
                            borderRadius: 6,
                            color: user.is_superuser ? theme.red : theme.purple,
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                          }}
                        >
                          <Shield size={14} />
                          {user.is_superuser ? 'Revoke Super' : 'Make Super'}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

const headerStyle = {
  padding: '16px',
  textAlign: 'left',
  fontSize: 13,
  fontWeight: 700,
  color: '#78716C',
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const cellStyle = {
  padding: '16px',
  fontSize: 14,
};




