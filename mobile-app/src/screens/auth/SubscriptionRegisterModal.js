import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  Modal, ActivityIndicator, KeyboardAvoidingView,
  Platform, StatusBar, Image,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../contexts/AuthContext';
import api from '../../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

// ── 6-box OTP input component (matching website) ─────────────────────────────
function OtpInput({ value, onChange }) {
  const refs = [useRef(), useRef(), useRef(), useRef(), useRef(), useRef()];
  const digits = (value + '      ').slice(0, 6).split('');

  const handle = (i, text) => {
    const v = text.replace(/\D/g, '').slice(-1);
    const arr = digits.map(d => d.trim());
    arr[i] = v;
    onChange(arr.join('').replace(/ /g, ''));
    if (v && i < 5) refs[i + 1].current?.focus();
  };

  const handleKey = (i, e) => {
    if (e.nativeEvent.key === 'Backspace' && !digits[i].trim() && i > 0) {
      refs[i - 1].current?.focus();
    }
  };

  return (
    <View style={otp.row}>
      {digits.map((d, i) => (
        <TextInput
          key={i}
          ref={refs[i]}
          style={[otp.box, d.trim() && otp.boxFilled]}
          value={d.trim()}
          onChangeText={t => handle(i, t)}
          onKeyPress={e => handleKey(i, e)}
          keyboardType="number-pad"
          maxLength={1}
          textAlign="center"
          secureTextEntry
        />
      ))}
    </View>
  );
}

const otp = StyleSheet.create({
  row: { flexDirection: 'row', justifyContent: 'center', gap: 10, marginVertical: 24 },
  box: { width: 46, height: 54, borderRadius: 10, textAlign: 'center', fontSize: 22, fontWeight: '800', color: '#fff', backgroundColor: CARD, borderWidth: 2, borderColor: BORDER },
  boxFilled: { borderColor: GOLD },
});

// ── Field wrapper component (matching website) ─────────────────────────────────
function Field({ label, icon, focused, children }) {
  return (
    <View style={{ marginBottom: 16 }}>
      <Text style={s.label}>{label}</Text>
      <View style={[s.inputRow, focused && s.inputRowFocused]}>
        <Ionicons name={icon} size={17} color={GOLD} style={s.inputIcon} />
        {children}
      </View>
    </View>
  );
}

// ── Gold button component (matching website) ───────────────────────────────────
function GoldBtn({ loading, onClick, disabled, children }) {
  return (
    <TouchableOpacity
      style={[s.goldBtn, (loading || disabled) && s.goldBtnDisabled]}
      onPress={onClick}
      disabled={loading || disabled}
    >
      {loading ? <ActivityIndicator color="#000" /> : <Text style={s.goldBtnText}>{children}</Text>}
    </TouchableOpacity>
  );
}

// ── Error box component (matching website) ───────────────────────────────────
function ErrorBox({ msg }) {
  if (!msg) return null;
  return (
    <View style={s.errorBox}>
      <Text style={s.errorText}>⚠️ {msg}</Text>
    </View>
  );
}

/**
 * Shown when user arrives via Onevas SMS link:
 * ?subscription_tp=true&phone=251XXXXXXXXX&otp=XXXXXX
 *
 * Fields: Username, Phone (pre-filled), OTP (pre-filled / editable), Password
 * Calls POST /api/auth/login-with-subscription-otp/
 */
export default function SubscriptionRegisterModal({ 
  prefillPhone, 
  prefillOtp, 
  onSuccess, 
  onBackToLogin,
  visible 
}) {
  const insets = useSafeAreaInsets();
  const { login } = useAuth();
  
  const [username, setUsername] = useState('');
  const [phone, setPhone] = useState(prefillPhone || '');
  const [otp, setOtp] = useState(prefillOtp || '');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Focus states
  const [focusUser, setFocusUser] = useState(false);
  const [focusPhone, setFocusPhone] = useState(false);
  const [focusPwd, setFocusPwd] = useState(false);
  const [focusConfirm, setFocusConfirm] = useState(false);

  useEffect(() => {
    if (prefillPhone) setPhone(prefillPhone);
    if (prefillOtp) setOtp(prefillOtp);
  }, [prefillPhone, prefillOtp]);

  const handleRegister = async () => {
    setError('');

    if (!username) { setError('Please enter a username'); return; }
    if (!phone) { setError('Please enter your phone number'); return; }
    if (otp.length !== 6) { setError('Please enter the 6-digit OTP from your SMS'); return; }
    if (!/^\d{6}$/.test(password)) { setError('PIN must be exactly 6 digits'); return; }
    if (password !== confirm) { setError('PINs do not match'); return; }

    setLoading(true);
    try {
      const res = await api.request('/auth/login-with-subscription-otp/', {
        method: 'POST',
        body: JSON.stringify({
          phone,
          username,
          otp,
          password,
        }),
      });
      
      await api.setAuthToken(res.token);
      await login(username, password);
      
      // Pass user data to success callback
      onSuccess({
        id: res.user.id,
        username: res.user.username,
        email: res.user.email || '',
        first_name: res.user.first_name || '',
        last_name: res.user.last_name || '',
        name: res.user.first_name || res.user.username,
        profile_photo: res.user.profile_photo || null,
        bio: res.user.bio || '',
        followers_count: res.user.followers_count || 0,
        following_count: res.user.following_count || 0,
        is_staff: res.user.is_staff || false,
      });
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || 'Registration failed. Check your OTP and try again.');
    } finally {
      setLoading(false);
    }
  };

  if (!visible) return null;

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onBackToLogin}>
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

            {/* Card */}
            <View style={s.card}>
              <View style={s.cardHeader}>
                <Text style={{ fontSize: 32, marginBottom: 8 }}>🎉</Text>
                <Text style={s.cardTitle}>Complete Registration</Text>
                <Text style={s.cardSubtitle}>Your subscription is confirmed! Set up your account below.</Text>
              </View>

              {/* Success badge */}
              <View style={s.successBadge}>
                <Text style={s.successBadgeText}>✅ Subscription active — Enter your OTP from the SMS</Text>
              </View>

              <ErrorBox msg={error} />

              {/* Username */}
              <Field label="Username *" icon="person-outline" focused={focusUser}>
                <TextInput
                  style={s.textInput}
                  placeholder="Choose a unique username"
                  placeholderTextColor="#555"
                  value={username}
                  onChangeText={t => setUsername(t.toLowerCase().replace(/\s/g, ''))}
                  autoCapitalize="none"
                  onFocus={() => setFocusUser(true)}
                  onBlur={() => setFocusUser(false)}
                />
              </Field>

              {/* Phone */}
              <Field label="Phone Number *" icon="call-outline" focused={focusPhone}>
                <TextInput
                  style={s.textInput}
                  placeholder="09XXXXXXXX or +251XXXXXXXXX"
                  placeholderTextColor="#555"
                  value={phone}
                  onChangeText={setPhone}
                  keyboardType="phone-pad"
                  onFocus={() => setFocusPhone(true)}
                  onBlur={() => setFocusPhone(false)}
                />
              </Field>

              {/* OTP */}
              <View style={{ marginBottom: 8 }}>
                <Text style={s.label}>OTP from SMS *</Text>
                <Text style={s.otpHelperText}>Enter the 6-digit code you received via SMS</Text>
                <OtpInput value={otp} onChange={setOtp} />
              </View>

              {/* Password */}
              <Field label="6-Digit PIN *" icon="lock-closed-outline" focused={focusPwd}>
                <TextInput
                  style={[s.textInput, { flex: 1 }]}
                  placeholder="••••••"
                  placeholderTextColor="#555"
                  value={password}
                  onChangeText={t => setPassword(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry={!showPwd}
                  keyboardType="number-pad"
                  maxLength={6}
                  onFocus={() => setFocusPwd(true)}
                  onBlur={() => setFocusPwd(false)}
                />
                <TouchableOpacity onPress={() => setShowPwd(v => !v)} style={{ padding: 4 }}>
                  <Ionicons name={showPwd ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
                </TouchableOpacity>
              </Field>

              {/* Confirm */}
              <Field label="Confirm PIN *" icon="lock-closed-outline" focused={focusConfirm}>
                <TextInput
                  style={[s.textInput, { flex: 1 }]}
                  placeholder="••••••"
                  placeholderTextColor="#555"
                  value={confirm}
                  onChangeText={t => setConfirm(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry={!showConfirm}
                  keyboardType="number-pad"
                  maxLength={6}
                  onFocus={() => setFocusConfirm(true)}
                  onBlur={() => setFocusConfirm(false)}
                />
                <TouchableOpacity onPress={() => setShowConfirm(v => !v)} style={{ padding: 4 }}>
                  <Ionicons name={showPwd ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
                </TouchableOpacity>
              </Field>

              <GoldBtn 
                loading={loading} 
                onClick={handleRegister} 
                disabled={otp.length < 6}
              >
                Create Account & Login 🚀
              </GoldBtn>

              {/* Back to login */}
              <View style={s.backToLoginRow}>
                <Text style={s.backToLoginText}>Already have an account? </Text>
                <TouchableOpacity onPress={onBackToLogin}>
                  <Text style={s.backToLoginLink}>Log in</Text>
                </TouchableOpacity>
              </View>
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
  card: { 
    backgroundColor: CARD, 
    borderRadius: 18, 
    padding: 24, 
    borderWidth: 1, 
    borderColor: GOLD + '30' 
  },
  cardHeader: { 
    alignItems: 'center', 
    marginBottom: 24 
  },
  cardTitle: { 
    fontSize: 22, 
    fontWeight: '900', 
    color: GOLD, 
    marginBottom: 4 
  },
  cardSubtitle: { 
    fontSize: 13, 
    color: '#aaa', 
    textAlign: 'center' 
  },
  successBadge: { 
    padding: 10, 
    backgroundColor: '#1A2A1A', 
    borderWidth: 1, 
    borderColor: '#22C55E', 
    borderRadius: 8, 
    marginBottom: 20, 
    alignItems: 'center' 
  },
  successBadgeText: { 
    color: '#22C55E', 
    fontSize: 13, 
    fontWeight: '600' 
  },
  errorBox: { 
    backgroundColor: '#2D1010', 
    borderWidth: 1, 
    borderColor: '#EF4444', 
    borderRadius: 8, 
    padding: 10, 
    marginBottom: 16 
  },
  errorText: { 
    color: '#EF4444', 
    fontSize: 13, 
    fontWeight: '600' 
  },
  label: { 
    fontSize: 12, 
    fontWeight: '700', 
    color: GOLD, 
    marginBottom: 7, 
    letterSpacing: 0.5 
  },
  otpHelperText: { 
    fontSize: 12, 
    color: '#aaa', 
    marginBottom: 4 
  },
  inputRow: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    backgroundColor: BG, 
    borderRadius: 10, 
    borderWidth: 1.5, 
    borderColor: BORDER, 
    paddingHorizontal: 14, 
    height: 50 
  },
  inputRowFocused: { 
    borderColor: GOLD 
  },
  inputIcon: { 
    marginRight: 10 
  },
  textInput: { 
    flex: 1, 
    fontSize: 15, 
    color: '#fff' 
  },
  goldBtn: { 
    backgroundColor: GOLD, 
    borderRadius: 10, 
    height: 50, 
    justifyContent: 'center', 
    alignItems: 'center', 
    marginBottom: 16 
  },
  goldBtnDisabled: { 
    backgroundColor: '#3A3A3A' 
  },
  goldBtnText: { 
    color: '#000', 
    fontSize: 15, 
    fontWeight: '800' 
  },
  backToLoginRow: { 
    flexDirection: 'row', 
    justifyContent: 'center' 
  },
  backToLoginText: { 
    fontSize: 13, 
    color: '#666' 
  },
  backToLoginLink: { 
    fontSize: 13, 
    color: GOLD, 
    fontWeight: '700' 
  },
});
