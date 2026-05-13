import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, ScrollView, TouchableOpacity, Modal, Alert, ActivityIndicator
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';

const COIN_PACKAGES = [
  { id: 1, coins: 100, price: 10, bonus: 0, popular: false, description: 'Starter Package' },
  { id: 2, coins: 250, price: 25, bonus: 25, popular: false, description: 'Good Value' },
  { id: 3, coins: 500, price: 50, bonus: 75, popular: true, description: 'Most Popular' },
  { id: 4, coins: 1000, price: 100, bonus: 200, popular: false, description: 'Best Deal' },
  { id: 5, coins: 2500, price: 250, bonus: 625, popular: false, description: 'Premium Package' },
];

export default function CoinPurchaseScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [userCoins, setUserCoins] = useState(0);
  const [selectedPackage, setSelectedPackage] = useState(null);
  const [loading, setLoading] = useState(false);
  const [showPaymentModal, setShowPaymentModal] = useState(false);

  useEffect(() => {
    loadUserCoins();
  }, []);

  const loadUserCoins = async () => {
    try {
      const response = await api.request('/user/profile/');
      setUserCoins(response.coins || 0);
    } catch (error) {
      console.error('Failed to load user coins:', error);
    }
  };

  const handlePackageSelect = (pkg) => {
    setSelectedPackage(pkg);
    setShowPaymentModal(true);
  };

  const handlePaymentMethod = async (method) => {
    if (!selectedPackage) return;

    setLoading(true);
    try {
      if (method === 'airtime') {
        // Show confirmation before sending SMS
        Alert.alert(
          'Confirm Purchase',
          `Purchase ${selectedPackage.coins + selectedPackage.bonus} coins for ${selectedPackage.price} ETB via airtime?`,
          [
            { text: 'Cancel', style: 'cancel' },
            {
              text: 'Confirm',
              onPress: () => sendAirtimeSMS(selectedPackage)
            }
          ]
        );
      } else if (method === 'telebirr') {
        // Handle Telebirr payment
        const response = await api.request('/payments/telebirr/coins', {
          method: 'POST',
          body: JSON.stringify({
            package_id: selectedPackage.id,
            amount: selectedPackage.price,
            coins: selectedPackage.coins,
            bonus: selectedPackage.bonus
          })
        });
        
        if (response.payment_url) {
          // Open Telebirr app or web
          Alert.alert('Redirecting', 'Opening Telebirr payment...');
        }
      }
    } catch (error) {
      Alert.alert('Error', 'Failed to process payment. Please try again.');
    } finally {
      setLoading(false);
      setShowPaymentModal(false);
    }
  };

  const sendAirtimeSMS = (pkg) => {
    const smsCode = getSMSCode(pkg);
    // Open SMS with the code
    import('react-native').then(({ Linking }) => {
      Linking.openURL(`sms:9286?body=${encodeURIComponent(smsCode)}`).catch(() => {
        Alert.alert('Error', 'Could not open SMS app. Please try again.');
      });
    });
  };

  const getSMSCode = (pkg) => {
    const codes = {
      1: 'COIN100',
      2: 'COIN250', 
      3: 'COIN500',
      4: 'COIN1000',
      5: 'COIN2500'
    };
    return codes[pkg.id] || 'COIN100';
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

      {/* Coin Balance Card */}
      <View style={[styles.balanceCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
        <View style={styles.balanceLeft}>
          <View style={[styles.coinIcon, { backgroundColor: colors.primary + '20' }]}>
            <Ionicons name="wallet" size={28} color={colors.primary} />
          </View>
          <View>
            <Text style={[styles.balanceLabel, { color: colors.textSecondary }]}>Current Balance</Text>
            <Text style={[styles.balanceAmount, { color: colors.text }]}>{userCoins.toLocaleString()} Coins</Text>
          </View>
        </View>
        <TouchableOpacity style={styles.addBtn}>
          <Ionicons name="add" size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      {/* Coin Packages */}
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        <Text style={[styles.sectionTitle, { color: colors.text }]}>Choose Package</Text>
        
        {COIN_PACKAGES.map((pkg) => (
          <TouchableOpacity
            key={pkg.id}
            style={[
              styles.packageCard,
              { backgroundColor: colors.cardBg, borderColor: colors.border },
              selectedPackage?.id === pkg.id && { borderColor: colors.primary, borderWidth: 2 }
            ]}
            onPress={() => handlePackageSelect(pkg)}
          >
            <View style={styles.packageLeft}>
              <View style={styles.coinDisplay}>
                <Ionicons name="coin" size={32} color={colors.primary} />
                <Text style={[styles.coinAmount, { color: colors.text }]}>{pkg.coins.toLocaleString()}</Text>
              </View>
              <View style={styles.packageInfo}>
                <Text style={[styles.packageName, { color: colors.text }]}>{pkg.description}</Text>
                <Text style={[styles.packageDesc, { color: colors.textSecondary }]}>
                  {pkg.price} ETB
                  {pkg.bonus > 0 && ` • +${pkg.bonus} Bonus`}
                </Text>
              </View>
            </View>
            
            <View style={styles.packageRight}>
              {pkg.popular && (
                <View style={[styles.popularBadge, { backgroundColor: colors.primary }]}>
                  <Text style={styles.popularText}>Popular</Text>
                </View>
              )}
              <View style={styles.totalDisplay}>
                <Text style={[styles.totalCoins, { color: colors.text }]}>
                  {(pkg.coins + pkg.bonus).toLocaleString()}
                </Text>
                <Text style={[styles.totalLabel, { color: colors.textSecondary }]}>Total Coins</Text>
              </View>
            </View>
          </TouchableOpacity>
        ))}
      </ScrollView>

      {/* Payment Method Modal */}
      <Modal
        visible={showPaymentModal}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setShowPaymentModal(false)}
      >
        <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.5)' }]}>
          <View style={[styles.paymentModal, { backgroundColor: colors.cardBg }]}>
            <View style={styles.modalHeader}>
              <Text style={[styles.modalTitle, { color: colors.text }]}>Payment Method</Text>
              <TouchableOpacity onPress={() => setShowPaymentModal(false)}>
                <Ionicons name="close" size={24} color={colors.text} />
              </TouchableOpacity>
            </View>

            {selectedPackage && (
              <View style={[styles.selectedPackage, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                <View style={styles.selectedPackageLeft}>
                  <Ionicons name="coin" size={24} color={colors.primary} />
                  <View>
                    <Text style={[styles.selectedAmount, { color: colors.text }]}>
                      {selectedPackage.coins + selectedPackage.bonus} Coins
                    </Text>
                    <Text style={[styles.selectedPrice, { color: colors.textSecondary }]}>
                      {selectedPackage.price} ETB
                    </Text>
                  </View>
                </View>
              </View>
            )}

            <View style={styles.paymentOptions}>
              <TouchableOpacity
                style={[styles.paymentOption, { backgroundColor: colors.bg, borderColor: colors.border }]}
                onPress={() => handlePaymentMethod('airtime')}
                disabled={loading}
              >
                <Ionicons name="phone-portrait" size={24} color={colors.primary} />
                <Text style={[styles.paymentOptionText, { color: colors.text }]}>Pay with Airtime</Text>
                {loading ? (
                  <ActivityIndicator size="small" color={colors.primary} />
                ) : (
                  <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
                )}
              </TouchableOpacity>

              <TouchableOpacity
                style={[styles.paymentOption, { backgroundColor: colors.bg, borderColor: colors.border }]}
                onPress={() => handlePaymentMethod('telebirr')}
                disabled={loading}
              >
                <Ionicons name="card" size={24} color={colors.primary} />
                <Text style={[styles.paymentOptionText, { color: colors.text }]}>Pay with Telebirr</Text>
                {loading ? (
                  <ActivityIndicator size="small" color={colors.primary} />
                ) : (
                  <Ionicons name="chevron-forward" size={20} color={colors.textSecondary} />
                )}
              </TouchableOpacity>
            </View>
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
  balanceCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    margin: 16,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
  },
  balanceLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  coinIcon: {
    width: 48,
    height: 48,
    borderRadius: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  balanceLabel: {
    fontSize: 12,
  },
  balanceAmount: {
    fontSize: 20,
    fontWeight: '700',
  },
  addBtn: {
    padding: 8,
  },
  content: {
    flex: 1,
    paddingHorizontal: 16,
  },
  sectionTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 16,
  },
  packageCard: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    marginBottom: 12,
  },
  packageLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    flex: 1,
  },
  coinDisplay: {
    alignItems: 'center',
  },
  coinAmount: {
    fontSize: 16,
    fontWeight: '700',
    marginTop: 4,
  },
  packageInfo: {
    flex: 1,
  },
  packageName: {
    fontSize: 16,
    fontWeight: '600',
  },
  packageDesc: {
    fontSize: 14,
    marginTop: 2,
  },
  packageRight: {
    alignItems: 'flex-end',
  },
  popularBadge: {
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 8,
    marginBottom: 8,
  },
  popularText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '600',
  },
  totalDisplay: {
    alignItems: 'center',
  },
  totalCoins: {
    fontSize: 18,
    fontWeight: '700',
  },
  totalLabel: {
    fontSize: 12,
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
    padding: 20,
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
});
