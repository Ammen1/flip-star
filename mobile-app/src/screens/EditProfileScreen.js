import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, TextInput, Image, ScrollView, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';
import { AppAlert } from '../components/AppAlert';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

export default function EditProfileScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { user, loadUser } = useAuth();
  const [form, setForm] = useState({ first_name: '', last_name: '', username: '', bio: '' });
  const [photo, setPhoto] = useState(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (user) {
      setForm({
        first_name: user.first_name || '',
        last_name: user.last_name || '',
        username: user.username || '',
        bio: user.bio || '',
      });
      setPhoto(user.profile_photo || null);
    }
  }, [user]);

  const pickPhoto = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') { AppAlert.alert('Permission Required', 'Please allow photo library access.'); return; }
    const result = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ImagePicker.MediaTypeOptions.Images, allowsEditing: true, aspect: [1, 1], quality: 0.8 });
    if (!result.canceled && result.assets?.length) setPhoto(result.assets[0].uri);
  };

  const save = async () => {
    console.log('Save button pressed, saving state:', saving);
    
    // Prevent multiple simultaneous saves
    if (saving) {
      console.log('Save already in progress, ignoring click');
      return;
    }
    
    setSaving(true);
    console.log('Set saving to true');
    
    // Safety timeout to reset saving state if it gets stuck
    const timeout = setTimeout(() => {
      console.log('Safety timeout: resetting saving state');
      setSaving(false);
    }, 10000); // 10 second timeout
    
    try {
      let photoUploadSuccess = false;
      
      // Step 1: Update profile text fields
      const profileData = {
        first_name: form.first_name,
        last_name: form.last_name,
        username: form.username,
        bio: form.bio,
      };
      
      console.log('Updating profile text fields...');
      const response = await api.updateProfile(profileData);
      console.log('Profile update response:', response);
      
      // Step 2: Upload photo if changed
      if (photo && photo !== user?.profile_photo) {
        console.log('Uploading new profile photo...');
        try {
          const photoFile = {
            uri: photo,
            type: 'image/jpeg',
            name: 'profile_photo.jpg',
          };
          await api.uploadProfilePhoto(photoFile);
          console.log('Photo upload successful');
          photoUploadSuccess = true;
        } catch (photoError) {
          console.log('Photo upload failed:', photoError);
          // Don't fail the entire operation if photo upload fails
        }
      }
      
      // Step 3: Reload user data
      await loadUser();
      
      // Step 4: Show appropriate success message
      if (photo && photo !== user?.profile_photo && photoUploadSuccess) {
        AppAlert.alert('✅ Profile Updated!', 'Your profile and photo have been saved.', [{ text: 'OK', onPress: () => navigation.goBack() }]);
      } else if (photo && photo !== user?.profile_photo) {
        AppAlert.alert('⚠️ Profile Updated', 'Your profile information was saved, but the photo could not be uploaded. Please try again later.', [{ text: 'OK', onPress: () => navigation.goBack() }]);
      } else {
        AppAlert.alert('✅ Profile Updated!', 'Your profile has been saved.', [{ text: 'OK', onPress: () => navigation.goBack() }]);
      }
    } catch (e) {
      console.error('Profile update error:', e);
      const errorMessage = e.message || 'Failed to update profile';
      
      // Provide more helpful error messages
      if (errorMessage.includes('Network request failed')) {
        AppAlert.alert('Network Error', 'Unable to connect to the server. Please check your internet connection and try again.');
      } else if (errorMessage.includes('401') || errorMessage.includes('Unauthorized')) {
        AppAlert.alert('Authentication Error', 'Please log in again and try updating your profile.');
      } else if (errorMessage.includes('400') || errorMessage.includes('Bad Request')) {
        AppAlert.alert('Invalid Data', 'Please check your profile information and try again.');
      } else {
        AppAlert.alert('Error', errorMessage);
      }
    } finally { 
    console.log('Resetting saving state to false');
    clearTimeout(timeout); // Clear the safety timeout
    setSaving(false); 
  }
  };

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="close" size={24} color="#fff" />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>Edit Profile</Text>
        <TouchableOpacity onPress={save} disabled={saving}>
          {saving ? <ActivityIndicator size="small" color={GOLD} /> : <Text style={styles.saveBtn}>Save</Text>}
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={{ padding: 20 }}>
        {/* Avatar */}
        <TouchableOpacity style={styles.avatarContainer} onPress={pickPhoto}>
          {photo
            ? <Image source={{ uri: photo }} style={styles.avatar} />
            : <View style={[styles.avatar, { backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center' }]}>
                <Text style={{ color: '#000', fontSize: 32, fontWeight: '700' }}>{(form.username || '?')[0].toUpperCase()}</Text>
              </View>}
          <View style={styles.editPhotoOverlay}>
            <Ionicons name="camera" size={20} color="#fff" />
          </View>
        </TouchableOpacity>
        <Text style={styles.changePhotoText}>Change photo</Text>

        {/* Fields */}
        {[
          { key: 'first_name', label: 'First Name', placeholder: 'Enter first name' },
          { key: 'last_name', label: 'Last Name', placeholder: 'Enter last name' },
          { key: 'username', label: 'Username', placeholder: 'Enter username' },
        ].map(f => (
          <View key={f.key} style={styles.field}>
            <Text style={styles.label}>{f.label}</Text>
            <TextInput
              style={styles.input}
              value={form[f.key]}
              onChangeText={v => setForm(p => ({ ...p, [f.key]: v }))}
              placeholder={f.placeholder}
              placeholderTextColor="#555"
              autoCapitalize={f.key === 'username' ? 'none' : 'words'}
            />
          </View>
        ))}

        <View style={styles.field}>
          <Text style={styles.label}>Bio</Text>
          <TextInput
            style={[styles.input, { height: 90, textAlignVertical: 'top', paddingTop: 12 }]}
            value={form.bio}
            onChangeText={v => setForm(p => ({ ...p, bio: v }))}
            placeholder="Write something about yourself..."
            placeholderTextColor="#555"
            multiline
            maxLength={150}
          />
          <Text style={styles.charCount}>{form.bio.length}/150</Text>
        </View>
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#fff' },
  saveBtn: { color: GOLD, fontSize: 15, fontWeight: '700' },
  avatarContainer: { alignSelf: 'center', marginBottom: 12, position: 'relative' },
  avatar: { width: 100, height: 100, borderRadius: 50, borderWidth: 3, borderColor: GOLD },
  editPhotoOverlay: { position: 'absolute', bottom: 0, right: 0, width: 32, height: 32, borderRadius: 16, backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center', borderWidth: 2, borderColor: BG },
  changePhotoText: { textAlign: 'center', color: GOLD, fontSize: 14, fontWeight: '600', marginBottom: 28 },
  field: { marginBottom: 20 },
  label: { fontSize: 13, fontWeight: '600', color: GOLD, marginBottom: 8, textTransform: 'uppercase', letterSpacing: 0.5 },
  input: { backgroundColor: CARD, borderRadius: 12, borderWidth: 1.5, borderColor: BORDER, paddingHorizontal: 16, paddingVertical: 14, color: '#fff', fontSize: 16 },
  charCount: { fontSize: 12, color: '#666', textAlign: 'right', marginTop: 6 },
});
