import React, { useState, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Modal, ActivityIndicator, TextInput, Alert
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';

export default function CoinPurchaseScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loadingAirtime, setLoadingAirtime] = useState(false);
  const [loadingTelebirr, setLoadingTelebirr] = useState(false);
  const [showResultModal, setShowResultModal] = useState(false);
  const [resultSuccess, setResultSuccess] = useState(false);
  const [resultMessage, setResultMessage] = useState('');

  // Fixed on-demand offer
  const COINS_AMOUNT = 100;
  const ETB_AMOUNT = 10;

  useEffect(() => {
    loadUserPhone();
  }, []);

  const loadUserPhone = async () => {
    try {
      const profile = await api.request('/profile/me/');
      if (profile && profile.phone_number) {
        setPhoneNumber(profile.phone_number);
      }
    } catch (error) {
      console.error('[CoinPurchase] Failed to fetch phone number:', error);
    }
  };

  const handleAirtimePurchase = async () => {
    if (!phoneNumber) {
      setResultSuccess(false);
      setResultMessage('Please enter your phone number');
      setShowResultModal(true);
      return;
    }

    setLoadingAirtime(true);
    try {
      const response = await api.request('/charging/coin-purchase/', {
        method: 'POST',
        body: JSON.stringify({
          phone_number: phoneNumber,
        }),
      });

      if (response.success) {
        setResultSuccess(true);
        setResultMessage(response.message);
        setShowResultModal(true);
        setTimeout(() => {
          setShowResultModal(false);
          navigation.goBack();
        }, 2000);
      } else {
        setResultSuccess(false);
        // Map error messages to user-friendly text
        let errorMessage = response.message || response.error || 'Purchase failed';
        if (errorMessage === 'NO_BALANCE' || response.error === 'charging_failed') {
          errorMessage = 'Your balance is not enough to complete this purchase';
        }
        setResultMessage(errorMessage);
        setShowResultModal(true);
      }
    } catch (error) {
      console.error('airtime coin purchase error:', error);
      console.error('error.message:', error.message);
      console.error('error.response:', error.response);
      setResultSuccess(false);
      let errorMessage = 'Purchase failed. Please try again.';
      
      // Parse the error message to extract NO_BALANCE
      if (error.message && error.message.includes('NO_BALANCE')) {
        errorMessage = 'Your balance is not enough to complete this purchase';
      } else if (error.message && error.message.includes('charging_failed')) {
        errorMessage = 'Your balance is not enough to complete this purchase';
      } else if (error.response && error.response.data && error.response.data.message === 'NO_BALANCE') {
        errorMessage = 'Your balance is not enough to complete this purchase';
      }
      
      setResultMessage(errorMessage);
      setShowResultModal(true);
    } finally {
      setLoadingAirtime(false);
    }
  };

  const handleTelebirrPurchase = async () => {
    if (!phoneNumber) {
      setResultSuccess(false);
      setResultMessage('Please enter your phone number');
      setShowResultModal(true);
      return;
    }

    setLoadingTelebirr(true);
    try {
      const response = await api.request('/wallet/telebirr/initiate/', {
        method: 'POST',
        body: JSON.stringify({
          package_id: 1, // On-demand package ID
          phone_number: phoneNumber,
        }),
      });

      if (response.success && response.payment_url) {
        // Open Telebirr payment URL
        Alert.alert('Redirecting', 'Opening Telebirr payment...', [
          { text: 'OK', onPress: () => navigation.goBack() }
        ]);
      } else {
        setResultSuccess(false);
        setResultMessage(response.error || 'Payment initiation failed');
        setShowResultModal(true);
      }
    } catch (error) {
      console.error('telebirr payment error:', error);
      setResultSuccess(false);
      setResultMessage('Payment initiation failed. Please try again.');
      setShowResultModal(true);
    } finally {
      setLoadingTelebirr(false);
    }
  };

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>Buy Coins</Text>
        <View style={{ width: 24 }} />
      </View>

      {/* Coin Offer Card */}
      <View style={[styles.offerCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
        <View style={styles.offerContent}>
          <View style={[styles.coinIcon, { backgroundColor: colors.primary + '20' }]}>
            <Ionicons name="wallet" size={32} color={colors.primary} />
          </View>
          <View style={styles.offerText}>
            <Text style={[styles.coinAmount, { color: colors.text }]}>{COINS_AMOUNT} Coins</Text>
            <Text style={[styles.offerPrice, { color: colors.textSecondary }]}>for {ETB_AMOUNT} ETB</Text>
          </View>
        </View>
      </View>

      {/* Phone Input (locked to registered number) */}
      <View style={styles.inputContainer}>
        <Text style={[styles.label, { color: colors.textSecondary }]}>Phone Number</Text>
        <TextInput
          style={[styles.input, { backgroundColor: colors.cardBg, borderColor: colors.border, color: colors.text, opacity: 0.85 }]}
          value={phoneNumber}
          editable={false}
          placeholder="+251 9xx xxx xxx"
          placeholderTextColor={colors.textSecondary}
          keyboardType="phone-pad"
        />
        <Text style={{ fontSize: 11, color: colors.textSecondary, marginTop: 6 }}>
          Charges go to your registered phone number.
        </Text>
      </View>

      {/* Payment Buttons */}
      <View style={styles.buttonContainer}>
        <TouchableOpacity
          style={[styles.paymentButton, { backgroundColor: colors.primary }]}
          onPress={handleAirtimePurchase}
          disabled={loadingAirtime || loadingTelebirr}
        >
          {loadingAirtime ? (
            <ActivityIndicator size="small" color="#000" />
          ) : (
            <Text style={styles.buttonText}>From Airtime</Text>
          )}
        </TouchableOpacity>

        <TouchableOpacity
          style={[styles.paymentButton, { backgroundColor: colors.primary }]}
          onPress={handleTelebirrPurchase}
          disabled={loadingAirtime || loadingTelebirr}
        >
          {loadingTelebirr ? (
            <ActivityIndicator size="small" color="#000" />
          ) : (
            <Text style={styles.buttonText}>From Telebirr</Text>
          )}
        </TouchableOpacity>
      </View>

      {/* Result Modal */}
      <Modal
        visible={showResultModal}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowResultModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.resultModal, { backgroundColor: colors.cardBg }]}>
            <View style={[styles.resultIcon, { backgroundColor: resultSuccess ? '#10B981' : '#EF4444' }]}>
              <Ionicons 
                name={resultSuccess ? 'checkmark-circle' : 'close-circle'} 
                size={32} 
                color="#fff" 
              />
            </View>
            <Text style={[styles.resultTitle, { color: colors.text }]}>
              {resultSuccess ? 'Success' : 'Error'}
            </Text>
            <Text style={[styles.resultMessage, { color: colors.textSecondary }]}>
              {resultMessage}
            </Text>
            <TouchableOpacity
              style={[styles.okButton, { backgroundColor: colors.primary }]}
              onPress={() => setShowResultModal(false)}
            >
              <Text style={styles.buttonText}>OK</Text>
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
  offerCard: {
    margin: 16,
    padding: 20,
    borderRadius: 16,
    borderWidth: 1,
    alignItems: 'center',
  },
  offerContent: {
    alignItems: 'center',
    gap: 16,
  },
  coinIcon: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
  },
  offerText: {
    alignItems: 'center',
  },
  coinAmount: {
    fontSize: 32,
    fontWeight: '700',
  },
  offerPrice: {
    fontSize: 16,
    marginTop: 4,
  },
  inputContainer: {
    paddingHorizontal: 16,
    marginBottom: 24,
  },
  label: {
    fontSize: 13,
    fontWeight: '600',
    marginBottom: 8,
  },
  input: {
    paddingHorizontal: 14,
    paddingVertical: 12,
    borderRadius: 10,
    borderWidth: 1,
    fontSize: 15,
  },
  buttonContainer: {
    paddingHorizontal: 16,
    gap: 12,
  },
  paymentButton: {
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
  },
  buttonText: {
    fontSize: 15,
    fontWeight: '700',
    color: '#000',
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.85)',
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 16,
  },
  resultModal: {
    width: '100%',
    maxWidth: 400,
    borderRadius: 16,
    padding: 20,
    alignItems: 'center',
  },
  resultIcon: {
    width: 60,
    height: 60,
    borderRadius: 30,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  resultTitle: {
    fontSize: 18,
    fontWeight: '700',
    marginBottom: 8,
  },
  resultMessage: {
    fontSize: 16,
    textAlign: 'center',
    marginBottom: 20,
  },
  okButton: {
    paddingHorizontal: 32,
    paddingVertical: 12,
    borderRadius: 12,
    alignItems: 'center',
  },
});
