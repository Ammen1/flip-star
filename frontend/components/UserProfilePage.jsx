import { useState } from "react";
import { useLegacyT } from "../contexts/ThemeContext";

export function UserProfilePage({ user, onClose }) {
  const T = useLegacyT();
  const [stats] = useState({
    videos: 24,
    followers: 12500,
    following: 345,
    likes: 156789,
  });

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "rgba(0,0,0,0.7)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      zIndex: 1000,
      overflowY: "auto",
    }}>
      <div style={{
        background: "#fff",
        borderRadius: 16,
        padding: 24,
        maxWidth: 600,
        width: "90%",
        maxHeight: "90vh",
        overflowY: "auto",
      }}>
        {/* Header */}
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 24 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.txt }}>Profile 👤</div>
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
            ✕
          </button>
        </div>

        {/* Profile Header */}
        <div style={{ textAlign: "center", marginBottom: 30 }}>
          <div style={{
            width: 100,
            height: 100,
            borderRadius: "50%",
            background: T.pri + "30",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            fontSize: 50,
            margin: "0 auto 16px",
          }}>
            👤
          </div>
          <div style={{ fontSize: 24, fontWeight: 800, color: T.txt, marginBottom: 4 }}>
            {user?.name || "Creator"}
          </div>
          <div style={{ fontSize: 14, color: T.sub, marginBottom: 4 }}>
            @{user?.email?.split("@")[0] || "creator"}
          </div>
          <div style={{ fontSize: 13, color: T.sub }}>
            {user?.email}
          </div>
        </div>

        {/* Stats Grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(4, 1fr)",
          gap: 12,
          marginBottom: 30,
        }}>
          {[
            { label: "Videos", value: stats.videos, icon: "🎬" },
            { label: "Followers", value: stats.followers.toLocaleString(), icon: "👥" },
            { label: "Following", value: stats.following, icon: "➕" },
            { label: "Likes", value: stats.likes.toLocaleString(), icon: "❤️" },
          ].map((stat, i) => (
            <div key={i} style={{
              background: T.bg,
              borderRadius: 12,
              padding: 16,
              textAlign: "center",
            }}>
              <div style={{ fontSize: 24, marginBottom: 8 }}>{stat.icon}</div>
              <div style={{ fontSize: 18, fontWeight: 800, color: T.txt, marginBottom: 4 }}>
                {stat.value}
              </div>
              <div style={{ fontSize: 11, color: T.sub }}>
                {stat.label}
              </div>
            </div>
          ))}
        </div>

        {/* Profile Info */}
        <div style={{ marginBottom: 30 }}>
          <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 12 }}>
            Account Info
          </div>
          <div style={{
            background: T.bg,
            borderRadius: 12,
            padding: 16,
            display: "flex",
            flexDirection: "column",
            gap: 12,
          }}>
            <div>
              <div style={{ fontSize: 11, color: T.sub, fontWeight: 600, marginBottom: 4 }}>
                PLAN
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>
                {user?.plan || "Free"} Plan
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: T.sub, fontWeight: 600, marginBottom: 4 }}>
                MEMBER SINCE
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>
                March 2026
              </div>
            </div>
            <div>
              <div style={{ fontSize: 11, color: T.sub, fontWeight: 600, marginBottom: 4 }}>
                VERIFICATION
              </div>
              <div style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>
                ✅ Verified
              </div>
            </div>
          </div>
        </div>

        {/* Action Buttons */}
        <div style={{ display: "flex", gap: 12 }}>
          <button
            style={{
              flex: 1,
              padding: 12,
              background: T.bg,
              border: "none",
              borderRadius: 8,
              color: T.txt,
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Edit Profile
          </button>
          <button
            onClick={onClose}
            style={{
              flex: 1,
              padding: 12,
              background: `linear-gradient(135deg, ${T.pri}, #B8821E)`,
              border: "none",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}




