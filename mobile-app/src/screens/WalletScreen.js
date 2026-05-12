import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, ScrollView,
  ActivityIndicator, Alert, Modal, TextInput, RefreshControl,
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
      setSummary({ ...s, profile });
      setConfig(c);
      setPackages(Array.isArray(pkgs) ? pkgs : (pkgs.results || []));
    } catch (e) { Alert.alert('Error', 'Failed to load wallet'); }
    finally { setLoading(false); setRefreshing(false); }
  };

  const handleTabChange = (tab) => {
    setActiveTab(tab);
    if (tab === 'transactions' && transactions.length === 0) loadTransactions();
    if (tab === 'withdrawals' && withdrawals.length === 0) loadWithdrawals();
  };

  const loadTransactions = async () => {
    try {
      const data = await api.request('/wallet/transactions/?page_size=50');
      setTransactions(data.results || []);
    } catch {}
  };

  const loadWithdrawals = async () => {
    try {
      const data = await api.request('/wallet/withdrawals/');
      setWithdrawals(data.results || []);
    } catch {}
  };

  const handleWithdraw = async () => {
    if (!withdrawAmount || !withdrawAccount) {
      Alert.alert('Error', 'Please fill all fields'); return;
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

  const total = summary?.balance?.total ?? summary?.total ?? 0;
  const earned = summary?.balance?.earned ?? summary?.earned_total ?? 0;
  const purchased = summary?.balance?.purchased ?? summary?.purchased_total ?? 0;
  
  // Gamification stats from profile
  const profile = summary?.profile || {};
  const coins = profile.coins || 0;
  const points = profile.points || 0;
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
        {/* Balance Card */}
        <View style={[styles.balanceCard, { backgroundColor: '#C8A84B' }]}>
          <View style={styles.balanceHeader}>
            <Ionicons name="wallet" size={22} color="#000" />
            <Text style={styles.balanceLabel}>My Wallet</Text>
          </View>
          <Text style={styles.balanceAmount}>{coins}</Text>
          <Text style={styles.balanceSubtext}>Coins</Text>
        </View>

        {/* Gamification Stats */}
        <View style={styles.statsContainer}>
          <View style={[styles.statItem, { backgroundColor: '#2D1F1F' }]}>
            <Ionicons name="flame" size={28} color="#FF6B6B" />
            <Text style={styles.statNumber}>{loginStreak}</Text>
            <Text style={styles.statLabel}>Streak</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: '#2D2A1F' }]}>
            <Ionicons name="star" size={28} color="#FFD93D" />
            <Text style={styles.statNumber}>{points}</Text>
            <Text style={styles.statLabel}>Points</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: '#252029' }]}>
            <Ionicons name="flash" size={28} color="#A78BFA" />
            <Text style={styles.statNumber}>{xp}</Text>
            <Text style={styles.statLabel}>XP</Text>
          </View>
          <View style={[styles.statItem, { backgroundColor: '#1F2A2D' }]}>
            <Ionicons name="trophy" size={28} color="#4ECDC4" />
            <Text style={styles.statNumber}>{level}</Text>
            <Text style={styles.statLabel}>Level</Text>
          </View>
        </View>

        {/* Action buttons */}
        <View style={styles.actionRow}>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => setShowTopUpModal(true)}>
            <View style={[styles.actionGrad, { backgroundColor: colors.primary }]}>
              <Ionicons name="add-circle" size={24} color="#fff" />
              <Text style={styles.actionText}>Buy Coins</Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => setShowWithdrawModal(true)}>
            <View style={[styles.actionGrad, { backgroundColor: colors.primary }]}>
              <Ionicons name="arrow-up-circle" size={24} color="#fff" />
              <Text style={styles.actionText}>Withdraw</Text>
            </View>
          </TouchableOpacity>
          <TouchableOpacity style={[styles.actionBtn, { backgroundColor: colors.cardBg }]} onPress={() => handleTabChange('transactions')}>
            <View style={[styles.actionGrad, { backgroundColor: colors.primary }]}>
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
              <Text style={styles.sectionTitle}>All Transactions</Text>
              {transactions.length === 0
                ? <Text style={styles.emptyText}>No transactions yet</Text>
                : transactions.map(tx => (
                  <View key={tx.id} style={styles.txItem}>
                    <View style={[styles.txIcon, { backgroundColor: tx.is_credit ? '#0D2D1A' : '#2D1010' }]}>
                      <Ionicons name={tx.is_credit ? 'arrow-down' : 'arrow-up'} size={16} color={tx.is_credit ? '#10B981' : '#EF4444'} />
                    </View>
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={styles.txType}>{tx.type_display || tx.type}</Text>
                      <Text style={styles.txDate}>{timeAgo(tx.created_at)}</Text>
                    </View>
                    <Text style={[styles.txAmount, { color: tx.is_credit ? '#10B981' : '#EF4444' }]}>
                      {tx.is_credit ? '+' : '-'}{tx.coins}
                    </Text>
                  </View>
                ))}
            </>
          )}

          {/* Withdrawals */}
          {activeTab === 'withdrawals' && (
            <>
              <Text style={styles.sectionTitle}>Withdrawals</Text>
              {withdrawals.length === 0
                ? <Text style={styles.emptyText}>No withdrawals yet</Text>
                : withdrawals.map(w => (
                  <View key={w.id} style={styles.txItem}>
                    <View style={[styles.txIcon, { backgroundColor: '#1A1A2D' }]}>
                      <Ionicons name="card-outline" size={16} color="#667eea" />
                    </View>
                    <View style={{ flex: 1, marginLeft: 12 }}>
                      <Text style={styles.txType}>{w.coin_amount} coins ? {w.net_birr} ETB</Text>
                      <Text style={styles.txDate}>{w.status}</Text>
                    </View>
                    <View style={[styles.statusBadge, { backgroundColor: w.status === 'completed' ? '#0D2D1A' : '#2D2010' }]}>
                      <Text style={{ color: w.status === 'completed' ? '#10B981' : GOLD, fontSize: 11, fontWeight: '700' }}>{w.status}</Text>
                    </View>
                  </View>
                ))}
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
              {['telebirr', 'cbe_birr', 'bank'].map(m => (
                <TouchableOpacity key={m} style={[styles.methodBtn, withdrawMethod === m && styles.methodBtnActive]} onPress={() => setWithdrawMethod(m)}>
                  <Text style={[styles.methodText, withdrawMethod === m && styles.methodTextActive]}>{m.replace('_', ' ')}</Text>
                </TouchableOpacity>
              ))}
            </View>
            <Text style={styles.fieldLabel}>Account Number</Text>
            <TextInput style={styles.input} placeholder="Phone or account number" placeholderTextColor="#666" value={withdrawAccount} onChangeText={setWithdrawAccount} keyboardType="phone-pad" />
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
});

