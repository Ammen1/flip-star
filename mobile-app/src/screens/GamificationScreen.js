import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, ActivityIndicator, Animated, RefreshControl, Dimensions } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import { AppAlert } from '../components/AppAlert';

const GOLD = '#C8B56A', BG = '#0B0B0C', CARD = '#161616', BORDER = '#242424';

function n(val, key) { if (val == null) return 0; if (typeof val === 'object') return val[key] ?? val.current ?? val.balance ?? 0; return Number(val) || 0; }

const STREAK_DAYS = [1,2,3,4,5,6,7].map((d,i) => ({ day: d, coins: [5,10,15,20,30,40,50][i] }));

export default function GamificationScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { width } = Dimensions.get('window');
  const [status, setStatus] = useState(null);
  const [quests, setQuests] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [claimingBonus, setClaimingBonus] = useState(false);
  const pulseAnim = useRef(new Animated.Value(1)).current;
  const slideAnim = useRef(new Animated.Value(0)).current;
  const fadeAnim = useRef(new Animated.Value(0)).current;

  useEffect(() => {
    loadAll();
    Animated.loop(Animated.sequence([
      Animated.timing(pulseAnim, { toValue: 1.06, duration: 800, useNativeDriver: true }),
      Animated.timing(pulseAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
    ])).start();
    
    // Entrance animations
    Animated.parallel([
      Animated.timing(slideAnim, { toValue: 1, duration: 600, useNativeDriver: true }),
      Animated.timing(fadeAnim, { toValue: 1, duration: 800, useNativeDriver: true }),
    ]).start();
  }, []);

  const loadAll = async (silent = false) => {
    if (!silent) setLoading(true); else setRefreshing(true);
    const [s, q] = await Promise.all([
      api.request('/gamification/status/').catch(() => null),
      api.request('/quests/').catch(() => []),
    ]);
    
    // Debug: Log the API response to understand the data structure
    console.log('Gamification status response:', s);
    
    // If gift data is missing, try to fetch it from a different endpoint
    if (s && (!s.gifts || (s.gifts.sent_today === 0 && s.gifts.received_today === 0))) {
      try {
        const giftHistory = await api.request('/gamification/gifts/history/');
        console.log('Gift history response:', giftHistory);
        
        // Calculate gift statistics from history if API doesn't provide them
        if (giftHistory) {
          const today = new Date().toDateString();
          const sentToday = (giftHistory.sent || []).filter(g => 
            new Date(g.created_at).toDateString() === today
          ).length;
          const receivedToday = (giftHistory.received || []).filter(g => 
            new Date(g.created_at).toDateString() === today
          ).length;
          const sentTotal = (giftHistory.sent || []).length;
          
          // Update the status object with calculated gift statistics
          s.gifts = {
            ...s.gifts,
            sent_today: sentToday,
            received_today: receivedToday,
            sent_total: sentTotal
          };
        }
      } catch (error) {
        console.log('Failed to fetch gift history:', error);
      }
    }
    
    setStatus(s); 
    setQuests(Array.isArray(q) ? q : (q?.results || []));
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

  if (loading) return <View style={[styles.container, { backgroundColor: colors.bg }, styles.centered]}><ActivityIndicator size='large' color={colors.primary} /></View>;

  const coins = n(status?.wallet?.balance?.total ?? status?.total_coins ?? status?.coins, 'balance');
  const streak = n(status?.login_streak, 'current');
  const longest = n(status?.login_streak, 'longest');
  const bonusAvailable = status?.login_streak?.bonus_available ?? false;
  const points = n(status?.points, 'balance');
  const nextBonus = status?.login_streak?.next_bonus?.coins ?? 0;
  
  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backBtn}>
          <Ionicons name="chevron-back" size={22} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>Rewards</Text>
        <TouchableOpacity onPress={() => loadAll(true)} style={styles.backBtn}>
          <Ionicons name="refresh" size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>
      
      <ScrollView showsVerticalScrollIndicator={false} contentContainerStyle={{ paddingBottom: insets.bottom + 32 }}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} tintColor={colors.primary} />}>
        
        <Animated.View 
          style={[
            styles.heroCard, 
            { 
              backgroundColor: colors.cardBg, 
              borderColor: colors.border,
              opacity: fadeAnim,
              transform: [{ translateY: slideAnim.interpolate({ inputRange: [0, 1], outputRange: [20, 0] }) }]
            }
          ]}
        >
          <LinearGradient
            colors={['rgba(200, 181, 106, 0.1)', 'rgba(200, 181, 106, 0.02)']}
            style={styles.heroGradient}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 1 }}
          />
          <View style={styles.heroMain}>
            <Animated.View style={[styles.coinCircle, { backgroundColor: colors.primary, transform: [{ scale: pulseAnim }] }]}>
              <Ionicons name="star" size={32} color="#000" />
            </Animated.View>
            <View style={{ marginLeft: 16 }}>
              <Text style={[styles.coinAmount, { color: colors.text }]}>{coins.toLocaleString()}</Text>
              <Text style={[styles.coinLabel, { color: colors.textSecondary }]}>Coins Balance</Text>
            </View>
          </View>
          <View style={styles.heroStats}>
            <View style={styles.heroStat}>
              <View style={[styles.statIconContainer, { backgroundColor: colors.error + '20' }]}>
                <Ionicons name="flame" size={16} color={colors.error} />
              </View>
              <Text style={[styles.heroStatVal, { color: colors.text }]}>{streak}</Text>
              <Text style={[styles.heroStatLabel, { color: colors.textSecondary }]}>Streak</Text>
            </View>
            <View style={[styles.heroStatDivider, { backgroundColor: colors.border }]} />
            <View style={styles.heroStat}>
              <View style={[styles.statIconContainer, { backgroundColor: colors.primary + '20' }]}>
                <Ionicons name="star" size={16} color={colors.primary} />
              </View>
              <Text style={[styles.heroStatVal, { color: colors.text }]}>{points.toLocaleString()}</Text>
              <Text style={[styles.heroStatLabel, { color: colors.textSecondary }]}>Points</Text>
            </View>
            <View style={[styles.heroStatDivider, { backgroundColor: colors.border }]} />
            <View style={styles.heroStat}>
              <View style={[styles.statIconContainer, { backgroundColor: colors.primary + '20' }]}>
                <Ionicons name="trophy" size={16} color={colors.primary} />
              </View>
              <Text style={[styles.heroStatVal, { color: colors.text }]}>{longest}</Text>
              <Text style={[styles.heroStatLabel, { color: colors.textSecondary }]}>Best</Text>
            </View>
          </View>
        </Animated.View>

        <Animated.View style={[styles.section, { backgroundColor: colors.cardBg, opacity: fadeAnim }]}>
          <LinearGradient
            colors={['rgba(239, 68, 68, 0.05)', 'rgba(239, 68, 68, 0.01)']}
            style={styles.sectionGradient}
            start={{ x: 0, y: 0 }}
            end={{ x: 1, y: 0 }}
          />
          <View style={[styles.sectionHeader, { borderBottomColor: colors.border }]}>
            <View style={[styles.sectionIconContainer, { backgroundColor: colors.error + '20' }]}>
              <Ionicons name="flame" size={18} color={colors.error} />
            </View>
            <Text style={[styles.sectionTitle, { color: colors.text }]}>Daily Streak</Text>
            <Animated.View style={[styles.sectionBadge, { backgroundColor: colors.primary, transform: [{ scale: bonusAvailable ? pulseAnim : 1 }] }]}>
              <Text style={[styles.sectionBadgeText, { color: '#000' }]}>Day {streak}</Text>
            </Animated.View>
          </View>
          <View style={styles.streakRow}>
            {STREAK_DAYS.map((d, index) => {
              const done = streak >= d.day;
              const isToday = streak + 1 === d.day;
              return (
                <Animated.View 
                  key={d.day} 
                  style={[
                    styles.streakDay, 
                    { 
                      backgroundColor: colors.bg, 
                      borderColor: colors.border,
                      transform: [{ scale: done ? 1.05 : 1 }]
                    }, 
                    done && { backgroundColor: colors.primary, borderColor: colors.primary }, 
                    isToday && { borderColor: colors.primary, borderWidth: 2 }
                  ]}
                >
                  <Text style={[styles.streakDayNum, { color: colors.textSecondary }, done && { color: '#000', fontWeight: '700' }, isToday && { color: colors.primary }]}>{d.day}</Text>
                  <Text style={[styles.streakDayCoins, { color: colors.textSecondary }, done && { color: '#000' }]}>+{d.coins}</Text>
                </Animated.View>
              );
            })}
          </View>
          <Animated.View style={{ transform: [{ scale: bonusAvailable ? pulseAnim : 1 }] }}>
            <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.primary }, !bonusAvailable && { backgroundColor: colors.border }]}
              onPress={claimBonus} disabled={!bonusAvailable || claimingBonus}>
              {claimingBonus ? <ActivityIndicator size="small" color="#000" /> : (
                <>
                  <Ionicons name="gift" size={18} color={bonusAvailable ? '#000' : colors.textSecondary} />
                  <Text style={[styles.actionBtnText, { color: '#000' }, !bonusAvailable && { color: colors.textSecondary }]}>
                    {bonusAvailable ? 'Claim +' + nextBonus + ' Coins' : 'Bonus Claimed Today'}
                  </Text>
                </>
              )}
            </TouchableOpacity>
          </Animated.View>
        </Animated.View>

        {quests.length > 0 && (
          <Animated.View style={[styles.section, { backgroundColor: colors.cardBg, opacity: fadeAnim }]}>
            <LinearGradient
              colors={['rgba(34, 197, 94, 0.05)', 'rgba(34, 197, 94, 0.01)']}
              style={styles.sectionGradient}
              start={{ x: 0, y: 0 }}
              end={{ x: 1, y: 0 }}
            />
            <View style={[styles.sectionHeader, { borderBottomColor: colors.border }]}>
              <View style={[styles.sectionIconContainer, { backgroundColor: colors.primary + '20' }]}>
                <Ionicons name="list" size={18} color={colors.primary} />
              </View>
              <Text style={[styles.sectionTitle, { color: colors.text }]}>Quests</Text>
              <View style={[styles.questCountBadge, { backgroundColor: colors.primary + '20' }]}>
                <Text style={[styles.questCountText, { color: colors.primary }]}>{quests.length}</Text>
              </View>
            </View>
            {quests.map((q, index) => (
              <Animated.View 
                key={q.id} 
                style={[
                  styles.questCard, 
                  { 
                    backgroundColor: colors.bg, 
                    borderColor: colors.border,
                    transform: [{ translateY: fadeAnim.interpolate({ inputRange: [0, 1], outputRange: [20 * (index + 1), 0] }) }]
                  }
                ]}
              >
                <View style={[styles.questIcon, { backgroundColor: colors.primary }]}>
                  <Ionicons name="checkmark-done" size={18} color="#000" />
                </View>
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={[styles.questTitle, { color: colors.text }]}>{q.title || q.name}</Text>
                  {q.description ? <Text style={[styles.questDesc, { color: colors.textSecondary }]}>{q.description}</Text> : null}
                </View>
                <View style={styles.questReward}>
                  <Ionicons name="star" size={13} color={colors.primary} />
                  <Text style={styles.questRewardText}>{q.reward_coins || q.coins || 0}</Text>
                </View>
              </Animated.View>
            ))}
          </Animated.View>
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
  headerTitle: { fontSize: 18, fontWeight: '800', color: '#fff' },
  
  // Enhanced Hero Styles
  heroCard: { 
    margin: 16, 
    borderRadius: 20, 
    borderWidth: 1, 
    padding: 20, 
    position: 'relative',
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  heroGradient: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 20,
  },
  heroMain: { flexDirection: 'row', alignItems: 'center', marginBottom: 20 },
  coinCircle: { 
    width: 64, 
    height: 64, 
    borderRadius: 32, 
    justifyContent: 'center', 
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 4,
  },
  coinAmount: { fontSize: 32, fontWeight: '900', color: '#fff', letterSpacing: -1 },
  coinLabel: { fontSize: 13, color: '#666', marginTop: 2 },
  heroStats: { flexDirection: 'row', justifyContent: 'space-between' },
  heroStat: { alignItems: 'center', flex: 1 },
  statIconContainer: {
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 4,
  },
  heroStatVal: { fontSize: 18, fontWeight: '700', color: '#fff', marginBottom: 2 },
  heroStatLabel: { fontSize: 11, color: '#666', textTransform: 'uppercase', letterSpacing: 0.5 },
  heroStatDivider: { width: 1, height: 40, marginHorizontal: 8 },
  
  // Enhanced Section Styles
  section: { marginHorizontal: 16, marginBottom: 20 },
  sectionGradient: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    borderRadius: 16,
  },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 14, borderBottomWidth: 1, borderBottomColor: BORDER, paddingBottom: 10 },
  sectionIconContainer: {
    width: 32,
    height: 32,
    borderRadius: 16,
    justifyContent: 'center',
    alignItems: 'center',
  },
  sectionTitle: { fontSize: 15, fontWeight: '700', color: '#fff', flex: 1 },
  sectionBadge: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 12 },
  sectionBadgeText: { fontSize: 11, fontWeight: '700' },
  
  // Streak Styles
  streakRow: { flexDirection: 'row', gap: 6, marginBottom: 14 },
  streakDay: { flex: 1, alignItems: 'center', paddingVertical: 10, backgroundColor: CARD, borderRadius: 12, borderWidth: 1, borderColor: BORDER },
  streakDayNum: { fontSize: 13, fontWeight: '800', color: '#666' },
  streakDayCoins: { fontSize: 9, color: '#555', fontWeight: '600', marginTop: 2 },
  
  // Action Button Styles
  actionBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, borderRadius: 14, padding: 14 },
  actionBtnText: { fontWeight: '800', fontSize: 15 },
  
  // Quest Styles
  questCountBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 12 },
  questCountText: { fontSize: 11, fontWeight: '700' },
  questCard: { flexDirection: 'row', alignItems: 'center', backgroundColor: CARD, borderRadius: 14, borderWidth: 1, borderColor: BORDER, padding: 14, marginBottom: 8 },
  questIcon: { width: 38, height: 38, borderRadius: 12, justifyContent: 'center', alignItems: 'center' },
  questTitle: { fontSize: 14, fontWeight: '700', color: '#fff' },
  questDesc: { fontSize: 12, color: '#666', marginTop: 2 },
  questReward: { flexDirection: 'row', alignItems: 'center', gap: 4, backgroundColor: GOLD + '18', paddingHorizontal: 10, paddingVertical: 5, borderRadius: 20 },
  questRewardText: { color: GOLD, fontWeight: '700', fontSize: 13 },
});
