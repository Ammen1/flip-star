import { useState, useEffect } from 'react';
import { Bell, Send, Users, CheckCircle, Mail, Phone, User, Megaphone, MessageSquare, AlertTriangle, Zap, Clock, RefreshCw, X, ChevronDown, Search } from 'lucide-react';
import api from '../../api';

// ─── Channel metadata ──────────────────────────────────────────────────────────
const CHANNELS = [
  { id: 'mass', label: 'Mass Push', desc: 'Send to all active users instantly', icon: Megaphone, color: '#DA9B2A' },
  { id: 'in_app', label: 'By Username', desc: 'Target a specific FlipStar account', icon: User, color: '#7C3AED' },
  { id: 'email', label: 'By Email', desc: 'Send to a specific email address', icon: Mail, color: '#0EA5E9' },
  { id: 'phone', label: 'By Phone', desc: 'Send SMS to a phone number', icon: Phone, color: '#10B981' },
];

const NOTIF_TYPES = [
  { id: 'announcement', label: 'Announcement', color: '#DA9B2A' },
  { id: 'alert', label: 'Alert', color: '#EF4444' },
  { id: 'promo', label: 'Promotion', color: '#10B981' },
  { id: 'update', label: 'Update', color: '#3B82F6' },
  { id: 'warning', label: 'Warning', color: '#F59E0B' },
  { id: 'info', label: 'Info', color: '#6B7280' },
];

const STATUS_COLORS = { sent: '#10B981', pending: '#F59E0B', failed: '#EF4444', delivered: '#3B82F6' };

export function NotificationsPage({ theme }) {
  const [tab, setTab] = useState('compose');
  const [notifications, setNotifications] = useState([]);
  const [history, setHistory] = useState([]);
  const [loading, setLoading] = useState(true);
  const [histLoading, setHistLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [toast, setToast] = useState(null);

  // Compose state
  const [channel, setChannel] = useState('mass');
  const [target, setTarget] = useState('');
  const [title, setTitle] = useState('');
  const [message, setMessage] = useState('');
  const [notifType, setNotifType] = useState('announcement');
  const [priority, setPriority] = useState('normal');
  const [scheduleMode, setScheduleMode] = useState('now');
  const [scheduleTime, setScheduleTime] = useState('');

  const showToast = (msg, ok = true) => { setToast({ msg, ok }); setTimeout(() => setToast(null), 3500); };

  const resetCompose = () => { setTarget(''); setTitle(''); setMessage(''); setNotifType('announcement'); setPriority('normal'); setScheduleMode('now'); setScheduleTime(''); };

  useEffect(() => {
    loadInbox();
  }, []);

  const loadInbox = async () => {
    setLoading(true);
    try {
      const data = await api.request('/admin/notifications/');
      setNotifications(Array.isArray(data) ? data : []);
    } catch (e) { console.error(e); }
    finally { setLoading(false); }
  };

  const loadHistory = async () => {
    setHistLoading(true);
    try {
      const data = await api.request('/admin/notifications/sent/');
      setHistory(Array.isArray(data) ? data : []);
    } catch (e) {
      setHistory([]);
    } finally { setHistLoading(false); }
  };

  useEffect(() => { if (tab === 'history') loadHistory(); }, [tab]);

  const handleMarkRead = async (id) => {
    try {
      await api.request(`/admin/notifications/${id}/read/`, { method: 'POST' });
      setNotifications(prev => prev.filter(n => n.id !== id));
    } catch (e) { console.error(e); }
  };

  const handleSend = async () => {
    if (!title.trim() || !message.trim()) { showToast('Title and message are required', false); return; }
    if (channel !== 'mass' && !target.trim()) { showToast('Please enter a target', false); return; }
    setSending(true);
    try {
      const payload = {
        channel,
        target: channel === 'mass' ? null : target.trim(),
        title: title.trim(),
        message: message.trim(),
        notification_type: notifType,
        priority,
        schedule: scheduleMode === 'later' ? scheduleTime : null,
      };
      await api.request('/admin/notifications/send/', { method: 'POST', body: JSON.stringify(payload) });
      showToast('Notification sent successfully!');
      resetCompose();
      setTab('history');
    } catch (e) {
      showToast('Failed to send notification. Check API/logs.', false);
    } finally { setSending(false); }
  };

  const activeChannel = CHANNELS.find(c => c.id === channel);
  const activeType = NOTIF_TYPES.find(t => t.id === notifType);
  const charCount = message.length;
  const T = theme;

  const inputStyle = { width: '100%', padding: '11px 14px', border: `1px solid ${T.border}`, borderRadius: 9, fontSize: 14, outline: 'none', background: T.card, color: T.txt, boxSizing: 'border-box', fontFamily: 'inherit' };
  const labelStyle = { display: 'block', fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 7 };

  return (
    <div style={{ position: 'relative' }}>
      {/* Toast */}
      {toast && (
        <div style={{ position: 'fixed', bottom: 24, right: 24, zIndex: 9999, padding: '13px 20px', borderRadius: 10, background: toast.ok ? '#10B981' : '#EF4444', color: '#fff', fontSize: 14, fontWeight: 600, boxShadow: '0 4px 20px rgba(0,0,0,0.18)', display: 'flex', alignItems: 'center', gap: 10 }}>
          {toast.ok ? <CheckCircle size={16} /> : <AlertTriangle size={16} />} {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 700, color: T.txt }}>Notifications Center</h1>
          <p style={{ margin: '4px 0 0', fontSize: 13, color: T.sub }}>Compose and send notifications across every channel</p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={loadInbox} style={{ padding: '9px 14px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: T.txt }}>
            <RefreshCw size={13} /> Refresh
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 0, marginBottom: 24, background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 4, width: 'fit-content' }}>
        {[['compose', Send, 'Compose'], ['inbox', Bell, `Inbox${notifications.length ? ` (${notifications.length})` : ''}`], ['history', Clock, 'Sent History']].map(([id, Icon, label]) => (
          <button key={id} onClick={() => setTab(id)}
            style={{ padding: '9px 18px', background: tab === id ? T.pri : 'transparent', border: 'none', borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 7, fontSize: 13, fontWeight: 600, color: tab === id ? '#fff' : T.sub, transition: 'all 0.15s' }}>
            <Icon size={14} /> {label}
          </button>
        ))}
      </div>

      {/* ── COMPOSE TAB ── */}
      {tab === 'compose' && (
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 340px', gap: 22 }}>
          {/* Left: Form */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>

            {/* Channel selector */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: T.txt, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Delivery Channel</div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
                {CHANNELS.map(ch => {
                  const Icon = ch.icon;
                  const active = channel === ch.id;
                  return (
                    <button key={ch.id} onClick={() => { setChannel(ch.id); setTarget(''); }}
                      style={{ padding: '12px 14px', background: active ? ch.color + '15' : T.bg, border: `2px solid ${active ? ch.color : T.border}`, borderRadius: 10, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <Icon size={16} color={active ? ch.color : T.sub} />
                        <span style={{ fontSize: 13, fontWeight: 700, color: active ? ch.color : T.txt }}>{ch.label}</span>
                      </div>
                      <div style={{ fontSize: 11, color: T.sub }}>{ch.desc}</div>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Target (only for non-mass) */}
            {channel !== 'mass' && (
              <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
                <label style={labelStyle}>
                  {channel === 'in_app' ? 'FlipStar Username' : channel === 'email' ? 'Email Address' : 'Phone Number'}
                </label>
                <div style={{ position: 'relative' }}>
                  <div style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: T.sub }}>
                    {channel === 'in_app' ? <User size={15} /> : channel === 'email' ? <Mail size={15} /> : <Phone size={15} />}
                  </div>
                  <input
                    value={target} onChange={e => setTarget(e.target.value)}
                    placeholder={channel === 'in_app' ? '@username' : channel === 'email' ? 'user@example.com' : '+1234567890'}
                    style={{ ...inputStyle, paddingLeft: 34 }} />
                </div>
              </div>
            )}

            {/* Title + Message */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div>
                <label style={labelStyle}>Notification Title</label>
                <input value={title} onChange={e => setTitle(e.target.value)} placeholder="Enter a clear, concise title" style={inputStyle} maxLength={100} />
                <div style={{ fontSize: 11, color: T.sub, marginTop: 4, textAlign: 'right' }}>{title.length}/100</div>
              </div>
              <div>
                <label style={labelStyle}>Message Body</label>
                <textarea value={message} onChange={e => setMessage(e.target.value)} placeholder="Write your notification message here..." rows={4}
                  style={{ ...inputStyle, resize: 'vertical', lineHeight: 1.6 }} maxLength={500} />
                <div style={{ fontSize: 11, color: charCount > 460 ? '#EF4444' : T.sub, marginTop: 4, textAlign: 'right' }}>{charCount}/500</div>
              </div>
            </div>

            {/* Type + Priority */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
                <div>
                  <label style={labelStyle}>Notification Type</label>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {NOTIF_TYPES.map(t => (
                      <button key={t.id} onClick={() => setNotifType(t.id)}
                        style={{ padding: '6px 12px', background: notifType === t.id ? t.color : T.bg, border: `1px solid ${notifType === t.id ? t.color : T.border}`, borderRadius: 7, cursor: 'pointer', fontSize: 12, fontWeight: 600, color: notifType === t.id ? '#fff' : T.sub, transition: 'all 0.12s' }}>
                        {t.label}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <label style={labelStyle}>Priority</label>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {[['low', T.sub, 'Low'], ['normal', T.blue, 'Normal'], ['high', T.orange, 'High'], ['critical', T.red, 'Critical']].map(([val, col, lbl]) => (
                      <button key={val} onClick={() => setPriority(val)}
                        style={{ padding: '7px 12px', background: priority === val ? col + '20' : T.bg, border: `1px solid ${priority === val ? col : T.border}`, borderRadius: 7, cursor: 'pointer', fontSize: 12, fontWeight: 600, color: priority === val ? col : T.sub, textAlign: 'left', display: 'flex', alignItems: 'center', gap: 7 }}>
                        <div style={{ width: 8, height: 8, borderRadius: '50%', background: col }} /> {lbl}
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* Schedule */}
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, padding: 20 }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: T.txt, marginBottom: 12 }}>Delivery Schedule</div>
              <div style={{ display: 'flex', gap: 10, marginBottom: scheduleMode === 'later' ? 14 : 0 }}>
                {[['now', Zap, 'Send Now'], ['later', Clock, 'Schedule Later']].map(([val, Icon, lbl]) => (
                  <button key={val} onClick={() => setScheduleMode(val)}
                    style={{ flex: 1, padding: '10px', background: scheduleMode === val ? T.pri + '15' : T.bg, border: `1.5px solid ${scheduleMode === val ? T.pri : T.border}`, borderRadius: 9, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7, fontSize: 13, fontWeight: 600, color: scheduleMode === val ? T.pri : T.sub }}>
                    <Icon size={14} /> {lbl}
                  </button>
                ))}
              </div>
              {scheduleMode === 'later' && (
                <input type="datetime-local" value={scheduleTime} onChange={e => setScheduleTime(e.target.value)} style={inputStyle} />
              )}
            </div>

            {/* Send button */}
            <button onClick={handleSend} disabled={sending}
              style={{ padding: '14px', background: sending ? T.sub : T.pri, border: 'none', borderRadius: 12, color: '#fff', fontSize: 15, fontWeight: 700, cursor: sending ? 'not-allowed' : 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 10, transition: 'all 0.15s' }}>
              {sending ? <><div style={{ width: 16, height: 16, border: '2px solid #fff4', borderTopColor: '#fff', borderRadius: '50%', animation: 'spin 0.7s linear infinite' }} /> Sending...</> : <><Send size={16} /> {scheduleMode === 'later' ? 'Schedule Notification' : channel === 'mass' ? 'Send to All Users' : 'Send Notification'}</>}
            </button>
            <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
          </div>

          {/* Right: Preview card */}
          <div style={{ position: 'sticky', top: 20, height: 'fit-content' }}>
            <div style={{ fontSize: 12, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 10 }}>Preview</div>
            {/* Phone mockup */}
            <div style={{ background: '#111', borderRadius: 26, padding: '10px 6px 14px', boxShadow: '0 8px 32px rgba(0,0,0,0.3)', width: 240, margin: '0 auto' }}>
              <div style={{ background: '#f2f2f2', borderRadius: 20, overflow: 'hidden', minHeight: 340, padding: '0 0 10px' }}>
                <div style={{ background: '#fff', padding: '14px 14px 10px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #eee' }}>
                  <div style={{ fontSize: 12, fontWeight: 800, color: T.pri }}>FlipStar</div>
                  <div style={{ fontSize: 10, color: '#999' }}>now</div>
                </div>
                {/* Notification banner */}
                <div style={{ margin: '14px 10px 0', background: '#fff', borderRadius: 12, padding: '12px', boxShadow: '0 2px 12px rgba(0,0,0,0.1)' }}>
                  <div style={{ display: 'flex', alignItems: 'flex-start', gap: 8 }}>
                    <div style={{ width: 32, height: 32, borderRadius: 8, background: activeChannel?.color || T.pri, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      {activeChannel && <activeChannel.icon size={16} color="#fff" />}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 5, marginBottom: 3 }}>
                        <span style={{ fontSize: 11, fontWeight: 700, color: '#111' }}>FlipStar</span>
                        {activeType && <span style={{ fontSize: 9, fontWeight: 700, padding: '1px 5px', borderRadius: 4, background: activeType.color + '20', color: activeType.color }}>{activeType.label}</span>}
                      </div>
                      <div style={{ fontSize: 12, fontWeight: 700, color: '#111', marginBottom: 2, wordBreak: 'break-word' }}>{title || 'Notification title'}</div>
                      <div style={{ fontSize: 11, color: '#666', lineHeight: 1.4, wordBreak: 'break-word' }}>{message || 'Your message body will appear here...'}</div>
                    </div>
                  </div>
                </div>
                {/* Audience badge */}
                <div style={{ margin: '12px 10px 0', padding: '8px 12px', background: (activeChannel?.color || T.pri) + '15', borderRadius: 8, display: 'flex', alignItems: 'center', gap: 7 }}>
                  {channel === 'mass' ? <Users size={13} color={activeChannel?.color} /> : activeChannel && <activeChannel.icon size={13} color={activeChannel.color} />}
                  <span style={{ fontSize: 11, fontWeight: 600, color: activeChannel?.color }}>
                    {channel === 'mass' ? 'All users' : target || 'No target set'}
                  </span>
                </div>
              </div>
            </div>
            {/* Meta info */}
            <div style={{ marginTop: 14, padding: 12, background: T.card, border: `1px solid ${T.border}`, borderRadius: 10 }}>
              {[
                ['Channel', activeChannel?.label || '—'],
                ['Type', activeType?.label || '—'],
                ['Priority', priority],
                ['Schedule', scheduleMode === 'now' ? 'Immediately' : scheduleTime || 'Not set'],
              ].map(([k, v]) => (
                <div key={k} style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                  <span style={{ fontSize: 12, color: T.sub }}>{k}</span>
                  <span style={{ fontSize: 12, fontWeight: 600, color: T.txt }}>{v}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── INBOX TAB ── */}
      {tab === 'inbox' && (
        <div>
          {loading ? (
            <div style={{ padding: 60, textAlign: 'center', color: T.sub }}>Loading…</div>
          ) : notifications.length === 0 ? (
            <div style={{ background: T.card, borderRadius: 14, padding: 60, textAlign: 'center', border: `1px solid ${T.border}` }}>
              <Bell size={44} color={T.sub} style={{ marginBottom: 12 }} />
              <div style={{ fontSize: 16, fontWeight: 600, color: T.txt, marginBottom: 6 }}>Inbox is empty</div>
              <div style={{ fontSize: 13, color: T.sub }}>No unread system alerts at this time.</div>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {notifications.map(n => {
                const pColors = { critical: T.red, high: T.orange, medium: T.blue, low: T.sub };
                const pc = pColors[n.priority] || T.sub;
                return (
                  <div key={n.id} style={{ background: T.card, borderRadius: 12, padding: 18, border: `1px solid ${T.border}`, borderLeft: `4px solid ${pc}`, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 16 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 7 }}>
                        <span style={{ padding: '2px 8px', borderRadius: 5, fontSize: 10, fontWeight: 700, textTransform: 'uppercase', background: pc + '20', color: pc }}>{n.priority || 'info'}</span>
                        <span style={{ fontSize: 12, color: T.sub }}>{new Date(n.created_at).toLocaleString()}</span>
                      </div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: T.txt, marginBottom: 5 }}>{n.title}</div>
                      <div style={{ fontSize: 13, color: T.sub, lineHeight: 1.6 }}>{n.message}</div>
                    </div>
                    <button onClick={() => handleMarkRead(n.id)}
                      style={{ padding: '7px 14px', background: '#10B98115', border: 'none', borderRadius: 7, color: '#10B981', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 5, flexShrink: 0 }}>
                      <CheckCircle size={13} /> Done
                    </button>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ── HISTORY TAB ── */}
      {tab === 'history' && (
        <div>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
            <div style={{ fontSize: 14, color: T.sub }}>{history.length} notifications sent</div>
            <button onClick={loadHistory} style={{ padding: '7px 14px', background: T.card, border: `1px solid ${T.border}`, borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, color: T.txt }}>
              <RefreshCw size={12} /> Reload
            </button>
          </div>
          {histLoading ? (
            <div style={{ padding: 60, textAlign: 'center', color: T.sub }}>Loading history…</div>
          ) : history.length === 0 ? (
            <div style={{ background: T.card, borderRadius: 14, padding: 60, textAlign: 'center', border: `1px solid ${T.border}` }}>
              <Clock size={44} color={T.sub} style={{ marginBottom: 12 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 6 }}>No sent history yet</div>
              <div style={{ fontSize: 13, color: T.sub }}>Sent notifications will appear here.</div>
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 14, overflow: 'hidden' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 120px 100px 110px 100px', padding: '10px 18px', background: T.bg, borderBottom: `1px solid ${T.border}`, fontSize: 11, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: '0.5px', gap: 12 }}>
                <span>Notification</span><span>Channel</span><span>Target</span><span>Sent At</span><span>Status</span>
              </div>
              {history.map((h, i) => {
                const sc = STATUS_COLORS[h.status] || T.sub;
                const ch = CHANNELS.find(c => c.id === h.channel);
                return (
                  <div key={h.id || i} style={{ display: 'grid', gridTemplateColumns: '1fr 120px 100px 110px 100px', padding: '13px 18px', borderBottom: i < history.length - 1 ? `1px solid ${T.border}` : 'none', alignItems: 'center', gap: 12 }}>
                    <div>
                      <div style={{ fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 2 }}>{h.title}</div>
                      <div style={{ fontSize: 11, color: T.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.message}</div>
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                      {ch && <ch.icon size={12} color={ch.color} />}
                      <span style={{ fontSize: 12, color: T.txt }}>{ch?.label || h.channel}</span>
                    </div>
                    <div style={{ fontSize: 12, color: T.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{h.target || 'All'}</div>
                    <div style={{ fontSize: 11, color: T.sub }}>{h.sent_at ? new Date(h.sent_at).toLocaleDateString() : '—'}</div>
                    <div style={{ padding: '3px 8px', background: sc + '20', borderRadius: 5, fontSize: 11, fontWeight: 700, color: sc, textTransform: 'capitalize', width: 'fit-content' }}>{h.status || 'sent'}</div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}
    </div>
  );
}




