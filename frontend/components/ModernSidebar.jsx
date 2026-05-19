import { Home, Search, Compass, Film, MessageCircle, Heart, PlusSquare, User, Menu, Trophy, Bell, Settings } from "lucide-react";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import config from "../config";

export function ModernSidebar({ user, activeTab, onTabChange, onShowPostPage, onLogout, onShowProfile, onShowSettings, onShowCampaigns, onShowNotifications, onRequireAuth }) {
  const { colors: T, glassEnabled } = useTheme();
  const { t } = useLanguage();
  const menuItems = [
    { id: "home", icon: Home, label: t('home') },
    { id: "explore", icon: Compass, label: t('explore') },
    { id: "messages", icon: MessageCircle, label: t('messages') },
    { id: "notifications", icon: Bell, label: t('notifications') },
    { id: "create", icon: PlusSquare, label: t('create') },
    { id: "profile", icon: User, label: t('profile') },
    { id: "campaigns", icon: Trophy, label: t('campaigns') },
    { id: "settings", icon: Settings, label: t('settings') },
  ];

  const handleItemClick = (itemId) => {
    if (itemId === "create") {
      onShowPostPage?.();
    } else if (itemId === "profile") {
      onShowProfile?.();
    } else if (itemId === "settings") {
      onShowSettings?.();
    } else if (itemId === "campaigns") {
      onShowCampaigns?.();
    } else if (itemId === "notifications") {
      onShowNotifications?.();
    } else if (itemId === "messages") {
      if (!user) {
        onRequireAuth?.();
        return;
      }
      onTabChange?.(itemId);
    } else {
      onTabChange?.(itemId);
    }
  };

  return (
    <>
      {/* Desktop Sidebar */}
      <div
        className={`modern-desktop-sidebar ${glassEnabled ? 'glass-sidebar' : ''}`}
        style={{
          width: 240,
          height: "100vh",
          position: "fixed",
          left: 0,
          top: 0,
          background: T.cardBg,
          borderRight: `1px solid ${T.border}`,
          display: "flex",
          flexDirection: "column",
          padding: "20px 12px",
          zIndex: 100,
        }}
      >
        {/* Logo */}
        <div style={{
          padding: "12px 16px",
          marginBottom: 20,
          display: "flex",
          alignItems: "center",
          gap: 10,
        }}>
          <img src="/static/images/logoG.png" alt="FlipStar" style={{ width: '100%', height: 80, objectFit: 'contain', flexShrink: 0 }} />
          <div style={{
            fontSize: 18,
            fontWeight: 900,
            background: `linear-gradient(135deg, ${T.pri}, ${T.dark})`,
            WebkitBackgroundClip: "text",
            WebkitTextFillColor: "transparent",
            backgroundClip: "text",
          }}>
            FlipStar
          </div>
        </div>

        {/* Menu Items */}
        <nav style={{ flex: 1, display: "flex", flexDirection: "column", gap: 2, overflowY: "auto", paddingRight: 4 }}>
          {menuItems.map(item => {
            const Icon = item.icon;
            const isActive = activeTab === item.id;
            
            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "10px 14px",
                  border: "none",
                  background: isActive ? T.bg : "transparent",
                  borderRadius: 10,
                  cursor: "pointer",
                  transition: "all 0.2s",
                  textAlign: "left",
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = T.bg;
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = "transparent";
                }}
              >
                <Icon 
                  size={20} 
                  strokeWidth={isActive ? 2.5 : 2}
                  color={isActive ? T.pri : T.txt}
                />
                <span style={{
                  fontSize: 14,
                  fontWeight: isActive ? 700 : 500,
                  color: isActive ? T.txt : T.txt,
                }}>
                  {item.label}
                </span>
              </button>
            );
          })}
        </nav>

        {/* User Section */}
        {user && (
          <div style={{
            padding: "10px 14px",
            borderTop: `1px solid ${T.border}`,
            marginTop: "auto",
            flexShrink: 0,
          }}>
            <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 10 }}>
              {user.profile_photo ? (
                <img
                  src={user.profile_photo.startsWith('http') ? user.profile_photo : `${config.API_BASE_URL.replace('/api', '')}${user.profile_photo}`}
                  alt="Profile"
                  style={{
                    width: 32,
                    height: 32,
                    borderRadius: "50%",
                    objectFit: "cover",
                  }}
                />
              ) : (
                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: T.pri + "30",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 16,
                }}>
                  👤
                </div>
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13, fontWeight: 700, color: T.txt, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {user.username}
                </div>
                <div style={{ fontSize: 11, color: T.sub }}>
                  @{user.username}
                </div>
              </div>
            </div>
            <button
              onClick={onLogout}
              style={{
                width: "100%",
                padding: "7px 10px",
                border: `1px solid ${T.border}`,
                background: "transparent",
                borderRadius: 8,
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 600,
                color: T.txt,
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = T.bg;
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = "transparent";
              }}
            >
              {t('logout')}
            </button>
          </div>
        )}
      </div>

      {/* Mobile Bottom Navigation */}
      <div 
        className="modern-mobile-nav"
        style={{
          position: "fixed",
          bottom: 0,
          left: 0,
          right: 0,
          height: 60,
          background: T.cardBg,
          borderTop: `1px solid ${T.border}`,
          display: "none",
          alignItems: "center",
          justifyContent: "space-around",
          padding: "0 20px",
          zIndex: 100,
        }}
      >
        {[menuItems[0], menuItems[1], menuItems[6], menuItems[4], menuItems[7]].map(item => {
          const Icon = item.icon;
          // Handle special cases for active tab detection
          let isActive = activeTab === item.id;
          
          // Handle special cases where activeTab might be different from item.id
          if (item.id === 'home' && (activeTab === 'foryou' || activeTab === 'feed')) {
            isActive = true;
          }
          if (item.id === 'explore' && activeTab === 'explore') {
            isActive = true;
          }
          if (item.id === 'campaigns' && activeTab === 'campaigns') {
            isActive = true;
          }
          if (item.id === 'create' && activeTab === 'create') {
            isActive = true;
          }
          if (item.id === 'settings' && activeTab === 'settings') {
            isActive = true;
          }
          
          return (
            <button
              key={item.id}
              onClick={() => handleItemClick(item.id)}
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                gap: 4,
                border: "none",
                background: "transparent",
                cursor: "pointer",
                padding: 8,
              }}
            >
              <Icon 
                size={24} 
                strokeWidth={isActive ? 2.5 : 2}
                color={isActive ? T.pri : T.txt}
              />
              {isActive && (
                <div style={{
                  width: 4,
                  height: 4,
                  borderRadius: "50%",
                  background: T.pri,
                }}></div>
              )}
            </button>
          );
        })}
      </div>

      <style>{`
        @media (max-width: 1024px) {
          .modern-desktop-sidebar {
            display: none !important;
          }
          .modern-mobile-nav {
            display: flex !important;
          }
        }
        
        @media (min-width: 1025px) {
          .modern-mobile-nav {
            display: none !important;
          }
        }
      `}</style>
    </>
  );
}




