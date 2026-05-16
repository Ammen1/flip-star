import { useState, useEffect } from "react";
import { ChevronLeft, UserPlus, UserCheck } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import config from "../config";

export function FollowersListPage({ user, userId, type = "followers", onBack, onUserClick }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [followingStates, setFollowingStates] = useState({});
  const [mutualUsers, setMutualUsers] = useState(new Set());

  useEffect(() => {
    if (user && userId) {
      fetchUsers();
    } else {
      setLoading(false);
      setUsers([]);
    }
  }, [userId, type, user]);

  const fetchUsers = async () => {
    if (!user || !userId) {
      setUsers([]);
      return;
    }
    try {
      setLoading(true);
      const raw = type === "followers" 
        ? await api.getFollowers(userId)
        : await api.getFollowing(userId);
      
      const data = Array.isArray(raw) ? raw : (raw.results || []);
      
      // Initialize following states
      const states = {};
      const mutual = new Set();
      
      data.forEach(item => {
        const userItem = type === "followers" ? item.follower : item.following;
        states[userItem.id] = userItem.is_following || false;
        
        // Check if this user is mutual (both current user and profile user follow each other)
        if (userItem.id === user?.id) {
          mutual.add(userItem.id);
        }
      });
      
      setFollowingStates(states);
      setMutualUsers(mutual);
      
      // Sort users: current user first, then mutual users, then others
      const sortedData = [...data].sort((a, b) => {
        const userA = type === "followers" ? a.follower : a.following;
        const userB = type === "followers" ? b.follower : b.following;
        
        // Current user first
        if (userA.id === user?.id) return -1;
        if (userB.id === user?.id) return 1;
        
        // Then mutual users
        if (mutual.has(userA.id) && !mutual.has(userB.id)) return -1;
        if (!mutual.has(userA.id) && mutual.has(userB.id)) return 1;
        
        return 0;
      });
      
      setUsers(sortedData);
    } catch (error) {
      console.error("Failed to fetch users:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleFollowToggle = async (targetUserId) => {
    try {
      const response = await api.toggleFollow(targetUserId);
      setFollowingStates(prev => ({
        ...prev,
        [targetUserId]: response.following
      }));
    } catch (error) {
      console.error("Failed to toggle follow:", error);
    }
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "#fff",
      overflowY: "auto",
      zIndex: 200,
    }}>
      {/* Header */}
      <div style={{
        position: "sticky",
        top: 0,
        background: "#fff",
        borderBottom: `1px solid ${T.border}`,
        padding: "12px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        zIndex: 10,
      }}>
        <button
          onClick={onBack}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 8,
            display: "flex",
            alignItems: "center",
            color: T.txt,
          }}
        >
          <ChevronLeft size={24} />
        </button>
        <div style={{ flex: 1, fontSize: 18, fontWeight: 700, color: T.txt }}>
          {type === "followers" ? "Followers" : "Following"}
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: "0" }}>
        {loading ? (
          <div style={{ padding: 40, textAlign: "center", color: T.sub }}>
            Loading...
          </div>
        ) : users.length === 0 ? (
          <div style={{ padding: 40, textAlign: "center", color: T.sub }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>👥</div>
            <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>
              No {type} yet
            </div>
            <div style={{ fontSize: 13 }}>
              {type === "followers" ? "No one is following this user yet" : "Not following anyone yet"}
            </div>
          </div>
        ) : (
          <div>
            {users.map(item => {
              const user = type === "followers" ? item.follower : item.following;
              const isFollowing = followingStates[user.id];
              
              return (
                <div
                  key={user.id}
                  style={{
                    padding: "12px 20px",
                    borderBottom: `1px solid ${T.border}`,
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                  }}
                >
                  <button
                    onClick={() => onUserClick?.(user)}
                    style={{
                      flex: 1,
                      display: "flex",
                      alignItems: "center",
                      gap: 12,
                      background: "none",
                      border: "none",
                      cursor: "pointer",
                      textAlign: "left",
                      padding: 0,
                    }}
                  >
                    {user.profile_photo ? (
                      <img
                        src={user.profile_photo.startsWith('http') ? user.profile_photo : `${config.API_BASE_URL.replace('/api', '')}${user.profile_photo}`}
                        alt={user.username}
                        style={{
                          width: 48,
                          height: 48,
                          borderRadius: "50%",
                          objectFit: "cover",
                          flexShrink: 0,
                          border: `1px solid ${T.border}`,
                        }}
                        onError={(e) => {
                          e.target.style.display = 'none';
                          e.target.nextSibling.style.display = 'flex';
                        }}
                      />
                    ) : null}
                    <div style={{
                      width: 48,
                      height: 48,
                      borderRadius: "50%",
                      background: T.pri + "30",
                      display: user.profile_photo ? "none" : "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontSize: 20,
                      flexShrink: 0,
                    }}>
                      👤
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ 
                        fontSize: 15, 
                        fontWeight: 700, 
                        color: T.txt,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                        display: "flex",
                        alignItems: "center",
                        gap: 6,
                      }}>
                        {user.username}
                        {user.id === user?.id && (
                          <span style={{
                            fontSize: 10,
                            background: T.pri,
                            color: "#fff",
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                          }}>
                            You
                          </span>
                        )}
                        {mutualUsers.has(user.id) && user.id !== user?.id && (
                          <span style={{
                            fontSize: 10,
                            background: T.pri + "20",
                            color: T.pri,
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                          }}>
                            Mutual
                          </span>
                        )}
                      </div>
                      <div style={{ 
                        fontSize: 13, 
                        color: T.sub,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap"
                      }}>
                        {user.first_name} {user.last_name}
                      </div>
                      <div style={{ fontSize: 12, color: T.sub }}>
                        {user.followers_count} followers
                      </div>
                    </div>
                  </button>
                  <button
                    onClick={() => handleFollowToggle(user.id)}
                    style={{
                      padding: "8px 16px",
                      border: isFollowing ? `1px solid ${T.border}` : "none",
                      background: isFollowing ? "#fff" : T.pri,
                      borderRadius: 8,
                      cursor: "pointer",
                      fontSize: 13,
                      fontWeight: 700,
                      color: isFollowing ? T.txt : "#fff",
                      flexShrink: 0,
                      display: "flex",
                      alignItems: "center",
                      gap: 6,
                      transition: "all 0.2s",
                    }}
                  >
                    {isFollowing ? <UserCheck size={16} /> : <UserPlus size={16} />}
                    {isFollowing ? "Following" : "Follow"}
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}




