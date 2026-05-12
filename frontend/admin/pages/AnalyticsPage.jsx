import { useState, useEffect, useRef } from 'react';
import { TrendingUp, Users, Video, Download, RefreshCw, Activity, FileText, Printer, Film, ImageIcon } from 'lucide-react';
import api from '../../api';

// ─── SVG Chart: Line / Area ───────────────────────────────────────────────────
function SvgLineChart({ data, color, height = 140, theme }) {
  if (!data || data.length < 2) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.sub, fontSize: 13 }}>No data for this range</div>;
  }
  const W = 560, H = height;
  const pad = { t: 16, r: 16, b: 30, l: 38 };
  const vals = data.map(d => d.value);
  const min = Math.min(...vals);
  const max = Math.max(...vals) || 1;
  const xi = (i) => pad.l + (i / (data.length - 1)) * (W - pad.l - pad.r);
  const yi = (v) => pad.t + (1 - (v - min) / (max - min || 1)) * (H - pad.t - pad.b);
  const pts = data.map((d, i) => `${xi(i)},${yi(d.value)}`).join(' ');
  const area = `${xi(0)},${H - pad.b} ${pts} ${xi(data.length - 1)},${H - pad.b}`;
  const yTicks = [min, Math.round((min + max) / 2), max];
  const step = Math.max(1, Math.ceil(data.length / 6));
  const gradId = `lg-${color.replace(/[^a-z0-9]/gi, '')}`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height }}>
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.25" />
          <stop offset="100%" stopColor={color} stopOpacity="0.01" />
        </linearGradient>
      </defs>
      {yTicks.map((v, i) => (
        <g key={i}>
          <line x1={pad.l} x2={W - pad.r} y1={yi(v)} y2={yi(v)} stroke={theme.border} strokeWidth="1" strokeDasharray="3 3" />
          <text x={pad.l - 5} y={yi(v) + 4} fontSize="9.5" fill={theme.sub} textAnchor="end">{v}</text>
        </g>
      ))}
      <polygon points={area} fill={`url(#${gradId})`} />
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
      {data.map((d, i) => (
        <circle key={i} cx={xi(i)} cy={yi(d.value)} r="3.5" fill={color} stroke="#fff" strokeWidth="1.5" />
      ))}
      {data.map((d, i) => i % step === 0 && (
        <text key={i} x={xi(i)} y={H - 4} fontSize="9.5" fill={theme.sub} textAnchor="middle">{d.label}</text>
      ))}
    </svg>
  );
}

// ─── SVG Chart: Bar ───────────────────────────────────────────────────────────
function SvgBarChart({ data, color, height = 140, theme }) {
  if (!data || data.length === 0) {
    return <div style={{ height, display: 'flex', alignItems: 'center', justifyContent: 'center', color: theme.sub, fontSize: 13 }}>No data for this range</div>;
  }
  const W = 560, H = height;
  const pad = { t: 16, r: 16, b: 30, l: 38 };
  const max = Math.max(...data.map(d => d.value)) || 1;
  const slot = (W - pad.l - pad.r) / data.length;
  const bw = slot * 0.65;
  const bx = (i) => pad.l + i * slot + (slot - bw) / 2;
  const bh = (v) => ((v / max) * (H - pad.t - pad.b));
  const by = (v) => H - pad.b - bh(v);
  const step = Math.max(1, Math.ceil(data.length / 7));
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', height }}>
      {[0, 0.25, 0.5, 0.75, 1].map((f, i) => {
        const v = Math.round(max * f);
        const yp = H - pad.b - f * (H - pad.t - pad.b);
        return (
          <g key={i}>
            <line x1={pad.l} x2={W - pad.r} y1={yp} y2={yp} stroke={theme.border} strokeWidth="1" strokeDasharray="3 3" />
            <text x={pad.l - 5} y={yp + 4} fontSize="9.5" fill={theme.sub} textAnchor="end">{v}</text>
          </g>
        );
      })}
      {data.map((d, i) => (
        <g key={i}>
          <rect x={bx(i)} y={by(d.value)} width={bw} height={Math.max(bh(d.value), 2)} fill={color} rx="3" opacity="0.85" />
          {bh(d.value) > 18 && (
            <text x={bx(i) + bw / 2} y={by(d.value) - 4} fontSize="9" fill={color} textAnchor="middle" fontWeight="700">{d.value}</text>
          )}
          {i % step === 0 && (
            <text x={bx(i) + bw / 2} y={H - 4} fontSize="9.5" fill={theme.sub} textAnchor="middle">{d.label}</text>
          )}
        </g>
      ))}
    </svg>
  );
}

// ─── SVG Chart: Donut ─────────────────────────────────────────────────────────
function DonutChart({ segments, size = 160, theme }) {
  const total = (segments || []).reduce((s, g) => s + g.value, 0) || 1;
  let angle = -Math.PI / 2;
  const arcs = (segments || []).map(seg => {
    const start = angle;
    const sweep = (seg.value / total) * Math.PI * 2;
    angle += sweep;
    return { ...seg, start, end: angle };
  });
  const cx = size / 2, cy = size / 2, R = size * 0.38, r = size * 0.22;
  const arc = (s, e, R1, R2) => {
    const x1 = cx + R1 * Math.cos(s), y1 = cy + R1 * Math.sin(s);
    const x2 = cx + R1 * Math.cos(e), y2 = cy + R1 * Math.sin(e);
    const ix1 = cx + R2 * Math.cos(e), iy1 = cy + R2 * Math.sin(e);
    const ix2 = cx + R2 * Math.cos(s), iy2 = cy + R2 * Math.sin(s);
    const lg = (e - s) > Math.PI ? 1 : 0;
    return `M${x1} ${y1} A${R1} ${R1} 0 ${lg} 1 ${x2} ${y2} L${ix1} ${iy1} A${R2} ${R2} 0 ${lg} 0 ${ix2} ${iy2}Z`;
  };
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 24, flexWrap: 'wrap' }}>
      <svg width={size} height={size} style={{ flexShrink: 0 }}>
        {arcs.map((seg, i) => <path key={i} d={arc(seg.start, seg.end, R, r)} fill={seg.color} opacity="0.9" />)}
        <text x={cx} y={cy - 7} fontSize="20" fontWeight="800" fill={theme.txt} textAnchor="middle">{total.toLocaleString()}</text>
        <text x={cx} y={cy + 14} fontSize="10" fill={theme.sub} textAnchor="middle">Total</text>
      </svg>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
        {(segments || []).map((seg, i) => (
          <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ width: 11, height: 11, borderRadius: 3, background: seg.color, flexShrink: 0 }} />
            <span style={{ fontSize: 13, color: theme.txt }}>{seg.label}</span>
            <span style={{ fontSize: 13, fontWeight: 700, color: seg.color, marginLeft: 4 }}>{seg.value.toLocaleString()}</span>
            <span style={{ fontSize: 11, color: theme.sub }}>({Math.round(seg.value / total * 100)}%)</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ─── Sparkline ────────────────────────────────────────────────────────────────
function Spark({ data, color }) {
  if (!data || data.length < 2) return null;
  const W = 72, H = 28;
  const min = Math.min(...data), max = Math.max(...data) || 1;
  const x = (i) => (i / (data.length - 1)) * W;
  const y = (v) => H - ((v - min) / (max - min + 0.001)) * H;
  const pts = data.map((v, i) => `${x(i)},${y(v)}`).join(' ');
  return (
    <svg width={W} height={H}>
      <polyline points={pts} fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

// ─── Date helpers ─────────────────────────────────────────────────────────────
const daysAgo = (n) => { const d = new Date(); d.setDate(d.getDate() - n); return d; };
const fmtDay = (d) => new Date(d).toLocaleDateString('en', { month: 'short', day: 'numeric' });
const fmtWeek = (d) => new Date(d).toLocaleDateString('en', { month: 'short', day: 'numeric' });

function groupByDay(items, field, days) {
  const map = {};
  for (let i = days - 1; i >= 0; i--) {
    const k = daysAgo(i).toISOString().split('T')[0];
    map[k] = 0;
  }
  const since = daysAgo(days);
  items.forEach(it => {
    const d = new Date(it[field]);
    if (d >= since) {
      const k = d.toISOString().split('T')[0];
      if (k in map) map[k]++;
    }
  });
  return Object.entries(map).map(([date, value]) => ({ label: fmtDay(date), date, value }));
}

function groupByWeek(items, field, weeks) {
  return Array.from({ length: weeks }, (_, idx) => {
    const start = daysAgo((weeks - idx) * 7);
    const end = daysAgo((weeks - idx - 1) * 7);
    const value = items.filter(it => { const d = new Date(it[field]); return d >= start && d < end; }).length;
    return { label: fmtWeek(end), date: end.toISOString(), value };
  });
}

// ─── Main Component ───────────────────────────────────────────────────────────
export function AnalyticsPage({ theme }) {
  const [range, setRange] = useState('30');
  const [dashStats, setDashStats] = useState(null);
  const [userData, setUserData] = useState([]);
  const [reelsData, setReelsData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [exportingKey, setExportingKey] = useState('');

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    setLoading(true);
    try {
      const [d, u, r] = await Promise.allSettled([
        api.request('/admin/dashboard/'),
        api.request('/admin/analytics/export/?type=users'),
        api.request('/admin/analytics/export/?type=reels'),
      ]);
      if (d.status === 'fulfilled') setDashStats(d.value);
      if (u.status === 'fulfilled') setUserData(Array.isArray(u.value) ? u.value : []);
      if (r.status === 'fulfilled') setReelsData(Array.isArray(r.value) ? r.value : []);
    } catch (e) {
      console.error('Analytics load error:', e);
    } finally {
      setLoading(false);
    }
  };

  const rangeInt = parseInt(range);

  // ── Derived chart data ──────────────────────────────────────────────────────
  const userGrowth = userData.length
    ? (rangeInt <= 30 ? groupByDay(userData, 'date_joined', rangeInt) : groupByWeek(userData, 'date_joined', Math.ceil(rangeInt / 7)))
    : [];

  const postActivity = reelsData.length
    ? (rangeInt <= 30 ? groupByDay(reelsData, 'created_at', rangeInt) : groupByWeek(reelsData, 'created_at', Math.ceil(rangeInt / 7)))
    : [];

  const cumulative = userGrowth.reduce((acc, d, i) => {
    acc.push({ label: d.label, value: (acc[i - 1]?.value || 0) + d.value });
    return acc;
  }, []);

  const since = daysAgo(rangeInt);
  const usersInRange = userData.filter(u => new Date(u.date_joined) >= since).length;
  const reelsInRange = reelsData.filter(r => new Date(r.created_at) >= since).length;

  const contentTypes = (() => {
    const videos = reelsData.filter(r => r.media && (r.media.includes('/video/') || /\.(mp4|webm|mov|avi)/i.test(r.media))).length;
    return [
      { label: 'Videos', value: videos, color: theme.purple },
      { label: 'Images', value: Math.max(0, reelsData.length - videos), color: theme.blue },
    ];
  })();

  const sparkUser = userGrowth.slice(-7).map(d => d.value);
  const sparkPost = postActivity.slice(-7).map(d => d.value);

  // ── Top creators ────────────────────────────────────────────────────────────
  const topCreators = (() => {
    const map = {};
    reelsData.forEach(r => {
      const u = r.user;
      const key = typeof u === 'object' ? (u?.username || String(u?.id || 'unknown')) : String(u || 'unknown');
      if (!map[key]) map[key] = { username: key, posts: 0 };
      map[key].posts++;
    });
    return Object.values(map).sort((a, b) => b.posts - a.posts).slice(0, 6);
  })();
  const maxPosts = Math.max(...topCreators.map(c => c.posts), 1);

  // ── Download helpers ────────────────────────────────────────────────────────
  const toCSV = (rows) => {
    if (!rows?.length) return 'No data';
    const keys = Object.keys(rows[0]);
    return [keys.join(','), ...rows.map(r => keys.map(k => JSON.stringify(r[k] ?? '')).join(','))].join('\n');
  };

  const saveFile = (content, name, mime = 'text/csv') => {
    const blob = new Blob([content], { type: mime });
    const url = URL.createObjectURL(blob);
    Object.assign(document.createElement('a'), { href: url, download: name }).click();
    URL.revokeObjectURL(url);
  };

  const handleDownload = async (type, fmt) => {
    const key = `${type}-${fmt}`;
    setExportingKey(key);
    try {
      const today = new Date().toISOString().split('T')[0];
      if (type === 'users') {
        fmt === 'csv'
          ? saveFile(toCSV(userData), `users_${today}.csv`)
          : saveFile(JSON.stringify(userData, null, 2), `users_${today}.json`, 'application/json');
      } else if (type === 'reels') {
        fmt === 'csv'
          ? saveFile(toCSV(reelsData), `posts_${today}.csv`)
          : saveFile(JSON.stringify(reelsData, null, 2), `posts_${today}.json`, 'application/json');
      } else {
        const summary = {
          exported_at: new Date().toISOString(),
          range: `Last ${range} days`,
          kpis: {
            total_users: dashStats?.users?.total,
            new_users_in_range: usersInRange,
            total_posts: dashStats?.content?.total_reels,
            new_posts_in_range: reelsInRange,
            total_votes: dashStats?.engagement?.total_votes,
            total_comments: dashStats?.content?.total_comments,
          },
          user_growth: userGrowth,
          post_activity: postActivity,
          content_types: contentTypes,
          top_creators: topCreators,
        };
        fmt === 'csv'
          ? saveFile(toCSV([summary.kpis]), `summary_${today}.csv`)
          : saveFile(JSON.stringify(summary, null, 2), `summary_${today}.json`, 'application/json');
      }
    } catch (e) {
      console.error('Export error', e);
    } finally {
      setExportingKey('');
    }
  };

  if (loading) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: 400, gap: 16 }}>
        <div style={{ width: 40, height: 40, border: `3px solid ${theme.border}`, borderTopColor: theme.pri, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <span style={{ color: theme.sub, fontSize: 14 }}>Loading analytics…</span>
        <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
      </div>
    );
  }

  const Card = ({ children, style = {} }) => (
    <div style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 14, padding: 24, ...style }}>
      {children}
    </div>
  );

  const rangeLabels = [['7', '7D'], ['30', '30D'], ['90', '90D'], ['365', '1Y']];
  const kpis = [
    { title: 'Total Users', main: dashStats?.users?.total || 0, sub: `+${usersInRange} in range`, color: theme.blue, Icon: Users, spark: sparkUser },
    { title: 'Total Posts', main: dashStats?.content?.total_reels || 0, sub: `+${reelsInRange} in range`, color: theme.purple, Icon: Video, spark: sparkPost },
    { title: 'Total Votes', main: dashStats?.engagement?.total_votes || 0, sub: `+${dashStats?.engagement?.votes_today || 0} today`, color: theme.green, Icon: TrendingUp, spark: null },
    { title: 'Comments', main: dashStats?.content?.total_comments || 0, sub: `+${dashStats?.content?.comments_today || 0} today`, color: theme.orange, Icon: Activity, spark: null },
  ];

  return (
    <div>
      {/* ── Header ── */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: theme.txt, marginBottom: 4 }}>Analytics & Reports</h1>
          <p style={{ margin: 0, fontSize: 13, color: theme.sub }}>
            Real-time platform insights · Updated {new Date().toLocaleTimeString()}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <div style={{ display: 'flex', background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 10, overflow: 'hidden' }}>
            {rangeLabels.map(([val, lbl]) => (
              <button key={val} onClick={() => setRange(val)}
                style={{ padding: '8px 14px', background: range === val ? theme.pri : 'transparent', border: 'none', cursor: 'pointer', fontSize: 13, fontWeight: 600, color: range === val ? '#fff' : theme.sub, transition: 'all 0.15s' }}>
                {lbl}
              </button>
            ))}
          </div>
          <button onClick={loadAll}
            style={{ padding: '8px 14px', background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: theme.txt }}>
            <RefreshCw size={14} /> Refresh
          </button>
          <button onClick={() => window.print()}
            style={{ padding: '8px 14px', background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 10, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 6, fontSize: 13, color: theme.txt }}>
            <Printer size={14} /> Print
          </button>
        </div>
      </div>

      {/* ── KPI Cards ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16, marginBottom: 24 }}>
        {kpis.map(({ title, main, sub, color, Icon, spark }, i) => (
          <div key={i} style={{ background: theme.card, border: `1px solid ${theme.border}`, borderRadius: 14, padding: '18px 20px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
              <div style={{ width: 40, height: 40, borderRadius: 10, background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Icon size={20} color={color} />
              </div>
              {spark && <Spark data={spark} color={color} />}
            </div>
            <div style={{ fontSize: 30, fontWeight: 800, color: theme.txt, lineHeight: 1 }}>{(main || 0).toLocaleString()}</div>
            <div style={{ fontSize: 12, color: theme.sub, marginTop: 4 }}>{title}</div>
            <div style={{ fontSize: 12, color, fontWeight: 600, marginTop: 2 }}>{sub}</div>
          </div>
        ))}
      </div>

      {/* ── Row 1: Line + Bar ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(340px, 1fr))', gap: 20, marginBottom: 20 }}>
        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt }}>User Registrations</div>
              <div style={{ fontSize: 12, color: theme.sub }}>New signups per {rangeInt <= 30 ? 'day' : 'week'}</div>
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, color: theme.blue }}>{usersInRange.toLocaleString()}</div>
          </div>
          <SvgLineChart data={userGrowth} color={theme.blue} height={140} theme={theme} />
        </Card>

        <Card>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 14 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt }}>Post Activity</div>
              <div style={{ fontSize: 12, color: theme.sub }}>Uploads per {rangeInt <= 30 ? 'day' : 'week'}</div>
            </div>
            <div style={{ fontSize: 24, fontWeight: 800, color: theme.purple }}>{reelsInRange.toLocaleString()}</div>
          </div>
          <SvgBarChart data={postActivity} color={theme.purple} height={140} theme={theme} />
        </Card>
      </div>

      {/* ── Row 2: Cumulative + Donut ── */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 20, marginBottom: 20 }}>
        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt, marginBottom: 4 }}>Cumulative Growth</div>
          <div style={{ fontSize: 12, color: theme.sub, marginBottom: 14 }}>Running total of all new users</div>
          <SvgLineChart data={cumulative} color={theme.green} height={140} theme={theme} />
        </Card>

        <Card>
          <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt, marginBottom: 4 }}>Content Breakdown</div>
          <div style={{ fontSize: 12, color: theme.sub, marginBottom: 20 }}>Videos vs images across all posts</div>
          <DonutChart segments={contentTypes} size={150} theme={theme} />
        </Card>
      </div>

      {/* ── Top Creators ── */}
      {topCreators.length > 0 && (
        <Card style={{ marginBottom: 20 }}>
          <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt, marginBottom: 16 }}>Top Creators by Posts</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 11 }}>
            {topCreators.map((c, i) => {
              const palettes = [theme.blue, theme.purple, theme.green, theme.orange, theme.red, theme.pri];
              const col = palettes[i % palettes.length];
              return (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{ width: 26, height: 26, borderRadius: '50%', background: col, display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700, color: '#fff', flexShrink: 0 }}>
                    {i + 1}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5 }}>
                      <span style={{ fontSize: 13, fontWeight: 600, color: theme.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>@{c.username}</span>
                      <span style={{ fontSize: 12, color: theme.sub, marginLeft: 8, whiteSpace: 'nowrap' }}>{c.posts} posts</span>
                    </div>
                    <div style={{ height: 6, background: theme.border, borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', width: `${(c.posts / maxPosts) * 100}%`, background: col, borderRadius: 3 }} />
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      )}

      {/* ── Export / Downloads ── */}
      <Card>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <Download size={18} color={theme.pri} />
          <div style={{ fontSize: 16, fontWeight: 700, color: theme.txt }}>Export Reports</div>
        </div>
        <div style={{ fontSize: 13, color: theme.sub, marginBottom: 20 }}>Download platform data in CSV or JSON format</div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(230px, 1fr))', gap: 14 }}>
          {[
            { type: 'users', label: 'User Data', desc: 'All registered users with dates & stats', Icon: Users, color: theme.blue },
            { type: 'reels', label: 'Content Data', desc: 'All posts with engagement metrics', Icon: Video, color: theme.purple },
            { type: 'summary', label: 'Summary Report', desc: 'Platform KPIs + full chart data', Icon: FileText, color: theme.green },
          ].map(({ type, label, desc, Icon, color }) => (
            <div key={type} style={{ padding: 16, background: theme.bg, borderRadius: 10, border: `1px solid ${theme.border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ width: 36, height: 36, borderRadius: 8, background: color + '18', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon size={18} color={color} />
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: theme.txt }}>{label}</div>
                  <div style={{ fontSize: 11, color: theme.sub }}>{desc}</div>
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => handleDownload(type, 'csv')} disabled={!!exportingKey}
                  style={{ flex: 1, padding: '8px 10px', background: color, border: 'none', borderRadius: 7, color: '#fff', fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, opacity: exportingKey === `${type}-csv` ? 0.6 : 1 }}>
                  <FileText size={12} /> CSV
                </button>
                <button onClick={() => handleDownload(type, 'json')} disabled={!!exportingKey}
                  style={{ flex: 1, padding: '8px 10px', background: 'transparent', border: `1.5px solid ${color}`, borderRadius: 7, color: color, fontSize: 12, fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 5, opacity: exportingKey === `${type}-json` ? 0.6 : 1 }}>
                  {'{ }'} JSON
                </button>
              </div>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}




