import React from 'react';
import {
  View, Text, TouchableOpacity, StyleSheet,
  Modal, KeyboardAvoidingView,
  Platform, StatusBar, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

/**
 * Modal that appears when user clicks "Sign up free" on login screen
 * Shows options for regular registration vs subscription registration
 * Matches website's behavior exactly
 */
export default function RegisterChoiceModal({ 
  visible, 
  onRegularRegister, 
  onSubscriptionRegister,
  onClose 
}) {
  const insets = useSafeAreaInsets();

  if (!visible) return null;

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <StatusBar barStyle="light-content" />
        
        <View style={s.modalOverlay}>
          <View style={s.modalContent}>
            
            {/* Logos */}
            <View style={s.logosRow}>
              <View style={StyleSheet.absoluteFill} pointerEvents="none">
                <View style={{ flex: 1, flexDirection: 'row' }}>
                  {Array.from({ length: 40 }, (_, i) => {
                    const v = Math.round(255 * (1 - i / 39));
                    return <View key={i} style={{ flex: 1, backgroundColor: `rgb(${v},${v},${v})` }} />;
                  })}
                </View>
              </View>
              <Image 
                source={require('../../../assets/images/ethio-logo.png')} 
                style={s.ethioLogo}
                resizeMode="contain"
              />
              <Image 
                source={require('../../../assets/images/flipstar-logo.png')} 
                style={s.flipstarLogo}
                resizeMode="contain"
              />
            </View>

            {/* Main Content - Website Style */}
            <View style={s.mainContent}>
              <View style={s.header}>
                <Text style={s.title}>Create Account</Text>
                <Text style={s.subtitle}>Choose how you'd like to register</Text>
              </View>

              {/* Options Container */}
              <View style={s.optionsContainer}>
                {/* Regular Registration */}
                <TouchableOpacity 
                  style={s.registerOption} 
                  onPress={onRegularRegister}
                >
                  <View style={s.optionHeader}>
                    <View style={s.regularIcon}>
                      <Ionicons name="person-outline" size={20} color="#F9E08B" />
                    </View>
                    <View style={s.optionInfo}>
                      <Text style={s.optionTitle}>Register with Phone</Text>
                      <Text style={s.optionDesc}>Free registration with phone verification</Text>
                    </View>
                  </View>
                  <View style={s.optionArrow}>
                    <Ionicons name="chevron-forward" size={20} color="#666" />
                  </View>
                </TouchableOpacity>

                {/* Subscription Registration */}
                <TouchableOpacity 
                  style={[s.registerOption, s.subscriptionOption]} 
                  onPress={onSubscriptionRegister}
                >
                  <View style={s.subscriptionBadge}>
                    <Text style={s.subscriptionBadgeText}>POPULAR</Text>
                  </View>
                  <View style={s.optionHeader}>
                    <View style={[s.regularIcon, s.subscriptionIcon]}>
                      <Ionicons name="card-outline" size={20} color="#F9E08B" />
                    </View>
                    <View style={s.optionInfo}>
                      <Text style={s.optionTitle}>Register with Subscription</Text>
                      <Text style={s.optionDesc}>Use your Onevas subscription OTP for instant access</Text>
                    </View>
                  </View>
                  <View style={s.optionArrow}>
                    <Ionicons name="chevron-forward" size={20} color="#F9E08B" />
                  </View>
                </TouchableOpacity>
              </View>

              {/* Back Button */}
              <TouchableOpacity style={s.backButton} onPress={onClose}>
                <Ionicons name="chevron-back" size={16} color="#F9E08B" />
                <Text style={s.backButtonText}>Back to Login</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const s = StyleSheet.create({
  modalOverlay: { 
    flex: 1, 
    backgroundColor: 'rgba(0,0,0,0.85)', 
    justifyContent: 'flex-end' 
  },
  modalContent: { 
    backgroundColor: '#0D0D0D', 
    borderTopLeftRadius: 18, 
    borderTopRightRadius: 18, 
    padding: 24, 
    paddingBottom: 40, 
    maxHeight: '95%' 
  },
  logosRow: { 
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    alignItems: 'center', 
    marginBottom: 24, 
    borderRadius: 12, 
    paddingHorizontal: 12,
    paddingVertical: 10,
    overflow: 'hidden',
  },
  ethioLogo: { width: 100, height: 50 },
  flipstarLogo: { width: 100, height: 50 },
  mainContent: {
    flex: 1,
  },
  header: {
    alignItems: 'center',
    marginBottom: 32,
  },
  title: {
    fontSize: 24,
    fontWeight: '900',
    color: '#F9E08B',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 14,
    color: '#aaa',
    textAlign: 'center',
  },
  optionsContainer: {
    marginBottom: 24,
  },
  registerOption: {
    backgroundColor: '#1A1A1A',
    borderRadius: 12,
    borderWidth: 1,
    borderColor: '#262626',
    marginBottom: 12,
    padding: 16,
    position: 'relative',
  },
  subscriptionOption: {
    borderColor: '#F9E08B',
    borderWidth: 1.5,
  },
  subscriptionBadge: {
    position: 'absolute',
    top: -8,
    right: 16,
    backgroundColor: '#F9E08B',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 12,
  },
  subscriptionBadgeText: {
    color: '#000',
    fontSize: 10,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  optionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
  },
  regularIcon: {
    width: 40,
    height: 40,
    borderRadius: 10,
    backgroundColor: '#0D0D0D',
    borderWidth: 1,
    borderColor: '#262626',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  subscriptionIcon: {
    backgroundColor: '#F9E08B20',
    borderColor: '#F9E08B',
  },
  optionInfo: {
    flex: 1,
  },
  optionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 4,
  },
  optionDesc: {
    fontSize: 13,
    color: '#aaa',
    lineHeight: 18,
  },
  optionArrow: {
    marginLeft: 12,
  },
  backButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: 16,
    paddingVertical: 12,
  },
  backButtonText: {
    color: '#F9E08B',
    fontSize: 14,
    fontWeight: '600',
    marginLeft: 4,
  },
});
