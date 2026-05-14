import React, { useState, useEffect, useRef } from 'react';
import api from '../api';
import config from '../config';
import { ArrowLeft, Heart, MessageCircle, Award, TrendingUp, Clock, Star, Trophy } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

// Add CSS animation for points notification
if (typeof document !== 'undefined' && !document.getElementById('points-earned-animation')) {
  const style = document.createElement('style');
  style.id = 'points-earned-animation';
  style.textContent = `
    @keyframes pointsEarned {
      0% {
        opacity: 0;
        transform: translate(-50%, -50%) scale(0.5);
      }
      20% {
        opacity: 1;
        transform: translate(-50%, -50%) scale(1.1);
      }
      80% {
        opacity: 1;
        transform: translate(-50%, -80%) scale(1);
      }
      100% {
        opacity: 0;
        transform: translate(-50%, -100%) scale(0.8);
      }
    }
  `;
  document.head.appendChild(style);
}

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

const RANK_STYLES = {
  1: { bg: 'rgba(143,196,65,0.2)', border: '#8fc441', text: '#8fc441', label: '🥇 #1' },
  2: { bg: 'rgba(143,196,65,0.15)', border: 'rgba(143,196,65,0.7)', text: 'rgba(143,196,65,0.8)', label: '🥈 #2' },
  3: { bg: 'rgba(143,196,65,0.12)', border: 'rgba(143,196,65,0.6)', text: 'rgba(143,196,65,0.7)', label: '🥉 #3' },
};

// ── Per-campaign stale-while-revalidate cache ─────────────────────────────
// Paints the last-known feed instantly (including when the backend is cold),
// then refreshes in the background.  Lives only for the session.
const CF_CACHE_TTL = 5 * 60 * 1000;   // 5 min fresh window
const cfCacheKey = (id, filter) => `campaign_feed_${id}_${filter}`;
const readCfCache = (id, filter) => {
  try {
    const raw = sessionStorage.getItem(cfCacheKey(id, filter));
    if (!raw) return null;
    const { ts, data } = JSON.parse(raw);
    if (Date.now() - ts > CF_CACHE_TTL) return null;
    return data;
  } catch { return null; }
};
const writeCfCache = (id, filter, data) => {
  try { sessionStorage.setItem(cfCacheKey(id, filter), JSON.stringify({ ts: Date.now(), data })); } catch {}
};

const CampaignFeed = ({ campaignId, onBack }) => {
  const { colors: T } = useTheme();
  // Seed from cache so the page paints immediately instead of waiting for a
  // cold-start roundtrip.  If no cache, we show the skeleton loader.
  const cached = readCfCache(campaignId, 'all');
  const [loading, setLoading] = useState(!cached);
  const [campaign, setCampaign] = useState(cached?.campaign || null);
  const [posts, setPosts] = useState(cached?.posts || []);
  const [filter, setFilter] = useState('all');
  const engagementTimer = useRef(null);

  useEffect(() => { loadData(); }, [campaignId, filter]);

  const loadData = async (silent = false) => {
    try {
      // If we have fresh cache for this filter combo, paint it first and
      // only show the spinner when there's nothing to show.
      const cached = readCfCache(campaignId, filter);
      if (cached) {
        setCampaign(cached.campaign);
        setPosts(cached.posts || []);
        setLoading(false);
        silent = true;                // refresh in background
      } else if (!silent) {
        setLoading(true);
      }

      const [campaignRes, feedRes] = await Promise.all([
        api.request(`/campaigns/${campaignId}/`),
        api.request(`/campaigns/${campaignId}/feed/?filter=${filter}`)
      ]);
      setCampaign(campaignRes);
      setPosts(feedRes.posts || []);
      writeCfCache(campaignId, filter, { campaign: campaignRes, posts: feedRes.posts || [] });
    } catch (error) {
      console.error('Error loading feed:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLike = async (post) => {
    const reelId = post.reel?.id;
    if (!reelId) return;

    const wasLiked = post.engagement?.user_liked ?? false;
    const prevLikes = post.engagement?.likes ?? 0;

    // Optimistic update — instant UI response
    setPosts(prev => prev.map(p =>
      p.id === post.id
        ? { ...p, engagement: { ...p.engagement, user_liked: !wasLiked, likes: wasLiked ? prevLikes - 1 : prevLikes + 1 } }
        : p
    ));

    try {
      // 1. Toggle like on the reel (syncs with profile vote count everywhere)
      const voteResponse = await api.request(`/reels/${reelId}/vote/`, { method: 'POST' });
      
      // 2. Get scoring config to show points earned
      const configResponse = await api.request(`/campaigns/${campaignId}/scoring-config/`);
      const campaignType = campaign?.campaign_type || 'daily';
      const likesWeight = configResponse[campaignType]?.engagement?.likes_weight || 1.0;
      
      // Show points earned notification (only if liking, not unliking)
      if (!wasLiked) {
        showPointsEarned(post.user_id, likesWeight, 'like');
      }

      // 3. Debounce engagement score refresh (avoids hammering on rapid clicks)
      clearTimeout(engagementTimer.current);
      engagementTimer.current = setTimeout(async () => {
        try {
          // Update engagement_score → total_score on all posts in campaign
          await api.request(`/campaigns/${campaignId}/engagement/update/`, { method: 'POST' });
          // Re-fetch feed to get updated scores + re-ordered ranking
          loadData(true);
        } catch (e) {
          console.error('Engagement sync error:', e);
        }
      }, 1200);
    } catch (error) {
      // Revert optimistic update on failure
      setPosts(prev => prev.map(p =>
        p.id === post.id
          ? { ...p, engagement: { ...p.engagement, user_liked: wasLiked, likes: prevLikes } }
          : p
      ));
      console.error('Vote error:', error);
    }
  };

  const showPointsEarned = (userId, points, type) => {
    // Show floating points notification
    const notification = document.createElement('div');
    notification.style.cssText = `
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
      color: white;
      padding: 16px 24px;
      border-radius: 12px;
      font-size: 18px;
      font-weight: 700;
      z-index: 10000;
      box-shadow: 0 8px 24px rgba(102, 126, 234, 0.4);
      animation: pointsEarned 1.5s ease-out forwards;
    `;
    notification.innerHTML = `+${points} points! 🎯`;
    document.body.appendChild(notification);
    
    setTimeout(() => notification.remove(), 1500);
  };

  const FILTERS = [
    { id: 'all', label: 'All Posts', icon: <TrendingUp size={14} /> },
    { id: 'top', label: 'Top Scored', icon: <Star size={14} /> },
    { id: 'recent', label: 'Recent', icon: <Clock size={14} /> },
  ];

  return (
    <div style={{ minHeight: '100vh', background: T.bg, boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{
        background: T.card,
        borderBottom: `1px solid ${T.border}`,
        padding: '16px 24px',
        position: 'sticky',
        top: 0,
        zIndex: 100,
      }}>
        <div style={{ maxWidth: 760, margin: '0 auto' }}>
          <button
            onClick={() => onBack?.()}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: T.sub, fontSize: 14, fontWeight: 600, padding: '4px 0',
              marginBottom: 10,
            }}
          >
            <ArrowLeft size={16} />
            Back to Campaign
          </button>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12 }}>
            <div>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: T.txt }}>{campaign?.title}</h1>
              <p style={{ margin: 0, fontSize: 13, color: T.sub }}>Campaign Feed · {posts.length} entries</p>
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              {FILTERS.map(f => (
                <button
                  key={f.id}
                  onClick={() => setFilter(f.id)}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 5,
                    padding: '7px 14px',
                    background: filter === f.id ? T.pri : T.card,
                    color: filter === f.id ? '#fff' : T.sub,
                    border: `1.5px solid ${filter === f.id ? T.pri : T.border}`,
                    borderRadius: 20, cursor: 'pointer',
                    fontSize: 13, fontWeight: 600,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {f.icon}{f.label}
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ maxWidth: 760, margin: '0 auto', padding: '24px 24px 60px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: T.sub }}>
            <div style={{ fontSize: 15 }}>Loading posts...</div>
          </div>
        ) : posts.length === 0 ? (
          <div style={{
            background: T.card, borderRadius: 14, padding: '48px 24px',
            textAlign: 'center', border: `1px solid ${T.border}`,
          }}>
            <Award size={44} color={T.pri} style={{ marginBottom: 16, opacity: 0.5 }} />
            <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: T.txt }}>No Posts Yet</h3>
            <p style={{ margin: 0, color: T.sub, fontSize: 14 }}>Be the first to participate!</p>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {posts.map((post, idx) => (
              <PostCard key={post.id} post={post} rank={idx + 1} onVote={handleLike} campaignType={campaign?.campaign_type} isVotingOpen={campaign?.status === 'voting'} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const PostCard = ({ post, rank, onVote, campaignType, isVotingOpen }) => {
  const [showScores, setShowScores] = useState(false);

  const totalScore = post.scores?.total ?? post.total_score ?? 0;
  const likes = post.engagement?.likes ?? post.votes_count ?? 0;
  const comments = post.engagement?.comments ?? post.comments_count ?? 0;
  const userLiked = post.engagement?.user_liked ?? post.has_voted ?? false;
  const createdAt = post.reel?.created_at ?? post.created_at;
  const scores = post.scores ?? {
    creativity: post.creativity_score,
    engagement: post.engagement_score,
    quality: post.quality_score,
    theme_relevance: post.theme_relevance_score,
  };
  const rankStyle = RANK_STYLES[rank];

  return (
    <div style={{
      background: T.card, borderRadius: 14, overflow: 'hidden',
      border: `1.5px solid ${rankStyle ? rankStyle.border : T.border}`,
      boxShadow: rankStyle ? `0 2px 12px ${rankStyle.border}30` : '0 1px 4px rgba(0,0,0,0.06)',
    }}>
      {/* User Row */}
      <div style={{ padding: '14px 16px', display: 'flex', alignItems: 'center', gap: 12 }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          background: `linear-gradient(135deg, ${T.pri}, #F59E0B)`,
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: '#fff', fontSize: 16, fontWeight: 700, flexShrink: 0,
        }}>
          {post.user?.username?.[0]?.toUpperCase() || '?'}
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 14, color: T.txt }}>{post.user?.username}</div>
          {createdAt && (
            <div style={{ fontSize: 12, color: T.sub }}>
              {new Date(createdAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {rankStyle && (
            <div style={{
              background: rankStyle.bg, color: rankStyle.text,
              border: `1px solid ${rankStyle.border}`,
              padding: '4px 10px', borderRadius: 20,
              fontSize: 12, fontWeight: 700,
            }}>
              {rankStyle.label}
            </div>
          )}
          {!rankStyle && rank && (
            <div style={{
              background: T.bg, color: T.sub,
              border: `1px solid ${T.border}`,
              padding: '4px 10px', borderRadius: 20,
              fontSize: 12, fontWeight: 600,
            }}>
              #{rank}
            </div>
          )}
          {totalScore > 0 && (
            <div style={{
              background: T.pri + '18', color: T.pri,
              border: `1px solid ${T.pri}40`,
              padding: '5px 12px', borderRadius: 20,
              fontSize: 13, fontWeight: 700,
            }}>
              {Number(totalScore).toFixed(1)} pts
            </div>
          )}
        </div>
      </div>

      {/* Media */}
      {(post.reel?.thumbnail || post.reel?.image || post.reel?.media) && (
        <div style={{ background: '#000', maxHeight: 480, overflow: 'hidden' }}>
          {post.reel?.thumbnail ? (
            <img
              src={mediaUrl(post.reel.thumbnail)}
              alt=""
              style={{ width: '100%', display: 'block', objectFit: 'contain', maxHeight: 480 }}
            />
          ) : post.reel?.image ? (
            <img
              src={mediaUrl(post.reel.image)}
              alt=""
              style={{ width: '100%', display: 'block', objectFit: 'contain', maxHeight: 480 }}
            />
          ) : post.reel?.media ? (
            <video
              src={mediaUrl(post.reel.media)}
              controls
              playsInline
              style={{ width: '100%', display: 'block', maxHeight: 480 }}
            />
          ) : null}
        </div>
      )}

      {/* Caption */}
      {post.reel?.caption && (
        <div style={{ padding: '12px 16px' }}>
          <p style={{ margin: 0, fontSize: 14, color: T.txt, lineHeight: 1.55 }}>{post.reel.caption}</p>
        </div>
      )}

      {/* Actions */}
      <div style={{
        padding: '10px 16px', borderTop: `1px solid ${T.border}`,
        display: 'flex', alignItems: 'center', gap: 16,
      }}>
        <button
          onClick={() => {
            if (campaignType === 'grand' && isVotingOpen) {
              onVote(post);
            }
          }}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            background: userLiked ? `${T.red}12` : 'transparent',
            border: `1.5px solid ${userLiked ? T.red : T.border}`,
            borderRadius: 20, padding: '5px 12px',
            cursor: (campaignType === 'grand' && isVotingOpen) ? 'pointer' : 'default',
            fontSize: 14, fontWeight: 700,
            color: userLiked ? T.red : T.sub,
            transition: 'all 0.18s ease',
            opacity: (campaignType === 'grand' && isVotingOpen) ? 1 : 0.7,
          }}
          disabled={campaignType !== 'grand' || !isVotingOpen}
        >
          <Heart size={16} fill={userLiked ? T.red : 'none'} color={userLiked ? T.red : T.sub} />
          {likes}
        </button>
        <button style={{
          display: 'flex', alignItems: 'center', gap: 6,
          background: 'transparent', border: 'none', cursor: 'default',
          fontSize: 14, fontWeight: 600, color: T.sub,
        }}>
          <MessageCircle size={18} />
          {comments}
        </button>
        {totalScore > 0 && (
          <button
            onClick={() => setShowScores(!showScores)}
            style={{
              marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 5,
              background: 'transparent', border: 'none', cursor: 'pointer',
              fontSize: 13, fontWeight: 600, color: T.pri,
            }}
          >
            <Award size={16} />
            {showScores ? 'Hide' : 'View'} Scores
          </button>
        )}
      </div>

      {/* Score Breakdown */}
      {showScores && totalScore > 0 && (
        <div style={{ padding: '14px 16px', background: T.bg, borderTop: `1px solid ${T.border}` }}>
          <p style={{ margin: '0 0 12px', fontSize: 13, fontWeight: 700, color: T.txt }}>Score Breakdown</p>
          <div style={{ display: 'grid', gap: 8 }}>
            {scores.creativity > 0 && <ScoreBar label="Creativity" score={scores.creativity} max={30} theme={T} />}
            {scores.engagement > 0 && <ScoreBar label="Engagement" score={scores.engagement} max={25} theme={T} />}
            {scores.quality > 0 && <ScoreBar label="Quality" score={scores.quality} max={15} theme={T} />}
            {scores.theme_relevance > 0 && <ScoreBar label="Theme Relevance" score={scores.theme_relevance} max={10} theme={T} />}
          </div>
        </div>
      )}
    </div>
  );
};

const ScoreBar = ({ label, score, max, theme: T }) => {
  const pct = Math.round((score / max) * 100);
  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 5, fontSize: 12 }}>
        <span style={{ color: T.sub, fontWeight: 500 }}>{label}</span>
        <span style={{ fontWeight: 700, color: T.pri }}>{score}/{max}</span>
      </div>
      <div style={{ height: 6, background: T.border, borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', background: T.pri, borderRadius: 3, transition: 'width 0.4s ease' }} />
      </div>
    </div>
  );
};

export default CampaignFeed;




