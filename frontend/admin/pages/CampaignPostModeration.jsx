import React, { useState, useEffect } from 'react';
import api from '../../api';
import config from '../../config';
import { ArrowLeft, CheckCircle, XCircle, Eye } from 'lucide-react';

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

const PRI = '#8fc441';
const BG = '#FAFAF9';
const CARD = '#FFFFFF';
const BORDER = '#E7E5E4';
const TXT = '#1C1917';
const SUB = '#78716C';
const RED = '#EF4444';
const GREEN = '#10B981';

const ScoreSlider = ({ label, value, max, color, onChange }) => {
  const pct = Math.round((value / max) * 100);
  return (
    <div style={{ marginBottom: 14 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 6 }}>
        <span style={{ fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em' }}>{label}</span>
        <span style={{ fontSize: 15, fontWeight: 800, color }}>{value}<span style={{ fontSize: 11, color: SUB, fontWeight: 500 }}>/{max}</span></span>
      </div>
      <div style={{ position: 'relative', height: 6, background: `${color}20`, borderRadius: 4 }}>
        <div style={{ position: 'absolute', left: 0, top: 0, height: '100%', width: `${pct}%`, background: color, borderRadius: 4, transition: 'width 0.15s' }} />
      </div>
      <input type="range" min="0" max={max} value={value} onChange={e => onChange(parseInt(e.target.value))}
        style={{ width: '100%', marginTop: 4, accentColor: color, cursor: 'pointer' }} />
    </div>
  );
};

const CampaignPostModeration = ({ campaignId, onBack }) => {
  const [loading, setLoading] = useState(true);
  const [campaign, setCampaign] = useState(null);
  const [posts, setPosts] = useState([]);
  const [selectedPost, setSelectedPost] = useState(null);
  const [toast, setToast] = useState(null);

  const showToast = (msg, type = 'success') => { setToast({ msg, type }); setTimeout(() => setToast(null), 3000); };

  useEffect(() => { loadData(); }, [campaignId]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [campaignRes, postsRes] = await Promise.all([
        api.request(`/campaigns/${campaignId}/`),
        api.request(`/admin/campaigns/${campaignId}/posts/pending/`)
      ]);
      setCampaign(campaignRes);
      setPosts(postsRes.posts || []);
    } catch (err) {
      console.error('Error loading data:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleModerate = async (scoreId, action, scores = {}) => {
    try {
      await api.request(`/admin/campaigns/posts/${scoreId}/moderate/`, {
        method: 'POST',
        body: JSON.stringify({ action, ...scores })
      });
      showToast(`Post ${action === 'approve' ? 'approved' : 'rejected'} successfully!`, action === 'approve' ? 'success' : 'warn');
      setSelectedPost(null);
      loadData();
    } catch (err) {
      showToast('Failed to moderate post', 'error');
    }
  };

  if (loading) return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: 300 }}>
      <div style={{ width: 36, height: 36, border: `3px solid ${PRI}30`, borderTopColor: PRI, borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
      <style>{`@keyframes spin{to{transform:rotate(360deg)}}`}</style>
    </div>
  );

  return (
    <div style={{ maxWidth: 1100, margin: '0 auto' }}>
      {toast && (
        <div style={{ position: 'fixed', top: 24, right: 24, zIndex: 9999, padding: '12px 20px', borderRadius: 10, background: toast.type === 'error' ? '#FEF2F2' : '#F0FDF4', border: `1.5px solid ${toast.type === 'error' ? '#FECACA' : '#BBF7D0'}`, color: toast.type === 'error' ? RED : GREEN, fontSize: 14, fontWeight: 600, boxShadow: '0 4px 16px rgba(0,0,0,0.12)' }}>
          {toast.msg}
        </div>
      )}

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 28, flexWrap: 'wrap', gap: 12 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
          <button onClick={() => onBack?.()} style={{ display: 'flex', alignItems: 'center', gap: 6, padding: '8px 14px', background: CARD, border: `1.5px solid ${BORDER}`, borderRadius: 8, cursor: 'pointer', fontSize: 13, fontWeight: 600, color: SUB }}>
            <ArrowLeft size={15} /> Back
          </button>
          <div>
            <h1 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: TXT }}>Post Moderation</h1>
            {campaign && <p style={{ margin: 0, fontSize: 13, color: SUB, marginTop: 2 }}>{campaign.title}</p>}
          </div>
        </div>
        {posts.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '8px 16px', background: `${PRI}12`, border: `1.5px solid ${PRI}30`, borderRadius: 20 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: PRI, animation: 'pulse 1.5s ease-in-out infinite' }} />
            <span style={{ fontSize: 13, fontWeight: 700, color: PRI }}>{posts.length} Pending Review</span>
            <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.4}}`}</style>
          </div>
        )}
      </div>

      {posts.length === 0 ? (
        <div style={{ background: CARD, borderRadius: 14, padding: 60, textAlign: 'center', border: `1.5px solid ${BORDER}` }}>
          <CheckCircle size={44} color={`${GREEN}`} style={{ marginBottom: 14 }} />
          <h3 style={{ margin: '0 0 6px', fontSize: 18, fontWeight: 700, color: TXT }}>All Caught Up!</h3>
          <p style={{ margin: 0, color: SUB, fontSize: 14 }}>No posts pending moderation</p>
        </div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: 16 }}>
          {posts.map((post) => (
            <div key={post.id} onClick={() => setSelectedPost(post)}
              style={{ background: CARD, borderRadius: 12, overflow: 'hidden', border: `1.5px solid ${BORDER}`, cursor: 'pointer', transition: 'box-shadow 0.2s, border-color 0.2s' }}
              onMouseEnter={e => { e.currentTarget.style.boxShadow = `0 4px 18px rgba(0,0,0,0.10)`; e.currentTarget.style.borderColor = PRI; }}
              onMouseLeave={e => { e.currentTarget.style.boxShadow = 'none'; e.currentTarget.style.borderColor = BORDER; }}
            >
              {/* Media thumbnail */}
              <div style={{ position: 'relative', paddingTop: '80%', background: '#F3F4F6' }}>
                {post.reel?.thumbnail
                  ? <img src={mediaUrl(post.reel.thumbnail)} alt="Post" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                  : post.reel?.media
                  ? <video src={mediaUrl(post.reel.media)} style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                  : post.reel?.image
                  ? <img src={mediaUrl(post.reel.image)} alt="Post" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover' }} />
                  : null}
                {!post.reel?.thumbnail && !post.reel?.image && !post.reel?.media && (
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Eye size={28} color={`${SUB}60`} />
                  </div>
                )}
                <div style={{ position: 'absolute', top: 8, right: 8, background: 'rgba(0,0,0,0.65)', color: '#fff', padding: '4px 10px', borderRadius: 20, fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 4 }}>
                  <Eye size={11} /> Review
                </div>
              </div>
              {/* Info */}
              <div style={{ padding: '12px 14px' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 6 }}>
                  <div style={{ width: 30, height: 30, borderRadius: '50%', background: `linear-gradient(135deg, ${PRI}, #8fc441)`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 13, fontWeight: 800, flexShrink: 0 }}>
                    {post.user?.username?.[0]?.toUpperCase() || '?'}
                  </div>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontWeight: 700, fontSize: 13, color: TXT, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{post.user?.username}</div>
                    <div style={{ fontSize: 11, color: SUB }}>{new Date(post.created_at).toLocaleDateString()}</div>
                  </div>
                </div>
                {post.reel?.caption && (
                  <p style={{ margin: 0, fontSize: 12, color: SUB, overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', lineHeight: 1.4 }}>
                    {post.reel.caption}
                  </p>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {selectedPost && (
        <ModerationModal post={selectedPost} onClose={() => setSelectedPost(null)} onModerate={handleModerate} />
      )}
    </div>
  );
};

const ModerationModal = ({ post, onClose, onModerate }) => {
  const [action, setAction] = useState('approve');
  const [submitting, setSubmitting] = useState(false);
  const [scores, setScores] = useState({ creativity_score: 20, quality_score: 10, theme_relevance_score: 5 });
  const setScore = (k, v) => setScores(p => ({ ...p, [k]: v }));
  const total = scores.creativity_score + scores.quality_score + scores.theme_relevance_score;

  const handleSubmit = async () => {
    setSubmitting(true);
    await onModerate(post.id, action, action === 'approve' ? scores : {});
    setSubmitting(false);
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000, padding: 16 }}
      onClick={onClose}>
      <div style={{ background: CARD, borderRadius: 16, maxWidth: 860, width: '100%', maxHeight: '90vh', overflow: 'hidden', display: 'grid', gridTemplateColumns: '1fr 1fr', boxShadow: '0 24px 60px rgba(0,0,0,0.25)' }}
        onClick={e => e.stopPropagation()}>

        {/* Left: Media */}
        <div style={{ background: '#0C0C0C', display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 400, position: 'relative', borderRadius: '16px 0 0 16px', overflow: 'hidden' }}>
          {post.reel?.thumbnail
            ? <img src={mediaUrl(post.reel.thumbnail)} alt="Post" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            : post.reel?.media
            ? <video src={mediaUrl(post.reel.media)} controls playsInline style={{ width: '100%', maxHeight: '90vh', objectFit: 'contain' }} />
            : post.reel?.image
            ? <img src={mediaUrl(post.reel.image)} alt="Post" style={{ width: '100%', height: '100%', objectFit: 'contain' }} />
            : null}
          {!post.reel?.thumbnail && !post.reel?.image && !post.reel?.media && (
            <div style={{ color: SUB, fontSize: 14 }}>No media</div>
          )}
        </div>

        {/* Right: Form */}
        <div style={{ display: 'flex', flexDirection: 'column', overflowY: 'auto', maxHeight: '90vh' }}>
          {/* Modal header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '18px 20px', borderBottom: `1.5px solid ${BORDER}`, flexShrink: 0 }}>
            <div>
              <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: TXT }}>Review Post</h2>
              <p style={{ margin: 0, fontSize: 12, color: SUB }}>Campaign moderation</p>
            </div>
            <button onClick={onClose} style={{ width: 32, height: 32, borderRadius: '50%', background: BG, border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <XCircle size={16} color={SUB} />
            </button>
          </div>

          <div style={{ padding: '18px 20px', flex: 1 }}>
            {/* User */}
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 14, paddingBottom: 14, borderBottom: `1.5px solid ${BORDER}` }}>
              <div style={{ width: 40, height: 40, borderRadius: '50%', background: `linear-gradient(135deg, ${PRI}, #8fc441)`, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#fff', fontSize: 16, fontWeight: 800, flexShrink: 0 }}>
                {post.user?.username?.[0]?.toUpperCase() || '?'}
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 14, color: TXT }}>{post.user?.username}</div>
                <div style={{ fontSize: 12, color: SUB }}>{new Date(post.created_at).toLocaleString()}</div>
              </div>
            </div>
            {post.reel?.caption && <p style={{ margin: '0 0 16px', fontSize: 13, color: SUB, lineHeight: 1.5 }}>{post.reel.caption}</p>}

            {/* Decision */}
            <div style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8 }}>Decision</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <button onClick={() => setAction('approve')} style={{ padding: '10px', background: action === 'approve' ? `${GREEN}15` : BG, color: action === 'approve' ? GREEN : SUB, border: `2px solid ${action === 'approve' ? GREEN : BORDER}`, borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                  <CheckCircle size={15} /> Approve
                </button>
                <button onClick={() => setAction('reject')} style={{ padding: '10px', background: action === 'reject' ? '#FEF2F2' : BG, color: action === 'reject' ? RED : SUB, border: `2px solid ${action === 'reject' ? RED : BORDER}`, borderRadius: 8, cursor: 'pointer', fontWeight: 700, fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                  <XCircle size={15} /> Reject
                </button>
              </div>
            </div>

            {/* Scores */}
            {action === 'approve' && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: SUB, textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 12 }}>Initial Scores</div>
                <ScoreSlider label="Creativity" value={scores.creativity_score} max={30} color={PRI} onChange={v => setScore('creativity_score', v)} />
                <ScoreSlider label="Quality" value={scores.quality_score} max={15} color="#8B5CF6" onChange={v => setScore('quality_score', v)} />
                <ScoreSlider label="Theme Relevance" value={scores.theme_relevance_score} max={10} color="#3B82F6" onChange={v => setScore('theme_relevance_score', v)} />
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '10px 14px', background: `${PRI}10`, border: `1.5px solid ${PRI}30`, borderRadius: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 700, color: TXT }}>Initial Total</span>
                  <span style={{ fontSize: 20, fontWeight: 800, color: PRI }}>{total} pts</span>
                </div>
                <p style={{ margin: '8px 0 0', fontSize: 11, color: SUB }}>Engagement & consistency scores auto-calculated from activity</p>
              </div>
            )}
          </div>

          {/* Footer */}
          <div style={{ display: 'flex', gap: 10, padding: '14px 20px', borderTop: `1.5px solid ${BORDER}`, background: '#fff', flexShrink: 0 }}>
            <button onClick={onClose} style={{ flex: 1, padding: '11px', background: BG, border: `1.5px solid ${BORDER}`, borderRadius: 8, fontWeight: 600, cursor: 'pointer', color: TXT, fontSize: 13 }}>Cancel</button>
            <button onClick={handleSubmit} disabled={submitting}
              style={{ flex: 2, padding: '11px', background: submitting ? `${action === 'approve' ? GREEN : RED}aa` : action === 'approve' ? GREEN : RED, color: '#fff', border: 'none', borderRadius: 8, fontWeight: 700, cursor: submitting ? 'not-allowed' : 'pointer', fontSize: 13, display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7 }}>
              {submitting ? 'Submitting...' : action === 'approve' ? <><CheckCircle size={15} /> Approve Post</> : <><XCircle size={15} /> Reject Post</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};

export default CampaignPostModeration;




