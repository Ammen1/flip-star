import React, { useState, useEffect } from 'react';
import { View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';
import { useConsent } from '../contexts/ConsentContext';

const GDPRConsentBanner = ({ visible, onAccept, onCustomize }) => {
  const { consents, updateConsent } = useConsent();
  const [slideAnim] = useState(new Animated.Value(100));

  useEffect(() => {
    if (visible) {
      Animated.timing(slideAnim, {
        toValue: 0,
        duration: 300,
        useNativeDriver: true,
      }).start();
    } else {
      Animated.timing(slideAnim, {
        toValue: 100,
        duration: 300,
        useNativeDriver: true,
      }).start();
    }
  }, [visible, slideAnim]);

  const handleAcceptAll = () => {
    // Enable all optional consents
    updateConsent('analytics', true);
    updateConsent('marketing', true);
    updateConsent('camera', true);
    updateConsent('storage', true);
    onAccept();
  };

  const handleCustomize = () => {
    onCustomize();
  };

  if (!visible) return null;

  return (
    <Animated.View 
      style={[
        styles.banner, 
        { transform: [{ translateY: slideAnim }] }
      ]}
    >
      <View style={styles.bannerContent}>
        <View style={styles.textContainer}>
          <Text style={styles.bannerTitle}>Privacy & Cookies</Text>
          <Text style={styles.bannerText}>
            We use cookies and similar technologies to help personalize content, tailor and measure ads, and provide a better experience.
          </Text>
        </View>
        
        <View style={styles.buttonContainer}>
          <TouchableOpacity 
            style={styles.customizeButton} 
            onPress={handleCustomize}
          >
            <Text style={styles.customizeButtonText}>Customize</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={styles.acceptButton} 
            onPress={handleAcceptAll}
          >
            <Text style={styles.acceptButtonText}>Accept All</Text>
          </TouchableOpacity>
        </View>
      </View>
    </Animated.View>
  );
};

const styles = StyleSheet.create({
  banner: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    backgroundColor: '#1A1A1A',
    borderTopWidth: 1,
    borderTopColor: '#333',
    zIndex: 1000,
  },
  bannerContent: {
    padding: 20,
    paddingBottom: 30, // Extra padding for safe area
  },
  textContainer: {
    marginBottom: 16,
  },
  bannerTitle: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 8,
  },
  bannerText: {
    color: '#ccc',
    fontSize: 14,
    lineHeight: 20,
  },
  buttonContainer: {
    flexDirection: 'row',
    gap: 12,
  },
  customizeButton: {
    flex: 1,
    backgroundColor: '#333',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  customizeButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  acceptButton: {
    flex: 1,
    backgroundColor: '#3B82F6',
    paddingVertical: 12,
    paddingHorizontal: 20,
    borderRadius: 8,
    alignItems: 'center',
  },
  acceptButtonText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
});

export default GDPRConsentBanner;
