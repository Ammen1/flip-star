import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import { Linking } from 'react-native';

const GOLD = '#C8B56A';
const BG = '#0B0B0C';
const CARD = '#161616';
const BORDER = '#242424';

const PLAN_ICONS = { daily: 'flash', weekly: 'star', monthly: 'trophy', ondemand: 'diamond' };
const PLAN_COLORS = { daily: '#F59E0B', weekly: '#8B5CF6', monthly: '#C8B56A', ondemand: '#3B82F6' };

const FALLBACK_TIERS = [
  { id: 1, name: 'Daily', duration_type: 'daily',    price_etb: 3,  description: '24 hours of full access', features: ['Ad-free videos', 'HD quality', 'All content'] },
  { id: 2, name: 'Weekly', duration_type: 'weekly',   price_etb: 20, description: '7 days of full access',  features: ['Ad-free videos', 'HD quality', 'All content', 'Priority support'] },
  { id: 3, name: 'Monthly', duration_type: 'monthly',  price_etb: 70, description: '30 days of full access', features: ['Ad-free videos', 'HD quality', 'All content', 'Priority support', 'Campaign boosts'] },
  { id: 4, name: 'On Demand', duration_type: 'ondemand', price_etb: 10, price_coins: 100, description: 'Pay per use with coins', features: ['Flexible access', 'No recurring charges', 'Use coins anytime'] },
];

const BENEFITS = [
  { icon: 'videocam-outline',    text: 'HD Videos' },
  { icon: 'ad-outline',          text: 'Ad-Free Experience' },
  { icon: 'star-outline',        text: 'Exclusive Content' },
  { icon: 'trophy-outline',      text: 'Campaign Priority' },
];

export default function SubscriptionScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [tiers, setTiers] = useState(FALLBACK_TIERS);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [selectedPaymentTier, setSelectedPaymentTier] = useState(null);
  const [currentSub, setCurrentSub] = useState(null);
  const [selectedTier, setSelectedTier] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [tiersData, subData] = await Promise.all([
        api.request('/subscriptions/tiers/active/').catch(() => []),
        api.request('/subscriptions/').catch(() => null),
      ]);
      
      console.log('Subscription API Response:', { tiersData, subData });
      console.log('Current subscription data:', subData);
      console.log('Subscription status:', subData?.status);
      console.log('Subscription tier:', subData?.tier);
      
      if (Array.isArray(tiersData) && tiersData.length > 0) setTiers(tiersData);
      setCurrentSub(subData);
    } catch (error) {
      console.error('Error loading subscription data:', error);
    }
    finally { setLoading(false); }
  };

  const handleSubscribe = async (tier) => {
    // OnDemand uses coins - show payment options
    if (tier.duration_type === 'ondemand') {
      setSelectedPaymentTier(tier);
      setShowPaymentModal(true);
      return;
    }

    // Other tiers use SMS
    const codeMap = { daily: 'OK1', weekly: 'OK2', monthly: 'OK3' };
    const code = codeMap[tier.duration_type] || 'OK1';
    Linking.openURL(`sms:9286?body=${encodeURIComponent(code)}`).catch(() =>
      Alert.alert('Error', 'Could not open SMS app')
    );
  };

  const isActive = currentSub?.status === 'active';
  
  console.log('isActive check:', { 
    currentSub, 
    status: currentSub?.status, 
    isActive, 
    hasCurrentSub: !!currentSub,
    hasTier: !!currentSub?.tier 
  });

  if (loading) {
    return (
      <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
        <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
          <TouchableOpacity onPress={() => navigation.goBack()}>
            <Ionicons name="chevron-back" size={24} color={colors.text} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.text }]}>Subscription</Text>
          <View style={{ width: 24 }} />
        </View>
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading subscription plans...</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>Subscription</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}>
        {/* Benefits */}
        <View style={[styles.benefitsSection, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
          <Text style={[styles.sectionLabel, { color: colors.text }]}>Why Premium?</Text>
          <View style={styles.benefitsGrid}>
            {BENEFITS.map((benefit, i) => (
              <View key={i} style={styles.benefitItem}>
                <Ionicons name={benefit.icon} size={20} color={colors.primary} />
                <Text style={[styles.benefitText, { color: colors.text }]}>{benefit.text}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* Current Subscription Status */}
        {currentSub && (
          <View style={[styles.currentSubCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <View style={styles.currentSubHeader}>
              <Ionicons name="checkmark-circle" size={24} color={colors.primary} />
              <Text style={[styles.currentSubTitle, { color: colors.text }]}>Current Subscription</Text>
            </View>
            <View style={styles.currentSubDetails}>
              <Text style={[styles.currentPlanName, { color: colors.text }]}>
                {currentSub.tier?.name || currentSub.plan_name || currentSub.name || 'Active Plan'}
              </Text>
              <Text style={[styles.currentPlanDesc, { color: colors.textSecondary }]}>
                {currentSub.tier?.description || currentSub.description || 'Full access to all features'}
              </Text>
              <Text style={[styles.currentPlanPrice, { color: colors.primary }]}>
                {currentSub.tier?.price_etb || currentSub.price_etb || currentSub.price || 0} ETB
              </Text>
              <Text style={[styles.currentPlanExpiry, { color: colors.textSecondary }]}>
                Status: {currentSub.status || 'Unknown'}
              </Text>
              {currentSub.end_date && (
                <Text style={[styles.currentPlanExpiry, { color: colors.textSecondary }]}>
                  Expires: {new Date(currentSub.end_date).toLocaleDateString()}
                </Text>
              )}
              <Text style={[styles.debugInfo, { color: colors.textSecondary, fontSize: 10 }]}>
                Debug: isActive={String(isActive)}, hasData={String(!!currentSub)}
              </Text>
            </View>
          </View>
        )}

        {/* No Subscription Info */}
        {!currentSub && !loading && (
          <View style={[styles.currentSubCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <View style={styles.currentSubHeader}>
              <Ionicons name="information-circle" size={24} color={colors.textSecondary} />
              <Text style={[styles.currentSubTitle, { color: colors.text }]}>No Subscription Plan</Text>
            </View>
            <View style={styles.currentSubDetails}>
              <Text style={[styles.currentPlanName, { color: colors.text }]}>
                Upgrade Now
              </Text>
              <Text style={[styles.currentPlanDesc, { color: colors.textSecondary }]}>
                Choose a plan below to subscribe
              </Text>
            </View>
          </View>
        )}

        {/* Available Plans - filter based on current subscription */}
        {(() => {
          const PLAN_ORDER = { daily: 1, weekly: 2, monthly: 3 };
          const currentType = currentSub?.tier?.duration_type || currentSub?.duration_type || null;
          const currentRank = isActive && currentType ? (PLAN_ORDER[currentType] || 0) : 0;

          // Filter: remove ondemand, and only show plans higher than current
          const visibleTiers = tiers.filter(tier => {
            if (tier.duration_type === 'ondemand') return false;
            const tierRank = PLAN_ORDER[tier.duration_type] || 0;
            // If no active sub, show all plans
            if (!isActive) return true;
            // If monthly (highest), show nothing - only current sub card above
            if (currentRank >= 3) return false;
            // Show only plans higher than current
            return tierRank > currentRank;
          });

          const sectionTitle = isActive 
            ? (currentRank >= 3 ? null : 'Upgrade Your Plan')
            : 'Available Plans';

          return (
            <>
              {sectionTitle && (
                <Text style={[styles.sectionLabel, { color: colors.text }]}>
                  {sectionTitle}
                </Text>
              )}

              {visibleTiers.map((tier, i) => {
                const isSelected = selectedTier?.id === tier.id;
                const isCurrent = currentSub?.tier?.id === tier.id && isActive;
                const color = PLAN_COLORS[tier.duration_type] || GOLD;
                const icon = PLAN_ICONS[tier.duration_type] || 'star';

                return (
                  <View
                    key={tier.id}
                    style={[
                      styles.planCard,
                      { backgroundColor: colors.cardBg, borderColor: colors.border },
                      isSelected && { borderColor: color, borderWidth: 2 },
                      isCurrent && styles.planCardCurrent,
                    ]}
                  >
                    {isCurrent && (
                      <View style={[styles.currentTag, { backgroundColor: color }]}>
                        <Text style={styles.currentTagText}>Current</Text>
                      </View>
                    )}

                    <View style={styles.planTop}>
                      <View style={[styles.planIconBox, { backgroundColor: color + '22' }]}>
                        <Ionicons name={icon} size={22} color={color} />
                      </View>
                      <View style={{ flex: 1, marginLeft: 14 }}>
                        <Text style={[styles.planName, { color: colors.text }]}>{tier.name}</Text>
                        <Text style={[styles.planDesc, { color: colors.textSecondary }]}>{tier.description}</Text>
                      </View>
                      <View style={styles.planPriceBox}>
                        <Text style={[styles.planPrice, { color }]}>{tier.price_etb}</Text>
                        <Text style={[styles.planCurrency, { color: colors.textSecondary }]}>ETB</Text>
                      </View>
                    </View>

                    <View style={styles.planFeatures}>
                      {(tier.features || []).map((f, fi) => (
                        <View key={fi} style={styles.featureRow}>
                          <Ionicons name="checkmark" size={14} color={colors.primary} />
                          <Text style={[styles.featureText, { color: colors.text }]}>{f}</Text>
                        </View>
                      ))}
                    </View>

                    <TouchableOpacity
                      style={[styles.planBtn, { backgroundColor: color }]}
                      onPress={() => handleSubscribe(tier)}
                    >
                      <Ionicons name="chatbubble-ellipses-outline" size={15} color="#000" />
                      <Text style={[styles.planBtnText, { color: '#000' }]}>
                        Upgrade to {tier.name}
                      </Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </>
          );
        })()}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 18, fontWeight: '800', color: '#fff' },
  loadingText: { marginTop: 12, fontSize: 14, color: '#666' },
  benefitsSection: { margin: 16, padding: 20, borderRadius: 16, borderWidth: 1, borderColor: BORDER },
  sectionLabel: { fontSize: 17, fontWeight: '700', color: '#fff', marginBottom: 16 },
  benefitsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 16 },
  benefitItem: { width: '45%', alignItems: 'center', gap: 8 },
  benefitText: { fontSize: 12, color: '#fff', textAlign: 'center', fontWeight: '600' },
  currentSubCard: { margin: 16, padding: 20, borderRadius: 16, borderWidth: 1, borderColor: BORDER },
  currentSubHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 16 },
  currentSubTitle: { fontSize: 18, fontWeight: '700', color: '#fff' },
  currentSubDetails: { gap: 8 },
  currentPlanName: { fontSize: 16, fontWeight: '800', color: '#fff' },
  currentPlanDesc: { fontSize: 14, color: '#666', marginBottom: 8 },
  currentPlanPrice: { fontSize: 20, fontWeight: '900', color: GOLD },
  currentPlanExpiry: { fontSize: 12, color: '#666' },
  planCard: { marginHorizontal: 16, marginBottom: 14, padding: 20, borderRadius: 16, borderWidth: 1, borderColor: BORDER },
  planCardCurrent: { borderColor: '#10B98150', backgroundColor: '#0D2D1A18' },
  currentTag: { position: 'absolute', top: -10, right: 16, paddingHorizontal: 12, paddingVertical: 4, borderRadius: 12 },
  currentTagText: { color: '#000', fontSize: 10, fontWeight: '800' },
  planTop: { flexDirection: 'row', alignItems: 'center', marginBottom: 14 },
  planIconBox: { width: 46, height: 46, borderRadius: 14, justifyContent: 'center', alignItems: 'center' },
  planName: { fontSize: 16, fontWeight: '800', color: '#fff', marginBottom: 2 },
  planDesc: { fontSize: 12, color: '#666' },
  planPriceBox: { alignItems: 'flex-end' },
  planPrice: { fontSize: 24, fontWeight: '900', lineHeight: 26 },
  planCurrency: { fontSize: 11, color: '#666', fontWeight: '600' },
  planFeatures: { gap: 7, marginBottom: 16 },
  featureRow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  featureText: { fontSize: 13, color: '#fff', fontWeight: '500' },
  planBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 14, borderRadius: 12 },
  planBtnText: { fontWeight: '800', fontSize: 14 },
  debugInfo: { marginTop: 8, padding: 4, backgroundColor: '#333', borderRadius: 4 },
});
