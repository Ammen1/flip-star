import React, { useState, useEffect, useRef, lazy, Suspense, startTransition } from 'react';
import { AppShell } from './components/AppShell';
import { TikTokLayout } from './components/TikTokLayout';
import { useTheme } from './contexts/ThemeContext';
import api from './api';
import webPush from './services/WebPushService';
import { Coins, Gift, X, CheckCircle, XCircle } from 'lucide-react';

// ---------------------------------------------------------------
// Helper Styles for Modal
// ---------------------------------------------------------------

const btnPrimary = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '12px 16px', borderRadius: 12, border: 'none',
  background: T.pri, color: '#000', fontSize: 14, fontWeight: 700,
  cursor: 'pointer',
});

const modalLabel = (T) => ({
  display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6,
});

const modalInput = (T) => ({
  width: '100%', padding: '12px 14px', borderRadius: 10,
  border: `1px solid ${T.border}`, background: T.card, color: T.txt,
  fontSize: 15, outline: 'none', boxSizing: 'border-box',
  cursor: 'text', pointerEvents: 'auto',
});

// ---------------------------------------------------------------
// Modal Components
// ---------------------------------------------------------------

function Modal({ children, onClose, theme: T, title }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.85)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999, padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: T.card || '#1A1A1A', borderRadius: 16, padding: 20,
          maxWidth: 400, width: '100%', maxHeight: '80vh', overflowY: 'auto',
          border: `1px solid ${T.border || '#333'}`,
          boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700, color: T.txt || '#fff', margin: 0 }}>{title}</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.sub || '#999' }}>
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function EmptyState({ theme: T, icon, title, subtitle }) {
  return (
    <div style={{ textAlign: 'center', padding: '40px 20px', color: T.sub }}>
      <div style={{ marginBottom: 12, opacity: 0.5 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>{title}</div>
      {subtitle && <div style={{ fontSize: 13 }}>{subtitle}</div>}
    </div>
  );
}

function TopUpModal({ theme: T, onClose }) {
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loading, setLoading] = useState(false);
  const [loadingAirtime, setLoadingAirtime] = useState(false);
  const [loadingTelebirr, setLoadingTelebirr] = useState(false);
  const [showResultModal, setShowResultModal] = useState(false);
  const [resultSuccess, setResultSuccess] = useState(false);
  const [resultMessage, setResultMessage] = useState('');

  // Fetch user's phone number when modal opens
  useEffect(() => {
    const fetchPhoneNumber = async () => {
      try {
        const profile = await api.request('/profile/me/');
        if (profile && profile.phone_number) {
          setPhoneNumber(profile.phone_number);
        }
      } catch (error) {
        console.error('[TopUpModal] Failed to fetch phone number:', error);
      }
    };
    fetchPhoneNumber();
  }, []);

  const handleAirtimePurchase = async () => {
    if (!phoneNumber) {
      setResultSuccess(false);
      setResultMessage('Please enter your phone number');
      setShowResultModal(true);
      return;
    }

    setLoadingAirtime(true);
    try {
      const response = await api.request('/charging/coin-purchase/', {
        method: 'POST',
        body: JSON.stringify({
          phone_number: phoneNumber,
        }),
      });

      if (response.success) {
        setResultSuccess(true);
        setResultMessage(response.message);
        setShowResultModal(true);
        setTimeout(() => {
          onClose();
        }, 2000);
      } else {
        setResultSuccess(false);
        setResultMessage(response.message || 'Purchase failed');
        setShowResultModal(true);
      }
    } catch (error) {
      console.error('airtime coin purchase error:', error);
      setResultSuccess(false);
      setResultMessage('Purchase failed. Please try again.');
      setShowResultModal(true);
    } finally {
      setLoadingAirtime(false);
    }
  };

  const handleTelebirrPurchase = async () => {
    if (!phoneNumber) {
      setResultSuccess(false);
      setResultMessage('Please enter your phone number');
      setShowResultModal(true);
      return;
    }

    setLoadingTelebirr(true);
    try {
      const response = await api.request('/wallet/telebirr/initiate/', {
        method: 'POST',
        body: JSON.stringify({
          package_id: 1, // On-demand package ID
          phone_number: phoneNumber,
        }),
      });

      if (response.success && response.payment_url) {
        window.open(response.payment_url, '_blank');
        onClose();
      } else {
        setResultSuccess(false);
        setResultMessage(response.error || 'Payment initiation failed');
        setShowResultModal(true);
      }
    } catch (error) {
      console.error('telebirr payment error:', error);
      setResultSuccess(false);
      setResultMessage('Payment initiation failed. Please try again.');
      setShowResultModal(true);
    } finally {
      setLoadingTelebirr(false);
    }
  };

  return (
    <>
      <Modal onClose={onClose} theme={T} title="Buy Coins">
        <div style={{ textAlign: 'center', marginBottom: 20 }}>
          <div style={{ fontSize: 32, fontWeight: 700, color: T.txt, marginBottom: 8 }}>
            100 Coins
          </div>
          <div style={{ fontSize: 16, color: T.sub }}>
            for 10 ETB
          </div>
        </div>

        <div style={{ marginBottom: 20 }}>
          <label style={{ ...modalLabel(T), marginBottom: 8 }}>Phone Number</label>
          <input
            type="tel"
            value={phoneNumber}
            readOnly
            disabled
            placeholder="+251 9xx xxx xxx"
            style={{
              ...modalInput(T),
              background: (T.card || '#1A1A1A'),
              color: (T.txt || '#fff'),
              border: `1px solid ${T.border || '#444'}`,
              opacity: 0.85,
              cursor: 'not-allowed',
            }}
          />
          <div style={{ fontSize: 11, color: T.sub || '#888', marginTop: 6 }}>
            Charges go to your registered phone number.
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
          <button
            onClick={handleAirtimePurchase}
            disabled={loadingAirtime || loadingTelebirr}
            style={{
              ...btnPrimary(T),
              opacity: loadingAirtime || loadingTelebirr ? 0.5 : 1,
              background: T.pri,
              color: '#000',
              border: 'none',
            }}
          >
            {loadingAirtime ? 'Processing...' : 'From Airtime'}
          </button>
          <button
            onClick={handleTelebirrPurchase}
            disabled={loadingAirtime || loadingTelebirr}
            style={{
              ...btnPrimary(T),
              opacity: loadingAirtime || loadingTelebirr ? 0.5 : 1,
              background: T.pri,
              color: '#000',
              border: 'none',
            }}
          >
            {loadingTelebirr ? 'Processing...' : 'From Telebirr'}
          </button>
        </div>
      </Modal>

      {showResultModal && (
        <Modal onClose={() => setShowResultModal(false)} theme={T} title={resultSuccess ? 'Success' : 'Error'}>
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <div style={{
              width: 60, height: 60, borderRadius: '50%',
              background: resultSuccess ? '#10B981' : '#EF4444',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              margin: '0 auto 16px',
            }}>
              {resultSuccess ? (
                <CheckCircle size={32} color="#fff" />
              ) : (
                <XCircle size={32} color="#fff" />
              )}
            </div>
            <p style={{ fontSize: 16, color: T.txt, margin: 0 }}>
              {resultMessage}
            </p>
          </div>
        </Modal>
      )}
    </>
  );
}

// Lazy load ALL non-critical components for smaller initial bundle
const PhoneLoginModal = lazy(() => import('./components/PhoneLoginModal').then(m => ({ default: m.PhoneLoginModal })));
const SubscriptionRegisterModal = lazy(() => import('./components/SubscriptionRegisterModal').then(m => ({ default: m.SubscriptionRegisterModal })));
const LandingPage = lazy(() => import('./components/LandingPage').then(m => ({ default: m.LandingPage })));
const EnhancedPostPage = lazy(() => import('./components/EnhancedPostPage').then(m => ({ default: m.EnhancedPostPage })));
const ProfilePage = lazy(() => import('./components/ProfilePage').then(m => ({ default: m.ProfilePage })));
const EditProfilePage = lazy(() => import('./components/EditProfilePage').then(m => ({ default: m.EditProfilePage })));
const FollowersListPage = lazy(() => import('./components/FollowersListPage').then(m => ({ default: m.FollowersListPage })));
const SettingsPage = lazy(() => import('./components/SettingsPage').then(m => ({ default: m.SettingsPage })));
const NotificationsPage = lazy(() => import('./components/NotificationsPage').then(m => ({ default: m.NotificationsPage })));
const CampaignsPage = lazy(() => import('./pages/CampaignsPage').then(m => ({ default: m.CampaignsPage })));
const CampaignDetailPage = lazy(() => import('./pages/CampaignDetailPage').then(m => ({ default: m.CampaignDetailPage })));
const CampaignLeaderboard = lazy(() => import('./pages/CampaignLeaderboard'));
const CampaignFeed = lazy(() => import('./pages/CampaignFeed'));
const VideoDetailPage = lazy(() => import('./components/VideoDetailPage').then(m => ({ default: m.VideoDetailPage })));
const MessagesPage = lazy(() => import('./components/MessagesPage').then(m => ({ default: m.MessagesPage })));
const ExplorerPage = lazy(() => import('./components/ExplorerPage').then(m => ({ default: m.ExplorerPage })));
const HomePage = lazy(() => import('./components/HomePage').then(m => ({ default: m.HomePage })));
const WalletPage = lazy(() => import('./pages/WalletPage').then(m => ({ default: m.WalletPage })));
const SubscriptionPage = lazy(() => import('./components/SubscriptionPage').then(m => ({ default: m.SubscriptionPage })));
const AdminApp = lazy(() => import('./admin/AdminApp').then(m => ({ default: m.AdminApp })));

// Prefetch critical lazy chunks after initial load for faster navigation
const prefetchComponents = () => {
  // Only prefetch the most commonly used components
  setTimeout(() => {
    import('./components/ProfilePage');
    import('./components/EnhancedPostPage');
    import('./components/ExplorerPage');
    import('./components/HomePage');
  }, 2000); // Wait 2 seconds after initial load
};

// Error boundary for lazy loading failures
class LazyLoadErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null, errorInfo: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, errorInfo) {
    console.error('Lazy loading error:', error, errorInfo);
    this.setState({ errorInfo });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          height: '100vh', background: '#fff', gap: 16,
        }}>
          <div style={{ fontSize: 18, fontWeight: 600, color: '#000' }}>Failed to load page</div>
          <div style={{ fontSize: 14, color: '#666' }}>
            {this.state.error?.message || 'Please refresh the page to try again'}
          </div>
          {this.state.error && (
            <div style={{ fontSize: 12, color: '#999', maxWidth: 400, textAlign: 'center' }}>
              Error: {this.state.error.toString()}
            </div>
          )}
          <button 
            onClick={() => window.location.reload()} 
            style={{ padding: '12px 24px', background: '#000', color: '#fff', border: 'none', borderRadius: 8, cursor: 'pointer', fontSize: 14 }}
          >
            Refresh
          </button>
        </div>
      );
    }

    return this.props.children;
  }
}

// Page skeleton for navigation transitions
function PageSkeleton() {
  return (
    <div style={{
      position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
      background: '#fff', display: 'flex', flexDirection: 'column',
      zIndex: 200,
    }}>
      <div style={{
        padding: '16px 20px', borderBottom: '1px solid #E7E5E4',
        display: 'flex', alignItems: 'center', gap: 16,
      }}>
        <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#f0f0f0' }} />
        <div style={{ width: 120, height: 16, background: '#f0f0f0', borderRadius: 8 }} />
      </div>
      <div style={{ padding: 20, display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
          <div style={{ width: 80, height: 80, borderRadius: '50%', background: '#f5f5f5' }} />
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 8 }}>
            <div style={{ width: '60%', height: 14, background: '#f0f0f0', borderRadius: 7 }} />
            <div style={{ width: '40%', height: 12, background: '#f5f5f5', borderRadius: 6 }} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 20, justifyContent: 'center' }}>
          {[0,1,2].map(i => (
            <div key={i} style={{ textAlign: 'center' }}>
              <div style={{ width: 40, height: 14, background: '#f0f0f0', borderRadius: 7, margin: '0 auto 4px' }} />
              <div style={{ width: 50, height: 10, background: '#f5f5f5', borderRadius: 5, margin: '0 auto' }} />
            </div>
          ))}
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 2, marginTop: 16 }}>
          {[0,1,2,3,4,5].map(i => (
            <div key={i} style={{ aspectRatio: '1', background: '#f5f5f5', borderRadius: 2 }} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function WerqRoot() {
  // Check if accessing admin panel
  if (
    window.location.pathname === '/admin' ||
    window.location.hash === '#/admin'
  ) {
    return (
      <Suspense fallback={<div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>Loading Admin...</div>}>
        <AdminApp />
      </Suspense>
    );
  }

  const [screen, setScreen] = useState('app');
  const { applyFromSettings, colors } = useTheme();

  // Global skeleton removal - ultimate fallback to prevent infinite loading
  useEffect(() => {
    const timeout = setTimeout(() => {
      const skeleton = document.getElementById('app-skeleton');
      if (skeleton) {
        skeleton.style.transition = 'opacity 0.2s ease';
        skeleton.style.opacity = '0';
        setTimeout(() => skeleton.remove(), 220);
      }
    }, 2000); // Remove after 2 seconds regardless of state
    return () => clearTimeout(timeout);
  }, []);

  // In-session keep-alive — pings the cheap /health/ endpoint every 10 min
  // while the tab is focused so the Render free-tier service doesn't sleep
  // mid-session.  Skipped when the tab is hidden so we don't waste requests.
  // (External uptime monitor is still recommended for between-session warmth.)
  useEffect(() => {
    let cancelled = false;
    const ping = () => {
      if (document.hidden) return;
      api.request('/health/', { skipCache: true }).catch(() => {});
    };
    const id = setInterval(() => { if (!cancelled) ping(); }, 10 * 60 * 1000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  // ── Restore auth synchronously so pages never receive user=null on first render
  (() => {
    try {
      const t = localStorage.getItem('authToken');
      if (t) api.setAuthToken(t);
    } catch {}
  })();
  const [authUser, setAuthUser] = useState(() => {
    try {
      const u = localStorage.getItem('user');
      return u ? JSON.parse(u) : null;
    } catch { return null; }
  });

  const [showLogin, setShowLogin] = useState(false);

  // Parse URL params for subscription registration link (sent via Onevas SMS)
  const _urlParams = new URLSearchParams(window.location.search);
  const _isSubTp = _urlParams.get('subscription_tp') === 'true' || _urlParams.get('subscriptiontp') === 'true';
  const _prefillPhone = _urlParams.get('phone') || '';
  const _prefillOtp = _urlParams.get('otp') || '';

  // If arriving via SMS registration link, show register modal (not login)
  const [showSubRegister, setShowSubRegister] = useState(_isSubTp && !authUser);

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    if (params.get('login') === 'true') setShowLogin(true);
  }, []);

  const forceShowLogin = false;

  // ── Restore navigation state from browser history on initial load ──
  // This ensures that refreshing the page maintains the current view
  const _historyState = (() => {
    try {
      const state = window.history.state || {};
      return state;
    } catch { return {}; }
  })();

  // ── Read the saved nav snapshot — ONLY restore the active tab, never overlays ──
  // On first launch (no sessionStorage), always start with 'home', ignore localStorage
  const VALID_TABS = ['home', 'reels', 'messages'];
  const _savedActiveTab = (() => {
    try {
      // Priority: history state > sessionStorage > 'home'
      const raw = _historyState.activeTab
        || JSON.parse(sessionStorage.getItem('_nav') || '{}').activeTab
        || 'home';
      return VALID_TABS.includes(raw) ? raw : 'home';
    } catch { return 'home'; }
  })();

  const [showPostPage, setShowPostPage] = useState(_historyState.showPostPage || false);
  const [showProfile, setShowProfile] = useState(_historyState.showProfile || false);
  const [profileUserId, setProfileUserId] = useState(_historyState.profileUserId || null);
  const [activeTab, setActiveTab] = useState(_savedActiveTab);
  const [showEditProfile, setShowEditProfile] = useState(_historyState.showEditProfile || false);
  const [showFollowersList, setShowFollowersList] = useState(_historyState.showFollowersList || false);
  const [followersListType, setFollowersListType] = useState(_historyState.followersListType || 'followers');
  const [followersListUserId, setFollowersListUserId] = useState(_historyState.followersListUserId || null);
  const [showSettings, setShowSettings] = useState(_historyState.showSettings || false);
  const [showWallet, setShowWallet] = useState(_historyState.showWallet || false);
  const [showSubscription, setShowSubscription] = useState(_historyState.showSubscription || false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);
  const settingsReturnState = useRef(null); // tracks where to go back to when settings closes
  const walletReturnState = useRef(null); // tracks where to go back to when wallet closes
  const walletShowTopUpOnMount = useRef(false); // tracks whether to show top-up modal on wallet mount
  const subscriptionReturnState = useRef(null); // tracks where to go back to when subscription closes
  const prevNavState = useRef(null); // tracks nav state before any overlay page opens
  const [showNotifications, setShowNotifications] = useState(_historyState.showNotifications || false);
  const [showCampaigns, setShowCampaigns] = useState(_historyState.showCampaigns || false);
  const [showCampaignLeaderboard, setShowCampaignLeaderboard] = useState(_historyState.showCampaignLeaderboard || false);
  const [showCampaignFeed, setShowCampaignFeed] = useState(_historyState.showCampaignFeed || false);
  const [showCampaignDetail, setShowCampaignDetail] = useState(_historyState.showCampaignDetail || false);
  const [campaignId, setCampaignId] = useState(_historyState.campaignId || null);

  // ── Parse shared post link (/post/:id or ?post=:id) SYNCHRONOUSLY so the
  //    shared content opens on the very first render — no flash of home/landing.
  const _sharedPostId = (() => {
    try {
      const path = window.location.pathname;
      const m = path.match(/^\/post\/(\d+)/);
      if (m) return parseInt(m[1], 10);
      const params = new URLSearchParams(window.location.search);
      const p = params.get('post');
      if (p && /^\d+$/.test(p)) return parseInt(p, 10);
    } catch {}
    return null;
  })();
  // Don't clean the URL - keep it so user can refresh and still see the post
  // Clean URL only after component mounts to avoid issues
  // if (_sharedPostId) {
  //   try { window.history.replaceState({}, '', '/'); } catch {}
  // }

  const [showVideoDetail, setShowVideoDetail] = useState(!!_sharedPostId);
  const [videoDetailId, setVideoDetailId] = useState(
    _sharedPostId ||
    _historyState.videoDetailId ||
    JSON.parse(sessionStorage.getItem('_nav') || '{}').videoDetailId ||
    null
  );
  const [showExplorer, setShowExplorer] = useState(false);
  const [showForgotPassword, setShowForgotPassword] = useState(false);
  const [unreadNotifCount, setUnreadNotifCount] = useState(0);
  const [unreadDmCount, setUnreadDmCount] = useState(0);
  const [subscriptionStatus, setSubscriptionStatus] = useState(null);
  const [subscriptionChecked, setSubscriptionChecked] = useState(false);

  // Pause all videos when login modal or other overlays are shown
  useEffect(() => {
    const pauseAllVideos = () => {
      const videos = document.querySelectorAll('video');
      videos.forEach(video => {
        if (!video.paused) {
          video.pause();
        }
      });
    };

    if (showLogin || showSubRegister || showSubscription || showWallet || showSettings || showNotifications || showCampaigns || showCampaignDetail || showCampaignLeaderboard || showCampaignFeed || showPostPage || showEditProfile || showFollowersList || showProfile || showVideoDetail || showExplorer || showForgotPassword) {
      pauseAllVideos();
    }
  }, [showLogin, showSubRegister, showSubscription, showWallet, showSettings, showNotifications, showCampaigns, showCampaignDetail, showCampaignLeaderboard, showCampaignFeed, showPostPage, showEditProfile, showFollowersList, showProfile, showVideoDetail, showExplorer, showForgotPassword]);

  // Pause videos when page loses visibility or focus
  useEffect(() => {
    const pauseAllVideos = () => {
      const videos = document.querySelectorAll('video');
      videos.forEach(video => {
        if (!video.paused) {
          video.pause();
        }
      });
    };

    const handleVisibilityChange = () => {
      if (document.hidden) {
        pauseAllVideos();
      }
    };

    const handleBlur = () => {
      pauseAllVideos();
    };

    const handleBeforeUnload = () => {
      pauseAllVideos();
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    window.addEventListener('blur', handleBlur);
    window.addEventListener('beforeunload', handleBeforeUnload);

    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
      window.removeEventListener('blur', handleBlur);
      window.removeEventListener('beforeunload', handleBeforeUnload);
    };
  }, []);

  // Clean URL after component mounts to avoid navigation issues
  useEffect(() => {
    if (_sharedPostId) {
      try { window.history.replaceState({}, '', '/'); } catch {}
    }
  }, [_sharedPostId]);

  // Subscribe to Web Push when the user is logged in. The helper silently
  // no-ops on unsupported browsers / when VAPID keys aren't configured.
  useEffect(() => {
    if (!authUser) return;
    let cancelled = false;
    (async () => {
      try {
        const res = await webPush.ensureSubscribed();
        if (!cancelled && res && !res.ok) {
          console.debug('[WebPush] not subscribed:', res.reason);
        }
      } catch (err) {
        console.warn('[WebPush] subscribe error', err);
      }
    })();
    return () => { cancelled = true; };
  }, [authUser]);

  // Bridge notification clicks from the service worker → SPA deep-link.
  useEffect(() => {
    const off = webPush.onPushClick((data) => {
      try {
        if (data?.reel_id) {
          handleShowVideoDetail(data.reel_id);
        }
      } catch (_) {}
    });
    return off;
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll unread notification count every 60s when user is logged in (reduced for performance)
  useEffect(() => {
    if (!authUser) { setUnreadNotifCount(0); return; }
    const fetchCount = async () => {
      try {
        const data = await api.getUnreadNotificationCount();
        setUnreadNotifCount(data.unread_count || 0);
      } catch (_) {}
    };
    fetchCount();
    const interval = setInterval(fetchCount, 60000); // 60s instead of 30s
    return () => clearInterval(interval);
  }, [authUser]);

  // Poll unread DM count - disabled due to 502 errors
  // useEffect(() => {
  //   if (!authUser) { setUnreadDmCount(0); return; }
  //   const fetchDm = async () => {
  //     try {
  //       const data = await api.request('/messages/unread-count/');
  //       setUnreadDmCount(data?.unread_count || 0);
  //     } catch (_) {}
  //   };
  //   fetchDm();
  //   const interval = setInterval(fetchDm, 30000);
  //   return () => clearInterval(interval);
  // }, [authUser]);

  // Load and apply platform typography settings
  const [typographyLoaded, setTypographyLoaded] = useState(false);
  const [typographyError, setTypographyError] = useState(null);
  const [currentFont, setCurrentFont] = useState('Inter');
  
  // Defer font loading to after initial render to reduce LCP time
  useEffect(() => {
    const loadTypographySettings = async () => {
      try {
        const settings = await api.request('/settings/public/');
        
        if (!settings || !settings.font_family_secondary) {
          setTypographyError('No settings returned from server');
          return;
        }
        
        setCurrentFont(settings.font_family_secondary);
        
        // Load Google Fonts dynamically (after LCP)
        const fonts = [
          settings.font_family_primary,
          settings.font_family_secondary,
          settings.font_family_username,
          settings.font_family_caption,
        ].filter((f, i, arr) => f && arr.indexOf(f) === i);
        
        fonts.forEach(font => {
          if (font && font !== 'Inter') {
            const fontUrl = `https://fonts.googleapis.com/css2?family=${font.replace(/ /g, '+')}:wght@300;400;500;600;700;800;900&display=swap`;
            const link = document.createElement('link');
            link.href = fontUrl;
            link.rel = 'stylesheet';
            if (!document.querySelector(`link[href*="${font.replace(/ /g, '+')}"]`)) {
              document.head.appendChild(link);
            }
          }
        });
        
        // Build CSS with actual values from settings
        const fontPrimary = `"${settings.font_family_primary || 'Inter'}", sans-serif`;
        const fontSecondary = `"${settings.font_family_secondary || 'Inter'}", sans-serif`;
        const fontUsername = `"${settings.font_family_username || 'Inter'}", sans-serif`;
        const fontCaption = `"${settings.font_family_caption || 'Inter'}", sans-serif`;
        const baseFontSize = settings.font_size_base || 16;
        
        // Apply CSS variables
        const root = document.documentElement;
        root.style.setProperty('--font-primary', fontPrimary);
        root.style.setProperty('--font-secondary', fontSecondary);
        root.style.setProperty('--font-username', fontUsername);
        root.style.setProperty('--font-caption', fontCaption);
        root.style.setProperty('--font-size-base', `${baseFontSize}px`);
        root.style.setProperty('--font-weight-headings', settings.font_weight_headings || '700');
        root.style.setProperty('--font-weight-body', settings.font_weight_body || '400');
        root.style.setProperty('--letter-spacing', settings.letter_spacing || 'normal');
        root.style.setProperty('--line-height', settings.line_height || '1.5');
        // Colors managed by ThemeContext — do not override here
        
        // Apply to body
        document.body.style.fontFamily = fontSecondary;
        document.body.style.fontSize = `${baseFontSize}px`;
        document.body.style.lineHeight = settings.line_height || '1.5';
        document.body.style.letterSpacing = settings.letter_spacing || 'normal';
        
        // Inject comprehensive global CSS with !important
        let styleEl = document.getElementById('platform-typography');
        if (!styleEl) {
          styleEl = document.createElement('style');
          styleEl.id = 'platform-typography';
          document.head.appendChild(styleEl);
        }
        
        const css = `
          :root {
            --font-primary: ${fontPrimary};
            --font-secondary: ${fontSecondary};
            --font-username: ${fontUsername};
            --font-caption: ${fontCaption};
            --font-size-base: ${baseFontSize}px;
          }
          
          /* Force font on ALL elements */
          *, *::before, *::after {
            font-family: ${fontSecondary} !important;
          }
          
          /* Headings use primary font with proportional scaling */
          h1, h1 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 2) !important;
          }
          h2, h2 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 1.5) !important;
          }
          h3, h3 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 1.125) !important;
          }
          h4, h4 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 1) !important;
          }
          h5, h5 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 0.875) !important;
          }
          h6, h6 * {
            font-family: ${fontPrimary} !important;
            font-weight: ${settings.font_weight_headings || '700'} !important;
            font-size: calc(var(--font-size-base) * 0.75) !important;
          }
          
          /* Specific overrides for username with proportional scaling */
          .username, .username *,
          [class*="username"], [class*="username"] *,
          .user-name, .user-name *,
          .handle, .handle * {
            font-family: ${fontUsername} !important;
            font-size: calc(var(--font-size-base) * 0.9375) !important;
          }
          
          /* Remove ALL blue tap highlights globally - replace with gold brand color */
          * {
            -webkit-tap-highlight-color: rgba(143,196,65,0.4) !important;
            -webkit-touch-callout: none !important;
            -webkit-user-select: none !important;
            user-select: none !important;
          }
          
          /* Allow text selection for inputs and text areas */
          input, textarea, [contenteditable="true"], .selectable {
            -webkit-user-select: text !important;
            user-select: text !important;
          }
          
          /* Gold active states for all interactive elements */
          button:active, a:active, [role="button"]:active, .clickable:active {
            background-color: rgba(143,196,65,0.25) !important;
            transform: scale(0.96) !important;
            transition: all 0.1s ease !important;
          }
          
          /* Buttons and inputs */
          button, input, textarea, select {
            font-family: ${fontSecondary} !important;
            font-size: calc(var(--font-size-base) * 0.875) !important;
          }
          
          /* Captions with proportional scaling */
          .caption, .caption *,
          .description, .description * {
            font-family: ${fontCaption} !important;
            font-size: calc(var(--font-size-base) * 0.875) !important;
          }
          
          /* Small text (descriptions, secondary content) */
          small, .small, .small * {
            font-size: calc(var(--font-size-base) * 0.875) !important;
          }
          
          /* Extra small text */
          .text-xs, .text-xs * {
            font-size: calc(var(--font-size-base) * 0.75) !important;
          }
        `;
        
        styleEl.textContent = css;
        
        console.log('[Typography] Styles applied successfully');
        console.log('[Typography] Current font:', fontSecondary);
        applyFromSettings(settings);
        setTypographyLoaded(true);
        setTypographyError(null);
      } catch (error) {
        console.error('[Typography] Error loading settings:', error);
        setTypographyError(error.message || 'Failed to load settings');
      }
    };
    
    // Defer loading to avoid blocking initial render. Dedup in api.js means
    // this call is also shared with any other component that reads
    // /settings/public/, so it won't double-fire.
    // Load typography settings promptly to minimize layout shift
    const timer = setTimeout(loadTypographySettings, 100);
    return () => clearTimeout(timer);
  }, []);

  // Browser history support
  useEffect(() => {
    const handlePopState = (event) => {
      const state = event.state || {};
      // Restore state from history
      setShowLogin(state.showLogin || false);
      setShowPostPage(state.showPostPage || false);
      setShowProfile(state.showProfile || false);
      setProfileUserId(state.profileUserId || null);
      setActiveTab(state.activeTab || 'home');
      setShowEditProfile(state.showEditProfile || false);
      setShowFollowersList(state.showFollowersList || false);
      setFollowersListType(state.followersListType || 'followers');
      setFollowersListUserId(state.followersListUserId || null);
      setShowSettings(state.showSettings || false);
      setShowNotifications(state.showNotifications || false);
      setShowCampaigns(state.showCampaigns || false);
      setShowCampaignLeaderboard(state.showCampaignLeaderboard || false);
      setShowCampaignFeed(state.showCampaignFeed || false);
      setShowVideoDetail(state.showVideoDetail || false);
      setVideoDetailId(state.videoDetailId || null);
      setShowExplorer(state.showExplorer || false);
      // Update sessionStorage to match restored state
      saveNav({
        activeTab: state.activeTab || 'home',
        showPostPage: state.showPostPage || false,
        showProfile: state.showProfile || false,
        profileUserId: state.profileUserId || null,
        showSettings: state.showSettings || false,
        showCampaigns: state.showCampaigns || false,
        showExplorer: state.showExplorer || false,
      });
    };

    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Push state to history whenever navigation state changes
  const pushHistoryState = (newState, replace = false) => {
    const state = {
      showLogin: newState.showLogin !== undefined ? newState.showLogin : showLogin,
      showPostPage: newState.showPostPage !== undefined ? newState.showPostPage : showPostPage,
      showProfile: newState.showProfile !== undefined ? newState.showProfile : showProfile,
      profileUserId: newState.profileUserId !== undefined ? newState.profileUserId : profileUserId,
      activeTab: newState.activeTab !== undefined ? newState.activeTab : activeTab,
      showEditProfile: newState.showEditProfile !== undefined ? newState.showEditProfile : showEditProfile,
      showFollowersList: newState.showFollowersList !== undefined ? newState.showFollowersList : showFollowersList,
      followersListType: newState.followersListType !== undefined ? newState.followersListType : followersListType,
      followersListUserId: newState.followersListUserId !== undefined ? newState.followersListUserId : followersListUserId,
      showSettings: newState.showSettings !== undefined ? newState.showSettings : showSettings,
      showNotifications: newState.showNotifications !== undefined ? newState.showNotifications : showNotifications,
      showCampaigns: newState.showCampaigns !== undefined ? newState.showCampaigns : showCampaigns,
      showCampaignLeaderboard: newState.showCampaignLeaderboard !== undefined ? newState.showCampaignLeaderboard : showCampaignLeaderboard,
      showCampaignFeed: newState.showCampaignFeed !== undefined ? newState.showCampaignFeed : showCampaignFeed,
      showCampaignDetail: newState.showCampaignDetail !== undefined ? newState.showCampaignDetail : showCampaignDetail,
      campaignId: newState.campaignId !== undefined ? newState.campaignId : campaignId,
      showVideoDetail: newState.showVideoDetail !== undefined ? newState.showVideoDetail : showVideoDetail,
      videoDetailId: newState.videoDetailId !== undefined ? newState.videoDetailId : videoDetailId,
      showExplorer: newState.showExplorer !== undefined ? newState.showExplorer : showExplorer,
    };
    if (replace) {
      window.history.replaceState(state, '');
    } else {
      window.history.pushState(state, '');
    }
  };

  // Function to reset all special page states
  const resetAllPages = () => {
    setShowPostPage(false);
    setShowProfile(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowSettings(false);
    setShowNotifications(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    setShowExplorer(false);
};

  // ── Save nav snapshot to sessionStorage on every relevant state change ──
  const saveNav = (patch = {}) => {
    const next = {
      activeTab,
      showPostPage,
      showProfile,
      profileUserId,
      showSettings,
      showCampaigns,
      showExplorer,
      // Only save videoDetailId if we're on the reels tab and it was intentionally set
      // This prevents stale video IDs from persisting when navigating away
      ...(activeTab === 'reels' && videoDetailId ? { videoDetailId } : {}),
      ...patch,
    };
    try { sessionStorage.setItem('_nav', JSON.stringify(next)); } catch {}
    if (next.activeTab) { try { localStorage.setItem('_activeTab', next.activeTab); } catch {} }
  };

  // Persist whenever any of these state vars change
  useEffect(() => {
    saveNav();
  }, [activeTab, showPostPage, showProfile, profileUserId, showSettings, showCampaigns, showExplorer, videoDetailId]); // eslint-disable-line

  // Load user from localStorage on mount + prefetch lazy components
  useEffect(() => {
    // Auth is already restored synchronously above.
    // This effect just prefetches lazy chunks.
    // Prefetch lazy components after app is idle
    if ('requestIdleCallback' in window) {
      requestIdleCallback(prefetchComponents);
    } else {
      setTimeout(prefetchComponents, 2000);
    }

  }, []);

  // Refresh user profile from backend on startup to sync across devices
  useEffect(() => {
    const refreshUserProfile = async () => {
      if (!authUser || !api.hasToken()) return;
      
      try {
        // Fetch fresh profile data from backend
        const profileData = await api.request('/profile/me/');
        if (profileData) {
          // /profile/me/ returns { user: {...}, profile_photo, bio, ... }
          const userData = profileData.user || {};
          const updatedUser = {
            id: userData.id || authUser.id,
            username: userData.username || authUser.username,
            email: userData.email || authUser.email,
            first_name: userData.first_name || authUser.first_name || "",
            last_name: userData.last_name || authUser.last_name || "",
            name: userData.first_name || userData.username || authUser.name,
            profile_photo: profileData.profile_photo || userData.profile_photo || null,
            bio: profileData.bio || userData.bio || "",
            followers_count: userData.followers_count || authUser.followers_count || 0,
            following_count: userData.following_count || authUser.following_count || 0,
            is_staff: userData.is_staff || authUser.is_staff || false,
          };
          // Only update if there are actual changes
          if (JSON.stringify(updatedUser) !== JSON.stringify(authUser)) {
            setAuthUser(updatedUser);
            localStorage.setItem('user', JSON.stringify(updatedUser));
            console.log('👤 Profile synced from backend');
          }
        }
      } catch (e) {
        console.log('Could not refresh profile:', e.message);
      }
    };
    
    // Defer to after home page loads to reduce initial fetch time
    // Sync profile after a short delay to avoid blocking LCP
    const timer = setTimeout(refreshUserProfile, 1500);
    return () => clearTimeout(timer);
  }, []); // Run once on mount

  // Check subscription status for authenticated users
  useEffect(() => {
    const checkSubscription = async () => {
      if (!authUser || !api.hasToken()) {
        setSubscriptionStatus(null);
        setSubscriptionChecked(false);
        return;
      }

      try {
        const status = await api.checkSubscriptionStatus();
        setSubscriptionStatus(status);
        setSubscriptionChecked(true);
        
        // If user has no subscription, redirect to subscription page
        if (!status.has_subscription && !showSubscription) {
          console.log('🔒 User has no active subscription, redirecting to subscription page');
          setShowSubscription(true);
        }
      } catch (e) {
        console.log('Could not check subscription status:', e.message);
        setSubscriptionChecked(true);
      }
    };

    // Check subscription status after a short delay
    const timer = setTimeout(checkSubscription, 2000);
    return () => clearTimeout(timer);
  }, [authUser]); // Run when authUser changes

  // Listen for navigate to create post event from campaign modal
  useEffect(() => {
    const handleNavigateToCreatePost = () => {
      setShowPostPage(true);
      setShowProfile(false);
      setShowEditProfile(false);
      setShowFollowersList(false);
      setShowCampaigns(false);
      setShowCampaignDetail(false);
      setShowCampaignLeaderboard(false);
      setShowCampaignFeed(false);
    };
    window.addEventListener('navigateToCreatePost', handleNavigateToCreatePost);

    // Set up global navigation function for post upload
    window.navigateToReels = () => {
      resetAllPages();
      setActiveTab('reels');
      setShowPostPage(false);
    };

    return () => {
      window.removeEventListener(
        'navigateToCreatePost',
        handleNavigateToCreatePost,
      );
      delete window.navigateToReels;
    };
  }, []);

  const handleLogout = () => {
    // Best-effort: drop the browser's push subscription so we stop pushing.
    try { webPush.unsubscribe(); } catch (_) {}
    api.setAuthToken(null);
    localStorage.removeItem('authToken');
    localStorage.removeItem('user');
    setAuthUser(null);
    setShowProfile(false);
    setShowPostPage(false);
    setShowSettings(false);
    setShowNotifications(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setActiveTab('home');
    try { sessionStorage.removeItem('_nav'); localStorage.setItem('_activeTab', 'home'); } catch {}
    setShowLogin(true);
  };

  const handleShowProfile = (userId = null) => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    
    // Profile viewing is allowed for all users (even without subscription)
    // Save current state before navigating (without video detail to avoid showing random videos on back)
    prevNavState.current = { activeTab, showProfile, profileUserId };
    setActiveTab('profile');
    setProfileUserId(userId);
    setShowProfile(true);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowVideoDetail(false);
    setVideoDetailId(null);
    // Push new history entry for profile overlay
    pushHistoryState({ showProfile: true, profileUserId: userId, showPostPage: false, showEditProfile: false, showFollowersList: false, activeTab: 'profile', showVideoDetail: false, videoDetailId: null });
  };

  const handleShowPostPage = () => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    
    // Check subscription status before allowing post creation
    if (subscriptionChecked && !subscriptionStatus?.has_subscription) {
      setShowSubscription(true);
      return;
    }
    
    prevNavState.current = { activeTab, showProfile, profileUserId };
    setActiveTab('create');
    setShowPostPage(true);
    setShowProfile(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    pushHistoryState({ showPostPage: true, showProfile: false, showEditProfile: false, showFollowersList: false });
  };

  const handleClosePostPage = () => { goHome(); };

  const handlePostSuccess = (reelId) => {
    setShowPostPage(false);
    prevNavState.current = null;
    handleShowVideoDetail(reelId);
  };

  const handleShowEditProfile = () => {
    // Save the previous state to return to it later
    prevNavState.current = {
      showSettings: showSettings,
      showProfile: showProfile,
      showPostPage: showPostPage,
      showFollowersList: showFollowersList,
    };
    setShowEditProfile(true);
    setShowProfile(false);
    setShowPostPage(false);
    setShowFollowersList(false);
    setShowSettings(false);
    pushHistoryState({ showEditProfile: true, showProfile: false, showPostPage: false, showFollowersList: false, showSettings: false });
  };

  const handleShowFollowers = (userId, type = 'followers') => {
    setFollowersListUserId(userId);
    setFollowersListType(type);
    setShowFollowersList(true);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowSettings(false);
    pushHistoryState({ showFollowersList: true, followersListUserId: userId, followersListType: type, showProfile: false, showPostPage: false, showEditProfile: false, showSettings: false });
  };

  const handleShowSettings = () => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    // Save current state so X button restores it
    settingsReturnState.current = {
      activeTab,
      showProfile,
      profileUserId,
      showVideoDetail,
      videoDetailId,
    };
    setActiveTab('settings');
    setShowSettings(true);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowNotifications(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    // Push new history entry for settings overlay
    pushHistoryState({ showSettings: true, showProfile: false, showPostPage: false, showEditProfile: false, showFollowersList: false, showNotifications: false, showCampaigns: false, showCampaignDetail: false, showCampaignLeaderboard: false, showCampaignFeed: false, showVideoDetail: false, activeTab: 'settings' });
  };

  const handleShowWallet = () => {
    if (!authUser) { setShowLogin(true); return; }
    // Save the current page so back button can restore it
    walletReturnState.current = {
      showProfile, profileUserId, activeTab,
      showSettings, showNotifications,
    };
    setShowWallet(true);
    setShowSettings(false);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowNotifications(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    pushHistoryState({ showWallet: true });
  };

  const handleShowCoinPurchase = async () => {
    if (!authUser) { setShowLogin(true); return; }
    setShowTopUpModal(true);
  };

  const handleCloseWallet = () => {
    setShowWallet(false);
    walletShowTopUpOnMount.current = false;
    const ret = walletReturnState.current;
    if (ret) {
      walletReturnState.current = null;
      if (ret.showProfile) {
        setShowProfile(true);
        setProfileUserId(ret.profileUserId);
        setActiveTab(ret.activeTab || 'profile');
        pushHistoryState({ showWallet: false, showProfile: true, profileUserId: ret.profileUserId, activeTab: ret.activeTab || 'profile' }, true);
      } else if (ret.showSettings) {
        setShowSettings(true);
        setActiveTab(ret.activeTab || 'settings');
        pushHistoryState({ showWallet: false, showSettings: true, activeTab: ret.activeTab || 'settings' }, true);
      }
    } else {
      pushHistoryState({ showWallet: false }, true);
    }
  };

  const handleShowSubscription = () => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    prevNavState.current = { activeTab, showProfile, profileUserId, showVideoDetail, videoDetailId };
    setActiveTab('subscription');
    setShowSubscription(true);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowSettings(false);
    setShowWallet(false);
    setShowNotifications(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    pushHistoryState({ showSubscription: true, activeTab: 'subscription' });
  };

  const handleCloseSubscription = () => {
    setShowSubscription(false);
    const ret = subscriptionReturnState.current;
    if (ret) {
      subscriptionReturnState.current = null;
      if (ret.showProfile) {
        setShowProfile(true);
        setProfileUserId(ret.profileUserId);
        setActiveTab(ret.activeTab || 'profile');
        pushHistoryState({ showSubscription: false, showProfile: true, profileUserId: ret.profileUserId, activeTab: ret.activeTab || 'profile' }, true);
        return;
      }
      if (ret.showSettings) {
        setShowSettings(true);
        setActiveTab(ret.activeTab || 'settings');
        pushHistoryState({ showSubscription: false, showSettings: true, activeTab: ret.activeTab || 'settings' }, true);
        return;
      }
    }
    pushHistoryState({ showSubscription: false }, true);
  };

  const handleCloseSettings = () => { goHome(); };

  const handleShowCampaigns = () => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    prevNavState.current = { activeTab, showProfile, profileUserId, showVideoDetail, videoDetailId };
    setActiveTab('campaigns');
    setShowCampaigns(true);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowSettings(false);
    setShowNotifications(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    // Push new history entry for campaigns overlay
    pushHistoryState({ showCampaigns: true, showProfile: false, showPostPage: false, showEditProfile: false, showFollowersList: false, showSettings: false, showNotifications: false, showCampaignDetail: false, showCampaignLeaderboard: false, showCampaignFeed: false, showVideoDetail: false, activeTab: 'campaigns' });
  };

  const handleShowNotifications = () => {
    if (!authUser) {
      setShowLogin(true);
      return;
    }
    prevNavState.current = { activeTab, showProfile, profileUserId, showVideoDetail, videoDetailId };
    setActiveTab('notifications');
    setShowNotifications(true);
    setUnreadNotifCount(0);
    setShowProfile(false);
    setShowPostPage(false);
    setShowEditProfile(false);
    setShowFollowersList(false);
    setShowSettings(false);
    setShowCampaigns(false);
    setShowCampaignDetail(false);
    setShowCampaignLeaderboard(false);
    setShowCampaignFeed(false);
    setShowVideoDetail(false);
    // Push new history entry for notifications overlay
    pushHistoryState({ showNotifications: true, showProfile: false, showPostPage: false, showEditProfile: false, showFollowersList: false, showSettings: false, showCampaigns: false, showCampaignDetail: false, showCampaignLeaderboard: false, showCampaignFeed: false, showVideoDetail: false, activeTab: 'notifications' });
  };

  const handleShowVideoDetail = (reelId) => {
    // Save current state before navigating
    prevNavState.current = { activeTab, showProfile, profileUserId };
    resetAllPages();
    // Set videoDetailId BEFORE changing tab to prevent it from being cleared
    console.log('handleShowVideoDetail called with reelId:', reelId);
    setVideoDetailId(reelId);
    startTransition(() => {
      setActiveTab('reels');
      pushHistoryState({
        activeTab: 'reels',
        videoDetailId: reelId,
        showNotifications: false,
        showProfile: false,
        showPostPage: false,
        showSettings: false,
        showCampaigns: false,
        showCampaignDetail: false,
        showCampaignLeaderboard: false,
        showCampaignFeed: false,
        showExplorer: false,
        showVideoDetail: true,
        showEditProfile: false,
        showFollowersList: false,
      });
    });
  };

  const handleShowExplorer = () => {
    // Remember where we came from so Back restores it (was landing on a
    // blank screen because activeTab stayed 'explore' with no matching view).
    prevNavState.current = { activeTab, showProfile, profileUserId };
    resetAllPages();
    startTransition(() => {
      setActiveTab('explore');
      setShowExplorer(true);
      pushHistoryState({ showExplorer: true });
    });
  };

  const handleCloseExplorer = () => {
    setShowExplorer(false);
    const ret = prevNavState.current;
    if (ret) {
      setActiveTab(ret.activeTab || 'home');
      if (ret.showProfile) {
        setShowProfile(true);
        setProfileUserId(ret.profileUserId || null);
      }
      prevNavState.current = null;
    } else {
      setActiveTab('home');
    }
    pushHistoryState({ showExplorer: false });
  };

  const handleProfileSaved = (updatedUser) => {
    setAuthUser(updatedUser);
  };

  const handleRequireAuth = () => {
    setShowLogin(true);
  };

  const goHome = () => {
    resetAllPages();
    prevNavState.current = null;
    setActiveTab('home');
    pushHistoryState({ activeTab: 'home', showProfile: false, showPostPage: false, showSettings: false, showNotifications: false, showCampaigns: false, showCampaignDetail: false, showCampaignLeaderboard: false, showCampaignFeed: false, showVideoDetail: false, showEditProfile: false, showFollowersList: false, showExplorer: false }, true);
  };

  return (
    <div className="App">
      <AppShell
        user={authUser}
        activeTab={activeTab}
        onTabChange={(tab) => {
          const feedTabs = ['home', 'reels', 'messages', 'following', 'bookmarks', 'search'];
          if (feedTabs.includes(tab)) resetAllPages();
          setShowWallet(false); // always close wallet when switching tabs
          startTransition(() => {
            setActiveTab(tab);
            // Clear videoDetailId when switching tabs UNLESS we're intentionally navigating to a specific video
            // This prevents stale video IDs from persisting when navigating away from reels
            if (tab !== 'reels' && videoDetailId) {
              setVideoDetailId(null);
            }
            // Normal tab switching must NOT carry a stale deep-link target.
            // Otherwise clicking the Reels tab would keep re-ordering the feed
            // to the last notification / post the user previously opened.
            saveNav({ activeTab: tab });
            // Use replaceState instead of pushState for tab switching to avoid building up history
            pushHistoryState({
              activeTab: tab,
              showNotifications: false,
              showProfile: false,
              showPostPage: false,
              showSettings: false,
              showCampaigns: false,
              showCampaignDetail: false,
              showCampaignLeaderboard: false,
              showCampaignFeed: false,
              showExplorer: false,
              showVideoDetail: false,
              showEditProfile: false,
              showFollowersList: false,
            }, true);
          });
        }}
        onLogout={handleLogout}
        onShowProfile={() => handleShowProfile(null)}
        onShowPostPage={handleShowPostPage}
        onShowSettings={handleShowSettings}
        onShowNotifications={handleShowNotifications}
        onShowCampaigns={handleShowCampaigns}
        onShowExplorer={handleShowExplorer}
        onRequireAuth={handleRequireAuth}
        unreadNotifCount={unreadNotifCount}
        unreadDmCount={unreadDmCount}
      >
        {/* Each lazy page gets its own Suspense so only one loads at a time */}
        {showWallet && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <WalletPage theme={colors} onBack={handleCloseWallet} showTopUpOnMount={walletShowTopUpOnMount.current} onShowCoinPurchase={handleShowCoinPurchase} />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showSubscription && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <SubscriptionPage user={authUser} onBack={handleCloseSubscription} />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showSettings && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <SettingsPage
                user={authUser}
                onClose={handleCloseSettings}
                onLogout={handleLogout}
                onShowWallet={handleShowWallet}
                onShowSubscription={handleShowSubscription}
                onShowEditProfile={handleShowEditProfile}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showNotifications && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <NotificationsPage
                user={authUser}
                onUserClick={(userId) => {
                  setShowNotifications(false);
                  handleShowProfile(userId);
                }}
                onBack={() => goHome()}
                onShowPostPage={handleShowPostPage}
                onLogout={handleLogout}
                onShowProfile={() => handleShowProfile(null)}
                onShowSettings={handleShowSettings}
                onShowSubscription={handleShowSubscription}
                onShowCampaigns={handleShowCampaigns}
                onShowVideoDetail={(reelId) => {
                  setShowNotifications(false);
                  handleShowVideoDetail(reelId);
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showEditProfile && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <EditProfilePage
                user={authUser}
                onBack={() => {
                  setShowEditProfile(false);
                  // Restore previous state if available
                  if (prevNavState.current) {
                    const { showSettings, showProfile, showPostPage, showFollowersList } = prevNavState.current;
                    setShowSettings(showSettings || false);
                    setShowProfile(showProfile || false);
                    setShowPostPage(showPostPage || false);
                    setShowFollowersList(showFollowersList || false);
                    prevNavState.current = null;
                  } else {
                    goHome();
                  }
                }}
                onSave={handleProfileSaved}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showFollowersList && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <FollowersListPage
                user={authUser}
                userId={followersListUserId}
                type={followersListType}
                onBack={() => goHome()}
                onUserClick={(userId) => {
                  const id = typeof userId === 'object' ? userId.id : userId;
                  setShowFollowersList(false);
                  handleShowProfile(id);
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showProfile && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ProfilePage
                user={authUser}
                userId={profileUserId}
                onBack={() => goHome()}
                onEditProfile={handleShowEditProfile}
                onShowSettings={handleShowSettings}
                onShowWallet={handleShowWallet}
                onShowSubscription={handleShowSubscription}
                onShowCoinPurchase={handleShowCoinPurchase}
                onShowFollowers={(userId) =>
                  handleShowFollowers(userId, 'followers')
                }
                onShowFollowing={(userId) =>
                  handleShowFollowers(userId, 'following')
                }
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showCampaignDetail && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <CampaignDetailPage
                theme={{
                  pri: '#8fc441',
                  txt: '#1C1917',
                  sub: '#78716C',
                  bg: '#FAFAF9',
                  card: '#FFFFFF',
                  border: '#E7E5E4',
                  blue: '#3B82F6',
                  green: '#10B981',
                  red: '#EF4444',
                  orange: '#8fc441',
                  purple: '#8B5CF6',
                }}
                campaignId={campaignId}
                onBack={() => {
                  setShowCampaignDetail(false);
                  setShowCampaigns(true);
                  window.history.back();
                }}
                onShowLeaderboard={() => {
                  setShowCampaignDetail(false);
                  setShowCampaignLeaderboard(true);
                }}
                onShowFeed={() => {
                  setShowCampaignDetail(false);
                  setShowCampaignFeed(true);
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showCampaignLeaderboard && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <CampaignLeaderboard
                campaignId={campaignId}
                onBack={() => {
                  setShowCampaignLeaderboard(false);
                  setShowCampaignDetail(true);
                  window.history.back();
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showCampaignFeed && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <CampaignFeed
                campaignId={campaignId}
                onBack={() => {
                  setShowCampaignFeed(false);
                  setShowCampaignDetail(true);
                  window.history.back();
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showCampaigns && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <CampaignsPage
                onCampaignClick={(id) => {
                  setCampaignId(id);
                  setShowCampaigns(false);
                  setShowCampaignDetail(true);
                }}
                onBack={() => goHome()}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showPostPage && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <EnhancedPostPage
                user={authUser}
                onBack={handleClosePostPage}
                onPostSuccess={handlePostSuccess}
                onNavHome={() => { setShowPostPage(false); setActiveTab('home'); }}
                onNavReels={() => { setShowPostPage(false); setActiveTab('reels'); }}
                onNavMessages={() => { setShowPostPage(false); setActiveTab('messages'); }}
                onNavProfile={() => handleShowProfile(null)}
                unreadDmCount={unreadDmCount}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showTopUpModal && (
          <TopUpModal
            theme={colors}
            onClose={() => setShowTopUpModal(false)}
          />
        )}
        {showVideoDetail && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <VideoDetailPage
                reelId={videoDetailId}
                user={authUser}
                onBack={() => setShowVideoDetail(false)}
                onShowProfile={handleShowProfile}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {showExplorer && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <ExplorerPage
                user={authUser}
                onBack={handleCloseExplorer}
                onShowProfile={handleShowProfile}
                onShowVideoDetail={handleShowVideoDetail}
                onRequireAuth={handleRequireAuth}
                onShowPostPage={handleShowPostPage}
                onShowSettings={handleShowSettings}
                onShowNotifications={handleShowNotifications}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {screen === 'landing' && !showWallet && !showSettings && !showNotifications && !showEditProfile && !showFollowersList && !showProfile && !showCampaignDetail && !showCampaigns && !showCampaignLeaderboard && !showCampaignFeed && !showPostPage && !showVideoDetail && !showExplorer && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <LandingPage
                onLogin={() => setShowLogin(true)}
                onRegister={() => { setShowLogin(true); }}
                onShowCampaigns={handleShowCampaigns}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {screen !== 'landing' && !showWallet && !showSettings && !showNotifications && !showEditProfile && !showFollowersList && !showProfile && !showCampaignDetail && !showCampaigns && !showCampaignLeaderboard && !showCampaignFeed && !showPostPage && !showVideoDetail && !showExplorer && activeTab === 'home' && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <HomePage
                user={authUser}
                onShowProfile={handleShowProfile}
                onShowPostPage={handleShowPostPage}
                onRequireAuth={handleRequireAuth}
                onShowExplorer={handleShowExplorer}
                onShowVideoDetail={handleShowVideoDetail}
                onShowCampaigns={handleShowCampaigns}
                onShowWallet={handleShowWallet}
                onShowCoinPurchase={handleShowCoinPurchase}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {screen !== 'landing' && !showWallet && !showSettings && !showNotifications && !showEditProfile && !showFollowersList && !showProfile && !showCampaignDetail && !showCampaigns && !showCampaignLeaderboard && !showCampaignFeed && !showPostPage && !showVideoDetail && !showExplorer && activeTab === 'messages' && (
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <MessagesPage
                user={authUser}
                onShowProfile={handleShowProfile}
                onRequireAuth={handleRequireAuth}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        )}
        {screen !== 'landing' && !showWallet && !showSettings && !showNotifications && !showEditProfile && !showFollowersList && !showProfile && !showCampaignDetail && !showCampaigns && !showCampaignLeaderboard && !showCampaignFeed && !showPostPage && !showVideoDetail && !showExplorer && activeTab === 'reels' && (
          <TikTokLayout
            user={authUser}
            activeTab={activeTab}
            videosOnly={true}
            initialVideoId={videoDetailId}
            onLogout={handleLogout}
            onRequireAuth={handleRequireAuth}
            onShowPostPage={handleShowPostPage}
            onShowProfile={handleShowProfile}
            onShowSettings={handleShowSettings}
            onShowNotifications={handleShowNotifications}
            onShowVideoDetail={handleShowVideoDetail}
            onShowExplorer={handleShowExplorer}
            onShowWallet={handleShowWallet}
            onShowCoinPurchase={handleShowCoinPurchase}
            unreadNotifCount={unreadNotifCount}
          />
        )}
      </AppShell>
      {/* ── SMS Registration (arriving via Onevas link) ── */}
      {showSubRegister && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 4000, overflowY: 'auto', background: '#0D0D0D' }}>
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <SubscriptionRegisterModal
                prefillPhone={_prefillPhone}
                prefillOtp={_prefillOtp}
                onSuccess={(u) => {
                  setAuthUser(u);
                  localStorage.setItem('user', JSON.stringify(u));
                  setShowSubRegister(false);
                }}
                onBackToLogin={() => {
                  setShowSubRegister(false);
                  setShowLogin(true);
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        </div>
      )}

      {/* ── Phone Login Modal ── */}
      {showLogin && !showSubRegister && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 3000, overflowY: 'auto', background: '#0D0D0D' }}>
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <PhoneLoginModal
                onSuccess={(u) => {
                  setAuthUser(u);
                  localStorage.setItem('user', JSON.stringify(u));
                  setShowLogin(false);
                }}
                onSignUp={() => {
                  setShowLogin(false);
                  setShowSubscription(true);
                }}
                onClose={() => setShowLogin(false)}
                onForgotPasswordToggle={(showing) => setShowForgotPassword(showing)}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        </div>
      )}

      {/* ── Subscription Gateway (new user selects plan → SMS) ── */}
      {showSubscription && !showLogin && (
        <div style={{ position: 'fixed', inset: 0, zIndex: 3000, overflowY: 'auto', background: '#0D0D0D' }}>
          <LazyLoadErrorBoundary>
            <Suspense fallback={<PageSkeleton />}>
              <SubscriptionPage
                user={null}
                onBack={() => {
                  setShowSubscription(false);
                  setShowLogin(true);
                }}
              />
            </Suspense>
          </LazyLoadErrorBoundary>
        </div>
      )}
    </div>
  );
}




