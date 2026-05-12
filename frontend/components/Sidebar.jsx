import { useState, useEffect } from "react";
import { Menu, X } from "lucide-react";
import { useLegacyT } from "../contexts/ThemeContext";

export function Sidebar({ activeTab, onTabChange, user, onLogout, onRequireAuth, onShowPostPage }) {
  const T = useLegacyT();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 1024);
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  const menuItems = [
    { id: "feed", icon: "🏠", label: "For You" },
    { id: "following", icon: "👥", label: "Following" },
    { id: "explore", icon: "🔍", label: "Explore" },
    { id: "likes", icon: "❤️", label: "Likes" },
    { id: "bookmarks", icon: "🔖", label: "Bookmarks" },
  ];

  const handleMenuClick = (itemId) => {
    onTabChange(itemId);
    setMenuOpen(false);
  };

  return (
    <>
      {/* Mobile Header with Hamburger */}
      {isMobile && (
        <header style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          height: 56,
          background: "#fff",
          borderBottom: `1px solid ${T.border}`,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          padding: "0 16px",
          zIndex: 1000,
        }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: T.pri }}>⭐ Selfie Star</div>
          <button
            onClick={() => setMenuOpen(true)}
            style={{
              background: "transparent",
              border: "none",
              cursor: "pointer",
              padding: 8,
            }}
          >
            <Menu size={24} color={T.txt} />
          </button>
        </header>
      )}

      {/* Mobile Drawer Menu */}
      {isMobile && menuOpen && (
        <>
          <div
            onClick={() => setMenuOpen(false)}
            style={{
              position: "fixed",
              top: 0,
              left: 0,
              right: 0,
              bottom: 0,
              background: "rgba(0,0,0,0.5)",
              zIndex: 1001,
            }}
          />
          <div style={{
            position: "fixed",
            top: 0,
            left: 0,
            bottom: 0,
            width: 280,
            background: "#fff",
            zIndex: 1002,
            display: "flex",
            flexDirection: "column",
          }}>
            {/* Drawer Header */}
            <div style={{
              padding: "16px",
              borderBottom: `1px solid ${T.border}`,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
            }}>
              <div style={{ fontSize: 20, fontWeight: 800, color: T.pri }}>⭐ Selfie Star</div>
              <button
                onClick={() => setMenuOpen(false)}
                style={{
                  background: "transparent",
                  border: "none",
                  cursor: "pointer",
                  padding: 4,
                }}
              >
                <X size={24} color={T.txt} />
              </button>
            </div>

            {/* Menu Items */}
            <div style={{ flex: 1, padding: "12px 0" }}>
              {menuItems.map(item => (
                <button
                  key={item.id}
                  onClick={() => handleMenuClick(item.id)}
                  style={{
                    width: "100%",
                    padding: "14px 16px",
                    background: activeTab === item.id ? T.pri + "15" : "transparent",
                    border: "none",
                    borderLeft: activeTab === item.id ? `4px solid ${T.pri}` : "4px solid transparent",
                    cursor: "pointer",
                    textAlign: "left",
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    fontSize: 16,
                    color: T.txt,
                  }}
                >
                  <span style={{ fontSize: 20 }}>{item.icon}</span>
                  <span style={{ fontWeight: activeTab === item.id ? 700 : 500 }}>{item.label}</span>
                </button>
              ))}
            </div>

            {/* Post Button */}
            <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.border}` }}>
              <button
                onClick={() => {
                  if (!user) {
                    onRequireAuth();
                  } else {
                    onShowPostPage();
                  }
                  setMenuOpen(false);
                }}
                style={{
                  width: "100%",
                  padding: "14px",
                  background: T.pri,
                  border: "none",
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 16,
                  fontWeight: 700,
                  cursor: "pointer",
                }}
              >
                📹 Post
              </button>
            </div>

            {/* User Info */}
            {user && (
              <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.border}` }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                  <div style={{
                    width: 40,
                    height: 40,
                    borderRadius: "50%",
                    background: T.pri + "30",
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "center",
                    fontSize: 20,
                  }}>
                    👤
                  </div>
                  <div>
                    <div style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>{user?.name}</div>
                    <div style={{ fontSize: 12, color: T.sub }}>{user?.email}</div>
                  </div>
                </div>
                <button
                  onClick={onLogout}
                  style={{
                    width: "100%",
                    padding: "10px",
                    background: "#FEE2E2",
                    border: "none",
                    borderRadius: 6,
                    color: "#EF4444",
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: "pointer",
                  }}
                >
                  Logout
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {/* Desktop Sidebar - Hidden on Mobile */}
      {!isMobile && (
        <div style={{
          width: 280,
          background: "#fff",
          borderRight: `1px solid ${T.border}`,
          display: "flex",
          flexDirection: "column",
          height: "100vh",
          overflowY: "auto",
          position: "fixed",
          left: 0,
          top: 0,
        }}>
          {/* Logo */}
          <div style={{ padding: "20px 16px", borderBottom: `1px solid ${T.border}` }}>
            <div style={{ fontSize: 28, fontWeight: 900, color: T.pri }}>⭐</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: T.txt, marginTop: 4 }}>Selfie Star</div>
          </div>

          {/* Main Menu */}
          <div style={{ flex: 1, padding: "12px 0", overflowY: "auto" }}>
            {menuItems.map(item => (
              <button
                key={item.id}
                onClick={() => onTabChange(item.id)}
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  background: activeTab === item.id ? T.pri + "15" : "transparent",
                  border: "none",
                  borderLeft: activeTab === item.id ? `4px solid ${T.pri}` : "4px solid transparent",
                  cursor: "pointer",
                  textAlign: "left",
                  transition: "all .2s",
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                }}
              >
                <div style={{ fontSize: 24 }}>{item.icon}</div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: T.txt }}>{item.label}</div>
                </div>
              </button>
            ))}
          </div>

          {/* Upload Button */}
          <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.border}` }}>
            <button
              onClick={() => {
                if (!user) {
                  onRequireAuth();
                } else {
                  onShowPostPage();
                }
              }}
              style={{
                width: "100%",
                padding: "12px",
                background: `linear-gradient(135deg, ${T.pri}, #B8821E)`,
                border: "none",
                borderRadius: 8,
                color: "#fff",
                fontSize: 15,
                fontWeight: 700,
                cursor: "pointer",
                marginBottom: 12,
              }}
            >
              📹 Post
            </button>
          </div>

          {/* User Profile */}
          {user && (
            <div style={{ padding: "12px 16px", borderTop: `1px solid ${T.border}` }}>
              <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: "50%",
                  background: T.pri + "30",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 20,
                }}>
                  👤
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.txt }}>{user?.name}</div>
                  <div style={{ fontSize: 11, color: T.sub }}>{user?.email}</div>
                </div>
              </div>
              <button
                onClick={onLogout}
                style={{
                  width: "100%",
                  padding: "10px",
                  background: "#FEE2E2",
                  border: "none",
                  borderRadius: 6,
                  color: "#EF4444",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Logout
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}




