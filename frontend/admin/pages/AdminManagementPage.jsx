import { useState, useEffect } from 'react';
import { Shield, UserPlus, UserMinus, Search, Users, Key, FileText, Settings, Plus, Edit, Trash2 } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';

export function AdminManagementPage({ theme }) {
  const [activeTab, setActiveTab] = useState('users');
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });
  const [search, setSearch] = useState('');
  
  // Role CRUD state
  const [roleModal, setRoleModal] = useState({ isOpen: false, mode: 'create', role: null });
  const [roleForm, setRoleForm] = useState({ id: '', name: '', description: '', type: 'platform_user', surfaces: ['mobile'], is_active: true });

  const headerStyle = {
    padding: '16px',
    textAlign: 'left',
    fontSize: 13,
    fontWeight: 700,
    color: theme.sub,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  };

  const cellStyle = {
    padding: '16px',
    fontSize: 14,
  };

  useEffect(() => {
    loadUsers();
    loadRoles();
    loadPermissions();
    loadAuditLogs();
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

  const loadRoles = async () => {
    try {
      const response = await api.request('/admin/rbac/roles/');
      setRoles(response.results || response);
    } catch (error) {
      console.error('Failed to load roles:', error);
    }
  };

  const loadPermissions = async () => {
    try {
      const response = await api.request('/admin/rbac/permissions/');
      setPermissions(response.results || response);
    } catch (error) {
      console.error('Failed to load permissions:', error);
    }
  };

  const loadAuditLogs = async () => {
    try {
      const response = await api.request('/admin/rbac/audit-logs/');
      setAuditLogs(response.results || response);
    } catch (error) {
      console.error('Failed to load audit logs:', error);
    }
  };

  // Role CRUD functions
  const handleCreateRole = () => {
    setRoleForm({ id: '', name: '', description: '', type: 'platform_user', surfaces: ['mobile'], is_active: true });
    setRoleModal({ isOpen: true, mode: 'create', role: null });
  };

  const handleEditRole = (role) => {
    setRoleForm({
      id: role.id,
      name: role.name,
      description: role.description,
      type: role.type,
      surfaces: role.surfaces || ['mobile'],
      is_active: role.is_active,
    });
    setRoleModal({ isOpen: true, mode: 'edit', role });
  };

  const handleDeleteRole = (role) => {
    setAlertModal({
      isOpen: true,
      title: 'Delete Role',
      message: `Are you sure you want to delete the role "${role.name}"? This action cannot be undone.`,
      type: 'warning',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(`/admin/rbac/roles/${role.id}/`, { method: 'DELETE' });
          loadRoles();
          setAlertModal({ ...alertModal, isOpen: false });
        } catch (error) {
          console.error('Failed to delete role:', error);
          setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to delete role', type: 'error' });
        }
      }
    });
  };

  const handleSaveRole = async () => {
    try {
      if (roleModal.mode === 'create') {
        await api.request('/admin/rbac/roles/', {
          method: 'POST',
          body: JSON.stringify(roleForm)
        });
      } else {
        await api.request(`/admin/rbac/roles/${roleForm.id}/`, {
          method: 'PUT',
          body: JSON.stringify(roleForm)
        });
      }
      loadRoles();
      setRoleModal({ isOpen: false, mode: 'create', role: null });
    } catch (error) {
      console.error('Failed to save role:', error);
      setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to save role', type: 'error' });
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
          RBAC Management
        </h1>
        <p style={{
          margin: 0,
          fontSize: 16,
          color: theme.sub,
        }}>
          Manage roles, permissions, users, and audit logs
        </p>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 24,
        borderBottom: `1px solid ${theme.border}`,
        paddingBottom: 16,
      }}>
        {[
          { id: 'users', label: 'Users', icon: Users },
          { id: 'roles', label: 'Roles', icon: Settings },
          { id: 'permissions', label: 'Permissions', icon: Key },
          { id: 'audit', label: 'Audit Log', icon: FileText },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '10px 16px',
              border: 'none',
              borderRadius: 8,
              background: activeTab === tab.id ? theme.pri + '20' : 'transparent',
              color: activeTab === tab.id ? theme.pri : theme.sub,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              transition: 'all 0.2s',
            }}
            onMouseEnter={(e) => {
              if (activeTab !== tab.id) {
                e.target.style.background = theme.bg;
              }
            }}
            onMouseLeave={(e) => {
              if (activeTab !== tab.id) {
                e.target.style.background = 'transparent';
              }
            }}
          >
            <tab.icon size={18} />
            {tab.label}
          </button>
        ))}
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
          placeholder={`Search ${activeTab}...`}
          style={{
            width: '100%',
            padding: '12px 16px 12px 48px',
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            fontSize: 14,
            outline: 'none',
            background: theme.card,
            color: theme.txt,
          }}
        />
      </div>

      {/* Tab Content */}
      {activeTab === 'users' && (
        <>
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
                              background: user.is_staff ? theme.orange + '30' : theme.pri + '30',
                              border: `1px solid ${user.is_staff ? theme.orange : theme.pri}`,
                              borderRadius: 6,
                              color: user.is_staff ? theme.orange : theme.pri,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              transition: 'all 0.2s',
                            }}
                            onMouseEnter={(e) => {
                              e.target.style.background = user.is_staff ? theme.orange + '50' : theme.pri + '50';
                            }}
                            onMouseLeave={(e) => {
                              e.target.style.background = user.is_staff ? theme.orange + '30' : theme.pri + '30';
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
                                background: user.is_superuser ? theme.red + '30' : theme.purple + '30',
                                border: `1px solid ${user.is_superuser ? theme.red : theme.purple}`,
                                borderRadius: 6,
                                color: user.is_superuser ? theme.red : theme.purple,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                transition: 'all 0.2s',
                              }}
                              onMouseEnter={(e) => {
                                e.target.style.background = user.is_superuser ? theme.red + '50' : theme.purple + '50';
                              }}
                              onMouseLeave={(e) => {
                                e.target.style.background = user.is_superuser ? theme.red + '30' : theme.purple + '30';
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
        </>
      )}

      {activeTab === 'roles' && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: theme.txt, margin: 0 }}>
              Roles Management
            </h3>
            <button
              onClick={handleCreateRole}
              style={{
                padding: '8px 16px',
                background: theme.pri,
                border: 'none',
                borderRadius: 8,
                color: '#fff',
                fontSize: 13,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              <Plus size={16} />
              Create Role
            </button>
          </div>
          
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 16 }}>
            {roles.map((role) => (
              <div key={role.id} style={{
                background: theme.bg,
                borderRadius: 8,
                padding: 16,
                border: `1px solid ${theme.border}`,
                position: 'relative',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>
                    {role.name}
                  </div>
                  <div style={{ display: 'flex', gap: 4 }}>
                    <button
                      onClick={() => handleEditRole(role)}
                      style={{
                        padding: '4px',
                        background: 'transparent',
                        border: 'none',
                        borderRadius: 4,
                        color: theme.sub,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                      onMouseEnter={(e) => { e.target.style.color = theme.pri; e.target.style.background = theme.pri + '20'; }}
                      onMouseLeave={(e) => { e.target.style.color = theme.sub; e.target.style.background = 'transparent'; }}
                    >
                      <Edit size={14} />
                    </button>
                    <button
                      onClick={() => handleDeleteRole(role)}
                      style={{
                        padding: '4px',
                        background: 'transparent',
                        border: 'none',
                        borderRadius: 4,
                        color: theme.sub,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                      }}
                      onMouseEnter={(e) => { e.target.style.color = theme.red; e.target.style.background = theme.red + '20'; }}
                      onMouseLeave={(e) => { e.target.style.color = theme.sub; e.target.style.background = 'transparent'; }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
                <div style={{ fontSize: 12, color: theme.sub, marginBottom: 8 }}>
                  {role.description}
                </div>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 600,
                    background: theme.pri + '20',
                    color: theme.pri,
                  }}>
                    {role.type}
                  </span>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 600,
                    background: role.is_active ? '#10B98120' : '#EF444420',
                    color: role.is_active ? '#10B981' : '#EF4444',
                  }}>
                    {role.is_active ? 'Active' : 'Inactive'}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Role Modal */}
      {roleModal.isOpen && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: 20,
        }}>
          <div style={{
            background: theme.card,
            borderRadius: 12,
            padding: 24,
            width: '100%',
            maxWidth: 500,
            maxHeight: '90vh',
            overflow: 'auto',
            border: `1px solid ${theme.border}`,
          }}>
            <h3 style={{ fontSize: 18, fontWeight: 700, color: theme.txt, marginBottom: 16, margin: 0 }}>
              {roleModal.mode === 'create' ? 'Create Role' : 'Edit Role'}
            </h3>
            
            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                Role ID
              </label>
              <input
                type="text"
                value={roleForm.id}
                onChange={(e) => setRoleForm({ ...roleForm, id: e.target.value })}
                disabled={roleModal.mode === 'edit'}
                placeholder="e.g., content_manager"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                Role Name
              </label>
              <input
                type="text"
                value={roleForm.name}
                onChange={(e) => setRoleForm({ ...roleForm, name: e.target.value })}
                placeholder="e.g., Content Manager"
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                Description
              </label>
              <textarea
                value={roleForm.description}
                onChange={(e) => setRoleForm({ ...roleForm, description: e.target.value })}
                placeholder="Role description..."
                rows={3}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  background: theme.bg,
                  color: theme.txt,
                  resize: 'vertical',
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                Role Type
              </label>
              <select
                value={roleForm.type}
                onChange={(e) => setRoleForm({ ...roleForm, type: e.target.value })}
                style={{
                  width: '100%',
                  padding: '10px 12px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  background: theme.bg,
                  color: theme.txt,
                }}
              >
                <option value="platform_user">Platform User</option>
                <option value="internal_operator">Internal Operator</option>
              </select>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                Surfaces
              </label>
              <div style={{ display: 'flex', gap: 8 }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: theme.txt }}>
                  <input
                    type="checkbox"
                    checked={roleForm.surfaces.includes('mobile')}
                    onChange={(e) => {
                      const surfaces = e.target.checked 
                        ? [...roleForm.surfaces, 'mobile']
                        : roleForm.surfaces.filter(s => s !== 'mobile');
                      setRoleForm({ ...roleForm, surfaces });
                    }}
                  />
                  Mobile
                </label>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: theme.txt }}>
                  <input
                    type="checkbox"
                    checked={roleForm.surfaces.includes('web')}
                    onChange={(e) => {
                      const surfaces = e.target.checked 
                        ? [...roleForm.surfaces, 'web']
                        : roleForm.surfaces.filter(s => s !== 'web');
                      setRoleForm({ ...roleForm, surfaces });
                    }}
                  />
                  Web
                </label>
              </div>
            </div>

            <div style={{ marginBottom: 24 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: theme.txt }}>
                <input
                  type="checkbox"
                  checked={roleForm.is_active}
                  onChange={(e) => setRoleForm({ ...roleForm, is_active: e.target.checked })}
                />
                Active
              </label>
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end' }}>
              <button
                onClick={() => setRoleModal({ isOpen: false, mode: 'create', role: null })}
                style={{
                  padding: '8px 16px',
                  background: 'transparent',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.txt,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveRole}
                style={{
                  padding: '8px 16px',
                  background: theme.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Save
              </button>
            </div>
          </div>
        </div>
      )}

      {activeTab === 'permissions' && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: theme.txt, marginBottom: 16, margin: 0 }}>
            Permissions Management
          </h3>
          <p style={{ fontSize: 14, color: theme.sub, marginBottom: 24 }}>
            View all system permissions grouped by domain. Permissions are managed through the Roles tab.
          </p>
          
          {/* Group permissions by domain */}
          {Object.entries(
            permissions.reduce((acc, perm) => {
              if (!acc[perm.domain]) acc[perm.domain] = [];
              acc[perm.domain].push(perm);
              return acc;
            }, {})
          ).map(([domain, perms]) => (
            <div key={domain} style={{ marginBottom: 24 }}>
              <h4 style={{ fontSize: 14, fontWeight: 600, color: theme.pri, marginBottom: 12, margin: 0, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                {domain}
              </h4>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 12 }}>
                {perms.map((perm) => (
                  <div key={perm.id} style={{
                    background: theme.bg,
                    borderRadius: 8,
                    padding: 12,
                    border: `1px solid ${theme.border}`,
                  }}>
                    <div style={{ fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                      {perm.name}
                    </div>
                    <div style={{ fontSize: 11, color: theme.sub }}>
                      {perm.description}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}

      {activeTab === 'audit' && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <h3 style={{ fontSize: 18, fontWeight: 700, color: theme.txt, marginBottom: 16, margin: 0 }}>
            Audit Log
          </h3>
          <p style={{ fontSize: 14, color: theme.sub, marginBottom: 24 }}>
            Track all admin actions and system changes
          </p>
          
          <div style={{
            background: theme.bg,
            borderRadius: 8,
            border: `1px solid ${theme.border}`,
            overflow: 'hidden',
          }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: theme.bg }}>
                  <th style={headerStyle}>Timestamp</th>
                  <th style={headerStyle}>Action</th>
                  <th style={headerStyle}>Actor</th>
                  <th style={headerStyle}>Target</th>
                  <th style={headerStyle}>IP Address</th>
                </tr>
              </thead>
              <tbody>
                {auditLogs.slice(0, 50).map((log) => (
                  <tr key={log.id} style={{
                    borderTop: `1px solid ${theme.border}`,
                  }}>
                    <td style={cellStyle}>
                      <div style={{ fontSize: 12, color: theme.sub }}>
                        {new Date(log.timestamp).toLocaleString()}
                      </div>
                    </td>
                    <td style={cellStyle}>
                      <span style={{
                        padding: '4px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 600,
                        background: theme.pri + '20',
                        color: theme.pri,
                      }}>
                        {log.action}
                      </span>
                    </td>
                    <td style={cellStyle}>
                      <div style={{ fontSize: 13, color: theme.txt }}>
                        {log.actor_username || 'System'}
                      </div>
                    </td>
                    <td style={cellStyle}>
                      <div style={{ fontSize: 13, color: theme.sub }}>
                        {log.target_name || 'N/A'}
                      </div>
                    </td>
                    <td style={cellStyle}>
                      <div style={{ fontSize: 12, color: theme.sub }}>
                        {log.ip_address || 'N/A'}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {auditLogs.length === 0 && (
              <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
                No audit logs found
              </div>
            )}
          </div>
          {auditLogs.length > 50 && (
            <div style={{ marginTop: 16, fontSize: 13, color: theme.sub, textAlign: 'center' }}>
              Showing first 50 entries. Use the API to view more.
            </div>
          )}
        </div>
      )}
    </div>
  );
}



