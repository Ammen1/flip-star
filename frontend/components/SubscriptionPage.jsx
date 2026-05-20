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
  const [telebirrModalOpen, setTelebirrModalOpen] = useState(false);
  const [telebirrPhone, setTelebirrPhone] = useState('');
  const [selectedTierForTelebirr, setSelectedTierForTelebirr] = useState(null);
  const [successModalOpen, setSuccessModalOpen] = useState(false);
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
    const tierCode = tier.duration_type === 'daily' ? '1' :
                     tier.duration_type === 'weekly' ? '2' :
                     tier.duration_type === 'monthly' ? '3' : '4';
    const shortCode = tier.short_code || '9286';
    const smsUrl = `sms:${shortCode}?body=${encodeURIComponent(tierCode)}`;
    window.location.href = smsUrl;
  };

  const handleTelebirrSubscribe = async (tier) => {
    setSelectedTierForTelebirr(tier);
    // Fetch phone number from API like the coin purchase modal does
    try {
      const profile = await api.request('/profile/me/');
      setTelebirrPhone(profile?.phone_number || user?.profile?.phone_number || '');
    } catch (error) {
      console.error('Failed to fetch phone number:', error);
      setTelebirrPhone(user?.profile?.phone_number || '');
    }
    setTelebirrModalOpen(true);
  };

  const handleTelebirrProceed = async () => {
    if (!telebirrPhone || telebirrPhone.length < 10) {
      showToast('error', 'Please enter a valid phone number');
      return;
    }

    setProcessing(true);
    setProcessingTierId(selectedTierForTelebirr.id);
    setTelebirrModalOpen(false);

    try {
      const frequency = selectedTierForTelebirr.duration_type === 'daily' ? '02' :
                       selectedTierForTelebirr.duration_type === 'weekly' ? '03' :
                       selectedTierForTelebirr.duration_type === 'monthly' ? '05' : '05';
      
      const response = await api.request('/direct-debit/create/', {
        method: 'POST',
        body: JSON.stringify({
          tier_id: selectedTierForTelebirr.id,
          payer_msisdn: telebirrPhone,
          frequency: frequency,
        }),
      });

      if (response.success) {
        setSuccessModalOpen(true);
        setTimeout(() => setSuccessModalOpen(false), 3000);
        // Start polling for mandate activation
        startPolling(selectedTierForTelebirr);
      } else {
        showToast('error', response.error || 'Failed to create mandate');
      }
    } catch (error) {
      console.error('telebirr subscription error:', error);
      showToast('error', 'Failed to process telebirr subscription');
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

  const handleCancelTelebirrSubscription = async () => {
    if (!currentSubscription?.mandate_id) {
      showToast('error', 'No telebirr mandate found');
      return;
    }

    if (confirm('Are you sure you want to cancel your telebirr subscription?')) {
      setProcessing(true);
      try {
        const response = await api.request('/direct-debit/cancel/', {
          method: 'POST',
          body: JSON.stringify({
            mandate_id: currentSubscription.mandate_id,
          }),
        });

        if (response.success) {
          showToast('success', 'telebirr subscription cancelled successfully');
          loadSubscriptionData();
        } else {
          showToast('error', response.error || 'Failed to cancel telebirr subscription');
        }
      } catch (error) {
        console.error('Cancel telebirr subscription error:', error);
        showToast('error', 'Failed to cancel telebirr subscription');
      } finally {
        setProcessing(false);
      }
    }
  };

  // ── Mobile-app design tokens (mirrors mobile-app/src/screens/SubscriptionScreen.js) ──
  const M_BG     = '#0B0B0C';
  const M_CARD   = '#161616';
  const M_BORDER = '#242424';
  const BRAND_GREEN = '#8fc441';
  const PLAN_COLORS = { daily: BRAND_GREEN, weekly: BRAND_GREEN, monthly: BRAND_GREEN };
  const PLAN_ICON   = { daily: Zap,       weekly: Star,      monthly: Trophy };
  const BENEFITS = [
    { icon: Video,  text: 'HD Videos' },
    { icon: Ban,    text: 'No Ads' },
    { icon: Star,   text: 'Exclusive Content' },
    { icon: Trophy, text: 'Campaign Priority' },
  ];

  const getTierColor = (durationType) => PLAN_COLORS[durationType] || BRAND_GREEN;
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
        padding: '12px 16px',
        display: 'flex',
        alignItems: 'center',
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
      </div>

      <div style={{ maxWidth: '100%', margin: '0 auto', paddingBottom: 32 }}>
        {/* Hero */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', padding: '32px 24px' }}>
          <div style={{ fontSize: 32, fontWeight: 900, marginBottom: 8, color: '#fff' }}>FlipStar Premium</div>
          <div style={{ fontSize: 16, color: BRAND_GREEN, textAlign: 'center', fontWeight: 600 }}>Unlock the full experience</div>
          {isActive && currentSubscription?.end_date && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8, marginTop: 14 }}>
              <div style={{
                display: 'inline-flex', alignItems: 'center', gap: 6,
                background: '#0D2D1A', padding: '7px 14px', borderRadius: 20,
                border: '1px solid #10B98140',
              }}>
                <span style={{ width: 7, height: 7, borderRadius: 4, background: '#10B981' }} />
                <span style={{ color: '#10B981', fontSize: 13, fontWeight: 600 }}>
                  Active · expires {new Date(currentSubscription.end_date).toLocaleDateString()}
                </span>
              </div>
              {currentSubscription?.payment_method === 'telebirr_direct_debit' && (
                <button
                  onClick={handleCancelTelebirrSubscription}
                  disabled={processing}
                  style={{
                    background: '#EF4444',
                    color: '#fff',
                    border: 'none',
                    borderRadius: 12,
                    padding: '8px 16px',
                    fontSize: 13,
                    fontWeight: 600,
                    cursor: processing ? 'wait' : 'pointer',
                    opacity: processing ? 0.7 : 1,
                  }}
                >
                  Cancel telebirr Subscription
                </button>
              )}
            </div>
          )}
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
          gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
          gap: 20,
          padding: '0 16px',
          width: '100%',
          maxWidth: '1200px',
          margin: '0 auto',
        }}>
          {tiers.map((tier) => {
              const TierIcon = getTierIcon(tier.duration_type);
              const color = BRAND_GREEN;
              const isCurrent = isActive && currentSubscription?.tier?.id === tier.id;
              const isProcessingThis = processing && processingTierId === tier.id;

              return (
                <div
                  key={tier.id}
                  style={{
                    background: isCurrent ? BRAND_GREEN + '10' : M_CARD,
                    borderRadius: 24,
                    padding: 24,
                    border: `2px solid ${isCurrent ? BRAND_GREEN : M_BORDER}`,
                    position: 'relative',
                    transition: 'all 0.3s ease',
                  }}
                >
                {isCurrent && (
                  <div style={{
                    position: 'absolute', top: -12, right: 20,
                    background: BRAND_GREEN,
                    padding: '6px 16px', borderRadius: 20,
                    color: '#000', fontSize: 12, fontWeight: 800,
                    boxShadow: '0 4px 12px rgba(143,196,65,0.3)',
                  }}>
                    Current Plan
                  </div>
                )}

                {/* Top: icon + name/desc + price */}
                <div style={{ display: 'flex', alignItems: 'center', marginBottom: 20 }}>
                  <div style={{
                    width: 60, height: 60, borderRadius: 20,
                    background: BRAND_GREEN,
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    flexShrink: 0,
                    boxShadow: '0 8px 24px rgba(143,196,65,0.2)',
                  }}>
                    <TierIcon size={28} color="#fff" />
                  </div>
                  <div style={{ flex: 1, marginLeft: 16, minWidth: 0 }}>
                    <div style={{ fontSize: 18, fontWeight: 800, color: '#fff', marginBottom: 4 }}>
                      {tier.name}
                    </div>
                    <div style={{ fontSize: 13, color: '#666', fontWeight: 500 }}>
                      {tier.description}
                    </div>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', flexShrink: 0 }}>
                    <div style={{ fontSize: 32, fontWeight: 900, color: BRAND_GREEN, lineHeight: '34px' }}>
                      {tier.price_etb}
                    </div>
                    <div style={{ fontSize: 13, color: BRAND_GREEN, fontWeight: 600 }}>ETB</div>
                  </div>
                </div>

                {/* CTA buttons */}
                {!isCurrent && (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                    <button
                      onClick={() => handleTelebirrSubscribe(tier)}
                      disabled={isProcessingThis}
                      style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        background: isProcessingThis ? '#333' : BRAND_GREEN,
                        color: isProcessingThis ? '#666' : '#000',
                        border: 'none', borderRadius: 16, padding: 16,
                        fontSize: 15, fontWeight: 800,
                        cursor: isProcessingThis ? 'wait' : 'pointer',
                        opacity: isProcessingThis ? 0.7 : 1,
                        transition: 'all 0.3s ease',
                        boxShadow: isProcessingThis ? 'none' : '0 8px 24px rgba(143,196,65,0.3)',
                      }}
                      onMouseOver={(e) => {
                        if (isProcessingThis) return;
                        e.currentTarget.style.transform = 'translateY(-2px)';
                        e.currentTarget.style.boxShadow = '0 12px 32px rgba(143,196,65,0.4)';
                      }}
                      onMouseOut={(e) => { 
                        e.currentTarget.style.transform = 'translateY(0)';
                        e.currentTarget.style.boxShadow = '0 8px 24px rgba(143,196,65,0.3)';
                      }}
                    >
                      <Trophy size={16} color={isProcessingThis ? '#666' : '#000'} />
                      {isProcessingThis ? 'Processing…' : 'Subscribe via telebirr'}
                    </button>
                    <button
                      onClick={() => handleSubscribe(tier)}
                      disabled={isProcessingThis}
                      style={{
                        width: '100%',
                        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                        background: isProcessingThis ? '#333' : 'transparent',
                        color: isProcessingThis ? '#666' : BRAND_GREEN,
                        border: `2px solid ${isProcessingThis ? '#333' : BRAND_GREEN}`,
                        borderRadius: 16, padding: 14,
                        fontSize: 15, fontWeight: 800,
                        cursor: isProcessingThis ? 'wait' : 'pointer',
                        opacity: isProcessingThis ? 0.7 : 1,
                        transition: 'all 0.3s ease',
                      }}
                      onMouseOver={(e) => {
                        if (isProcessingThis) return;
                        e.currentTarget.style.background = BRAND_GREEN + '10';
                        e.currentTarget.style.transform = 'translateY(-1px)';
                      }}
                      onMouseOut={(e) => { 
                        e.currentTarget.style.background = 'transparent';
                        e.currentTarget.style.transform = 'translateY(0)';
                      }}
                    >
                      <MessageCircle size={16} color={isProcessingThis ? '#666' : BRAND_GREEN} />
                      {'Subscribe via SMS'}
                    </button>
                  </div>
                )}
                {isCurrent && (
                  <button
                    disabled
                    style={{
                      width: '100%',
                      display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
                      background: BRAND_GREEN + '15',
                      color: BRAND_GREEN,
                      border: `2px solid ${BRAND_GREEN}`,
                      borderRadius: 16, padding: 16,
                      fontSize: 15, fontWeight: 800,
                      cursor: 'default',
                    }}
                  >
                    <Check size={16} color={BRAND_GREEN} />
                    Active Plan
                  </button>
                )}
              </div>
            );
          })}
        </div>

        {/* Payment info */}
        <div style={{
          display: 'flex', gap: 12, alignItems: 'flex-start',
          margin: '4px 16px 0',
          background: BRAND_GREEN + '10', borderRadius: 16, padding: 16,
          border: `1px solid ${BRAND_GREEN}30`,
        }}>
          <Info size={20} color={BRAND_GREEN} style={{ flexShrink: 0, marginTop: 2 }} />
          <div style={{ flex: 1, fontSize: 13, color: '#ccc', lineHeight: 1.6 }}>
            <div style={{ marginBottom: 8 }}>
              <strong style={{ color: BRAND_GREEN, fontWeight: 700 }}>telebirr:</strong> One-tap subscription via telebirr app. Auto-renew enabled.
            </div>
            <div>
              <strong style={{ color: BRAND_GREEN, fontWeight: 700 }}>SMS:</strong> Send SMS to <span style={{ color: BRAND_GREEN, fontWeight: 800 }}>9286</span> with code{' '}
              <span style={{ color: '#fff', fontWeight: 700 }}>1</span> (Daily),{' '}
              <span style={{ color: '#fff' }}>2</span> (Weekly),{' '}
              <span style={{ color: '#fff' }}>3</span> (Monthly) via ethio telecom.
            </div>
          </div>
        </div>

        {/* telebirr Receipt Modal — shown when user clicks "Subscribe via telebirr" */}
        {telebirrModalOpen && selectedTierForTelebirr && (
          <div style={{
            position: 'fixed',
            top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0, 0, 0, 0.85)',
            display: 'flex', alignItems: 'flex-end', justifyContent: 'center',
            zIndex: 1000,
          }}>
            <div style={{
              background: '#F5F5F5',
              borderTopLeftRadius: 24,
              borderTopRightRadius: 24,
              padding: 24,
              width: '100%',
              maxWidth: 480,
              boxShadow: '0 -8px 32px rgba(0,0,0,0.4)',
            }}>
              {/* Close button */}
              <div style={{ display: 'flex', justifyContent: 'flex-start', marginBottom: 4 }}>
                <button
                  onClick={() => setTelebirrModalOpen(false)}
                  aria-label="Close"
                  style={{
                    background: 'transparent',
                    border: 'none',
                    cursor: 'pointer',
                    padding: 4,
                    color: '#000',
                    fontSize: 22,
                    lineHeight: 1,
                  }}
                >
                  <X size={22} color="#000" />
                </button>
              </div>

              {/* Title */}
              <div style={{
                textAlign: 'center',
                fontSize: 14,
                color: '#333',
                marginBottom: 4,
              }}>
                Subscribe to FlipStar {selectedTierForTelebirr.name}
              </div>

              {/* Total amount big */}
              <div style={{
                textAlign: 'center',
                fontSize: 36,
                fontWeight: 900,
                color: '#000',
                marginBottom: 20,
              }}>
                {selectedTierForTelebirr.price_etb}.00
                <span style={{ fontSize: 14, fontWeight: 700, marginLeft: 4 }}>ETB</span>
              </div>

              {/* Receipt details card */}
              <div style={{
                background: '#fff',
                borderRadius: 12,
                padding: 16,
                marginBottom: 12,
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <span style={{ fontSize: 14, color: '#333' }}>Plan</span>
                  <span style={{ fontSize: 14, color: '#000', fontWeight: 700 }}>
                    {selectedTierForTelebirr.name}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <span style={{ fontSize: 14, color: '#333' }}>
                    {selectedTierForTelebirr.duration_type === 'daily' ? 'Daily Amount' :
                     selectedTierForTelebirr.duration_type === 'weekly' ? 'Weekly Amount' :
                     selectedTierForTelebirr.duration_type === 'monthly' ? 'Monthly Amount' : 'Amount'}
                  </span>
                  <span style={{ fontSize: 14, color: '#000', fontWeight: 700 }}>
                    {selectedTierForTelebirr.price_etb}.00 ETB
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 14 }}>
                  <span style={{ fontSize: 14, color: '#333' }}>Date</span>
                  <span style={{ fontSize: 14, color: '#000', fontWeight: 700 }}>
                    {new Date().toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}
                  </span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span style={{ fontSize: 14, color: '#333' }}>Phone Number</span>
                  <span style={{ fontSize: 14, color: '#000', fontWeight: 700 }}>
                    {telebirrPhone || 'N/A'}
                  </span>
                </div>
              </div>

              {/* Payment method card */}
              <div style={{
                background: '#fff',
                borderRadius: 12,
                padding: 16,
                marginBottom: 20,
                display: 'flex',
                alignItems: 'center',
                gap: 12,
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 8,
                  background: '#8fc441',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <Crown size={18} color="#fff" />
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, color: '#000', fontWeight: 700 }}>telebirr</div>
                  <div style={{ fontSize: 12, color: '#888' }}>
                    Direct debit from your telebirr balance
                  </div>
                </div>
                <Check size={20} color="#10B981" />
              </div>

              {/* Proceed button */}
              <button
                onClick={handleTelebirrProceed}
                disabled={processing}
                style={{
                  width: '100%',
                  padding: '16px',
                  background: processing ? '#9CB870' : '#8fc441',
                  border: 'none',
                  borderRadius: 12,
                  color: '#fff',
                  fontSize: 16,
                  fontWeight: 700,
                  cursor: processing ? 'wait' : 'pointer',
                  boxShadow: '0 4px 16px rgba(143,196,65,0.3)',
                }}
              >
                {processing ? 'Processing…' : 'Proceed'}
              </button>
            </div>
          </div>
        )}

        {/* Success Modal */}
        {successModalOpen && (
          <div
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(0,0,0,0.85)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              zIndex: 9999,
              animation: 'fadeIn 0.3s ease',
            }}
          >
            <div
              style={{
                background: '#1A1A1A',
                borderRadius: 16,
                padding: 32,
                maxWidth: 320,
                width: '90%',
                textAlign: 'center',
                border: '1px solid #333',
                boxShadow: '0 24px 64px rgba(0,0,0,0.7)',
                animation: 'scaleIn 0.3s ease',
              }}
            >
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: '50%',
                  background: '#10B981',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  margin: '0 auto 20px',
                }}
              >
                <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="20 6 9 17 4 12"></polyline>
                </svg>
              </div>
              <div style={{ fontSize: 20, fontWeight: 700, color: '#fff', marginBottom: 8 }}>
                Successfully Subscribed!
              </div>
              <div style={{ fontSize: 14, color: '#999', lineHeight: 1.5 }}>
                Please confirm via Telebirr app to complete activation.
              </div>
            </div>
          </div>
        )}
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


