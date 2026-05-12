import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Animated, RefreshControl } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import api from '../api';
import { AppAlert } from '../components/AppAlert';

const GOLD = '#C8B56A', BG = '#0B0B0C', CARD = '#161616', BORDER = '#242424';

function n(val, key) { if (val == null) return 0; if (typeof val === 'object') return val[key] ?? val.current ?? val.balance ?? 0; return Number(val) || 0; }

const STREAK_DAYS = [1,2,3,4,5,6,7].map((d,i) => ({ day: d, coins: [5,10,15,20,30,40,50][i] }));

export default function GamificationScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const [status, setStatus] = useState(null);
  const [quests, setQuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [claimingBonus, setClaimingBonus] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    loadAll();
    Animated.loop(Animated.sequence([
      Animated.timing(pulseAnim, { toValue: 1.06, duration: 800, useNativeDriver: true }),
      Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
    ])).start();
  }, []);

  const loadAll = async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    const [s, q] = await Promise.all([
      api.request('/gamification/status/').catch(() => null),
      api.request('/quests/').catch(() => []),
    ]);
    setStatus(s); setQuests(Array.isArray(q) ? q : (q?.results || []));
    setLoading(false); setRefreshing(false);
  };

  const claimBonus = async () => {
    setClaimingBonus(true);
    try {
      const res = await api.request('/gamification/login-bonus/', { method: 'POST' });
      AppAlert.alert('🎁 Bonus Claimed!', 'You earned ' + (res.coins_earned || res.coins || 0) + ' coins!');
      loadAll(true);
    } catch (e) {
      // Handle specific login bonus already claimed case
      const errorMessage = e?.message || '';
      if (errorMessage.includes('already claimed today')) {
        AppAlert.alert('⏰ Bonus Already Claimed', 'You already claimed your login bonus today. Come back tomorrow for your next bonus!');
      } else {
        AppAlert.alert('Error', e?.message || 'Could not claim bonus.');
      }
    }
    finally { setClaimingBonus(false); }
  };


  if (loading) return <View style={[styles.container, styles.centered]}><ActivityIndicator size='large' color={GOLD} /></View>;

  const coins = n(status?.coins, 'balance');
  const streak = n(status?.login_streak, 'current');
  const longest = n(status?.login_streak, 'longest');
  const bonusAvailable = status?.login_streak?.bonus_available ?? false;
  const points = n(status?.points, 'balance');
  const nextBonus = status?.login_streak?.next_bonus?.coins ?? 0;
  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Rewards</Text>
        <TouchableOpacity onPress={() => loadAll(true)} style={styles.backBtn}>
          <Ionicons name="refresh" size={20} color={GOLD} />
        </TouchableOpacity>
      </View>
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} tintColor={GOLD} />}>
        <View style={styles.heroCard}>
          <View style={styles.heroMain}>
            <View style={styles.coinCircle}><Ionicons name="star" size={32} color={GOLD} /></View>
            <View style={{ marginLeft: 16 }}>
              <Text style={styles.coinAmount}>{coins.toLocaleString()}</Text>
              <Text style={styles.coinLabel}>Coins Balance</Text>
            </View>
          </View>
          <View style={styles.heroStats}>
            <View style={styles.heroStat}>
              <Ionicons name="flame" size={16} color="#F97316" />
              <Text style={styles.heroStatVal}>{streak}</Text>
              <Text style={styles.heroStatLabel}>Streak</Text>
            </View>
            <View style={styles.heroStatDivider} />
            <View style={styles.heroStat}>
              <Ionicons name="star" size={16} color="#8B5CF6" />
              <Text style={styles.heroStatVal}>{points.toLocaleString()}</Text>
              <Text style={styles.heroStatLabel}>Points</Text>
            </View>
            <View style={styles.heroStatDivider} />
            <View style={styles.heroStat}>
              <Ionicons name="trophy" size={16} color={GOLD} />
              <Text style={styles.heroStatVal}>{longest}</Text>
              <Text style={styles.heroStatLabel}>Best</Text>
            </View>
          </View>
        </View>
        <View style={styles.section}>
          <View style={styles.sectionHeader}>
            <Ionicons name="flame" size={18} color="#F97316" />
            <Text style={styles.sectionTitle}>Daily Streak</Text>
            <Text style={styles.sectionBadge}>Day {streak}</Text>
          </View>
          <View style={styles.streakRow}>
            {STREAK_DAYS.map((d) => {
              const done = streak >= d.day;
              const isToday = streak + 1 === d.day;
              return (
                <View key={d.day} style={[styles.streakDay, done && styles.streakDayDone, isToday && styles.streakDayToday]}>
                  <Text style={[styles.streakDayNum, done && { color: '#000' }, isToday && { color: GOLD }]}>{d.day}</Text>
                  <Text style={[styles.streakDayCoins, done && { color: '#000' }]}>+{d.coins}</Text>
                </View>
              );
            })}
          </View>
          <Animated.View style={{ transform: [{ scale: bonusAvailable ? pulseAnim : 1 }] }}>
            <TouchableOpacity style={[styles.actionBtn, !bonusAvailable && styles.actionBtnDisabled]}
              onPress={claimBonus} disabled={!bonusAvailable || claimingBonus}>
              {claimingBonus ? <ActivityIndicator size="small" color="#000" /> : (
                <>
                  <Ionicons name="gift" size={18} color={bonusAvailable ? '#000' : '#555'} />
                  <Text style={[styles.actionBtnText, !bonusAvailable && { color: '#555' }]}>
                    {bonusAvailable ? 'Claim +' + nextBonus + ' Coins' : 'Bonus Claimed Today'}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </Animated.View>
        </View>


        {quests.length > 0 && (
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Ionicons name="list" size={18} color="#10B981" />
              <Text style={styles.sectionTitle}>Quests</Text>
            </View>
            {quests.map((q) => (
              <View key={q.id} style={styles.questCard}>
                <View style={styles.questIcon}><Ionicons name="checkmark-done" size={18} color="#10B981" /></View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.questTitle}>{q.title || q.name}</Text>
                  {q.description ? <Text style={styles.questDesc}>{q.description}</Text> : null}
                </View>
                <View style={styles.questReward}>
                  <Ionicons name="star" size={13} color={GOLD} />
                  <Text style={styles.questRewardText}>{q.reward_coins || q.coins || 0}</Text>
                </View>
              </View>
            ))}
          </View>
        )}
        {status?.gifts && (
          <View style={styles.section}>
            <View style={styles.sectionHeader}>
              <Ionicons name="gift" size={18} color="#EC4899" />
              <Text style={styles.sectionTitle}>Gifts Today</Text>
            </View>
            <View style={styles.giftsRow}>
              <View style={styles.giftStat}>
                <Ionicons name="arrow-up-circle" size={22} color="#EC4899" />
                <Text style={styles.giftStatVal}>{status.gifts.sent_today ?? 0}</Text>
                <Text style={styles.giftStatLabel}>Sent</Text>
              </View>
              <View style={styles.giftStatDivider} />
              <View style={styles.giftStat}>
                <Ionicons name="arrow-down-circle" size={22} color="#10B981" />
                <Text style={styles.giftStatVal}>{status.gifts.received_today ?? 0}</Text>
                <Text style={styles.giftStatLabel}>Received</Text>
              </View>
              <View style={styles.giftStatDivider} />
              <View style={styles.giftStat}>
                <Ionicons name="send" size={22} color={GOLD} />
                <Text style={styles.giftStatVal}>{status.gifts.sent_total ?? 0}</Text>
                <Text style={styles.giftStatLabel}>All Time</Text>
              </View>
            </View>
          </View>
        )}
      </ScrollView>

    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  centered: { justifyContent: 'center', alignItems: 'center' },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12 },
  backBtn: { width: 36, height: 36, borderRadius: 18, backgroundColor: '#1a1a1a', justifyContent: 'center', alignItems: 'center' },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#fff' },
  heroCard: { marginHorizontal: 16, marginBottom: 20, backgroundColor: CARD, borderRadius: 20, borderWidth: 1, borderColor: GOLD + '30', padding: 20 },
  heroMain: { flexDirection: 'row', alignItems: 'center', marginBottom: 18 },
  coinCircle: { width: 64, height: 64, borderRadius: 32, backgroundColor: GOLD + '18', borderWidth: 1.5, borderColor: GOLD + '40', justifyContent: 'center', alignItems: 'center' },
  coinAmount: { fontSize: 32, fontWeight: '900', color: GOLD, lineHeight: 34 },
  coinLabel: { fontSize: 12, color: '#666', fontWeight: '600', marginTop: 2 },
  heroStats: { flexDirection: 'row', borderTopWidth: 1, borderTopColor: BORDER, paddingTop: 14, justifyContent: 'space-around' },
  heroStat: { alignItems: 'center', gap: 4 },
  heroStatVal: { fontSize: 18, fontWeight: '800', color: '#fff' },
  heroStatLabel: { fontSize: 11, color: '#555', fontWeight: '600' },
  heroStatDivider: { width: 1, backgroundColor: BORDER },
  section: { marginHorizontal: 16, marginBottom: 20 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14 },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#fff', flex: 1 },
  sectionBadge: { backgroundColor: '#F9731622', color: '#F97316', fontSize: 11, fontWeight: '700', paddingHorizontal: 8, paddingVertical: 3, borderRadius: 10 },
  readyDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: '#10B981' },
  streakRow: { flexDirection: 'row', gap: 6, marginBottom: 14 },
  streakDay: { flex: 1, alignItems: 'center', paddingVertical: 10, backgroundColor: CARD, borderRadius: 12, borderWidth: 1, borderColor: BORDER },
  streakDayDone: { backgroundColor: GOLD, borderColor: GOLD },
  streakDayToday: { backgroundColor: '#1A1200', borderColor: GOLD },
  streakDayNum: { fontSize: 13, fontWeight: '800', color: '#666' },
  streakDayCoins: { fontSize: 9, color: '#555', fontWeight: '600', marginTop: 2 },
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, backgroundColor: GOLD, borderRadius: 14, padding: 14 },
  actionBtnDisabled: { backgroundColor: '#1a1a1a', borderWidth: 1, borderColor: BORDER },
  actionBtnText: { color: '#000', fontWeight: '800', fontSize: 15 },
  questCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: CARD, borderRadius: 14, borderWidth: 1, borderColor: BORDER, padding: 14, marginBottom: 8 },
  questIcon: { width: 38, height: 38, borderRadius: 12, backgroundColor: '#10B98118', justifyContent: 'center', alignItems: 'center' },
  questTitle: { fontSize: 14, fontWeight: '700', color: '#fff' },
  questDesc: { fontSize: 12, color: '#666', marginTop: 2 },
  questReward: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: GOLD + '18', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 },
  questRewardText: { color: GOLD, fontWeight: '700', fontSize: 13 },
  giftsRow: { flexDirection: 'row', backgroundColor: CARD, borderRadius: 16, borderWidth: 1, borderColor: BORDER, padding: 18, justifyContent: 'space-around', alignItems: 'center' },
  giftStat: { alignItems: 'center', gap: 6 },
  giftStatVal: { fontSize: 20, fontWeight: '800', color: '#fff' },
  giftStatLabel: { fontSize: 11, color: '#555', fontWeight: '600' },
  giftStatDivider: { width: 1, height: 40, backgroundColor: BORDER },
  spinCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: CARD, borderRadius: 16, borderWidth: 1, borderColor: GOLD + '30', padding: 16 },
  spinCardDisabled: { opacity: 0.5, borderColor: BORDER },
  spinIconContainer: { width: 56, height: 56, borderRadius: 14, backgroundColor: GOLD + '15', justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  spinContent: { flex: 1 },
  spinTitle: { fontSize: 16, fontWeight: '700', color: '#fff', marginBottom: 4 },
  spinSubtitle: { fontSize: 13, color: '#888' },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.8)', justifyContent: 'center', alignItems: 'center', padding: 20 },
  spinModal: { backgroundColor: CARD, borderRadius: 20, padding: 24, width: '100%', maxWidth: 380 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 18, fontWeight: '700', color: GOLD },
  wheelContainer: { width: 260, height: 260, alignSelf: 'center', marginBottom: 20, position: 'relative' },
  wheel: { width: '100%', height: '100%', borderRadius: 130, borderWidth: 4, borderColor: GOLD, position: 'absolute' },
  wheelSegment: { position: 'absolute', width: '100%', height: '100%', alignItems: 'center', justifyContent: 'center' },
  wheelEmoji: { fontSize: 28, position: 'absolute', top: 20 },
  wheelPointer: { position: 'absolute', top: -15, left: '50%', marginLeft: -10, width: 0, height: 0, borderLeftWidth: 10, borderRightWidth: 10, borderTopWidth: 20, borderLeftColor: 'transparent', borderRightColor: 'transparent', borderTopColor: GOLD },
  spinButton: { position: 'absolute', top: '50%', left: '50%', marginTop: -28, marginLeft: -28, width: 56, height: 56, borderRadius: 28, backgroundColor: CARD, borderWidth: 2, borderColor: GOLD, justifyContent: 'center', alignItems: 'center' },
  rewardsPreview: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginBottom: 20 },
  rewardItem: { width: '30%', alignItems: 'center', backgroundColor: '#1a1a1a', borderRadius: 10, padding: 8, marginBottom: 8 },
  rewardEmoji: { fontSize: 22, marginBottom: 4 },
  rewardLabel: { fontSize: 10, color: '#888', textAlign: 'center' },
  modalButton: { backgroundColor: GOLD, borderRadius: 12, padding: 14, alignItems: 'center' },
  modalButtonDisabled: { backgroundColor: '#333' },
  modalButtonText: { color: '#000', fontSize: 16, fontWeight: '700' },
  spinResult: { alignItems: 'center', padding: 20 },
  resultEmoji: { fontSize: 64, marginBottom: 12 },
  resultLabel: { fontSize: 20, fontWeight: '700', color: GOLD, marginBottom: 4 },
  resultAmount: { fontSize: 16, color: '#fff', marginBottom: 8 },
  resultBalance: { fontSize: 13, color: '#888', marginBottom: 20 },
});
