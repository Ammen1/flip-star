import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal,
  ActivityIndicator, KeyboardAvoidingView, ScrollView,
  Platform, StatusBar, Image, Linking, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../../contexts/ThemeContext';
import api from '../../api';
import TelebirrReceiptModal from '../../components/TelebirrReceiptModal';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

const getFallbackTiers = () => [
  {
    id: 1,
    name: 'Daily',
    duration_type: 'daily',
    price_etb: 3,
    price_coins: null,
    description: 'Access for 24 hours',
    features: ['Full access for 24 hours', 'Ad-free experience', 'HD quality videos'],
    short_code: '9286'
  },
  {
    id: 2,
    name: 'Weekly',
    duration_type: 'weekly',
    price_etb: 20,
    price_coins: null,
    description: 'Access for 7 days',
    features: ['Full access for 7 days', 'Ad-free experience', 'HD quality videos'],
    short_code: '9286'
  },
  {
    id: 3,
    name: 'Monthly',
    duration_type: 'monthly',
    price_etb: 70,
    price_coins: null,
    description: 'Access for 30 days',
    features: ['Full access for 30 days', 'Ad-free experience', 'HD quality videos'],
    short_code: '9286'
  },
];

export default function SubscriptionPlansModal({ visible, onClose, onSuccess, user }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [tiers, setTiers] = useState(getFallbackTiers());
  const [loading, setLoading] = useState(false);
  const [selectedTier, setSelectedTier] = useState(null);
  const [smsSent, setSmsSent] = useState(false);
  const [pendingTier, setPendingTier] = useState(null);
  const [confirmed, setConfirmed] = useState(false);
  const [pollCount, setPollCount] = useState(0);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [paymentTier, setPaymentTier] = useState(null);
  const [showTelebirrReceipt, setShowTelebirrReceipt] = useState(false);
  const [selectedPaymentMethod, setSelectedPaymentMethod] = useState('sms');
  
  const pollRef = useRef(null);
  const POLL_INTERVAL = 5000;
  const MAX_POLLS = 36; // 3 minutes

  useEffect(() => {
    if (visible) {
      loadSubscriptionData();
    }
  }, [visible]);

  useEffect(() => {
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
      }
    };
  }, []);

  const startPolling = (tier) => {
    let count = 0;
    pollRef.current = setInterval(async () => {
      count++;
      setPollCount(count);
      try {
        const sub = await api.request('/subscriptions/');
        if (sub && sub.status === 'active') {
          clearInterval(pollRef.current);
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

  const loadSubscriptionData = async () => {
    // Use fallback tiers only since API requires authentication
    // In a real app, this endpoint should be public or handle unauthenticated requests
    try {
      console.log('Using fallback subscription tiers');
    } catch (error) {
      console.error('Error loading subscription data:', error);
    }
  };

  const handleSubscribe = async (tier) => {
    setSelectedTier(tier);
    setSelectedPaymentMethod('sms');
    setShowPaymentModal(true);
    setPaymentTier(tier);
  };

  const handlePaymentMethodSelect = (method) => {
    setSelectedPaymentMethod(method);
    if (method === 'telebirr') {
      setShowPaymentModal(false);
      setShowTelebirrReceipt(true);
    } else {
      // SMS payment
      proceedWithSms();
    }
  };

  const proceedWithSms = () => {
    setShowPaymentModal(false);
    const tier = paymentTier || selectedTier;
    if (!tier) return;

    const tierCode = tier.duration_type === 'daily' ? 'OK1' :
                     tier.duration_type === 'weekly' ? 'OK2' :
                     tier.duration_type === 'monthly' ? 'OK3' : 'OK1';
    const shortCode = tier.short_code || '9286';
    const smsUrl = `sms:${shortCode}?body=${encodeURIComponent(tierCode)}`;
    
    // Open SMS app
    Linking.openURL(smsUrl).catch(err => {
      console.error('Failed to open SMS app:', err);
      Alert.alert('Error', 'Could not open SMS app');
    });
    
    // Show pending screen after a short delay (SMS app opens)
    setTimeout(() => {
      setPendingTier(tier);
      setSmsSent(true);
      setSelectedTier(tier);
      setPollCount(0);
      setConfirmed(false);
      if (user) startPolling(tier);
    }, 1500);
  };

  const handleTelebirrProceed = () => {
    setShowTelebirrReceipt(false);
    // Here you would initiate the Telebirr payment flow
    // For now, show the pending screen similar to SMS
    const tier = selectedTier;
    if (tier) {
      setPendingTier(tier);
      setSmsSent(true);
      setSelectedTier(tier);
      setPollCount(0);
      setConfirmed(false);
      if (user) startPolling(tier);
    }
  };


  const getTierIcon = (durationType) => {
    switch (durationType) {
      case 'daily': return 'calendar-outline';
      case 'weekly': return 'flash-outline';
      case 'monthly': return 'ribbon-outline';
      default: return 'ribbon-outline';
    }
  };

  const getTierColor = (durationType) => {
    switch (durationType) {
      case 'daily': return '#3B82F6';
      case 'weekly': return '#10B981';
      case 'monthly': return '#C8B56A';
      default: return '#C8B56A';
    }
  };

  if (!visible) return null;

  // Detect if user already has an active subscription
  const activeSubTier = user?.subscription_tier || user?.active_subscription?.tier || null;
  const activeSubStatus = user?.subscription_status || user?.active_subscription?.status || null;
  const isAlreadySubscribed =
    activeSubStatus === 'active' &&
    activeSubTier;

  const visibleTiers = tiers;

  // ── Pending / Confirmed overlay ──
  if (smsSent && pendingTier) {
    const timedOut = pollCount >= MAX_POLLS;
    return (
      <Modal visible animationType="slide" transparent onRequestClose={onClose}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <StatusBar barStyle="light-content" />
          <View style={s.pendingModalOverlay}>
            <View style={s.pendingModalContent}>
              {confirmed ? (
                <>
                  <View style={s.successIcon}>
                    <Text style={{ fontSize: 56 }}>✅</Text>
                  </View>
                  <Text style={s.successTitle}>Subscription Active!</Text>
                  <Text style={s.successSubtitle}>
                    Your <Text style={{ color: '#fff', fontWeight: '700' }}>{pendingTier.name}</Text> plan is now active.
                  </Text>
                  <Text style={s.successDesc}>
                    {user ? 'You can now enjoy all FlipStar features.' : 'Check your SMS for a registration link to complete your account setup.'}
                  </Text>
                  <TouchableOpacity
                    style={s.goldBtn}
                    onPress={() => {
                      stopPolling();
                      onSuccess && onSuccess();
                    }}
                  >
                    <Text style={s.goldBtnText}>{user ? 'Go to FlipStar →' : 'Check SMS →'}</Text>
                  </TouchableOpacity>
                </>
              ) : timedOut ? (
                <>
                  <View style={s.pendingIcon}>
                    <Text style={{ fontSize: 56 }}>⏱️</Text>
                  </View>
                  <Text style={s.pendingTitle}>Taking longer than expected</Text>
                  <Text style={s.pendingSubtitle}>
                    Check your SMS inbox for a confirmation message from Ethiotelecom. Your subscription may still be processing.
                  </Text>
                  <TouchableOpacity
                    style={[s.goldBtn, { marginBottom: 12 }]}
                    onPress={() => { stopPolling(); loadSubscriptionData(); }}
                  >
                    <Text style={s.goldBtnText}>Check Again</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    style={s.secondaryBtn}
                    onPress={stopPolling}
                  >
                    <Text style={s.secondaryBtnText}>Back to Plans</Text>
                  </TouchableOpacity>
                </>
              ) : (
                <>
                  <View style={s.pendingIcon}>
                    <Text style={{ fontSize: 48 }}>📱</Text>
                  </View>
                  <Text style={s.pendingTitle}>SMS Sent!</Text>
                  <Text style={s.pendingSubtitle}>
                    Waiting for Ethiotelecom to confirm your <Text style={{ color: '#fff', fontWeight: '700' }}>{pendingTier.name}</Text> subscription…
                  </Text>
                  {user && (
                    <Text style={s.pollingText}>
                      Checking every 5 seconds ({Math.max(0, MAX_POLLS - pollCount)} checks remaining)
                    </Text>
                  )}
                  {!user && (
                    <Text style={s.pendingDesc}>
                      Once confirmed, you'll receive an SMS with a link to complete your registration.
                    </Text>
                  )}
                  
                  {/* Spinner */}
                  <View style={s.spinnerContainer}>
                    <View style={s.spinner} />
                  </View>
                  
                  <View style={s.planInfo}>
                    <Text style={s.planInfoTitle}>Plan selected</Text>
                    <Text style={s.planInfoText}>{pendingTier.name} — {pendingTier.price_etb} ETB</Text>
                    <Text style={s.planInfoSub}>SMS sent to: {pendingTier.short_code || '9286'}</Text>
                  </View>
                  
                  <TouchableOpacity
                    style={[s.secondaryBtn, { marginBottom: 8 }]}
                    onPress={() => handleSubscribe(pendingTier)}
                  >
                    <Text style={s.secondaryBtnText}>Resend SMS</Text>
                  </TouchableOpacity>
                  
                  <TouchableOpacity
                    style={s.secondaryBtn}
                    onPress={stopPolling}
                  >
                    <Text style={s.secondaryBtnText}>Cancel</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>
    );
  }

  return (
    <>
      {/* Payment Method Selection Modal */}
      <Modal visible={showPaymentModal} animationType="slide" transparent onRequestClose={() => setShowPaymentModal(false)}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <StatusBar barStyle="light-content" />
          <View style={s.paymentOverlay}>
            <View style={s.paymentModal}>
              <View style={s.pmHandle} />
              <View style={s.pmIconWrap}>
                <View style={s.pmIconCircle}>
                  <Ionicons name="wallet" size={28} color="#8B5CF6" />
                </View>
              </View>
              <Text style={s.paymentTitle}>Choose Payment Method</Text>
              <Text style={s.paymentDesc}>Select how you want to pay for your subscription</Text>
              
              <View style={s.pmPriceRow}>
                <View style={s.pmChip}>
                  <Ionicons name="pricetag" size={14} color={GOLD} />
                  <Text style={s.pmChipText}>{paymentTier?.price_etb} ETB</Text>
                </View>
                <View style={s.pmChip}>
                  <Ionicons name="time" size={14} color={GOLD} />
                  <Text style={s.pmChipText}>{paymentTier?.duration_type}</Text>
                </View>
              </View>
              
              <View style={s.pmDivider} />
              
              {/* SMS Payment Option */}
              <TouchableOpacity
                style={[s.pmMethodBtn, selectedPaymentMethod === 'sms' && { borderColor: GOLD, borderWidth: 2 }]}
                onPress={() => handlePaymentMethodSelect('sms')}
              >
                <View style={[s.pmMethodIcon, { backgroundColor: '#3B82F620' }]}>
                  <Ionicons name="chatbubble-outline" size={22} color="#3B82F6" />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.pmMethodTitle}>SMS Payment</Text>
                  <Text style={s.pmMethodSub}>Pay via Ethiotelecom SMS</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={selectedPaymentMethod === 'sms' ? GOLD : '#666'} />
              </TouchableOpacity>
              
              {/* Telebirr Payment Option */}
              <TouchableOpacity
                style={[s.pmMethodBtn, selectedPaymentMethod === 'telebirr' && { borderColor: GOLD, borderWidth: 2 }]}
                onPress={() => handlePaymentMethodSelect('telebirr')}
              >
                <View style={[s.pmMethodIcon, { backgroundColor: '#C8B56A20' }]}>
                  <Ionicons name="card" size={22} color={GOLD} />
                </View>
                <View style={{ flex: 1 }}>
                  <Text style={s.pmMethodTitle}>Telebirr</Text>
                  <Text style={s.pmMethodSub}>Pay via Telebirr mobile money</Text>
                </View>
                <Ionicons name="chevron-forward" size={20} color={selectedPaymentMethod === 'telebirr' ? GOLD : '#666'} />
              </TouchableOpacity>
              
              <TouchableOpacity
                style={s.paymentCancelBtn}
                onPress={() => setShowPaymentModal(false)}
              >
                <Text style={s.paymentCancelText}>Cancel</Text>
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Telebirr Receipt Modal */}
      <TelebirrReceiptModal
        visible={showTelebirrReceipt}
        onClose={() => setShowTelebirrReceipt(false)}
        onProceed={handleTelebirrProceed}
        tier={selectedTier}
        phoneNumber={user?.phone || user?.username || ''}
      />

      {/* Main Subscription Plans Modal */}
      <Modal visible animationType="slide" transparent onRequestClose={onClose}>
        <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <StatusBar barStyle="light-content" />
          
          <View style={s.modalOverlay}>
            <View style={s.modalContent}>
              
              
              <View style={s.contentContainer}>
              {/* Header with Back Button */}
              <View style={s.topHeader}>
                <TouchableOpacity style={s.topBackButton} onPress={onClose}>
                  <Ionicons name="chevron-back" size={20} color={colors.primary} />
                </TouchableOpacity>
                <Text style={s.headerTitle}>Choose Your Plan</Text>
                <View style={s.placeholder} />
              </View>

              <Text style={s.subtitle}>
                Select a subscription to unlock premium features
              </Text>


              {/* Subscription Tiers */}
              <View style={s.tiersContainer}>
                {visibleTiers.map((tier) => {
                  const icon = getTierIcon(tier.duration_type);
                  const color = getTierColor(tier.duration_type);
                  
                  return (
                    <TouchableOpacity
                      key={tier.id}
                      style={[s.tierCard, { borderColor: color }]}
                      onPress={() => handleSubscribe(tier)}
                      activeOpacity={0.8}
                    >
                      <View style={[s.iconContainer, { backgroundColor: color + '20', borderColor: color }]}>
                        <Ionicons name={icon} size={24} color={color} />
                      </View>

                      <View style={s.tierInfo}>
                        <View style={s.tierHeader}>
                          <Text style={s.tierName}>{tier.name}</Text>
                          <View style={[s.durationBadge, { backgroundColor: color + '30' }]}>
                            <Text style={[s.durationText, { color }]}>{tier.duration_type}</Text>
                          </View>
                        </View>
                        <Text style={s.tierPrice}>{tier.price_etb} ETB</Text>
                        {tier.price_coins && (
                          <Text style={s.tierCoinPrice}>or {tier.price_coins} coins</Text>
                        )}
                        <Text style={s.tierDescription}>{tier.description}</Text>
                        
                        {/* Features List */}
                        <View style={s.featuresList}>
                          {tier.features?.slice(0, 2).map((feature, index) => (
                            <View key={index} style={s.featureItem}>
                              <Ionicons name="checkmark-circle" size={14} color={color} />
                              <Text style={s.featureText}>{feature}</Text>
                            </View>
                          ))}
                        </View>
                      </View>

                      <View style={s.tierArrow}>
                        <Ionicons name="chevron-forward" size={20} color={color} />
                      </View>
                    </TouchableOpacity>
                  );
                })}
              </View>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>

    </Modal>
    </>
  );
}

const s = StyleSheet.create({
  modalOverlay: { 
    flex: 1, 
    backgroundColor: 'rgba(0,0,0,1)', 
    justifyContent: 'center',
    alignItems: 'center'
  },
  modalContent: { 
    backgroundColor: '#000000', 
    borderRadius: 18, 
    padding: 24, 
    paddingBottom: 40, 
    maxHeight: '95%',
    minHeight: '90%',
    width: '100%',
    maxWidth: 500
  },
  logosRow: { 
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    alignItems: 'center', 
    marginBottom: 24, 
    borderRadius: 12, 
    paddingHorizontal: 12,
    paddingVertical: 10,
    overflow: 'hidden',
  },
  ethioLogo: { width: 100, height: 50 },
  flipstarLogo: { width: 100, height: 50 },
  topHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 8,
    paddingTop: 2,
  },
  topBackButton: {
    padding: 8,
    borderRadius: 8,
  },
  headerTitle: {
    fontSize: 20,
    fontWeight: '900',
    color: GOLD,
    textAlign: 'center',
    flex: 1,
  },
  placeholder: {
    width: 36,
  },
  contentContainer: {
    flex: 1,
  },
  mainContent: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    marginBottom: 20,
  },
  title: {
    fontSize: 24,
    fontWeight: '900',
    color: GOLD,
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 12,
    color: '#aaa',
    textAlign: 'center',
    marginBottom: 8,
  },
  activeBanner: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    backgroundColor: '#0D2B1F',
    borderWidth: 1.5,
    borderColor: '#10B981',
    borderRadius: 12,
    padding: 14,
    marginBottom: 16,
  },
  activeBannerTitle: {
    fontSize: 15,
    fontWeight: '800',
    color: '#10B981',
    marginBottom: 4,
  },
  activeBannerSub: {
    fontSize: 12,
    color: '#aaa',
    lineHeight: 18,
  },
  tiersContainer: {
    marginBottom: 8,
  },
  tierCard: {
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: 12,
    borderWidth: 2,
    borderColor: BORDER,
    marginBottom: 10,
    padding: 12,
    flexDirection: 'row',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  iconContainer: {
    width: 40,
    height: 40,
    borderRadius: 10,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
    borderWidth: 2,
  },
  tierInfo: {
    flex: 1,
  },
  tierHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  tierName: {
    fontSize: 16,
    fontWeight: '800',
    color: '#fff',
  },
  durationBadge: {
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 8,
  },
  durationText: {
    fontSize: 9,
    fontWeight: '700',
    textTransform: 'uppercase',
  },
  tierPrice: {
    fontSize: 18,
    fontWeight: '900',
    color: GOLD,
    marginBottom: 2,
  },
  tierCoinPrice: {
    fontSize: 12,
    color: '#aaa',
    marginBottom: 4,
  },
  tierDescription: {
    fontSize: 11,
    color: '#aaa',
    marginBottom: 6,
  },
  featuresList: {
    marginTop: 4,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    marginBottom: 3,
  },
  featureText: {
    fontSize: 10,
    color: '#ccc',
    marginLeft: 4,
  },
  tierArrow: {
    marginLeft: 12,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
    paddingVertical: 12,
  },
  backButtonText: {
    color: GOLD,
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 4,
  },
  // Pending/Success states
  successIcon: {
    alignItems: 'center',
    marginBottom: 16,
  },
  successTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: GOLD,
    textAlign: 'center',
    marginBottom: 8,
  },
  successSubtitle: {
    fontSize: 14,
    color: '#aaa',
    textAlign: 'center',
    marginBottom: 8,
  },
  successDesc: {
    fontSize: 13,
    color: '#aaa',
    textAlign: 'center',
    marginBottom: 28,
  },
  pendingIcon: {
    alignItems: 'center',
    marginBottom: 16,
  },
  pendingTitle: {
    fontSize: 22,
    fontWeight: '900',
    color: GOLD,
    textAlign: 'center',
    marginBottom: 8,
  },
  pendingSubtitle: {
    fontSize: 14,
    color: '#aaa',
    textAlign: 'center',
    marginBottom: 4,
  },
  pendingDesc: {
    fontSize: 13,
    color: '#aaa',
    textAlign: 'center',
    marginBottom: 20,
  },
  pollingText: {
    fontSize: 12,
    color: '#666',
    marginBottom: 20,
    textAlign: 'center',
  },
  spinnerContainer: {
    display: 'flex',
    justifyContent: 'center',
    marginBottom: 24,
  },
  spinner: {
    width: 40,
    height: 40,
    borderRadius: 20,
    borderWidth: 3,
    borderColor: '#262626',
    borderTopColor: GOLD,
    // Animation would require additional implementation
  },
  planInfo: {
    padding: 16,
    backgroundColor: '#111',
    borderRadius: 10,
    marginBottom: 20,
  },
  planInfoTitle: {
    color: GOLD,
    fontWeight: '700',
    marginBottom: 4,
    fontSize: 13,
  },
  planInfoText: {
    color: '#fff',
    fontSize: 14,
  },
  planInfoSub: {
    color: '#aaa',
    fontSize: 12,
    marginTop: 2,
  },
  goldBtn: { 
    backgroundColor: GOLD, 
    borderRadius: 10, 
    height: 50, 
    justifyContent: 'center', 
    alignItems: 'center', 
    marginBottom: 16 
  },
  goldBtnText: { 
    color: '#000', 
    fontSize: 15, 
    fontWeight: '800' 
  },
  secondaryBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: '#333',
    borderRadius: 10,
    height: 44,
    justifyContent: 'center',
    alignItems: 'center',
  },
  secondaryBtnText: {
    color: '#666',
    fontSize: 13,
    fontWeight: '700',
  },
  pendingModalOverlay: { 
    flex: 1, 
    backgroundColor: 'rgba(0,0,0,1)', 
    justifyContent: 'center',
    alignItems: 'center'
  },
  pendingModalContent: { 
    backgroundColor: '#000000', 
    borderRadius: 18, 
    padding: 28, 
    paddingBottom: 40, 
    maxHeight: '90%',
    minHeight: '80%',
    width: '95%',
    maxWidth: 400
  },
  // Payment Modal — bottom sheet style
  paymentOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'flex-end',
  },
  paymentModal: {
    backgroundColor: '#141414',
    borderTopLeftRadius: 28,
    borderTopRightRadius: 28,
    paddingHorizontal: 24,
    paddingTop: 12,
    paddingBottom: 36,
    borderTopWidth: 1,
    borderColor: '#2a2a2a',
  },
  pmHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: '#333', alignSelf: 'center', marginBottom: 20,
  },
  pmIconWrap: { alignItems: 'center', marginBottom: 12 },
  pmIconCircle: {
    width: 60, height: 60, borderRadius: 30,
    backgroundColor: 'rgba(139,92,246,0.15)',
    borderWidth: 2, borderColor: '#8B5CF6',
    justifyContent: 'center', alignItems: 'center',
  },
  paymentTitle: {
    fontSize: 22, fontWeight: '900', color: '#fff',
    textAlign: 'center', marginBottom: 6,
  },
  paymentDesc: {
    fontSize: 13, color: '#888', textAlign: 'center',
    marginBottom: 16, lineHeight: 19,
  },
  pmPriceRow: {
    flexDirection: 'row', justifyContent: 'center', gap: 10, marginBottom: 20,
  },
  pmChip: {
    flexDirection: 'row', alignItems: 'center', gap: 5,
    backgroundColor: 'rgba(200,181,106,0.12)',
    borderWidth: 1, borderColor: GOLD,
    paddingHorizontal: 12, paddingVertical: 5, borderRadius: 20,
  },
  pmChipText: { fontSize: 13, fontWeight: '700', color: GOLD },
  pmDivider: { height: 1, backgroundColor: '#222', marginBottom: 16 },
  pmMethodBtn: {
    flexDirection: 'row', alignItems: 'center', gap: 14,
    backgroundColor: '#1E1E1E', borderRadius: 14,
    padding: 16, marginBottom: 10,
    borderWidth: 1, borderColor: '#2a2a2a',
  },
  pmMethodIcon: {
    width: 44, height: 44, borderRadius: 22,
    justifyContent: 'center', alignItems: 'center',
  },
  pmMethodTitle: { fontSize: 15, fontWeight: '700', color: '#fff', marginBottom: 2 },
  pmMethodSub: { fontSize: 12, color: '#666' },
  paymentCancelBtn: {
    paddingVertical: 14, alignItems: 'center', marginTop: 4,
  },
  paymentCancelText: { fontSize: 14, fontWeight: '600', color: '#555' },
});
