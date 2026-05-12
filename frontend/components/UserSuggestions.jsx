import { useState, useEffect } from "react";
import { UserPlus, UserCheck } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";

export function UserSuggestions({ onUserClick }) {
  const { colors: T } = useTheme();
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [followingStates, setFollowingStates] = useState({});

  useEffect(() => {
    // Only fetch suggestions if user is authenticated
    if (api.hasToken()) {
      fetchSuggestions();
    } else {
      setLoading(false);
    }
  }, []);

  const fetchSuggestions = async () => {
    try {
      setLoading(true);
      const raw = await api.getUserSuggestions();
      const all = Array.isArray(raw) ? raw : (raw.results || []);
      const data = all.filter(u => !u.is_staff && !u.is_superuser);
      setSuggestions(data);
      
      // Initialize following states
      const states = {};
      data.forEach(user => {
        states[user.id] = user.is_following || false;
      });
      setFollowingStates(states);
    } catch (error) {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFollowToggle = async (userId) => {
    try {
      const response = await api.toggleFollow(userId);
      setFollowingStates(prev => ({
        ...prev,
        [userId]: response.following
      }));
      
      // Update the user in suggestions list
      setSuggestions(prev => prev.map(user => 
        user.id === userId 
          ? { ...user, followers_count: user.followers_count + (response.following ? 1 : -1) }
          : user
      ));
    } catch (error) {
      console.error("Failed to toggle follow:", error);
    }
  };

  // All hooks must be called before any returns - use conditional content instead
  let content;
  if (loading) {
    content = (
      <div style={{ padding: 20, textAlign: "center", color: T.sub, fontSize: 13 }}>
        Loading suggestions...
      </div>
    );
  } else if (suggestions.length === 0) {
    content = (
      <div style={{ padding: 20, textAlign: "center", color: T.sub, fontSize: 13 }}>
        No suggestions available
      </div>
    );
  } else {

  return (
    <div style={{ padding: "0 0 20px 0" }}>
      <div style={{ 
        fontSize: 14, 
        fontWeight: 700, 
        color: T.txt, 
        marginBottom: 12,
        padding: "0 20px"
      }}>
        Suggested for you
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "0 20px" }}>
        {suggestions.slice(0, 5).map(user => {
          const isFollowing = followingStates[user.id];
          
          return (
            <div
              key={user.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 10,
              }}
            >
              <button
                onClick={() => onUserClick?.(user)}
                style={{
                  flex: 1,
                  display: "flex",
                  alignItems: "center",
                  gap: 10,
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  textAlign: "left",
                  padding: 0,
                }}
              >
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background: T.pri + "30",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 18,
                  flexShrink: 0,
                }}>
                  👤
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ 
                    fontSize: 13, 
                    fontWeight: 700, 
                    color: T.txt, 
                    overflow: "hidden", 
                    textOverflow: "ellipsis", 
                    whiteSpace: "nowrap" 
                  }}>
                    {user.username}
                  </div>
                  <div style={{ 
                    fontSize: 11, 
                    color: T.sub,
                    overflow: "hidden", 
                    textOverflow: "ellipsis", 
                    whiteSpace: "nowrap" 
                  }}>
                    {user.followers_count} followers
                  </div>
                </div>
              </button>
              <button
                onClick={() => handleFollowToggle(user.id)}
                style={{
                  padding: "6px 12px",
                  border: isFollowing ? `1.5px solid rgba(249,224,139,0.6)` : "none",
                  background: isFollowing ? 'rgba(249,224,139,0.15)' : '#F9E08B',
                  borderRadius: 6,
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: 700,
                  color: isFollowing ? '#F9E08B' : '#000',
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  gap: 4,
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  if (isFollowing) {
                    e.currentTarget.style.background = 'rgba(249,224,139,0.25)';
                  }
                }}
                onMouseLeave={(e) => {
                  if (isFollowing) {
                    e.currentTarget.style.background = 'rgba(249,224,139,0.15)';
                  }
                }}
              >
                {isFollowing ? <UserCheck size={14} /> : <UserPlus size={14} />}
                {isFollowing ? "Following" : "Follow"}
              </button>
            </div>
          );
        })}
      </div>
    </div>
    );
  }

  return content;
}




