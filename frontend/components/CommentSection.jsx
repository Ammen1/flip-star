import { useState, useEffect } from "react";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

export function CommentSection({ reelId, user, onClose, onCommentPosted }) {
  const T = useLegacyT();
  const [comments, setComments] = useState([]);
  const [newComment, setNewComment] = useState("");
  const [loading, setLoading] = useState(false);
  const [postingComment, setPostingComment] = useState(false);

  const fetchComments = async () => {
    try {
      setLoading(true);
      const data = await api.getComments(reelId);
      setComments(data);
    } catch (error) {
      console.error("Failed to fetch comments:", error);
    } finally {
      setLoading(false);
    }
  };

  const postComment = async () => {
    if (!newComment.trim() || !user) return;

    try {
      setPostingComment(true);
      const response = await api.postComment(reelId, newComment);
      
      // Add the new comment to the list
      setComments(prev => [response, ...prev]);
      setNewComment("");
      
      // Notify parent component that a comment was posted
      if (onCommentPosted) {
        onCommentPosted(response);
      }
    } catch (error) {
      console.error("Failed to post comment:", error);
      alert("Failed to post comment. Please try again.");
    } finally {
      setPostingComment(false);
    }
  };

  // Load comments when component mounts
  useEffect(() => {
    fetchComments();
  }, [reelId]);

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "rgba(0,0,0,0.8)",
      display: "flex",
      alignItems: "flex-end",
      zIndex: 5000,
    }}>
      <div style={{
        width: "100%",
        maxWidth: 600,
        height: "85vh",
        background: T.cardBg,
        borderTopLeftRadius: 20,
        borderTopRightRadius: 20,
        display: "flex",
        flexDirection: "column",
        margin: "0 auto",
      }}>
        {/* Header */}
        <div style={{
          padding: "16px 20px",
          borderBottom: `1px solid ${T.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
        }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.txt }}>
            Comments
          </div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 24,
              cursor: "pointer",
              color: T.sub,
            }}
          >
            ×
          </button>
        </div>

        {/* Comments List */}
        <div style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px 20px",
        }}>
          {loading ? (
            <div style={{ textAlign: "center", padding: "20px", color: T.sub }}>
              Loading comments...
            </div>
          ) : comments.length === 0 ? (
            <div style={{ textAlign: "center", padding: "20px", color: T.sub }}>
              No comments yet. Be the first to comment!
            </div>
          ) : (
            comments.map(comment => (
              <div key={comment.id} style={{
                display: "flex",
                gap: 12,
                marginBottom: 16,
              }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background: T.pri + "20",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 20,
                  flexShrink: 0,
                }}>
                  👤
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: T.txt,
                    marginBottom: 4,
                  }}>
                    {comment.user?.username || "Anonymous"}
                  </div>
                  <div style={{
                    fontSize: 14,
                    color: T.txt,
                    lineHeight: 1.4,
                  }}>
                    {comment.text}
                  </div>
                  <div style={{
                    fontSize: 12,
                    color: T.sub,
                    marginTop: 4,
                  }}>
                    {new Date(comment.created_at).toLocaleString()}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Comment Input */}
        {user ? (
          <div style={{
            padding: "12px 20px 8px 20px",
            borderTop: `1px solid ${T.border}`,
            display: "flex",
            gap: 12,
          }}>
            <div style={{
              width: 40,
              height: 40,
              borderRadius: "50%",
              background: T.pri + "20",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 20,
              flexShrink: 0,
            }}>
              👤
            </div>
            <div style={{ flex: 1 }}>
              <input
                type="text"
                placeholder="Add a comment..."
                value={newComment}
                onChange={(e) => setNewComment(e.target.value)}
                onKeyPress={(e) => e.key === 'Enter' && postComment()}
                style={{
                  width: "100%",
                  padding: "10px 12px",
                  border: `1px solid ${T.border}`,
                  borderRadius: 20,
                  fontSize: 14,
                  outline: "none",
                  background: T.bg,
                  color: T.txt,
                }}
              />
            </div>
            <button
              onClick={postComment}
              disabled={!newComment.trim() || postingComment}
              style={{
                background: newComment.trim() && !postingComment ? T.pri : T.sub + "40",
                border: "none",
                borderRadius: 20,
                color: newComment.trim() && !postingComment ? "#fff" : T.sub,
                padding: "8px 16px",
                fontSize: 14,
                fontWeight: 600,
                cursor: newComment.trim() && !postingComment ? "pointer" : "not-allowed",
              }}
            >
              {postingComment ? "Posting..." : "Post"}
            </button>
          </div>
        ) : (
          <div style={{
            padding: "16px 20px",
            borderTop: `1px solid ${T.border}`,
            textAlign: "center",
            color: T.sub,
          }}>
            Please login to comment
          </div>
        )}
      </div>
    </div>
  );
}




