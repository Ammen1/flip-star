import { useState, useEffect, useRef } from "react";
import { UserPlus, UserCheck, X } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";

const BACKEND = api.config?.baseURL?.replace('/api', '') || '';
function mediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return BACKEND + url;
}

export function HorizontalUserSuggestions({ onUserClick, onDismiss }) {
  const { colors: T } = useTheme();
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [followingStates, setFollowingStates] = useState({});
  const scrollRef = useRef(null);

  useEffect(() => {
    fetchSuggestions();
  }, []);

  const fetchSuggestions = async () => {
    try {
      setLoading(true);
      const raw = await api.getUserSuggestions();
      const all = Array.isArray(raw) ? raw : (raw.results || []);
      // Filter out staff and already followed if needed, but the API usually handles this
      const data = all.filter(u => !u.is_staff && !u.is_superuser).slice(0, 10);
      setSuggestions(data);
      
      const states = {};
      data.forEach(user => {
        states[user.id] = user.is_following || false;
      });
      setFollowingStates(states);
    } catch (error) {
      console.error("Failed to fetch suggestions:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleFollowToggle = async (e, userId) => {
    e.stopPropagation();
    try {
      const response = await api.toggleFollow(userId);
      setFollowingStates(prev => ({
        ...prev,
        [userId]: response.following
      }));
    } catch (error) {
      console.error("Failed to toggle follow:", error);
    }
  };

  if (loading || suggestions.length === 0) return null;

  return (
    <div style={{ 
      margin: '8px 0 24px',
      background: T.cardBg || '#fff',
      borderTop: `1px solid ${T.border}30`,
      borderBottom: `1px solid ${T.border}30`,
      padding: '16px 0',
      position: 'relative',
      overflow: 'hidden'
    }}>
      <div style={{ 
        display: 'flex', 
        justifyContent: 'space-between', 
        alignItems: 'center', 
        padding: '0 16px',
        marginBottom: 12 
      }}>
        <span style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>Suggested for you</span>
        <button 
          onClick={onDismiss}
          style={{ background: 'none', border: 'none', padding: 4, cursor: 'pointer', color: T.sub }}
        >
          <X size={16} />
        </button>
      </div>

      <div 
        ref={scrollRef}
        style={{ 
          display: 'flex', 
          gap: 12, 
          overflowX: 'auto', 
          padding: '0 16px',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          WebkitOverflowScrolling: 'touch'
        }}
      >
        {suggestions.map(user => {
          const isFollowing = followingStates[user.id];
          const avatar = user.profile_photo ? mediaUrl(user.profile_photo) : null;

          return (
            <div
              key={user.id}
              onClick={() => onUserClick?.(user.id)}
              style={{
                width: 150,
                minWidth: 150,
                background: T.cardBg || '#1A1A1A',
                border: '1.5px solid rgba(226,179,85,0.35)',
                borderRadius: 12,
                padding: '16px 12px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                textAlign: 'center',
                position: 'relative',
                cursor: 'pointer',
                transition: 'transform 0.1s'
              }}
              onMouseDown={e => e.currentTarget.style.transform = 'scale(0.98)'}
              onMouseUp={e => e.currentTarget.style.transform = 'scale(1)'}
            >
              <div style={{
                width: 70,
                height: 70,
                minWidth: 70,
                minHeight: 70,
                borderRadius: '50%',
                background: T.pri + '20',
                marginBottom: 10,
                overflow: 'hidden',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: `2px solid ${T.cardBg}`
              }}>
                {avatar ? (
                  <img src={avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                ) : (
                  <span style={{ fontSize: 24 }}>👤</span>
                )}
              </div>
              
              <div style={{ 
                fontSize: 13, 
                fontWeight: 700, 
                color: T.txt,
                maxWidth: '100%',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                marginBottom: 2
              }}>
                {user.username}
              </div>
              
              <div style={{ 
                fontSize: 11, 
                color: T.sub,
                marginBottom: 12,
                maxWidth: '100%',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap'
              }}>
                {user.first_name ? `${user.first_name} ${user.last_name || ''}` : 'Suggested for you'}
              </div>

              <button
                onClick={(e) => handleFollowToggle(e, user.id)}
                style={{
                  width: '100%',
                  padding: '7px 0',
                  borderRadius: 8,
                  border: 'none',
                  background: isFollowing ? 'rgba(249,224,139,0.15)' : '#F9E08B',
                  border: `1.5px solid ${isFollowing ? 'rgba(249,224,139,0.6)' : 'transparent'}`,
                  color: isFollowing ? '#F9E08B' : '#000',
                  fontSize: 12,
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 4,
                  transition: 'background 0.2s'
                }}
              >
                {isFollowing ? <UserCheck size={14} /> : <UserPlus size={14} />}
                {isFollowing ? "Following" : "Follow"}
              </button>
            </div>
          );
        })}
      </div>
      <style>{`
        div::-webkit-scrollbar { display: none; }
      `}</style>
    </div>
  );
}




