import { useState, useEffect } from 'react';
import { Shield, UserPlus, UserMinus, Search, Users, Key, FileText, Settings, Plus, Edit, Trash2 } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';

export function AdminManagementPage({ theme }) {
  const [activeTab, setActiveTab] = useState(() => {
    // Restore active tab from localStorage
    const savedTab = localStorage.getItem('adminActiveTab');
    return savedTab || 'users';
  });
  const [users, setUsers] = useState([]);
  const [roles, setRoles] = useState([]);
  const [permissions, setPermissions] = useState([]);
  const [auditLogs, setAuditLogs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });
  const [search, setSearch] = useState('');
  
  // Save active tab to localStorage when it changes
  useEffect(() => {
    localStorage.setItem('adminActiveTab', activeTab);
  }, [activeTab]);
  
  // Role CRUD state
  const [roleModal, setRoleModal] = useState({ isOpen: false, mode: 'create', role: null });
  const [roleForm, setRoleForm] = useState({ id: '', name: '', description: '', type: 'platform_user', surfaces: ['mobile'], is_active: true, selectedPermissions: [] });
  
  // User role assignment state
  const [userRoleModal, setUserRoleModal] = useState({ isOpen: false, userId: null, username: '', clickPosition: { x: 0, y: 0 } });
  const [selectedUserRoles, setSelectedUserRoles] = useState([]);
  const [userCredentials, setUserCredentials] = useState({ email: '', password: '' });

  // User role assignment functions
  const handleAssignRole = (user, event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    const scrollTop = window.pageYOffset || document.documentElement.scrollTop;
    const scrollLeft = window.pageXOffset || document.documentElement.scrollLeft;
    
    // Load user's existing roles from the new API format
    const userRoles = user.roles ? user.roles.map(r => r.id) : [];
    
    setUserRoleModal({ 
      isOpen: true, 
      userId: user.id, 
      username: user.username,
      clickPosition: { x: rect.left + scrollLeft + rect.width / 2, y: rect.top + scrollTop }
    });
    setSelectedUserRoles(userRoles);
    setUserCredentials({ email: user.email || '', password: '' });
  };

  const handleSaveUserRole = async () => {
    try {
      await api.request(`/admin/rbac/users/${userRoleModal.userId}/`, {
        method: 'PUT',
        body: JSON.stringify({ 
          role_ids: selectedUserRoles,
          email: userCredentials.email,
          password: userCredentials.password,
        })
      });
      loadUsers();
      setUserRoleModal({ isOpen: false, userId: null, username: '', clickPosition: { x: 0, y: 0 } });
      setSelectedUserRoles([]);
      setUserCredentials({ email: '', password: '' });
    } catch (error) {
      console.error('Failed to assign roles:', error);
      setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to assign roles', type: 'error' });
    }
  };

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
    setRoleForm({ id: '', name: '', description: '', type: 'platform_user', surfaces: ['mobile'], is_active: true, selectedPermissions: [] });
    setRoleModal({ isOpen: true, mode: 'create', role: null });
  };

  const handleEditRole = async (role) => {
    // Load role permissions
    try {
      const response = await api.request(`/admin/rbac/role-permissions/?role_id=${role.id}`);
      const rolePermissions = response.results || response;
      const selectedPermissions = rolePermissions.map(rp => rp.permission_id);
      
      setRoleForm({
        id: role.id,
        name: role.name,
        description: role.description,
        type: role.type,
        surfaces: role.surfaces || ['mobile'],
        is_active: role.is_active,
        selectedPermissions,
      });
      setRoleModal({ isOpen: true, mode: 'edit', role });
    } catch (error) {
      console.error('Failed to load role permissions:', error);
      setRoleForm({
        id: role.id,
        name: role.name,
        description: role.description,
        type: role.type,
        surfaces: role.surfaces || ['mobile'],
        is_active: role.is_active,
        selectedPermissions: [],
      });
      setRoleModal({ isOpen: true, mode: 'edit', role });
    }
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
        // Create role
        const roleResponse = await api.request('/admin/rbac/roles/', {
          method: 'POST',
          body: JSON.stringify({
            id: roleForm.id,
            name: roleForm.name,
            description: roleForm.description,
            type: roleForm.type,
            surfaces: roleForm.surfaces,
            is_active: roleForm.is_active,
          })
        });
        
        // Create role-permission mappings
        for (const permissionId of roleForm.selectedPermissions) {
          await api.request('/admin/rbac/role-permissions/', {
            method: 'POST',
            body: JSON.stringify({
              role_id: roleForm.id,
              permission_id: permissionId,
              access_level: 'full',
            })
          });
        }
      } else {
        // Update role
        await api.request(`/admin/rbac/roles/${roleForm.id}/`, {
          method: 'PUT',
          body: JSON.stringify({
            id: roleForm.id,
            name: roleForm.name,
            description: roleForm.description,
            type: roleForm.type,
            surfaces: roleForm.surfaces,
            is_active: roleForm.is_active,
          })
        });
        
        // Delete existing role-permission mappings
        const existingMappings = await api.request(`/admin/rbac/role-permissions/?role_id=${roleForm.id}`);
        for (const mapping of existingMappings.results || existingMappings) {
          await api.request(`/admin/rbac/role-permissions/${mapping.id}/`, {
            method: 'DELETE'
          });
        }
        
        // Create new role-permission mappings
        for (const permissionId of roleForm.selectedPermissions) {
          await api.request('/admin/rbac/role-permissions/', {
            method: 'POST',
            body: JSON.stringify({
              role_id: roleForm.id,
              permission_id: permissionId,
              access_level: 'full',
            })
          });
        }
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
                      <td style={{ ...cellStyle, width: '200px', verticalAlign: 'middle' }}>
                        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
                          <button
                            onClick={(e) => handleAssignRole(user, e)}
                            style={{
                              padding: '6px 12px',
                              background: theme.purple + '30',
                              border: `1px solid ${theme.purple}`,
                              borderRadius: 6,
                              color: theme.purple,
                              fontSize: 12,
                              fontWeight: 600,
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 4,
                              transition: 'all 0.2s',
                              whiteSpace: 'nowrap',
                            }}
                            onMouseEnter={(e) => {
                              e.target.style.background = theme.purple + '50';
                            }}
                            onMouseLeave={(e) => {
                              e.target.style.background = theme.purple + '30';
                            }}
                          >
                            <Settings size={14} />
                            Assign Role
                          </button>
                          {user.is_staff && (
                            <button
                              onClick={() => handleToggleSuperuser(user.id, user.is_superuser)}
                              style={{
                                padding: '6px 12px',
                                background: user.is_superuser ? theme.red + '30' : theme.pri + '30',
                                border: `1px solid ${user.is_superuser ? theme.red : theme.pri}`,
                                borderRadius: 6,
                                color: user.is_superuser ? theme.red : theme.pri,
                                fontSize: 12,
                                fontWeight: 600,
                                cursor: 'pointer',
                                display: 'flex',
                                alignItems: 'center',
                                gap: 4,
                                transition: 'all 0.2s',
                                whiteSpace: 'nowrap',
                              }}
                              onMouseEnter={(e) => {
                                e.target.style.background = user.is_superuser ? theme.red + '50' : theme.pri + '50';
                              }}
                              onMouseLeave={(e) => {
                                e.target.style.background = user.is_superuser ? theme.red + '30' : theme.pri + '30';
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
            borderRadius: 16,
            padding: 32,
            width: '100%',
            maxWidth: 900,
            maxHeight: '90vh',
            overflow: 'auto',
            border: `1px solid ${theme.border}`,
            margin: 'auto',
            position: 'relative',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, paddingBottom: 16, borderBottom: `1px solid ${theme.border}` }}>
              <h3 style={{ fontSize: 20, fontWeight: 700, color: theme.txt, margin: 0 }}>
                {roleModal.mode === 'create' ? 'Create New Role' : 'Edit Role'}
              </h3>
              <button
                onClick={() => setRoleModal({ isOpen: false, mode: 'create', role: null })}
                style={{
                  padding: '8px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 8,
                  color: theme.sub,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.target.style.color = theme.txt; e.target.style.background = theme.bg; }}
                onMouseLeave={(e) => { e.target.style.color = theme.sub; e.target.style.background = 'transparent'; }}
              >
                ✕
              </button>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
              <div>
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
                    padding: '12px 16px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: theme.bg,
                    color: theme.txt,
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                />
              </div>

              <div>
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
                    padding: '12px 16px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: theme.bg,
                    color: theme.txt,
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                />
              </div>
            </div>

            <div style={{ marginBottom: 24 }}>
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
                  padding: '12px 16px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  background: theme.bg,
                  color: theme.txt,
                  resize: 'vertical',
                  transition: 'border-color 0.2s',
                  fontFamily: 'inherit',
                }}
                onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                onBlur={(e) => { e.target.style.borderColor = theme.border; }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                  Role Type
                </label>
                <select
                  value={roleForm.type}
                  onChange={(e) => setRoleForm({ ...roleForm, type: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: theme.bg,
                    color: theme.txt,
                    cursor: 'pointer',
                  }}
                >
                  <option value="platform_user">Platform User</option>
                  <option value="internal_operator">Internal Operator</option>
                </select>
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                  Surfaces
                </label>
                <div style={{ display: 'flex', gap: 16, padding: '12px 16px', border: `1px solid ${theme.border}`, borderRadius: 8, background: theme.bg }}>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: theme.txt, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={roleForm.surfaces.includes('mobile')}
                      onChange={(e) => {
                        const surfaces = e.target.checked 
                          ? [...roleForm.surfaces, 'mobile']
                          : roleForm.surfaces.filter(s => s !== 'mobile');
                        setRoleForm({ ...roleForm, surfaces });
                      }}
                      style={{ cursor: 'pointer' }}
                    />
                    Mobile
                  </label>
                  <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: theme.txt, cursor: 'pointer' }}>
                    <input
                      type="checkbox"
                      checked={roleForm.surfaces.includes('web')}
                      onChange={(e) => {
                        const surfaces = e.target.checked 
                          ? [...roleForm.surfaces, 'web']
                          : roleForm.surfaces.filter(s => s !== 'web');
                        setRoleForm({ ...roleForm, surfaces });
                      }}
                      style={{ cursor: 'pointer' }}
                    />
                    Web
                  </label>
                </div>
              </div>
            </div>

            <div style={{ marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12, padding: '16px', background: theme.bg, borderRadius: 8, border: `1px solid ${theme.border}` }}>
              <input
                type="checkbox"
                checked={roleForm.is_active}
                onChange={(e) => setRoleForm({ ...roleForm, is_active: e.target.checked })}
                id="role-active"
                style={{ cursor: 'pointer', width: 18, height: 18 }}
              />
              <label htmlFor="role-active" style={{ fontSize: 14, color: theme.txt, cursor: 'pointer' }}>
                Active Role
              </label>
            </div>

            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, paddingBottom: 12, borderBottom: `1px solid ${theme.border}` }}>
                <label style={{ fontSize: 15, fontWeight: 700, color: theme.txt, margin: 0 }}>
                  Assign Permissions
                </label>
                <div style={{ fontSize: 13, color: theme.sub }}>
                  {roleForm.selectedPermissions.length} of {permissions.length} selected
                </div>
              </div>
              
              <div style={{
                maxHeight: 400,
                overflow: 'auto',
                border: `1px solid ${theme.border}`,
                borderRadius: 12,
                padding: 20,
                background: theme.bg,
              }}>
                {Object.entries(
                  permissions.reduce((acc, perm) => {
                    if (!acc[perm.domain]) acc[perm.domain] = [];
                    acc[perm.domain].push(perm);
                    return acc;
                  }, {})
                ).map(([domain, perms]) => (
                  <div key={domain} style={{ marginBottom: 24 }}>
                    <div style={{ 
                      fontSize: 12, 
                      fontWeight: 700, 
                      color: theme.pri, 
                      marginBottom: 12, 
                      textTransform: 'uppercase', 
                      letterSpacing: '1px',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}>
                      <div style={{ width: 4, height: 4, background: theme.pri, borderRadius: '50%' }} />
                      {domain}
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))', gap: 8 }}>
                      {perms.map((perm) => (
                        <label key={perm.id} style={{ 
                          display: 'flex', 
                          alignItems: 'flex-start', 
                          gap: 10, 
                          fontSize: 13, 
                          color: theme.txt,
                          padding: '10px 12px',
                          borderRadius: 8,
                          background: theme.card,
                          border: `1px solid ${theme.border}`,
                          cursor: 'pointer',
                          transition: 'all 0.2s',
                        }}
                        onMouseEnter={(e) => { e.target.style.borderColor = theme.pri; e.target.style.background = theme.pri + '10'; }}
                        onMouseLeave={(e) => { e.target.style.borderColor = theme.border; e.target.style.background = theme.card; }}
                        >
                          <input
                            type="checkbox"
                            checked={roleForm.selectedPermissions.includes(perm.id)}
                            onChange={(e) => {
                              const selectedPermissions = e.target.checked
                                ? [...roleForm.selectedPermissions, perm.id]
                                : roleForm.selectedPermissions.filter(id => id !== perm.id);
                              setRoleForm({ ...roleForm, selectedPermissions });
                            }}
                            style={{ marginTop: 2, cursor: 'pointer' }}
                          />
                          <div>
                            <div style={{ fontWeight: 600, marginBottom: 2 }}>{perm.name}</div>
                            <div style={{ fontSize: 11, color: theme.sub, lineHeight: 1.4 }}>{perm.description}</div>
                          </div>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', paddingTop: 16, borderTop: `1px solid ${theme.border}` }}>
              <button
                onClick={() => setRoleModal({ isOpen: false, mode: 'create', role: null })}
                style={{
                  padding: '12px 24px',
                  background: 'transparent',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.target.style.background = theme.bg; }}
                onMouseLeave={(e) => { e.target.style.background = 'transparent'; }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveRole}
                style={{
                  padding: '12px 24px',
                  background: theme.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: `0 4px 6px -1px ${theme.pri}40`,
                }}
                onMouseEnter={(e) => { e.target.style.transform = 'translateY(-1px)'; e.target.style.boxShadow = `0 6px 8px -1px ${theme.pri}50`; }}
                onMouseLeave={(e) => { e.target.style.transform = 'translateY(0)'; e.target.style.boxShadow = `0 4px 6px -1px ${theme.pri}40`; }}
              >
                {roleModal.mode === 'create' ? 'Create Role' : 'Save Changes'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* User Role Assignment Modal */}
      {userRoleModal.isOpen && (
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
            borderRadius: 16,
            padding: 32,
            width: '100%',
            maxWidth: 700,
            maxHeight: '90vh',
            overflow: 'auto',
            border: `1px solid ${theme.border}`,
            position: 'fixed',
            left: '50%',
            top: '50%',
            transform: 'translate(-50%, -50%)',
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24, paddingBottom: 16, borderBottom: `1px solid ${theme.border}` }}>
              <h3 style={{ fontSize: 20, fontWeight: 700, color: theme.txt, margin: 0 }}>
                Manage {userRoleModal.username}
              </h3>
              <button
                onClick={() => {
                  setUserRoleModal({ isOpen: false, userId: null, username: '', clickPosition: { x: 0, y: 0 } });
                  setSelectedUserRoles([]);
                  setUserCredentials({ email: '', password: '' });
                }}
                style={{
                  padding: '8px',
                  background: 'transparent',
                  border: 'none',
                  borderRadius: 8,
                  color: theme.sub,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.target.style.color = theme.txt; e.target.style.background = theme.bg; }}
                onMouseLeave={(e) => { e.target.style.color = theme.sub; e.target.style.background = 'transparent'; }}
              >
                ✕
              </button>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 24, marginBottom: 24 }}>
              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                  Email
                </label>
                <input
                  type="email"
                  value={userCredentials.email}
                  onChange={(e) => setUserCredentials({ ...userCredentials, email: e.target.value })}
                  placeholder="user@example.com"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: theme.bg,
                    color: theme.txt,
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                />
              </div>

              <div>
                <label style={{ fontSize: 13, fontWeight: 600, color: theme.sub, marginBottom: 8, display: 'block' }}>
                  Password
                </label>
                <input
                  type="password"
                  value={userCredentials.password}
                  onChange={(e) => setUserCredentials({ ...userCredentials, password: e.target.value })}
                  placeholder="Leave empty to keep current"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: theme.bg,
                    color: theme.txt,
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                />
              </div>
            </div>
            
            <div style={{ marginBottom: 24 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, paddingBottom: 12, borderBottom: `1px solid ${theme.border}` }}>
                <label style={{ fontSize: 15, fontWeight: 700, color: theme.txt, margin: 0 }}>
                  Assign Roles
                </label>
                <div style={{ fontSize: 13, color: theme.sub }}>
                  {selectedUserRoles.length} of {roles.length} selected
                </div>
              </div>
              
              <div style={{
                maxHeight: 300,
                overflow: 'auto',
                border: `1px solid ${theme.border}`,
                borderRadius: 12,
                padding: 20,
                background: theme.bg,
              }}>
                {roles.map((role) => (
                  <label key={role.id} style={{ 
                    display: 'flex', 
                    alignItems: 'flex-start', 
                    gap: 12, 
                    fontSize: 13, 
                    color: theme.txt,
                    padding: '12px 14px',
                    borderRadius: 8,
                    marginBottom: 6,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    background: selectedUserRoles.includes(role.id) ? theme.pri + '15' : theme.card,
                    border: selectedUserRoles.includes(role.id) ? `1px solid ${theme.pri}` : `1px solid ${theme.border}`,
                  }}
                  onMouseEnter={(e) => { e.target.style.borderColor = theme.pri; e.target.style.background = theme.pri + '10'; }}
                  onMouseLeave={(e) => { e.target.style.borderColor = selectedUserRoles.includes(role.id) ? theme.pri : theme.border; e.target.style.background = selectedUserRoles.includes(role.id) ? theme.pri + '15' : theme.card; }}
                  >
                    <input
                      type="checkbox"
                      checked={selectedUserRoles.includes(role.id)}
                      onChange={(e) => {
                        const selectedRoles = e.target.checked
                          ? [...selectedUserRoles, role.id]
                          : selectedUserRoles.filter(id => id !== role.id);
                        setSelectedUserRoles(selectedRoles);
                      }}
                      style={{ marginTop: 2, cursor: 'pointer' }}
                    />
                    <div>
                      <div style={{ fontWeight: 600, marginBottom: 2 }}>{role.name}</div>
                      <div style={{ fontSize: 11, color: theme.sub, lineHeight: 1.4 }}>{role.description}</div>
                    </div>
                  </label>
                ))}
              </div>
            </div>

            <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', paddingTop: 16, borderTop: `1px solid ${theme.border}` }}>
              <button
                onClick={() => {
                  setUserRoleModal({ isOpen: false, userId: null, username: '', clickPosition: { x: 0, y: 0 } });
                  setSelectedUserRoles([]);
                  setUserCredentials({ email: '', password: '' });
                }}
                style={{
                  padding: '12px 24px',
                  background: 'transparent',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.target.style.background = theme.bg; }}
                onMouseLeave={(e) => { e.target.style.background = 'transparent'; }}
              >
                Cancel
              </button>
              <button
                onClick={handleSaveUserRole}
                style={{
                  padding: '12px 24px',
                  background: theme.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: `0 4px 6px -1px ${theme.pri}40`,
                }}
                onMouseEnter={(e) => { e.target.style.transform = 'translateY(-1px)'; e.target.style.boxShadow = `0 6px 8px -1px ${theme.pri}50`; }}
                onMouseLeave={(e) => { e.target.style.transform = 'translateY(0)'; e.target.style.boxShadow = `0 4px 6px -1px ${theme.pri}40`; }}
              >
                Save Changes
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Alert Modal */}
      {alertModal.isOpen && (
        <AlertModal
          isOpen={alertModal.isOpen}
          title={alertModal.title}
          message={alertModal.message}
          type={alertModal.type}
          showCancel={alertModal.showCancel}
          onConfirm={alertModal.onConfirm}
          onClose={() => setAlertModal({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null })}
        />
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
                  <th style={headerStyle}>Email</th>
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
                      <div style={{ fontSize: 12, color: theme.sub }}>
                        {log.actor_email || 'N/A'}
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



