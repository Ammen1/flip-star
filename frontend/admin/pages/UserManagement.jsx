import { useState, useEffect } from 'react';
import { Search, Edit2, Trash2, Shield, Ban, CheckCircle, XCircle, Crown } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';

export function UserManagement({ theme }) {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);
  const [selectedUser, setSelectedUser] = useState(null);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', onConfirm: null });

  useEffect(() => {
    loadUsers();
  }, [page, search]);

  const loadUsers = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/admin/users/?page=${page}&search=${search}`);
      setUsers(response.users);
      setTotalPages(response.total_pages);
    } catch (error) {
      console.error('Failed to load users:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggleActive = async (userId, currentStatus) => {
    try {
      await api.request(`/admin/users/${userId}/update/`, {
        method: 'PATCH',
        body: JSON.stringify({ is_active: !currentStatus })
      });
      loadUsers();
    } catch (error) {
      console.error('Failed to update user:', error);
    }
  };

  const handleDeleteUser = (userId) => {
    setAlertModal({
      isOpen: true,
      title: 'Delete User',
      message: 'Are you sure you want to delete this user? This action cannot be undone.',
      type: 'error',
      onConfirm: async () => {
        try {
          await api.request(`/admin/users/${userId}/delete/`, { method: 'DELETE' });
          loadUsers();
        } catch (error) {
          console.error('Failed to delete user:', error);
        }
      }
    });
  };

  const handleUpgradeSubscription = async (userId, plan) => {
    try {
      await api.request(`/admin/subscriptions/${userId}/upgrade/`, {
        method: 'POST',
        body: JSON.stringify({ plan, days: 30 })
      });
      loadUsers();
    } catch (error) {
      console.error('Failed to upgrade subscription:', error);
    }
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
          User Management
        </h1>
        <p style={{
          margin: 0,
          fontSize: 16,
          color: theme.sub,
        }}>
          Manage users, subscriptions, and permissions
        </p>
      </div>

      {/* Search Bar */}
      <div style={{
        marginBottom: 24,
        display: 'flex',
        gap: 16,
        alignItems: 'center',
      }}>
        <div style={{ position: 'relative', flex: 1, maxWidth: 400 }}>
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
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            placeholder="Search users by name, email, or username..."
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
      </div>

      {/* Users Table */}
      <div style={{
        background: theme.card,
        borderRadius: 12,
        border: `1px solid ${theme.border}`,
        overflow: 'hidden',
      }}>
        <div style={{
          overflowX: 'auto',
        }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
          }}>
            <thead>
              <tr style={{ background: theme.bg }}>
                <th style={headerStyle}>User</th>
                <th style={headerStyle}>Email</th>
                <th style={headerStyle}>Stats</th>
                <th style={headerStyle}>Subscription</th>
                <th style={headerStyle}>Status</th>
                <th style={headerStyle}>Actions</th>
              </tr>
            </thead>
            <tbody>
              {loading ? (
                <tr>
                  <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
                    Loading users...
                  </td>
                </tr>
              ) : users.length === 0 ? (
                <tr>
                  <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
                    No users found
                  </td>
                </tr>
              ) : (
                users.map((user) => (
                  <tr key={user.id} style={{
                    borderTop: `1px solid ${theme.border}`,
                  }}>
                    <td style={cellStyle}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                        <div style={{
                          width: 40,
                          height: 40,
                          borderRadius: '50%',
                          background: theme.pri + '30',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          fontSize: 18,
                        }}>
                          👤
                        </div>
                        <div>
                          <div style={{
                            fontSize: 14,
                            fontWeight: 600,
                            color: theme.txt,
                            display: 'flex',
                            alignItems: 'center',
                            gap: 6,
                          }}>
                            {user.username}
                            {user.is_staff && (
                              <Shield size={14} color={theme.pri} />
                            )}
                          </div>
                          <div style={{
                            fontSize: 12,
                            color: theme.sub,
                          }}>
                            Level {user.level} • {user.xp} XP
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
                      <div style={{ fontSize: 13, color: theme.sub }}>
                        {user.reel_count} reels • {user.follower_count} followers
                      </div>
                    </td>
                    <td style={cellStyle}>
                      <span style={{
                        padding: '4px 12px',
                        borderRadius: 12,
                        fontSize: 12,
                        fontWeight: 600,
                        background: user.subscription === 'premium' ? theme.pri + '20' : 
                                   user.subscription === 'pro' ? theme.blue + '20' : 
                                   theme.sub + '20',
                        color: user.subscription === 'premium' ? theme.pri : 
                               user.subscription === 'pro' ? theme.blue : 
                               theme.sub,
                        textTransform: 'capitalize',
                      }}>
                        {user.subscription}
                      </span>
                    </td>
                    <td style={cellStyle}>
                      {user.is_active ? (
                        <CheckCircle size={20} color={theme.green} />
                      ) : (
                        <XCircle size={20} color={theme.red} />
                      )}
                    </td>
                    <td style={cellStyle}>
                      <div style={{ display: 'flex', gap: 8 }}>
                        <button
                          onClick={() => handleToggleActive(user.id, user.is_active)}
                          style={{
                            padding: '6px 12px',
                            background: user.is_active ? theme.red + '15' : theme.green + '15',
                            border: 'none',
                            borderRadius: 6,
                            color: user.is_active ? theme.red : theme.green,
                            fontSize: 12,
                            fontWeight: 600,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 4,
                          }}
                        >
                          {user.is_active ? <Ban size={14} /> : <CheckCircle size={14} />}
                          {user.is_active ? 'Suspend' : 'Activate'}
                        </button>
                        {user.subscription === 'free' && (
                          <button
                            onClick={() => handleUpgradeSubscription(user.id, 'pro')}
                            style={{
                              padding: '6px 12px',
                              background: theme.pri + '15',
                              border: 'none',
                              borderRadius: 6,
                              color: theme.pri,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                            }}
                          >
                            <Crown size={14} />
                            Upgrade
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteUser(user.id)}
                          style={{
                            padding: '6px',
                            background: 'transparent',
                            border: 'none',
                            borderRadius: 6,
                            color: theme.red,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                          }}
                        >
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination */}
        {totalPages > 1 && (
          <div style={{
            padding: 16,
            borderTop: `1px solid ${theme.border}`,
            display: 'flex',
            justifyContent: 'center',
            gap: 8,
          }}>
            <button
              onClick={() => setPage(p => Math.max(1, p - 1))}
              disabled={page === 1}
              style={{
                padding: '8px 16px',
                background: page === 1 ? theme.bg : theme.pri,
                border: 'none',
                borderRadius: 6,
                color: page === 1 ? theme.sub : '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: page === 1 ? 'not-allowed' : 'pointer',
              }}
            >
              Previous
            </button>
            <span style={{
              padding: '8px 16px',
              fontSize: 14,
              fontWeight: 600,
              color: theme.txt,
            }}>
              Page {page} of {totalPages}
            </span>
            <button
              onClick={() => setPage(p => Math.min(totalPages, p + 1))}
              disabled={page === totalPages}
              style={{
                padding: '8px 16px',
                background: page === totalPages ? theme.bg : theme.pri,
                border: 'none',
                borderRadius: 6,
                color: page === totalPages ? theme.sub : '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: page === totalPages ? 'not-allowed' : 'pointer',
              }}
            >
              Next
            </button>
          </div>
        )}
      </div>
      
      <AlertModal
        isOpen={alertModal.isOpen}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
        onClose={() => setAlertModal({ isOpen: false })}
        onConfirm={alertModal.onConfirm}
      />
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




