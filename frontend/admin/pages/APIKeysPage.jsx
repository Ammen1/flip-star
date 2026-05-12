import { useState, useEffect } from 'react';
import { Key, Plus, Trash2, Copy, Check, Eye, EyeOff } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';

export function APIKeysPage({ theme }) {
  const [apiKeys, setApiKeys] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });
  const [copiedKey, setCopiedKey] = useState(null);
  const [visibleKeys, setVisibleKeys] = useState({});

  useEffect(() => {
    loadApiKeys();
  }, []);

  const loadApiKeys = async () => {
    try {
      const data = await api.request('/admin/api-keys/');
      setApiKeys(data);
    } catch (error) {
      console.error('Failed to load API keys:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCreateKey = async (name, expiryDays) => {
    try {
      const data = await api.request('/admin/api-keys/create/', {
        method: 'POST',
        body: JSON.stringify({ name, expires_days: expiryDays })
      });
      setApiKeys([data, ...apiKeys]);
      setShowCreateModal(false);
      setAlertModal({ isOpen: true, title: 'Success', message: 'API key created successfully! Make sure to copy it now.', type: 'success' });
    } catch (error) {
      console.error('Failed to create API key:', error);
      setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to create API key', type: 'error' });
    }
  };

  const handleDeleteKey = async (keyId) => {
    setAlertModal({
      isOpen: true,
      title: 'Delete API Key',
      message: 'Are you sure you want to delete this API key? This action cannot be undone.',
      type: 'warning',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(`/admin/api-keys/${keyId}/delete/`, { method: 'DELETE' });
          setApiKeys(apiKeys.filter(k => k.id !== keyId));
          setAlertModal({ ...alertModal, isOpen: false });
        } catch (error) {
          console.error('Failed to delete API key:', error);
          setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to delete API key', type: 'error' });
        }
      }
    });
  };

  const handleToggleKey = async (keyId) => {
    try {
      const response = await api.request(`/admin/api-keys/${keyId}/toggle/`, { method: 'POST' });
      setApiKeys(apiKeys.map(k => k.id === keyId ? { ...k, is_active: response.is_active } : k));
    } catch (error) {
      console.error('Failed to toggle API key:', error);
    }
  };

  const copyToClipboard = (key, keyId) => {
    navigator.clipboard.writeText(key);
    setCopiedKey(keyId);
    setTimeout(() => setCopiedKey(null), 2000);
  };

  const toggleKeyVisibility = (keyId) => {
    setVisibleKeys({ ...visibleKeys, [keyId]: !visibleKeys[keyId] });
  };

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 32,
      }}>
        <div>
          <h1 style={{
            margin: 0,
            fontSize: 32,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 8,
          }}>
            API Keys
          </h1>
          <p style={{
            margin: 0,
            fontSize: 16,
            color: theme.sub,
          }}>
            Manage API keys for third-party integrations
          </p>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{
            padding: '12px 24px',
            background: theme.pri,
            border: 'none',
            borderRadius: 8,
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Plus size={16} />
          Create API Key
        </button>
      </div>

      {/* API Keys List */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
          Loading API keys...
        </div>
      ) : apiKeys.length === 0 ? (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 60,
          textAlign: 'center',
          border: `1px solid ${theme.border}`,
        }}>
          <Key size={48} color={theme.sub} style={{ marginBottom: 16 }} />
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
            No API keys yet
          </h3>
          <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
            Create your first API key to start integrating with external services
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {apiKeys.map(key => {
            const isVisible = visibleKeys[key.id];
            const maskedKey = key.key.substring(0, 8) + '•'.repeat(40);
            
            return (
              <div
                key={key.id}
                style={{
                  background: theme.card,
                  borderRadius: 12,
                  padding: 24,
                  border: `1px solid ${theme.border}`,
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontSize: 16,
                      fontWeight: 600,
                      color: theme.txt,
                      marginBottom: 8,
                      display: 'flex',
                      alignItems: 'center',
                      gap: 8,
                    }}>
                      {key.name}
                      <span style={{
                        padding: '2px 8px',
                        borderRadius: 4,
                        fontSize: 11,
                        fontWeight: 600,
                        background: key.is_active ? theme.green + '20' : theme.red + '20',
                        color: key.is_active ? theme.green : theme.red,
                      }}>
                        {key.is_active ? 'Active' : 'Inactive'}
                      </span>
                    </div>
                    
                    <div style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 12,
                      marginBottom: 12,
                    }}>
                      <code style={{
                        padding: '8px 12px',
                        background: theme.bg,
                        borderRadius: 6,
                        fontSize: 13,
                        fontFamily: 'monospace',
                        color: theme.txt,
                        flex: 1,
                      }}>
                        {isVisible ? key.key : maskedKey}
                      </code>
                      <button
                        onClick={() => toggleKeyVisibility(key.id)}
                        style={{
                          padding: '8px',
                          background: theme.bg,
                          border: 'none',
                          borderRadius: 6,
                          cursor: 'pointer',
                          color: theme.sub,
                        }}
                      >
                        {isVisible ? <EyeOff size={16} /> : <Eye size={16} />}
                      </button>
                      <button
                        onClick={() => copyToClipboard(key.key, key.id)}
                        style={{
                          padding: '8px',
                          background: copiedKey === key.id ? theme.green + '20' : theme.bg,
                          border: 'none',
                          borderRadius: 6,
                          cursor: 'pointer',
                          color: copiedKey === key.id ? theme.green : theme.sub,
                        }}
                      >
                        {copiedKey === key.id ? <Check size={16} /> : <Copy size={16} />}
                      </button>
                    </div>
                    
                    <div style={{ fontSize: 13, color: theme.sub }}>
                      Created: {new Date(key.created_at).toLocaleDateString()}
                      {key.expires_at && ` • Expires: ${new Date(key.expires_at).toLocaleDateString()}`}
                      {key.last_used && ` • Last used: ${new Date(key.last_used).toLocaleDateString()}`}
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => handleToggleKey(key.id)}
                      style={{
                        padding: '8px 16px',
                        background: key.is_active ? theme.orange + '15' : theme.green + '15',
                        border: 'none',
                        borderRadius: 6,
                        color: key.is_active ? theme.orange : theme.green,
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      {key.is_active ? 'Disable' : 'Enable'}
                    </button>
                    <button
                      onClick={() => handleDeleteKey(key.id)}
                      style={{
                        padding: '8px',
                        background: theme.red + '15',
                        border: 'none',
                        borderRadius: 6,
                        color: theme.red,
                        cursor: 'pointer',
                      }}
                    >
                      <Trash2 size={16} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Modal */}
      {showCreateModal && (
        <CreateAPIKeyModal
          theme={theme}
          onClose={() => setShowCreateModal(false)}
          onCreate={handleCreateKey}
        />
      )}
    </div>
  );
}

function CreateAPIKeyModal({ theme, onClose, onCreate }) {
  const [name, setName] = useState('');
  const [expiryDays, setExpiryDays] = useState(365);

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) {
      alert('Please enter a name for the API key');
      return;
    }
    onCreate(name, expiryDays);
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: theme.card,
          borderRadius: 12,
          padding: 32,
          width: '100%',
          maxWidth: 500,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 24 }}>
          Create API Key
        </h2>
        
        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 20 }}>
            <label style={{
              display: 'block',
              fontSize: 14,
              fontWeight: 600,
              color: theme.txt,
              marginBottom: 8,
            }}>
              Key Name
            </label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Production API Key"
              required
              style={{
                width: '100%',
                padding: '12px',
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>
          
          <div style={{ marginBottom: 24 }}>
            <label style={{
              display: 'block',
              fontSize: 14,
              fontWeight: 600,
              color: theme.txt,
              marginBottom: 8,
            }}>
              Expiry (days)
            </label>
            <input
              type="number"
              value={expiryDays}
              onChange={(e) => setExpiryDays(parseInt(e.target.value))}
              min="1"
              max="3650"
              style={{
                width: '100%',
                padding: '12px',
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                outline: 'none',
              }}
            />
          </div>
          
          <div style={{ display: 'flex', gap: 12 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                flex: 1,
                padding: '12px',
                background: theme.bg,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                color: theme.txt,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              style={{
                flex: 1,
                padding: '12px',
                background: theme.pri,
                border: 'none',
                borderRadius: 8,
                color: '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Create Key
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}




