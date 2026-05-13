import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, Alert, ActivityIndicator,
  Image, Dimensions, Linking
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';
import SoundManager from '../utils/SoundUtils';

const { width } = Dimensions.get('window');

// Fallback packages if backend fetch fails
const FALLBACK_PACKAGES = [
  { id: 1, coins: 100, price: 10, bonus: 0, popular: false, description: 'Starter Pack', savings: 0, color: '#3B82F6' },
];

export default function WebsiteCoinScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { user: authUser } = useAuth();
  const [userCoins, setUserCoins] = useState(0);
  const [coinPackages, setCoinPackages] = useState(FALLBACK_PACKAGES);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);
  const [showSuccessModal, setShowSuccessModal] = useState(false);
  const [purchasedCoins, setPurchasedCoins] = useState(0);
  const [paymentMethod, setPaymentMethod] = useState('airtime');

  useEffect(() => {
    loadUserCoins();
    loadPackages();
  }, []);

  const loadPackages = async () => {
    try {
      const response = await api.request('/coins/packages/');
      console.log('Packages API response:', response);
      // Backend returns { packages: [...] }
      const rawPkgs = response?.packages || response || [];
      const pkgs = (Array.isArray(rawPkgs) ? rawPkgs : []).map(p => ({
        id: p.id,
        coins: p.coin_amount,
        price: parseFloat(p.price_etb),
        bonus: p.bonus_coins || 0,
        popular: p.is_featured || false,
        description: p.name,
        savings: 0,
        color: '#3B82F6',
      }));
      console.log('Loaded packages:', pkgs);
      if (pkgs.length > 0) setCoinPackages(pkgs);
    } catch (e) {
      console.log('Using fallback packages:', e);
    }
  };

  const loadUserCoins = async () => {
    try {
      // Use wallet API to get total coin balance (same as WalletScreen)
      const response = await api.request('/wallet/');
      console.log('Wallet API response for coins:', response);
      
      // Get total balance from wallet data
      const totalCoins = response?.balance?.total ?? response?.total ?? 0;
      console.log('Setting user coins to:', totalCoins);
      
      setUserCoins(totalCoins);
    } catch (error) {
      console.error('Failed to load user coins from wallet:', error);
      
      // Fallback to profile API if wallet fails
      try {
        let response;
        try {
          response = await api.request('/profile/');
        } catch {
          try {
            response = await api.request('/user/profile/');
          } catch {
            response = await api.request('/auth/profile/');
          }
        }
        const coins = response?.coins || 0;
        console.log('Fallback: Setting user coins to:', coins);
        setUserCoins(coins);
      } catch (fallbackError) {
        console.error('All coin loading methods failed:', fallbackError);
        setUserCoins(0);
      }
    }
  };

  const handlePackageSelect = (pkg, paymentMethod = 'airtime') => {
    setSelectedPackage(pkg);
    setPaymentMethod(paymentMethod);
    setShowPaymentModal(true);
  };

  const handlePaymentMethod = async () => {
    if (!selectedPackage) {
      Alert.alert('Error', 'No package selected. Please try again.');
      return;
    }

    const confirmTitle = paymentMethod === 'airtime' ? 'Confirm Airtime Payment' : 'Confirm Telebirr Payment';
    const confirmMsg = paymentMethod === 'airtime'
      ? `${selectedPackage.price} ETB will be deducted from your airtime balance and you'll receive ${selectedPackage.coins + selectedPackage.bonus} coins.`
      : `You will be redirected to Telebirr to pay ${selectedPackage.price} ETB for ${selectedPackage.coins + selectedPackage.bonus} coins.`;

    Alert.alert(confirmTitle, confirmMsg, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Confirm',
        onPress: () => processPurchase(selectedPackage),
      }
    ]);
  };

  const processPurchase = async (pkg) => {
    try {
      setLoading(true);

      // Get user's phone number
      let userPhoneNumber = authUser?.phone_number || authUser?.phone || authUser?.username;
      if (userPhoneNumber) {
        if (userPhoneNumber.startsWith('0')) {
          userPhoneNumber = '251' + userPhoneNumber.substring(1);
        } else if (userPhoneNumber.startsWith('+')) {
          userPhoneNumber = userPhoneNumber.substring(1);
        }
      }
      if (!userPhoneNumber) {
        Alert.alert('Error', 'Phone number not found. Please update your profile.');
        return;
      }

      if (paymentMethod === 'airtime') {
        // Use /coins/purchase/ endpoint - same as website "From Airtime" button
        // This directly credits coins (no SMS, no Onevas call needed)
        const response = await api.request('/coins/purchase/', {
          method: 'POST',
          body: JSON.stringify({
            package_id: pkg.id,
            payment_method: 'airtime',
            phone_number: userPhoneNumber,
            amount: pkg.price,
          }),
        });

        console.log('Airtime purchase response:', response);

        if (response.coins_added || response.message?.includes('successfully')) {
          await loadUserCoins();
          setPurchasedCoins(response.coins_added || (pkg.coins + pkg.bonus));
          setShowSuccessModal(true);
          setShowPaymentModal(false);
          SoundManager.playCoinSound();
        } else {
          Alert.alert('Payment Failed', response.error || 'Could not complete purchase. Please try again.');
        }
      } else {
        // Telebirr - use /wallet/telebirr/initiate/ endpoint
        const response = await api.request('/wallet/telebirr/initiate/', {
          method: 'POST',
          body: JSON.stringify({
            package_id: pkg.id,
            phone_number: userPhoneNumber,
          }),
        });

        console.log('Telebirr initiation response:', response);

        if (response.success && response.payment_url) {
          setShowPaymentModal(false);
          await Linking.openURL(response.payment_url);
          
          // Poll for balance update after payment
          let pollCount = 0;
          const pollInterval = setInterval(async () => {
            pollCount++;
            await loadUserCoins();
            if (pollCount >= 12) clearInterval(pollInterval);
          }, 5000);
        } else {
          Alert.alert('Payment Failed', response.error || 'Could not initiate payment. Please try again.');
        }
      }
    } catch (error) {
      console.error('Payment error:', error);
      const errMsg = error?.message || '';
      if (errMsg.includes('Package not found')) {
        Alert.alert('Error', 'Coin package not available. Please try again later.');
      } else {
        Alert.alert('Payment Failed', 'Could not complete purchase. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };



  const formatSavings = (savings) => {
    return savings > 0 ? `Save ${savings}%` : '';
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>Purchase Coins</Text>
        <View style={{ width: 24 }} />
      </View>

      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {/* Hero Section with Gradient */}
        <View style={[styles.heroSection, { background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)' }]}>
          <View style={[styles.coinBalanceCard, { backgroundColor: 'rgba(255,255,255,0.1)', borderColor: 'rgba(255,255,255,0.2)' }]}>
            <View style={styles.balanceLeft}>
              <View style={[styles.coinIconCircle, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
                <Ionicons name="wallet" size={32} color="#fff" />
              </View>
              <View>
                <Text style={[styles.balanceLabel, { color: 'rgba(255,255,255,0.8)' }]}>Current Balance</Text>
                <Text style={[styles.balanceAmount, { color: '#fff' }]}>{userCoins.toLocaleString()}</Text>
                <Text style={[styles.balanceSubtext, { color: 'rgba(255,255,255,0.8)' }]}>Coins</Text>
              </View>
            </View>
            <TouchableOpacity style={[styles.addCoinsBtn, { backgroundColor: 'rgba(255,255,255,0.2)' }]}>
              <Ionicons name="add-circle" size={28} color="#fff" />
            </TouchableOpacity>
          </View>
        </View>

        {/* Website-style Title */}
        <View style={styles.titleSection}>
          <Text style={[styles.mainTitle, { color: colors.text }]}>Get 100 Coins</Text>
          <Text style={[styles.subtitle, { color: colors.textSecondary }]}>
            Unlock premium features and support your favorite creators
          </Text>
        </View>

        {/* Coin Package - Single Large Card */}
        <View style={styles.packagesGrid}>
          {coinPackages.map((pkg) => (
            <TouchableOpacity
              key={pkg.id}
              style={[
                styles.packageCard,
                { 
                  backgroundColor: colors.cardBg, 
                  borderColor: pkg.color,
                  borderWidth: 2,
                  shadowColor: pkg.color,
                  shadowOffset: { width: 0, height: 4 },
                  shadowOpacity: 0.3,
                  shadowRadius: 8,
                  elevation: 8,
                }
              ]}
              onPress={() => handlePackageSelect(pkg)}
            >
              {/* Package Header with Gradient */}
              <View style={[styles.packageHeader, { backgroundColor: pkg.color + '10' }]}>
                <View style={styles.coinDisplay}>
                  <View style={[styles.coinIconCircle, { backgroundColor: pkg.color }]}>
                    <Ionicons name="diamond" size={32} color="#fff" />
                  </View>
                  <View style={styles.coinInfo}>
                    <Text style={[styles.coinAmount, { color: pkg.color }]}>
                      {pkg.coins.toLocaleString()}
                    </Text>
                    <Text style={[styles.coinLabel, { color: colors.textSecondary }]}>Coins</Text>
                  </View>
                </View>
                <View style={styles.priceTag}>
                  <Text style={[styles.priceAmount, { color: '#fff' }]}>
                    {pkg.price} ETB
                  </Text>
                </View>
              </View>

              {/* Package Info */}
              <View style={styles.packageInfo}>
                <Text style={[styles.packageName, { color: colors.text }]}>{pkg.description}</Text>
                <Text style={[styles.packageDesc, { color: colors.textSecondary }]}>
                  Instant delivery to your account
                </Text>
              </View>

              {/* Features */}
              <View style={styles.featuresList}>
                <View style={styles.featureItem}>
                  <Ionicons name="checkmark-circle" size={16} color={pkg.color} />
                  <Text style={[styles.featureText, { color: colors.text }]}>Instant delivery</Text>
                </View>
                <View style={styles.featureItem}>
                  <Ionicons name="checkmark-circle" size={16} color={pkg.color} />
                  <Text style={[styles.featureText, { color: colors.text }]}>No hidden fees</Text>
                </View>
                <View style={styles.featureItem}>
                  <Ionicons name="checkmark-circle" size={16} color={pkg.color} />
                  <Text style={[styles.featureText, { color: colors.text }]}>Support creators</Text>
                </View>
              </View>

              {/* Purchase Options */}
              <View style={styles.purchaseOptions}>
                <TouchableOpacity 
                  style={[styles.purchaseBtn, { backgroundColor: '#F59E0B' }]}
                  onPress={() => handlePackageSelect(pkg, 'airtime')}
                >
                  <Ionicons name="phone-portrait" size={20} color="#fff" />
                  <Text style={styles.purchaseBtnText}>Buy via Airtime</Text>
                </TouchableOpacity>
                
                <TouchableOpacity 
                  style={[styles.purchaseBtn, { backgroundColor: '#F59E0B' }]}
                  onPress={() => handlePackageSelect(pkg, 'telebirr')}
                >
                  <Ionicons name="card" size={20} color="#fff" />
                  <Text style={styles.purchaseBtnText}>Buy via Telebirr</Text>
                </TouchableOpacity>
              </View>
            </TouchableOpacity>
          ))}
        </View>

        {/* Features Section */}
        <View style={styles.featuresSection}>
          <Text style={[styles.featuresTitle, { color: colors.text }]}>What You Can Do With Coins</Text>
          <View style={styles.featuresList}>
            <View style={styles.featureItem}>
              <Ionicons name="diamond" size={20} color={colors.primary} />
              <Text style={[styles.featureText, { color: colors.text }]}>Unlock premium content</Text>
            </View>
            <View style={styles.featureItem}>
              <Ionicons name="gift" size={20} color={colors.primary} />
              <Text style={[styles.featureText, { color: colors.text }]}>Send virtual gifts</Text>
            </View>
            <View style={styles.featureItem}>
              <Ionicons name="trophy" size={20} color={colors.primary} />
              <Text style={[styles.featureText, { color: colors.text }]}>Access exclusive features</Text>
            </View>
            <View style={styles.featureItem}>
              <Ionicons name="heart" size={20} color={colors.primary} />
              <Text style={[styles.featureText, { color: colors.text }]}>Support your favorite creators</Text>
            </View>
          </View>
        </View>
      </ScrollView>

      {/* Payment Confirmation Modal */}
      <Modal
        visible={showPaymentModal}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setShowPaymentModal(false)}
      >
        <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
          <View style={[styles.paymentModal, { backgroundColor: colors.cardBg }]}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>
                {paymentMethod === 'airtime' ? 'Airtime Payment' : 'Telebirr Payment'}
              </Text>
              <TouchableOpacity onPress={() => setShowPaymentModal(false)}>
                <Ionicons name="close" size={24} color={colors.text} />
              </TouchableOpacity>
            </View>

            {selectedPackage ? (
              <View style={[styles.selectedPackage, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                <View style={styles.selectedPackageLeft}>
                  <Ionicons name="diamond" size={24} color={selectedPackage.color || '#3B82F6'} />
                  <View>
                    <Text style={[styles.selectedAmount, { color: colors.text }]}>
                      {(selectedPackage.coins || 0) + (selectedPackage.bonus || 0)} Coins
                    </Text>
                    <Text style={[styles.selectedPrice, { color: colors.textSecondary }]}>
                      {selectedPackage.price || 0} ETB
                    </Text>
                  </View>
                </View>
              </View>
            ) : (
              <View style={[styles.selectedPackage, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                <Text style={[styles.selectedAmount, { color: colors.text }]}>No package selected</Text>
              </View>
            )}

            <View style={styles.paymentMethodInfo}>
              <View style={styles.paymentMethodIcon}>
                <Ionicons 
                  name={paymentMethod === 'airtime' ? 'phone-portrait' : 'card'} 
                  size={32} 
                  color={paymentMethod === 'airtime' ? '#10B981' : '#F59E0B'} 
                />
              </View>
              <Text style={[styles.paymentMethodTitle, { color: colors.text }]}>
                {paymentMethod === 'airtime' ? 'Pay with Airtime' : 'Pay with Telebirr'}
              </Text>
              <Text style={[styles.paymentMethodDesc, { color: colors.textSecondary }]}>
                {paymentMethod === 'airtime' 
                  ? `${selectedPackage?.price || 0} ETB will be deducted from your airtime balance`
                  : `You will be redirected to Telebirr to complete the payment`
                }
              </Text>
            </View>

            <TouchableOpacity
              style={[
                styles.confirmPaymentBtn, 
                { backgroundColor: paymentMethod === 'airtime' ? '#10B981' : '#F59E0B' }
              ]}
              onPress={handlePaymentMethod}
              disabled={loading}
            >
              {loading ? (
                <ActivityIndicator size="small" color="#fff" />
              ) : (
                <Text style={styles.confirmPaymentBtnText}>
                  {paymentMethod === 'airtime' ? 'Confirm Airtime Payment' : 'Proceed to Telebirr'}
                </Text>
              )}
            </TouchableOpacity>
          </View>
        </View>
      </Modal>

      {/* Success Modal */}
      <Modal
        visible={showSuccessModal}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowSuccessModal(false)}
      >
        <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
          <View style={[styles.successModal, { backgroundColor: colors.cardBg }]}>
            <View style={[styles.successIconCircle, { backgroundColor: '#10B98120' }]}>
              <Ionicons name="checkmark-circle" size={48} color="#10B981" />
            </View>
            <Text style={[styles.successTitle, { color: colors.text }]}>Payment Successful!</Text>
            <Text style={[styles.successMessage, { color: colors.textSecondary }]}>
              {purchasedCoins} coins have been added to your account!
            </Text>
            <TouchableOpacity
              style={[styles.successBtn, { backgroundColor: colors.primary }]}
              onPress={() => {
                setShowSuccessModal(false);
                loadUserCoins(); // Refresh balance
              }}
            >
              <Text style={styles.successBtnText}>Got it</Text>
            </TouchableOpacity>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  content: {
    flex: 1,
  },
  heroSection: {
    paddingHorizontal: 16,
    paddingVertical: 30,
    marginHorizontal: 16,
    borderRadius: 20,
    marginBottom: 20,
  },
  coinBalanceCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 24,
    borderRadius: 16,
    borderWidth: 1,
  },
  balanceLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  coinIconCircle: {
    width: 56,
    height: 56,
    borderRadius: 28,
    justifyContent: 'center',
    alignItems: 'center',
  },
  balanceLabel: {
    fontSize: 14,
    fontWeight: '500',
  },
  balanceAmount: {
    fontSize: 32,
    fontWeight: '800',
    lineHeight: 36,
  },
  balanceSubtext: {
    fontSize: 14,
    fontWeight: '500',
  },
  addCoinsBtn: {
    padding: 12,
    borderRadius: 20,
  },
  titleSection: {
    paddingHorizontal: 16,
    paddingVertical: 16,
    alignItems: 'center',
  },
  mainTitle: {
    fontSize: 28,
    fontWeight: '900',
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    textAlign: 'center',
    lineHeight: 22,
  },
  packagesGrid: {
    paddingHorizontal: 16,
    paddingBottom: 20,
  },
  packageCard: {
    borderRadius: 20,
    padding: 24,
    marginBottom: 16,
    position: 'relative',
  },
  packageHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderRadius: 16,
    marginBottom: 20,
  },
  coinDisplay: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  coinInfo: {
    alignItems: 'flex-start',
  },
  coinAmount: {
    fontSize: 28,
    fontWeight: '800',
  },
  coinLabel: {
    fontSize: 14,
    fontWeight: '500',
  },
  priceTag: {
    backgroundColor: 'rgba(0,0,0,0.2)',
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 20,
  },
  priceAmount: {
    fontSize: 16,
    fontWeight: '700',
  },
  packageInfo: {
    marginBottom: 20,
  },
  packageName: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 4,
  },
  packageDesc: {
    fontSize: 14,
    lineHeight: 20,
  },
  featuresList: {
    gap: 8,
    marginBottom: 20,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  featureText: {
    fontSize: 14,
    fontWeight: '500',
  },
  purchaseOptions: {
    gap: 12,
  },
  purchaseBtn: {
    flexDirection: 'row',
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
    padding: 16,
    borderRadius: 12,
  },
  purchaseBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  paymentMethodInfo: {
    alignItems: 'center',
    padding: 20,
    marginBottom: 20,
  },
  paymentMethodIcon: {
    width: 64,
    height: 64,
    borderRadius: 32,
    backgroundColor: 'rgba(0,0,0,0.05)',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 12,
  },
  paymentMethodTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 4,
  },
  paymentMethodDesc: {
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
  },
  confirmPaymentBtn: {
    padding: 16,
    borderRadius: 12,
    alignItems: 'center',
  },
  confirmPaymentBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  popularBadge: {
    position: 'absolute',
    top: -1,
    right: -1,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderTopRightRadius: 16,
    borderBottomLeftRadius: 8,
  },
  popularText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  packageHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 16,
  },
  coinDisplay: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderRadius: 12,
  },
  coinAmount: {
    fontSize: 20,
    fontWeight: '700',
  },
  bonusBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
  },
  bonusText: {
    color: '#fff',
    fontSize: 12,
    fontWeight: '700',
  },
  packageInfo: {
    marginBottom: 16,
  },
  packageName: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 4,
  },
  totalCoins: {
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 4,
  },
  savingsText: {
    fontSize: 14,
    fontWeight: '600',
  },
  priceSection: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  priceAmount: {
    fontSize: 20,
    fontWeight: '800',
  },
  selectBtn: {
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  selectBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
  featuresSection: {
    paddingHorizontal: 16,
    paddingVertical: 24,
  },
  featuresTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 16,
  },
  featuresList: {
    gap: 12,
  },
  featureItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  featureText: {
    fontSize: 16,
    fontWeight: '500',
  },
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  paymentModal: {
    width: '90%',
    maxWidth: 400,
    borderRadius: 20,
    padding: 24,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
  },
  selectedPackage: {
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 20,
  },
  selectedPackageLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  selectedAmount: {
    fontSize: 16,
    fontWeight: '700',
  },
  selectedPrice: {
    fontSize: 14,
  },
  paymentOptions: {
    gap: 12,
  },
  paymentOption: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
  },
  paymentOptionText: {
    fontSize: 16,
    fontWeight: '600',
    flex: 1,
    marginLeft: 12,
  },
  successModal: {
    width: '90%',
    maxWidth: 320,
    borderRadius: 20,
    padding: 24,
    alignItems: 'center',
  },
  successIconCircle: {
    width: 80,
    height: 80,
    borderRadius: 40,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  successTitle: {
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 8,
  },
  successMessage: {
    fontSize: 14,
    textAlign: 'center',
    lineHeight: 20,
    marginBottom: 20,
  },
  successBtn: {
    paddingHorizontal: 24,
    paddingVertical: 12,
    borderRadius: 20,
  },
  successBtnText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
});
