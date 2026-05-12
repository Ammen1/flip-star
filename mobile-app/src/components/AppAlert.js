import React, { useState, useEffect, useRef } from 'react';
import { Modal, View, Text, TouchableOpacity, StyleSheet, Animated } from 'react-native';

const GOLD = '#C8B56A';
const BG = '#111111';
const CARD = '#1A1A1A';
const BORDER = '#2A2A2A';

let _setAlert = null;

export function AppAlertProvider({ children }) {
  const [config, setConfig] = useState(null);
  const fadeAnim = useRef(new Animated.Value(0)).current;
  const scaleAnim = useRef(new Animated.Value(0.9)).current;

  useEffect(() => {
    _setAlert = (cfg) => {
      setConfig(cfg);
      Animated.parallel([
        Animated.timing(fadeAnim, { toValue: 1, duration: 180, useNativeDriver: true }),
        Animated.spring(scaleAnim, { toValue: 1, tension: 120, friction: 8, useNativeDriver: true }),
      ]).start();
    };
    return () => { _setAlert = null; };
  }, []);

  const close = (onPress) => {
    Animated.timing(fadeAnim, { toValue: 0, duration: 140, useNativeDriver: true }).start(() => {
      scaleAnim.setValue(0.9);
      setConfig(null);
      onPress?.();
    });
  };

  return (
    <>
      {children}
      {config && (
        <Modal transparent visible animationType="none" onRequestClose={() => close()}>
          <Animated.View style={[styles.overlay, { opacity: fadeAnim }]}>
            <Animated.View style={[styles.card, { transform: [{ scale: scaleAnim }] }]}>
              {config.icon ? <Text style={styles.icon}>{config.icon}</Text> : null}
              {config.title ? <Text style={styles.title}>{config.title}</Text> : null}
              {config.message ? <Text style={styles.message}>{config.message}</Text> : null}
              <View style={[styles.btnRow, config.buttons?.length === 1 && { justifyContent: 'center' }]}>
                {(config.buttons || [{ text: 'OK' }]).map((btn, i) => (
                  <TouchableOpacity
                    key={i}
                    style={[styles.btn, btn.style === 'cancel' ? styles.btnCancel : styles.btnPrimary,
                      config.buttons?.length === 1 && { flex: 0, minWidth: 120 }]}
                    onPress={() => close(btn.onPress)}
                    activeOpacity={0.75}
                  >
                    <Text style={[styles.btnText, btn.style === 'cancel' ? styles.btnTextCancel : styles.btnTextPrimary]}>
                      {btn.text}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </Animated.View>
          </Animated.View>
        </Modal>
      )}
    </>
  );
}

export const AppAlert = {
  alert: (title, message, buttons, icon) => {
    if (_setAlert) {
      _setAlert({ title, message, buttons, icon });
    }
  },
};

const styles = StyleSheet.create({
  overlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.75)',
    justifyContent: 'center', alignItems: 'center', padding: 32,
  },
  card: {
    backgroundColor: CARD, borderRadius: 20, padding: 28,
    borderWidth: 1, borderColor: GOLD + '40', width: '100%', maxWidth: 340,
    alignItems: 'center',
  },
  icon: { fontSize: 44, marginBottom: 12 },
  title: { fontSize: 18, fontWeight: '800', color: GOLD, textAlign: 'center', marginBottom: 8 },
  message: { fontSize: 14, color: '#aaa', textAlign: 'center', lineHeight: 20, marginBottom: 24 },
  btnRow: { flexDirection: 'row', gap: 10, width: '100%' },
  btn: { flex: 1, paddingVertical: 13, borderRadius: 12, alignItems: 'center' },
  btnPrimary: { backgroundColor: GOLD },
  btnCancel: { backgroundColor: '#242424', borderWidth: 1, borderColor: BORDER },
  btnText: { fontSize: 15, fontWeight: '700' },
  btnTextPrimary: { color: '#000' },
  btnTextCancel: { color: '#aaa' },
});
