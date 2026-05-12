import { useState, useEffect, useRef } from "react";
import { Search, X, User, Hash, Image } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";

export function SearchBar({ onUserClick, onHashtagClick, onPostClick }) {
  const { colors: T } = useTheme();
  const [query, setQuery] = useState("");
  const [results, setResults] = useState({ users: [], posts: [], hashtags: [] });
  const [isOpen, setIsOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const searchRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchRef.current && !searchRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  useEffect(() => {
    const searchTimeout = setTimeout(async () => {
      if (query.trim().length > 0) {
        setLoading(true);
        try {
          const data = await api.search(query);
          setResults(data);
          setIsOpen(true);
        } catch (error) {
          console.error("Search failed:", error);
        } finally {
          setLoading(false);
        }
      } else {
        setResults({ users: [], posts: [], hashtags: [] });
        setIsOpen(false);
      }
    }, 300);

    return () => clearTimeout(searchTimeout);
  }, [query]);

  const handleClear = () => {
    setQuery("");
    setResults({ users: [], posts: [], hashtags: [] });
    setIsOpen(false);
  };

  const hasResults = results.users.length > 0 || results.posts.length > 0 || results.hashtags.length > 0;

  return (
    <div ref={searchRef} style={{ position: "relative", width: "100%" }}>
      <div style={{ position: "relative" }}>
        <Search
          size={18}
          style={{
            position: "absolute",
            left: 12,
            top: "50%",
            transform: "translateY(-50%)",
            color: T.sub,
          }}
        />
        <input
          type="text"
          placeholder="Search users, posts, hashtags..."
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={() => query && setIsOpen(true)}
          style={{
            width: "100%",
            padding: "10px 40px 10px 40px",
            border: `1px solid ${T.border}`,
            borderRadius: 20,
            fontSize: 14,
            outline: "none",
            background: T.bg,
            transition: "all 0.2s",
          }}
        />
        {query && (
          <button
            onClick={handleClear}
            style={{
              position: "absolute",
              right: 12,
              top: "50%",
              transform: "translateY(-50%)",
              background: "none",
              border: "none",
              cursor: "pointer",
              padding: 4,
              display: "flex",
              alignItems: "center",
              color: T.sub,
            }}
          >
            <X size={16} />
          </button>
        )}
      </div>

      {isOpen && hasResults && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 8px)",
          left: 0,
          right: 0,
          background: "#fff",
          borderRadius: 12,
          boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
          maxHeight: 400,
          overflowY: "auto",
          zIndex: 1000,
        }}>
          {results.users.length > 0 && (
            <div style={{ padding: "12px 0" }}>
              <div style={{ padding: "0 16px 8px", fontSize: 12, fontWeight: 700, color: T.sub, display: "flex", alignItems: "center", gap: 6 }}>
                <User size={14} /> Users
              </div>
              {results.users.map(user => (
                <button
                  key={user.id}
                  onClick={() => {
                    onUserClick?.(user);
                    handleClear();
                  }}
                  style={{
                    width: "100%",
                    padding: "10px 16px",
                    border: "none",
                    background: "none",
                    cursor: "pointer",
                    display: "flex",
                    alignItems: "center",
                    gap: 10,
                    textAlign: "left",
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
                  onMouseLeave={(e) => e.currentTarget.style.background = "none"}
                >
                  <div style={{
                    width: 36,
                    height: 36,
                    borderRadius: "50%",
                    background: T.pri + "30",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 16,
                  }}>
                    👤
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: T.txt }}>{user.username}</div>
                    <div style={{ fontSize: 12, color: T.sub }}>
                      {user.followers_count} followers
                    </div>
                  </div>
                </button>
              ))}
            </div>
          )}

          {results.hashtags.length > 0 && (
            <div style={{ padding: "12px 0", borderTop: results.users.length > 0 ? `1px solid ${T.border}` : "none" }}>
              <div style={{ padding: "0 16px 8px", fontSize: 12, fontWeight: 700, color: T.sub, display: "flex", alignItems: "center", gap: 6 }}>
                <Hash size={14} /> Hashtags
              </div>
              {results.hashtags.map((tag, idx) => (
                <button
                  key={idx}
                  onClick={() => {
                    onHashtagClick?.(tag);
                    handleClear();
                  }}
                  style={{
                    width: "100%",
                    padding: "10px 16px",
                    border: "none",
                    background: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    fontSize: 14,
                    color: T.txt,
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
                  onMouseLeave={(e) => e.currentTarget.style.background = "none"}
                >
                  #{tag}
                </button>
              ))}
            </div>
          )}

          {results.posts.length > 0 && (
            <div style={{ padding: "12px 0", borderTop: (results.users.length > 0 || results.hashtags.length > 0) ? `1px solid ${T.border}` : "none" }}>
              <div style={{ padding: "0 16px 8px", fontSize: 12, fontWeight: 700, color: T.sub, display: "flex", alignItems: "center", gap: 6 }}>
                <Image size={14} /> Posts
              </div>
              {results.posts.slice(0, 5).map(post => (
                <button
                  key={post.id}
                  onClick={() => {
                    onPostClick?.(post);
                    handleClear();
                  }}
                  style={{
                    width: "100%",
                    padding: "10px 16px",
                    border: "none",
                    background: "none",
                    cursor: "pointer",
                    textAlign: "left",
                    transition: "background 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
                  onMouseLeave={(e) => e.currentTarget.style.background = "none"}
                >
                  <div style={{ fontSize: 13, color: T.txt, marginBottom: 4 }}>
                    {post.caption.substring(0, 60)}{post.caption.length > 60 ? "..." : ""}
                  </div>
                  <div style={{ fontSize: 11, color: T.sub }}>
                    by @{post.user?.username} • {post.votes} likes
                  </div>
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {loading && isOpen && (
        <div style={{
          position: "absolute",
          top: "calc(100% + 8px)",
          left: 0,
          right: 0,
          background: "#fff",
          borderRadius: 12,
          boxShadow: "0 4px 20px rgba(0,0,0,0.15)",
          padding: 20,
          textAlign: "center",
          color: T.sub,
          fontSize: 13,
        }}>
          Searching...
        </div>
      )}
    </div>
  );
}




