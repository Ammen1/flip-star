import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, Switch, Alert, Modal, TextInput, Image, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';
import AsyncStorage from '@react-native-async-storage/async-storage';
import api from '../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const TEXT = '#fff';
const SUB = '#666';

function SettingRow({ icon, label, subtitle, value, onPress, isSwitch, switchValue, onSwitch, danger, chevron = true, colors }) {
  return (
    <TouchableOpacity style={[styles.row, { borderBottomColor: colors.border + '80' }]} onPress={onPress} disabled={isSwitch} activeOpacity={0.7}>
      <View style={[styles.rowIcon, { backgroundColor: danger ? (colors.error + '20') : (colors.primary + '20') }]}>
        <Ionicons name={icon} size={18} color={danger ? colors.error : colors.primary} />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text style={[styles.rowLabel, { color: danger ? colors.error : colors.text }]}>{label}</Text>
        {subtitle && <Text style={[styles.rowSubtitle, { color: colors.textSecondary }]}>{subtitle}</Text>}
      </View>
      <View style={{ marginLeft: 'auto', flexDirection: 'row', alignItems: 'center', gap: 8 }}>
        {value && <Text style={[styles.rowValue, { color: colors.textSecondary }]}>{value}</Text>}
        {isSwitch && <Switch value={switchValue} onValueChange={onSwitch} trackColor={{ true: colors.primary, false: colors.border }} thumbColor="#fff" />}
        {!isSwitch && chevron && <Ionicons name="chevron-forward" size={18} color={colors.textSecondary} />}
      </View>
    </TouchableOpacity>
  );
}

function Section({ title, children, colors }) {
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: colors.textSecondary }]}>{title}</Text>
      <View style={[styles.sectionCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>{children}</View>
    </View>
  );
}

function SectionLabel({ children, colors }) {
  return (
    <Text style={[styles.sectionLabel, { color: colors.textSecondary }]}>{children}</Text>
  );
}

function SectionCard({ children, colors }) {
  return (
    <View style={[styles.sectionCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>{children}</View>
  );
}

function BeautifulModal({ visible, onClose, title, children, height = '70%', colors }) {
  if (!visible) return null;
  
  return (
    <Modal visible={visible} transparent animationType="fade">
      <TouchableOpacity style={styles.modalOverlay} activeOpacity={1} onPress={onClose}>
        <TouchableOpacity 
          style={[styles.beautifulModal, { height, backgroundColor: colors.cardBg, borderColor: colors.border }]} 
          activeOpacity={1}
          onPress={e => e.stopPropagation()}
        >
          {/* Modal Header */}
          <View style={[styles.beautifulModalHeader, { borderBottomColor: colors.border }]}>
            <Text style={[styles.beautifulModalTitle, { color: colors.text }]}>{title}</Text>
            <TouchableOpacity 
              style={[styles.beautifulModalCloseButton, { backgroundColor: colors.border + '40' }]}
              onPress={onClose}
            >
              <Ionicons name="close" size={24} color={colors.text} />
            </TouchableOpacity>
          </View>
          
          {/* Modal Content */}
          <View style={styles.beautifulModalContent}>
            {children}
          </View>
        </TouchableOpacity>
      </TouchableOpacity>
    </Modal>
  );
}

export default function SettingsScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { user, logout } = useAuth();
  const { colors, darkMode, toggleDarkMode } = useTheme();
  const { language, setLanguage, t } = useLanguage();
  
  const [notifications, setNotifications] = useState(() => {
    return {
      likes: true,
      comments: true,
      follows: true,
      messages: true,
    };
  });
  
  const [privacy, setPrivacy] = useState(() => {
    return {
      privateAccount: false,
      showActivity: true,
      allowMessages: true,
    };
  });
  const [blockedUsers, setBlockedUsers] = useState([]);
  const [loadingBlocked, setLoadingBlocked] = useState(false);
  
  const [showPassModal, setShowPassModal] = useState(false);
  const [showLangModal, setShowLangModal] = useState(false);
  const [modal, setModal] = useState({ isOpen: false, title: '', message: '', type: 'info', onConfirm: null });
  
  const [password, setPassword] = useState({ current: '', new: '', confirm: '' });

  // Load settings from AsyncStorage and backend on mount
  useEffect(() => {
    const loadSettings = async () => {
      try {
        // Load notification settings from backend
        try {
          const notifData = await api.getNotificationSettings();
          if (notifData) {
            setNotifications({
              likes: notifData.likes ?? true,
              comments: notifData.comments ?? true,
              follows: notifData.follows ?? true,
              messages: notifData.messages ?? true,
            });
          }
        } catch (e) {
          // Fallback to AsyncStorage if backend fails
          const notifData = await AsyncStorage.getItem('notifications');
          if (notifData) setNotifications(JSON.parse(notifData));
        }
        
        // Load privacy settings from backend
        try {
          const privacyData = await api.getPrivacySettings();
          if (privacyData) {
            setPrivacy({
              privateAccount: privacyData.private_account ?? false,
              showActivity: privacyData.show_activity_status ?? true,
              allowMessages: privacyData.allow_messages_from_anyone ?? true,
            });
          }
        } catch (e) {
          // Fallback to AsyncStorage if backend fails
          const privacyData = await AsyncStorage.getItem('privacy');
          if (privacyData) setPrivacy(JSON.parse(privacyData));
        }
      } catch {}
    };
    loadSettings();

    // Load blocked users
    const loadBlockedUsers = async () => {
      try {
        setLoadingBlocked(true);
        const data = await api.getBlockedUsers();
        const users = Array.isArray(data) ? data : (data.results || []);
        setBlockedUsers(users.map(b => b.blocked));
      } catch {
        // backend may not support this endpoint
      } finally {
        setLoadingBlocked(false);
      }
    };
    loadBlockedUsers();
  }, []);

  // Save settings to AsyncStorage whenever they change
  useEffect(() => {
    AsyncStorage.setItem('notifications', JSON.stringify(notifications)).catch(() => {});
  }, [notifications]);

  useEffect(() => {
    AsyncStorage.setItem('privacy', JSON.stringify(privacy)).catch(() => {});
  }, [privacy]);

  const handleNotificationToggle = async (key) => {
    const newVal = !notifications[key];
    const next = { ...notifications, [key]: newVal };
    setNotifications(next);
    
    // Sync with backend
    try {
      await api.updateNotificationSettings({ [key]: newVal });
      console.log(`Updated ${key} notification setting to:`, newVal);
    } catch (error) {
      console.error('Failed to update notification settings:', error);
      // Revert on error
      setNotifications({ ...notifications, [key]: !newVal });
      Alert.alert('Error', 'Failed to update notification settings');
    }
  };

  const handlePrivacyToggle = async (key) => {
    const newVal = !privacy[key];
    const next = { ...privacy, [key]: newVal };
    setPrivacy(next);
    
    // Map frontend keys to backend keys
    const backendKeyMap = {
      privateAccount: 'private_account',
      showActivity: 'show_activity_status', 
      allowMessages: 'allow_messages_from_anyone',
    };
    
    // Sync with backend
    try {
      await api.updatePrivacySettings({ [backendKeyMap[key]]: newVal });
    } catch (error) {
      // Revert on error
      setPrivacy({ ...privacy, [key]: !newVal });
      Alert.alert('Error', 'Failed to update privacy settings');
    }
  };

  const handleDarkModeToggle = () => {
    toggleDarkMode();
  };

  const handleLanguageChange = (langId) => {
    setLanguage(langId);
    setShowLangModal(false);
    Alert.alert('Language Changed', `Language has been changed to ${languages.find(l => l.id === langId)?.label}`);
  };

  const handleResetSuggestions = async () => {
    Alert.alert(
      'Reset Suggested Content',
      'This will clear your recommendation history and start fresh. Continue?',
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Reset', 
          style: 'destructive',
          onPress: async () => {
            try {
              // Clear dismissed users from AsyncStorage
              await AsyncStorage.removeItem('dismissedSuggestions');
              // Clear any other suggestion-related data
              await AsyncStorage.removeItem('suggestionHistory');
              Alert.alert('Success', 'Your suggested content has been reset');
            } catch (error) {
              Alert.alert('Error', 'Failed to reset suggestions');
            }
          }
        }
      ]
    );
  };

  const handlePasswordChange = async () => {
    if (password.new !== password.confirm) {
      Alert.alert('Error', 'Passwords do not match');
      return;
    }
    if (password.new.length < 8) {
      Alert.alert('Error', 'Password must be at least 8 characters');
      return;
    }
    if (!password.current) {
      Alert.alert('Error', 'Please enter your current password');
      return;
    }
    
    try {
      console.log('Attempting to change password...');
      const response = await api.changePassword({
        old_password: password.current,
        new_password: password.new
      });
      
      console.log('Password change response:', response);
      Alert.alert('Success', 'Password changed successfully');
      setPassword({ current: '', new: '', confirm: '' });
      setShowPassModal(false);
    } catch (error) {
      console.error('Password change error:', error);
      const errorMessage = error?.response?.data?.message || error?.message || 'Failed to change password';
      Alert.alert('Error', errorMessage);
    }
  };

  const handleDeleteAccount = () => {
    Alert.alert('Delete Account', 'This action is permanent and cannot be undone. All your data will be deleted.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Delete', style: 'destructive', onPress: () => {
        Alert.alert('Final Confirmation', 'Are you absolutely sure you want to delete your account? This cannot be undone.', [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Delete', style: 'destructive', onPress: async () => {
            try {
              await api.request('/auth/delete-account/', { method: 'POST' });
              Alert.alert('Account Deleted', 'Your account is being deleted', [
                { text: 'OK', onPress: logout }
              ]);
            } catch (error) {
              Alert.alert('Error', 'Failed to delete account');
            }
          }},
        ]);
      }},
    ]);
  };

  const handleDownloadData = async () => {
    try {
      await api.request('/auth/download-data/', { method: 'POST' });
      Alert.alert('Download Initiated', 'Your data will be sent to your email shortly');
    } catch (error) {
      Alert.alert('Error', 'Failed to request data download');
    }
  };

  const handleUnblockUser = async (userId, username) => {
    try {
      await api.unblockUser(userId);
      setBlockedUsers(prev => prev.filter(u => u.id !== userId));
      Alert.alert('Success', `Unblocked ${username}`);
    } catch (error) {
      Alert.alert('Error', 'Failed to unblock user');
    }
  };

  const languages = [
    { id: 'en', label: 'English' },
    { id: 'am', label: 'አማርኛ (Amharic)' },
    { id: 'es', label: 'Español' },
    { id: 'fr', label: 'Français' },
    { id: 'ar', label: 'العربية' },
  ];

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={26} color={colors.text} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]}>{t('settings')}</Text>
        <View style={{ width: 34 }} />
      </View>

      <ScrollView showsVerticalScrollIndicator={false}>
        {/* Profile Summary */}
        <View style={[styles.profileSummary, { backgroundColor: colors.cardBg }]}>
          <View style={[styles.avatar, { backgroundColor: colors.primary }]}>
            {user?.profile_photo ? (
              <Image source={{ uri: user.profile_photo }} style={styles.avatarImage} />
            ) : (
              <Text style={[styles.avatarText, { color: darkMode ? '#000' : '#fff' }]}>{user?.username?.[0]?.toUpperCase() || 'U'}</Text>
            )}
          </View>
          <Text style={[styles.username, { color: colors.text }]}>@{user?.username}</Text>
          <Text style={[styles.email, { color: colors.textSecondary }]}>{user?.email}</Text>
        </View>

        {/* Account */}
        <SectionLabel colors={colors}>{t('account')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon="person-outline" label={t('editProfile')} subtitle="Change bio and photo" onPress={() => navigation.navigate('EditProfile')} colors={colors} />
          <SettingRow icon="wallet-outline" label={t('wallet')} subtitle="Coins & transactions" onPress={() => navigation.navigate('Wallet')} colors={colors} />
          <SettingRow icon="ribbon" label={t('subscription')} subtitle="Plans & billing" onPress={() => navigation.navigate('Subscription')} colors={colors} />
          <SettingRow icon="lock-closed-outline" label={t('changePassword')} onPress={() => setShowPassModal(true)} colors={colors} />
          <SettingRow icon="download-outline" label={t('downloadData')} subtitle="Get a copy of your data" onPress={handleDownloadData} colors={colors} />
        </SectionCard>

        {/* Notifications */}
        <SectionLabel colors={colors}>{t('notifications')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon="heart-outline" label={t('likes')} isSwitch switchValue={notifications.likes} onSwitch={() => handleNotificationToggle('likes')} colors={colors} />
          <SettingRow icon="chatbubble-outline" label={t('comments')} isSwitch switchValue={notifications.comments} onSwitch={() => handleNotificationToggle('comments')} colors={colors} />
          <SettingRow icon="people-outline" label={t('follows')} isSwitch switchValue={notifications.follows} onSwitch={() => handleNotificationToggle('follows')} colors={colors} />
          <SettingRow icon="mail-outline" label={t('messages')} isSwitch switchValue={notifications.messages} onSwitch={() => handleNotificationToggle('messages')} colors={colors} />
        </SectionCard>

        {/* Privacy */}
        <SectionLabel colors={colors}>{t('privacy')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon="eye-off-outline" label={t('privateAccount')} subtitle="Only followers can see your posts" isSwitch switchValue={privacy.privateAccount} onSwitch={() => handlePrivacyToggle('privateAccount')} colors={colors} />
          <SettingRow icon="pulse-outline" label={t('showActivity')} subtitle="Show your activity status" isSwitch switchValue={privacy.showActivity} onSwitch={() => handlePrivacyToggle('showActivity')} colors={colors} />
          <SettingRow icon="mail-outline" label={t('allowMessages')} subtitle="Receive messages from anyone" isSwitch switchValue={privacy.allowMessages} onSwitch={() => handlePrivacyToggle('allowMessages')} colors={colors} />
          <SettingRow icon="refresh-outline" label={t('resetSuggestions')} subtitle="Clear your recommendation history" onPress={handleResetSuggestions} colors={colors} />
        </SectionCard>

        {/* Appearance */}
        <SectionLabel colors={colors}>{t('appearance')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon={darkMode ? "moon-outline" : "sunny-outline"} label={t('darkMode')} isSwitch switchValue={darkMode} onSwitch={handleDarkModeToggle} colors={colors} />
          <SettingRow icon="globe-outline" label={t('language')} subtitle={language === 'en' ? t('english') : language === 'am' ? t('amharic') : language === 'es' ? t('spanish') : language === 'fr' ? t('french') : language === 'ar' ? t('arabic') : language} onPress={() => setShowLangModal(true)} colors={colors} />
          <SettingRow icon="ios-notifications-outline" label="Notification Sound" subtitle="Choose a notification sound" onPress={() => console.log('Notification Sound')} colors={colors} />
        </SectionCard>

        {/* Help */}
        <SectionLabel colors={colors}>{t('help')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon="help-circle-outline" label={t('helpCenter')} onPress={() => Alert.alert('Help Center', 'For support, email us at:\nsupport@flipstar.com\n\nOr visit our FAQ section in the app.')} colors={colors} />
          <SettingRow icon="shield-checkmark-outline" label={t('privacyPolicy')} onPress={() => Alert.alert('Privacy Policy', 'Our privacy policy explains how we collect, use, and protect your data. You can view the full policy on our website at flipstar.com/privacy')} colors={colors} />
          <SettingRow icon="document-text-outline" label={t('termsOfService')} onPress={() => Alert.alert('Terms of Service', 'Our terms of service outline the rules and guidelines for using FlipStar. View the full terms at flipstar.com/terms')} colors={colors} />
        </SectionCard>

        {/* Blocked Users */}
        <SectionLabel colors={colors}>{t('blockedUsers')}</SectionLabel>
        <SectionCard colors={colors}>
          {loadingBlocked ? (
            <View style={{ padding: 20, alignItems: 'center' }}>
              <ActivityIndicator color={colors.primary} />
            </View>
          ) : blockedUsers.length === 0 ? (
            <Text style={{ color: colors.textSecondary, fontSize: 14, padding: 20 }}>No blocked users</Text>
          ) : (
            blockedUsers.map(blockedUser => (
              <View key={blockedUser.id} style={{ flexDirection: 'row', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: colors.border + '80' }}>
                <View style={{ width: 32, height: 32, borderRadius: 16, backgroundColor: colors.border, justifyContent: 'center', alignItems: 'center', overflow: 'hidden' }}>
                  {blockedUser.profile_photo ? (
                    <Image source={{ uri: blockedUser.profile_photo }} style={{ width: '100%', height: '100%' }} />
                  ) : (
                    <Ionicons name="person" size={16} color={colors.textSecondary} />
                  )}
                </View>
                <Text style={{ flex: 1, marginLeft: 12, color: colors.text, fontSize: 15 }}>{blockedUser.username}</Text>
                <TouchableOpacity onPress={() => handleUnblockUser(blockedUser.id, blockedUser.username)}>
                  <Text style={{ color: colors.primary, fontSize: 14, fontWeight: '600' }}>Unblock</Text>
                </TouchableOpacity>
              </View>
            ))
          )}
        </SectionCard>

        {/* Danger Zone */}
        <SectionLabel colors={colors}>{t('dangerZone')}</SectionLabel>
        <SectionCard colors={colors}>
          <SettingRow icon="trash-outline" label={t('deleteAccount')} danger onPress={handleDeleteAccount} colors={colors} />
        </SectionCard>

        {/* Logout */}
        <TouchableOpacity style={[styles.logoutButton, { backgroundColor: colors.cardBg, borderColor: colors.border }]} onPress={logout}>
          <Ionicons name="log-out-outline" size={20} color={colors.error} />
          <Text style={[styles.logoutText, { color: colors.error }]}>{t('logout')}</Text>
        </TouchableOpacity>

        <View style={styles.footer}>
          <Text style={[styles.version, { color: colors.textSecondary }]}>Version 1.0.0</Text>
          <Text style={[styles.copyright, { color: colors.textSecondary }]}>© 2024 FlipStar Inc.</Text>
        </View>
      </ScrollView>

      {/* Language Modal */}
      <BeautifulModal
        visible={showLangModal}
        onClose={() => setShowLangModal(false)}
        title={t('chooseLanguage')}
        height="50%"
        colors={colors}
      >
        <View style={{ gap: 8 }}>
          {languages.map(l => (
            <TouchableOpacity
              key={l.id}
              onPress={() => handleLanguageChange(l.id)}
              style={[styles.languageOption, { backgroundColor: colors.bg, borderColor: colors.border }]}
            >
              <View style={styles.languageOptionContent}>
                <Text style={[styles.languageLabel, { color: language === l.id ? colors.primary : colors.text }]}>{l.label}</Text>
                {language === l.id && (
                  <View style={[styles.languageSelectedIndicator, { backgroundColor: colors.primary }]}>
                    <Ionicons name="checkmark" size={16} color={darkMode ? '#000' : '#fff'} />
                  </View>
                )}
              </View>
            </TouchableOpacity>
          ))}
        </View>
      </BeautifulModal>

      {/* Password Modal */}
      <BeautifulModal
        visible={showPassModal}
        onClose={() => setShowPassModal(false)}
        title={t('changePassword')}
        height="60%"
        colors={colors}
      >
        <View style={{ gap: 20 }}>
          <View style={styles.passwordField}>
            <Text style={[styles.passwordLabel, { color: colors.text }]}>{t('currentPassword')}</Text>
            <TextInput
              style={[styles.passwordInput, { borderColor: colors.border, backgroundColor: colors.bg, color: colors.text }]}
              secureTextEntry
              placeholder="Enter current password"
              placeholderTextColor={colors.textSecondary}
              value={password.current}
              onChangeText={text => setPassword(prev => ({ ...prev, current: text }))}
            />
          </View>
          <View style={styles.passwordField}>
            <Text style={[styles.passwordLabel, { color: colors.text }]}>{t('newPassword')}</Text>
            <TextInput
              style={[styles.passwordInput, { borderColor: colors.border, backgroundColor: colors.bg, color: colors.text }]}
              secureTextEntry
              placeholder="Enter new password"
              placeholderTextColor={colors.textSecondary}
              value={password.new}
              onChangeText={text => setPassword(prev => ({ ...prev, new: text }))}
            />
          </View>
          <View style={styles.passwordField}>
            <Text style={[styles.passwordLabel, { color: colors.text }]}>{t('confirmNewPassword')}</Text>
            <TextInput
              style={[styles.passwordInput, { borderColor: colors.border, backgroundColor: colors.bg, color: colors.text }]}
              secureTextEntry
              placeholder="Confirm new password"
              placeholderTextColor={colors.textSecondary}
              value={password.confirm}
              onChangeText={text => setPassword(prev => ({ ...prev, confirm: text }))}
            />
          </View>
          <TouchableOpacity style={[styles.beautifulUpdateButton, { backgroundColor: colors.primary }]} onPress={handlePasswordChange}>
            <Text style={[styles.updateButtonText, { color: darkMode ? '#000' : '#fff' }]}>{t('updatePassword')}</Text>
          </TouchableOpacity>
        </View>
      </BeautifulModal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 17, fontWeight: '700', color: TEXT },
  
  profileSummary: { flexDirection: 'column', alignItems: 'center', padding: 28, backgroundColor: CARD, marginBottom: 8 },
  avatar: { width: 80, height: 80, borderRadius: 40, backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center', marginBottom: 12, overflow: 'hidden' },
  avatarImage: { width: '100%', height: '100%' },
  avatarText: { fontSize: 32, fontWeight: '800', color: '#000' },
  username: { fontSize: 18, fontWeight: '800', color: TEXT },
  email: { fontSize: 13, color: SUB, marginTop: 2 },
  
  sectionLabel: { fontSize: 12, fontWeight: '700', color: SUB, textTransform: 'uppercase', letterSpacing: 1.2, marginHorizontal: 20, marginTop: 20, marginBottom: 8 },
  sectionCard: { marginHorizontal: 16, borderRadius: 16, borderWidth: 1, borderColor: BORDER, backgroundColor: CARD, overflow: 'hidden' },
  section: { marginTop: 24, paddingHorizontal: 16 },
  sectionTitle: { fontSize: 12, fontWeight: '700', color: SUB, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 8 },
  
  row: { flexDirection: 'row', alignItems: 'center', padding: 14, borderBottomWidth: 1, borderBottomColor: BORDER + '80' },
  rowIcon: { width: 36, height: 36, borderRadius: 10, justifyContent: 'center', alignItems: 'center', marginRight: 12 },
  rowLabel: { fontSize: 15, color: TEXT, fontWeight: '500' },
  rowSubtitle: { fontSize: 12, color: SUB, marginTop: 2 },
  rowValue: { fontSize: 13, color: SUB },
  
  logoutButton: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, marginHorizontal: 16, marginTop: 24, padding: 16, backgroundColor: CARD, borderWidth: 1, borderColor: BORDER, borderRadius: 16 },
  logoutText: { color: '#EF4444', fontSize: 15, fontWeight: '800' },
  
  footer: { alignItems: 'center', padding: 32 },
  version: { fontSize: 12, fontWeight: '600', color: SUB },
  copyright: { fontSize: 10, color: SUB, opacity: 0.6, marginTop: 4 },
  
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.6)', justifyContent: 'flex-end' },
  bottomSheet: { width: '100%', backgroundColor: CARD, borderTopLeftRadius: 24, borderTopRightRadius: 24, paddingBottom: 24 },
  bottomSheetHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottomWidth: 1, borderBottomColor: BORDER },
  bottomSheetTitle: { fontSize: 18, fontWeight: '800', color: TEXT },
  bottomSheetContent: { padding: '8px 20px' },
  languageRow: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', padding: 16, borderBottomWidth: 1, borderBottomColor: BORDER },
  languageLabel: { fontSize: 16, fontWeight: '600' },
  
  passwordField: { marginBottom: 14 },
  passwordLabel: { fontSize: 13, fontWeight: '700', color: TEXT, marginBottom: 6 },
  passwordInput: { width: '100%', padding: 14, borderRadius: 12, borderWidth: 1, borderColor: BORDER, backgroundColor: BG, color: TEXT, fontSize: 15 },
  updateButton: { width: '100%', marginTop: 12, padding: 16, borderRadius: 14, backgroundColor: GOLD, alignItems: 'center' },
  updateButtonText: { color: '#000', fontSize: 15, fontWeight: '800' },
  
  alertOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.7)', justifyContent: 'center', alignItems: 'center', padding: 16 },
  alertBox: { backgroundColor: CARD, borderRadius: 16, padding: 20, maxWidth: 360, width: '100%' },
  alertTitle: { fontSize: 17, fontWeight: '700', marginBottom: 8 },
  alertMessage: { fontSize: 14, color: TEXT, lineHeight: 20, marginBottom: 16 },
  alertButtons: { flexDirection: 'row', gap: 8, justifyContent: 'flex-end' },
  alertButton: { padding: 10, borderRadius: 10, borderWidth: 1, borderColor: BORDER, backgroundColor: CARD },
  alertButtonText: { fontSize: 13, fontWeight: '600', color: TEXT },
  alertButtonPrimary: { backgroundColor: GOLD, borderWidth: 0 },
  
  // Beautiful Modal Styles
  beautifulModal: {
    width: '90%',
    maxHeight: '80%',
    backgroundColor: CARD,
    borderRadius: 24,
    borderWidth: 1,
    borderColor: BORDER,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 10 },
    shadowOpacity: 0.3,
    shadowRadius: 20,
    elevation: 10,
    alignSelf: 'center',
    marginTop: 'auto',
    marginBottom: 'auto',
  },
  beautifulModalHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingVertical: 20,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    backgroundColor: CARD,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
  },
  beautifulModalTitle: {
    fontSize: 20,
    fontWeight: '800',
    color: TEXT,
    flex: 1,
  },
  beautifulModalCloseButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: BORDER + '40',
    alignItems: 'center',
    justifyContent: 'center',
  },
  beautifulModalContent: {
    flex: 1,
    paddingHorizontal: 24,
    paddingBottom: 24,
  },
  
  // Language Option Styles
  languageOption: {
    paddingVertical: 16,
    paddingHorizontal: 16,
    borderRadius: 12,
    backgroundColor: BG,
    borderWidth: 1,
    borderColor: BORDER,
  },
  languageOptionContent: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  languageSelectedIndicator: {
    width: 24,
    height: 24,
    borderRadius: 12,
    backgroundColor: GOLD,
    alignItems: 'center',
    justifyContent: 'center',
  },
  
  // Beautiful Button Styles
  beautifulUpdateButton: {
    width: '100%',
    paddingVertical: 16,
    borderRadius: 14,
    backgroundColor: GOLD,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 4,
  },
});
