import { useState, useEffect } from 'react';
import { Smartphone, Bell, RefreshCw, ToggleLeft, ToggleRight, Users, Activity, Send, CheckCircle, XCircle, Zap, Download, Globe } from 'lucide-react';
import api from '../../api';

// ── Brand gold to match mobile app theme ──────────────────────────────────────
const GOLD = '#DA9B2A';

export function MobileAppPage({ theme: T }) {
  const [stats,    setStats]    = useState(null);
  const [notif,    setNotif]    = useState({ title: '', body: '', target: 'all' });
  const [sending,  setSending]  = useState(false);
  const [sent,     setSent]     = useState(false);
  const [features, setFeatures] = useState({
    for_you_tab:   true,
    explore_tab:   true,
    campaigns_tab: true,
    categories_tab:true,
    create_post:   true,
    gift_feature:  true,
    reel_comments: true,
  });
  const [forceUpdate, setForceUpdate] = useState({ enabled: false, min_version: '1.0.0', message: '' });
  const [loadingStats, setLoadingStats] = useState(true);
  const [saveMsg, setSaveMsg] = useState('');

  useEffect(() => {
    loadMobileStats();
    loadMobileConfig();
  }, []);

  const loadMobileStats = async () => {
    setLoadingStats(true);
    try {
      const data = await api.request('/admin/dashboard/');
      setStats(data);
    } catch (e) {
      console.warn('Mobile stats load failed', e);
    } finally {
      setLoadingStats(false);
    }
  };

  const loadMobileConfig = async () => {
    try {
      const cfg = await api.request('/settings/public/');
      if (cfg?.mobile_features) setFeatures(f => ({ ...f, ...cfg.mobile_features }));
      if (cfg?.force_update)    setForceUpdate(fu => ({ ...fu, ...cfg.force_update }));
    } catch {}
  };

  const handleSendPush = async () => {
    if (!notif.title.trim() || !notif.body.trim()) return;
    setSending(true);
    try {
      await api.request('/admin/push-notifications/send/', {
        method: 'POST',
        body: JSON.stringify(notif),
        headers: { 'Content-Type': 'application/json' },
      });
      setSent(true);
      setNotif({ title: '', body: '', target: 'all' });
      setTimeout(() => setSent(false), 3000);
    } catch (e) {
      console.error('Push failed', e);
    } finally {
      setSending(false);
    }
  };

  const handleSaveFeatures = async () => {
    try {
      await api.request('/admin/mobile-config/', {
        method: 'POST',
        body: JSON.stringify({ mobile_features: features, force_update: forceUpdate }),
        headers: { 'Content-Type': 'application/json' },
      });
      setSaveMsg('Saved!');
      setTimeout(() => setSaveMsg(''), 2500);
    } catch {
      setSaveMsg('Save failed — check server');
      setTimeout(() => setSaveMsg(''), 3000);
    }
  };

  // ── Layout helpers ────────────────────────────────────────────────────────
  const card = {
    background: T?.cardBg || '#fff',
    borderRadius: 12,
    padding: 24,
    border: `1px solid ${T?.border || '#e0e0e0'}`,
    marginBottom: 24,
  };

  const h2 = { margin: 0, marginBottom: 20, fontSize: 17, fontWeight: 700, color: T?.txt };

  const statCard = (label, value, Icon, color) => (
    <div key={label} style={{ flex: '1 1 160px', background: T?.bg || '#f5f5f5', borderRadius: 10, padding: '16px 20px', display: 'flex', alignItems: 'center', gap: 14 }}>
      <div style={{ width: 42, height: 42, borderRadius: 10, background: color + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', color }}>
        <Icon size={20} />
      </div>
      <div>
        <div style={{ fontSize: 22, fontWeight: 800, color: T?.txt }}>{value ?? '—'}</div>
        <div style={{ fontSize: 12, color: T?.sub, marginTop: 2 }}>{label}</div>
      </div>
    </div>
  );

  const Toggle = ({ value, onChange }) => (
    <button
      onClick={() => onChange(!value)}
      style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, color: value ? GOLD : (T?.sub || '#aaa') }}
    >
      {value
        ? <ToggleRight size={28} />
        : <ToggleLeft  size={28} />
      }
    </button>
  );

  const featureLabels = {
    for_you_tab:    'For You Tab',
    explore_tab:    'Explore Tab',
    campaigns_tab:  'Campaigns Tab',
    categories_tab: 'Categories Tab',
    create_post:    'Create Post',
    gift_feature:   'Gift / Tipping',
    reel_comments:  'Reel Comments',
  };

  return (
    <div style={{ maxWidth: 900 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 28 }}>
        <div style={{ width: 44, height: 44, borderRadius: 12, background: GOLD + '20', display: 'flex', alignItems: 'center', justifyContent: 'center', color: GOLD }}>
          <Smartphone size={22} />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 24, fontWeight: 800, color: T?.txt }}>Mobile App</h1>
          <p style={{ margin: 0, fontSize: 13, color: T?.sub }}>Manage the React Native mobile app from here</p>
        </div>
      </div>

      {/* Live stats */}
      <div style={card}>
        <h2 style={h2}>📱 Live Mobile Stats</h2>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {statCard('Total Users',     stats?.users?.total,         Users,    '#3B82F6')}
          {statCard('Active (30 d)',   stats?.users?.active_month,  Activity, GOLD)}
          {statCard('New Today',       stats?.users?.new_today,     Zap,      '#10B981')}
          {statCard('Total Reels',     stats?.content?.total_reels, Download, '#8B5CF6')}
          {statCard('Platform',        'iOS + Android',             Globe,    '#EF4444')}
        </div>
        {loadingStats && (
          <div style={{ textAlign: 'center', color: T?.sub, padding: '12px 0', fontSize: 13 }}>
            <RefreshCw size={14} style={{ marginRight: 6, animation: 'spin 1s linear infinite' }} />
            Loading stats…
          </div>
        )}
      </div>

      {/* Push Notifications */}
      <div style={card}>
        <h2 style={{ ...h2, display: 'flex', alignItems: 'center', gap: 8 }}>
          <Bell size={18} color={GOLD} /> Push Notifications
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <input
            placeholder="Notification title"
            value={notif.title}
            onChange={e => setNotif(n => ({ ...n, title: e.target.value }))}
            style={{ padding: '10px 14px', borderRadius: 8, border: `1px solid ${T?.border || '#e0e0e0'}`, fontSize: 14, color: T?.txt, background: T?.bg, outline: 'none' }}
          />
          <textarea
            placeholder="Notification body / message"
            rows={3}
            value={notif.body}
            onChange={e => setNotif(n => ({ ...n, body: e.target.value }))}
            style={{ padding: '10px 14px', borderRadius: 8, border: `1px solid ${T?.border || '#e0e0e0'}`, fontSize: 14, color: T?.txt, background: T?.bg, resize: 'vertical', fontFamily: 'inherit', outline: 'none' }}
          />
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <select
              value={notif.target}
              onChange={e => setNotif(n => ({ ...n, target: e.target.value }))}
              style={{ padding: '9px 12px', borderRadius: 8, border: `1px solid ${T?.border || '#e0e0e0'}`, fontSize: 13, color: T?.txt, background: T?.bg, flex: '0 0 auto' }}
            >
              <option value="all">All users</option>
              <option value="active">Active (30d)</option>
              <option value="new">New (7d)</option>
            </select>
            <button
              onClick={handleSendPush}
              disabled={sending || !notif.title.trim() || !notif.body.trim()}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '10px 20px', borderRadius: 8, border: 'none',
                background: sending ? '#ccc' : GOLD,
                color: '#fff', fontWeight: 700, fontSize: 14,
                cursor: sending ? 'not-allowed' : 'pointer',
                transition: 'background 0.2s',
              }}
            >
              <Send size={14} /> {sending ? 'Sending…' : 'Send Push'}
            </button>
            {sent && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, color: '#10B981', fontSize: 13, fontWeight: 600 }}>
                <CheckCircle size={16} /> Sent!
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Feature Flags */}
      <div style={card}>
        <h2 style={{ ...h2, display: 'flex', alignItems: 'center', gap: 8 }}>
          <ToggleRight size={18} color={GOLD} /> Mobile Feature Flags
        </h2>
        <p style={{ margin: '0 0 16px', fontSize: 13, color: T?.sub }}>
          Toggle features on/off in the React Native app. Changes take effect on next app load.
        </p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {Object.keys(featureLabels).map(key => (
            <div key={key} style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 16px', background: T?.bg, borderRadius: 8,
            }}>
              <div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T?.txt }}>{featureLabels[key]}</div>
                <div style={{ fontSize: 12, color: T?.sub }}>
                  {features[key] ? '✅ Enabled' : '❌ Disabled'}
                </div>
              </div>
              <Toggle
                value={features[key]}
                onChange={val => setFeatures(f => ({ ...f, [key]: val }))}
              />
            </div>
          ))}
        </div>
      </div>

      {/* Force Update Banner */}
      <div style={card}>
        <h2 style={{ ...h2, display: 'flex', alignItems: 'center', gap: 8 }}>
          <RefreshCw size={18} color={GOLD} /> Force Update Banner
        </h2>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', background: T?.bg, borderRadius: 8 }}>
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: T?.txt }}>Enable Force-Update Banner</div>
              <div style={{ fontSize: 12, color: T?.sub }}>Show an update prompt to users below the minimum version</div>
            </div>
            <Toggle
              value={forceUpdate.enabled}
              onChange={val => setForceUpdate(fu => ({ ...fu, enabled: val }))}
            />
          </div>
          {forceUpdate.enabled && (
            <>
              <input
                placeholder="Minimum version (e.g. 2.0.0)"
                value={forceUpdate.min_version}
                onChange={e => setForceUpdate(fu => ({ ...fu, min_version: e.target.value }))}
                style={{ padding: '10px 14px', borderRadius: 8, border: `1px solid ${T?.border || '#e0e0e0'}`, fontSize: 14, color: T?.txt, background: T?.bg, outline: 'none' }}
              />
              <textarea
                placeholder="Update message shown to user…"
                rows={2}
                value={forceUpdate.message}
                onChange={e => setForceUpdate(fu => ({ ...fu, message: e.target.value }))}
                style={{ padding: '10px 14px', borderRadius: 8, border: `1px solid ${T?.border || '#e0e0e0'}`, fontSize: 14, color: T?.txt, background: T?.bg, resize: 'vertical', fontFamily: 'inherit', outline: 'none' }}
              />
            </>
          )}
        </div>
      </div>

      {/* Save button */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <button
          onClick={handleSaveFeatures}
          style={{
            padding: '12px 32px', borderRadius: 10, border: 'none',
            background: GOLD, color: '#fff', fontWeight: 700, fontSize: 15,
            cursor: 'pointer', boxShadow: `0 4px 16px ${GOLD}55`,
          }}
        >
          Save Mobile Config
        </button>
        {saveMsg && (
          <span style={{ fontSize: 13, fontWeight: 600, color: saveMsg.includes('fail') ? '#EF4444' : '#10B981' }}>
            {saveMsg.includes('fail') ? <XCircle size={14} style={{ marginRight: 4 }} /> : <CheckCircle size={14} style={{ marginRight: 4 }} />}
            {saveMsg}
          </span>
        )}
      </div>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}




