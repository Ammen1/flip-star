import { useState, useEffect } from 'react';
import { Flag, CheckCircle, XCircle, AlertCircle, Eye, Trash2, User, FileVideo, MessageSquare, RefreshCw, ShieldAlert, Ban, AlertOctagon, Clock, ChevronDown, ChevronUp, ExternalLink } from 'lucide-react';
import api from '../../api';

const PRIORITY_COLORS = {
  critical: '#EF4444',
  high: '#F59E0B',
  medium: '#3B82F6',
  low: '#6B7280',
};

const REPORT_TYPE_LABELS = {
  inappropriate: 'Inappropriate',
  spam: 'Spam',
  harassment: 'Harassment',
  copyright: 'Copyright',
  scam: 'Scam/Fraud',
  hate_speech: 'Hate Speech',
  self_harm: 'Self Harm',
  violence: 'Violence',
  other: 'Other',
};

const MODERATION_ACTIONS = [
  { value: 'warning', label: 'Issue Warning', icon: AlertOctagon, color: '#F59E0B', desc: 'Send a warning to the user without removing content.' },
  { value: 'content_removed', label: 'Remove Content', icon: Trash2, color: '#EF4444', desc: 'Delete the reported reel or comment.' },
  { value: 'shadowban', label: 'Shadow Ban', icon: Eye, color: '#8B5CF6', desc: "Hide user's content from others without notifying them." },
  { value: 'temp_ban', label: 'Temporary Ban', icon: Clock, color: '#F97316', desc: 'Restrict user posting for 24–72 hours.' },
  { value: 'permanent_ban', label: 'Permanent Ban', icon: Ban, color: '#DC2626', desc: 'Permanently deactivate the user account.' },
  { value: 'no_action', label: 'No Action', icon: CheckCircle, color: '#6B7280', desc: 'Dismiss — report does not violate guidelines.' },
];

export function ReportsPage({ theme }) {
  const [reports, setReports] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [selectedReport, setSelectedReport] = useState(null);
  const [filterStatus, setFilterStatus] = useState('all');
  const [filterPriority, setFilterPriority] = useState('all');
  const [resolutionNotes, setResolutionNotes] = useState('');
  const [selectedAction, setSelectedAction] = useState('');
  const [moderating, setModerating] = useState(false);
  const [toast, setToast] = useState(null);

  const showToast = (msg, isError = false) => {
    setToast({ msg, isError });
    setTimeout(() => setToast(null), 3000);
  };

  useEffect(() => {
    fetchReports();
    fetchStats();
  }, [filterStatus]);

  const fetchReports = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (filterStatus !== 'all') params.set('status', filterStatus);
      const qs = params.toString() ? `?${params}` : '';
      const response = await api.request(`/admin/reports/${qs}`);
      setReports(response || []);
    } catch (error) {
      console.error('Failed to fetch reports:', error);
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await api.request('/admin/reports/stats/');
      setStats(response);
    } catch (error) {
      console.error('Failed to fetch stats:', error);
    }
  };

  const handleMarkReviewing = async (reportId) => {
    try {
      await api.request(`/admin/reports/${reportId}/`, {
        method: 'PUT',
        body: JSON.stringify({ status: 'reviewing' }),
      });
      fetchReports(); fetchStats();
      setSelectedReport(prev => prev ? { ...prev, status: 'reviewing' } : null);
    } catch (e) { showToast('Failed to update status', true); }
  };

  const handleModerate = async () => {
    if (!selectedAction) { showToast('Please select an action', true); return; }
    setModerating(true);
    try {
      await api.request(`/admin/reports/${selectedReport.id}/moderate/`, {
        method: 'POST',
        body: JSON.stringify({ action_taken: selectedAction, reason_details: resolutionNotes }),
      });
      showToast('Moderation action applied successfully');
      setSelectedReport(null);
      setSelectedAction('');
      setResolutionNotes('');
      fetchReports(); fetchStats();
    } catch (e) {
      showToast('Failed to apply moderation action', true);
    } finally {
      setModerating(false);
    }
  };

  const getStatusColor = (s) => ({ pending: '#F59E0B', reviewing: '#3B82F6', resolved: '#10B981', dismissed: '#6B7280' }[s] || theme.txt);
  const getStatusIcon = (s) => ({ pending: AlertCircle, reviewing: Eye, resolved: CheckCircle, dismissed: XCircle }[s] || Flag);

  const visibleReports = filterPriority === 'all' ? reports : reports.filter(r => r.priority === filterPriority);

  return (
    <div style={{ position: 'relative' }}>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 24, right: 24, zIndex: 9999,
          padding: '12px 20px', borderRadius: 10,
          background: toast.isError ? '#EF4444' : '#10B981',
          color: '#fff', fontWeight: 600, fontSize: 14,
          boxShadow: '0 4px 16px rgba(0,0,0,0.2)',
        }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 4 }}>
            Reports &amp; Moderation
          </h1>
          <p style={{ fontSize: 14, color: theme.sub }}>Review, investigate and act on user reports</p>
        </div>
        <button onClick={() => { fetchReports(); fetchStats(); }}
          style={{ padding: '10px 16px', background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, fontSize: 14, color: theme.txt }}>
          <RefreshCw size={16} /> Refresh
        </button>
      </div>

      {/* Stats */}
      {stats && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(130px, 1fr))', gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Total', value: stats.total_reports, color: theme.txt },
            { label: 'Pending', value: stats.pending_reports, color: '#F59E0B' },
            { label: 'Reviewing', value: stats.reviewing_reports, color: '#3B82F6' },
            { label: 'Resolved', value: stats.resolved_reports, color: '#10B981' },
            { label: 'Dismissed', value: stats.dismissed_reports, color: '#6B7280' },
          ].map(s => (
            <div key={s.label} style={{ padding: '14px 16px', background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}` }}>
              <div style={{ fontSize: 26, fontWeight: 700, color: s.color }}>{s.value ?? 0}</div>
              <div style={{ fontSize: 12, color: theme.sub, marginTop: 2 }}>{s.label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Filters row */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap', alignItems: 'center' }}>
        {/* Status tabs */}
        <div style={{ display: 'flex', gap: 4, background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 4 }}>
          {['all', 'pending', 'reviewing', 'resolved', 'dismissed'].map(s => (
            <button key={s} onClick={() => setFilterStatus(s)}
              style={{ padding: '6px 12px', background: filterStatus === s ? theme.pri : 'transparent', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: filterStatus === s ? '#fff' : theme.sub, textTransform: 'capitalize' }}>
              {s}
            </button>
          ))}
        </div>
        {/* Priority filter */}
        <div style={{ display: 'flex', gap: 4, background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 8, padding: 4 }}>
          {['all', 'critical', 'high', 'medium', 'low'].map(p => (
            <button key={p} onClick={() => setFilterPriority(p)}
              style={{ padding: '6px 12px', background: filterPriority === p ? (PRIORITY_COLORS[p] || theme.pri) : 'transparent', border: 'none', borderRadius: 6, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: filterPriority === p ? '#fff' : theme.sub, textTransform: 'capitalize' }}>
              {p}
            </button>
          ))}
        </div>
      </div>

      {/* Reports list */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 60, color: theme.sub }}>Loading reports...</div>
      ) : visibleReports.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 60, background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}` }}>
          <Flag size={48} style={{ color: theme.sub, marginBottom: 12 }} />
          <h3 style={{ fontSize: 18, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>No reports found</h3>
          <p style={{ fontSize: 14, color: theme.sub }}>No {filterStatus !== 'all' ? filterStatus : ''} {filterPriority !== 'all' ? filterPriority + ' priority' : ''} reports at this time.</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
          {visibleReports.map((report) => {
            const StatusIcon = getStatusIcon(report.status);
            const priorityColor = PRIORITY_COLORS[report.priority] || '#6B7280';
            return (
              <div key={report.id} onClick={() => { setSelectedReport(report); setSelectedAction(''); setResolutionNotes(''); }}
                style={{ padding: 16, background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}`, cursor: 'pointer', transition: 'box-shadow 0.15s' }}
                onMouseEnter={e => e.currentTarget.style.boxShadow = '0 2px 10px rgba(0,0,0,0.08)'}
                onMouseLeave={e => e.currentTarget.style.boxShadow = 'none'}>

                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                    <div style={{ width: 40, height: 40, borderRadius: '50%', background: `${getStatusColor(report.status)}20`, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <StatusIcon size={20} color={getStatusColor(report.status)} />
                    </div>
                    <div>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>
                          {REPORT_TYPE_LABELS[report.report_type] || report.report_type}
                        </span>
                        <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 700, background: priorityColor + '20', color: priorityColor, textTransform: 'uppercase' }}>
                          {report.priority}
                        </span>
                        <span style={{ padding: '2px 8px', borderRadius: 20, fontSize: 11, fontWeight: 600, background: getStatusColor(report.status) + '20', color: getStatusColor(report.status), textTransform: 'capitalize' }}>
                          {report.status}
                        </span>
                      </div>
                      <div style={{ fontSize: 12, color: theme.sub, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
                        <span>By: <strong>{report.reported_by?.username || 'Unknown'}</strong></span>
                        <span>•</span>
                        {report.reported_user && <span><User size={11} style={{ display: 'inline' }} /> Against: <strong>{report.reported_user?.username}</strong></span>}
                        {report.reported_reel && <span><FileVideo size={11} style={{ display: 'inline' }} /> Reel #{typeof report.reported_reel === 'object' ? report.reported_reel.id : report.reported_reel}</span>}
                        <span>•</span>
                        <span>{new Date(report.created_at).toLocaleDateString()}</span>
                      </div>
                    </div>
                  </div>
                  <span style={{ fontSize: 12, color: theme.sub, whiteSpace: 'nowrap' }}>#{report.id}</span>
                </div>

                {report.description && (
                  <div style={{ marginTop: 10, padding: '8px 12px', background: theme.bg, borderRadius: 8, fontSize: 13, color: theme.sub, borderLeft: `3px solid ${priorityColor}` }}>
                    {report.description.length > 100 ? report.description.slice(0, 100) + '...' : report.description}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Detail / Moderation Modal */}
      {selectedReport && (
        <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}
          onClick={() => setSelectedReport(null)}>
          <div style={{ background: theme.card, borderRadius: 20, padding: 28, width: '100%', maxWidth: 620, maxHeight: '90vh', overflow: 'auto' }}
            onClick={e => e.stopPropagation()}>

            {/* Modal Header */}
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
              <div>
                <h2 style={{ fontSize: 20, fontWeight: 700, color: theme.txt, margin: 0 }}>Report #{selectedReport.id}</h2>
                <span style={{ fontSize: 13, color: theme.sub }}>Submitted {new Date(selectedReport.created_at).toLocaleString()}</span>
              </div>
              <button onClick={() => setSelectedReport(null)} style={{ background: 'none', border: 'none', fontSize: 22, cursor: 'pointer', color: theme.sub }}>×</button>
            </div>

            {/* Badges row */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
              <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 700, background: (PRIORITY_COLORS[selectedReport.priority] || '#888') + '20', color: PRIORITY_COLORS[selectedReport.priority] || '#888', textTransform: 'uppercase' }}>
                {selectedReport.priority} priority
              </span>
              <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: getStatusColor(selectedReport.status) + '20', color: getStatusColor(selectedReport.status), textTransform: 'capitalize' }}>
                {selectedReport.status}
              </span>
              <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: theme.border, color: theme.txt }}>
                {REPORT_TYPE_LABELS[selectedReport.report_type] || selectedReport.report_type}
              </span>
              <span style={{ padding: '4px 12px', borderRadius: 20, fontSize: 12, fontWeight: 600, background: theme.border, color: theme.txt, textTransform: 'capitalize' }}>
                Target: {selectedReport.target_type || 'reel'}
              </span>
            </div>

            {/* Two-column info */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
              <InfoBlock label="Reported By" value={selectedReport.reported_by?.username || 'Unknown'} theme={theme} />
              <InfoBlock label="Against User" value={selectedReport.reported_user?.username || '—'} theme={theme} />
              {selectedReport.reported_reel && (
                <InfoBlock label="Reported Reel" value={`#${typeof selectedReport.reported_reel === 'object' ? selectedReport.reported_reel.id : selectedReport.reported_reel}`} theme={theme} />
              )}
              {selectedReport.reviewed_by && (
                <InfoBlock label="Reviewed By" value={selectedReport.reviewed_by?.username} theme={theme} />
              )}
            </div>

            {/* Description */}
            <div style={{ marginBottom: 20 }}>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>REPORTER'S DESCRIPTION</div>
              <div style={{ padding: 14, background: theme.bg, borderRadius: 10, fontSize: 14, color: theme.txt, lineHeight: 1.6 }}>
                {selectedReport.description || 'No description provided.'}
              </div>
            </div>

            {/* Content preview if reel attached */}
            {selectedReport.reported_reel && typeof selectedReport.reported_reel === 'object' && selectedReport.reported_reel.media && (
              <div style={{ marginBottom: 20 }}>
                <div style={{ fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>REPORTED CONTENT</div>
                <video src={selectedReport.reported_reel.media} style={{ width: '100%', maxHeight: 240, borderRadius: 10, background: '#000', objectFit: 'cover' }} controls />
                {selectedReport.reported_reel.caption && (
                  <p style={{ fontSize: 13, color: theme.sub, marginTop: 6 }}>{selectedReport.reported_reel.caption}</p>
                )}
              </div>
            )}

            {/* Resolution notes if already resolved */}
            {selectedReport.resolution_notes && (
              <div style={{ marginBottom: 20, padding: 12, background: '#10B98115', borderRadius: 10, border: '1px solid #10B981' }}>
                <div style={{ fontSize: 12, color: '#10B981', fontWeight: 700, marginBottom: 4 }}>RESOLUTION NOTES</div>
                <div style={{ fontSize: 14, color: theme.txt }}>{selectedReport.resolution_notes}</div>
              </div>
            )}

            {/* Moderation action section — only for open reports */}
            {(selectedReport.status === 'pending' || selectedReport.status === 'reviewing') && (
              <>
                {selectedReport.status === 'pending' && (
                  <button onClick={() => handleMarkReviewing(selectedReport.id)}
                    style={{ width: '100%', padding: '10px', marginBottom: 16, background: '#3B82F6', border: 'none', borderRadius: 10, color: '#fff', fontWeight: 600, fontSize: 14, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8 }}>
                    <Eye size={16} /> Mark as Under Review
                  </button>
                )}

                <div style={{ fontSize: 12, color: theme.sub, marginBottom: 10, fontWeight: 600 }}>SELECT MODERATION ACTION</div>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 16 }}>
                  {MODERATION_ACTIONS.map(act => {
                    const Icon = act.icon;
                    const isSelected = selectedAction === act.value;
                    return (
                      <button key={act.value} onClick={() => setSelectedAction(act.value)}
                        style={{ padding: '10px 12px', background: isSelected ? act.color + '20' : theme.bg, border: `2px solid ${isSelected ? act.color : theme.border}`, borderRadius: 10, cursor: 'pointer', textAlign: 'left', transition: 'all 0.15s' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                          <Icon size={15} color={act.color} />
                          <span style={{ fontSize: 13, fontWeight: 700, color: act.color }}>{act.label}</span>
                        </div>
                        <div style={{ fontSize: 11, color: theme.sub, lineHeight: 1.4 }}>{act.desc}</div>
                      </button>
                    );
                  })}
                </div>

                <div style={{ marginBottom: 16 }}>
                  <div style={{ fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>INTERNAL NOTES (optional)</div>
                  <textarea value={resolutionNotes} onChange={e => setResolutionNotes(e.target.value)}
                    placeholder="Add notes about your decision…"
                    style={{ width: '100%', padding: 12, border: `1px solid ${theme.border}`, borderRadius: 10, fontSize: 14, fontFamily: 'inherit', minHeight: 80, resize: 'vertical', boxSizing: 'border-box', background: theme.bg, color: theme.txt }} />
                </div>

                <button onClick={handleModerate} disabled={moderating || !selectedAction}
                  style={{ width: '100%', padding: 14, background: selectedAction ? (MODERATION_ACTIONS.find(a => a.value === selectedAction)?.color || theme.pri) : theme.border, border: 'none', borderRadius: 12, color: '#fff', fontWeight: 700, fontSize: 15, cursor: selectedAction ? 'pointer' : 'not-allowed', opacity: moderating ? 0.7 : 1 }}>
                  {moderating ? 'Applying action…' : selectedAction ? `Apply: ${MODERATION_ACTIONS.find(a => a.value === selectedAction)?.label}` : 'Select an action above'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function InfoBlock({ label, value, theme }) {
  return (
    <div style={{ padding: '10px 14px', background: '#00000008', borderRadius: 10 }}>
      <div style={{ fontSize: 11, color: '#9CA3AF', fontWeight: 600, marginBottom: 3, textTransform: 'uppercase' }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 600, color: theme?.txt || '#111' }}>{value}</div>
    </div>
  );
}




