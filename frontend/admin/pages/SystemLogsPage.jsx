import { useState, useEffect, useRef, useCallback } from 'react';
import {
  FileText, AlertCircle, Info, AlertTriangle, Shield,
  RefreshCw, Download, Trash2, Search, X, ChevronLeft, ChevronRight,
} from 'lucide-react';
import api from '../../api';

const LOG_TYPES = [
  { id: 'all',      label: 'All Logs',  icon: FileText,       colorKey: 'txt'    },
  { id: 'info',     label: 'Info',      icon: Info,            colorKey: 'blue'   },
  { id: 'warning',  label: 'Warning',   icon: AlertTriangle,  colorKey: 'orange' },
  { id: 'error',    label: 'Error',     icon: AlertCircle,    colorKey: 'red'    },
  { id: 'critical', label: 'Critical',  icon: AlertCircle,    colorKey: 'red'    },
  { id: 'security', label: 'Security',  icon: Shield,          colorKey: 'purple' },
];

function exportCSV(logs) {
  const header = ['ID', 'Type', 'Message', 'User', 'IP', 'Endpoint', 'Time'];
  const rows = logs.map(l => [
    l.id, l.log_type,
    `"${(l.message || '').replace(/"/g, '""')}"`,
    l.user || '', l.ip_address || '', l.endpoint || '',
    new Date(l.created_at).toISOString(),
  ]);
  const csv = [header, ...rows].map(r => r.join(',')).join('\n');
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url;
  a.download = `system-logs-${Date.now()}.csv`; a.click();
  URL.revokeObjectURL(url);
}

export function SystemLogsPage({ theme }) {
  const [logs, setLogs]           = useState([]);
  const [loading, setLoading]     = useState(true);
  const [filter, setFilter]       = useState('all');
  const [search, setSearch]       = useState('');
  const [debouncedSearch, setDS]  = useState('');
  const [page, setPage]           = useState(1);
  const [total, setTotal]         = useState(0);
  const [totalPages, setTotalPages] = useState(1);
  const [clearing, setClearing]   = useState(false);
  const [confirmClear, setConfirmClear] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setDS(search), 350);
    return () => clearTimeout(t);
  }, [search]);

  useEffect(() => { setPage(1); }, [filter, debouncedSearch]);

  useEffect(() => { loadLogs(); }, [page, filter, debouncedSearch]);

  const loadLogs = useCallback(async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams({ page, page_size: 50 });
      if (filter !== 'all') params.set('type', filter);
      if (debouncedSearch)  params.set('search', debouncedSearch);
      const response = await api.request(`/admin/logs/?${params}`);
      setLogs(response?.logs || []);
      setTotal(response?.total || 0);
      setTotalPages(response?.total_pages || 1);
    } catch (err) {
      console.error('Failed to load logs:', err);
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [page, filter, debouncedSearch]);

  const handleClearLogs = async () => {
    if (!confirmClear) { setConfirmClear(true); return; }
    try {
      setClearing(true);
      await api.request('/admin/logs/clear/', { method: 'POST', body: JSON.stringify({ log_type: filter }) });
      setConfirmClear(false);
      loadLogs();
    } catch (err) {
      console.error('Clear failed:', err);
    } finally {
      setClearing(false);
    }
  };

  const logMeta = {
    all:      { icon: FileText,      color: theme.txt    },
    info:     { icon: Info,          color: theme.blue   },
    warning:  { icon: AlertTriangle, color: theme.orange },
    error:    { icon: AlertCircle,   color: theme.red    },
    critical: { icon: AlertCircle,   color: theme.red    },
    security: { icon: Shield,        color: theme.purple },
  };

  const getIcon  = (t) => (logMeta[t]?.icon  || FileText);
  const getColor = (t) => (logMeta[t]?.color || theme.txt);

  const btnBase = {
    display: 'flex', alignItems: 'center', gap: 6,
    padding: '8px 14px', borderRadius: 8, fontSize: 13,
    fontWeight: 600, cursor: 'pointer', border: 'none',
  };

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: theme.txt, marginBottom: 4 }}>
            System Logs
          </h1>
          <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
            Monitor system activity and events · {total.toLocaleString()} total entries
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => { setConfirmClear(false); loadLogs(); }}
            style={{ ...btnBase, background: theme.bg, border: `1px solid ${theme.border}`, color: theme.txt }}>
            <RefreshCw size={14} />Refresh
          </button>
          <button onClick={() => exportCSV(logs)} disabled={!logs.length}
            style={{ ...btnBase, background: theme.bg, border: `1px solid ${theme.border}`, color: theme.txt, opacity: logs.length ? 1 : 0.4 }}>
            <Download size={14} />Export CSV
          </button>
          <button
            onClick={handleClearLogs}
            disabled={clearing}
            style={{ ...btnBase,
              background: confirmClear ? theme.red : theme.bg,
              border: `1px solid ${confirmClear ? theme.red : theme.border}`,
              color: confirmClear ? '#fff' : theme.red,
            }}>
            {clearing ? <RefreshCw size={14} /> : <Trash2 size={14} />}
            {confirmClear ? 'Confirm Clear?' : `Clear ${filter !== 'all' ? filter : 'All'}`}
          </button>
          {confirmClear && (
            <button onClick={() => setConfirmClear(false)}
              style={{ ...btnBase, background: theme.bg, border: `1px solid ${theme.border}`, color: theme.sub }}>
              <X size={14} />Cancel
            </button>
          )}
        </div>
      </div>

      {/* ── Filter tabs + Search row ── */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {Object.entries(logMeta).map(([id, meta]) => {
            const Icon = meta.icon;
            const isActive = filter === id;
            const label = id === 'all' ? 'All Logs' : id.charAt(0).toUpperCase() + id.slice(1);
            return (
              <button key={id} onClick={() => setFilter(id)} style={{
                padding: '8px 14px', borderRadius: 8,
                background: isActive ? meta.color + '18' : theme.card,
                border: `1.5px solid ${isActive ? meta.color : theme.border}`,
                color: isActive ? meta.color : theme.txt,
                fontSize: 13, fontWeight: 600, cursor: 'pointer',
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <Icon size={14} />{label}
              </button>
            );
          })}
        </div>
        {/* Search box */}
        <div style={{ position: 'relative', flex: 1, minWidth: 200 }}>
          <Search size={14} color={theme.sub} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
          <input
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search messages, endpoints…"
            style={{
              width: '100%', boxSizing: 'border-box',
              padding: '9px 32px 9px 32px',
              border: `1.5px solid ${theme.border}`, borderRadius: 8,
              fontSize: 13, background: theme.card, color: theme.txt, outline: 'none',
            }}
          />
          {search && (
            <button onClick={() => setSearch('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: theme.sub, display: 'flex', alignItems: 'center' }}>
              <X size={13} />
            </button>
          )}
        </div>
      </div>

      {/* ── Log list ── */}
      {loading ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
          {[...Array(6)].map((_, i) => (
            <div key={i} style={{ height: 72, background: theme.border + '60', borderRadius: 8, opacity: 0.6, animation: 'pulse 1.2s infinite' }} />
          ))}
          <style>{`@keyframes pulse{0%,100%{opacity:.6}50%{opacity:.3}}`}</style>
        </div>
      ) : logs.length === 0 ? (
        <div style={{ background: theme.card, borderRadius: 12, padding: 60, textAlign: 'center', border: `1px solid ${theme.border}` }}>
          <FileText size={44} color={theme.sub} style={{ marginBottom: 12, opacity: 0.4 }} />
          <h3 style={{ margin: 0, fontSize: 17, fontWeight: 600, color: theme.txt, marginBottom: 6 }}>No logs found</h3>
          <p style={{ margin: 0, fontSize: 13, color: theme.sub }}>
            {search ? `No logs matching "${search}"` : 'No logs for this filter yet. Activity will appear here automatically.'}
          </p>
        </div>
      ) : (
        <>
          <div style={{ background: theme.card, borderRadius: 12, border: `1px solid ${theme.border}`, overflow: 'hidden' }}>
            {logs.map((log, i) => {
              const Icon  = getIcon(log.log_type);
              const color = getColor(log.log_type);
              return (
                <div key={log.id} style={{
                  padding: '14px 18px',
                  borderBottom: i < logs.length - 1 ? `1px solid ${theme.border}` : 'none',
                  display: 'flex', gap: 14, alignItems: 'flex-start',
                }}>
                  <div style={{ width: 36, height: 36, borderRadius: 8, background: color + '18',
                    display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                    <Icon size={18} color={color} />
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 4, flexWrap: 'wrap' }}>
                      <span style={{ padding: '2px 7px', borderRadius: 4, fontSize: 10, fontWeight: 800,
                        textTransform: 'uppercase', background: color + '22', color }}>
                        {log.log_type}
                      </span>
                      <span style={{ fontSize: 12, color: theme.sub }}>
                        {new Date(log.created_at).toLocaleString()}
                      </span>
                      {log.user && <span style={{ fontSize: 12, color: theme.sub }}>· {log.user}</span>}
                      {log.ip_address && <span style={{ fontSize: 11, color: theme.sub, fontFamily: 'monospace' }}>{log.ip_address}</span>}
                    </div>
                    <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: log.endpoint ? 4 : 0 }}>
                      {log.message}
                    </div>
                    {log.endpoint && (
                      <div style={{ fontSize: 12, color: theme.sub, fontFamily: 'monospace' }}>{log.endpoint}</div>
                    )}
                    {log.details && (
                      <details style={{ marginTop: 6 }}>
                        <summary style={{ fontSize: 12, color: theme.pri, cursor: 'pointer', fontWeight: 600 }}>Details</summary>
                        <pre style={{ marginTop: 6, padding: 10, background: theme.bg, borderRadius: 6,
                          fontSize: 11, fontFamily: 'monospace', overflow: 'auto', maxHeight: 160, color: theme.txt }}>
                          {JSON.stringify(log.details, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div style={{ marginTop: 20, display: 'flex', justifyContent: 'center', alignItems: 'center', gap: 8 }}>
              <button onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}
                style={{ ...btnBase, background: page === 1 ? theme.bg : theme.pri, color: page === 1 ? theme.sub : '#fff',
                  border: `1px solid ${theme.border}`, opacity: page === 1 ? 0.4 : 1 }}>
                <ChevronLeft size={14} />Prev
              </button>
              <span style={{ fontSize: 13, fontWeight: 600, color: theme.txt }}>
                Page {page} / {totalPages}
              </span>
              <button onClick={() => setPage(p => Math.min(totalPages, p + 1))} disabled={page === totalPages}
                style={{ ...btnBase, background: page === totalPages ? theme.bg : theme.pri, color: page === totalPages ? theme.sub : '#fff',
                  border: `1px solid ${theme.border}`, opacity: page === totalPages ? 0.4 : 1 }}>
                Next<ChevronRight size={14} />
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}




