import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet, Modal,
  Platform, StatusBar,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';

const GOLD = '#C8B56A';

export default function TelebirrReceiptModal({
  visible,
  onClose,
  onProceed,
  tier,
  phoneNumber,
}) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();

  if (!visible || !tier) return null;

  const currentDate = new Date().toLocaleDateString('en-US', {
    weekday: 'long',
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  });

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <StatusBar barStyle="light-content" />
      <View style={s.overlay}>
        <View style={[s.modalContent, { backgroundColor: colors.cardBg }]}>
          
          {/* Header */}
          <View style={s.header}>
            <TouchableOpacity style={s.closeButton} onPress={onClose}>
              <Ionicons name="close" size={24} color={colors.textSecondary} />
            </TouchableOpacity>
            <Text style={[s.headerTitle, { color: colors.text }]}>Payment Confirmation</Text>
            <View style={{ width: 24 }} />
          </View>

          {/* Receipt Card */}
          <View style={[s.receiptCard, { backgroundColor: colors.bg, borderColor: colors.border }]}>
            
            {/* Telebirr Logo/Icon */}
            <View style={s.logoContainer}>
              <View style={[s.iconCircle, { backgroundColor: GOLD + '20' }]}>
                <Ionicons name="card" size={32} color={GOLD} />
              </View>
              <Text style={[s.providerName, { color: colors.text }]}>Telebirr</Text>
            </View>

            {/* Divider */}
            <View style={[s.divider, { backgroundColor: colors.border }]} />

            {/* Payment Details */}
            <View style={s.detailsSection}>
              <Text style={[s.sectionLabel, { color: colors.textSecondary }]}>PAYMENT DETAILS</Text>
              
              {/* Plan Name */}
              <View style={s.detailRow}>
                <Text style={[s.detailLabel, { color: colors.textSecondary }]}>Plan</Text>
                <Text style={[s.detailValue, { color: colors.text }]}>{tier.name}</Text>
              </View>

              {/* Daily Amount */}
              <View style={s.detailRow}>
                <Text style={[s.detailLabel, { color: colors.textSecondary }]}>Daily Amount</Text>
                <View style={s.amountRow}>
                  <Text style={[s.detailValue, { color: GOLD, fontWeight: '900' }]}>{tier.price_etb} ETB</Text>
                </View>
              </View>

              {/* Duration */}
              <View style={s.detailRow}>
                <Text style={[s.detailLabel, { color: colors.textSecondary }]}>Duration</Text>
                <Text style={[s.detailValue, { color: colors.text }]}>{tier.duration_type}</Text>
              </View>

              {/* Date */}
              <View style={s.detailRow}>
                <Text style={[s.detailLabel, { color: colors.textSecondary }]}>Date</Text>
                <Text style={[s.detailValue, { color: colors.text }]}>{currentDate}</Text>
              </View>

              {/* Phone Number */}
              <View style={s.detailRow}>
                <Text style={[s.detailLabel, { color: colors.textSecondary }]}>Phone Number</Text>
                <Text style={[s.detailValue, { color: colors.text }]}>{phoneNumber || 'N/A'}</Text>
              </View>
            </View>

            {/* Divider */}
            <View style={[s.divider, { backgroundColor: colors.border }]} />

            {/* Total */}
            <View style={s.totalSection}>
              <Text style={[s.totalLabel, { color: colors.textSecondary }]}>Total Amount</Text>
              <Text style={[s.totalAmount, { color: GOLD }]}>{tier.price_etb} ETB</Text>
            </View>

          </View>

          {/* Proceed Button */}
          <TouchableOpacity
            style={[s.proceedButton, { backgroundColor: GOLD }]}
            onPress={onProceed}
          >
            <Ionicons name="arrow-forward" size={20} color="#000" />
            <Text style={s.proceedButtonText}>Proceed</Text>
          </TouchableOpacity>

          {/* Cancel Button */}
          <TouchableOpacity
            style={s.cancelButton}
            onPress={onClose}
          >
            <Text style={[s.cancelButtonText, { color: colors.textSecondary }]}>Cancel</Text>
          </TouchableOpacity>

        </View>
      </View>
    </Modal>
  );
}

const s = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.8)',
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  modalContent: {
    width: '100%',
    maxWidth: 400,
    borderRadius: 20,
    padding: 24,
    paddingBottom: 32,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: 24,
  },
  closeButton: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  headerTitle: {
    fontSize: 18,
    fontWeight: '800',
    textAlign: 'center',
    flex: 1,
  },
  receiptCard: {
    borderRadius: 16,
    borderWidth: 1,
    padding: 20,
    marginBottom: 24,
  },
  logoContainer: {
    alignItems: 'center',
    marginBottom: 16,
  },
  iconCircle: {
    width: 64,
    height: 64,
    borderRadius: 32,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 8,
  },
  providerName: {
    fontSize: 16,
    fontWeight: '700',
  },
  divider: {
    height: 1,
    marginVertical: 16,
  },
  detailsSection: {
    marginBottom: 8,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 1,
    marginBottom: 16,
  },
  detailRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 14,
  },
  detailLabel: {
    fontSize: 13,
    fontWeight: '500',
  },
  detailValue: {
    fontSize: 14,
    fontWeight: '600',
  },
  amountRow: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  totalSection: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: 8,
  },
  totalLabel: {
    fontSize: 14,
    fontWeight: '700',
  },
  totalAmount: {
    fontSize: 24,
    fontWeight: '900',
  },
  proceedButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 16,
    borderRadius: 12,
    marginBottom: 12,
  },
  proceedButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '800',
    marginLeft: 8,
  },
  cancelButton: {
    paddingVertical: 14,
    alignItems: 'center',
  },
  cancelButtonText: {
    fontSize: 14,
    fontWeight: '600',
  },
});
