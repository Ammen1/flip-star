import { useState, useEffect, useCallback } from 'react';
import {
  Shield, AlertCircle, AlertTriangle, Info, Lock, Ban,
  Users, TrendingUp, RefreshCw, Eye, LogIn, LogOut, ExternalLink,
  UserX, Key, Activity, ChevronRight, Search, X, Database, Server,
  HardDrive, CheckCircle, XCircle, Clock, MapPin, ShieldAlert,
} from 'lucide-react';
import api from '../../api';

function StatCard({ icon: Icon, label, value, sub, color, theme }) {
  return (
    <div style={{
      background: theme.card, borderRadius: 12,
      padding: '18px 20px', border: `1px solid ${theme.border}`,
      display: 'flex', alignItems: 'center', gap: 14,
    }}>
      <div style={{
        width: 44, height: 44, borderRadius: 10,
        background: color + '18', display: 'flex',
        alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        <Icon size={22} color={color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 22, fontWeight: 800, color: theme.txt }}>{value}</div>
        <div style={{ fontSize: 12, fontWeight: 600, color: theme.sub }}>{label}</div>
        {sub && <div style={{ fontSize: 11, color, marginTop: 1 }}>{sub}</div>}
      </div>
    </div>
  );
}

function DistributionBar({ label, count, total, color, theme }) {
  const pct = total > 0 ? Math.round((count / total) * 100) : 0;
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
        <span style={{ fontSize: 13, fontWeight: 600, color: theme.txt }}>{label}</span>
        <span style={{ fontSize: 13, fontWeight: 700, color }}>{count.toLocaleString()} ({pct}%)</span>
      </div>
      <div style={{ height: 8, background: theme.border, borderRadius: 4, overflow: 'hidden' }}>
        <div style={{ height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width .6s' }} />
      </div>
    </div>
  );
}

const EVENT_ICON = {
  security: { icon: Shield,        color: '#8B5CF6' },
  error:    { icon: AlertCircle,   color: '#EF4444' },
  warning:  { icon: AlertTriangle, color: '#F59E0B' },
  info:     { icon: Info,          color: '#3B82F6' },
  critical: { icon: AlertCircle,   color: '#DC2626' },
};

export function SecurityPage({ theme, onNavigate }) {
  const [overview, setOverview]       = useState(null);
  const [loading, setLoading]         = useState(true);
  const [search, setSearch]           = useState('');
  const [eventFilter, setEventFilter] = useState('all');
  const [selectedIP, setSelectedIP]   = useState(null);
  const [showIPModal, setShowIPModal] = useState(false);
  const [banningIP, setBanningIP]     = useState(null);
  const [healthExpanded, setHealthExpanded] = useState(false);

  const load = useCallback(async () => {
    try {
      setLoading(true);
      const data = await api.request('/admin/security/');
      setOverview(data);
    } catch (err) {
      console.error('Security load error:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const handleBanIP = async (ip) => {
    if (!confirm(`Block IP address ${ip}? This will prevent further login attempts from this address.`)) return;
    try {
      setBanningIP(ip);
      await api.request('/admin/security/ban-ip/', {
        method: 'POST',
        body: JSON.stringify({ ip_address: ip })
      });
      // Log the action
      await api.request('/admin/logs/', { method: 'POST', body: JSON.stringify({
        log_type: 'security',
        message: `IP ${ip} blocked by admin`,
      })});
      alert(`IP ${ip} has been blocked`);
      load();
    } catch (err) {
      alert('Failed to block IP: ' + (err.message || 'Unknown error'));
    } finally {
      setBanningIP(null);
    }
  };

  const navigateTo = (page) => {
    if (onNavigate) onNavigate(page);
  };

  const T = theme;

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ height: 36, width: 240, background: T.border, borderRadius: 8, opacity: 0.6 }} />
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 14 }}>
          {[0,1,2,3].map(i => <div key={i} style={{ height: 90, background: T.border, borderRadius: 12, opacity: 0.5 }} />)}
        </div>
        {[0,1,2,3,4,5].map(i => <div key={i} style={{ height: 62, background: T.border, borderRadius: 8, opacity: 0.4 }} />)}
        <style>{`@keyframes pulse{0%,100%{opacity:.5}50%{opacity:.25}}`}</style>
      </div>
    );
  }

  const stats        = overview?.stats         || {};
  const distribution = overview?.log_distribution || {};
  const events       = overview?.recent_events  || [];
  const totalLogs    = stats.total_logs || 0;

  const filtered = events.filter(e => {
    const msg = e.message?.toLowerCase() || '';
    const matchFilter = eventFilter === 'all' ? true :
                       eventFilter === 'login' ? msg.includes('login') :
                       eventFilter === 'failed' ? msg.includes('failed') :
                       eventFilter === 'cleared' ? msg.includes('clear') :
                       eventFilter === 'created' ? msg.includes('created') :
                       eventFilter === 'deleted' ? msg.includes('deleted') :
                       true;
    const matchSearch = !search || e.message?.toLowerCase().includes(search.toLowerCase())
                     || e.user?.toLowerCase().includes(search.toLowerCase())
                     || e.ip_address?.includes(search);
    return matchFilter && matchSearch;
  });

  const suspiciousIPs = overview?.suspicious_ips || [];
  const health = overview?.health || {};
  const apiKeys = overview?.api_keys || { active: 0, total: 0 };
  const admins = overview?.admins || 0;

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ marginBottom: 24, display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between' }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: T.txt, marginBottom: 4, display: 'flex', alignItems: 'center', gap: 10 }}>
            <Shield size={26} color={T.purple} /> Security
          </h1>
          <p style={{ margin: 0, fontSize: 14, color: T.sub }}>
            Monitor authentication, access control, and security events
          </p>
        </div>
        <button onClick={load} style={{
          display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px',
          borderRadius: 8, border: `1px solid ${T.border}`, background: T.card,
          fontSize: 13, fontWeight: 600, cursor: 'pointer', color: T.txt,
        }}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {/* ── Stat cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 14, marginBottom: 28 }}>
        <StatCard icon={Shield}        label="Security Events (24h)" value={stats.security_24h || 0}  sub={`${stats.security_total || 0} total`}       color={T.purple} theme={T} />
        <StatCard icon={AlertCircle}   label="Errors (24h)"          value={stats.error_24h    || 0}  sub={`${stats.error_total || 0} total`}           color={T.red}    theme={T} />
        <StatCard icon={AlertTriangle} label="Warnings (24h)"        value={stats.warning_24h  || 0}  sub={`${stats.warning_total || 0} total`}         color={T.orange} theme={T} />
        <StatCard icon={Users}         label="Active Users (7d)"     value={stats.active_users_7d || 0} sub={`+${stats.new_users_24h || 0} joined today`} color={T.green}  theme={T} />
        <StatCard icon={Activity}      label="Total Logs"            value={(totalLogs).toLocaleString()} sub="all time"                                color={T.blue}   theme={T} />
        <StatCard icon={ShieldAlert}   label="Suspicious IPs"        value={suspiciousIPs.length} sub={suspiciousIPs.length > 0 ? 'Potential attacks detected' : 'No threats detected'} color={suspiciousIPs.length > 0 ? T.red : T.green} theme={T} />
      </div>

      {/* ── Suspicious IPs Alert ── */}
      {suspiciousIPs.length > 0 && (
        <div style={{ background: T.red + '10', border: `1.5px solid ${T.red}`, borderRadius: 12, padding: 16, marginBottom: 24 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
            <ShieldAlert size={24} color={T.red} />
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 16, fontWeight: 700, color: T.txt }}>Potential Security Threats Detected</div>
              <div style={{ fontSize: 13, color: T.sub }}>{suspiciousIPs.length} IP address(es) with multiple failed login attempts in the last 24 hours</div>
            </div>
            <button onClick={() => setShowIPModal(true)} style={{
              padding: '8px 14px', borderRadius: 8, background: T.red, color: '#fff',
              border: 'none', fontSize: 13, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6,
            }}>
              <Eye size={14} /> View Details
            </button>
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {suspiciousIPs.slice(0, 5).map(ip => (
              <span key={ip.ip} style={{
                padding: '4px 10px', borderRadius: 6, background: T.card,
                border: `1px solid ${T.red}40`, fontSize: 12, color: T.txt,
                display: 'flex', alignItems: 'center', gap: 6,
              }}>
                <MapPin size={12} color={T.red} />
                {ip.ip} ({ip.failed_attempts} attempts)
              </span>
            ))}
            {suspiciousIPs.length > 5 && (
              <span style={{ padding: '4px 10px', fontSize: 12, color: T.sub }}>+{suspiciousIPs.length - 5} more</span>
            )}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 300px', gap: 20 }}>
        {/* ── Recent security events ── */}
        <div>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
            <h2 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: T.txt }}>Recent Security Events</h2>
            <div style={{ display: 'flex', gap: 8 }}>
              {['all','login','failed','cleared','created','deleted'].map(f => (
                <button key={f} onClick={() => setEventFilter(f)} style={{
                  padding: '5px 10px', borderRadius: 6, fontSize: 11, fontWeight: 700, cursor: 'pointer',
                  border: `1.5px solid ${eventFilter === f ? T.purple : T.border}`,
                  background: eventFilter === f ? T.purple + '18' : T.card,
                  color: eventFilter === f ? T.purple : T.sub,
                }}>
                  {f === 'all' ? 'All' : f.charAt(0).toUpperCase() + f.slice(1)}
                </button>
              ))}
            </div>
          </div>

          {/* Search */}
          <div style={{ position: 'relative', marginBottom: 14 }}>
            <Search size={13} color={T.sub} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
            <input value={search} onChange={e => setSearch(e.target.value)}
              placeholder="Search events, users, IP addresses…"
              style={{ width: '100%', boxSizing: 'border-box', padding: '9px 32px 9px 30px',
                border: `1.5px solid ${T.border}`, borderRadius: 8, fontSize: 13,
                background: T.card, color: T.txt, outline: 'none' }} />
            {search && (
              <button onClick={() => setSearch('')} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', color: T.sub, display: 'flex' }}>
                <X size={13} />
              </button>
            )}
          </div>

          {filtered.length === 0 ? (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 40, textAlign: 'center' }}>
              <Shield size={36} color={T.sub} style={{ opacity: 0.3, marginBottom: 10 }} />
              <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 6 }}>No security events yet</div>
              <div style={{ fontSize: 13, color: T.sub }}>Events are recorded when users log in, fail authentication, or perform admin actions.</div>
            </div>
          ) : (
            <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, overflow: 'hidden' }}>
              {filtered.map((ev, i) => {
                const meta  = EVENT_ICON[ev.log_type] || EVENT_ICON.info;
                const Icon  = meta.icon;
                const color = meta.color;
                const isLogin   = ev.message?.toLowerCase().includes('successful login');
                const isFailed  = ev.message?.toLowerCase().includes('failed');
                return (
                  <div key={ev.id} style={{
                    padding: '13px 16px',
                    borderBottom: i < filtered.length - 1 ? `1px solid ${T.border}` : 'none',
                    display: 'flex', gap: 12, alignItems: 'flex-start',
                    background: isFailed ? T.red + '06' : isLogin ? T.green + '06' : 'transparent',
                  }}>
                    <div style={{ width: 34, height: 34, borderRadius: 8, background: color + '18',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      {isLogin ? <LogIn size={16} color={T.green} />
                       : isFailed ? <UserX size={16} color={T.red} />
                       : <Icon size={16} color={color} />}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 3 }}>{ev.message}</div>
                      <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
                        {ev.user && (
                          <button onClick={() => navigateTo('users')} style={{
                            fontSize: 11, color: T.pri, background: 'none', border: 'none',
                            cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 4,
                            padding: 0, fontWeight: 600,
                          }}>
                            👤 {ev.user}
                          </button>
                        )}
                        {ev.ip_address && (
                          <span style={{ fontSize: 11, color: T.sub, fontFamily: 'monospace', display: 'flex', alignItems: 'center', gap: 4 }}>
                            🌐 {ev.ip_address}
                          </span>
                        )}
                        <span style={{ fontSize: 11, color: T.sub, display: 'flex', alignItems: 'center', gap: 4 }}>
                          <Clock size={11} /> {new Date(ev.created_at).toLocaleString()}
                        </span>
                      </div>
                      {ev.details && (
                        <details style={{ marginTop: 5 }}>
                          <summary style={{ fontSize: 11, color: T.pri, cursor: 'pointer', fontWeight: 600 }}>Details</summary>
                          <pre style={{ marginTop: 4, padding: 8, background: T.bg, borderRadius: 6, fontSize: 10,
                            fontFamily: 'monospace', maxHeight: 120, overflow: 'auto', color: T.txt }}>
                            {JSON.stringify(ev.details, null, 2)}
                          </pre>
                        </details>
                      )}
                    </div>
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
                      <span style={{
                        padding: '2px 6px', borderRadius: 4, fontSize: 9, fontWeight: 800,
                        textTransform: 'uppercase', background: color + '20', color, flexShrink: 0,
                      }}>
                        {ev.log_type}
                      </span>
                      {ev.user_id && (
                        <button onClick={() => navigateTo('users')} style={{
                          fontSize: 10, color: T.sub, background: 'none', border: 'none',
                          cursor: 'pointer', display: 'flex', alignItems: 'center',
                        }} title="View user">
                          <ExternalLink size={10} />
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* ── Right column: distribution ── */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 18 }}>
            <h3 style={{ margin: '0 0 16px', fontSize: 15, fontWeight: 700, color: T.txt }}>Log Distribution</h3>
            {totalLogs === 0 ? (
              <div style={{ fontSize: 13, color: T.sub, textAlign: 'center', padding: '20px 0' }}>No logs yet</div>
            ) : (
              <>
                <DistributionBar label="Security" count={distribution.security || 0} total={totalLogs} color={T.purple} theme={T} />
                <DistributionBar label="Info"     count={distribution.info     || 0} total={totalLogs} color={T.blue}   theme={T} />
                <DistributionBar label="Warning"  count={distribution.warning  || 0} total={totalLogs} color={T.orange} theme={T} />
                <DistributionBar label="Error"    count={distribution.error    || 0} total={totalLogs} color={T.red}    theme={T} />
                <DistributionBar label="Critical" count={distribution.critical || 0} total={totalLogs} color="#DC2626"  theme={T} />
              </>
            )}
          </div>

          {/* Quick actions - Clickable */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 18 }}>
            <h3 style={{ margin: '0 0 14px', fontSize: 15, fontWeight: 700, color: T.txt }}>Security Checklist</h3>
            {[
              { id: 'api-keys', icon: Key,      label: 'API Keys', detail: `${apiKeys.active}/${apiKeys.total} active keys`, color: T.orange },
              { id: 'admins',   icon: Users,    label: 'Admin Accounts', detail: `${admins} staff member${admins !== 1 ? 's' : ''}`, color: T.blue },
              { id: 'logs',     icon: Lock,     label: 'Failed Logins', detail: `${stats.security_total || 0} security events total`, color: T.red },
              { id: 'logs',     icon: Activity, label: 'System Logs', detail: `${totalLogs.toLocaleString()} entries`, color: T.purple },
            ].map(({ id, icon: Icon, label, detail, color }) => (
              <button key={label} onClick={() => navigateTo(id)} style={{
                display: 'flex', alignItems: 'center', gap: 10, padding: '10px 0',
                borderBottom: `1px solid ${T.border}`, width: '100%', background: 'none',
                borderLeft: 'none', borderRight: 'none', borderTop: 'none', cursor: 'pointer',
                textAlign: 'left',
              }}>
                <div style={{ width: 30, height: 30, borderRadius: 8, background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon size={15} color={color} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.txt }}>{label}</div>
                  <div style={{ fontSize: 11, color: T.sub }}>{detail}</div>
                </div>
                <ChevronRight size={14} color={T.sub} />
              </button>
            ))}
          </div>

          {/* System health - Real checks */}
          <div style={{ background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 18 }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 14 }}>
              <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700, color: T.txt }}>System Health</h3>
              <button onClick={() => setHealthExpanded(!healthExpanded)} style={{
                fontSize: 11, color: T.pri, background: 'none', border: 'none', cursor: 'pointer', fontWeight: 600,
              }}>
                {healthExpanded ? 'Hide' : 'Details'}
              </button>
            </div>
            {[
              { label: 'Database',    key: 'database',    icon: Database,  color: health.database === 'healthy' ? T.green : T.red },
              { label: 'API',         key: 'api',         icon: Server,    color: health.api === 'healthy' ? T.green : health.api === 'slow' ? T.orange : T.red },
              { label: 'Storage',     key: 'storage',     icon: HardDrive, color: health.storage === 'healthy' ? T.green : T.red },
            ].map(({ label, key, icon: Icon, color }) => {
              const status = health[key] || 'unknown';
              const isHealthy = status === 'healthy';
              return (
                <div key={label} style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <Icon size={14} color={color} />
                    <span style={{ fontSize: 13, color: T.txt }}>{label}</span>
                  </div>
                  <span style={{ fontSize: 11, fontWeight: 700, color, background: color + '18', padding: '2px 8px', borderRadius: 20, textTransform: 'uppercase' }}>
                    {status}
                  </span>
                </div>
              );
            })}
            {healthExpanded && (
              <div style={{ marginTop: 12, padding: 12, background: T.bg, borderRadius: 8, fontSize: 12, color: T.sub }}>
                <div style={{ marginBottom: 6 }}><strong>API Response Time:</strong> {health.api_response_ms || '--'} ms</div>
                <div style={{ marginBottom: 6 }}><strong>Media Files:</strong> {health.media_files || '--'}</div>
                <div>Last checked: {new Date().toLocaleTimeString()}</div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Suspicious IPs Modal ── */}
      {showIPModal && (
        <div style={{
          position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(0,0,0,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center',
          zIndex: 1000, padding: 20,
        }} onClick={() => setShowIPModal(false)}>
          <div style={{
            background: T.card, borderRadius: 12, padding: 24, maxWidth: 600, width: '100%', maxHeight: '80vh',
            overflow: 'auto', border: `1px solid ${T.border}`,
          }} onClick={e => e.stopPropagation()}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
              <h2 style={{ margin: 0, fontSize: 20, fontWeight: 700, color: T.txt, display: 'flex', alignItems: 'center', gap: 10 }}>
                <ShieldAlert color={T.red} /> Suspicious IP Addresses
              </h2>
              <button onClick={() => setShowIPModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.sub }}>
                <X size={24} />
              </button>
            </div>
            <p style={{ margin: '0 0 20px', fontSize: 14, color: T.sub }}>
              These IPs have more than 5 failed login attempts in the last 24 hours. Consider blocking them if they are not legitimate users.
            </p>
            {suspiciousIPs.length === 0 ? (
              <div style={{ textAlign: 'center', padding: 40, color: T.sub }}>No suspicious IPs detected</div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                {suspiciousIPs.map(ip => (
                  <div key={ip.ip} style={{
                    padding: 16, background: T.bg, borderRadius: 8, border: `1px solid ${T.border}`,
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                  }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 700, color: T.txt, fontFamily: 'monospace', marginBottom: 4 }}>{ip.ip}</div>
                      <div style={{ fontSize: 12, color: T.sub }}>
                        {ip.failed_attempts} failed attempts · Last: {new Date(ip.last_attempt).toLocaleString()}
                      </div>
                      {ip.targeted_users.length > 0 && (
                        <div style={{ fontSize: 12, color: T.sub, marginTop: 4 }}>
                          Targeted users: {ip.targeted_users.join(', ')}
                        </div>
                      )}
                    </div>
                    <button
                      onClick={() => handleBanIP(ip.ip)}
                      disabled={banningIP === ip.ip}
                      style={{
                        padding: '8px 14px', borderRadius: 6, background: T.red, color: '#fff',
                        border: 'none', fontSize: 12, fontWeight: 600, cursor: 'pointer',
                        display: 'flex', alignItems: 'center', gap: 6, opacity: banningIP === ip.ip ? 0.6 : 1,
                      }}
                    >
                      <Ban size={14} />
                      {banningIP === ip.ip ? 'Blocking...' : 'Block IP'}
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}




