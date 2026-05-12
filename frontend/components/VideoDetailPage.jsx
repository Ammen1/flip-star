import { useState, useEffect, useRef } from 'react';
import { ChevronLeft, Heart, MessageCircle, Share2, Bookmark, MoreVertical } from 'lucide-react';
import api from '../api';
import config from '../config';
import { useLegacyT } from '../contexts/ThemeContext';

export function VideoDetailPage({ reelId, onBack, onShowProfile, user }) {
  const T = useLegacyT();
  const [reel, setReel] = useState(null);
  const [loading, setLoading] = useState(true);
  const [liked, setLiked] = useState(false);
  const [saved, setSaved] = useState(false);
  const [likesCount, setLikesCount] = useState(0);
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState('');
  const [showComments, setShowComments] = useState(false);
  const [editingComment, setEditingComment] = useState(null);
  const [replyingTo, setReplyingTo] = useState(null);
  const [replyText, setReplyText] = useState('');
  const videoRef = useRef(null);

  useEffect(() => {
    loadReel();
  }, [reelId]);

  const loadReel = async () => {
    try {
      setLoading(true);
      const data = await api.request(`/reels/${reelId}/`);
      setReel(data);
      setLiked(data.is_liked || false);
      setSaved(data.is_saved || false);
      setLikesCount(data.votes || 0);
      
      // Load comments
      const commentsData = await api.request(`/reels/${reelId}/comments/`);
      setComments(Array.isArray(commentsData) ? commentsData : commentsData.results || []);
    } catch (err) {
      console.error('Failed to load reel:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleLike = async () => {
    if (!user) return;
    // Optimistic UI — fill/unfill the heart immediately
    const prevLiked = liked;
    const prevCount = likesCount;
    setLiked(!prevLiked);
    setLikesCount(prevLiked ? Math.max(0, prevCount - 1) : prevCount + 1);
    try {
      const res = await api.request(`/reels/${reelId}/vote/`, { method: 'POST' });
      // Reconcile with server truth
      if (res && typeof res.voted === 'boolean') {
        setLiked(res.voted);
        if (typeof res.votes === 'number') setLikesCount(res.votes);
      }
      // Invalidate any cached reels lists so next fetch is fresh
      api.invalidateCache?.('/reels/');
    } catch (err) {
      console.error('Failed to like:', err);
      // Revert on failure
      setLiked(prevLiked);
      setLikesCount(prevCount);
    }
  };

  const handleSave = async () => {
    if (!user) return;
    try {
      if (saved) {
        await api.request(`/saved/${reelId}/`, { method: 'DELETE' });
      } else {
        await api.request('/saved/', {
          method: 'POST',
          body: JSON.stringify({ reel: reelId }),
        });
      }
      setSaved(!saved);
    } catch (err) {
      console.error('Failed to save:', err);
    }
  };

  const handleShare = () => {
    const url = `${window.location.origin}/post/${reelId}`;
    navigator.clipboard.writeText(url).then(() => {
      alert('Link copied to clipboard!');
    });
  };

  const handleAddComment = async () => {
    if (!newComment.trim() || !user) return;
    try {
      const comment = await api.request(`/reels/${reelId}/comments/`, {
        method: 'POST',
        body: JSON.stringify({ text: newComment }),
      });
      setComments(prev => [comment, ...prev]);
      setNewComment('');
    } catch (err) {
      console.error('Failed to add comment:', err);
    }
  };

  const handleDeleteComment = async (commentId) => {
    try {
      await api.request(`/comments/${commentId}/`, { method: 'DELETE' });
      setComments(prev => prev.map(c => c.id === commentId ? { ...c, is_deleted: true, text: '' } : c));
    } catch (err) {
      console.error('Failed to delete comment:', err);
    }
  };

  const handleEditComment = async (commentId, newText) => {
    try {
      const updated = await api.request(`/comments/${commentId}/`, {
        method: 'PATCH',
        body: JSON.stringify({ text: newText }),
      });
      setComments(prev => prev.map(c => c.id === commentId ? updated : c));
      setEditingComment(null);
    } catch (err) {
      console.error('Failed to edit comment:', err);
    }
  };

  const handleReplyToComment = async (commentId) => {
    if (!replyText.trim() || !user) return;
    try {
      const reply = await api.replyToComment(commentId, replyText);
      setComments(prev => prev.map(c => {
        if (c.id === commentId) {
          return {
            ...c,
            replies: [...(c.replies || []), reply],
            replies_count: (c.replies_count || 0) + 1,
          };
        }
        return c;
      }));
      setReplyText('');
      setReplyingTo(null);
    } catch (err) {
      console.error('Failed to reply to comment:', err);
    }
  };

  if (loading) {
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: '#000', display: 'flex', alignItems: 'center',
        justifyContent: 'center', zIndex: 1000,
      }}>
        <div style={{ color: '#fff', fontSize: 16 }}>Loading...</div>
      </div>
    );
  }

  if (!reel) {
    return (
      <div style={{
        position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
        background: '#000', display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', zIndex: 1000,
      }}>
        <div style={{ color: '#fff', fontSize: 16, marginBottom: 20 }}>Post not found</div>
        <button
          onClick={onBack}
          style={{
            padding: '12px 24px', background: T.pri, color: '#fff',
            border: 'none', borderRadius: 8, fontSize: 15, fontWeight: 600,
            cursor: 'pointer',
          }}
        >
          Go Back
        </button>
      </div>
    );
  }

  const mediaUrl = reel.media || reel.image;
  const fullUrl = mediaUrl?.startsWith('http') ? mediaUrl : `${config.API_BASE_URL.replace('/api', '')}${mediaUrl}`;
  const isVideo = (reel.media || '').match(/\.(mp4|webm|ogg|mov)$/i) || (reel.media || '').includes('video');

  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: '#000', zIndex: 1000, display: 'flex',
      flexDirection: 'column',
    }}>
      {/* Header */}
      <div style={{
        padding: '12px 16px', display: 'flex', alignItems: 'center',
        gap: 12, background: 'rgba(0,0,0,0.5)', position: 'absolute',
        top: 0, left: 0, right: 0, zIndex: 10,
      }}>
        <button
          onClick={onBack}
          style={{
            background: 'none', border: 'none', cursor: 'pointer',
            padding: 8, display: 'flex', alignItems: 'center',
          }}
        >
          <ChevronLeft size={24} color="#fff" />
        </button>
        <div
          onClick={() => onShowProfile?.(reel.user.id)}
          style={{
            display: 'flex', alignItems: 'center', gap: 12,
            cursor: 'pointer', flex: 1,
          }}
        >
          <img
            src={reel.user.profile_photo || '/default-avatar.png'}
            alt={reel.user.username}
            style={{
              width: 36, height: 36, borderRadius: '50%',
              objectFit: 'cover', border: '2px solid #fff',
            }}
          />
          <div style={{ color: '#fff', fontSize: 15, fontWeight: 600 }}>
            {reel.user.username}
          </div>
        </div>
      </div>

      {/* Media */}
      <div style={{
        flex: 1, display: 'flex', alignItems: 'center',
        justifyContent: 'center', position: 'relative',
      }}>
        {isVideo ? (
          <video
            ref={videoRef}
            src={fullUrl}
            style={{
              width: '100%', height: '100%', objectFit: 'contain',
            }}
            controls
            autoPlay
            loop
          />
        ) : (
          <img
            src={fullUrl}
            alt="Post"
            style={{
              width: '100%', height: '100%', objectFit: 'contain',
            }}
          />
        )}

        {/* Action Buttons */}
        <div style={{
          position: 'absolute', right: 12, bottom: 80,
          display: 'flex', flexDirection: 'column', gap: 20,
        }}>
          <div style={{ textAlign: 'center' }}>
            <button
              onClick={handleLike}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 0, display: 'flex', flexDirection: 'column',
                alignItems: 'center', gap: 4,
              }}
            >
              <Heart
                size={32}
                color={liked ? '#EF4444' : '#fff'}
                fill={liked ? '#EF4444' : 'none'}
              />
              <div style={{ color: '#fff', fontSize: 12, fontWeight: 600 }}>
                {likesCount}
              </div>
            </button>
          </div>

          <div style={{ textAlign: 'center' }}>
            <button
              onClick={() => setShowComments(!showComments)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 0, display: 'flex', flexDirection: 'column',
                alignItems: 'center', gap: 4,
              }}
            >
              <MessageCircle size={32} color="#fff" />
              <div style={{ color: '#fff', fontSize: 12, fontWeight: 600 }}>
                {comments.length}
              </div>
            </button>
          </div>

          <div style={{ textAlign: 'center' }}>
            <button
              onClick={handleSave}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 0,
              }}
            >
              <Bookmark
                size={32}
                color={saved ? T.pri : '#fff'}
                fill={saved ? T.pri : 'none'}
              />
            </button>
          </div>

          <div style={{ textAlign: 'center' }}>
            <button
              onClick={handleShare}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 0,
              }}
            >
              <Share2 size={32} color="#fff" />
            </button>
          </div>
        </div>
      </div>

      {/* Caption */}
      {reel.caption && (
        <div style={{
          padding: '12px 16px', background: 'rgba(0,0,0,0.7)',
          color: '#fff', fontSize: 14, lineHeight: 1.5,
        }}>
          <span style={{ fontWeight: 600 }}>{reel.user.username}</span> {reel.caption}
        </div>
      )}

      {/* Comments Panel */}
      {showComments && (
        <div style={{
          position: 'absolute', bottom: 0, left: 0, right: 0,
          background: T.cardBg || '#1A1A1A', borderTopLeftRadius: 20,
          borderTopRightRadius: 20, maxHeight: '60%',
          display: 'flex', flexDirection: 'column',
          borderTop: '1.5px solid rgba(226,179,85,0.3)',
        }}>
          <div style={{
            padding: '16px 20px', borderBottom: `1px solid ${T.border}`,
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: T.txt }}>
              Comments ({comments.length})
            </div>
            <button
              onClick={() => setShowComments(false)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                fontSize: 24, color: T.sub,
              }}
            >
              ×
            </button>
          </div>

          <div style={{
            flex: 1, overflowY: 'auto', padding: '12px 20px',
          }}>
            {comments.map((comment) => (
              <div key={comment.id} style={{ marginBottom: 20 }}>
                {/* Main comment */}
                <div style={{ display: 'flex', gap: 12 }}>
                  <img
                    src={comment.user.profile_photo || '/default-avatar.png'}
                    alt={comment.user.username}
                    style={{
                      width: 32, height: 32, borderRadius: '50%',
                      objectFit: 'cover', flexShrink: 0,
                    }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                      <div style={{ fontSize: 14, fontWeight: 600, color: T.txt }}>
                        {comment.user.username}
                      </div>
                      {comment.edited_at && (
                        <div style={{ fontSize: 11, color: T.sub, fontStyle: 'italic' }}>
                          (edited)
                        </div>
                      )}
                    </div>
                    {comment.is_deleted ? (
                      <div style={{ fontSize: 14, color: T.sub, fontStyle: 'italic', marginTop: 4 }}>
                        Comment deleted
                      </div>
                    ) : editingComment === comment.id ? (
                      <div style={{ marginTop: 4 }}>
                        <input
                          type="text"
                          defaultValue={comment.text}
                          onKeyPress={(e) => {
                            if (e.key === 'Enter') {
                              handleEditComment(comment.id, e.target.value);
                            }
                          }}
                          onBlur={(e) => handleEditComment(comment.id, e.target.value)}
                          style={{
                            width: '100%', padding: '6px 10px', fontSize: 14,
                            border: `1px solid ${T.border}`, borderRadius: 8,
                            outline: 'none',
                          }}
                          autoFocus
                        />
                      </div>
                    ) : (
                      <div style={{ fontSize: 14, color: T.txt, marginTop: 4 }}>
                        {comment.text}
                      </div>
                    )}
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 4 }}>
                      <div style={{ fontSize: 12, color: T.sub }}>
                        {new Date(comment.created_at).toLocaleDateString()}
                      </div>
                      {user && !comment.is_deleted && (
                        <>
                          <button
                            onClick={() => setReplyingTo(comment.id)}
                            style={{
                              background: 'none', border: 'none', cursor: 'pointer',
                              fontSize: 12, color: T.sub, padding: 0,
                            }}
                          >
                            Reply
                          </button>
                          {comment.user.id === user.id && comment.is_editable && (
                            <>
                              <button
                                onClick={() => setEditingComment(comment.id)}
                                style={{
                                  background: 'none', border: 'none', cursor: 'pointer',
                                  fontSize: 12, color: T.sub, padding: 0,
                                }}
                              >
                                Edit
                              </button>
                              <button
                                onClick={() => handleDeleteComment(comment.id)}
                                style={{
                                  background: 'none', border: 'none', cursor: 'pointer',
                                  fontSize: 12, color: '#ef4444', padding: 0,
                                }}
                              >
                                Delete
                              </button>
                            </>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                </div>

                {/* Reply input */}
                {replyingTo === comment.id && (
                  <div style={{ marginLeft: 44, marginTop: 8, display: 'flex', gap: 8 }}>
                    <input
                      type="text"
                      value={replyText}
                      onChange={(e) => setReplyText(e.target.value)}
                      onKeyPress={(e) => e.key === 'Enter' && handleReplyToComment(comment.id)}
                      placeholder={`Reply to ${comment.user.username}...`}
                      style={{
                        flex: 1, padding: '8px 12px', fontSize: 14,
                        border: `1px solid ${T.border}`, borderRadius: 20,
                        outline: 'none',
                      }}
                      autoFocus
                    />
                    <button
                      onClick={() => handleReplyToComment(comment.id)}
                      disabled={!replyText.trim()}
                      style={{
                        padding: '8px 16px', background: T.pri,
                        color: '#fff', border: 'none', borderRadius: 20,
                        fontSize: 13, fontWeight: 600, cursor: 'pointer',
                        opacity: replyText.trim() ? 1 : 0.5,
                      }}
                    >
                      Reply
                    </button>
                    <button
                      onClick={() => { setReplyingTo(null); setReplyText(''); }}
                      style={{
                        background: 'none', border: 'none', cursor: 'pointer',
                        fontSize: 20, color: T.sub, padding: 0,
                      }}
                    >
                      ×
                    </button>
                  </div>
                )}

                {/* Nested replies */}
                {comment.replies && comment.replies.length > 0 && (
                  <div style={{ marginLeft: 44, marginTop: 12 }}>
                    {comment.replies.map((reply) => (
                      <div key={reply.id} style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
                        <img
                          src={reply.user.profile_photo || '/default-avatar.png'}
                          alt={reply.user.username}
                          style={{
                            width: 24, height: 24, borderRadius: '50%',
                            objectFit: 'cover', flexShrink: 0,
                          }}
                        />
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <div style={{ fontSize: 13, fontWeight: 600, color: T.txt }}>
                              {reply.user.username}
                            </div>
                            {reply.edited_at && (
                              <div style={{ fontSize: 10, color: T.sub, fontStyle: 'italic' }}>
                                (edited)
                              </div>
                            )}
                          </div>
                          {reply.is_deleted ? (
                            <div style={{ fontSize: 13, color: T.sub, fontStyle: 'italic', marginTop: 2 }}>
                              Reply deleted
                            </div>
                          ) : (
                            <div style={{ fontSize: 13, color: T.txt, marginTop: 2 }}>
                              {reply.text}
                            </div>
                          )}
                          <div style={{ fontSize: 11, color: T.sub, marginTop: 2 }}>
                            {new Date(reply.created_at).toLocaleDateString()}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          {user && (
            <div style={{
              padding: '12px 20px', borderTop: `1px solid ${T.border}`,
              display: 'flex', gap: 12,
            }}>
              <input
                type="text"
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && handleAddComment()}
                placeholder="Add a comment..."
                style={{
                  flex: 1, padding: '10px 14px', fontSize: 14,
                  border: `1px solid ${T.border}`, borderRadius: 20,
                  outline: 'none',
                }}
              />
              <button
                onClick={handleAddComment}
                disabled={!newComment.trim()}
                style={{
                  padding: '10px 20px', background: T.pri,
                  color: '#fff', border: 'none', borderRadius: 20,
                  fontSize: 14, fontWeight: 600, cursor: 'pointer',
                  opacity: newComment.trim() ? 1 : 0.5,
                }}
              >
                Post
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}




