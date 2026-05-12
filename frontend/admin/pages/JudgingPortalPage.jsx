import { useState, useEffect } from 'react';
import { Eye, CheckCircle, XCircle, Star, Image as ImageIcon, User, Award, Filter } from 'lucide-react';
import api from '../../api';

export function JudgingPortalPage({ theme }) {
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('pending');
  const [selectedPost, setSelectedPost] = useState(null);
  const [scores, setScores] = useState({ creativity: 0, quality: 0, theme: 0 });

  useEffect(() => {
    loadPosts();
  }, [filter]);

  const loadPosts = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/admin/contest/judging/?status=${filter}`);
      setPosts(response.posts || []);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load posts:', error);
      setLoading(false);
    }
  };

  const submitJudging = async () => {
    if (!selectedPost) return;

    try {
      await api.request(`/admin/contest/judge/${selectedPost.reel_id}/`, {
        method: 'POST',
        body: JSON.stringify({
          creativity: parseInt(scores.creativity),
          quality: parseInt(scores.quality),
          theme_relevance: parseInt(scores.theme),
        }),
      });

      // Refresh posts
      loadPosts();
      setSelectedPost(null);
      setScores({ creativity: 0, quality: 0, theme: 0 });
    } catch (error) {
      console.error('Failed to submit judging:', error);
    }
  };

  const ScoreInput = ({ label, value, max, onChange }) => (
    <div style={{ marginBottom: 16 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>{label}</span>
        <span style={{ fontSize: 14, color: theme.sub }}>{value} / {max}</span>
      </div>
      <input
        type="range"
        min="0"
        max={max}
        value={value}
        onChange={(e) => onChange(parseInt(e.target.value))}
        style={{
          width: '100%',
          height: 8,
          borderRadius: 4,
          accentColor: theme.pri,
        }}
      />
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        marginTop: 8,
        gap: 8,
      }}>
        {[0, max/4, max/2, max*0.75, max].map((val) => (
          <button
            key={val}
            onClick={() => onChange(Math.floor(val))}
            style={{
              padding: '4px 8px',
              background: value === Math.floor(val) ? theme.pri : theme.bg,
              border: 'none',
              borderRadius: 4,
              fontSize: 12,
              color: value === Math.floor(val) ? '#fff' : theme.txt,
              cursor: 'pointer',
            }}
          >
            {Math.floor(val)}
          </button>
        ))}
      </div>
    </div>
  );

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{ margin: 0, fontSize: 32, fontWeight: 700, color: theme.txt, marginBottom: 8 }}>
          Judging Portal
        </h1>
        <p style={{ margin: 0, fontSize: 16, color: theme.sub }}>
          Score posts on Creativity, Quality, and Theme Relevance
        </p>
      </div>

      {/* Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
        gap: 16,
        marginBottom: 24,
      }}>
        {[
          { label: 'Pending', value: '0', color: theme.orange },
          { label: 'Judged', value: '0', color: theme.green },
          { label: 'Total', value: posts.length, color: theme.pri },
        ].map((stat) => (
          <div key={stat.label} style={{
            background: theme.card,
            borderRadius: 12,
            padding: 16,
            border: `1px solid ${theme.border}`,
            textAlign: 'center',
          }}>
            <div style={{ fontSize: 28, fontWeight: 700, color: stat.color }}>{stat.value}</div>
            <div style={{ fontSize: 12, color: theme.sub }}>{stat.label}</div>
          </div>
        ))}
      </div>

      {/* Filter */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 24 }}>
        {['pending', 'judged', 'all'].map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            style={{
              padding: '8px 16px',
              background: filter === f ? theme.pri : theme.card,
              border: `1px solid ${filter === f ? theme.pri : theme.border}`,
              borderRadius: 8,
              color: filter === f ? '#fff' : theme.txt,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {f}
          </button>
        ))}
      </div>

      {/* Posts Grid */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
          Loading posts...
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: 20,
        }}>
          {posts.map((post) => (
            <div
              key={post.id}
              onClick={() => {
                setSelectedPost(post);
                setScores(post.current_scores || { creativity: 0, quality: 0, theme: 0 });
              }}
              style={{
                background: theme.card,
                borderRadius: 12,
                overflow: 'hidden',
                border: `2px solid ${selectedPost?.id === post.id ? theme.pri : theme.border}`,
                cursor: 'pointer',
                transition: 'all 0.2s',
              }}
            >
              {/* Image Preview */}
              <div style={{
                height: 160,
                background: post.image ? `url(${post.image}) center/cover` : theme.bg,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                {!post.image && <ImageIcon size={40} color={theme.sub} />}
              </div>

              <div style={{ padding: 16 }}>
                {/* User Info */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
                  <div style={{
                    width: 32,
                    height: 32,
                    borderRadius: '50%',
                    background: theme.pri,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <User size={16} color="#fff" />
                  </div>
                  <span style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>
                    @{post.user?.username}
                  </span>
                </div>

                {/* Caption */}
                <p style={{
                  margin: 0,
                  fontSize: 13,
                  color: theme.sub,
                  lineHeight: 1.5,
                  marginBottom: 12,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  display: '-webkit-box',
                  WebkitLineClamp: 2,
                  WebkitBoxOrient: 'vertical',
                }}>
                  {post.caption || 'No caption'}
                </p>

                {/* Status */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {post.is_judged ? (
                    <>
                      <CheckCircle size={16} color={theme.green} />
                      <span style={{ fontSize: 12, color: theme.green, fontWeight: 600 }}>
                        Judged • {post.total_score} pts
                      </span>
                    </>
                  ) : (
                    <>
                      <Award size={16} color={theme.orange} />
                      <span style={{ fontSize: 12, color: theme.orange, fontWeight: 600 }}>
                        Pending Judgment
                      </span>
                    </>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Judging Modal */}
      {selectedPost && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0,0,0,0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000,
          padding: 20,
        }}>
          <div style={{
            background: '#fff',
            borderRadius: 16,
            padding: 32,
            width: '100%',
            maxWidth: 500,
            maxHeight: '90vh',
            overflowY: 'auto',
          }}>
            <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 24 }}>
              Score Post
            </h2>

            {/* Post Preview */}
            <div style={{
              height: 200,
              background: selectedPost.image ? `url(${selectedPost.image}) center/cover` : theme.bg,
              borderRadius: 12,
              marginBottom: 24,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {!selectedPost.image && <ImageIcon size={48} color={theme.sub} />}
            </div>

            <p style={{ fontSize: 14, color: theme.sub, marginBottom: 24 }}>
              By @{selectedPost.user?.username}
            </p>

            {/* Score Inputs */}
            <ScoreInput
              label="Creativity (Max 30)"
              value={scores.creativity}
              max={30}
              onChange={(val) => setScores({ ...scores, creativity: val })}
            />
            <ScoreInput
              label="Quality (Max 15)"
              value={scores.quality}
              max={15}
              onChange={(val) => setScores({ ...scores, quality: val })}
            />
            <ScoreInput
              label="Theme Relevance (Max 10)"
              value={scores.theme}
              max={10}
              onChange={(val) => setScores({ ...scores, theme: val })}
            />

            {/* Total Preview */}
            <div style={{
              padding: 16,
              background: theme.pri + '10',
              borderRadius: 12,
              marginBottom: 24,
              textAlign: 'center',
            }}>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Your Score Contribution</div>
              <div style={{ fontSize: 32, fontWeight: 800, color: theme.pri }}>
                {scores.creativity + scores.quality + scores.theme}
              </div>
              <div style={{ fontSize: 12, color: theme.sub }}>
                + Engagement & Consistency (Auto)
              </div>
            </div>

            {/* Actions */}
            <div style={{ display: 'flex', gap: 12 }}>
              <button
                onClick={() => setSelectedPost(null)}
                style={{
                  flex: 1,
                  padding: 14,
                  background: theme.bg,
                  border: 'none',
                  borderRadius: 8,
                  color: theme.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                onClick={submitJudging}
                style={{
                  flex: 1,
                  padding: 14,
                  background: theme.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Submit Score
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}




