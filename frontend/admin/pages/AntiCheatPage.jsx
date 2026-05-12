import { useState, useEffect } from 'react';
import { Shield, AlertTriangle, CheckCircle, XCircle, User, Clock, Eye, Ban } from 'lucide-react';
import api from '../../api';

export function AntiCheatPage({ theme }) {
  const [flags, setFlags] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [selectedFlag, setSelectedFlag] = useState(null);

  useEffect(() => {
    loadFlags();
  }, [filter]);

  const loadFlags = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/admin/contest/anti-cheat/?status=${filter}`);
      setFlags(response.flags || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load flags:', error);
      setLoading(false);
    }
  };

  const reviewFlag = async (status) => {
    if (!selectedFlag) return;

    try {
      await api.request(`/admin/contest/review-flag/${selectedFlag.id}/`, {
        method: 'POST',
        body: JSON.stringify({ status }),
      });

      loadFlags();
      setSelectedFlag(null);
    } catch (error) {
      console.error('Failed to review flag:', error);
    }
  };

  const getFlagIcon = (type) => {
    switch (type) {
      case 'like_spam':
        return <AlertTriangle size={20} color={theme.red} />;
      case 'follow_spam':
        return <User size={20} color={theme.orange} />;
      case 'vote_spam':
        return <AlertTriangle size={20} color={theme.red} />;
      default:
        return <Shield size={20} color={theme.sub} />;
    }
  };

  const getFlagColor = (type) => {
    switch (type) {
      case 'like_spam':
      case 'vote_spam':
        return theme.red;
      case 'follow_spam':
        return theme.orange;
      default:
        return theme.sub;
    }
  };

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700, color: theme.txt, marginBottom: 8 }}>
          <Shield size={32} style={{ verticalAlign: 'middle', marginRight: 12 }} />
          Anti-Cheat System
        </h1>
        <p style={{ margin: 0, fontSize: 16, color: theme.sub }}>
          Review flagged accounts and suspicious activity
        </p>
      </div>

      {/* Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: 16,
        marginBottom: 24,
      }}>
        {[
          { label: 'Pending Review', value: flags.filter(f => f.status === 'pending').length, color: theme.orange },
          { label: 'Cleared', value: flags.filter(f => f.status === 'cleared').length, color: theme.green },
          { label: 'Confirmed', value: flags.filter(f => f.status === 'confirmed').length, color: theme.red },
        ].map((stat) => (
          <div key={stat.label} style={{
            background: theme.card,
            borderRadius: 12,
            padding: 16,
            border: `1px solid ${theme.border}`,
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: stat.color }}>{stat.value}</div>
            <div style={{ fontSize: 12, color: theme.sub }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {['pending', 'cleared', 'confirmed', 'all'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '8px 16px',
              background: filter === f ? theme.pri : theme.card,
              border: `1px solid ${filter === f ? theme.pri : theme.border}`,
              borderRadius: 8,
              color: filter === f ? '#fff' : theme.txt,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Flags List */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
          Loading flags...
        </div>
      ) : flags.length === 0 ? (
        <div style={{
          padding: 60,
          textAlign: 'center',
          background: theme.card,
          borderRadius: 16,
          border: `1px solid ${theme.border}`,
        }}>
          <Shield size={48} color={theme.green} style={{ marginBottom: 16 }} />
          <h3 style={{ margin: 0, fontSize: 18, color: theme.txt, marginBottom: 8 }}>
            No flags found
          </h3>
          <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
            All accounts are behaving normally
          </p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {flags.map((flag) => (
            <div
              key={flag.id}
              onClick={() => setSelectedFlag(flag)}
              style={{
                background: theme.card,
                borderRadius: 12,
                padding: 20,
                border: `2px solid ${selectedFlag?.id === flag.id ? theme.pri : theme.border}`,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 16,
              }}
            >
              {/* Icon */}
              <div style={{
                width: 48,
                height: 48,
                borderRadius: 12,
                background: getFlagColor(flag.flag_type) + '15',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {getFlagIcon(flag.flag_type)}
              </div>

              {/* Content */}
              <div style={{ flex: 1 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: theme.txt }}>
                    @{flag.user?.username}
                  </span>
                  <span style={{
                    padding: '2px 8px',
                    background: getFlagColor(flag.flag_type) + '20',
                    borderRadius: 4,
                    fontSize: 11,
                    fontWeight: 600,
                    color: getFlagColor(flag.flag_type),
                    textTransform: 'uppercase',
                  }}>
                    {flag.flag_type.replace('_', ' ')}
                  </span>
                </div>
                <p style={{ margin: 0, fontSize: 13, color: theme.sub, marginBottom: 8 }}>
                  {flag.description}
                </p>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16, fontSize: 12, color: theme.sub }}>
                  <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Clock size={12} />
                    {new Date(flag.created_at).toLocaleDateString()}
                  </span>
                  <span style={{
                    padding: '2px 8px',
                    borderRadius: 4,
                    background: flag.status === 'pending' ? theme.orange + '20' :
                               flag.status === 'cleared' ? theme.green + '20' : theme.red + '20',
                    color: flag.status === 'pending' ? theme.orange :
                           flag.status === 'cleared' ? theme.green : theme.red,
                    fontWeight: 600,
                    textTransform: 'uppercase',
                  }}>
                    {flag.status}
                  </span>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Review Modal */}
      {selectedFlag && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000,
          padding: 20,
        }}>
          <div style={{
            background: '#fff',
            borderRadius: 16,
            padding: 32,
            width: '100%',
            maxWidth: 500,
          }}>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 24 }}>
              Review Flag
            </h2>

            <div style={{
              padding: 16,
              background: getFlagColor(selectedFlag.flag_type) + '10',
              borderRadius: 12,
              marginBottom: 24,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                {getFlagIcon(selectedFlag.flag_type)}
                <span style={{ fontSize: 18, fontWeight: 700, color: theme.txt }}>
                  {selectedFlag.flag_type.replace('_', ' ').toUpperCase()}
                </span>
              </div>
              <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
                {selectedFlag.description}
              </p>
            </div>

            {/* Evidence */}
            {selectedFlag.evidence && (
              <div style={{ marginBottom: 24 }}>
                <h4 style={{ fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                  Evidence
                </h4>
                <pre style={{
                  padding: 12,
                  background: theme.bg,
                  borderRadius: 8,
                  fontSize: 12,
                  color: theme.sub,
                  overflow: 'auto',
                }}>
                  {JSON.stringify(selectedFlag.evidence, null, 2)}
                </pre>
              </div>
            )}

            {/* Actions */}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => setSelectedFlag(null)}
                style={{
                  flex: 1,
                  padding: 14,
                  background: theme.bg,
                  border: 'none',
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
                onClick={() => reviewFlag('cleared')}
                style={{
                  flex: 1,
                  padding: 14,
                  background: theme.green,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <CheckCircle size={18} />
                Clear User
              </button>
              <button
                onClick={() => reviewFlag('confirmed')}
                style={{
                  flex: 1,
                  padding: 14,
                  background: theme.red,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Ban size={18} />
                Confirm Fraud
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}




