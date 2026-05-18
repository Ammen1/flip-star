import { useState, useEffect, useRef } from 'react';
import {
  Home,
  Compass,
  Plus,
  PlusSquare,
  MessageCircle,
  User,
  Bell,
  Settings,
  Trophy,
  LogOut,
  Film,
} from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';
import config from '../config';

export function AppShell({
  user,
  activeTab,
  onTabChange,
  onLogout,
  onShowProfile,
  onShowPostPage,
  onShowSettings,
  onShowNotifications,
  onShowCampaigns,
  onShowExplorer,
  onRequireAuth,
  unreadNotifCount = 0,
  unreadDmCount = 0,
  children,
}) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 1024);

  useEffect(() => {
    const handleResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // All nav items (sidebar uses full list; mobile bottom uses subset)
  const menuItems = [
    { id: 'home',          icon: Home,         label: 'Home' },
    { id: 'reels',         icon: Film,         label: 'Reels' },
    {
      id: 'campaigns',
      icon: Trophy,
      label: 'Campaigns',
      action: onShowCampaigns,
    },
    {
      id: 'notifications',
      icon: Bell,
      label: t('notifications'),
      action: onShowNotifications,
    },
    { id: 'messages',      icon: MessageCircle, label: t('messages') },
    {
      id: 'create',
      icon: PlusSquare,
      label: t('create'),
      action: onShowPostPage,
    },
    { id: 'profile',  icon: User,    label: t('profile'), action: onShowProfile },
    {
      id: 'settings',
      icon: Settings,
      label: t('settings'),
      action: onShowSettings,
    },
  ];

  // Mobile bottom-bar: Home | Reels | [+] | Messages | Profile
  const MOBILE_BOTTOM_TABS = [
    { item: menuItems[0], label: 'Home',     iconName: 'home' },
    { item: menuItems[1], label: 'Reels',    iconName: 'discover' },
    { item: menuItems[5], label: '',         isCreate: true },
    { item: menuItems[4], label: 'Messages', iconName: 'message', badge: unreadDmCount },
    { item: menuItems[6], label: 'Profile',  iconName: 'profile' },
  ];

  const handleItemClick = (item) => {
    // If tapping the already-active feed tab (no special action), scroll to top + refresh
    const feedTabs = ['home', 'reels', 'messages', 'following', 'bookmarks'];
    if (item.id === activeTab && feedTabs.includes(item.id) && !item.action) {
      window.dispatchEvent(new CustomEvent('tabReselected', { detail: { tab: item.id } }));
      return;
    }
    // Check auth for messages
    if (item.id === 'messages' && !user) {
      onRequireAuth?.();
      return;
    }
    onTabChange?.(item.id);
    if (item.action) {
      item.action();
    }
  };

  // ─── Mobile: swipe left/right to switch bottom-nav tabs (TikTok-style) ──────
  const MOBILE_TAB_ORDER = ['home', 'reels', 'notifications', 'profile'];
  const swipeStart = useRef({ x: 0, y: 0, t: 0, active: false });
  const handleMainTouchStart = (e) => {
    if (!isMobile) return;
    const t0 = e.touches[0];
    // Ignore swipes that start on common interactive controls so we don't hijack
    // carousels, sliders, or horizontal pickers.
    const tag = (e.target?.tagName || '').toLowerCase();
    if (tag === 'input' || tag === 'textarea' || tag === 'select') {
      swipeStart.current.active = false;
      return;
    }
    swipeStart.current = { x: t0.clientX, y: t0.clientY, t: Date.now(), active: true };
  };
  const handleMainTouchEnd = (e) => {
    if (!isMobile || !swipeStart.current.active) return;
    const t1 = e.changedTouches[0];
    const dx = t1.clientX - swipeStart.current.x;
    const dy = t1.clientY - swipeStart.current.y;
    const dt = Date.now() - swipeStart.current.t;
    swipeStart.current.active = false;

    // Must be a fast, clearly horizontal flick:
    //  - horizontal distance > 70px
    //  - horizontal is at least 1.8x vertical (so vertical scrolling & pull-to-refresh win)
    //  - gesture completes in under 600ms
    const absX = Math.abs(dx);
    const absY = Math.abs(dy);
    if (absX < 70 || absX < absY * 1.8 || dt > 600) return;

    // Find where we are in the tab order. Map common aliases back onto the
    // canonical tab id used by the bottom bar.
    const aliasMap = { foryou: 'home', feed: 'home' };
    const current = aliasMap[activeTab] || activeTab;
    const idx = MOBILE_TAB_ORDER.indexOf(current);
    if (idx === -1) return; // current page isn't one of the swipeable tabs

    const nextIdx = dx < 0 ? idx + 1 : idx - 1; // swipe left = next, right = prev
    if (nextIdx < 0 || nextIdx >= MOBILE_TAB_ORDER.length) return;
    const target = menuItems.find((m) => m.id === MOBILE_TAB_ORDER[nextIdx]);
    if (target) handleItemClick(target);
  };

  return (
    <div
      style={{
        display: 'flex',
        height: '100dvh',
        width: '100%',
        background: T.bg,
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      <style>{`
        @media (max-width: 1024px) {
          .appshell-desktop-sidebar {
            display: none !important;
          }
        }
        @media (min-width: 1025px) {
          .appshell-mobile-nav {
            display: none !important;
          }
        }
        .appshell-main::-webkit-scrollbar { display: none; }
        .appshell-main { -ms-overflow-style: none; scrollbar-width: none; }
        .mob-nav-btn svg { color: #8fc441 !important; }
        .mob-nav-btn span { color: #8fc441 !important; }
        .mob-nav-gold svg { color: #8fc441 !important; filter: drop-shadow(0 0 6px #8fc441); }
        .mob-nav-gold span { color: #8fc441 !important; text-shadow: 0 0 8px #8fc441; }
        .mob-nav-btn:hover svg { filter: drop-shadow(0 0 8px #8fc441); transform: scale(1.15); transition: all 0.2s; }
        .mob-nav-btn:hover span { text-shadow: 0 0 8px #8fc441; transition: all 0.2s; }
        .mob-nav-btn { transition: all 0.2s; }
      `}</style>
      {/* 1. Desktop Sidebar */}
      {!isMobile && (
        <aside
          className="appshell-desktop-sidebar"
          style={{
            width: 260,
            borderRight: `1px solid ${T.border}`,
            background: T.cardBg,
            display: 'flex',
            flexDirection: 'column',
            padding: '24px 12px',
            zIndex: 100,
          }}
        >
          <nav
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              gap: 4,
            }}
          >
            {/* Logo above home menu */}
            <div style={{
              padding: '8px 16px',
              marginBottom: 8,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <img
                src="/static/images/flipstar-logo.png"
                alt="FlipStar"
                style={{
                  height: 80,
                  width: 'auto',
                  objectFit: 'contain',
                  display: 'block',
                }}
                onError={(e) => {
                  console.error('Flipstar logo failed to load');
                  e.target.style.display = 'none';
                }}
                onLoad={() => console.log('Flipstar logo loaded successfully')}
              />
            </div>

            {menuItems.map((item) => {
              const Icon = item.icon;
              const isActive = activeTab === item.id;
              const isBell = item.id === 'notifications';
              const isMsg = item.id === 'messages';
              const badgeCount = isBell ? unreadNotifCount : (isMsg ? unreadDmCount : 0);
              return (
                <button
                  key={item.id}
                  onClick={() => handleItemClick(item)}
                  className={isActive ? 'sidebar-nav-gold' : ''}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: '12px 16px',
                    border: 'none',
                    background: isActive ? `${T.priFallback || '#E2B355'}18` : 'transparent',
                    borderRadius: 12,
                    cursor: 'pointer',
                    color: isActive ? (T.priFallback || '#E2B355') : T.txt,
                    fontWeight: isActive ? 700 : 500,
                    transition: 'all 0.2s',
                    position: 'relative',
                    WebkitTapHighlightColor: 'transparent',
                    outline: 'none',
                  }}
                >
                  <div style={{ position: 'relative', display: 'flex', alignItems: 'center' }}>
                    <Icon size={22} strokeWidth={isActive ? 2.5 : 2} />
                    {(isBell || isMsg) && badgeCount > 0 && (
                      <div style={{
                        position: 'absolute',
                        top: -5,
                        right: -6,
                        minWidth: 16,
                        height: 16,
                        borderRadius: 8,
                        background: '#EF4444',
                        color: '#fff',
                        fontSize: 9,
                        fontWeight: 800,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        padding: '0 3px',
                        boxSizing: 'border-box',
                        border: '1.5px solid #fff',
                        lineHeight: 1,
                      }}>
                        {badgeCount > 99 ? '99+' : badgeCount}
                      </div>
                    )}
                  </div>
                  <span style={isActive ? {
                    background: 'linear-gradient(to bottom, #8fc441 0%, #b5dd8f 50%, #6ba835 100%)',
                    WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent',
                    backgroundClip: 'text',
                  } : {}}>{item.label}</span>
                </button>
              );
            })}
          </nav>

          {user && (
            <div
              style={{
                marginTop: 'auto',
                padding: '16px',
                borderTop: `1px solid ${T.border}`,
              }}
            >
              {/* Profile image + name */}
              <button
                onClick={onShowProfile}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '8px',
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  borderRadius: 10,
                  marginBottom: 8,
                  textAlign: 'left',
                }}
                onMouseEnter={e => e.currentTarget.style.background = T.bg}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                {user.profile_photo ? (
                  <img
                    src={user.profile_photo.startsWith('http') ? user.profile_photo : `${config.API_BASE_URL.replace('/api', '')}${user.profile_photo}`}
                    alt={user.username}
                    style={{ width: 36, height: 36, borderRadius: '50%', objectFit: 'cover', flexShrink: 0 }}
                  />
                ) : (
                  <div style={{
                    width: 36, height: 36, borderRadius: '50%',
                    background: T.pri + '30',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: 18, flexShrink: 0,
                  }}>
                    👤
                  </div>
                )}
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 13, fontWeight: 700, color: T.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {user.username}
                  </div>
                  <div style={{ fontSize: 11, color: T.sub }}>
                    @{user.username}
                  </div>
                </div>
              </button>
              {/* Logout */}
              <button
                onClick={onLogout}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 10,
                  width: '100%',
                  padding: '10px 12px',
                  border: 'none',
                  background: 'transparent',
                  color: T.sub,
                  cursor: 'pointer',
                  borderRadius: 8,
                  fontSize: 13,
                  fontWeight: 500,
                }}
                onMouseEnter={e => e.currentTarget.style.background = T.bg}
                onMouseLeave={e => e.currentTarget.style.background = 'transparent'}
              >
                <LogOut size={18} />
                <span>{t('logout')}</span>
              </button>
            </div>
          )}
        </aside>
      )}


      {/* 3. Main Content Area */}
      <main
        className="appshell-main"
        onTouchStart={handleMainTouchStart}
        onTouchEnd={handleMainTouchEnd}
        style={{
          flex: 1,
          position: 'relative',
          height: isMobile ? '100dvh' : '100%',
          overflowY: 'auto',
          paddingBottom: isMobile ? 70 : 0,
          paddingTop: isMobile ? 0 : 0,
          boxSizing: 'border-box',
          WebkitOverflowScrolling: 'touch',
          overscrollBehaviorY: 'contain',
        }}
      >
                {children}
      </main>

      {/* 4. Mobile Bottom Navigation — matches React Native AppNavigator exactly */}
      {isMobile && (
        <nav
          style={{
            position: 'fixed',
            bottom: 0, left: 0, right: 0,
            height: 60,
            background: (T.cardBg && T.cardBg !== '#fff' && T.cardBg !== '#FFF' && T.cardBg !== '#FFFFFF')
              ? T.cardBg + 'f7'
              : 'rgba(13,13,13,0.97)',
            backdropFilter: 'blur(20px)',
            WebkitBackdropFilter: 'blur(20px)',
            borderTop: `1px solid ${T.border}`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-around',
            zIndex: 1000,
            paddingBottom: 'env(safe-area-inset-bottom, 4px)',
            boxSizing: 'border-box',
            boxShadow: '0 -2px 16px rgba(0,0,0,0.07)',
            overflow: 'visible',
          }}
        >
          {MOBILE_BOTTOM_TABS.map(({ item, label, isCreate, badge }) => {
            const { id, icon: Icon } = item;
            const isActive = activeTab === id;
            const badgeCount = badge || 0;
            return (
              <button
                key={id}
                onClick={() => handleItemClick(item)}
                className={`mob-nav-btn ${isActive ? 'mob-nav-gold' : ''}`}
                style={{
                  flex: 1,
                  height: '100%',
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: isCreate ? 'flex-start' : 'center',
                  gap: 2,
                  padding: isCreate ? '0 8px' : '4px 8px',
                  position: 'relative',
                  WebkitTapHighlightColor: 'transparent !important',
                  outline: 'none',
                  overflow: 'visible',
                  paddingTop: isCreate ? 0 : 4,
                }}
              >
                {/* Icon */}
                {isCreate ? (
                  <div style={{
                    position: 'absolute',
                    top: -18,
                    left: '50%',
                    transform: 'translateX(-50%)',
                    width: 54,
                    height: 54,
                    borderRadius: '50%',
                    background: 'linear-gradient(145deg, #8fc441 0%, #6ba835 100%)',
                    boxShadow: '0 4px 18px rgba(143,196,65,0.5), 0 2px 6px rgba(0,0,0,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0,
                    border: '3px solid rgba(255,255,255,0.15)',
                  }}>
                    <Plus size={26} strokeWidth={2.8} color='#1A0A00' />
                  </div>
                ) : (
                  <div style={{
                    position: 'relative',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <Icon
                      size={24}
                      strokeWidth={1.8}
                      color='#8fc441'
                      fill='none'
                    />
                    {badgeCount > 0 && (
                      <div style={{
                        position: 'absolute', top: -4, right: -6,
                        minWidth: 15, height: 15, borderRadius: 8,
                        background: '#EF4444', color: '#fff',
                        fontSize: 8, fontWeight: 800,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        padding: '0 3px', boxSizing: 'border-box',
                        border: '1.5px solid #fff', lineHeight: 1,
                      }}>
                        {badgeCount > 99 ? '99+' : badgeCount}
                      </div>
                    )}
                  </div>
                )}

                {/* Label */}
                {isCreate ? (
                  <span style={{
                    fontSize: 10,
                    fontWeight: 500,
                    color: '#F9E08B',
                    lineHeight: 1,
                    marginTop: 'auto',
                    paddingBottom: 4,
                  }}>Create</span>
                ) : label ? (
                  <span
                    style={{
                      fontSize: 10,
                      fontWeight: isActive ? 700 : 400,
                      color: '#F9E08B',
                      lineHeight: 1,
                    }}>{label}</span>
                ) : null}
              </button>
            );
          })}
        </nav>
)}

    </div>
  );
}




