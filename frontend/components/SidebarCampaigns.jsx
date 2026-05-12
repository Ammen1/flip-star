import { useState, useEffect, useRef } from 'react';
import { Trophy, Clock, Zap, ChevronRight, Award, Calendar } from 'lucide-react';
import api from '../api';
import { useTheme } from '../contexts/ThemeContext';
import config from '../config';

// ── 5-minute stale-while-revalidate cache ────────────────────────────────────
const SC_TTL = 5 * 60 * 1000;
const scRead = (k) => {
  try {
    const r = sessionStorage.getItem(k);
    if (!r) return null;
    const { ts, data } = JSON.parse(r);
    if (Date.now() - ts > SC_TTL) { sessionStorage.removeItem(k); return null; }
    return data;
  } catch { return null; }
};
const scWrite = (k, data) => {
  try { sessionStorage.setItem(k, JSON.stringify({ ts: Date.now(), data })); } catch {}
};

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

const timeLeft = (end) => {
  const diff = new Date(end) - Date.now();
  if (diff <= 0) return 'Ended';
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  const m = Math.floor((diff % 3600000) / 60000);
  if (d > 0) return `${d}d ${h}h left`;
  if (h > 0) return `${h}h ${m}m left`;
  return `${m}m left`;
};

const formatStart = (dt) =>
  new Date(dt).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

// ── Skeleton shimmer ─────────────────────────────────────────────────────────
function Shimmer({ h = 72, radius = 12 }) {
  return (
    <div style={{
      height: h, borderRadius: radius,
      background: 'linear-gradient(90deg,#f0f0f0 25%,#e0e0e0 50%,#f0f0f0 75%)',
      backgroundSize: '400% 100%',
      animation: 'sc-shimmer 1.4s ease infinite',
    }} />
  );
}

// ── Active campaign card ─────────────────────────────────────────────────────
function ActiveCard({ c, T, onJoin }) {
  return (
    <div style={{
      borderRadius: 14,
      overflow: 'hidden',
      border: `1.5px solid ${T.pri}40`,
      background: `linear-gradient(135deg,${T.pri}10 0%,${T.bg} 100%)`,
      position: 'relative',
    }}>
      {/* Banner */}
      {c.banner_image && (
        <div style={{ height: 72, overflow: 'hidden', position: 'relative' }}>
          <img src={mediaUrl(c.banner_image)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom,transparent 40%,rgba(0,0,0,0.55))' }} />
        </div>
      )}
      <div style={{ padding: '10px 12px 12px' }}>
        {/* LIVE badge + prize */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 4, background: '#10B981', borderRadius: 20, padding: '2px 8px', fontSize: 10, fontWeight: 800, color: '#fff' }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#fff', display: 'inline-block', animation: 'sc-pulse 1.2s ease infinite' }} />
              LIVE
            </span>
            {c.campaign_type && (
              <span style={{ fontSize: 10, fontWeight: 700, color: T.sub, textTransform: 'uppercase' }}>{c.campaign_type}</span>
            )}
          </div>
          {c.prize_amount && (
            <span style={{ fontSize: 13, fontWeight: 800, color: T.pri }}>
              ${Number(c.prize_amount).toLocaleString()}
            </span>
          )}
        </div>
        {/* Title */}
        <div style={{ fontSize: 13, fontWeight: 700, color: T.txt, marginBottom: 4, lineHeight: 1.3,
          overflow: 'hidden', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' }}>
          {c.title}
        </div>
        {/* Countdown + entries */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: T.sub }}>
            <Clock size={11} />
            {c.end_date ? timeLeft(c.end_date) : 'Ongoing'}
          </div>
          {c.participant_count != null && (
            <div style={{ fontSize: 11, color: T.sub }}>{c.participant_count.toLocaleString()} entries</div>
          )}
        </div>
        {/* Join button */}
        <button onClick={() => onJoin?.(c)} style={{
          width: '100%', padding: '7px', borderRadius: 8, border: 'none',
          background: T.pri, color: '#fff', fontSize: 12, fontWeight: 800,
          cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 4,
        }}>
          <Zap size={12} />
          Join Now
          <ChevronRight size={12} />
        </button>
      </div>
    </div>
  );
}

// ── Upcoming campaign card ────────────────────────────────────────────────────
function UpcomingCard({ c, T, onJoin }) {
  return (
    <div style={{
      borderRadius: 12, padding: '10px 12px',
      border: `1px solid ${T.border}`,
      background: T.cardBg || T.bg,
      display: 'flex', alignItems: 'center', gap: 10,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: 8, flexShrink: 0,
        background: `${T.pri}20`, display: 'flex', alignItems: 'center', justifyContent: 'center',
        overflow: 'hidden',
      }}>
        {c.banner_image
          ? <img src={mediaUrl(c.banner_image)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <Calendar size={16} color={T.pri} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{c.title}</div>
        <div style={{ fontSize: 11, color: T.sub, marginTop: 2, display: 'flex', alignItems: 'center', gap: 4 }}>
          <Clock size={10} />
          Starts {c.start_date ? formatStart(c.start_date) : 'Soon'}
        </div>
      </div>
      <span style={{
        background: `${T.pri}18`, color: T.pri, borderRadius: 20,
        fontSize: 10, fontWeight: 800, padding: '3px 8px', flexShrink: 0,
      }}>SOON</span>
    </div>
  );
}

// ── Winner row ────────────────────────────────────────────────────────────────
const MEDALS = ['🥇', '🥈', '🥉'];
function WinnerRow({ w, rank, T }) {
  const photo = w.user?.profile_photo ? mediaUrl(w.user.profile_photo) : null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '7px 0' }}>
      <span style={{ fontSize: 18, width: 24, textAlign: 'center', flexShrink: 0 }}>{MEDALS[rank] || '🏅'}</span>
      <div style={{
        width: 32, height: 32, borderRadius: '50%', flexShrink: 0, overflow: 'hidden',
        background: T.pri + '30', display: 'flex', alignItems: 'center', justifyContent: 'center',
        border: `2px solid ${rank === 0 ? '#FFD700' : rank === 1 ? '#C0C0C0' : rank === 2 ? '#CD7F32' : T.border}`,
      }}>
        {photo ? <img src={photo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : <span style={{ fontSize: 14 }}>👤</span>}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: T.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          @{w.user?.username || 'Anonymous'}
        </div>
        <div style={{ fontSize: 11, color: T.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {w.campaign?.title || 'Campaign'}
        </div>
      </div>
      {w.prize_amount && (
        <span style={{ fontSize: 12, fontWeight: 800, color: T.pri, flexShrink: 0 }}>${Number(w.prize_amount).toLocaleString()}</span>
      )}
    </div>
  );
}

// ── Section header ────────────────────────────────────────────────────────────
function SectionHeader({ icon: Icon, label, color, T }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 7, marginBottom: 10 }}>
      <Icon size={15} color={color || T.pri} />
      <span style={{ fontSize: 13, fontWeight: 800, color: T.txt }}>{label}</span>
    </div>
  );
}

// ── Main exported component ───────────────────────────────────────────────────
export function SidebarCampaigns({ onCampaignClick }) {
  const { colors: T } = useTheme();

  const [active, setActive]     = useState(() => scRead('sc_active') || []);
  const [upcoming, setUpcoming] = useState(() => scRead('sc_upcoming') || []);
  const [winners, setWinners]   = useState(() => scRead('sc_winners') || []);
  const [loading, setLoading]   = useState(!scRead('sc_active'));
  const fetchedRef = useRef(false);

  useEffect(() => {
    if (fetchedRef.current) return;
    fetchedRef.current = true;

    const alreadyCached = scRead('sc_active') && scRead('sc_upcoming') && scRead('sc_winners');

    const doFetch = async () => {
      try {
        const [a, u, w] = await Promise.all([
          api.request('/campaigns/?status=active&limit=3'),
          api.request('/campaigns/?status=upcoming&limit=3'),
          api.request('/winners/latest/?limit=4').catch(() => []),
        ]);
        const aList = Array.isArray(a) ? a.slice(0, 3) : (a?.results || []).slice(0, 3);
        const uList = Array.isArray(u) ? u.slice(0, 3) : (u?.results || []).slice(0, 3);
        const wList = Array.isArray(w) ? w.slice(0, 4) : (w?.results || []).slice(0, 4);
        setActive(aList);   scWrite('sc_active', aList);
        setUpcoming(uList); scWrite('sc_upcoming', uList);
        setWinners(wList);  scWrite('sc_winners', wList);
      } catch (e) {
        console.warn('SidebarCampaigns fetch error', e);
      } finally {
        setLoading(false);
      }
    };

    if (alreadyCached) {
      setLoading(false);
      // refresh in background
      doFetch();
    } else {
      doFetch();
    }
  }, []);

  const hasActive   = active.length > 0;
  const hasUpcoming = upcoming.length > 0;
  const hasWinners  = winners.length > 0;
  const hasAnything = hasActive || hasUpcoming || hasWinners;

  return (
    <>
      <style>{`
        @keyframes sc-shimmer{0%{background-position:200% 0}100%{background-position:-200% 0}}
        @keyframes sc-pulse{0%,100%{opacity:1}50%{opacity:0.4}}
      `}</style>

      {/* ── Active Campaigns ────────────────────────────────────────────── */}
      {(loading || hasActive) && (
        <div style={{ marginBottom: 24 }}>
          <SectionHeader icon={Zap} label="Live Campaigns" color="#10B981" T={T} />
          {loading
            ? [0, 1].map(i => <div key={i} style={{ marginBottom: 10 }}><Shimmer h={120} /></div>)
            : active.map(c => (
                <div key={c.id} style={{ marginBottom: 10 }}>
                  <ActiveCard c={c} T={T} onJoin={onCampaignClick} />
                </div>
              ))}
        </div>
      )}

      {/* ── Upcoming Campaigns ──────────────────────────────────────────── */}
      {(loading || hasUpcoming) && (
        <div style={{ marginBottom: 24, paddingTop: hasActive ? 4 : 0 }}>
          <SectionHeader icon={Calendar} label="Coming Soon" color={T.pri} T={T} />
          {loading
            ? [0, 1].map(i => <div key={i} style={{ marginBottom: 8 }}><Shimmer h={58} /></div>)
            : upcoming.map(c => (
                <div key={c.id} style={{ marginBottom: 8 }}>
                  <UpcomingCard c={c} T={T} onJoin={onCampaignClick} />
                </div>
              ))}
        </div>
      )}

      {/* ── Recent Winners ──────────────────────────────────────────────── */}
      {(loading || hasWinners) && (
        <div style={{
          marginBottom: 20,
          padding: '14px 14px',
          borderRadius: 14,
          background: `linear-gradient(135deg,#FFD70010,${T.bg})`,
          border: `1px solid #FFD70030`,
        }}>
          <SectionHeader icon={Trophy} label="Recent Winners" color="#F59E0B" T={T} />
          {loading
            ? [0, 1, 2].map(i => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
                  <Shimmer h={32} radius={16} /><Shimmer h={32} radius={16} />
                </div>
              ))
            : winners.map((w, i) => (
                <div key={w.id || i} style={{ borderBottom: i < winners.length - 1 ? `1px solid #FFD70020` : 'none' }}>
                  <WinnerRow w={w} rank={i} T={T} />
                </div>
              ))}
        </div>
      )}

      {/* Empty state */}
      {!loading && !hasAnything && (
        <div style={{ textAlign: 'center', padding: '24px 0', color: T.sub }}>
          <Trophy size={28} style={{ marginBottom: 8, opacity: 0.4 }} />
          <div style={{ fontSize: 13 }}>No campaigns yet</div>
        </div>
      )}
    </>
  );
}




