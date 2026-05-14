import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, Alert, Modal, TextInput, RefreshControl, FlatList,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

function timeAgo(d) {
  if (!d) return '';
  const dt = new Date(d);
  return dt.toLocaleDateString();
}

export default function WalletScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [summary, setSummary] = useState(null);
  const [config, setConfig] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [withdrawals, setWithdrawals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeTab, setActiveTab] = useState('overview');
  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(false);
  const [withdrawAmount, setWithdrawAmount] = useState('');
  const [withdrawAccount, setWithdrawAccount] = useState('');
  const [withdrawMethod, setWithdrawMethod] = useState('telebirr');
  const [processing, setProcessing] = useState(false);
  const [packages, setPackages] = useState([]);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [phone, setPhone] = useState('');

  useEffect(() => { loadAll(); }, []);

  const loadAll = async (silent = false) => {
    try {
      if (!silent) setLoading(true); else setRefreshing(true);
      const [s, c, pkgs, profile] = await Promise.all([
        api.request('/wallet/'),
        api.request('/wallet/config/').catch(() => ({})),
        api.request('/coins/packages/').catch(() => []),
        api.request('/profile/me/').catch(() => ({})),
      ]);
      console.log('Wallet data:', s);
      console.log('Profile data:', profile);
      setSummary({ ...s, profile });
      setConfig(c);
      setPackages(Array.isArray(pkgs) ? pkgs : (pkgs.results || []));
      
      // Always load all transactions to match website behavior
      if (!transactions.length) {
        loadTransactions();
      } else if (silent) {
        // If refreshing silently, still load all transactions to get latest
        loadTransactions();
      }
    } catch (e) { 
      console.error('Wallet load error:', e);
      Alert.alert('Error', 'Failed to load wallet'); 
    }
    finally { setLoading(false); setRefreshing(false); }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab === 'transactions' && transactions.length === 0) loadTransactions();
    if (tab === 'withdrawals' && withdrawals.length === 0) loadWithdrawals();
  };

  const loadTransactions = async () => {
    try {
      let allTransactions = [];
      let page = 1;
      let hasMore = true;
      let consecutiveEmptyPages = 0;
      
      while (hasMore && consecutiveEmptyPages < 3) {
        try {
          const data = await api.request(`/wallet/transactions/?page=${page}&page_size=100`);
          const pageTransactions = data.results || [];
          
          if (pageTransactions.length > 0) {
            allTransactions = [...allTransactions, ...pageTransactions];
            consecutiveEmptyPages = 0;
            console.log(`Page ${page}: Loaded ${pageTransactions.length} transactions`);
          } else {
            consecutiveEmptyPages++;
            console.log(`Page ${page}: No transactions found`);
          }
          
          hasMore = data.has_next && pageTransactions.length > 0;
          page++;
          
          // Safety check: don't load more than 50 pages total
          if (page > 50) {
            console.log('Reached maximum page limit (50), stopping pagination');
            break;
          }
        } catch (pageError) {
          console.error(`Error loading page ${page}:`, pageError);
          consecutiveEmptyPages++;
          if (consecutiveEmptyPages >= 3) {
            console.log('Too many consecutive errors, stopping pagination');
            break;
          }
          page++;
        }
      }
      
      // Sort transactions by date (newest first)
      allTransactions.sort((a, b) => new Date(b.created_at) - new Date(a.created_at));
      
      console.log(`✅ Total loaded: ${allTransactions.length} transactions from ${page - 1} pages`);
      setTransactions(allTransactions);
    } catch (e) {
      console.error('❌ Critical error loading transactions:', e);
      // Fallback to empty array to prevent UI issues
      setTransactions([]);
    }
  };

  const loadWithdrawals = async () => {
    try {
      let allWithdrawals = [];
      let page = 1;
      let hasMore = true;
      
      while (hasMore) {
        try {
          const data = await api.request(`/wallet/withdrawals/?page=${page}&page_size=100`);
          const pageWithdrawals = data.results || [];
          
          if (pageWithdrawals.length > 0) {
            allWithdrawals = [...allWithdrawals, ...pageWithdrawals];
            hasMore = data.has_next;
            page++;
          } else {
            hasMore = false;
          }
        } catch (e) {
          console.error(`Error loading withdrawals page ${page}:`, e);
          hasMore = false;
        }
      }
      
      setWithdrawals(allWithdrawals);
    } catch (e) {
      console.error('Error loading withdrawals:', e);
      setWithdrawals([]);
    }
  };

  const handleWithdraw = async () => {
    if (!withdrawAmount || !withdrawMethod || !withdrawAccount) {
      Alert.alert('Error', 'Please fill all fields');
      return;
    }
    if (withdrawAccount.length !== 6 || !/^\d{6}$/.test(withdrawAccount)) {
      Alert.alert('Error', 'Please enter a valid 6-digit PIN'); return;
    }
    setProcessing(true);
    try {
      await api.request('/wallet/withdraw/', {
        method: 'POST',
        body: JSON.stringify({ coin_amount: parseInt(withdrawAmount), payout_method: withdrawMethod, payout_account: withdrawAccount }),
      });
      Alert.alert('Success', 'Withdrawal request submitted');
      setShowWithdrawModal(false);
      setWithdrawAmount(''); setWithdrawAccount('');
      loadAll(true);
    } catch (e) { Alert.alert('Error', e.message || 'Withdrawal failed'); }
    finally { setProcessing(false); }
  };

  const handleMonetizeCoins = async () => {
    const availableCoins = summary?.balance?.purchased || 0;
    if (availableCoins < 1000) {
      Alert.alert('Insufficient Coins', 'You need at least 1,000 purchased coins to monetize.');
      return;
    }
    
    Alert.alert(
      'Monetize Coins',
      `Convert ${availableCoins} coins to ETB via telebirr?\nEstimated payout: ${(availableCoins * 0.08).toFixed(2)} ETB (after 20% commission)`,
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Monetize',
          onPress: async () => {
            try {
              const response = await api.request('/monetize/', {
                method: 'POST',
                body: JSON.stringify({
                  coins: availableCoins,
                  method: 'telebirr'
                })
              });
              
              Alert.alert(
                'Success', 
                `Monetization request submitted!\n${availableCoins} coins will be converted to ${(availableCoins * 0.08).toFixed(2)} ETB`
              );
              loadAll();
            } catch (error) {
              Alert.alert('Error', 'Monetization failed. Please try again.');
            }
          }
        }
      ]
    );
  };

  const handleTopUp = async () => {
    if (!selectedPackage || !phone) {
      Alert.alert('Error', 'Select a package and enter phone number'); return;
    }
    setProcessing(true);
    try {
      const res = await api.request('/wallet/telebirr/initiate/', {
        method: 'POST',
        body: JSON.stringify({ package_id: selectedPackage.id, phone_number: phone }),
      });
      Alert.alert('Payment Initiated', res.message || 'Complete payment in telebirr app');
      setShowTopUpModal(false);
      loadAll(true);
    } catch (e) { Alert.alert('Error', e.message || 'Payment failed'); }
    finally { setProcessing(false); }
  };

  const renderTxRow = (tx) => {
    const isGift = tx.type === 'gift_sent' || tx.type === 'gift_received';
    const isPointTx = tx.type === 'gift_received';
    const isPurchase = tx.type === 'purchase' || tx.type === 'coin_purchase';
    const isBonus = tx.type === 'bonus' || tx.type === 'daily_bonus' || tx.type === 'weekly_bonus' || tx.type === 'monthly_bonus';
    const isWithdrawal = tx.type === 'withdrawal';
    
    let primaryLabel = tx.type_display || tx.type;
    if (tx.type === 'gift_sent' && tx.other_user) {
      primaryLabel = `Gift sent to @${tx.other_user.username}`;
    } else if (tx.type === 'gift_received' && tx.other_user) {
      primaryLabel = `Gift from @${tx.other_user.username}`;
    } else if (isPurchase) {
      primaryLabel = 'Coin Purchase';
    } else if (isBonus) {
      primaryLabel = tx.type_display || 'Bonus Received';
    } else if (isWithdrawal) {
      primaryLabel = 'Withdrawal';
    }
    
    // Choose appropriate icon
    let iconName = 'arrow-down'; // default
    if (isGift) iconName = 'gift';
    else if (isPurchase) iconName = 'cart';
    else if (isBonus) iconName = 'star';
    else if (isWithdrawal) iconName = 'arrow-up';
    else iconName = tx.is_credit ? 'arrow-down' : 'arrow-up';
    
    // Build post info for gift transactions
    let postInfo = '';
    if (isGift && tx.post_details) {
      const post = tx.post_details;
      if (post.title) {
        postInfo = ` • Post: ${post.title}`;
      } else if (post.description && post.description.length > 30) {
        postInfo = ` • Post: ${post.description.substring(0, 30)}...`;
      } else if (post.description) {
        postInfo = ` • Post: ${post.description}`;
      }
    }
    
    // Ensure amount is displayed
    const amount = Math.abs(tx.coins || tx.amount || 0);
    const currency = isPointTx ? 'points' : (tx.currency || 'coins');
    
    return (
      <View key={tx.id || `${tx.type}-${tx.created_at}`} style={styles.txItem}>
        <View style={[styles.txIcon, { backgroundColor: tx.is_credit ? '#0D2D1A' : '#2D1010' }]}>
          <Ionicons name={iconName} size={16} color={tx.is_credit ? '#10B981' : '#EF4444'} />
        </View>
        <View style={{ flex: 1, marginLeft: 12 }}>
          <Text style={styles.txType}>{primaryLabel}</Text>
          <Text style={styles.txDate}>
            {timeAgo(tx.created_at)}
            {tx.description ? ` • ${tx.description}` : ''}
            {postInfo}
          </Text>
        </View>
        <View style={{ alignItems: 'flex-end' }}>
          <Text style={[styles.txAmount, { color: tx.is_credit ? '#10B981' : '#EF4444' }]}>
            {tx.is_credit ? '+' : '-'}{amount}
          </Text>
          <Text style={{ fontSize: 10, color: '#666' }}>{currency}</Text>
        </View>
      </View>
    );
  };

  const total = summary?.balance?.total ?? summary?.total ?? 0;
  const earned = summary?.balance?.earned ?? summary?.earned_total ?? 0;
  const purchased = summary?.balance?.purchased ?? summary?.purchased_total ?? 0;
  const points = summary?.points || { current: 0, earned_total: 0, withdrawn_total: 0 };
  
  // Gamification stats from profile
  const profile = summary?.profile || {};
  const coins = profile.coins || 0;
  const loginStreak = profile.login_streak || 0;
  const xp = profile.xp || 0;
  const level = profile.level || 1;

  if (loading) return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top, justifyContent: 'center', alignItems: 'center' }]}>
      <ActivityIndicator size="large" color={colors.primary} />
    </View>
  );

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.primary} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>Wallet</Text>
        <TouchableOpacity onPress={() => loadAll(true)}>
          {refreshing ? <ActivityIndicator size="small" color={colors.primary} /> : <Ionicons name="refresh" size={22} color={colors.primary} />}
        </TouchableOpacity>
      </View>

      <ScrollView
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} tintColor={colors.primary} />}
        showsVerticalScrollIndicator={false}
        contentContainerStyle={{ paddingBottom: insets.bottom + 20 }}
      >
        {/* Three Horizontal Dashboard Cards */}
        <View style={styles.dashboardRow}>
          {/* Card 1: Coins */}
          <View style={[styles.dashCard, { backgroundColor: '#D4AF37' }]}>
            <View style={styles.dashCardHeader}>
              <Ionicons name="wallet" size={14} color="#1A1A1A" />
              <Text style={styles.dashCardTitle}>COINS</Text>
            </View>
            <Text style={styles.dashCardValue}>{total}</Text>
            <Text style={styles.dashCardSubtitle}>Total Coins</Text>
            <View style={[styles.dashCardDivider, { borderTopColor: 'rgba(0,0,0,0.15)' }]}>
              <View style={styles.dashCardRow}>
                <Text style={styles.dashCardLabel}>Earned</Text>
                <Text style={styles.dashCardStrong}>{earned}</Text>
              </View>
              <View style={styles.dashCardRow}>
                <Text style={styles.dashCardLabel}>Purchased</Text>
                <Text style={styles.dashCardStrong}>{purchased}</Text>
              </View>
            </View>
          </View>

          {/* Card 2: Points */}
          <View style={[styles.dashCard, { backgroundColor: '#8B5CF6' }]}>
            <View style={styles.dashCardHeader}>
              <Ionicons name="gift" size={14} color="#fff" />
              <Text style={[styles.dashCardTitle, { color: '#fff' }]}>POINTS</Text>
            </View>
            <Text style={[styles.dashCardValue, { color: '#fff' }]}>{points.current || 0}</Text>
            <Text style={[styles.dashCardSubtitle, { color: 'rgba(255,255,255,0.85)' }]}>Balance</Text>
            <View style={[styles.dashCardDivider, { borderTopColor: 'rgba(255,255,255,0.2)' }]}>
              <View style={styles.dashCardRow}>
                <Text style={[styles.dashCardLabel, { color: 'rgba(255,255,255,0.85)' }]}>Earned</Text>
                <Text style={[styles.dashCardStrong, { color: '#fff' }]}>{points.earned_total || 0}</Text>
              </View>
              <View style={styles.dashCardRow}>
                <Text style={[styles.dashCardLabel, { color: 'rgba(255,255,255,0.85)' }]}>Gifts</Text>
                <Text style={[styles.dashCardStrong, { color: '#fff' }]}>{points.earned_total || 0}</Text>
              </View>
            </View>
          </View>

          {/* Card 3: Withdraw */}
          <View style={[styles.dashCard, { backgroundColor: '#10B981' }]}>
            <View style={styles.dashCardHeader}>
              <Ionicons name="cash" size={14} color="#fff" />
              <Text style={[styles.dashCardTitle, { color: '#fff' }]}>WITHDRAW</Text>
            </View>
            <Text style={[styles.dashCardValue, { color: '#fff' }]}>
              {(((points.current || 0) / (config?.points_per_birr || 10))).toFixed(1)}
            </Text>
            <Text style={[styles.dashCardSubtitle, { color: 'rgba(255,255,255,0.85)' }]}>ETB Available</Text>
            <View style={[styles.dashCardDivider, { borderTopColor: 'rgba(255,255,255,0.2)' }]}>
              <View style={styles.dashCardRow}>
                <Text style={[styles.dashCardLabel, { color: 'rgba(255,255,255,0.85)' }]}>Min</Text>
                <Text style={[styles.dashCardStrong, { color: '#fff' }]}>{config?.withdrawal_min_points || 100} pts</Text>
              </View>
              <TouchableOpacity
                onPress={() => setShowWithdrawModal(true)}
                disabled={(points.current || 0) < (config?.withdrawal_min_points || 100)}
                style={[
                  styles.dashCardBtn,
                  { opacity: (points.current || 0) >= (config?.withdrawal_min_points || 100) ? 1 : 0.5 },
                ]}
              >
                <Text style={styles.dashCardBtnText}>Points → Birr</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>

        {/* Gamification Stats */}
        <View style={styles.statsContainer}>
          <View style={[styles.statItem, { backgroundColor: colors.cardBg }]}>
            <Ionicons name="flame" size={28} color={colors.error} />
            <Text style={[styles.statNumber, { color: colors.text }]}>{loginStreak}</Text>
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Streak</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: colors.cardBg }]}>
            <Ionicons name="star" size={28} color={colors.primary} />
            <Text style={[styles.statNumber, { color: colors.text }]}>{points.current || 0}</Text>
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Points</Text>
          </View>
                    <View style={[styles.statItem, { backgroundColor: colors.cardBg }]}>
            <Ionicons name="trophy" size={28} color={colors.primary} />
            <Text style={[styles.statNumber, { color: colors.text }]}>{level}</Text>
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Level</Text>
          </View>
        </View>

        {/* Action buttons */}
        <View style={styles.actionRow}>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => navigation.navigate('CoinPurchase')}>
            <View style={[styles.actionGrad, { backgroundColor: GOLD }]}>
              <Ionicons name="add-circle" size={24} color="#fff" />
              <Text style={styles.actionText}>Buy Coins</Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => setShowWithdrawModal(true)}>
            <View style={[styles.actionGrad, { backgroundColor: GOLD }]}>
              <Ionicons name="arrow-up-circle" size={24} color="#fff" />
              <Text style={styles.actionText}>Withdraw</Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => handleTabChange('transactions')}>
            <View style={[styles.actionGrad, { backgroundColor: GOLD }]}>
              <Ionicons name="receipt" size={24} color="#fff" />
              <Text style={styles.actionText}>History</Text>
            </View>
          </TouchableOpacity>
        </View>

        {/* Tabs */}
        <View style={[styles.tabs, { borderBottomColor: colors.border }]}>
          {['overview', 'transactions', 'withdrawals'].map(tab => (
            <TouchableOpacity key={tab} style={styles.tabBtn} onPress={() => handleTabChange(tab)}>
              <Text style={[styles.tabText, { color: colors.textSecondary }, activeTab === tab && { color: colors.primary, fontWeight: '700' }]}>
                {tab.charAt(0).toUpperCase() + tab.slice(1)}
              </Text>
              {activeTab === tab && <View style={[styles.tabIndicator, { backgroundColor: colors.primary }]} />}
            </TouchableOpacity>
          ))}
        </View>

        <View style={{ padding: 16 }}>
          {/* Overview */}
          {activeTab === 'overview' && (
            <>
              {/* Recent Transactions */}
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <Text style={styles.sectionTitle}>Recent Transactions</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12, color: colors.textSecondary, marginRight: 8 }}>
                    {transactions.length > 0 ? `${transactions.length} total` : ''}
                  </Text>
                  <TouchableOpacity onPress={() => loadAll(true)} style={{ padding: 4 }}>
                    <Ionicons name="refresh" size={16} color={colors.primary} />
                  </TouchableOpacity>
                </View>
              </View>
              {transactions.length === 0
                ? <Text style={styles.emptyText}>No transactions yet</Text>
                : transactions.slice(0, 5).map(renderTxRow)}
              {transactions.length > 5 && (
                <TouchableOpacity onPress={() => setActiveTab('transactions')}>
                  <Text style={[styles.viewAllText, { color: colors.primary }]}>View all transactions →</Text>
                </TouchableOpacity>
              )}

              {/* Coin Packages */}
              <Text style={styles.sectionTitle}>Coin Packages</Text>
              {packages.length === 0
                ? <Text style={styles.emptyText}>No packages available</Text>
                : packages.map(pkg => (
                  <TouchableOpacity
                    key={pkg.id}
                    style={[styles.packageCard, selectedPackage?.id === pkg.id && styles.packageCardSelected]}
                    onPress={() => { setSelectedPackage(pkg); setShowTopUpModal(true); }}
                  >
                    <View>
                      <Text style={styles.pkgName}>{pkg.name}</Text>
                      <Text style={styles.pkgCoins}>{pkg.coin_amount} coins</Text>
                      {pkg.bonus_coins > 0 && <Text style={styles.pkgBonus}>+{pkg.bonus_coins} bonus ?</Text>}
                    </View>
                    <View style={{ alignItems: 'flex-end' }}>
                      <Text style={styles.pkgPrice}>{pkg.price_etb} ETB</Text>
                      {pkg.is_featured && <View style={styles.featuredBadge}><Text style={styles.featuredText}>? Popular</Text></View>}
                    </View>
                  </TouchableOpacity>
                ))}
              <View style={styles.infoBox}>
                <Ionicons name="information-circle" size={18} color={GOLD} />
                <Text style={styles.infoText}>Only purchased coins can be used for gifting. Earned coins cannot be gifted.</Text>
              </View>
            </>
          )}

          {/* Transactions */}
          {activeTab === 'transactions' && (
            <>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <Text style={styles.sectionTitle}>All Transactions</Text>
                <View style={{ flexDirection: 'row', alignItems: 'center' }}>
                  <Text style={{ fontSize: 12, color: colors.textSecondary, marginRight: 8 }}>
                    {transactions.length > 0 ? `${transactions.length} loaded` : ''}
                  </Text>
                  <TouchableOpacity onPress={() => loadAll(true)} style={{ padding: 4 }}>
                    <Ionicons name="refresh" size={16} color={colors.primary} />
                  </TouchableOpacity>
                </View>
              </View>
              {transactions.length === 0
                ? <Text style={styles.emptyText}>No transactions yet</Text>
                : (
                  <FlatList
                    data={transactions}
                    keyExtractor={(item) => item.id?.toString() || `${item.type}-${item.created_at}`}
                    renderItem={({ item }) => renderTxRow(item)}
                    scrollEnabled={false}
                    nestedScrollEnabled={false}
                  />
                )}
              {activeTab === 'transactions' && transactions.length > 0 && (
                <View style={[styles.monetizeSection, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
                  <View style={styles.monetizeHeader}>
                    <Ionicons name="cash-outline" size={24} color={GOLD} />
                    <View style={styles.monetizeInfo}>
                      <Text style={[styles.monetizeTitle, { color: colors.text }]}>Monetize Your Coins</Text>
                      <Text style={[styles.monetizeSubtitle, { color: colors.textSecondary }]}>
                        Convert your available coins to ETB via telebirr
                      </Text>
                    </View>
                  </View>
                  <TouchableOpacity 
                    style={[styles.monetizeBtn, { backgroundColor: GOLD }]}
                    onPress={() => handleMonetizeCoins()}
                  >
                    <Ionicons name="trending-up" size={20} color="#000" />
                    <Text style={styles.monetizeBtnText}>Monetize All Coins</Text>
                  </TouchableOpacity>
                </View>
              )}
            </>
          )}

          {/* Withdrawals */}
          {activeTab === 'withdrawals' && (
            <>
              <Text style={styles.sectionTitle}>Withdrawals</Text>
              {withdrawals.length === 0
                ? <Text style={styles.emptyText}>No withdrawals yet</Text>
                : (
                  <FlatList
                    data={withdrawals}
                    keyExtractor={(item) => item.id?.toString()}
                    renderItem={({ item: w }) => (
                      <View key={w.id} style={styles.txItem}>
                        <View style={[styles.txIcon, { backgroundColor: '#1A1A2D' }]}>
                          <Ionicons name="card-outline" size={16} color="#667eea" />
                        </View>
                        <View style={{ flex: 1, marginLeft: 12 }}>
                          <Text style={styles.txType}>{w.coin_amount} coins → {w.net_birr} ETB</Text>
                          <Text style={styles.txDate}>{w.status}</Text>
                        </View>
                        <View style={[styles.statusBadge, { backgroundColor: w.status === 'completed' ? '#0D2D1A' : '#2D2010' }]}>
                          <Text style={{ color: w.status === 'completed' ? '#10B981' : GOLD, fontSize: 11, fontWeight: '700' }}>{w.status}</Text>
                        </View>
                      </View>
                    )}
                    scrollEnabled={false}
                    nestedScrollEnabled={false}
                  />
                )}
            </>
          )}
        </View>
      </ScrollView>

      {/* Withdraw Modal */}
      <Modal visible={showWithdrawModal} transparent animationType="slide" onRequestClose={() => setShowWithdrawModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Withdraw Coins</Text>
              <TouchableOpacity onPress={() => setShowWithdrawModal(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            <Text style={styles.fieldLabel}>Amount (coins)</Text>
            <TextInput style={styles.input} placeholder="e.g. 500" placeholderTextColor="#666" value={withdrawAmount} onChangeText={setWithdrawAmount} keyboardType="number-pad" />
            <Text style={styles.fieldLabel}>Payout Method</Text>
            <View style={styles.methodRow}>
              {['telebirr'].map(m => (
                <TouchableOpacity key={m} style={[styles.methodBtn, withdrawMethod === m && styles.methodBtnActive]} onPress={() => setWithdrawMethod(m)}>
                  <Text style={[styles.methodText, withdrawMethod === m && styles.methodTextActive]}>{m.replace('_', ' ')}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.fieldLabel}>6-Digit PIN</Text>
            <TextInput 
              style={styles.input} 
              placeholder="Enter 6-digit PIN" 
              placeholderTextColor="#666" 
              value={withdrawAccount} 
              onChangeText={setWithdrawAccount} 
              keyboardType="number-pad" 
              maxLength={6}
              secureTextEntry={true}
            />
            <TouchableOpacity style={[styles.submitBtn, processing && { opacity: 0.6 }]} onPress={handleWithdraw} disabled={processing}>
              {processing ? <ActivityIndicator color="#000" /> : <Text style={styles.submitBtnText}>Submit Withdrawal</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Top Up Modal */}
      <Modal visible={showTopUpModal} transparent animationType="slide" onRequestClose={() => setShowTopUpModal(false)}>
        <View style={styles.modalOverlay}>
          <View style={styles.modalSheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Buy Coins via telebirr</Text>
              <TouchableOpacity onPress={() => setShowTopUpModal(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            {selectedPackage && (
              <View style={styles.selectedPkg}>
                <Ionicons name="diamond-outline" size={28} color={GOLD} />
                <View style={{ flex: 1, marginLeft: 12 }}>
                  <Text style={styles.pkgName}>{selectedPackage.name}</Text>
                  <Text style={styles.pkgCoins}>{selectedPackage.coin_amount} coins</Text>
                </View>
                <Text style={styles.pkgPrice}>{selectedPackage.price_etb} ETB</Text>
              </View>
            )}
            <Text style={styles.fieldLabel}>Phone Number (telebirr)</Text>
            <TextInput style={styles.input} placeholder="+251 9xx xxx xxx" placeholderTextColor="#666" value={phone} onChangeText={setPhone} keyboardType="phone-pad" />
            <TouchableOpacity style={[styles.submitBtn, (!selectedPackage || !phone || processing) && { opacity: 0.6 }]} onPress={handleTopUp} disabled={!selectedPackage || !phone || processing}>
              {processing ? <ActivityIndicator color="#000" /> : <Text style={styles.submitBtnText}>{selectedPackage ? `Pay ${selectedPackage.price_etb} ETB` : 'Select a package'}</Text>}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 18, fontWeight: '700', color: GOLD },
  balanceCard: { margin: 16, padding: 24, borderRadius: 20, overflow: 'hidden' },
  balanceHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  balanceLabel: { fontSize: 13, color: '#000', fontWeight: '600' },
  balanceAmount: { fontSize: 44, fontWeight: '900', color: '#000', marginVertical: 4 },
  balanceSubtext: { fontSize: 13, color: '#000', opacity: 0.8 },
  dashboardRow: { flexDirection: 'row', paddingHorizontal: 12, paddingTop: 16, gap: 8, marginBottom: 12 },
  dashCard: { flex: 1, padding: 12, borderRadius: 14, minHeight: 160 },
  dashCardHeader: { flexDirection: 'row', alignItems: 'center', gap: 4, marginBottom: 6 },
  dashCardTitle: { fontSize: 10, fontWeight: '800', color: '#1A1A1A', letterSpacing: 0.5 },
  dashCardValue: { fontSize: 22, fontWeight: '900', color: '#1A1A1A', lineHeight: 24 },
  dashCardSubtitle: { fontSize: 10, color: 'rgba(0,0,0,0.7)', marginTop: 2, marginBottom: 8 },
  dashCardDivider: { marginTop: 'auto', paddingTop: 8, borderTopWidth: 1 },
  dashCardRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 },
  dashCardLabel: { fontSize: 10, color: 'rgba(0,0,0,0.7)' },
  dashCardStrong: { fontSize: 10, fontWeight: '700', color: '#1A1A1A' },
  dashCardBtn: { marginTop: 6, padding: 6, borderRadius: 6, backgroundColor: 'rgba(255,255,255,0.2)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)', alignItems: 'center' },
  dashCardBtnText: { fontSize: 10, fontWeight: '700', color: '#fff' },
  actionRow: { flexDirection: 'row', paddingHorizontal: 16, gap: 10, marginBottom: 8 },
  actionBtn: { flex: 1, borderRadius: 14, overflow: 'hidden' },
  actionGrad: { padding: 14, alignItems: 'center', gap: 6, backgroundColor: '#2A2A2A', borderRadius: 14 },
  actionText: { color: '#fff', fontSize: 11, fontWeight: '700' },
  tabs: { flexDirection: 'row', borderBottomWidth: 1, borderBottomColor: BORDER, paddingHorizontal: 16 },
  tabBtn: { flex: 1, paddingVertical: 12, alignItems: 'center', position: 'relative' },
  tabText: { fontSize: 13, color: '#666', fontWeight: '500' },
  tabTextActive: { color: GOLD, fontWeight: '700' },
  tabIndicator: { position: 'absolute', bottom: 0, left: 0, right: 0, height: 2, backgroundColor: GOLD },
  sectionTitle: { fontSize: 16, fontWeight: '700', color: GOLD, marginBottom: 12 },
  emptyText: { color: '#666', textAlign: 'center', padding: 24 },
  packageCard: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', backgroundColor: CARD, borderRadius: 14, padding: 16, marginBottom: 10, borderWidth: 1, borderColor: BORDER },
  packageCardSelected: { borderColor: GOLD, backgroundColor: GOLD + '10' },
  pkgName: { fontSize: 15, fontWeight: '600', color: '#fff', marginBottom: 2 },
  pkgCoins: { fontSize: 18, fontWeight: '800', color: GOLD },
  pkgBonus: { fontSize: 12, color: '#10B981', fontWeight: '600' },
  pkgPrice: { fontSize: 17, fontWeight: '700', color: '#fff' },
  featuredBadge: { backgroundColor: GOLD, paddingHorizontal: 8, paddingVertical: 3, borderRadius: 6, marginTop: 4 },
  featuredText: { fontSize: 10, color: '#000', fontWeight: '700' },
  infoBox: { flexDirection: 'row', backgroundColor: CARD, borderRadius: 12, padding: 14, gap: 10, borderWidth: 1, borderColor: BORDER, marginTop: 8 },
  infoText: { flex: 1, fontSize: 12, color: '#888', lineHeight: 18 },
  summaryCards: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 20 },
  summaryCard: { flex: 1, alignItems: 'center', padding: 16, borderRadius: 12, borderWidth: 1, marginHorizontal: 4 },
  summaryLabel: { fontSize: 12, fontWeight: '500', marginTop: 8, marginBottom: 4 },
  summaryAmount: { fontSize: 20, fontWeight: '700', marginBottom: 2 },
  summarySubtext: { fontSize: 11, fontWeight: '500' },
  pointsCard: { margin: 16, padding: 20, borderRadius: 16, borderWidth: 1 },
  pointsHeader: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 12 },
  pointsTitle: { fontSize: 13, fontWeight: '600' },
  pointsAmount: { fontSize: 36, fontWeight: '800', marginBottom: 4 },
  pointsSubtitle: { fontSize: 12, marginBottom: 12 },
  pointsStats: { flexDirection: 'row', gap: 12, paddingTop: 12, borderTopWidth: 1 },
  pointsStatItem: { flex: 1 },
  pointsStatLabel: { fontSize: 11, textTransform: 'uppercase', letterSpacing: 0.5 },
  pointsStatValue: { fontSize: 16, fontWeight: '700', marginTop: 2 },
  viewAllText: { textAlign: 'center', padding: 12, fontWeight: '600' },
  txItem: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: BORDER },
  txIcon: { width: 36, height: 36, borderRadius: 18, justifyContent: 'center', alignItems: 'center' },
  txType: { fontSize: 14, fontWeight: '600', color: '#fff' },
  txDate: { fontSize: 12, color: '#666', marginTop: 2 },
  txAmount: { fontSize: 15, fontWeight: '700' },
  statusBadge: { paddingHorizontal: 8, paddingVertical: 4, borderRadius: 8 },
  statsContainer: { 
    flexDirection: 'row', 
    paddingHorizontal: 12, 
    marginBottom: 20,
    gap: 8,
  },
  statItem: { 
    flex: 1, 
    backgroundColor: CARD, 
    borderRadius: 16, 
    paddingVertical: 20,
    paddingHorizontal: 8,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1.5, 
    borderColor: BORDER,
    minHeight: 110,
  },
  statNumber: { 
    fontSize: 22, 
    fontWeight: '900', 
    color: '#fff', 
    marginTop: 10,
    marginBottom: 6,
  },
  statLabel: { 
    fontSize: 11, 
    color: '#999', 
    fontWeight: '700',
    textAlign: 'center',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: '#111', borderTopLeftRadius: 24, borderTopRightRadius: 24, padding: 24, paddingBottom: 40, borderTopWidth: 1, borderTopColor: BORDER },
  sheetHandle: { width: 40, height: 4, backgroundColor: '#444', borderRadius: 2, alignSelf: 'center', marginBottom: 16 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 18, fontWeight: '700', color: '#fff' },
  fieldLabel: { fontSize: 13, fontWeight: '600', color: '#aaa', marginBottom: 8, marginTop: 12 },
  input: { backgroundColor: CARD, borderRadius: 12, padding: 14, color: '#fff', fontSize: 15, borderWidth: 1, borderColor: BORDER },
  methodRow: { flexDirection: 'row', gap: 8 },
  methodBtn: { flex: 1, paddingVertical: 10, borderRadius: 10, borderWidth: 1, borderColor: BORDER, alignItems: 'center' },
  methodBtnActive: { borderColor: GOLD, backgroundColor: GOLD + '20' },
  methodText: { color: '#666', fontSize: 12, fontWeight: '600', textTransform: 'capitalize' },
  methodTextActive: { color: GOLD },
  submitBtn: { backgroundColor: GOLD, borderRadius: 12, padding: 16, alignItems: 'center', marginTop: 20 },
  submitBtnText: { color: '#000', fontSize: 15, fontWeight: '800' },
  selectedPkg: { flexDirection: 'row', alignItems: 'center', backgroundColor: CARD, borderRadius: 14, padding: 14, marginBottom: 8, borderWidth: 1, borderColor: BORDER },
  monetizeSection: { margin: 16, padding: 20, borderRadius: 16, borderWidth: 1, marginTop: 20 },
  monetizeHeader: { flexDirection: 'row', alignItems: 'center', marginBottom: 16 },
  monetizeInfo: { flex: 1, marginLeft: 12 },
  monetizeTitle: { fontSize: 16, fontWeight: '700', marginBottom: 4 },
  monetizeSubtitle: { fontSize: 13, lineHeight: 18 },
  monetizeBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', padding: 16, borderRadius: 12, gap: 8 },
  monetizeBtnText: { color: '#000', fontSize: 15, fontWeight: '800' },
});

