import React, { useState, useEffect } from 'react';
import api from '../../api';
import { ArrowLeft, Plus, Edit2, Trash2, CheckCircle, Calendar, Hash, X, Save } from 'lucide-react';

const PRI = '#DA9B2A';
const BG = '#FAFAF9';
const CARD = '#FFFFFF';
const BORDER = '#E7E5E4';
const TXT = '#1C1917';
const SUB = '#78716C';
const RED = '#EF4444';
const GREEN = '#10B981';

const inp = {
  width: '100%', padding: '10px 12px', border: `1.5px solid ${BORDER}`,
  borderRadius: 8, fontSize: 14, color: TXT, background: CARD,
  outline: 'none', boxSizing: 'border-box',
};

const CampaignThemeManagement = ({ campaignId, onBack }) => {
  const [loading, setLoading] = useState(true);
  const [campaign, setCampaign] = useState(null);
  const [themes, setThemes] = useState([]);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingTheme, setEditingTheme] = useState(null);
  const [toast, setToast] = useState(null);
  const [deletingId, setDeletingId] = useState(null);

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => { loadData(); }, [campaignId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [campaignRes, themesRes] = await Promise.all([
        api.request(`/campaigns/${campaignId}/`),
        api.request(`/admin/campaigns/${campaignId}/themes/`)
      ]);
      setCampaign(campaignRes);
      setThemes(themesRes.themes || []);
    } catch (err) {
      console.error('Error loading data:', err);
      showToast('Failed to load themes', 'error');
    } finally {
      setLoading(false);
    }
  };

  const handleDeleteTheme = async (themeId) => {
    setDeletingId(themeId);
  };

  const confirmDelete = async () => {
    try {
      await api.request(`/admin/campaigns/themes/${deletingId}/`, { method: 'DELETE' });
      showToast('Theme deleted successfully');
      loadData();
    } catch (err) {
      showToast('Failed to delete theme', 'error');
    } finally {
      setDeletingId(null);
    }
  };

  const handleActivateTheme = async (themeId) => {
    try {
      await api.request(`/admin/campaigns/themes/${themeId}/activate/`, { method: 'POST' });
      showToast('Theme activated');
      loadData();
    } catch (err) {
      showToast('Failed to activate theme', 'error');
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
      <div style={{ width: 36, height: 36, border: `3px solid ${PRI}30`, borderTopColor: PRI, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 24, right: 24, zIndex: 9999,
          padding: '12px 20px', borderRadius: 10,
          background: toast.type === 'error' ? '#FEF2F2' : '#F0FDF4',
          border: `1.5px solid ${toast.type === 'error' ? '#FECACA' : '#BBF7D0'}`,
          color: toast.type === 'error' ? RED : GREEN,
          fontSize: 14, fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.12)',
        }}>{toast.msg}</div>
      )}

      {/* Delete Confirm */}
      {deletingId && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1001 }}>
          <div style={{ background: CARD, borderRadius: 14, padding: 28, maxWidth: 400, width: '90%', textAlign: 'center' }}>
            <Trash2 size={36} color={RED} style={{ marginBottom: 12 }} />
            <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: TXT }}>Delete Theme?</h3>
            <p style={{ margin: '0 0 24px', color: SUB, fontSize: 14 }}>This action cannot be undone.</p>
            <div style={{ display: 'flex', gap: 12 }}>
              <button onClick={() => setDeletingId(null)} style={{ flex: 1, padding: '10px', background: BG, border: `1.5px solid ${BORDER}`, borderRadius: 8, fontWeight: 600, cursor: 'pointer', color: TXT }}>Cancel</button>
              <button onClick={confirmDelete} style={{ flex: 1, padding: '10px', background: RED, border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer', color: '#fff' }}>Delete</button>
            </div>
          </div>
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={() => onBack?.()} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: CARD, border: `1.5px solid ${BORDER}`, borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: SUB }}>
            <ArrowLeft size={15} /> Back
          </button>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: TXT }}>Weekly Themes</h1>
            {campaign && <p style={{ margin: 0, fontSize: 13, color: SUB, marginTop: 2 }}>{campaign.title}</p>}
          </div>
        </div>
        <button
          onClick={() => setShowCreateModal(true)}
          style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '10px 20px', background: PRI, color: '#fff', border: 'none', borderRadius: 8, fontSize: 14, fontWeight: 700, cursor: 'pointer' }}
        >
          <Plus size={16} /> Create Theme
        </button>
      </div>

      {/* Empty */}
      {themes.length === 0 ? (
        <div style={{ background: CARD, borderRadius: 14, padding: 60, textAlign: 'center', border: `1.5px solid ${BORDER}` }}>
          <Calendar size={44} color={`${PRI}60`} style={{ marginBottom: 14 }} />
          <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: TXT }}>No Themes Yet</h3>
          <p style={{ margin: '0 0 20px', color: SUB, fontSize: 14 }}>Create weekly themes to guide participants</p>
          <button onClick={() => setShowCreateModal(true)} style={{ padding: '10px 24px', background: PRI, color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: 'pointer', fontSize: 14 }}>
            Create First Theme
          </button>
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 14 }}>
          {themes.map((theme) => (
            <div key={theme.id} style={{ background: CARD, borderRadius: 12, padding: '18px 20px', border: theme.is_active ? `2px solid ${PRI}` : `1.5px solid ${BORDER}` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 12 }}>
                <div style={{ flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 11, fontWeight: 700, color: PRI, background: `${PRI}15`, padding: '3px 10px', borderRadius: 20, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      Week {theme.week_number}
                    </span>
                    <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: TXT }}>{theme.title}</h3>
                    {theme.is_active && (
                      <span style={{ display: 'flex', alignItems: 'center', gap: 4, background: `${GREEN}15`, color: GREEN, padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 700 }}>
                        <CheckCircle size={13} /> Active
                      </span>
                    )}
                  </div>
                  <p style={{ margin: '0 0 10px', color: SUB, fontSize: 13, lineHeight: 1.5 }}>{theme.description}</p>
                  <div style={{ display: 'flex', gap: 16, fontSize: 12, color: SUB }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}><Calendar size={12} /> {new Date(theme.start_date).toLocaleDateString()}</span>
                    <span>→</span>
                    <span>{new Date(theme.end_date).toLocaleDateString()}</span>
                  </div>
                  {theme.hashtags?.length > 0 && (
                    <div style={{ marginTop: 10, display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                      {theme.hashtags.map((tag, i) => (
                        <span key={i} style={{ background: `${PRI}12`, color: PRI, padding: '3px 10px', borderRadius: 20, fontSize: 12, fontWeight: 600 }}>#{tag}</span>
                      ))}
                    </div>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 8, flexShrink: 0, alignItems: 'flex-start' }}>
                  {!theme.is_active && (
                    <button onClick={() => handleActivateTheme(theme.id)} style={{ padding: '7px 14px', background: `${GREEN}15`, color: GREEN, border: `1.5px solid ${GREEN}30`, borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 700 }}>
                      Activate
                    </button>
                  )}
                  <button onClick={() => setEditingTheme(theme)} style={{ padding: 8, background: `${PRI}12`, border: 'none', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                    <Edit2 size={15} color={PRI} />
                  </button>
                  <button onClick={() => handleDeleteTheme(theme.id)} style={{ padding: 8, background: '#FEF2F2', border: 'none', borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center' }}>
                    <Trash2 size={15} color={RED} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {(showCreateModal || editingTheme) && (
        <ThemeModal
          campaignId={campaignId}
          theme={editingTheme}
          onClose={() => { setShowCreateModal(false); setEditingTheme(null); }}
          onSuccess={(msg) => { setShowCreateModal(false); setEditingTheme(null); showToast(msg); loadData(); }}
        />
      )}
    </div>
  );
};

const ThemeModal = ({ campaignId, theme, onClose, onSuccess }) => {
  const [formData, setFormData] = useState({
    title: theme?.title || '',
    description: theme?.description || '',
    week_number: theme?.week_number || 1,
    start_date: theme?.start_date?.split('T')[0] || '',
    end_date: theme?.end_date?.split('T')[0] || '',
    hashtags: theme?.hashtags?.join(', ') || '',
  });
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');
  const set = (k, v) => setFormData(p => ({ ...p, [k]: v }));

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    try {
      setSaving(true);
      const payload = { ...formData, hashtags: formData.hashtags.split(',').map(t => t.trim()).filter(Boolean) };
      if (theme) {
        await api.request(`/admin/campaigns/themes/${theme.id}/`, { method: 'PUT', body: JSON.stringify(payload) });
      } else {
        await api.request(`/admin/campaigns/${campaignId}/themes/`, { method: 'POST', body: JSON.stringify(payload) });
      }
      onSuccess(`Theme ${theme ? 'updated' : 'created'} successfully!`);
    } catch (err) {
      setError('Failed to save theme. Please try again.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}
      onClick={onClose}>
      <div style={{ background: CARD, borderRadius: 16, width: '100%', maxWidth: 560, maxHeight: '92vh', overflowY: 'auto', boxShadow: '0 24px 60px rgba(0,0,0,0.2)' }}
        onClick={e => e.stopPropagation()}>
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 22px', borderBottom: `1.5px solid ${BORDER}`, position: 'sticky', top: 0, background: CARD, borderRadius: '16px 16px 0 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{ width: 36, height: 36, borderRadius: 9, background: `linear-gradient(135deg, ${PRI}, #F59E0B)`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Calendar size={18} color="#fff" />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: TXT }}>{theme ? 'Edit Theme' : 'Create Theme'}</h2>
              <p style={{ margin: 0, fontSize: 12, color: SUB }}>Weekly campaign theme</p>
            </div>
          </div>
          <button onClick={onClose} style={{ width: 32, height: 32, borderRadius: '50%', background: BG, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <X size={16} color={SUB} />
          </button>
        </div>
        <form onSubmit={handleSubmit} style={{ padding: '18px 22px 0' }}>
          {error && <div style={{ padding: '10px 14px', background: '#FEF2F2', border: `1.5px solid #FECACA`, borderRadius: 8, color: RED, fontSize: 13, marginBottom: 16 }}>{error}</div>}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Week #</label>
              <input type="number" required min="1" value={formData.week_number} onChange={e => set('week_number', e.target.value)} style={inp} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Theme Title *</label>
              <input type="text" required placeholder="e.g., Nature & Wildlife" value={formData.title} onChange={e => set('title', e.target.value)} style={inp} />
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Description *</label>
            <textarea required rows={3} placeholder="Describe the theme and what participants should create..." value={formData.description} onChange={e => set('description', e.target.value)} style={{ ...inp, resize: 'vertical' }} />
          </div>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 14 }}>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Start Date *</label>
              <input type="date" required value={formData.start_date} onChange={e => set('start_date', e.target.value)} style={inp} />
            </div>
            <div>
              <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>End Date *</label>
              <input type="date" required value={formData.end_date} onChange={e => set('end_date', e.target.value)} style={inp} />
            </div>
          </div>
          <div style={{ marginBottom: 14 }}>
            <label style={{ display: 'block', fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 6 }}>Hashtags (comma-separated)</label>
            <input type="text" placeholder="nature, wildlife, outdoors" value={formData.hashtags} onChange={e => set('hashtags', e.target.value)} style={inp} />
          </div>
          <div style={{ display: 'flex', gap: 10, padding: '14px 0 20px', position: 'sticky', bottom: 0, background: CARD }}>
            <button type="button" onClick={onClose} style={{ flex: 1, padding: '11px', background: BG, border: `1.5px solid ${BORDER}`, borderRadius: 8, fontWeight: 600, cursor: 'pointer', color: TXT, fontSize: 13 }}>Cancel</button>
            <button type="submit" disabled={saving} style={{ flex: 2, padding: '11px', background: saving ? `${PRI}aa` : PRI, border: 'none', borderRadius: 8, fontWeight: 700, cursor: saving ? 'not-allowed' : 'pointer', color: '#fff', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7 }}>
              <Save size={15} />{saving ? 'Saving...' : theme ? 'Update Theme' : 'Create Theme'}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};

export default CampaignThemeManagement;




