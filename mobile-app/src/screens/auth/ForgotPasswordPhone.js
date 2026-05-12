import React, { useState } from 'react';
import {
  View, Text, TextInput, TouchableOpacity, StyleSheet,
  Modal, ActivityIndicator, KeyboardAvoidingView, Platform, ScrollView,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../../api';

const GOLD = '#C8B56A';
const CARD = '#1A1A1A';
const BORDER = '#262626';

export default function ForgotPasswordPhone({ onClose, onSuccess }) {
  const [step, setStep] = useState(1);
  const [phone, setPhone] = useState('');
  const [code, setCode] = useState('');
  const [pwd, setPwd] = useState('');
  const [confirm, setConfirm] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [msg, setMsg] = useState('');
  const [devCode, setDevCode] = useState('');

  const sendCode = async () => {
    setError(''); setMsg(''); setDevCode('');
    if (!phone) { setError('Enter your phone number'); return; }
    const cleanPhone = phone.replace(/[^\d]/g, '');
    if (!/^\d{9,15}$/.test(cleanPhone)) { setError('Enter a valid phone number'); return; }
    setLoading(true);
    try {
      const data = await api.forgotPasswordPhoneRequest(phone);
      setMsg('Reset code sent via SMS!');
      if (data.dev_code) {
        setDevCode(data.dev_code);
        setMsg(`Reset code sent! Dev code: ${data.dev_code}`);
      }
      setStep(2);
    } catch (e) {
      const err = e?.message || 'Failed to send code';
      setError(err);
    } finally { setLoading(false); }
  };

  const confirmReset = async () => {
    setError(''); setMsg('');
    if (code.length !== 6) { setError('Enter the 6-digit code'); return; }
    if (!/^\d{6}$/.test(pwd)) { setError('New PIN must be exactly 6 digits'); return; }
    if (pwd !== confirm) { setError('PINs do not match'); return; }
    setLoading(true);
    try {
      await api.forgotPasswordPhoneVerify(phone, code, pwd);
      setStep(3);
    } catch (e) {
      const err = e?.message || 'Invalid or expired code';
      setError(err);
    } finally { setLoading(false); }
  };

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <KeyboardAvoidingView 
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
        style={{ flex: 1 }}
      >
        <View style={s.modalOverlay}>
          <ScrollView 
            contentContainerStyle={{ flexGrow: 1, justifyContent: 'flex-end' }}
            keyboardShouldPersistTaps="handled"
          >
            <View style={s.modalSheet}>
              <View style={s.modalHeader}>
                <Text style={s.modalTitle}>
                  {step === 1 ? 'Forgot PIN' : step === 2 ? 'Enter Reset Code' : 'PIN Reset!'}
                </Text>
                <TouchableOpacity onPress={onClose}><Ionicons name="close" size={22} color={GOLD} /></TouchableOpacity>
              </View>

              {!!error && <View style={s.errorBox}><Text style={s.errorText}>⚠️ {error}</Text></View>}
              {!!msg && <View style={s.successBox}><Text style={s.successText}>{msg}</Text></View>}

          {step === 1 && (
            <>
              <Text style={s.modalDesc}>Enter your registered phone number. A 6-digit reset code will be sent via SMS.</Text>
              <View style={[s.inputRow, { marginBottom: 16 }]}>
                <Ionicons name="call-outline" size={17} color={GOLD} style={s.inputIcon} />
                <TextInput
                  style={s.textInput}
                  placeholder="09XXXXXXXX or +251XXXXXXXXX"
                  placeholderTextColor="#555"
                  value={phone}
                  onChangeText={setPhone}
                  keyboardType="phone-pad"
                  autoCapitalize="none"
                />
              </View>
              <TouchableOpacity style={[s.goldBtn, loading && s.goldBtnDisabled]} onPress={sendCode} disabled={loading}>
                {loading ? <ActivityIndicator color="#000" /> : <Text style={s.goldBtnText}>Send Reset Code</Text>}
              </TouchableOpacity>
            </>
          )}

          {step === 2 && (
            <>
              <Text style={s.modalDesc}>Enter the code sent to <Text style={{ color: '#fff', fontWeight: '700' }}>{phone}</Text> and your new 6-digit PIN.</Text>
              <View style={[s.inputRow, { marginBottom: 16 }]}>
                <Ionicons name="chatbubble-outline" size={17} color={GOLD} style={s.inputIcon} />
                <TextInput
                  style={s.textInput}
                  placeholder="6-digit code"
                  placeholderTextColor="#555"
                  value={code}
                  onChangeText={t => setCode(t.replace(/\D/g, '').slice(0, 6))}
                  keyboardType="number-pad"
                  maxLength={6}
                />
              </View>
              <View style={[s.inputRow, { marginBottom: 16 }]}>
                <Ionicons name="lock-closed-outline" size={17} color={GOLD} style={s.inputIcon} />
                <TextInput
                  style={[s.textInput, { flex: 1 }]}
                  placeholder="New 6-digit PIN"
                  placeholderTextColor="#555"
                  value={pwd}
                  onChangeText={t => setPwd(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry={!showPwd}
                  keyboardType="number-pad"
                  maxLength={6}
                />
                <TouchableOpacity onPress={() => setShowPwd(v => !v)} style={{ padding: 4 }}>
                  <Ionicons name={showPwd ? 'eye-off-outline' : 'eye-outline'} size={17} color={GOLD} />
                </TouchableOpacity>
              </View>
              <View style={[s.inputRow, { marginBottom: 16 }]}>
                <Ionicons name="lock-closed-outline" size={17} color={GOLD} style={s.inputIcon} />
                <TextInput
                  style={s.textInput}
                  placeholder="Confirm new PIN"
                  placeholderTextColor="#555"
                  value={confirm}
                  onChangeText={t => setConfirm(t.replace(/\D/g, '').slice(0, 6))}
                  secureTextEntry
                  keyboardType="number-pad"
                  maxLength={6}
                />
              </View>
              <TouchableOpacity style={[s.goldBtn, loading && s.goldBtnDisabled]} onPress={confirmReset} disabled={loading}>
                {loading ? <ActivityIndicator color="#000" /> : <Text style={s.goldBtnText}>Reset PIN</Text>}
              </TouchableOpacity>
              <TouchableOpacity onPress={() => { setStep(1); setCode(''); setError(''); setMsg(''); setDevCode(''); }} style={{ flexDirection: 'row', alignItems: 'center', justifyContent: 'center', marginTop: 12 }}>
                <Ionicons name="chevron-back" size={14} color={GOLD} />
                <Text style={{ color: GOLD, fontSize: 13 }}>Back</Text>
              </TouchableOpacity>
            </>
          )}

          {step === 3 && (
            <View style={{ alignItems: 'center', padding: 20 }}>
              <Text style={{ fontSize: 48, marginBottom: 12 }}>✅</Text>
              <Text style={{ fontSize: 18, fontWeight: '800', color: GOLD, marginBottom: 8 }}>PIN Reset!</Text>
              <Text style={{ fontSize: 13, color: GOLD, marginBottom: 24, textAlign: 'center' }}>You can now log in with your new PIN.</Text>
              <TouchableOpacity style={s.goldBtn} onPress={() => { onClose(); onSuccess && onSuccess(); }}>
                <Text style={s.goldBtnText}>Go to Login</Text>
              </TouchableOpacity>
            </View>
          )}
            </View>
          </ScrollView>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

const s = StyleSheet.create({
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.85)', justifyContent: 'flex-end' },
  modalSheet: { backgroundColor: '#111', borderTopLeftRadius: 18, borderTopRightRadius: 18, padding: 24, paddingBottom: 40, maxHeight: '88%' },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 },
  modalTitle: { fontSize: 20, fontWeight: '900', color: GOLD },
  modalDesc: { fontSize: 13, color: GOLD, marginBottom: 16, lineHeight: 20 },
  errorBox: { backgroundColor: '#2D1010', borderWidth: 1, borderColor: '#EF4444', borderRadius: 8, padding: 10, marginBottom: 16 },
  errorText: { color: '#EF4444', fontSize: 13, fontWeight: '600' },
  successBox: { backgroundColor: '#1A2A1A', borderWidth: 1, borderColor: '#22C55E', borderRadius: 8, padding: 10, marginBottom: 16 },
  successText: { color: '#22C55E', fontSize: 13, fontWeight: '600' },
  inputRow: { flexDirection: 'row', alignItems: 'center', backgroundColor: CARD, borderRadius: 10, borderWidth: 1.5, borderColor: BORDER, paddingHorizontal: 14, height: 50 },
  inputIcon: { marginRight: 10 },
  textInput: { flex: 1, fontSize: 15, color: '#fff' },
  goldBtn: { backgroundColor: GOLD, borderRadius: 10, height: 50, justifyContent: 'center', alignItems: 'center', marginBottom: 16 },
  goldBtnDisabled: { backgroundColor: '#3A3A3A' },
  goldBtnText: { color: '#000', fontSize: 15, fontWeight: '800' },
});
