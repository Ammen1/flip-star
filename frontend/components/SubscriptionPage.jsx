import { useState, useEffect, useRef } from 'react';
import {
  Crown, Zap, Calendar, Coins, Check, X, ChevronLeft,
  Star, Trophy, Gem, MessageCircle, Info, Video, Ban,
} from 'lucide-react';
import api from '../api';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';

const getFallbackTiers = () => [
  {
    id: 1,
    name: 'Daily',
    duration_type: 'daily',
    price_etb: 3,
    price_coins: null,
    description: 'Access for 24 hours'
  },
  {
    id: 2,
    name: 'Weekly',
    duration_type: 'weekly',
    price_etb: 20,
    price_coins: null,
    description: 'Access for 7 days'
  },
  {
    id: 3,
    name: 'Monthly',
    duration_type: 'monthly',
    price_etb: 70,
    price_coins: null,
    description: 'Access for 30 days'
  },
];

export function SubscriptionPage({ user, onBack }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  
  const [tiers, setTiers] = useState(getFallbackTiers());
  const [currentSubscription, setCurrentSubscription] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedTier, setSelectedTier] = useState(null);
  const [processing, setProcessing] = useState(false);
  const [processingTierId, setProcessingTierId] = useState(null);
  const [smsSent, setSmsSent] = useState(false);
  const [pendingTier, setPendingTier] = useState(null);
  const [pollCount, setPollCount] = useState(0);
  const [confirmed, setConfirmed] = useState(false);
  // Inline toast state — replaces native alert() popups for the on-demand flow
  // so users don't get a system "message box" interrupting them.
  const [toast, setToast] = useState(null); // { type: 'success'|'error'|'info', text: string }
  const toastTimer = useRef(null);
  const showToast = (type, text, ms = 2800) => {
    setToast({ type, text });
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), ms);
  };
  const pollRef = useRef(null);
  const POLL_INTERVAL = 5000;
  const MAX_POLLS = 36; // 3 minutes

  useEffect(() => {
    // Load tiers and subscription in background
    loadSubscriptionData();
  }, []);

  const loadSubscriptionData = async () => {
    try {
      // Fetch both in parallel but don't block UI
      const [tiersData, subscriptionData] = await Promise.all([
        api.request('/subscriptions/tiers/active/').catch(() => []),
        api.request('/subscriptions/').catch(() => null),
      ]);
      // Only update tiers if API returns valid data
      if (Array.isArray(tiersData) && tiersData.length > 0) {
        // Filter out OnDemand tier
        const filteredTiers = tiersData.filter(tier => tier.name !== 'OnDemand');
        setTiers(filteredTiers);
      }
      setCurrentSubscription(subscriptionData);
    } catch (error) {
      console.error('Error loading subscription data:', error);
      // Keep using fallback tiers without OnDemand
      const fallbackTiers = getFallbackTiers().filter(tier => tier.name !== 'OnDemand');
      setTiers(fallbackTiers);
    }
  };

  const startPolling = (tier) => {
    let count = 0;
    pollRef.current = setInterval(async () => {
      count++;
      setPollCount(count);
      try {
        const sub = await api.request('/subscriptions/');
        if (sub && sub.status === 'active') {
          clearInterval(pollRef.current);
          setCurrentSubscription(sub);
          setConfirmed(true);
        }
      } catch {}
      if (count >= MAX_POLLS) {
        clearInterval(pollRef.current);
      }
    }, POLL_INTERVAL);
  };

  const stopPolling = () => {
    if (pollRef.current) clearInterval(pollRef.current);
    setSmsSent(false);
    setPendingTier(null);
    setPollCount(0);
    setConfirmed(false);
  };

  const handleSubscribe = async (tier) => {
    // For regular subscriptions, use SMS
    const tierCode = tier.duration_type === 'daily' ? 'OK1' :
                     tier.duration_type === 'weekly' ? 'OK2' :
                     tier.duration_type === 'monthly' ? 'OK3' : 'OK4';
    const shortCode = tier.short_code || '9286';
    const smsUrl = `sms:${shortCode}?body=${encodeURIComponent(tierCode)}`;
    window.location.href = smsUrl;
  };

  const handleTelebirrSubscribe = async (tier) => {
    setProcessing(true);
    setProcessingTierId(tier.id);
    try {
      const frequency = tier.duration_type === 'daily' ? '02' :
                       tier.duration_type === 'weekly' ? '03' :
                       tier.duration_type === 'monthly' ? '05' : '05';
      
      const response = await api.request('/direct-debit/create/', {
        method: 'POST',
        body: JSON.stringify({
          tier_id: tier.id,
          payer_msisdn: user.phone || '',
          frequency: frequency,
        }),
      });

      if (response.success) {
        showToast('success', `Mandate created! Ref: ${response.payer_reference_number}. Please confirm via Telebirr app.`);
        // Start polling for mandate activation
        startPolling(tier);
      } else {
        showToast('error', response.error || 'Failed to create mandate');
      }
    } catch (error) {
      console.error('Telebirr subscription error:', error);
      showToast('error', 'Failed to process Telebirr subscription');
    } finally {
      setProcessing(false);
      setProcessingTierId(null);
    }
  };


  const handlePayment = async () => {
    if (!selectedTier) return;

    setProcessing(true);
    try {
      const response = await api.request('/subscriptions/subscribe/', {
        method: 'POST',
        body: JSON.stringify({
          tier_id: selectedTier.id,
          payment_method: paymentMethod,
        }),
      });

      if (response.status === 'success' || response.status === 'pending') {
        if (response.payment_url) {
          // Redirect to payment URL for telebirr
          window.open(response.payment_url, '_blank');
        }
        alert(response.message || 'Subscription initiated successfully');
        setShowPaymentModal(false);
        loadSubscriptionData();
      } else {
        alert(response.error || 'Failed to subscribe');
      }
    } catch (error) {
      console.error('Subscription error:', error);
      alert('Failed to process subscription');
    } finally {
      setProcessing(false);
    }
  };

  const handleUnsubscribe = async () => {
    if (confirm('Are you sure you want to cancel your subscription?')) {
      try {
        await api.request('/subscriptions/unsubscribe/', {
          method: 'POST',
        });
        alert('Subscription cancelled successfully');
        loadSubscriptionData();
      } catch (error) {
        alert('Failed to cancel subscription');
      }
    }
  };

  // ── Mobile-app design tokens (mirrors mobile-app/src/screens/SubscriptionScreen.js) ──
  const M_BG     = '#0B0B0C';
  const M_CARD   = '#161616';
  const M_BORDER = '#242424';
  const GOLD     = '#8fc441';
  const PLAN_COLORS = { daily: '#F59E0B', weekly: '#8B5CF6', monthly: GOLD };
  const PLAN_ICON   = { daily: Zap,       weekly: Star,      monthly: Trophy };
  const BENEFITS = [
    { icon: Video,  text: 'HD Videos' },
    { icon: Ban,    text: 'No Ads' },
    { icon: Star,   text: 'Exclusive Content' },
    { icon: Trophy, text: 'Campaign Priority' },
  ];

  const getTierColor = (durationType) => PLAN_COLORS[durationType] || GOLD;
  const getTierIcon  = (durationType) => PLAN_ICON[durationType] || Crown;

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: '#666', background: M_BG, minHeight: '100vh' }}>
        Loading subscription data…
      </div>
    );
  }

  const isActive = currentSubscription?.status === 'active';

  return (
    <div style={{ minHeight: '100vh', background: M_BG, color: '#fff' }}>
      {/* Header */}
      <div style={{
        background: M_CARD,
        padding: '12px 16px',
        borderBottom: `1px solid ${M_BORDER}`,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        position: 'sticky',
        top: 0,
        zIndex: 10,
      }}>
        <button
          onClick={onBack}
          style={{
            width: 36, height: 36, borderRadius: 18,
            background: '#1a1a1a',
            border: 'none', cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: '#fff',
          }}
          aria-label="Back"
        >
          <ChevronLeft size={22} />
        </button>
        <div style={{ fontSize: 17, fontWeight: 700 }}>Premium</div>
        <div style={{ width: 36 }} />
      </div>

      <div style={{ maxWidth: 520, margin: '0 auto', paddingBottom: 32 }}>
        {/* Hero */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 24px' }}>
          <div style={{
            width: 80, height: 80, borderRadius: 40,
            background: '#8fc44118',
            border: `1.5px solid #8fc44140`,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            marginBottom: 16,
          }}>
            <Trophy size={36} color="#8fc441" />
          </div>
          <div style={{ fontSize: 26, fontWeight: 900, marginBottom: 6 }}>FlipStar Premium</div>
          <div style={{ fontSize: 14, color: '#666', textAlign: 'center' }}>Unlock the full experience</div>
          {isActive && currentSubscription?.end_date && (
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: '#0D2D1A', padding: '7px 14px', borderRadius: 20,
              marginTop: 14, border: '1px solid #10B98140',
            }}>
              <span style={{ width: 7, height: 7, borderRadius: 4, background: '#10B981' }} />
              <span style={{ color: '#10B981', fontSize: 13, fontWeight: 600 }}>
                Active · expires {new Date(currentSubscription.end_date).toLocaleDateString()}
              </span>
            </div>
          )}
        </div>

        {/* Benefits row */}
        <div style={{
          display: 'flex', flexWrap: 'wrap', gap: 8,
          padding: '0 16px', marginBottom: 28, justifyContent: 'center',
        }}>
          {BENEFITS.map((b, i) => {
            const BIcon = b.icon;
            return (
              <div key={i} style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: M_CARD, borderRadius: 20,
                padding: '7px 12px',
                border: `1px solid ${M_BORDER}`,
              }}>
                <BIcon size={16} color="#8fc441" />
                <span style={{ fontSize: 12, color: '#ccc', fontWeight: 500 }}>{b.text}</span>
              </div>
            );
          })}
        </div>

        {/* Section label */}
        <div style={{
          fontSize: 13, fontWeight: 700, color: '#555',
          padding: '0 16px', marginBottom: 12,
          letterSpacing: 1, textTransform: 'uppercase',
        }}>
          {isActive ? 'Add On-Demand Access' : 'Choose a plan'}
        </div>

        {/* Plan cards - horizontal on desktop, stack on mobile */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 14,
          padding: '0 16px',
        }}>
          {tiers.map((tier) => {
              const TierIcon = getTierIcon(tier.duration_type);
              const color = getTierColor(tier.duration_type);
              const isCurrent = isActive && currentSubscription?.tier?.id === tier.id;
              const isProcessingThis = processing && processingTierId === tier.id;

              return (
                <div
                  key={tier.id}
                  style={{
                    background: isCurrent ? '#0D2D1A18' : M_CARD,
                    borderRadius: 20,
                    padding: 18,
                    border: `1.5px solid ${isCurrent ? '#10B98150' : M_BORDER}`,
                    position: 'relative',
                  }}
                >
                {isCurrent && (
                  <div style={{
                    position: 'absolute', top: -10, right: 16,
                    background: color,
                    padding: '3px 10px', borderRadius: 10,
                    color: '#000', fontSize: 10, fontWeight: 800,
                  }}>
                    Current
                  </div>
                )}

                {/* Top: icon + name/desc + price */}
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 14 }}>
                  <div style={{
                    width: 46, height: 46, borderRadius: 14,
                    background: color + '22',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                  }}>
                    <TierIcon size={22} color={color} />
                  </div>
                  <div style={{ flex: 1, marginLeft: 14, minWidth: 0 }}>
                    <div style={{ fontSize: 16, fontWeight: 800, color: '#fff', marginBottom: 2 }}>
                      {tier.name}
                    </div>
                    <div style={{ fontSize: 12, color: '#666' }}>{tier.description}</div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', flexShrink: 0 }}>
                    <div style={{ fontSize: 24, fontWeight: 900, color, lineHeight: '26px' }}>
                      {tier.price_etb}
                    </div>
                    <div style={{ fontSize: 11, color: '#666', fontWeight: 600 }}>ETB</div>
                  </div>
                </div>

                {/* CTA buttons */}
                {!isCurrent && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                    <button
                      onClick={() => handleTelebirrSubscribe(tier)}
                      disabled={isProcessingThis}
                      style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                        background: isProcessingThis ? '#222' : '#8fc441',
                        color: isProcessingThis ? '#666' : '#000',
                        border: 'none', borderRadius: 14, padding: 13,
                        fontSize: 14, fontWeight: 800,
                        cursor: isProcessingThis ? 'wait' : 'pointer',
                        opacity: isProcessingThis ? 0.7 : 1,
                        transition: 'transform 0.15s, opacity 0.15s',
                      }}
                      onMouseOver={(e) => {
                        if (isProcessingThis) return;
                        e.currentTarget.style.transform = 'translateY(-1px)';
                      }}
                      onMouseOut={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
                    >
                      <Trophy size={15} color={isProcessingThis ? '#666' : '#000'} />
                      {isProcessingThis ? 'Processing…' : 'Subscribe via Telebirr'}
                    </button>
                    <button
                      onClick={() => handleSubscribe(tier)}
                      disabled={isProcessingThis}
                      style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                        background: isProcessingThis ? '#222' : color,
                        color: isProcessingThis ? '#666' : '#000',
                        border: 'none', borderRadius: 14, padding: 13,
                        fontSize: 14, fontWeight: 800,
                        cursor: isProcessingThis ? 'wait' : 'pointer',
                        opacity: isProcessingThis ? 0.7 : 1,
                        transition: 'transform 0.15s, opacity 0.15s',
                      }}
                      onMouseOver={(e) => {
                        if (isProcessingThis) return;
                        e.currentTarget.style.transform = 'translateY(-1px)';
                      }}
                      onMouseOut={(e) => { e.currentTarget.style.transform = 'translateY(0)'; }}
                    >
                      <MessageCircle size={15} color={isProcessingThis ? '#666' : '#000'} />
                      {'Subscribe via SMS'}
                    </button>
                  </div>
                )}
                {isCurrent && (
                  <button
                    disabled
                    style={{
                      width: '100%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 7,
                      background: '#222',
                      color: '#666',
                      border: 'none', borderRadius: 14, padding: 13,
                      fontSize: 14, fontWeight: 800,
                      cursor: 'default',
                    }}
                  >
                    <Check size={15} color="#666" />
                    Active Plan
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Payment info */}
        <div style={{
          display: 'flex', gap: 10, alignItems: 'flex-start',
          margin: '4px 16px 0',
          background: M_CARD, borderRadius: 14, padding: 14,
          border: `1px solid ${M_BORDER}`,
        }}>
          <Info size={18} color="#8fc441" style={{ flexShrink: 0, marginTop: 1 }} />
          <div style={{ flex: 1, fontSize: 12, color: '#666', lineHeight: 1.6 }}>
            <div style={{ marginBottom: 6 }}>
              <strong style={{ color: '#8fc441' }}>Telebirr:</strong> One-tap subscription via Telebirr app. Auto-renew enabled.
            </div>
            <div>
              <strong style={{ color: '#8fc441' }}>SMS:</strong> Send SMS to <span style={{ color: "#8fc441", fontWeight: 700 }}>9286</span> with code{' '}
              <span style={{ color: '#fff' }}>OK1</span> (Daily),{' '}
              <span style={{ color: '#fff' }}>OK2</span> (Weekly),{' '}
              <span style={{ color: '#fff' }}>OK3</span> (Monthly) via Ethio Telecom.
            </div>
          </div>
        </div>
      </div>

      {/* Inline toast — replaces native alert() popups for the on-demand
          (airtime) flow. Stays out of the way and auto-dismisses. */}
      {toast && (
        <div
          role="status"
          aria-live="polite"
          style={{
            position: 'fixed',
            left: '50%',
            bottom: 32,
            transform: 'translateX(-50%)',
            background: toast.type === 'success'
              ? '#10B981'
              : toast.type === 'error'
              ? '#EF4444'
              : 'rgba(20,20,20,0.92)',
            color: '#fff',
            padding: '12px 18px',
            borderRadius: 999,
            fontSize: 14,
            fontWeight: 600,
            boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
            zIndex: 10001,
            maxWidth: '90vw',
            textAlign: 'center',
          }}
        >
          {toast.text}
        </div>
      )}
    </div>
  );
}


