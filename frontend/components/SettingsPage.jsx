import { useState, useEffect } from "react";
import {
  X, User, Bell, Lock, Globe, HelpCircle, LogOut, ChevronRight, Moon, Sun, Wallet,
  ChevronLeft, MessageCircle, Heart, Users as UsersIcon, Mail, Eye, EyeOff, Activity,
  Trash2, Check, Crown, ChevronUp, ChevronDown, Zap
} from "lucide-react";
import api from "../api";
import config from "../config";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import { BoostDashboard } from "./BoostDashboard";

const FAQ_ITEMS = [
  { q: "What is FlipStar?", a: "FlipStar is a premium, subscription-based gamified social media platform by Ethio Telecom and Skykin Technologies PLC. Upload short videos and photos ('Flips'), compete in campaigns, earn coins, and participate in a creator economy powered by telebirr." },
  { q: "Who can use FlipStar?", a: "All active Ethio Telecom prepaid, postpaid, and hybrid mobile customers with a smartphone (Android, iOS) or web browser. Users must be at least 13 years old. For claiming prizes, users must be 18 or older." },
  { q: "What devices and platforms does FlipStar support?", a: "Android App: Available on Google Play Store (search: FlipStar). iOS App: Available on Apple App Store (search: FlipStar). Web: Visit https://flipstar.et in any modern browser." },
  { q: "Is FlipStar available to all Ethio Telecom customers?", a: "Yes. All active prepaid, postpaid, and hybrid Ethio Telecom mobile customers can subscribe and use the service. The subscriber's number must be in 'Active' status at the time of subscription." },
  { q: "How do I subscribe to FlipStar?", a: "Via SMS: Send 'OK' to the FlipStar shortcode. Via App/Web: Download the app or visit https://flipstar.et, select 'Sign Up', enter your full name and mobile number, then enter the confirmation code sent to your number." },
  { q: "What subscription plans are available?", a: "Flip Daily: 3 ETB/24hrs • Flip Weekly: 20 ETB/7days • Flip Monthly: 70 ETB/30days • Flip Yearly: 600 ETB/365days • Flip On-Demand: 10 ETB for 100 Coins (one-time purchase)." },
  { q: "Is there a free trial?", a: "Yes. New subscribers receive a 1-day (24-hour) free trial on their first subscription. Re-subscribers who previously used the trial are not eligible for another." },
  { q: "How am I charged?", a: "Prepaid: fee deducted from airtime balance. Postpaid: fee added to monthly bill. Hybrid: charged from your default account. A maximum of one charge applies per 24-hour cycle. Failed charges are retried automatically if you recharge the same day." },
  { q: "How do I unsubscribe?", a: "Send 'STOP' to the FlipStar shortcode, or go to Account Settings in the app and select Unsubscribe. Your request is processed immediately and you will receive a confirmation SMS." },
  { q: "What happens to my coins and progress if I unsubscribe?", a: "Your coins and digital assets remain valid for 30 days after unsubscription. Re-subscribing within 30 days restores your unexpired coins and progress. Assets not recovered within 30 days will expire." },
  { q: "What are coins and how do I earn them?", a: "Coins are FlipStar's digital currency. Earn them through: Daily login bonus (3 coins/day), Weekly loyalty bonus (50 coins for 7-day streak), or Purchase (1 ETB = 10 Coins via telebirr/Airtime)." },
  { q: "What can I do with coins?", a: "Gift creators, boost your content visibility, unlock extended video uploads (up to 90-120 seconds), level up, and unlock premium features." },
  { q: "Can I cash out my coins?", a: "Bonus coins (from login/loyalty) cannot be cashed out. However, Points earned by creators from gifts can be cashed out via telebirr. Minimum: 1,000 Points (80 ETB after 20% commission)." },
  { q: "What is the platform commission?", a: "A 20% commission applies to all gifting transaction payouts. For example: if a creator earns 1,000 Points, 200 Points (20%) are retained as platform commission, and the creator receives 800 Points (80 ETB) via telebirr." },
  { q: "Can I convert my Points back into Coins?", a: "Yes. The swap rate is 1 Point = 1 Coin. You can use earned Points to purchase more Coins for in-app spending instead of cashing out." },
  { q: "What is a Flip and how do I upload one?", a: "A Flip is a short video (15–120 seconds) or photo you upload to the platform. Tap the '+' button, select or record your content, add a caption and hashtags, optionally link it to a campaign, and tap 'Post'." },
  { q: "How long can my videos be?", a: "Standard subscribers: 15 to 60 seconds. Coin buyers (On-Demand / premium): up to 90–120 seconds." },
  { q: "What are the competition prizes?", a: "Daily Sprint (50 winners): 1GB data • Weekly Battle (10 winners): 1,000 ETB • Monthly Star (5 winners): 10,000 ETB • Grand Final: 1st-500,000 ETB, 2nd-300,000 ETB, 3rd-200,000 ETB." },
  { q: "How is my competition score calculated?", a: "Score = (Likes × 1) + (Comments × 2) + (Shares × 5) + (Gift/Vote Points × 10). The highest Engagement Score wins each tier." },
  { q: "Can I win multiple prizes?", a: "Yes, with rules. After winning a tier, you're ineligible for that same tier for 30 days. You can still win other tiers during the cooldown. Eligibility restores after 30 days." },
  { q: "How do I claim my prize?", a: "Cash prizes (ETB): sent automatically via telebirr. Daily Data prizes: credited to your Ethio Telecom account within 24 hours. Grand Final prizes: our team will contact you — you must present a valid National ID or passport. All prizes must be claimed within 30 days of notification." },
  { q: "Is there a daily voting limit for one creator?", a: "Yes. A single user can contribute a maximum of 5,000 Score Points (equivalent to 500 Coins) per day to any one specific creator. This Voting Cap prevents pay-to-win behaviour and protects competition integrity." },
  { q: "Do boosted views count toward my leaderboard score?", a: "No. Views and impressions from paid content boosts (Standard, Premium, or Viral Boost) do not count toward your organic Engagement Score. Only genuine, unboosted engagement contributes to your score." },
  { q: "Are there internet data charges for using FlipStar?", a: "Yes. Accessing FlipStar via the app or web portal at https://flipstar.et uses your regular Ethio Telecom data plan. You are responsible for any data charges incurred." },
  { q: "Is my personal data safe?", a: "Yes. FlipStar is hosted on Ethio Telecom InfraCloud within Ethiopia. Your phone number is encrypted and never displayed publicly. All personal metadata is removed from uploads." },
  { q: "Can Ethio Telecom change the Terms or cancel the service?", a: "Yes. Ethio Telecom reserves the right to modify, suspend, or terminate the FlipStar service at any time in accordance with Ethiopian laws. Changes will be published at https://flipstar.et. Continued use after changes take effect constitutes acceptance." },
  { q: "How do I contact support?", a: "In-App: Profile → Help & Support • Email: support@flipstar.et • SMS: 8994 • WhatsApp: +251 99 400 0000 • Telegram: t.me/ethio_telecom • Web: ethiotelecom.et" },
];

const SUPPORT_CATEGORIES = [
  { value: 'account', label: 'Account' },
  { value: 'payment', label: 'Payment / Wallet' },
  { value: 'technical', label: 'Technical Issue' },
  { value: 'content', label: 'Content / Post' },
  { value: 'abuse', label: 'Abuse / Report' },
  { value: 'suggestion', label: 'Suggestion / Feedback' },
  { value: 'other', label: 'Other' },
];

const STATUS_STYLES = {
  received: { color: '#3B82F6', bg: '#DBEAFE', label: 'Received' },
  pending: { color: '#8fc441', bg: '#FEF3C7', label: 'Pending' },
  in_progress: { color: '#8B5CF6', bg: '#EDE9FE', label: 'In Progress' },
  solved: { color: '#10B981', bg: '#D1FAE5', label: 'Solved' },
  closed: { color: '#6B7280', bg: '#E5E7EB', label: 'Closed' },
};

const SupportSection = ({ compact = false, T, supportForm, setSupportForm, supportSubmitting, handleSubmitSupport, supportRequests }) => {
  const [expandedReqId, setExpandedReqId] = useState(null);
  return (
  <div>
    {/* Submit new request */}
    <div style={{
      background: T.cardBg || T.bg, border: `1px solid ${T.border}`, borderRadius: 12,
      padding: 16, marginBottom: 16,
    }}>
      <div style={{ fontSize: 15, fontWeight: 700, color: T.txt, marginBottom: 12 }}>Submit a Request</div>

      <label style={{ fontSize: 12, fontWeight: 600, color: T.sub, display: 'block', marginBottom: 6 }}>Category</label>
      <select
        value={supportForm.category}
        onChange={(e) => setSupportForm(f => ({ ...f, category: e.target.value }))}
        style={{
          width: '100%', padding: '10px 12px', borderRadius: 10,
          border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
          marginBottom: 10, fontSize: 14,
        }}
      >
        {SUPPORT_CATEGORIES.map(c => <option key={c.value} value={c.value}>{c.label}</option>)}
      </select>

      <label style={{ fontSize: 12, fontWeight: 600, color: T.sub, display: 'block', marginBottom: 6 }}>Subject</label>
      <input
        type="text"
        maxLength={200}
        value={supportForm.subject}
        onChange={(e) => setSupportForm(f => ({ ...f, subject: e.target.value }))}
        placeholder="Brief summary of your issue"
        style={{
          width: '100%', padding: '10px 12px', borderRadius: 10,
          border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
          marginBottom: 10, fontSize: 14, boxSizing: 'border-box',
        }}
      />

      <label style={{ fontSize: 12, fontWeight: 600, color: T.sub, display: 'block', marginBottom: 6 }}>Message</label>
      <textarea
        rows={compact ? 4 : 5}
        maxLength={5000}
        value={supportForm.message}
        onChange={(e) => setSupportForm(f => ({ ...f, message: e.target.value }))}
        placeholder="Describe your issue or request in detail"
        style={{
          width: '100%', padding: '10px 12px', borderRadius: 10,
          border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
          marginBottom: 12, fontSize: 14, boxSizing: 'border-box', resize: 'vertical',
        }}
      />

      <button
        onClick={handleSubmitSupport}
        disabled={supportSubmitting || !supportForm.subject.trim() || !supportForm.message.trim()}
        style={{
          width: '100%', padding: '12px 16px', borderRadius: 12, border: 'none',
          background: T.pri, color: '#000', fontSize: 14, fontWeight: 700,
          cursor: supportSubmitting ? 'not-allowed' : 'pointer',
          opacity: supportSubmitting || !supportForm.subject.trim() || !supportForm.message.trim() ? 0.6 : 1,
        }}
      >
        {supportSubmitting ? 'Submitting...' : 'Submit Request'}
      </button>
    </div>

    {/* My requests */}
    <div style={{ fontSize: 15, fontWeight: 700, color: T.txt, marginBottom: 10 }}>My Requests</div>
    {supportRequests.length === 0 ? (
      <div style={{ padding: 20, textAlign: 'center', color: T.sub, fontSize: 13 }}>
        You haven't submitted any requests yet.
      </div>
    ) : (
      supportRequests.map(req => {
        const s = STATUS_STYLES[req.status] || STATUS_STYLES.received;
        const isOpen = expandedReqId === req.id;
        return (
          <div key={req.id} style={{
            background: T.cardBg || T.bg, border: `1px solid ${T.border}`, borderRadius: 12,
            marginBottom: 10, overflow: 'hidden',
          }}>
            <button
              type="button"
              onClick={() => setExpandedReqId(isOpen ? null : req.id)}
              style={{
                width: '100%', background: 'none', border: 'none', cursor: 'pointer',
                padding: 14, textAlign: 'left',
                display: 'flex', alignItems: 'center', gap: 10,
              }}
            >
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                  <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{req.subject}</div>
                  <span style={{
                    fontSize: 11, fontWeight: 700, padding: '4px 10px', borderRadius: 999,
                    background: s.bg, color: s.color, flexShrink: 0,
                  }}>{s.label}</span>
                </div>
                <div style={{ fontSize: 12, color: T.sub }}>
                  {req.category_display} • {new Date(req.created_at).toLocaleDateString()}
                </div>
              </div>
              {isOpen
                ? <ChevronUp size={16} color={T.sub} style={{ flexShrink: 0 }} />
                : <ChevronDown size={16} color={T.sub} style={{ flexShrink: 0 }} />}
            </button>
            {isOpen && (
              <div style={{ padding: '0 14px 14px' }}>
                <div style={{ fontSize: 13, color: T.txt, whiteSpace: 'pre-wrap' }}>{req.message}</div>
                {req.admin_response && (
                  <div style={{
                    marginTop: 10, padding: 10, background: '#0F172A10',
                    border: `1px dashed ${T.border}`, borderRadius: 8,
                  }}>
                    <div style={{ fontSize: 11, fontWeight: 700, color: T.sub, marginBottom: 4 }}>Admin Response</div>
                    <div style={{ fontSize: 13, color: T.txt, whiteSpace: 'pre-wrap' }}>{req.admin_response}</div>
                  </div>
                )}
              </div>
            )}
          </div>
        );
      })
    )}
  </div>
  );
};

export function SettingsPage({ user, onClose, onLogout, onShowWallet, onShowSubscription, onShowEditProfile }) {
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
    if (user) {
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
    }
  }, [user]);

  useEffect(() => {
    // Fetch privacy settings from server
    if (user) {
      api.getPrivacySettings().then(data => {
        if (data) {
          setPrivacy({
            privateAccount: data.privateAccount ?? false,
            showActivity: data.showActivity ?? true,
            allowMessages: data.allowMessages ?? true,
          });
        }
      }).catch(() => {
        // Keep localStorage values if fetch fails - silent fail
      });
    }
  }, [user]);

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
  const [showFaqModal, setShowFaqModal] = useState(false);
  const [faqOpen, setFaqOpen] = useState(null);
  const [showBoostDashboard, setShowBoostDashboard] = useState(false);

  // Support / help requests
  const [supportRequests, setSupportRequests] = useState([]);
  const [supportForm, setSupportForm] = useState({ category: 'other', subject: '', message: '' });
  const [supportSubmitting, setSupportSubmitting] = useState(false);

  const loadSupportRequests = async () => {
    try {
      const data = await api.getMySupportRequests();
      setSupportRequests(data?.results || []);
    } catch (e) {
      console.error('Failed to load support requests', e);
    }
  };

  useEffect(() => {
    if (user) {
      loadSupportRequests();
    }
  }, [user]);

  const handleSubmitSupport = async () => {
    if (!supportForm.subject.trim() || !supportForm.message.trim()) {
      setModal({ isOpen: true, title: t('error'), message: 'Subject and message are required.', type: 'error', onConfirm: null });
      return;
    }
    try {
      setSupportSubmitting(true);
      await api.createSupportRequest(supportForm);
      setSupportForm({ category: 'other', subject: '', message: '' });
      await loadSupportRequests();
      setModal({ isOpen: true, title: t('success'), message: 'Your request has been submitted. We will get back to you soon.', type: 'success', onConfirm: null });
    } catch (e) {
      setModal({ isOpen: true, title: t('error'), message: e?.message || 'Failed to submit request', type: 'error', onConfirm: null });
    } finally {
      setSupportSubmitting(false);
    }
  };

  // FAQ Modal Component
  const FaqModal = () => {
    if (!showFaqModal) return null;
    
    return (
      <div onClick={() => setShowFaqModal(false)} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 9999, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
        <div onClick={e => e.stopPropagation()} style={{ background: T.cardBg || "#111", borderRadius: "18px 18px 0 0", width: "100%", maxWidth: 520, maxHeight: "88vh", overflowY: "auto", padding: "24px 20px 40px" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
            <div style={{ fontSize: 20, fontWeight: 900, color: "#8fc441" }}>FAQ</div>
            <button onClick={() => setShowFaqModal(false)} style={{ background: "none", border: "none", cursor: "pointer", color: "#8fc441" }}><X size={22} /></button>
          </div>
          {FAQ_ITEMS.map((item, i) => (
            <div key={i} style={{ borderBottom: "1px solid #262626", marginBottom: 2 }}>
              <button onClick={() => setFaqOpen(faqOpen === i ? null : i)}
                style={{ width: "100%", background: "none", border: "none", cursor: "pointer", padding: "14px 0", display: "flex", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 700, color: "#fff", textAlign: "left" }}>{item.q}</span>
                {faqOpen === i ? <ChevronUp size={16} color="#8fc441" style={{ flexShrink: 0 }} /> : <ChevronDown size={16} color="#8fc441" style={{ flexShrink: 0 }} />}
              </button>
              {faqOpen === i && <div style={{ fontSize: 13, color: "#ccc", paddingBottom: 14, lineHeight: 1.6 }}>{item.a}</div>}
            </div>
          ))}
        </div>
      </div>
    );
  };

  const sections = [
    { id: "account", icon: User, label: t('account') },
    { id: "wallet", icon: Wallet, label: 'Wallet', isExternal: true },
    { id: "subscription", icon: Crown, label: 'Subscription', isExternal: true },
    { id: "boost", icon: Zap, label: 'Boost Dashboard' },
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
        message: error?.message || t('passwordChangeFailed'),
        type: 'error',
        onConfirm: null
      });
    }
  };


  // ─── MOBILE UI (mimics mobile app SettingsScreen) ────────────────────────────
  const [showPassModal, setShowPassModal] = useState(false);
  const [showLangModal, setShowLangModal] = useState(false);
  const [passVisible, setPassVisible] = useState({ current: false, new: false, confirm: false });

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
            <Row icon={Zap} title="Boost Dashboard" subtitle="Manage your boosted posts" onPress={() => setShowBoostDashboard(true)} />
            <Row icon={Lock} title={t('changePassword')} onPress={() => setShowPassModal(true)} />
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
            <Row icon={Globe} title={t('language')} subtitle={language === 'en' ? 'English' : language} onPress={() => setShowLangModal(true)} />
          </SectionCard>

          {/* Help & Support */}
          <SectionLabel>{t('help')}</SectionLabel>
          <div style={{ background: T.cardBg, borderRadius: 16, padding: 16, marginBottom: 16 }}>
            <SupportSection compact T={T} supportForm={supportForm} setSupportForm={setSupportForm} supportSubmitting={supportSubmitting} handleSubmitSupport={handleSubmitSupport} supportRequests={supportRequests} />
          </div>
          <SectionCard>
            <Row icon={HelpCircle} title="Frequently Asked Questions" onPress={() => setShowFaqModal(true)} />
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
                    <div style={{ position: 'relative' }}>
                      <input
                        type={passVisible[f.key] ? 'text' : 'password'}
                        value={password[f.key]}
                        onChange={(e) => setPassword({ ...password, [f.key]: e.target.value })}
                        style={{
                          width: '100%', padding: 14, paddingRight: 44, borderRadius: 12,
                          border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
                          fontSize: 15, boxSizing: 'border-box', outline: 'none',
                        }}
                      />
                      <button
                        type="button"
                        onClick={() => setPassVisible(v => ({ ...v, [f.key]: !v[f.key] }))}
                        style={{
                          position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                          background: 'none', border: 'none', cursor: 'pointer', color: T.sub || '#888',
                          padding: 6, display: 'flex', alignItems: 'center',
                        }}
                        aria-label={passVisible[f.key] ? 'Hide password' : 'Show password'}
                      >
                        {passVisible[f.key] ? <EyeOff size={18} /> : <Eye size={18} />}
                      </button>
                    </div>
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
              <h3 style={{ margin: 0, fontSize: 17, fontWeight: 700, color: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#8fc441' : modal.type === 'success' ? '#10B981' : T.txt, marginBottom: 8 }}>{modal.title}</h3>
              <p style={{ margin: 0, fontSize: 14, color: T.txt, lineHeight: 1.5, marginBottom: 16 }}>{modal.message}</p>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                {modal.onConfirm && (
                  <button onClick={() => setModal({ ...modal, isOpen: false })} style={{ padding: '10px 16px', borderRadius: 10, border: `1px solid ${T.border}`, background: T.cardBg, color: T.txt, fontSize: 13, fontWeight: 600, cursor: 'pointer' }}>
                    {t('cancel')}
                  </button>
                )}
                <button
                  onClick={() => { if (modal.onConfirm) modal.onConfirm(); setModal({ ...modal, isOpen: false }); }}
                  style={{ padding: '10px 16px', borderRadius: 10, border: 'none', background: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#8fc441' : modal.type === 'success' ? '#10B981' : T.pri, color: '#fff', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
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
                    if (section.id === 'boost') {
                      setShowBoostDashboard(true);
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
                    {['current', 'new', 'confirm'].map((k) => (
                      <div key={k} style={{ position: 'relative' }}>
                        <input
                          type={passVisible[k] ? 'text' : 'password'}
                          inputMode="numeric"
                          maxLength={6}
                          placeholder="••••••"
                          value={password[k]}
                          onChange={(e) => setPassword({ ...password, [k]: e.target.value.replace(/\D/g, "").slice(0, 6) })}
                          style={{
                            width: "100%",
                            padding: isSmallMobile ? "10px 12px" : "12px 16px",
                            paddingRight: 44,
                            border: `1px solid ${T.border}`,
                            borderRadius: 8,
                            fontSize: isSmallMobile ? 12 : 14,
                            boxSizing: 'border-box',
                          }}
                        />
                        <button
                          type="button"
                          onClick={() => setPassVisible(v => ({ ...v, [k]: !v[k] }))}
                          style={{
                            position: 'absolute', right: 10, top: '50%', transform: 'translateY(-50%)',
                            background: 'none', border: 'none', cursor: 'pointer', color: T.sub || '#888',
                            padding: 6, display: 'flex', alignItems: 'center',
                          }}
                          aria-label={passVisible[k] ? 'Hide password' : 'Show password'}
                        >
                          {passVisible[k] ? <EyeOff size={18} /> : <Eye size={18} />}
                        </button>
                      </div>
                    ))}
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
              </select>
            </div>
          )}

          {activeSection === "help" && (
            <div>
              <h2 style={{ fontSize: isSmallMobile ? 18 : 24, fontWeight: 700, marginBottom: 8, color: T.txt }}>{t('help')}</h2>
              <p style={{ fontSize: isSmallMobile ? 12 : 14, color: T.sub, marginBottom: isSmallMobile ? 20 : 24 }}>{t('getHelp')}</p>

              <SupportSection T={T} supportForm={supportForm} setSupportForm={setSupportForm} supportSubmitting={supportSubmitting} handleSubmitSupport={handleSubmitSupport} supportRequests={supportRequests} />

              <div style={{ marginTop: 20, padding: 16, background: T.bg, borderRadius: 12, textAlign: 'center' }}>
                <div style={{ fontSize: 11, color: T.sub, marginBottom: 4 }}>{t('version')}</div>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.txt }}>FlipStar 1.0.0</div>
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
              color: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#8fc441' : modal.type === 'success' ? '#10B981' : T.txt, 
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
                  background: modal.type === 'error' ? '#EF4444' : modal.type === 'warning' ? '#8fc441' : modal.type === 'success' ? '#10B981' : T.pri,
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

      {/* FAQ Modal */}
      <FaqModal />

      {/* Boost Dashboard Modal */}
      {showBoostDashboard && (
        <BoostDashboard onClose={() => setShowBoostDashboard(false)} />
      )}
    </div>
  );
}




