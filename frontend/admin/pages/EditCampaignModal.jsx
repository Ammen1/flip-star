import { useState, useEffect } from 'react';
import { X, Save, Image, Trophy, Calendar, Users, Hash, CheckCircle, Type, AlertCircle } from 'lucide-react';
import api from '../../api';

const toLocalInput = (iso) => {
  if (!iso) return '';
  try { return new Date(iso).toISOString().slice(0, 16); } catch { return ''; }
};

const STATUS_OPTIONS = [
  { value: 'draft',     label: 'Draft',     color: '#F59E0B' },
  { value: 'active',    label: 'Active',    color: '#10B981' },
  { value: 'voting',    label: 'Voting',    color: '#3B82F6' },
  { value: 'completed', label: 'Completed', color: '#6B7280' },
  { value: 'cancelled', label: 'Cancelled', color: '#EF4444' },
];

const inputStyle = (theme) => ({
  width: '100%',
  padding: '10px 14px',
  border: `1.5px solid ${theme.border}`,
  borderRadius: 8,
  fontSize: 14,
  color: theme.txt,
  background: theme.bg,
  outline: 'none',
  boxSizing: 'border-box',
  transition: 'border-color 0.2s',
});

const Section = ({ icon: Icon, title, color, children }) => (
  <div style={{
    marginBottom: 24,
    borderRadius: 10,
    border: `1.5px solid ${color}30`,
    overflow: 'hidden',
  }}>
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      padding: '12px 16px',
      background: `${color}12`,
      borderBottom: `1.5px solid ${color}30`,
    }}>
      <Icon size={16} color={color} />
      <span style={{ fontSize: 13, fontWeight: 700, color, textTransform: 'uppercase', letterSpacing: '0.04em' }}>
        {title}
      </span>
    </div>
    <div style={{ padding: '16px 16px 4px' }}>{children}</div>
  </div>
);

const Field = ({ label, required, children }) => (
  <div style={{ marginBottom: 16 }}>
    <label style={{ display: 'block', fontSize: 13, fontWeight: 600, marginBottom: 6, color: '#374151' }}>
      {label}{required && <span style={{ color: '#EF4444', marginLeft: 3 }}>*</span>}
    </label>
    {children}
  </div>
);

export function EditCampaignModal({ theme, campaign, onClose, onSuccess, selectedMasterCampaign }) {
  const [masterCampaigns, setMasterCampaigns] = useState([]);
  const [formData, setFormData] = useState({
    title:              campaign.title || '',
    description:        campaign.description || '',
    status:             campaign.status || 'draft',
    campaign_type:      campaign.campaign_type || 'grand',
    master_campaign:    campaign.master_campaign?.id || selectedMasterCampaign || '',
    prize_title:        campaign.prize_title || '',
    prize_description:  campaign.prize_description || '',
    prize_value:        campaign.prize_value || '',
    start_date:         toLocalInput(campaign.start_date),
    entry_deadline:     toLocalInput(campaign.entry_deadline),
    voting_start:       toLocalInput(campaign.voting_start),
    voting_end:         toLocalInput(campaign.voting_end),
    winner_count:       campaign.winner_count || 1,
    min_followers:      campaign.min_followers || 0,
    min_level:          campaign.min_level || 1,
    min_votes_per_reel: campaign.min_votes_per_reel || 0,
    required_hashtags:  campaign.required_hashtags || '',
  });
  const [imageFile, setImageFile]     = useState(null);
  const [imagePreview, setImagePreview] = useState(campaign.image || null);
  const [saving, setSaving]           = useState(false);
  const [saved, setSaved]             = useState(false);
  const [error, setError]             = useState('');

  const set = (field, value) => setFormData(p => ({ ...p, [field]: value }));

  useEffect(() => {
    loadMasterCampaigns();
  }, []);

  const loadMasterCampaigns = async () => {
    try {
      const response = await api.request('/admin/master-campaigns/');
      setMasterCampaigns(response.master_campaigns || []);
    } catch (error) {
      console.error('Failed to load master campaigns:', error);
      setMasterCampaigns([]);
    }
  };

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (!file) return;
    setImageFile(file);
    const reader = new FileReader();
    reader.onloadend = () => setImagePreview(reader.result);
    reader.readAsDataURL(file);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError('');
    setSaving(true);

    try {
      const fd = new FormData();

      fd.append('title',              formData.title);
      fd.append('description',        formData.description);
      fd.append('status',             formData.status);
      fd.append('campaign_type',      formData.campaign_type);
      fd.append('master_campaign',    formData.master_campaign);
      fd.append('prize_title',        formData.prize_title);
      fd.append('prize_description',  formData.prize_description || formData.prize_title);
      fd.append('prize_value',        formData.prize_value);
      fd.append('winner_count',       formData.winner_count);

      // Append image if a new one was selected
      if (imageFile) {
        fd.append('image', imageFile);
      }

      await api.request(`/admin/campaigns/${campaign.id}/update/`, {
        method: 'PATCH',
        body: fd,
        isFormData: true,
      });

      setSaved(true);
      setTimeout(() => onSuccess(), 1200);
    } catch (err) {
      console.error('Failed to update campaign:', err);
      if (err.status === 404) {
        setError('Campaign no longer exists. It will be removed from the list.');
        setTimeout(() => onSuccess('CAMPAIGN_NOT_FOUND'), 2000);
      } else {
        setError(err.message || 'Failed to save changes. Please try again.');
      }
    } finally {
      setSaving(false);
    }
  };

  const inp = inputStyle(theme);

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.55)',
        backdropFilter: 'blur(4px)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 1000, padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff',
          borderRadius: 16,
          width: '100%',
          maxWidth: 680,
          maxHeight: '92vh',
          overflowY: 'auto',
          boxShadow: '0 24px 60px rgba(0,0,0,0.25)',
          display: 'flex',
          flexDirection: 'column',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '20px 24px',
          borderBottom: '1.5px solid #F3F4F6',
          position: 'sticky', top: 0, background: '#fff', zIndex: 10,
          borderRadius: '16px 16px 0 0',
        }}>
          <div>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt, letterSpacing: '-0.02em' }}>
              Edit Campaign
            </h2>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: theme.sub }}>
              Update settings for {campaign.title}
            </p>
          </div>
          <button
            onClick={onClose}
            style={{
              width: 36, height: 36, borderRadius: '50%',
              background: '#F3F4F6', border: 'none', cursor: 'pointer',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <X size={18} color={theme.sub} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: '24px 32px' }}>
          {error && (
            <div style={{
              padding: '12px 16px', background: theme.red + '15',
              border: `1px solid ${theme.red}40`, borderRadius: 8,
              color: theme.red, fontSize: 14, marginBottom: 24,
              display: 'flex', alignItems: 'center', gap: 8,
            }}>
              <AlertCircle size={18} />
              {error}
            </div>
          )}

          <form onSubmit={handleSubmit} id="edit-campaign-form">
            {/* ── BASIC INFO ── */}
            <Section icon={Type} title="Basic Information" color="#3B82F6">
              <Field label="Campaign Title" required>
                <input type="text" value={formData.title}
                  onChange={e => set('title', e.target.value)} required style={inp} />
              </Field>

              <Field label="Campaign Type" required>
                <select
                  value={formData.campaign_type}
                  onChange={e => set('campaign_type', e.target.value)}
                  required
                  style={{...inp, cursor: 'pointer'}}
                >
                  <option value="daily">Daily Campaign (Scoring Only)</option>
                  <option value="weekly">Weekly Campaign (Scoring Only)</option>
                  <option value="monthly">Monthly Campaign (Scoring Only)</option>
                  <option value="grand">Grand Campaign (Voting + Scoring)</option>
                </select>
              </Field>

              <Field label="Master Campaign" required>
                <select
                  value={formData.master_campaign}
                  onChange={e => set('master_campaign', e.target.value)}
                  required
                  style={{...inp, cursor: 'pointer'}}
                >
                  <option value="">Select Master Campaign</option>
                  {masterCampaigns.map((mc) => (
                    <option key={mc.id} value={mc.id}>
                      {mc.title} ({mc.status})
                    </option>
                  ))}
                </select>
                {masterCampaigns.length === 0 && (
                  <div style={{
                    marginTop: 4,
                    fontSize: 12,
                    color: theme.red,
                  }}>
                    No master campaigns available. Please create one first.
                  </div>
                )}
              </Field>

              <Field label="Description" required>
                <textarea value={formData.description}
                  onChange={e => set('description', e.target.value)} required rows={3}
                  style={{ ...inp, resize: 'vertical' }} />
              </Field>

              <Field label="Campaign Status" required>
                <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                  {STATUS_OPTIONS.map(opt => (
                    <button key={opt.value} type="button"
                      onClick={() => set('status', opt.value)}
                      style={{
                        padding: '7px 16px', borderRadius: 20, cursor: 'pointer',
                        fontSize: 13, fontWeight: 600,
                        background: formData.status === opt.value ? opt.color : '#F9FAFB',
                        color: formData.status === opt.value ? '#fff' : '#6B7280',
                        border: `1.5px solid ${formData.status === opt.value ? opt.color : '#E5E7EB'}`,
                      }}
                    >{opt.label}</button>
                  ))}
                </div>
              </Field>
            </Section>

          {/* ── BANNER IMAGE ── */}
          <Section icon={Image} title="Banner Image" color="#8B5CF6">
            <div style={{ marginBottom: 16 }}>
              <div
                style={{
                  border: `2px dashed ${imagePreview ? '#8B5CF6' : '#E5E7EB'}`,
                  borderRadius: 10, padding: 16, textAlign: 'center',
                  cursor: 'pointer', background: imagePreview ? '#F5F3FF' : '#FAFAFA',
                  position: 'relative', transition: 'all 0.2s',
                }}
                onClick={() => document.getElementById('edit-img-upload').click()}
              >
                {imagePreview ? (
                  <div style={{ position: 'relative', display: 'inline-block' }}>
                    <img src={imagePreview} alt="Banner"
                      style={{ maxWidth: '100%', maxHeight: 180, borderRadius: 8, display: 'block' }} />
                    <button type="button"
                      onClick={e => { e.stopPropagation(); setImageFile(null); setImagePreview(campaign.image || null); }}
                      style={{
                        position: 'absolute', top: 6, right: 6,
                        background: '#EF4444', color: '#fff', border: 'none',
                        borderRadius: 6, padding: '3px 8px', cursor: 'pointer', fontSize: 11, fontWeight: 700,
                      }}
                    >Remove</button>
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 32, marginBottom: 6 }}>🖼️</div>
                    <div style={{ fontSize: 13, color: '#374151', fontWeight: 600 }}>Click to upload banner</div>
                    <div style={{ fontSize: 11, color: '#9CA3AF', marginTop: 2 }}>PNG, JPG up to 10 MB</div>
                  </>
                )}
                <input id="edit-img-upload" type="file" accept="image/*"
                  onChange={handleImageChange} style={{ display: 'none' }} />
              </div>
            </div>
          </Section>

          {/* ── PRIZE ── */}
          <Section icon={Trophy} title="Prize Details" color="#F59E0B">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Prize Title" required>
                <input type="text" value={formData.prize_title}
                  onChange={e => set('prize_title', e.target.value)} required style={inp} />
              </Field>
              <Field label="Prize Value (ETB)" required>
                <input type="number" value={formData.prize_value} min="0" step="0.01"
                  onChange={e => set('prize_value', e.target.value)} required style={inp} />
              </Field>
            </div>
            <Field label="Prize Description">
              <textarea value={formData.prize_description}
                onChange={e => set('prize_description', e.target.value)} rows={2}
                placeholder="Describe the prize in detail..."
                style={{ ...inp, resize: 'vertical' }} />
            </Field>
          </Section>

          {/* ── DATES ── */}
          <Section icon={Calendar} title="Campaign Timeline" color="#3B82F6">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
              <Field label="Start Date">
                <input type="datetime-local" value={formData.start_date}
                  onChange={e => set('start_date', e.target.value)} style={inp} />
              </Field>
              <Field label="Entry Deadline">
                <input type="datetime-local" value={formData.entry_deadline}
                  onChange={e => set('entry_deadline', e.target.value)} style={inp} />
              </Field>
              <Field label="Voting Opens">
                <input type="datetime-local" value={formData.voting_start}
                  onChange={e => set('voting_start', e.target.value)} style={inp} />
              </Field>
              <Field label="Voting Closes">
                <input type="datetime-local" value={formData.voting_end}
                  onChange={e => set('voting_end', e.target.value)} style={inp} />
              </Field>
            </div>
          </Section>

          {/* ── REQUIREMENTS ── */}
          <Section icon={Users} title="Entry Requirements" color="#10B981">
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 12 }}>
              <Field label="Min Followers">
                <input type="number" value={formData.min_followers} min="0"
                  onChange={e => set('min_followers', parseInt(e.target.value) || 0)} style={inp} />
              </Field>
              <Field label="Min Level">
                <input type="number" value={formData.min_level} min="1"
                  onChange={e => set('min_level', parseInt(e.target.value) || 1)} style={inp} />
              </Field>
              <Field label="Min Votes / Reel">
                <input type="number" value={formData.min_votes_per_reel} min="0"
                  onChange={e => set('min_votes_per_reel', parseInt(e.target.value) || 0)} style={inp} />
              </Field>
            </div>
            <Field label="Number of Winners" required>
              <input type="number" value={formData.winner_count} min="1"
                onChange={e => set('winner_count', parseInt(e.target.value) || 1)} required style={{ ...inp, maxWidth: 160 }} />
            </Field>
          </Section>

          {/* ── HASHTAGS ── */}
          <Section icon={Hash} title="Required Hashtags" color="#6B7280">
            <Field label="Hashtags (comma-separated)">
              <input type="text" value={formData.required_hashtags}
                placeholder="#contest, #giveaway, #challenge"
                onChange={e => set('required_hashtags', e.target.value)} style={inp} />
            </Field>
          </Section>

          {/* Footer */}
          <div style={{
            display: 'flex', gap: 12, padding: '16px 0 24px',
            position: 'sticky', bottom: 0, background: '#fff',
          }}>
            <button type="button" onClick={onClose}
              style={{
                flex: 1, padding: '12px 20px',
                background: '#F9FAFB', border: '1.5px solid #E5E7EB',
                borderRadius: 10, fontSize: 14, fontWeight: 600,
                color: '#374151', cursor: 'pointer',
              }}
            >Cancel</button>
            <button type="submit" disabled={saving || saved}
              style={{
                flex: 2, padding: '12px 20px',
                background: saved ? '#10B981' : saving ? `${theme.pri}aa` : theme.pri,
                border: 'none', borderRadius: 10,
                fontSize: 14, fontWeight: 700,
                color: '#fff', cursor: saving || saved ? 'not-allowed' : 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                transition: 'background 0.2s',
              }}
            >
              {saved ? 'Saved!' : saving ? 'Saving...' : 'Save Changes'}
            </button>
          </div>
          </form>
        </div>
      </div>
    </div>
  );
}




