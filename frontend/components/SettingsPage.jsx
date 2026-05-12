import { useState, useEffect } from "react";
import {
  X, User, Bell, Lock, Globe, HelpCircle, LogOut, ChevronRight, Moon, Sun, Wallet,
  ChevronLeft, MessageCircle, Heart, Users as UsersIcon, Mail, Eye, EyeOff, Activity,
  Download, Trash2, Shield, FileText, Check, Crown
} from "lucide-react";
import api from "../api";
import config from "../config";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";

export function SettingsPage({ user, onClose, onLogout, onShowWallet, onShowEditProfile }) {
  const { darkMode, toggleDarkMode, colors: T } = useTheme();
  const { language, changeLanguage, t } = useLanguage();
  const [activeSection, setActiveSection] = useState("account");
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);
  const [isSmallMobile, setIsSmallMobile] = useState(window.innerWidth <= 393);

  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth <= 768);
      setIsSmallMobile(window.innerWidth <= 393);
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);
  const [notifications, setNotifications] = useState(() => {
    const saved = localStorage.getItem('notifications');
    if (saved) return JSON.parse(saved);
    return { likes: true, comments: true, follows: true, messages: true };
  });

  useEffect(() => {
    // Fetch notification settings from server
    api.getNotificationSettings().then(data => {
      if (data) {
        setNotifications({
          likes: data.likes ?? true,
          comments: data.comments ?? true,
          follows: data.follows ?? true,
          messages: data.messages ?? true,
        });
      }
    }).catch(() => {
      // Keep localStorage values if fetch fails - silent fail
    });
  }, []);

  useEffect(() => {
    localStorage.setItem('notifications', JSON.stringify(notifications));
  }, [notifications]);

  const [privacy, setPrivacy] = useState(() => {
    const saved = localStorage.getItem('privacy');
    return saved ? JSON.parse(saved) : {
      privateAccount: false,
      showActivity: true,
      allowMessages: true,
    };
  });
  const [saving, setSaving] = useState(false);

  // Save settings to localStorage whenever they change
  useEffect(() => {
    localStorage.setItem('notifications', JSON.stringify(notifications));
  }, [notifications]);

  useEffect(() => {
    localStorage.setItem('privacy', JSON.stringify(privacy));
  }, [privacy]);

  const handleSaveSettings = () => {
    setSaving(true);
    setTimeout(() => {
      setSaving(false);
      setModal({
        isOpen: true,
        title: t('success'),
        message: t('settingsSaved'),
        type: 'success',
        onConfirm: null
      });
    }, 500);
  };

  const [password, setPassword] = useState({ current: '', new: '', confirm: '' });
  const [blockedUsers, setBlockedUsers] = useState([]);
  const [modal, setModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });

  const sections = [
    { id: "account", icon: User, label: t('account') },
    { id: "wallet", icon: Wallet, label: 'Wallet', isExternal: true },
    { id: "subscription", icon: Crown, label: 'Subscription', isExternal: true },
    { id: "notifications", icon: Bell, label: t('notificationsSettings') },
    { id: "privacy", icon: Lock, label: t('privacy') },
    { id: "appearance", icon: darkMode ? Moon : Sun, label: t('appearance') },
    { id: "language", icon: Globe, label: t('language') },
    { id: "help", icon: HelpCircle, label: t('help') },
  ];

  const handlePasswordChange = async () => {
    if (password.new !== password.confirm) {
      setModal({
        isOpen: true,
        title: t('error'),
        message: t('passwordMismatch'),
        type: 'error',
        onConfirm: null
      });
      return;
    }
    if (password.new.length !== 6 || !/^\d+$/.test(password.new)) {
      setModal({
        isOpen: true,
        title: t('error'),
        message: 'New password must be exactly 6 digits',
        type: 'error',
        onConfirm: null
      });
      return;
    }
    try {
      await api.changePassword(password.current, password.new);
      setModal({
        isOpen: true,
        title: t('success'),
        message: t('passwordChanged'),
        type: 'success',
        onConfirm: null
      });
      setPassword({ current: '', new: '', confirm: '' });
    } catch (error) {
      setModal({
        isOpen: true,
        title: t('error'),
        message: t('passwordChangeFailed'),
        type: 'error',
        onConfirm: null
      });
    }
  };

  const handleDeleteAccount = () => {
    setModal({
      isOpen: true,
      title: t('deleteAccount'),
      message: t('deleteConfirm'),
      type: 'warning',
      onConfirm: () => {
        setModal({
          isOpen: true,
          title: t('finalConfirm'),
          message: t('deleteWarning'),
          type: 'warning',
          onConfirm: async () => {
            try {
              await api.deleteAccount();
              setModal({
                isOpen: true,
                title: t('accountDeleted'),
                message: t('accountDeleting'),
                type: 'info',
                onConfirm: () => onLogout()
              });
            } catch (error) {
              setModal({
                isOpen: true,
                title: t('error'),
                message: 'Failed to delete account. Please try again.',
                type: 'error',
                onConfirm: null
              });
            }
          }
        });
      }
    });
  };

  const handleDownloadData = async () => {
    try {
      await api.downloadUserData();
      setModal({
        isOpen: true,
        title: t('downloadInitiated'),
        message: t('downloadEmail'),
        type: 'info',
        onConfirm: null
      });
    } catch (error) {
      setModal({
        isOpen: true,
        title: t('error'),
        message: 'Failed to request data download. Please try again.',
        type: 'error',
        onConfirm: null
      });
    }
  };

  // ─── MOBILE UI (mimics mobile app SettingsScreen) ────────────────────────────
  const [showPassModal, setShowPassModal] = useState(false);
  const [showLangModal, setShowLangModal] = useState(false);

  if (isMobile) {
    const Switch = ({ value, onChange }) => (
      <label style={{ position: 'relative', display: 'inline-block', width: 44, height: 26, flexShrink: 0 }}>
        <input type="checkbox" checked={value} onChange={onChange} style={{ opacity: 0, width: 0, height: 0 }} />
        <span style={{
          position: 'absolute', cursor: 'pointer', inset: 0,
          background: value ? T.pri : (T.border || '#3F3F46'),
          borderRadius: 26, transition: '0.25s',
        }}>
          <span style={{
            position: 'absolute', height: 20, width: 20,
            left: value ? 22 : 2, top: 3,
            background: '#fff', borderRadius: '50%', transition: '0.25s',
            boxShadow: '0 2px 4px rgba(0,0,0,0.2)',
          }} />
        </span>
      </label>
    );

    const Row = ({ icon: Icon, title, subtitle, type = 'chevron', value, onToggle, onPress, color, danger }) => {
      const c = danger ? '#EF4444' : (color || T.txt);
      return (
        <div
          onClick={type === 'switch' ? undefined : onPress}
          style={{
            display: 'flex', alignItems: 'center', justifyContent: 'space-between',
            padding: '14px 16px', borderBottom: `1px solid ${T.border}`,
            cursor: type === 'switch' ? 'default' : 'pointer',
            background: 'transparent',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', flex: 1, minWidth: 0 }}>
            <div style={{
              width: 36, height: 36, borderRadius: 10,
              background: c + '20',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginRight: 12, flexShrink: 0,
            }}>
              <Icon size={18} color={c} />
            </div>
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: danger ? '#EF4444' : T.txt }}>{title}</div>
              {subtitle && <div style={{ fontSize: 12, color: T.sub, marginTop: 2 }}>{subtitle}</div>}
            </div>
          </div>
          {type === 'switch' ? (
            <Switch value={value} onChange={onToggle} />
          ) : (
            <ChevronRight size={18} color={T.sub} />
          )}
        </div>
      );
    };

    const SectionLabel = ({ children }) => (
      <div style={{
        fontSize: 12, fontWeight: 700, color: T.sub,
        textTransform: 'uppercase', letterSpacing: 1.2,
        margin: '20px 20px 8px',
      }}>{children}</div>
    );

    const SectionCard = ({ children }) => (
      <div style={{
        margin: '0 16px', borderRadius: 16, overflow: 'hidden',
        border: `1px solid ${T.border}`, background: T.cardBg,
      }}>
        {children}
      </div>
    );

    const handleNotificationToggle = async (key) => {
      const newVal = !notifications[key];
      const next = { ...notifications, [key]: newVal };
      setNotifications(next);
      try { await api.updateNotificationSettings({ [key]: newVal }); } catch {}
    };

    const handlePrivacyToggle = async (key) => {
      const newVal = !privacy[key];
      const next = { ...privacy, [key]: newVal };
      setPrivacy(next);
      try { await api.updatePrivacySettings({ [key]: newVal }); } catch {
        setPrivacy({ ...privacy, [key]: !newVal });
      }
    };

    return (
      <div style={{
        position: 'fixed', inset: 0, zIndex: 4000,
        background: T.bg, display: 'flex', flexDirection: 'column',
      }}>
        {/* Header */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '12px 16px', background: T.cardBg,
          borderBottom: `1px solid ${T.border}`, flexShrink: 0,
        }}>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, display: 'flex', color: T.txt }}>
            <ChevronLeft size={26} />
          </button>
          <div style={{ fontSize: 17, fontWeight: 700, color: T.txt }}>{t('settings')}</div>
          <div style={{ width: 34 }} />
        </div>

        {/* Body */}
        <div style={{ flex: 1, overflowY: 'auto' }}>
          {/* Profile Summary */}
          <div style={{
            display: 'flex', flexDirection: 'column', alignItems: 'center',
            padding: '28px 16px', background: T.cardBg, marginBottom: 8,
          }}>
            <div style={{
              width: 80, height: 80, borderRadius: '50%', background: T.pri,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              marginBottom: 12, boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
              overflow: 'hidden',
            }}>
              {user?.profile_photo ? (
                <img
                  src={user.profile_photo.startsWith('http') ? user.profile_photo : `${config.API_BASE_URL.replace('/api', '')}${user.profile_photo}`}
                  alt={user.username}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <span style={{ fontSize: 32, fontWeight: 800, color: '#000' }}>
                  {user?.username?.[0]?.toUpperCase() || 'U'}
                </span>
              )}
            </div>
            <div style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>@{user?.username}</div>
            <div style={{ fontSize: 13, color: T.sub, marginTop: 2 }}>{user?.email}</div>
          </div>

          {/* Account */}
          <SectionLabel>{t('account')}</SectionLabel>
          <SectionCard>
            <Row icon={User} title={t('editProfile')} subtitle="Change bio and photo" onPress={() => { onClose?.(); onShowEditProfile?.(); }} />
            <Row icon={Wallet} title="Wallet" subtitle="Coins & transactions" onPress={() => { onClose?.(); onShowWallet?.(); }} />
            <Row icon={Crown} title="Subscription" subtitle="Plans & billing" onPress={() => { onClose?.(); onShowSubscription?.(); }} />
            <Row icon={Lock} title={t('changePassword')} onPress={() => setShowPassModal(true)} />
            <Row icon={Download} title={t('downloadData')} subtitle={t('downloadDataDesc')} onPress={handleDownloadData} />
          </SectionCard>

          {/* Notifications */}
          <SectionLabel>{t('notificationsSettings')}</SectionLabel>
          <SectionCard>
            <Row icon={Heart} title={t('likes') || 'Likes'} type="switch" value={notifications.likes} onToggle={() => handleNotificationToggle('likes')} />
            <Row icon={MessageCircle} title={t('comments') || 'Comments'} type="switch" value={notifications.comments} onToggle={() => handleNotificationToggle('comments')} />
            <Row icon={UsersIcon} title={t('follows') || 'Follows'} type="switch" value={notifications.follows} onToggle={() => handleNotificationToggle('follows')} />
            <Row icon={Mail} title={t('messages') || 'Messages'} type="switch" value={notifications.messages} onToggle={() => handleNotificationToggle('messages')} />
          </SectionCard>

          {/* Privacy */}
          <SectionLabel>{t('privacy')}</SectionLabel>
          <SectionCard>
            <Row icon={EyeOff} title={t('privateAccount') || 'Private Account'} subtitle={t('privateAccountDesc')} type="switch" value={privacy.privateAccount} onToggle={() => handlePrivacyToggle('privateAccount')} />
            <Row icon={Activity} title={t('showActivity') || 'Show Activity'} subtitle={t('showActivityDesc')} type="switch" value={privacy.showActivity} onToggle={() => handlePrivacyToggle('showActivity')} />
            <Row icon={Mail} title={t('allowMessages') || 'Allow Messages'} subtitle={t('allowMessagesDesc')} type="switch" value={privacy.allowMessages} onToggle={() => handlePrivacyToggle('allowMessages')} />
          </SectionCard>

          {/* Appearance */}
          <SectionLabel>{t('appearance')}</SectionLabel>
          <SectionCard>
            <Row icon={darkMode ? Moon : Sun} title={t('darkMode')} type="switch" value={darkMode} onToggle={toggleDarkMode} />
            <Row icon={Globe} title={t('language')} subtitle={language === 'en' ? 'English' : language === 'am' ? 'አማርኛ' : language} onPress={() => setShowLangModal(true)} />
          </SectionCard>

          {/* Help */}
          <SectionLabel>{t('help')}</SectionLabel>
          <SectionCard>
            <Row icon={HelpCircle} title={t('helpCenter')} onPress={() => setModal({ isOpen: true, title: 'Help', message: 'Contact support@flipstar.com', type: 'info', onConfirm: null })} />
            <Row icon={Shield} title={t('privacyPolicy')} onPress={() => window.open('/legal/privacy-policy', '_blank')} />
            <Row icon={FileText} title={t('termsOfService')} onPress={() => window.open('/legal/terms-of-service', '_blank')} />
          </SectionCard>

          {/* Danger Zone */}
          <SectionLabel>{t('dangerZone')}</SectionLabel>
          <SectionCard>
            <Row icon={Trash2} title={t('deleteAccount')} danger onPress={handleDeleteAccount} />
          </SectionCard>

          {/* Logout */}
          <button
            onClick={onLogout}
            style={{
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              gap: 10, margin: '24px 16px 0', padding: 16,
              background: T.cardBg, border: `1px solid ${T.border}`,
              borderRadius: 16, cursor: 'pointer',
              color: '#EF4444', fontSize: 15, fontWeight: 800, width: 'calc(100% - 32px)',
            }}
          >
            <LogOut size={20} />
            {t('logout')}
          </button>

          <div style={{ textAlign: 'center', padding: '32px 0' }}>
            <div style={{ fontSize: 12, fontWeight: 600, color: T.sub }}>{t('version')} 1.0.0</div>
            <div style={{ fontSize: 10, color: T.sub, opacity: 0.6, marginTop: 4 }}>© 2024 FlipStar Inc.</div>
          </div>
        </div>

        {/* Language Bottom Sheet */}
        {showLangModal && (
          <div onClick={() => setShowLangModal(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 4500, display: 'flex', alignItems: 'flex-end' }}>
            <div onClick={e => e.stopPropagation()} style={{ width: '100%', background: T.cardBg, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: 24 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottom: `1px solid ${T.border}` }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>{t('chooseLanguage')}</div>
                <button onClick={() => setShowLangModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.txt }}>
                  <X size={22} />
                </button>
              </div>
              <div style={{ padding: '8px 20px' }}>
                {[
                  { id: 'en', label: 'English' },
                  { id: 'am', label: 'አማርኛ (Amharic)' },
                  { id: 'es', label: 'Español' },
                  { id: 'fr', label: 'Français' },
                  { id: 'ar', label: 'العربية' },
                ].map(l => (
                  <button
                    key={l.id}
                    onClick={() => { changeLanguage(l.id); setShowLangModal(false); }}
                    style={{
                      width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                      padding: '16px 4px', background: 'none', border: 'none', cursor: 'pointer',
                      borderBottom: `1px solid ${T.border}`,
                    }}
                  >
                    <span style={{ fontSize: 16, fontWeight: 600, color: language === l.id ? T.pri : T.txt }}>{l.label}</span>
                    {language === l.id && <Check size={20} color={T.pri} />}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Password Bottom Sheet */}
        {showPassModal && (
          <div onClick={() => setShowPassModal(false)} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)', zIndex: 4500, display: 'flex', alignItems: 'flex-end' }}>
            <div onClick={e => e.stopPropagation()} style={{ width: '100%', background: T.cardBg, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: 32 }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottom: `1px solid ${T.border}` }}>
                <div style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>{t('changePassword')}</div>
                <button onClick={() => setShowPassModal(false)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.txt }}>
                  <X size={22} />
                </button>
              </div>
              <div style={{ padding: 20 }}>
                {[
                  { key: 'current', label: t('currentPassword') },
                  { key: 'new', label: t('newPassword') },
                  { key: 'confirm', label: t('confirmPassword') },
                ].map(f => (
                  <div key={f.key} style={{ marginBottom: 14 }}>
                    <label style={{ fontSize: 13, fontWeight: 700, color: T.txt, display: 'block', marginBottom: 6 }}>{f.label}</label>
                    <input
                      type="password"
                      value={password[f.key]}
                      onChange={(e) => setPassword({ ...password, [f.key]: e.target.value })}
                      style={{
                        width: '100%', padding: 14, borderRadius: 12,
                        border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
                        fontSize: 15, boxSizing: 'border-box', outline: 'none',
                      }}
                    />
                  </div>
                ))}
                <button
                  onClick={async () => { await handlePasswordChange(); setShowPassModal(false); }}
                  style={{
                    width: '100%', marginTop: 12, padding: 16, borderRadius: 14,
                    background: T.pri, color: '#000', border: 'none',
                    fontSize: 15, fontWeight: 800, cursor: 'pointer',
                    boxShadow: `0 4px 16px ${T.pri}40`,
                  }}
                >
                  {t('updatePassword')}
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Custom Modal (alerts) */}
        {modal.isOpen && (
          <div onClick={() => setModal({ ...modal, isOpen: false })} style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)', display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 5000, padding: 16 }}>
            <div onClick={e => e.stopPropagation()} style={{ background: T.cardBg, borderRadius: 16, padding: 20, maxWidth: 360, width: '100%' }}>
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#F59E0B' : modal.type === 'success' ? '#10B981' : T.txt, marginBottom: 8 }}>{modal.title}</h3>
              <p style={{ margin: 0, fontSize: 14, color: T.txt, lineHeight: 1.5, marginBottom: 16 }}>{modal.message}</p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                {modal.onConfirm && (
                  <button onClick={() => setModal({ ...modal, isOpen: false })} style={{ padding: '10px 16px', borderRadius: 10, border: `1px solid ${T.border}`, background: T.cardBg, color: T.txt, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                    {t('cancel')}
                  </button>
                )}
                <button
                  onClick={() => { if (modal.onConfirm) modal.onConfirm(); setModal({ ...modal, isOpen: false }); }}
                  style={{ padding: '10px 16px', borderRadius: 10, border: 'none', background: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#F59E0B' : modal.type === 'success' ? '#10B981' : T.pri, color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
                >
                  {modal.onConfirm ? t('confirm') : t('ok')}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    );
  }

  // ─── DESKTOP UI ──────────────────────────────────────────────────────────────
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
      zIndex: 4000,
    }}
    onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: isMobile ? "100%" : "100%",
          maxWidth: isMobile ? "100%" : 900,
          height: isMobile ? "100vh" : "auto",
          maxHeight: isMobile ? "100vh" : "90vh",
          background: T.cardBg,
          borderRadius: isMobile ? 0 : 20,
          display: "flex",
          overflow: "hidden",
        }}
      >
        {/* Sidebar */}
        <div style={{
          width: isSmallMobile ? 60 : (isMobile ? 80 : 280),
          background: T.bg,
          borderRight: `1px solid ${T.border}`,
          display: "flex",
          flexDirection: "column",
          flexShrink: 0,
        }}>
          <div style={{
            padding: isSmallMobile ? "12px 4px" : (isMobile ? "16px 8px" : "20px"),
            borderBottom: `1px solid ${T.border}`,
            display: "flex",
            alignItems: "center",
            justifyContent: isMobile ? "center" : "space-between",
          }}>
            {!isMobile && <div style={{ fontSize: 20, fontWeight: 700, color: T.txt }}>{t('settings')}</div>}
            <button
              onClick={onClose}
              style={{
                background: "none",
                border: "none",
                cursor: "pointer",
                padding: 8,
                display: "flex",
                color: T.txt,
              }}
            >
              <X size={24} />
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: isSmallMobile ? "8px 0" : "12px 0" }}>
            {sections.map(section => {
              const Icon = section.icon;
              const isActive = activeSection === section.id;
              return (
                <button
                  key={section.id}
                  onClick={() => {
                    if (section.isExternal && section.id === 'wallet' && onShowWallet) {
                      onShowWallet();
                      return;
                    }
                    if (section.isExternal && section.id === 'subscription' && onShowSubscription) {
                      onShowSubscription();
                      return;
                    }
                    setActiveSection(section.id);
                  }}
                  style={{
                    width: "100%",
                    padding: isSmallMobile ? "8px 4px" : (isMobile ? "12px 8px" : "14px 20px"),
                    border: "none",
                    background: isActive ? T.cardBg : "transparent",
                    cursor: "pointer",
                    display: "flex",
                    flexDirection: isMobile ? "column" : "row",
                    alignItems: "center",
                    justifyContent: "center",
                    gap: isSmallMobile ? 2 : (isMobile ? 4 : 12),
                    color: isActive ? T.pri : T.txt,
                    fontWeight: isActive ? 600 : 500,
                    borderLeft: isActive ? `3px solid ${T.pri}` : "3px solid transparent",
                  }}
                >
                  <Icon size={isSmallMobile ? 18 : (isMobile ? 22 : 20)} />
                  {!isMobile && <span style={{ flex: 1, textAlign: "left" }}>{section.label}</span>}
                  {isMobile && <span style={{ fontSize: isSmallMobile ? 8 : 10, textAlign: "center", lineHeight: 1.2 }}>{section.label}</span>}
                  {!isMobile && <ChevronRight size={16} style={{ opacity: 0.5 }} />}
                </button>
              );
            })}
          </div>

          <div style={{ padding: isSmallMobile ? 6 : (isMobile ? 8 : 20), borderTop: `1px solid ${T.border}`, paddingBottom: isSmallMobile ? 12 : (isMobile ? 16 : 20) }}>
            <button
              onClick={onLogout}
              style={{
                width: "100%",
                padding: isSmallMobile ? "8px 4px" : (isMobile ? "10px 8px" : "12px 16px"),
                background: "#EF4444",
                color: "#fff",
                border: "none",
                borderRadius: 8,
                cursor: "pointer",
                display: "flex",
                flexDirection: isMobile ? "column" : "row",
                alignItems: "center",
                justifyContent: "center",
                gap: isSmallMobile ? 2 : (isMobile ? 4 : 8),
                fontSize: isSmallMobile ? 8 : (isMobile ? 10 : 14),
                fontWeight: 600,
                lineHeight: 1.2,
              }}
            >
              <LogOut size={isSmallMobile ? 14 : 18} />
              {t('logout')}
            </button>
          </div>
        </div>

        {/* Content */}
        <div style={{ flex: 1, overflowY: "auto", padding: isSmallMobile ? 16 : (isMobile ? 24 : 32) }}>
          {activeSection === "account" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('accountSettings')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('manageAccount')}</p>

              <div style={{ display: "flex", flexDirection: "column", gap: 32 }}>
                {/* Basic Info */}
                <div>
                  <h3 style={{ fontSize: isSmallMobile ? 14 : 16, fontWeight: 600, color: T.txt, marginBottom: 16 }}>{t('basicInfo')}</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <div>
                      <label style={{ fontSize: isSmallMobile ? 12 : 14, fontWeight: 600, color: T.txt, marginBottom: 8, display: "block" }}>
                        {t('username')}
                      </label>
                      <input
                        type="text"
                        value={user?.username || ""}
                        disabled
                        style={{
                          width: "100%",
                          padding: "12px 16px",
                          border: `1px solid ${T.border}`,
                          borderRadius: 8,
                          fontSize: 14,
                          background: T.bg,
                          color: T.sub,
                        }}
                      />
                    </div>

                    <div>
                      <label style={{ fontSize: isSmallMobile ? 12 : 14, fontWeight: 600, color: T.txt, marginBottom: 8, display: "block" }}>
                        {t('email')}
                      </label>
                      <input
                        type="email"
                        value={user?.email || ""}
                        disabled
                        style={{
                          width: "100%",
                          padding: "12px 16px",
                          border: `1px solid ${T.border}`,
                          borderRadius: 8,
                          fontSize: 14,
                          background: T.bg,
                          color: T.sub,
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* Password Change */}
                <div>
                  <h3 style={{ fontSize: isSmallMobile ? 14 : 16, fontWeight: 600, color: T.txt, marginBottom: 16 }}>{t('changePassword')}</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                    <input
                      type="password"
                      inputMode="numeric"
                      maxLength={6}
                      placeholder="••••••"
                      value={password.current}
                      onChange={(e) => setPassword({...password, current: e.target.value.replace(/\D/g, "").slice(0, 6)})}
                      style={{
                        width: "100%",
                        padding: isSmallMobile ? "10px 12px" : "12px 16px",
                        border: `1px solid ${T.border}`,
                        borderRadius: 8,
                        fontSize: isSmallMobile ? 12 : 14,
                      }}
                    />
                    <input
                      type="password"
                      inputMode="numeric"
                      maxLength={6}
                      placeholder="••••••"
                      value={password.new}
                      onChange={(e) => setPassword({...password, new: e.target.value.replace(/\D/g, "").slice(0, 6)})}
                      style={{
                        width: "100%",
                        padding: isSmallMobile ? "10px 12px" : "12px 16px",
                        border: `1px solid ${T.border}`,
                        borderRadius: 8,
                        fontSize: isSmallMobile ? 12 : 14,
                      }}
                    />
                    <input
                      type="password"
                      inputMode="numeric"
                      maxLength={6}
                      placeholder="••••••"
                      value={password.confirm}
                      onChange={(e) => setPassword({...password, confirm: e.target.value.replace(/\D/g, "").slice(0, 6)})}
                      style={{
                        width: "100%",
                        padding: isSmallMobile ? "10px 12px" : "12px 16px",
                        border: `1px solid ${T.border}`,
                        borderRadius: 8,
                        fontSize: isSmallMobile ? 12 : 14,
                      }}
                    />
                    <button
                      onClick={handlePasswordChange}
                      style={{
                        padding: isSmallMobile ? "10px 16px" : "12px 24px",
                        background: T.pri,
                        color: "#fff",
                        border: "none",
                        borderRadius: 8,
                        fontSize: isSmallMobile ? 12 : 14,
                        fontWeight: 600,
                        cursor: "pointer",
                        alignSelf: "flex-start",
                      }}
                    >
                      {t('updatePassword')}
                    </button>
                  </div>
                </div>

                {/* Data Management */}
                <div>
                  <h3 style={{ fontSize: isSmallMobile ? 14 : 16, fontWeight: 600, color: T.txt, marginBottom: 16 }}>{t('dataManagement')}</h3>
                  <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                    <button
                      onClick={handleDownloadData}
                      style={{
                        padding: isSmallMobile ? "10px 16px" : "12px 20px",
                        background: T.bg,
                        border: `1px solid ${T.border}`,
                        borderRadius: 8,
                        fontSize: isSmallMobile ? 12 : 14,
                        fontWeight: 600,
                        cursor: "pointer",
                        textAlign: "left",
                        color: T.txt,
                      }}
                    >
                      📥 {t('downloadData')}
                    </button>
                    <p style={{ fontSize: isSmallMobile ? 10 : 12, color: T.sub, marginTop: -8 }}>
                      {t('downloadDataDesc')}
                    </p>
                  </div>
                </div>

                {/* Danger Zone */}
                <div style={{
                  padding: isSmallMobile ? 16 : 20,
                  background: "#FEE2E2",
                  borderRadius: 12,
                  border: "2px solid #EF4444",
                }}>
                  <h3 style={{ fontSize: isSmallMobile ? 14 : 16, fontWeight: 600, color: "#DC2626", marginBottom: 8 }}>{t('dangerZone')}</h3>
                  <p style={{ fontSize: isSmallMobile ? 11 : 13, color: "#991B1B", marginBottom: 16 }}>
                    {t('deleteWarning')}
                  </p>
                  <button
                    onClick={handleDeleteAccount}
                    style={{
                      padding: isSmallMobile ? "10px 16px" : "12px 24px",
                      background: "#DC2626",
                      color: "#fff",
                      border: "none",
                      borderRadius: 8,
                      fontSize: isSmallMobile ? 12 : 14,
                      fontWeight: 600,
                      cursor: "pointer",
                    }}
                  >
                    {t('deleteAccount')}
                  </button>
                </div>
              </div>
            </div>
          )}

          {activeSection === "notifications" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('notificationsSettings')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('manageNotifications')}</p>

              <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                {Object.entries(notifications).map(([key, value]) => (
                  <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                        {t(key) || key.charAt(0).toUpperCase() + key.slice(1)}
                      </div>
                      <div style={{ fontSize: isSmallMobile ? 11 : 13, color: T.sub }}>
                        {t('receiveNotifications')} {t(key) || key}
                      </div>
                    </div>
                    <label style={{ position: "relative", display: "inline-block", width: 48, height: 28 }}>
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={async (e) => {
                          const newValue = e.target.checked;
                          setNotifications({ ...notifications, [key]: newValue });
                          
                          // Save to backend
                          try {
                            await api.updateNotificationSettings({ [key]: newValue });
                            
                            // Show notification when enabled
                            if (newValue) {
                              setModal({
                                isOpen: true,
                                title: t('notificationEnabled'),
                                message: `${t('willReceive')} ${t(key) || key}`,
                                type: 'success',
                                onConfirm: null
                              });
                            }
                          } catch (error) {
                            console.error('Failed to update notification settings:', error);
                          }
                        }}
                        style={{ opacity: 0, width: 0, height: 0 }}
                      />
                      <span style={{
                        position: "absolute",
                        cursor: "pointer",
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: value ? T.pri : "#ccc",
                        borderRadius: 28,
                        transition: "0.3s",
                      }}>
                        <span style={{
                          position: "absolute",
                          content: "",
                          height: 20,
                          width: 20,
                          left: value ? 24 : 4,
                          bottom: 4,
                          background: "#fff",
                          borderRadius: "50%",
                          transition: "0.3s",
                        }} />
                      </span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSection === "privacy" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('privacy')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('controlPrivacy')}</p>

              <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
                {Object.entries(privacy).map(([key, value]) => (
                  <div key={key} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <div>
                      <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                        {key.replace(/([A-Z])/g, ' $1').trim().split(' ').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' ')}
                      </div>
                      <div style={{ fontSize: isSmallMobile ? 11 : 13, color: T.sub }}>
                        {key === 'privateAccount' && t('privateAccountDesc')}
                        {key === 'showActivity' && t('showActivityDesc')}
                        {key === 'allowMessages' && t('allowMessagesDesc')}
                      </div>
                    </div>
                    <label style={{ position: "relative", display: "inline-block", width: 48, height: 28 }}>
                      <input
                        type="checkbox"
                        checked={value}
                        onChange={async (e) => {
                          const newValue = e.target.checked;
                          setPrivacy({ ...privacy, [key]: newValue });
                          
                          // Save to backend
                          try {
                            await api.updatePrivacySettings({ [key]: newValue });
                            
                            // Show confirmation modal
                            setModal({
                              isOpen: true,
                              title: t('privacyUpdated'),
                              message: `${t('privacySettingChanged')} "${key.replace(/([A-Z])/g, ' $1').trim()}" ${t(newValue ? 'enabled' : 'disabled')}`,
                              type: 'success',
                              onConfirm: null
                            });
                          } catch (error) {
                            console.error('Failed to update privacy settings:', error);
                            // Revert on error
                            setPrivacy({ ...privacy, [key]: !newValue });
                          }
                        }}
                        style={{ opacity: 0, width: 0, height: 0 }}
                      />
                      <span style={{
                        position: "absolute",
                        cursor: "pointer",
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: value ? T.pri : "#ccc",
                        borderRadius: 28,
                        transition: "0.3s",
                      }}>
                        <span style={{
                          position: "absolute",
                          content: "",
                          height: 20,
                          width: 20,
                          left: value ? 24 : 4,
                          bottom: 4,
                          background: "#fff",
                          borderRadius: "50%",
                          transition: "0.3s",
                        }} />
                      </span>
                    </label>
                  </div>
                ))}
              </div>
            </div>
          )}

          {activeSection === "appearance" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('appearance')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('customizeAppearance')}</p>

              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: 20, background: T.bg, borderRadius: 12 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
                  {darkMode ? <Moon size={24} color={T.pri} /> : <Sun size={24} color={T.pri} />}
                  <div>
                    <div style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                      {t('darkMode')}
                    </div>
                    <div style={{ fontSize: isSmallMobile ? 11 : 13, color: T.sub }}>
                      {darkMode ? t('darkEnabled') : t('lightEnabled')}
                    </div>
                  </div>
                </div>
                <label style={{ position: "relative", display: "inline-block", width: 48, height: 28 }}>
                  <input
                    type="checkbox"
                    checked={darkMode}
                    onChange={toggleDarkMode}
                    style={{ opacity: 0, width: 0, height: 0 }}
                  />
                  <span style={{
                    position: "absolute",
                    cursor: "pointer",
                    top: 0,
                    left: 0,
                    right: 0,
                    bottom: 0,
                    background: darkMode ? T.pri : "#ccc",
                    borderRadius: 28,
                    transition: "0.3s",
                  }}>
                    <span style={{
                      position: "absolute",
                      content: "",
                      height: 20,
                      width: 20,
                      left: darkMode ? 24 : 4,
                      bottom: 4,
                      background: "#fff",
                      borderRadius: "50%",
                      transition: "0.3s",
                    }} />
                  </span>
                </label>
              </div>
            </div>
          )}

          {activeSection === "language" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('language')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('chooseLanguage')}</p>

              <select
                value={language}
                onChange={(e) => changeLanguage(e.target.value)}
                style={{
                  width: "100%",
                  padding: "12px 16px",
                  border: `1px solid ${T.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  background: T.cardBg,
                  color: T.txt,
                  cursor: "pointer",
                }}
              >
                <option value="en">English</option>
                <option value="am">አማርኛ (Amharic)</option>
                <option value="es">Español</option>
                <option value="fr">Français</option>
                <option value="ar">العربية</option>
              </select>
            </div>
          )}

          {activeSection === "help" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('help')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 32 }}>{t('getHelp')}</p>

              <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
                <button style={{
                  padding: isSmallMobile ? "12px 16px" : "16px 20px",
                  background: T.bg,
                  border: `1px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  textAlign: "left",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}>
                  <span style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt }}>{t('helpCenter')}</span>
                  <ChevronRight size={20} color={T.sub} />
                </button>

                <button style={{
                  padding: isSmallMobile ? "12px 16px" : "16px 20px",
                  background: T.bg,
                  border: `1px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  textAlign: "left",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}>
                  <span style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt }}>{t('reportProblem')}</span>
                  <ChevronRight size={20} color={T.sub} />
                </button>

                <button onClick={() => window.open('/legal/terms-of-service', '_blank')} style={{
                  padding: isSmallMobile ? "12px 16px" : "16px 20px",
                  background: T.bg,
                  border: `1px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  textAlign: "left",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}>
                  <span style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt }}>{t('termsOfService')}</span>
                  <ChevronRight size={20} color={T.sub} />
                </button>

                <button onClick={() => window.open('/legal/privacy-policy', '_blank')} style={{
                  padding: isSmallMobile ? "12px 16px" : "16px 20px",
                  background: T.bg,
                  border: `1px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  textAlign: "left",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                }}>
                  <span style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt }}>{t('privacyPolicy')}</span>
                  <ChevronRight size={20} color={T.sub} />
                </button>

                <div style={{ marginTop: 20, padding: isSmallMobile ? 16 : 20, background: T.bg, borderRadius: 12, textAlign: "center" }}>
                  <div style={{ fontSize: isSmallMobile ? 11 : 13, color: T.sub, marginBottom: 4 }}>{t('version')}</div>
                  <div style={{ fontSize: isSmallMobile ? 13 : 15, fontWeight: 600, color: T.txt }}>FlipStar 1.0.0</div>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Custom Modal */}
      {modal.isOpen && (
        <div
          style={{
            position: "fixed",
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: "rgba(0,0,0,0.8)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 10000,
          }}
          onClick={() => setModal({ ...modal, isOpen: false })}
        >
          <div
            style={{
              background: T.cardBg,
              borderRadius: 16,
              padding: isSmallMobile ? 16 : "24px",
              maxWidth: isSmallMobile ? 320 : 400,
              width: "90%",
              boxShadow: "0 8px 32px rgba(0,0,0,0.3)",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ 
              fontSize: isSmallMobile ? 16 : 20, 
              fontWeight: 700, 
              color: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#F59E0B' : modal.type === 'success' ? '#10B981' : T.txt, 
              marginBottom: 12 
            }}>
              {modal.title}
            </h3>
            <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.txt, lineHeight: 1.6, marginBottom: 20 }}>
              {modal.message}
            </p>
            
            <div style={{ display: "flex", gap: 12, justifyContent: "flex-end" }}>
              {modal.onConfirm && (
                <button
                  onClick={() => setModal({ ...modal, isOpen: false })}
                  style={{
                    padding: isSmallMobile ? "8px 16px" : "10px 20px",
                    border: `1px solid ${T.border}`,
                    borderRadius: 8,
                    background: T.cardBg,
                    cursor: "pointer",
                    fontSize: isSmallMobile ? 12 : 14,
                    fontWeight: 600,
                    color: T.txt,
                  }}
                >
                  {t('cancel')}
                </button>
              )}
              <button
                onClick={() => {
                  if (modal.onConfirm) {
                    modal.onConfirm();
                  }
                  setModal({ ...modal, isOpen: false });
                }}
                style={{
                  padding: isSmallMobile ? "8px 16px" : "10px 20px",
                  border: "none",
                  borderRadius: 8,
                  background: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#F59E0B' : modal.type === 'success' ? '#10B981' : T.pri,
                  cursor: "pointer",
                  fontSize: isSmallMobile ? 12 : 14,
                  fontWeight: 600,
                  color: "#fff",
                }}
              >
                {modal.onConfirm ? t('confirm') : t('ok')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}




