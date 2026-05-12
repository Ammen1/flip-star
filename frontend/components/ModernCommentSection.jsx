import { useState, useEffect, useRef } from "react";
import { X, Heart, MessageCircle, Send, Loader, Flag, AtSign, Gift } from "lucide-react";
import api from "../api";
import config from "../config";
import { AlertModal } from "./AlertModal";
import { getRelativeTime } from "../utils/timeUtils";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import GiftPage from "./GiftPage";
import "./ModernCommentSection.css";

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  if (url.startsWith('/')) return `${config.API_BASE_URL.replace('/api', '')}${url}`;
  return `${config.API_BASE_URL.replace('/api', '')}/${url}`;
};

// Render text with @mentions as colored, tappable spans. Mentions open the
// mentioned user's profile via the supplied callback. Falls back to plain text
// if no callback is provided.
function renderTextWithMentions(text, accentColor, onMentionTap) {
  if (!text) return null;
  const parts = [];
  const regex = /@(\w+)/g;
  let last = 0;
  let match;
  let i = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > last) {
      parts.push(text.slice(last, match.index));
    }
    const username = match[1];
    parts.push(
      <span
        key={`m-${i++}-${match.index}`}
        onClick={(e) => {
          e.stopPropagation();
          if (onMentionTap) onMentionTap(username);
        }}
        style={{
          color: accentColor || '#F9E08B',
          fontWeight: 700,
          cursor: onMentionTap ? 'pointer' : 'default',
        }}
      >@{username}</span>
    );
    last = match.index + match[0].length;
  }
  if (last < text.length) parts.push(text.slice(last));
  return parts;
}

// Look up a user id by username via /api/search/ and navigate to that profile.
async function openProfileByUsername(username, onShowProfile) {
  if (!onShowProfile) return;
  try {
    const res = await api.search(username);
    const found = (res?.users || []).find(
      (u) => (u.username || '').toLowerCase() === username.toLowerCase()
    );
    if (found?.id) onShowProfile(found.id);
  } catch (err) {
    console.warn('Failed to resolve mention to profile:', err);
  }
}

function buildCommentTree(flatList) {
  if (!Array.isArray(flatList)) return [];
  const map = {};
  const roots = [];
  // First pass: create map and initialize replies array for all comments
  flatList.forEach(c => {
    map[c.id] = { ...c, replies: [] };
  });
  // Second pass: build the tree structure
  flatList.forEach(c => {
    const node = map[c.id];
    if (c.parent) {
      const parent = map[c.parent];
      if (parent) {
        // Check if reply already exists to avoid duplicates
        if (!parent.replies.some(r => r.id === node.id)) {
          parent.replies.push(node);
        }
      } else {
        // Parent not found, treat as root
        roots.push(node);
      }
    } else {
      roots.push(node);
    }
  });
  // Sort roots by created_at (newest first)
  roots.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
  return roots;
}

const CommentItem = ({ comment, T, user, onLike, onReply, onReport, replyTo, replyText, onReplyTextChange, onPostReply, posting, depth = 0, expandedReplies, onToggleReplies, onShowProfile }) => {
  const isReply = depth > 0;
  const avatarSize = isReply ? 28 : 36;
  const hasReplies = comment.replies && comment.replies.length > 0;
  const isExpanded = expandedReplies?.has(comment.id);
  const showRepliesToggle = !isReply && hasReplies; // Only show toggle at top level

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
      <div style={{ display: "flex", gap: 12, position: 'relative' }}>
        <div style={{
          width: avatarSize,
          height: avatarSize,
          borderRadius: "50%",
          background: T.pri + "30",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: isReply ? 12 : 16,
          flexShrink: 0,
          overflow: "hidden",
          zIndex: 1,
        }}>
          {comment.user?.profile_photo ? (
            <img 
              src={mediaUrl(comment.user.profile_photo)} 
              alt="" 
              style={{ width: "100%", height: "100%", objectFit: "cover" }} 
            />
          ) : "👤"}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4, flexWrap: "wrap" }}>
            <span style={{ fontSize: isReply ? 13 : 14, fontWeight: 700, color: T.txt }}>
              {comment.user?.username || "User"}
            </span>
            <span style={{ fontSize: 11, color: T.sub }}>
              {getRelativeTime(comment.created_at)}
            </span>
          </div>
          <div style={{ fontSize: isReply ? 13 : 14, color: T.txt, marginBottom: 8, lineHeight: 1.5, wordBreak: "break-word" }}>
            {renderTextWithMentions(comment.text, T.pri, (username) => openProfileByUsername(username, onShowProfile))}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <button
              onClick={() => onLike(comment.id, isReply)}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: 0,
                display: "flex", alignItems: "center", gap: 4,
                color: comment.is_liked ? "#EF4444" : T.sub,
                fontSize: 12, fontWeight: 600,
              }}
            >
              <Heart size={16} fill={comment.is_liked ? "#EF4444" : "none"} />
              {comment.likes_count || 0}
            </button>
            <button
              onClick={() => onReply(comment)}
              style={{
                background: "none", border: "none", cursor: "pointer", padding: 0,
                display: "flex", alignItems: "center", gap: 4,
                color: T.sub, fontSize: 12, fontWeight: 600,
              }}
            >
              <MessageCircle size={16} />
              Reply
            </button>
            {user && comment.user?.id !== user?.id && (
              <button
                onClick={() => onReport(comment.id)}
                style={{
                  background: "none", border: "none", cursor: "pointer", padding: 0,
                  display: "flex", alignItems: "center", gap: 4,
                  color: T.sub, fontSize: 12, fontWeight: 600, marginLeft: "auto", opacity: 0.6,
                }}
              >
                <Flag size={13} />
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Reply Input */}
      {replyTo === comment.id && (
        <div style={{ marginLeft: depth === 0 ? 48 : 40, display: "flex", gap: 8 }}>
          <input
            type="text"
            value={replyText}
            onChange={(e) => onReplyTextChange(e.target.value)}
            placeholder={`Reply to ${comment.user?.username || 'user'}...`}
            autoFocus
            style={{
              flex: 1, padding: "8px 12px", border: `1px solid ${T.border}`,
              borderRadius: 20, fontSize: 14, outline: "none",
              background: T.bg, color: T.txt,
            }}
            onKeyPress={(e) => {
              if (e.key === "Enter" && !posting) {
                onPostReply(comment.id);
              }
            }}
          />
          <button
            onClick={() => onPostReply(comment.id)}
            disabled={posting || !replyText.trim()}
            style={{
              background: posting || !replyText.trim() ? T.sub : T.pri,
              border: "none", borderRadius: "50%", width: 32, height: 32,
              display: "flex", alignItems: "center", justifyContent: "center",
              cursor: posting || !replyText.trim() ? "not-allowed" : "pointer",
              color: "#000", flexShrink: 0
            }}
          >
            <Send size={14} />
          </button>
        </div>
      )}

      {/* "View replies" toggle — only at top level */}
      {showRepliesToggle && (
        <button
          onClick={() => onToggleReplies(comment.id)}
          style={{
            alignSelf: 'flex-start',
            marginLeft: 48,
            background: 'none', border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '4px 0',
            color: T.sub, fontSize: 12, fontWeight: 600,
          }}
        >
          <span style={{
            display: 'inline-block', width: 24, height: 1,
            background: T.sub, opacity: 0.5,
          }} />
          {isExpanded
            ? `Hide ${comment.replies.length} ${comment.replies.length === 1 ? 'reply' : 'replies'}`
            : `View ${comment.replies.length} ${comment.replies.length === 1 ? 'reply' : 'replies'}`}
        </button>
      )}

      {/* Recursive Replies — with tree line */}
      {hasReplies && (isReply || isExpanded) && (
        <div style={{
          marginLeft: depth === 0 ? 18 : 14,
          paddingLeft: depth === 0 ? 30 : 20,
          borderLeft: `2px solid ${T.border}`,
          display: "flex", flexDirection: "column", gap: 14,
        }}>
          {comment.replies.map(reply => (
            <CommentItem
              key={reply.id}
              comment={reply}
              T={T}
              user={user}
              onLike={onLike}
              onReply={onReply}
              onReport={onReport}
              replyTo={replyTo}
              replyText={replyText}
              onReplyTextChange={onReplyTextChange}
              onPostReply={onPostReply}
              posting={posting}
              depth={depth + 1}
              expandedReplies={expandedReplies}
              onToggleReplies={onToggleReplies}
              onShowProfile={onShowProfile}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export function ModernCommentSection({ reelId, user, onClose, onCommentPosted, onShowProfile }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [replyTo, setReplyTo] = useState(null);
  const [replyText, setReplyText] = useState("");
  const [loading, setLoading] = useState(true);
  const [posting, setPosting] = useState(false);
  const [expandedReplies, setExpandedReplies] = useState(() => new Set());

  const toggleReplies = (commentId) => {
    setExpandedReplies(prev => {
      const next = new Set(prev);
      if (next.has(commentId)) next.delete(commentId);
      else next.add(commentId);
      return next;
    });
  };

  // Helper: find the top-level ancestor id of a given comment id in the tree
  const findRootId = (list, targetId) => {
    for (const c of list) {
      if (String(c.id) === String(targetId)) return c.id;
      if (c.replies?.length) {
        const found = findRootId(c.replies, targetId);
        if (found !== null) return c.id; // return top-level ancestor
      }
    }
    return null;
  };
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: "", message: "", type: "info" });
  const [reportingComment, setReportingComment] = useState(null);
  const [reportSubmitting, setReportSubmitting] = useState(false);
  const [showGiftModal, setShowGiftModal] = useState(false);
  const [reelUsername, setReelUsername] = useState('');
  const [showMentionSuggestions, setShowMentionSuggestions] = useState(false);
  const [mentionQuery, setMentionQuery] = useState('');
  const [mentionSuggestions, setMentionSuggestions] = useState([]);
  const inputRef = useRef(null);

  // Mention autocomplete
  useEffect(() => {
    const match = newComment.match(/@(\w*)$/);
    if (match) {
      const query = match[1];
      setMentionQuery(query);
      setShowMentionSuggestions(true);
      if (query.length >= 2) {
        api.search(query).then(d => {
          setMentionSuggestions(d?.users?.slice(0, 5) || []);
        }).catch(() => setMentionSuggestions([]));
      } else {
        setMentionSuggestions([]);
      }
    } else {
      setShowMentionSuggestions(false);
      setMentionQuery('');
      setMentionSuggestions([]);
    }
  }, [newComment]);

  const COMMENT_REPORT_REASONS = [
    { id: 'spam', label: 'Spam or Misleading', icon: '⚠️' },
    { id: 'harassment', label: 'Harassment or Bullying', icon: '😡' },
    { id: 'hate_speech', label: 'Hate Speech', icon: '🚫' },
    { id: 'inappropriate', label: 'Inappropriate Content', icon: '😢' },
    { id: 'other', label: 'Other', icon: '📋' },
  ];

  const handleReportComment = async (commentId, reportType) => {
    setReportingComment(null);
    if (!user) {
      setAlertModal({ isOpen: true, title: 'Sign In Required', message: 'Please sign in to report comments.', type: 'info' });
      return;
    }
    setReportSubmitting(true);
    try {
      await api.request('/reports/create/', {
        method: 'POST',
        body: JSON.stringify({
          reported_comment_id: commentId,
          report_type: reportType,
          description: `Comment reported as: ${reportType}`,
          target_type: 'comment',
        }),
      });
      setAlertModal({ isOpen: true, title: 'Report Submitted', message: 'Thank you. Our team will review this comment.', type: 'success' });
    } catch (err) {
      setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to submit report. Please try again.', type: 'error' });
    } finally {
      setReportSubmitting(false);
    }
  };

  useEffect(() => {
    fetchComments();
    // Fetch reel data to get username for gift modal
    api.request(`/reels/${reelId}/`)
      .then(d => {
        setReelUsername(d.user?.username || '');
      })
      .catch(() => {});
  }, [reelId]);

  const fetchComments = async () => {
    try {
      setLoading(true);
      // Use the direct reels endpoint which is often faster and better indexed
      const data = await api.request(`/reels/${reelId}/comments/?include_replies=true&depth=10`);
      const raw = Array.isArray(data) ? data : (data?.results || []);
      setComments(buildCommentTree(raw));
    } catch (error) {
      console.error("Failed to fetch comments:", error);
    } finally {
      setLoading(false);
    }
  };

  const handlePostComment = async () => {
    if (!newComment.trim()) return;
    
    try {
      setPosting(true);
      const comment = await api.postComment(reelId, newComment);
      setComments([comment, ...comments]);
      setNewComment("");
      onCommentPosted?.(comment);
    } catch (error) {
      console.error("Failed to post comment:", error);
      setAlertModal({
        isOpen: true,
        title: "Error",
        message: "Failed to post comment",
        type: "error"
      });
    } finally {
      setPosting(false);
    }
  };

  const handleLikeComment = async (commentId, isReply = false) => {
    try {
      const response = isReply 
        ? await api.likeReply(commentId)
        : await api.likeComment(commentId);
      
      if (isReply) {
        // Update reply likes (handle nested replies recursively)
        const updateDeep = (list) => list.map(c => {
          const updatedReplies = c.replies?.map(r => {
            if (String(r.id) === String(commentId)) {
              return { ...r, is_liked: response.liked, likes_count: response.likes_count };
            }
            // Recursively update nested replies
            if (r.replies && r.replies.length) {
              return { ...r, replies: updateDeep(r.replies) };
            }
            return r;
          }) || [];
          return { ...c, replies: updatedReplies };
        });
        setComments(updateDeep(comments));
      } else {
        // Update comment likes
        setComments(comments.map(c => 
          c.id === commentId 
            ? { ...c, is_liked: response.liked, likes_count: response.likes_count }
            : c
        ));
      }
    } catch (error) {
      console.error("Failed to like comment/reply:", error);
    }
  };

  const handlePostReply = async (commentId) => {
    if (!replyText.trim()) return;
    
    try {
      setPosting(true);
      const reply = await api.replyToComment(commentId, replyText);
      if (reply && !reply.replies) reply.replies = [];
      const updateDeep = (list) => list.map(c => {
        if (String(c.id) === String(commentId)) {
          return { ...c, replies: [...(c.replies || []), reply], replies_count: (c.replies_count || 0) + 1 };
        }
        if (c.replies && c.replies.length) {
          return { ...c, replies: updateDeep(c.replies) };
        }
        return c;
      });
      setComments(prev => {
        const updated = updateDeep(prev);
        // Auto-expand the top-level ancestor so the new reply is visible
        const rootId = findRootId(updated, commentId);
        if (rootId != null) {
          setExpandedReplies(p => {
            const next = new Set(p);
            next.add(rootId);
            return next;
          });
        }
        return updated;
      });
      setReplyText("");
      setReplyTo(null);
    } catch (error) {
      console.error("Failed to post reply:", error);
      setAlertModal({
        isOpen: true,
        title: "Error",
        message: "Failed to post reply",
        type: "error"
      });
    } finally {
      setPosting(false);
    }
  };

  const handleSelectMention = (username) => {
    const match = newComment.match(/@(\w*)$/);
    if (match) {
      const newText = newComment.replace(/@\w*$/, `@${username} `);
      setNewComment(newText);
      setShowMentionSuggestions(false);
      setMentionQuery('');
      setMentionSuggestions([]);
    }
  };

  return (
    <>
      <div
        className="modern-comment-overlay"
        style={{
          position: "fixed",
          top: 0,
          left: window.innerWidth <= 1024 ? 0 : 260,
          right: 0,
          bottom: 0,
          background: "rgba(0,0,0,0.7)",
          display: "flex",
          alignItems: "flex-end",
          justifyContent: "center",
          zIndex: 4000,
        }}
        onClick={onClose}
      >
        <div
          className="modern-comment-modal"
          onClick={(e) => e.stopPropagation()}
          style={{
            width: "100%",
            maxWidth: 600,
            background: T.cardBg || '#1A1A1A',
            borderRadius: "20px 20px 0 0",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden",
          }}
        >
        {/* Header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.txt }}>
            Comments ({comments.length})
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: 8,
              display: "flex",
              color: T.txt,
            }}
          >
            <X size={24} />
          </button>
        </div>

        {/* Comments List */}
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px 20px",
          minHeight: 0,
          WebkitOverflowScrolling: "touch",
        }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: 40, color: T.sub }}>
              <Loader size={32} style={{ animation: "spin 1s linear infinite" }} />
            </div>
          ) : comments.length === 0 ? (
            <div style={{ textAlign: "center", padding: 40, color: T.sub }}>
              <MessageCircle size={48} style={{ margin: "0 auto 12px", opacity: 0.3 }} />
              <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>No comments yet</div>
              <div style={{ fontSize: 13 }}>Be the first to comment!</div>
            </div>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {comments.map(comment => (
                <CommentItem
                  key={comment.id}
                  comment={comment}
                  T={T}
                  user={user}
                  onLike={handleLikeComment}
                  onReply={(c) => {
                    setReplyTo(replyTo === c.id ? null : c.id);
                    // Auto-expand the top-level ancestor so user sees existing replies + input
                    const rootId = findRootId(comments, c.id);
                    if (rootId != null) {
                      setExpandedReplies(prev => {
                        const next = new Set(prev);
                        next.add(rootId);
                        return next;
                      });
                    }
                  }}
                  onReport={setReportingComment}
                  replyTo={replyTo}
                  replyText={replyText}
                  onReplyTextChange={setReplyText}
                  onPostReply={handlePostReply}
                  posting={posting}
                  expandedReplies={expandedReplies}
                  onToggleReplies={toggleReplies}
                  onShowProfile={onShowProfile}
                />
              ))}
            </div>
          )}
        </div>

        {/* Input - always visible at bottom */}
        <div style={{
          flexShrink: 0,
          padding: "12px 16px",
          paddingBottom: "calc(12px + env(safe-area-inset-bottom, 20px))",
          borderTop: `1px solid ${T.border}`,
          display: "flex",
          gap: 10,
          alignItems: "center",
          background: T.cardBg || '#1A1A1A',
          boxSizing: "border-box",
          width: "100%",
          position: 'relative',
        }}>
          <div style={{
            width: 36,
            height: 36,
            borderRadius: "50%",
            background: T.pri + "30",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 16,
            flexShrink: 0,
          }}>
            👤
          </div>
          <input
            ref={inputRef}
            type="text"
            value={newComment}
            onChange={(e) => setNewComment(e.target.value)}
            placeholder="Add a comment..."
            style={{
              flex: 1,
              padding: "10px 14px",
              border: `1px solid ${T.border}`,
              borderRadius: 22,
              fontSize: 16,
              outline: "none",
              boxSizing: "border-box",
              minWidth: 0,
            }}
            onKeyPress={(e) => {
              if (e.key === "Enter" && !posting) {
                handlePostComment();
              }
            }}
          />
          <button
            type="button"
            onClick={() => { inputRef.current?.focus(); setNewComment(prev => prev + '@'); }}
            style={{
              background: "none",
              border: "none",
              borderRadius: "50%",
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              color: "#F9E08B",
              flexShrink: 0,
              zIndex: 10,
            }}
          >
            <AtSign size={18} />
          </button>
          <button
            type="button"
            onClick={() => setShowGiftModal(true)}
            style={{
              background: "none",
              border: "none",
              borderRadius: "50%",
              width: 36,
              height: 36,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: "pointer",
              color: "#F9E08B",
              flexShrink: 0,
              zIndex: 10,
            }}
          >
            <Gift size={18} />
          </button>
          <button
            onClick={handlePostComment}
            disabled={posting || !newComment.trim()}
            style={{
              background: posting || !newComment.trim() ? T.sub : T.pri,
              border: "none",
              borderRadius: "50%",
              width: 38,
              height: 38,
              minWidth: 38,
              minHeight: 38,
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              cursor: posting || !newComment.trim() ? "not-allowed" : "pointer",
              color: "#fff",
              flexShrink: 0,
              zIndex: 10,
            }}
          >
            {posting ? <Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> : <Send size={18} />}
          </button>
        </div>

        {/* Mention Suggestions Dropdown */}
        {showMentionSuggestions && mentionSuggestions.length > 0 && (
          <div style={{
            position: 'absolute',
            bottom: 'calc(100% + 8px)',
            left: 16,
            right: 16,
            background: T.cardBg || '#1A1A1A',
            borderRadius: 12,
            border: `1px solid ${T.border || '#333'}`,
            maxHeight: 200,
            overflowY: 'auto',
            zIndex: 100,
            boxShadow: '0 4px 20px rgba(0,0,0,0.4)',
          }}>
            {mentionSuggestions.map(u => (
              <button
                key={u.id}
                onClick={() => handleSelectMention(u.username)}
                style={{
                  width: '100%',
                  padding: '10px 14px',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  color: T.txt || '#fff',
                  fontSize: 14,
                  transition: 'background 0.15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = (T.border || '#333')}
                onMouseLeave={e => e.currentTarget.style.background = 'none'}
              >
                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: T.pri + '30',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  {u.profile_photo ? (
                    <img src={mediaUrl(u.profile_photo)} alt="" style={{ width: '100%', height: '100%', borderRadius: '50%', objectFit: 'cover' }} />
                  ) : '👤'}
                </div>
                <span style={{ fontWeight: 600 }}>@{u.username}</span>
              </button>
            ))}
          </div>
        )}
      </div>

      <AlertModal
        isOpen={alertModal.isOpen}
        onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
      />

      {/* Comment Report Reason Picker */}
      {reportingComment && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", zIndex: 5000, display: "flex", alignItems: "flex-end", justifyContent: "center" }}
          onClick={() => setReportingComment(null)}
        >
          <div
            style={{ width: "100%", maxWidth: 600, background: T.cardBg || '#1A1A1A', borderRadius: "20px 20px 0 0", padding: "20px 20px 32px", boxSizing: "border-box" }}
            onClick={e => e.stopPropagation()}
          >
            <div style={{ width: 36, height: 4, background: T.border || '#333', borderRadius: 4, margin: "0 auto 16px" }} />
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
              <Flag size={18} color="#EF4444" />
              <span style={{ fontSize: 17, fontWeight: 700, color: T.txt || '#fff' }}>Report Comment</span>
            </div>
            <p style={{ fontSize: 13, color: T.sub || '#999', marginBottom: 16 }}>Why are you reporting this comment?</p>
            <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
              {COMMENT_REPORT_REASONS.map(r => (
                <button key={r.id} onClick={() => handleReportComment(reportingComment, r.id)} disabled={reportSubmitting}
                  style={{ padding: "13px 16px", border: `1px solid ${T.border || '#333'}`, borderRadius: 10, background: T.cardBg || '#1A1A1A', cursor: "pointer", display: "flex", alignItems: "center", gap: 12, fontSize: 14, color: T.txt || '#fff', fontWeight: 500, textAlign: "left", transition: "background 0.15s" }}
                  onMouseEnter={e => e.currentTarget.style.background = (T.border || '#333')}
                  onMouseLeave={e => e.currentTarget.style.background = (T.cardBg || '#1A1A1A')}
                >
                  <span style={{ fontSize: 18 }}>{r.icon}</span>
                  {r.label}
                </button>
              ))}
            </div>
            <button onClick={() => setReportingComment(null)}
              style={{ marginTop: 12, width: "100%", padding: 12, border: "none", borderRadius: 10, background: T.border || '#333', cursor: "pointer", fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Gift Modal */}
      {showGiftModal && (
        <GiftPage
          username={reelUsername}
          onClose={() => setShowGiftModal(false)}
          onShowWallet={() => setShowGiftModal(false)}
        />
      )}
    </div>
    </>
  );
}




