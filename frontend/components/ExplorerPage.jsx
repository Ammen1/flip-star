import { useState, useEffect, useRef, useCallback } from 'react';
import {
  Search, X, TrendingUp, Flame, Music, Laugh, Dumbbell, Utensils,
  Plane, Palette, Play, Heart, Eye, Hash, User, Clock, ChevronRight,
  Gamepad2, Sparkles, BookOpen, Baby, Shirt, ChevronLeft, ChevronDown,
} from 'lucide-react';
import api from '../api';
import { useTheme } from '../contexts/ThemeContext';
import config from '../config';
import { TikTokPostViewer } from './TikTokPostViewer';

// ── Constants ────────────────────────────────────────────────────────────────
const CATEGORIES = [
  { id: 'all',     label: 'Trending',  icon: Flame,    emoji: '🔥' },
  { id: 'dance',   label: 'Dance',     icon: Music,    emoji: '💃' },
  { id: 'comedy',  label: 'Comedy',    icon: Laugh,    emoji: '😂' },
  { id: 'sports',  label: 'Sports',    icon: Dumbbell, emoji: '⚽' },
  { id: 'food',    label: 'Food',      icon: Utensils, emoji: '🍕' },
  { id: 'travel',  label: 'Travel',    icon: Plane,    emoji: '✈️' },
  { id: 'art',     label: 'Art',       icon: Palette,  emoji: '🎨' },
  { id: 'gaming',  label: 'Gaming',    icon: Gamepad2, emoji: '🎮' },
  { id: 'beauty',  label: 'Beauty',    icon: Sparkles, emoji: '✨' },
  { id: 'fashion', label: 'Fashion',   icon: Shirt,    emoji: '👗' },
  { id: 'education', label: 'Learn',   icon: BookOpen, emoji: '📚' },
];

const TIME_RANGES = [
  { id: '24h', label: '24h'    },
  { id: '7d',  label: '7 days' },
  { id: '30d', label: '30d'    },
];

const RECENT_KEY = 'ep_recent_searches';
const MAX_RECENT = 8;

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

// Generate video poster thumbnail (returns null for local storage)
const getVideoPoster = (url) => null;

const fmt = (n) => {
  if (!n && n !== 0) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000)      return `${(n / 1000).toFixed(1)}k`;
  return String(n);
};

const readRecent = () => {
  try { return JSON.parse(localStorage.getItem(RECENT_KEY) || '[]'); } catch { return []; }
};
const saveRecent = (list) => {
  try { localStorage.setItem(RECENT_KEY, JSON.stringify(list.slice(0, MAX_RECENT))); } catch {}
};
const addRecent = (q) => {
  const prev = readRecent().filter(x => x !== q);
  saveRecent([q, ...prev]);
};

// ── Skeleton shimmer ─────────────────────────────────────────────────────────
function GridSkeleton({ T }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 3 }}>
      {Array.from({ length: 9 }).map((_, i) => (
        <div key={i} style={{
          aspectRatio: '9/16', borderRadius: 8,
          background: `linear-gradient(90deg,${T.border} 25%,${T.bg} 50%,${T.border} 75%)`,
          backgroundSize: '400% 100%',
          animation: 'ex-shimmer 1.4s ease infinite',
        }} />
      ))}
    </div>
  );
}

// ── Single video thumbnail card ───────────────────────────────────────────────
// `index` is the position in the grid; thumbs above the fold (first few) are
// eager-loaded so the user sees content immediately, the rest are lazy with
// async decoding so scrolling isn't stalled by image decodes on the main thread.
const EAGER_LOAD_COUNT = 6;
function VideoThumb({ reel, rank, index = 0, hero = false, onOpen, T }) {
  const [hovered, setHovered] = useState(false);
  const videoUrl = reel.file_url || reel.media;
  const imageUrl = reel.image || reel.media;
  const isVid = !!(videoUrl || '').match(/\.(mp4|webm|ogg|mov)/i) || (videoUrl && videoUrl.includes('/video/'));

  // Priority: 1) explicit thumbnail_url, 2) Cloudinary video poster, 3) image URL, 4) video URL
  const thumb = reel.thumbnail_url
    ? mediaUrl(reel.thumbnail_url)
    : isVid && videoUrl
      ? getVideoPoster(mediaUrl(videoUrl))
      : imageUrl ? mediaUrl(imageUrl)
      : videoUrl ? mediaUrl(videoUrl) : null;

  // Fallback: if no thumbnail found, try different URL patterns
  const finalThumb = thumb || (reel.image ? mediaUrl(reel.image) : null) || 
                     (reel.media && !isVid ? mediaUrl(reel.media) : null) ||
                     (reel.file_url && !isVid ? mediaUrl(reel.file_url) : null);

  const isEager = hero || index < EAGER_LOAD_COUNT;

  return (
    <div
      onClick={() => onOpen?.(reel)}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: 'relative',
        aspectRatio: hero ? '16/9' : '9/16',
        background: 'rgba(249,224,139,0.15)',
        borderRadius: 10,
        border: '1.5px solid rgba(249,224,139,0.3)',
        overflow: 'hidden',
        cursor: 'pointer',
        gridColumn: hero ? '1 / span 3' : undefined,
        boxSizing: 'border-box',
        transform: hovered ? 'scale(1.015)' : 'scale(1)',
        transition: 'transform 0.15s',
        zIndex: hovered ? 1 : 0,
        // Ask the browser to skip painting offscreen thumbs.
        contentVisibility: isEager ? 'visible' : 'auto',
        containIntrinsicSize: '0 260px',
      }}
    >
      {finalThumb
        ? <img src={finalThumb} alt="" loading={isEager ? 'eager' : 'lazy'}
            decoding="async"
            fetchPriority={isEager ? 'high' : 'low'}
            style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }} />
        : <div style={{ width: '100%', height: '100%',
            background: `linear-gradient(135deg,${T.pri}30,#00000080)`,
            display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Play size={hero ? 48 : 28} color="#fff" fill="#fff" />
          </div>
      }

      {/* Hover overlay */}
      <div style={{
        position: 'absolute', inset: 0,
        background: hovered ? 'rgba(0,0,0,0.32)' : 'rgba(0,0,0,0.12)',
        transition: 'background 0.2s',
      }} />

      {/* Video indicator */}
      {isVid && (
        <div style={{
          position: 'absolute', top: 7, left: 7,
          background: 'rgba(0,0,0,0.58)', borderRadius: 4, padding: '2px 5px',
          display: 'flex', alignItems: 'center', gap: 3,
        }}>
          <Play size={9} color="#fff" fill="#fff" />
        </div>
      )}

      {/* Rank medal (top 3) */}
      {rank !== undefined && rank < 3 && (
        <div style={{
          position: 'absolute', top: 7, right: 7,
          background: rank === 0 ? '#FFD700' : rank === 1 ? '#C0C0C0' : '#CD7F32',
          color: '#000', borderRadius: '50%',
          width: hero ? 28 : 20, height: hero ? 28 : 20,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: hero ? 13 : 10, fontWeight: 900,
        }}>
          {rank + 1}
        </div>
      )}

      {/* Bottom stats */}
      <div style={{
        position: 'absolute', bottom: 0, left: 0, right: 0,
        background: 'linear-gradient(transparent, rgba(0,0,0,0.72))',
        padding: hero ? '24px 12px 10px' : '12px 6px 6px',
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        {hero && reel.user?.username && (
          <span style={{ flex: 1, fontSize: 12, fontWeight: 700, color: '#b8d97a',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            @{reel.user.username}
          </span>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
          <Heart size={hero ? 13 : 10} color="#b8d97a" fill="#b8d97a" />
          <span style={{ color: '#b8d97a', fontSize: hero ? 12 : 10, fontWeight: 600 }}>
            {fmt(reel.votes || 0)}
          </span>
        </div>
        {(reel.comment_count > 0 || reel.comments > 0) && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 3 }}>
            <Eye size={hero ? 12 : 10} color="rgba(255,255,255,0.8)" />
            <span style={{ color: 'rgba(255,255,255,0.8)', fontSize: hero ? 12 : 10 }}>
              {fmt(reel.comment_count || reel.comments || 0)}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Main ExplorerPage ─────────────────────────────────────────────────────────
export function ExplorerPage({ user, onBack, onShowProfile, onShowVideoDetail, onShowPostPage, onRequireAuth, onShowSettings, onShowNotifications }) {
  const { colors: T } = useTheme();

  // ── Explore state ──────────────────────────────────────────────────────────
  const [activeCategory, setActiveCategory] = useState('all');
  const [timeRange, setTimeRange] = useState('7d');
  const [videos, setVideos]       = useState([]);
  const [loading, setLoading]     = useState(true);
  const [hashtags, setHashtags]   = useState([]);
  const [hashLoading, setHashLoading] = useState(true);
  const [selectedReel, setSelectedReel] = useState(null);
  const [showHashtagDropdown, setShowHashtagDropdown] = useState(false);

  // ── Search state ───────────────────────────────────────────────────────────
  const [query, setQuery]             = useState('');
  const [debouncedQ, setDebouncedQ]   = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [recentSearches, setRecentSearches] = useState(readRecent);
  const [searchResults, setSearchResults]   = useState({ users: [], posts: [], hashtags: [] });
  const [searchLoading, setSearchLoading]   = useState(false);

  const inputRef    = useRef(null);
  const inSearchMode = debouncedQ.trim().length > 0;

  // ── Fetch trending grid — initial page is small so the grid paints fast.
  //    Subsequent pages are loaded on scroll (infinite scroll, below).
  const INITIAL_LIMIT = 12;      // enough to fill 1.5 screens of 3-column grid
  const PAGE_LIMIT    = 12;
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore]         = useState(true);
  const loadMoreRef = useRef(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setHasMore(true);
    api.request(`/explorer/trending/?category=${activeCategory}&time_range=${timeRange}&limit=${INITIAL_LIMIT}`)
      .then(d => {
        if (cancelled) return;
        const list = Array.isArray(d) ? d : (d?.results || []);
        setVideos(list);
        // If the backend returned fewer than we asked for, there's no more.
        setHasMore(list.length >= INITIAL_LIMIT);
      })
      .catch(() => { if (!cancelled) setVideos([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [activeCategory, timeRange]);

  // ── Infinite scroll ────────────────────────────────────────────────────────
  // An IntersectionObserver on a sentinel below the grid fires the next page
  // only when the user nears the bottom — no work or requests until needed.
  useEffect(() => {
    if (inSearchMode) return;      // search has its own flow
    const node = loadMoreRef.current;
    if (!node || !hasMore || loading) return;

    const observer = new IntersectionObserver(async (entries) => {
      if (!entries[0]?.isIntersecting || loadingMore || !hasMore) return;
      setLoadingMore(true);
      try {
        const offset = videos.length;
        const d = await api.request(
          `/explorer/trending/?category=${activeCategory}&time_range=${timeRange}&limit=${PAGE_LIMIT}&offset=${offset}`
        );
        const page = Array.isArray(d) ? d : (d?.results || []);
        if (page.length === 0) {
          setHasMore(false);
        } else {
          // Dedup by id in case the backend re-sent overlapping items.
          setVideos(prev => {
            const seen = new Set(prev.map(v => v.id));
            return [...prev, ...page.filter(v => !seen.has(v.id))];
          });
          if (page.length < PAGE_LIMIT) setHasMore(false);
        }
      } catch { /* keep what we have */ }
      finally { setLoadingMore(false); }
    }, { rootMargin: '400px 0px' });

    observer.observe(node);
    return () => observer.disconnect();
  }, [activeCategory, timeRange, videos.length, hasMore, loading, loadingMore, inSearchMode]);

  // ── Fetch trending hashtags ────────────────────────────────────────────────
  useEffect(() => {
    let cancelled = false;
    setHashLoading(true);
    api.getTrendingHashtags({ time_range: timeRange, limit: 15 })
      .then(d => { if (!cancelled) setHashtags(Array.isArray(d) ? d : []); })
      .catch(() => { if (!cancelled) setHashtags([]); })
      .finally(() => { if (!cancelled) setHashLoading(false); });
    return () => { cancelled = true; };
  }, [timeRange]);

  // ── Debounce search query ──────────────────────────────────────────────────
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  // ── Live search ────────────────────────────────────────────────────────────
  useEffect(() => {
    if (!debouncedQ.trim()) { setSearchResults({ users: [], posts: [], hashtags: [] }); return; }
    let cancelled = false;
    setSearchLoading(true);
    api.search(debouncedQ.trim())
      .then(d => { if (!cancelled) setSearchResults(d || { users: [], posts: [], hashtags: [] }); })
      .catch(() => { if (!cancelled) setSearchResults({ users: [], posts: [], hashtags: [] }); })
      .finally(() => { if (!cancelled) setSearchLoading(false); });
    return () => { cancelled = true; };
  }, [debouncedQ]);

  const commitSearch = (q) => {
    const trimmed = (q || query).trim();
    if (!trimmed) return;
    addRecent(trimmed);
    setRecentSearches(readRecent());
    setQuery(trimmed);
    inputRef.current?.blur();
    setSearchFocused(false);
  };

  const clearSearch = () => {
    setQuery('');
    setDebouncedQ('');
    setSearchFocused(false);
  };

  // State for hashtag view
  const [hashtagView, setHashtagView] = useState(null); // { tag, videos }
  
  const handleHashtagClick = async (tag) => {
    const cleanTag = tag.replace(/^#/, '');
    setLoading(true);
    try {
      const data = await api.request(`/explorer/hashtag/?tag=${encodeURIComponent(cleanTag)}&limit=30`);
      const results = data?.results || [];
      setHashtagView({ tag: cleanTag, videos: results, count: data?.count || results.length });
      setVideos(results);
    } catch (e) {
      console.error('Failed to fetch hashtag:', e);
      setHashtagView({ tag: cleanTag, videos: [], count: 0 });
      setVideos([]);
    } finally {
      setLoading(false);
    }
  };

  const clearHashtagView = () => {
    setHashtagView(null);
    // Re-fetch trending
    setLoading(true);
    api.request(`/explorer/trending/?category=${activeCategory}&time_range=${timeRange}&limit=30`)
      .then(d => setVideos(Array.isArray(d) ? d : (d?.results || [])))
      .catch(() => setVideos([]))
      .finally(() => setLoading(false));
  };

  // Convert reel data to post format for TikTokPostViewer
  const convertReelToPost = (reel) => ({
    id: reel.id,
    media: reel.file_url || reel.media || reel.thumbnail_url,
    caption: reel.caption || reel.description || '',
    hashtags: reel.hashtags || '',
    user: reel.user,
    votes: reel.votes || 0,
    comment_count: reel.comment_count || reel.comments || 0,
    created_at: reel.created_at,
    is_liked: reel.is_liked,
    is_saved: reel.is_saved,
  });

  const openReel = (reel) => {
    // Find index in current videos array
    const index = videos.findIndex(v => v.id === reel.id);
    if (index !== -1) {
      setSelectedReel({ reel, index });
    } else {
      // For search results, just open the single reel
      setSelectedReel({ reel, index: 0, singleMode: true });
    }
  };

  const showRecentDropdown = searchFocused && query.length === 0 && recentSearches.length > 0;

  return (
    <div style={{ minHeight: '100%', background: T.bg, display: 'flex', flexDirection: 'column' }}>
      <style>{`
        @keyframes ex-shimmer { 0%{background-position:200% 0} 100%{background-position:-200% 0} }
      `}</style>

      {/* ── STICKY HEADER ───────────────────────────────────────────────── */}
      <div style={{
        position: 'sticky', top: 0, zIndex: 20,
        background: T.bg,
        borderBottom: inSearchMode ? 'none' : `1px solid ${T.border}`,
      }}>
        {/* Row 1 – title + search bar */}
        <div style={{ padding: '12px 16px 8px', display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Back button */}
          <button
            onClick={onBack}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '4px 6px 4px 0', display: 'flex', alignItems: 'center',
              color: T.txt, flexShrink: 0,
            }}
          >
            <ChevronLeft size={20} strokeWidth={2.5} />
          </button>
          
          {inSearchMode || searchFocused ? null : (
            <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
              <Flame size={18} color={T.pri} />
              <span style={{ fontSize: 18, fontWeight: 700, color: '#b8d97a' }}>Explore</span>
            </div>
          )}
          {/* Search input wrapper */}
          <div style={{ flex: 1, position: 'relative' }}>
            <Search size={14} color={T.sub} style={{ position: 'absolute', left: 10, top: '50%', transform: 'translateY(-50%)', pointerEvents: 'none' }} />
            <input
              ref={inputRef}
              value={query}
              onChange={e => setQuery(e.target.value)}
              onFocus={() => setSearchFocused(true)}
              onBlur={() => setTimeout(() => setSearchFocused(false), 180)}
              onKeyDown={e => { if (e.key === 'Enter') commitSearch(); }}
              placeholder="Search videos, users…"
              style={{
                width: '100%', boxSizing: 'border-box',
                padding: '8px 32px 8px 32px',
                borderRadius: 20, border: `1px solid ${searchFocused ? T.pri : T.border}`,
                fontSize: 13, background: T.bg, color: T.txt,
                outline: 'none', transition: 'border-color .2s',
              }}
            />
            {query && (
              <button onClick={clearSearch} style={{ position: 'absolute', right: 8, top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', cursor: 'pointer', padding: 4, display: 'flex', alignItems: 'center', color: T.sub }}>
                <X size={12} />
              </button>
            )}

            {/* Recent searches dropdown */}
            {showRecentDropdown && (
              <div style={{
                position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
                background: '#fff', borderRadius: 12,
                boxShadow: '0 8px 32px rgba(0,0,0,0.14)',
                overflow: 'hidden', zIndex: 30,
                border: `1px solid ${T.border}`,
              }}>
                <div style={{ padding: '8px 12px 4px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                  <span style={{ fontSize: 11, fontWeight: 700, color: '#b8d97a', display: 'flex', alignItems: 'center', gap: 4 }}>
                    <Clock size={11} /> Recent
                  </span>
                  <button onClick={() => { saveRecent([]); setRecentSearches([]); }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: 10, color: '#b8d97a', fontWeight: 600 }}>
                    Clear
                  </button>
                </div>
                {recentSearches.map(r => (
                  <button key={r} onMouseDown={() => { setQuery(r); commitSearch(r); }}
                    style={{ width: '100%', padding: '8px 12px', border: 'none', background: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, textAlign: 'left', color: T.txt, fontSize: 13 }}>
                    <Clock size={12} color={T.sub} />
                    <span style={{ flex: 1 }}>{r}</span>
                    <ChevronRight size={12} color={T.sub} />
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* Time range pills — only in explore mode */}
          {!inSearchMode && !searchFocused && (
            <div style={{ display: 'flex', gap: 4, flexShrink: 0 }}>
              {TIME_RANGES.map(r => (
                <button key={r.id} onClick={() => { setTimeRange(r.id); setHashtagView(null); }} style={{
                  padding: '4px 8px', borderRadius: 16,
                  border: `1px solid ${timeRange === r.id ? T.pri : T.border}`,
                  background: timeRange === r.id ? T.pri : 'transparent',
                  color: timeRange === r.id ? '#fff' : '#b8d97a',
                  fontSize: 10, fontWeight: 700, cursor: 'pointer', whiteSpace: 'nowrap',
                }}>
                  {r.label}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Row 2 - category navigation (explore mode only) */}
        {!inSearchMode && (
          <div style={{ padding: '0 16px 8px' }}>
            <div style={{ display: 'flex', gap: 6, overflowX: 'auto', scrollbarWidth: 'none', msOverflowStyle: 'none' }}>
              {CATEGORIES.map(cat => {
                const isActive = activeCategory === cat.id;
                return (
                  <div key={cat.id} onClick={() => { setActiveCategory(cat.id); setHashtagView(null); }} style={{
                    padding: '6px 12px', borderRadius: 10, flexShrink: 0,
                    background: isActive ? T.pri + '15' : T.bg,
                    border: `1px solid ${isActive ? T.pri + '30' : T.border}`,
                    color: isActive ? T.pri : T.txt,
                    fontSize: 12, fontWeight: 600, cursor: 'pointer',
                    display: 'flex', alignItems: 'center', gap: 4,
                    whiteSpace: 'nowrap', transition: 'all .18s',
                  }}>
                    <span style={{ fontSize: 14 }}>{cat.emoji}</span>
                    {cat.label}
                  </div>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* ── SCROLLABLE CONTENT ─────────────────────────────────────────────── */}
      <div style={{ flex: 1, overflowY: 'auto' }}>

        {/* ══ SEARCH RESULTS MODE ══════════════════════════════════════════ */}
        {inSearchMode && (
          <div style={{ padding: '12px 16px 32px', maxWidth: 680, margin: '0 auto' }}>
            {searchLoading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10, paddingTop: 8 }}>
                {[0,1,2,3].map(i => (
                  <div key={i} style={{ height: 56, borderRadius: 12,
                    background: `linear-gradient(90deg,${T.border} 25%,${T.bg} 50%,${T.border} 75%)`,
                    backgroundSize: '400% 100%', animation: 'ex-shimmer 1.4s ease infinite' }} />
                ))}
              </div>
            ) : (
              <>
                {/* Users */}
                {searchResults.users?.length > 0 && (
                  <div style={{ marginBottom: 28 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#b8d97a', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <User size={13} /> PEOPLE
                    </div>
                    {searchResults.users.map(u => {
                      const photo = u.profile_photo ? mediaUrl(u.profile_photo) : null;
                      return (
                        <button key={u.id} onClick={() => onShowProfile?.(u.id)} style={{
                          width: '100%', padding: '10px 12px', border: 'none', background: 'none',
                          cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 12,
                          borderRadius: 12, transition: 'background .15s',
                        }}
                          onMouseEnter={e => e.currentTarget.style.background = T.border + '60'}
                          onMouseLeave={e => e.currentTarget.style.background = 'none'}>
                          <div style={{ width: 42, height: 42, borderRadius: '50%', background: T.pri + '30', overflow: 'hidden', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, border: `2px solid ${T.border}` }}>
                            {photo ? <img src={photo} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} /> : <span style={{ fontSize: 20 }}>👤</span>}
                          </div>
                          <div style={{ flex: 1, textAlign: 'left' }}>
                            <div style={{ fontSize: 14, fontWeight: 700, color: '#b8d97a' }}>@{u.username}</div>
                            {u.followers_count > 0 && <div style={{ fontSize: 12, color: '#b8d97a' }}>{fmt(u.followers_count)} followers</div>}
                          </div>
                          <ChevronRight size={16} color={T.sub} />
                        </button>
                      );
                    })}
                  </div>
                )}

                {/* Hashtags */}
                {searchResults.hashtags?.length > 0 && (
                  <div style={{ marginBottom: 28 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#b8d97a', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Hash size={13} /> HASHTAGS
                    </div>
                    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      {searchResults.hashtags.map(tag => (
                        <button key={tag} onClick={() => handleHashtagClick(tag)} style={{
                          padding: '7px 14px', borderRadius: 20,
                          background: T.pri + '18', border: `1px solid ${T.pri}40`,
                          color: T.pri, fontSize: 14, fontWeight: 700, cursor: 'pointer',
                        }}>
                          #{tag}
                        </button>
                      ))}
                    </div>
                  </div>
                )}

                {/* Posts */}
                {searchResults.posts?.length > 0 && (
                  <div style={{ marginBottom: 24 }}>
                    <div style={{ fontSize: 13, fontWeight: 800, color: '#b8d97a', marginBottom: 10, display: 'flex', alignItems: 'center', gap: 6 }}>
                      <Play size={13} /> POSTS
                    </div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4 }}>
                      {searchResults.posts.map(r => (
                        <VideoThumb key={r.id} reel={r} onOpen={openReel} T={T} />
                      ))}
                    </div>
                  </div>
                )}

                {/* No results */}
                {!searchResults.users?.length && !searchResults.hashtags?.length && !searchResults.posts?.length && (
                  <div style={{ textAlign: 'center', padding: '60px 20px', color: '#b8d97a' }}>
                    <Search size={40} style={{ opacity: 0.3, marginBottom: 12 }} />
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#b8d97a', marginBottom: 6 }}>No results for "{debouncedQ}"</div>
                    <div style={{ fontSize: 13 }}>Try different keywords or browse trending below</div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ══ EXPLORE MODE ═════════════════════════════════════════════════ */}
        {!inSearchMode && (
          <div style={{ padding: '12px 16px 32px' }}>

            {/* ── Trending hashtags dropdown ─────────────────────────────── */}
            {!hashLoading && hashtags.length > 0 && (
              <div style={{ marginBottom: 20 }}>
                <button
                  onClick={() => setShowHashtagDropdown(!showHashtagDropdown)}
                  style={{
                    width: '100%',
                    padding: '10px 14px',
                    borderRadius: 10,
                    background: T.pri + '15',
                    border: `1px solid ${T.pri}35`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    cursor: 'pointer',
                    marginBottom: showHashtagDropdown ? 10 : 0,
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                    <TrendingUp size={13} color={T.pri} />
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#b8d97a' }}>TRENDING HASHTAGS</span>
                  </div>
                  <ChevronDown size={16} color={T.pri} style={{ 
                    transform: showHashtagDropdown ? 'rotate(180deg)' : 'rotate(0deg)',
                    transition: 'transform 0.2s'
                  }} />
                </button>
                
                {showHashtagDropdown && (
                  <div style={{
                    display: 'flex',
                    gap: 8,
                    flexWrap: 'wrap',
                    padding: '4px 0',
                  }}>
                    {hashtags.map(h => (
                      <button key={h.tag} onClick={() => handleHashtagClick(h.tag)} style={{
                        padding: '7px 14px', borderRadius: 20,
                        background: T.pri + '12', border: `1px solid ${T.pri}35`,
                        cursor: 'pointer', gap: 1,
                      }}>
                        <span style={{ fontSize: 13, fontWeight: 800, color: T.pri }}>#{h.tag}</span>
                        <span style={{ fontSize: 10, color: T.sub }}>{fmt(h.posts)} posts</span>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
            {hashLoading && (
              <div style={{ display: 'flex', gap: 8, overflowX: 'auto', marginBottom: 20 }}>
                {[0,1,2,3,4].map(i => (
                  <div key={i} style={{ flexShrink: 0, width: 80, height: 46, borderRadius: 20,
                    background: `linear-gradient(90deg,${T.border} 25%,${T.bg} 50%,${T.border} 75%)`,
                    backgroundSize: '400% 100%', animation: 'ex-shimmer 1.4s ease infinite' }} />
                ))}
              </div>
            )}

            {/* ── Hashtag view header ─────────────────────────────────── */}
            {hashtagView && (
              <div style={{ 
                display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16,
                padding: '12px 16px', background: T.pri + '15', borderRadius: 12,
              }}>
                <button onClick={clearHashtagView} style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 4,
                }}>
                  <X size={20} color={T.txt} />
                </button>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 18, fontWeight: 800, color: T.pri }}>#{hashtagView.tag}</div>
                  <div style={{ fontSize: 12, color: T.sub }}>{fmt(hashtagView.count)} posts</div>
                </div>
                <Hash size={28} color={T.pri} style={{ opacity: 0.5 }} />
              </div>
            )}

            {/* ── Trending video grid ─────────────────────────────────── */}
            {loading ? (
              <GridSkeleton T={T} />
            ) : videos.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px 20px', color: T.sub }}>
                {hashtagView ? (
                  <>
                    <Hash size={44} style={{ opacity: 0.3, marginBottom: 12 }} />
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#b8d97a', marginBottom: 6 }}>No posts with #{hashtagView.tag}</div>
                    <div style={{ fontSize: 13 }}>Be the first to post with this hashtag!</div>
                  </>
                ) : (
                  <>
                    <TrendingUp size={44} style={{ opacity: 0.3, marginBottom: 12 }} />
                    <div style={{ fontSize: 16, fontWeight: 700, color: '#b8d97a', marginBottom: 6 }}>Nothing trending yet</div>
                    <div style={{ fontSize: 13 }}>Check back soon or try a different category</div>
                  </>
                )}
              </div>
            ) : (
              <>
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 4 }}>
                  {videos.map((reel, idx) => (
                    <VideoThumb
                      key={reel.id}
                      reel={reel}
                      rank={idx}
                      index={idx}
                      hero={idx === 0}
                      onOpen={openReel}
                      T={T}
                    />
                  ))}
                </div>
                {/* Infinite-scroll sentinel + loader — only present when
                    there's more to fetch; disappears at the end so the
                    observer doesn't keep firing. */}
                {hasMore && !hashtagView && (
                  <div ref={loadMoreRef} style={{ padding: '16px 0', textAlign: 'center' }}>
                    {loadingMore && (
                      <span style={{ fontSize: 13, color: T.sub }}>Loading more…</span>
                    )}
                  </div>
                )}
                {!hasMore && videos.length > INITIAL_LIMIT && (
                  <div style={{ textAlign: 'center', padding: '18px 0', fontSize: 12, color: T.sub }}>
                    You're all caught up
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </div>

      {/* TikTok-style Post Viewer */}
      {selectedReel && (
        <TikTokPostViewer
          posts={selectedReel.singleMode ? [convertReelToPost(selectedReel.reel)] : videos.map(convertReelToPost)}
          initialIndex={selectedReel.index}
          user={user}
          profileUser={selectedReel.reel.user}
          onClose={() => setSelectedReel(null)}
          isOwnProfile={false}
        />
      )}
    </div>
  );
}




