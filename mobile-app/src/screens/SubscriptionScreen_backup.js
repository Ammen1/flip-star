import React, { useState, useEffect } from 'react';

import {

  View, Text, StyleSheet, TouchableOpacity, ScrollView, Modal,

  ActivityIndicator, Alert, Linking,

} from 'react-native';

import { Ionicons } from '@expo/vector-icons';

import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useTheme } from '../contexts/ThemeContext';

import api from '../api';



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

  { icon: 'ban-outline',         text: 'No Ads' },

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



  useEffect(() => {

    loadData();

  }, []);



  const loadData = async () => {

    try {

      const [tiersData, subData] = await Promise.all([

        api.request('/subscriptions/tiers/active/').catch(() => []),

        api.request('/subscriptions/').catch(() => null),

      ]);

      if (Array.isArray(tiersData) && tiersData.length > 0) setTiers(tiersData);

      setCurrentSub(subData);

    } catch {}

  };



  const handleSubscribe = async (tier) => {

    // OnDemand uses coins - show payment options

    if (tier.duration_type === 'ondemand') {

      Alert.alert(

        'Choose Payment Method',

        'Select how you want to pay for OnDemand access:',

        [

          {

            text: 'Airtime',

            onPress: () => {

              Linking.openURL(`sms:9286?body=${encodeURIComponent('OK1')}`).catch(() =>

                Alert.alert('Error', 'Could not open SMS app')

              );

            }

          },

          {

            text: 'telebirr',

            onPress: () => {

              Linking.openURL(`sms:9286?body=${encodeURIComponent('OK2')}`).catch(() =>

                Alert.alert('Error', 'Could not open SMS app')

              );

            }

          },

          {

            text: 'Cancel',

            style: 'cancel'

          }

        ]

      );

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



  return (

    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>

      {/* Header */}

      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>

        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>

          <Ionicons name="chevron-back" size={22} color={colors.text} />

        </TouchableOpacity>

        <Text style={[styles.headerTitle, { color: colors.text }]}>Premium</Text>

        <View style={{ width: 36 }} />

      </View>



      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}>



        {/* Hero */}

        <View style={styles.hero}>

          <View style={styles.crownCircle}>

            <Ionicons name="trophy" size={36} color={GOLD} />

          </View>

          <Text style={styles.heroTitle}>FlipStar Premium</Text>

          <Text style={styles.heroSub}>Unlock the full experience</Text>



          {isActive && (

            <View style={styles.activePill}>

              <View style={styles.activeDot} />

              <Text style={styles.activePillText}>

                Active · expires {new Date(currentSub.end_date).toLocaleDateString()}

              </Text>

            </View>

          )}

        </View>



        {/* Benefits row */}

        <View style={styles.benefitsRow}>

          {BENEFITS.map((b, i) => (

            <View key={i} style={styles.benefitChip}>

              <Ionicons name={b.icon} size={16} color={GOLD} />

              <Text style={styles.benefitChipText}>{b.text}</Text>

            </View>

          ))}

        </View>



        {/* Plans */}

        <Text style={styles.sectionLabel}>

          {isActive ? 'Your Subscription + Add-ons' : 'Available Plans'}

        </Text>



        {tiers.filter(tier => (isActive && currentSub?.tier?.id === tier.id) || tier.duration_type === 'ondemand')

          .map((tier, i) => {

          const isSelected = selectedTier?.id === tier.id;

          const isCurrent = currentSub?.tier?.id === tier.id && isActive;

          const color = PLAN_COLORS[tier.duration_type] || GOLD;

          const icon = PLAN_ICONS[tier.duration_type] || 'star';



          return (

            <TouchableOpacity

              key={tier.id}

              style={[

                styles.planCard,

                isSelected && { borderColor: color, borderWidth: 2 },

                isCurrent && styles.planCardCurrent,

              ]}

              onPress={() => setSelectedTier(tier)}

              activeOpacity={0.85}

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

                  <Text style={styles.planName}>{tier.name}</Text>

                  <Text style={styles.planDesc}>{tier.description}</Text>

                </View>

                <View style={styles.planPriceBox}>

                  <Text style={[styles.planPrice, { color }]}>{tier.price_etb}</Text>

                  <Text style={styles.planCurrency}>ETB</Text>

                </View>

              </View>



              <View style={styles.planFeatures}>

                {(tier.features || []).map((f, fi) => (

                  <View key={fi} style={styles.featureRow}>

                    <Ionicons name="checkmark-circle" size={13} color={color} />

                    <Text style={styles.featureText}>{f}</Text>

                  </View>

                ))}

              </View>



              <TouchableOpacity

                style={[styles.planBtn, { backgroundColor: isCurrent ? '#222' : color }]}

                onPress={() => handleSubscribe(tier)}

                disabled={isCurrent}

              >

                <Ionicons name="chatbubble-ellipses-outline" size={15} color={isCurrent ? '#666' : '#000'} />

                <Text style={[styles.planBtnText, { color: isCurrent ? '#666' : '#000' }]}>

                  {isCurrent ? 'Active Plan' : tier.duration_type === 'ondemand' ? 'Subscribe via Airtime/telebirr' : 'Subscribe via SMS'}

                </Text>

              </TouchableOpacity>

            </TouchableOpacity>

          );

        })}



        {/* SMS info */}

        <View style={styles.infoBox}>

          <Ionicons name="information-circle-outline" size={18} color={GOLD} />

          <Text style={styles.infoText}>

            Send SMS to <Text style={{ color: GOLD, fontWeight: '700' }}>9286</Text> with code{' '}

            <Text style={{ color: '#fff' }}>OK1</Text> (Daily),{' '}

            <Text style={{ color: '#fff' }}>OK2</Text> (Weekly),{' '}

            <Text style={{ color: '#fff' }}>OK3</Text> (Monthly), or{' '}

            <Text style={{ color: '#fff' }}>OK4</Text> (On Demand) via Ethio Telecom.

          </Text>

        </View>

      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({

  container: { flex: 1, backgroundColor: BG },



  header: {

    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',

    paddingHorizontal: 16, paddingVertical: 12,

  },

  backBtn: {

    width: 36, height: 36, borderRadius: 18,

    backgroundColor: '#1a1a1a', justifyContent: 'center', alignItems: 'center',

  },

  headerTitle: { fontSize: 17, fontWeight: '700', color: '#fff' },



  hero: { alignItems: 'center', paddingVertical: 32, paddingHorizontal: 24 },

  crownCircle: {

    width: 80, height: 80, borderRadius: 40,

    backgroundColor: GOLD + '18', borderWidth: 1.5, borderColor: GOLD + '40',

    justifyContent: 'center', alignItems: 'center', marginBottom: 16,

  },

  heroTitle: { fontSize: 26, fontWeight: '900', color: '#fff', marginBottom: 6 },

  heroSub: { fontSize: 14, color: '#666', textAlign: 'center' },

  activePill: {

    flexDirection: 'row', alignItems: 'center', gap: 6,

    backgroundColor: '#0D2D1A', paddingHorizontal: 14, paddingVertical: 7,

    borderRadius: 20, marginTop: 14, borderWidth: 1, borderColor: '#10B98140',

  },

  activeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: '#10B981' },

  activePillText: { color: '#10B981', fontSize: 13, fontWeight: '600' },



  benefitsRow: {

    flexDirection: 'row', flexWrap: 'wrap', gap: 8,

    paddingHorizontal: 16, marginBottom: 28,

  },

  benefitChip: {

    flexDirection: 'row', alignItems: 'center', gap: 6,

    backgroundColor: CARD, borderRadius: 20, paddingHorizontal: 12, paddingVertical: 7,

    borderWidth: 1, borderColor: BORDER,

  },

  benefitChipText: { fontSize: 12, color: '#ccc', fontWeight: '500' },



  sectionLabel: { fontSize: 13, fontWeight: '700', color: '#555', paddingHorizontal: 16, marginBottom: 12, letterSpacing: 1, textTransform: 'uppercase' },



  planCard: {

    marginHorizontal: 16, marginBottom: 14,

    backgroundColor: CARD, borderRadius: 20,

    padding: 18, borderWidth: 1.5, borderColor: BORDER,

    position: 'relative',

  },

  planCardCurrent: { borderColor: '#10B98150', backgroundColor: '#0D2D1A18' },

  currentTag: {

    position: 'absolute', top: -10, right: 16,

    paddingHorizontal: 10, paddingVertical: 3, borderRadius: 10,

  },

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

  featureText: { fontSize: 13, color: '#aaa' },



  planBtn: {

    flexDirection: 'row', alignItems: 'center', justifyContent: 'center',

    gap: 7, borderRadius: 14, padding: 13,

  },

  planBtnText: { fontWeight: '800', fontSize: 14 },



  infoBox: {

    flexDirection: 'row', gap: 10, alignItems: 'flex-start',

    marginHorizontal: 16, marginTop: 4,

    backgroundColor: CARD, borderRadius: 14, padding: 14,

    borderWidth: 1, borderColor: BORDER,

  },

  infoText: { flex: 1, fontSize: 12, color: '#666', lineHeight: 19 },

});


























