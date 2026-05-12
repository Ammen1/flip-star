import React, { useState, useEffect, useRef } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  ScrollView, ActivityIndicator, KeyboardAvoidingView,
  Platform, StatusBar, Image, SafeAreaView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../../contexts/AuthContext';
import api from '../../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

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

// ── 6-box OTP input ────────────────────────────────────────────────────────
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

// ── Step dot component (matching website) ───────────────────────────────────
function StepDot({ active, done }) {
  return (
    <View style={{
      width: done || active ? 22 : 10,
      height: done || active ? 22 : 10,
      borderRadius: 11,
      backgroundColor: done || active ? GOLD : BORDER,
      justifyContent: 'center', alignItems: 'center',
    }}>
      {done && <Text style={{ color: '#000', fontSize: 11, fontWeight: '700' }}>✓</Text>}
    </View>
  );
}

// ── Main Register Screen ───────────────────────────────────────────────────
export default function RegisterScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { register } = useAuth();

  const [step, setStep] = useState(1);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [phone, setPhone] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [otp, setOtp] = useState('');
  const [devCode, setDevCode] = useState('');
  const [verifiedPhone, setVerifiedPhone] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [resendTimer, setResendTimer] = useState(0);

  // Focus states
  const [fUser, setFUser] = useState(false);
  const [fEmail, setFEmail] = useState(false);
  const [fPhone, setFPhone] = useState(false);
  const [fPwd, setFPwd] = useState(false);
  const [fConfirm, setFConfirm] = useState(false);

  useEffect(() => {
    if (resendTimer <= 0) return;
    const t = setTimeout(() => setResendTimer(r => r - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  const handleSendOtp = async () => {
    setError('');
    if (!username) { setError('Please enter a username'); return; }
    if (!email) { setError('Please enter your email'); return; }
    if (!phone) { setError('Please enter your phone number'); return; }
    if (!/^\d{6}$/.test(password)) { setError('Password must be exactly 6 digits'); return; }
    if (password !== confirm) { setError('Passwords do not match'); return; }
    setLoading(true);
    try {
      // Send OTP directly via Onevas (app-first registration)
      const otpRes = await api.sendPhoneOtp(phone);
      setVerifiedPhone(otpRes.phone || phone);
      setResendTimer(60);
      // Dev mode: show OTP on page since SMS not configured yet
      if (otpRes.dev_code) {
        setDevCode(otpRes.dev_code);
      }
      setStep(2);
    } catch (otpErr) {
      // Check for specific error messages
      const errorMessage = otpErr?.response?.data?.error || otpErr?.message || "Failed to send OTP. Check your phone number.";
      if (errorMessage.includes("already registered")) {
        setError("This phone number is already in use. Please use a different number or log in to your existing account.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleVerifyAndRegister = async () => {
    setError('');
    if (otp.length !== 6) { setError('Enter the 6-digit code'); return; }
    setLoading(true);
    try {
      await api.verifyPhoneOtp(verifiedPhone, otp);
      // OTP verified — now create account
      await handleRegisterWithPhone(false); // skip_otp = false (app-first with OTP)
    } catch (e) {
      setError(e?.message || 'Invalid code or registration failed.');
    } finally {
      setLoading(false);
    }
  };

  // ── Register with phone (supports both OTP and OTP-less flows) ──────────────────────────────────
  const handleRegisterWithPhone = async (skipOtp = false) => {
    setError('');
    setLoading(true);
    try {
      const res = await api.request('/auth/register-with-phone/', {
        method: 'POST',
        body: JSON.stringify({
          phone: phone,
          username: username,
          password: password,
          email: email,
          skip_otp: skipOtp
        }),
      });
      await api.setAuthToken(res.token);
      await register({
        token: res.token,
        user: res.user,
      });
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || 'Registration failed.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: BG }}>
      <StatusBar barStyle="light-content" />
      <ScrollView 
        style={{ flex: 1 }} 
        contentContainerStyle={{ flexGrow: 1 }} 
        showsVerticalScrollIndicator={true}
        keyboardShouldPersistTaps="handled"
      >
        <View style={{ paddingTop: insets.top + 16, paddingBottom: 60 }}>
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

          {/* Step indicator */}
          <View style={s.stepRow}>
            <StepDot active={step === 1} done={step > 1} />
            <View style={[s.stepLine, step > 1 && s.stepLineDone]} />
            <StepDot active={step === 2} done={false} />
          </View>

          {/* Card */}
          <View style={s.card}>

          {/* ── STEP 1: Form ── */}
          {step === 1 && (
            <>
              <View style={s.cardHeader}>
                <Text style={{ fontSize: 36, marginBottom: 8 }}>📱</Text>
                <Text style={s.cardTitle}>Create Account</Text>
                <Text style={s.cardSubtitle}>Fill in your details to get started</Text>
              </View>

              <ErrorBox msg={error} />

              <Field label="Username *" icon="person-outline" focused={fUser}>
                <TextInput
                  style={s.textInput}
                  placeholder="Choose a unique username"
                  placeholderTextColor="#555"
                  value={username}
                  onChangeText={t => setUsername(t.replace(/\s/g, ''))}
                  autoCapitalize="none"
                  onFocus={() => setFUser(true)} onBlur={() => setFUser(false)}
                />
              </Field>

              <Field label="Email *" icon="mail-outline" focused={fEmail}>
                <TextInput
                  style={s.textInput}
                  placeholder="your@email.com"
                  placeholderTextColor="#555"
                  value={email}
                  onChangeText={setEmail}
                  keyboardType="email-address"
                  autoCapitalize="none"
                  onFocus={() => setFEmail(true)} onBlur={() => setFEmail(false)}
                />
              </Field>

              <Field label="Phone Number *" icon="call-outline" focused={fPhone}>
                <TextInput
                  style={s.textInput}
                  placeholder="09XXXXXXXX or +251XXXXXXXXX"
                  placeholderTextColor="#555"
                  value={phone}
                  onChangeText={setPhone}
                  keyboardType="phone-pad"
                  onFocus={() => setFPhone(true)} onBlur={() => setFPhone(false)}
                />
              </Field>

              <Field label="6-Digit PIN *" icon="lock-closed-outline" focused={fPwd}>
                <TextInput
                  style={[s.textInput, { flex: 1 }]}
                  placeholder="••••••"
                  placeholderTextColor="#555"
                  value={password}
                  onChangeText={t => setPassword(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry={!showPwd}
                  keyboardType="number-pad"
                  maxLength={6}
                  onFocus={() => setFPwd(true)} onBlur={() => setFPwd(false)}
                />
                <TouchableOpacity onPress={() => setShowPwd(v => !v)} style={{ padding: 4 }}>
                  <Ionicons name={showPwd ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
                </TouchableOpacity>
              </Field>

              <Field label="Confirm PIN *" icon="lock-closed-outline" focused={fConfirm}>
                <TextInput
                  style={[s.textInput, { flex: 1 }]}
                  placeholder="••••••"
                  placeholderTextColor="#555"
                  value={confirm}
                  onChangeText={t => setConfirm(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry={!showConfirm}
                  keyboardType="number-pad"
                  maxLength={6}
                  onFocus={() => setFConfirm(true)} onBlur={() => setFConfirm(false)}
                />
                <TouchableOpacity onPress={() => setShowConfirm(v => !v)} style={{ padding: 4 }}>
                  <Ionicons name={showConfirm ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
                </TouchableOpacity>
              </Field>

              <GoldBtn loading={loading} onClick={handleSendOtp}>Send OTP →</GoldBtn>
            </>
          )}

          {/* ── STEP 2: OTP Verification ── */}
          {step === 2 && (
            <>
              <View style={s.cardHeader}>
                <Text style={{ fontSize: 36, marginBottom: 8 }}>🔐</Text>
                <Text style={s.cardTitle}>Verify Code</Text>
                <Text style={s.cardSubtitle}>
                  Code sent to <Text style={{ color: '#fff', fontWeight: '700' }}>{verifiedPhone}</Text>
                </Text>
              </View>

              <ErrorBox msg={error} />

              {/* DEV MODE: show OTP on page */}
              {devCode && (
                <View style={s.devBox}>
                  <Text style={s.devText}>
                    🧪 DEV MODE — Your OTP code is: <Text style={{ fontSize: 22, letterSpacing: 4 }}>{devCode}</Text>
                  </Text>
                </View>
              )}

              <OtpInput value={otp} onChange={setOtp} />
              
              <GoldBtn loading={loading} onClick={handleVerifyAndRegister} disabled={otp.length < 6}>Verify & Register 🚀</GoldBtn>
              
              <View style={s.resendRow}>
                <TouchableOpacity onPress={() => { setStep(1); setOtp(''); setError(''); setDevCode(''); }} style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                  <Ionicons name="chevron-back" size={14} color={GOLD} />
                  <Text style={{ color: GOLD, fontSize: 13 }}>Go back</Text>
                </TouchableOpacity>
                {resendTimer > 0 ? (
                  <Text style={{ color: '#666', fontSize: 12 }}>Resend in {resendTimer}s</Text>
                ) : (
                  <TouchableOpacity onPress={handleSendOtp}>
                    <Text style={{ color: GOLD, fontSize: 13, fontWeight: '700' }}>Resend OTP</Text>
                  </TouchableOpacity>
                )}
              </View>
            </>
          )}

          {/* Footer */}
          <View style={s.signupRow}>
            <Text style={s.signupText}>Already have an account? </Text>
            <TouchableOpacity onPress={() => navigation.navigate('Login')}>
              <Text style={s.signupLink}>Log in</Text>
            </TouchableOpacity>
          </View>
        </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  scroll: { paddingHorizontal: 16 },
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
  stepRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginBottom: 24 },
  stepLine: { width: 48, height: 2, backgroundColor: BORDER, borderRadius: 1 },
  stepLineDone: { backgroundColor: GOLD },
  card: { backgroundColor: CARD, borderRadius: 18, padding: 24, borderWidth: 1, borderColor: GOLD + '30', marginBottom: 20 },
  cardHeader: { alignItems: 'center', marginBottom: 24 },
  cardTitle: { fontSize: 22, fontWeight: '900', color: GOLD, marginBottom: 4 },
  cardSubtitle: { fontSize: 13, color: GOLD, opacity: 0.8, textAlign: 'center' },
  errorBox: { backgroundColor: '#2D1010', borderWidth: 1, borderColor: '#EF4444', borderRadius: 8, padding: 10, marginBottom: 16 },
  errorText: { color: '#EF4444', fontSize: 13, fontWeight: '600' },
  devBox: { backgroundColor: '#1A2A1A', borderWidth: 1.5, borderColor: '#22C55E', borderRadius: 10, padding: 12, marginBottom: 14, alignItems: 'center' },
  devText: { color: '#22C55E', fontSize: 13, fontWeight: '700' },
  label: { fontSize: 12, fontWeight: '700', color: GOLD, marginBottom: 7, letterSpacing: 0.5 },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: BG, borderRadius: 10, borderWidth: 1.5, borderColor: BORDER, paddingHorizontal: 14, height: 50, marginBottom: 16 },
  inputRowFocused: { borderColor: GOLD },
  inputIcon: { marginRight: 10 },
  textInput: { flex: 1, fontSize: 15, color: '#fff' },
  goldBtn: { backgroundColor: GOLD, borderRadius: 10, height: 50, justifyContent: 'center', alignItems: 'center', marginTop: 8, marginBottom: 16 },
  goldBtnDisabled: { backgroundColor: '#3A3A3A' },
  goldBtnText: { color: '#000', fontSize: 15, fontWeight: '800' },
  resendRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 12, marginBottom: 16 },
  signupRow: { flexDirection: 'row', justifyContent: 'center', marginTop: 16 },
  signupText: { fontSize: 13, color: '#666' },
  signupLink: { fontSize: 13, color: GOLD, fontWeight: '700' },
});
