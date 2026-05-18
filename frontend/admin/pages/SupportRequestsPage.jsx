import { useState, useEffect } from 'react';
import { LifeBuoy, RefreshCw, Filter, MessageSquare, User as UserIcon, Clock, CheckCircle2, AlertCircle } from 'lucide-react';
import api from '../../api';

const CATEGORIES = [
  { value: '', label: 'All categories' },
  { value: 'account', label: 'Account' },
  { value: 'payment', label: 'Payment / Wallet' },
  { value: 'technical', label: 'Technical Issue' },
  { value: 'content', label: 'Content / Post' },
  { value: 'abuse', label: 'Abuse / Report' },
  { value: 'suggestion', label: 'Suggestion / Feedback' },
  { value: 'other', label: 'Other' },
];

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'received', label: 'Received' },
  { value: 'pending', label: 'Pending' },
  { value: 'in_progress', label: 'In Progress' },
  { value: 'solved', label: 'Solved' },
  { value: 'closed', label: 'Closed' },
];

const STATUS_COLORS = {
  received: { color: '#3B82F6', bg: '#1E3A8A33' },
  pending: { color: '#8fc441', bg: '#78350F33' },
  in_progress: { color: '#8B5CF6', bg: '#4C1D9533' },
  solved: { color: '#10B981', bg: '#064E3B33' },
  closed: { color: '#9CA3AF', bg: '#37415133' },
};

export function SupportRequestsPage({ theme }) {
  const T = theme || {};
  const [items, setItems] = useState([]);
  const [summary, setSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [selected, setSelected] = useState(null);
  const [saving, setSaving] = useState(false);

  const load = async () => {
    try {
      setLoading(true);
      const params = {};
      if (filterStatus) params.status = filterStatus;
      if (filterCategory) params.category = filterCategory;
      const data = await api.adminListSupportRequests(params);
      setItems(data?.results || []);
      setSummary(data?.summary || {});
    } catch (e) {
      console.error('Failed to load support requests', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => { load(); }, [filterStatus, filterCategory]);

  const handleSave = async () => {
    if (!selected) return;
    try {
      setSaving(true);
      console.log('[Support] Saving request:', selected.id, selected.status, selected.admin_response);
      const updated = await api.adminUpdateSupportRequest(selected.id, {
        status: selected.status,
        admin_response: selected.admin_response || '',
      });
      console.log('[Support] Updated response:', updated);
      setSelected(updated?.request || null);
      await load();
    } catch (e) {
      console.error('[Support] Save error:', e);
      alert(e?.message || 'Failed to update request');
    } finally {
      setSaving(false);
    }
  };

  const BG = '#0F0F0F';
  const CARD = '#1A1A1A';
  const BORDER = '#262626';
  const TXT = '#fff';
  const SUB = '#9CA3AF';
  const PRI = T.pri || '#8fc441';

  return (
    <div style={{ padding: 24, color: TXT, minHeight: '100%', background: BG }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <LifeBuoy size={26} color={PRI} />
          <h1 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Support Requests</h1>
        </div>
        <button
          onClick={load}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '8px 14px', borderRadius: 10,
            background: CARD, color: TXT, border: `1px solid ${BORDER}`,
            cursor: 'pointer', fontSize: 13, fontWeight: 600,
          }}
        >
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))', gap: 12, marginBottom: 20 }}>
        {Object.entries(STATUS_COLORS).map(([key, c]) => (
          <div key={key} style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 14 }}>
            <div style={{ fontSize: 11, color: SUB, textTransform: 'uppercase', letterSpacing: 0.5, fontWeight: 700 }}>{key.replace('_', ' ')}</div>
            <div style={{ fontSize: 24, fontWeight: 900, color: c.color, marginTop: 4 }}>{summary[key] || 0}</div>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 16, flexWrap: 'wrap' }}>
        <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)} style={{
          padding: '8px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
          background: CARD, color: TXT, fontSize: 13,
        }}>
          {STATUS_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
        <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)} style={{
          padding: '8px 12px', borderRadius: 10, border: `1px solid ${BORDER}`,
          background: CARD, color: TXT, fontSize: 13,
        }}>
          {CATEGORIES.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      </div>

      {/* List */}
      <div style={{ display: 'grid', gridTemplateColumns: selected ? '1fr 1fr' : '1fr', gap: 16 }}>
        <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, overflow: 'hidden' }}>
          {loading ? (
            <div style={{ padding: 40, textAlign: 'center', color: SUB }}>Loading...</div>
          ) : items.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: SUB }}>No support requests.</div>
          ) : (
            items.map(req => {
              const s = STATUS_COLORS[req.status] || STATUS_COLORS.received;
              const isSelected = selected?.id === req.id;
              return (
                <div
                  key={req.id}
                  onClick={() => setSelected({ ...req })}
                  style={{
                    padding: 14, borderBottom: `1px solid ${BORDER}`, cursor: 'pointer',
                    background: isSelected ? '#262626' : 'transparent',
                  }}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <div style={{ fontSize: 14, fontWeight: 700, color: TXT, flex: 1 }}>{req.subject}</div>
                    <span style={{
                      fontSize: 10, fontWeight: 700, padding: '3px 8px', borderRadius: 999,
                      background: s.bg, color: s.color, textTransform: 'uppercase', letterSpacing: 0.5,
                    }}>{req.status_display}</span>
                  </div>
                  <div style={{ fontSize: 12, color: SUB, display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                    <span><UserIcon size={11} style={{ verticalAlign: 'middle' }} /> @{req.user?.username}</span>
                    <span>{req.category_display}</span>
                    <span><Clock size={11} style={{ verticalAlign: 'middle' }} /> {new Date(req.created_at).toLocaleString()}</span>
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Detail panel */}
        {selected && (
          <div style={{ background: CARD, border: `1px solid ${BORDER}`, borderRadius: 12, padding: 18 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700 }}>Request #{selected.id}</h3>
              <button onClick={() => setSelected(null)} style={{ background: 'none', border: 'none', color: SUB, cursor: 'pointer', fontSize: 14 }}>Close</button>
            </div>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 4 }}>From</div>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 12 }}>@{selected.user?.username} ({selected.user?.email})</div>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 4 }}>Category</div>
            <div style={{ fontSize: 13, marginBottom: 12 }}>{selected.category_display}</div>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 4 }}>Subject</div>
            <div style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>{selected.subject}</div>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 4 }}>Message</div>
            <div style={{
              fontSize: 13, background: BG, border: `1px solid ${BORDER}`, borderRadius: 8,
              padding: 12, marginBottom: 16, whiteSpace: 'pre-wrap',
            }}>{selected.message}</div>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 6, fontWeight: 700 }}>Update Status</div>
            <select
              value={selected.status}
              onChange={(e) => setSelected(s => ({ ...s, status: e.target.value }))}
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 10,
                border: `1px solid ${BORDER}`, background: BG, color: TXT,
                marginBottom: 14, fontSize: 14,
              }}
            >
              {STATUS_OPTIONS.filter(o => o.value).map(o => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>

            <div style={{ fontSize: 12, color: SUB, marginBottom: 6, fontWeight: 700 }}>Admin Response (visible to user)</div>
            <textarea
              rows={5}
              value={selected.admin_response || ''}
              onChange={(e) => setSelected(s => ({ ...s, admin_response: e.target.value }))}
              placeholder="Write a response to the user..."
              style={{
                width: '100%', padding: '10px 12px', borderRadius: 10,
                border: `1px solid ${BORDER}`, background: BG, color: TXT,
                marginBottom: 14, fontSize: 14, boxSizing: 'border-box', resize: 'vertical',
              }}
            />

            <button
              onClick={handleSave}
              disabled={saving}
              style={{
                width: '100%', padding: 12, borderRadius: 10, border: 'none',
                background: PRI, color: '#000', fontSize: 14, fontWeight: 800,
                cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1,
              }}
            >
              {saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
