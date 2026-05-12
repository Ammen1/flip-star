import React, { useState, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, Alert,
  TextInput, ActivityIndicator, ScrollView, Dimensions,
  Platform, KeyboardAvoidingView, StatusBar, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';

const { width } = Dimensions.get('window');
const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

const FILTERS = [
  { id: 'none',    name: 'Original', overlay: 'transparent' },
  { id: 'warm',    name: 'Warm',     overlay: 'rgba(255,140,0,0.15)' },
  { id: 'cool',    name: 'Cool',     overlay: 'rgba(30,80,200,0.12)' },
  { id: 'vintage', name: 'Vintage',  overlay: 'rgba(120,70,10,0.2)' },
  { id: 'golden',  name: 'Golden',   overlay: 'rgba(218,155,42,0.18)' },
  { id: 'dark',    name: 'Dark',     overlay: 'rgba(0,0,0,0.25)' },
];

// Stage: 'pick' | 'edit' | 'details' | 'uploading'
export default function CreateScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [stage, setStage] = useState('pick');
  const [media, setMedia] = useState(null);
  const [caption, setCaption] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [filter, setFilter] = useState(FILTERS[0]);
  const [progress, setProgress] = useState(0);
  const videoRef = useRef(null);

  const pickFromLibrary = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Please allow access to your photo library.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.All,
      allowsEditing: false,
      quality: 0.85,
      videoMaxDuration: 60,
    });
    if (!result.canceled && result.assets?.length) {
      const asset = result.assets[0];
      setMedia({ uri: asset.uri, type: asset.type || 'image' });
      setStage('edit');
    }
  };

  const pickPhotoFromCamera = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Please allow camera access.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      allowsEditing: false,
      quality: 0.85,
    });
    if (!result.canceled && result.assets?.length) {
      const asset = result.assets[0];
      setMedia({ uri: asset.uri, type: 'image' });
      setStage('edit');
    }
  };

  const pickVideoFromCamera = async () => {
    const { status } = await ImagePicker.requestCameraPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission Required', 'Please allow camera access.');
      return;
    }
    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Videos,
      allowsEditing: false,
      quality: 0.85,
      videoMaxDuration: 60,
      presentationStyle: 'fullScreen',
    });
    if (!result.canceled && result.assets?.length) {
      const asset = result.assets[0];
      setMedia({ uri: asset.uri, type: 'video' });
      setStage('edit');
    }
  };

  const handlePost = async () => {
    if (!media) return;
    if (!user) { Alert.alert('Login Required', 'Please login to post.'); return; }
    setStage('uploading');
    setProgress(0);
    try {
      const isVideo = media.type === 'video';
      const fd = new FormData();
      
      // Backend expects exactly 'file' parameter (see backend/api/views.py line 753)
      // Properly handle URI for both iOS and Android
      let fileUri = media.uri;
      if (Platform.OS === 'ios' && fileUri.startsWith('file://')) {
        fileUri = fileUri.replace('file://', '');
      }
      // On Android, we might need to keep the file:// prefix or remove it based on the system
      if (Platform.OS === 'android' && fileUri.startsWith('file://')) {
        // Try removing file:// for Android as well
        fileUri = fileUri.replace('file://', '');
      }
      
      const fileName = isVideo ? 'video.mp4' : 'image.jpg';
      
      // Try different file object formats
      console.log('Original Media URI:', media.uri);
      console.log('Processed File URI:', fileUri);
      console.log('File name:', fileName);
      console.log('Is video:', isVideo);
      
      // Format 1: Standard React Native format
      const fileObj1 = {
        uri: fileUri,
        type: isVideo ? 'video/mp4' : 'image/jpeg',
        name: fileName,
      };
      
      // Format 2: With additional properties
      const fileObj2 = {
        uri: fileUri,
        type: isVideo ? 'video/mp4' : 'image/jpeg',
        name: fileName,
        fileName: fileName,
        fileSize: 0,
        lastModified: Date.now(),
      };
      
      // Try using the actual media asset if available
      let fileToUpload;
      
      if (media.assets && media.assets[0]) {
        // Use the actual asset from ImagePicker
        const asset = media.assets[0];
        fileToUpload = {
          uri: asset.uri,
          type: asset.type || (isVideo ? 'video/mp4' : 'image/jpeg'),
          name: asset.fileName || fileName,
        };
        console.log('Using asset from media.assets:', fileToUpload);
      } else {
        // Fallback to constructed file object
        fileToUpload = {
          uri: media.uri,
          type: isVideo ? 'video/mp4' : 'image/jpeg',
          name: fileName,
        };
        console.log('Using constructed file object:', fileToUpload);
      }
      
      fd.append('file', fileToUpload);
      
      // Debug FormData contents and media structure
      console.log('Media object structure:', JSON.stringify(media, null, 2));
      console.log('FormData entries:');
      for (let [key, value] of fd._parts) {
        console.log(`${key}:`, value);
        console.log(`${key} type:`, typeof value);
        console.log(`${key} keys:`, Object.keys(value));
      }
      
      // Try alternative FormData construction
      try {
        // Method 1: Direct append
        const fd2 = new FormData();
        fd2.append('file', {
          uri: fileToUpload.uri,
          type: fileToUpload.type,
          name: fileToUpload.name,
        });
        console.log('Alternative FormData created successfully');
      } catch (e) {
        console.log('Alternative FormData failed:', e);
      }
      
      fd.append('caption', caption || '');
      if (hashtags) fd.append('hashtags', hashtags);

      await api.createPost(fd, { onProgress: pct => setProgress(Math.min(pct, 99)) });
      setProgress(100);
      setTimeout(() => {
        setMedia(null); setCaption(''); setHashtags('');
        setFilter(FILTERS[0]); setStage('pick');
        navigation.navigate('Home');
      }, 600);
    } catch (err) {
      const msg = typeof err === 'object' ? (err.detail || err.error || err.message || 'Upload failed') : String(err);
      Alert.alert('Upload Failed', msg);
      setStage('details');
    }
  };

  // ── PICK STAGE ──────────────────────────────────────────────────────────────
  if (stage === 'pick') {
    return (
      <View style={[styles.container, { paddingTop: insets.top }]}>
        <StatusBar barStyle="light-content" />
        <View style={styles.header}>
          <Text style={styles.headerTitle}>New Post</Text>
        </View>
        <ScrollView contentContainerStyle={styles.pickBody}>
          {/* Hero */}
          <View style={styles.heroSection}>
            <View style={styles.heroCircle}>
              <Image
                source={require('../image/create_img.jpg')}
                style={{ width: 72, height: 72, borderRadius: 36 }}
                resizeMode="cover"
              />
              <View style={styles.sparkle}><Text style={{ fontSize: 11 }}>✨</Text></View>
            </View>
            <Text style={styles.heroTitle}>Create Post</Text>
            <Text style={styles.heroSub}>Choose how you want to create content</Text>
          </View>

          {/* Action cards */}
          <View style={styles.actionCards}>
            <TouchableOpacity style={styles.actionCard} onPress={pickPhotoFromCamera} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="camera" size={24} color={GOLD} />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardTitle}>Take Photo</Text>
                <Text style={styles.cardSub}>Use camera for photos</Text>
              </View>
            </TouchableOpacity>
            
            <TouchableOpacity style={styles.actionCard} onPress={pickVideoFromCamera} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="videocam" size={24} color={GOLD} />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardTitle}>Record Video</Text>
                <Text style={styles.cardSub}>Record up to 60 seconds</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={styles.actionCard} onPress={pickFromLibrary} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="cloud-upload-outline" size={24} color={GOLD} />
              </View>
              <View style={styles.cardText}>
                <Text style={styles.cardTitle}>Upload Photo/Video</Text>
                <Text style={styles.cardSub}>From gallery or files</Text>
              </View>
              <Text style={{ color: GOLD, fontSize: 22, fontWeight: '300' }}>+</Text>
            </TouchableOpacity>
          </View>
        </ScrollView>
      </View>
    );
  }

  // ── EDIT STAGE ──────────────────────────────────────────────────────────────
  if (stage === 'edit') {
    return (
      <View style={{ flex: 1, backgroundColor: '#000' }}>
        <StatusBar barStyle="light-content" />
        <View style={StyleSheet.absoluteFill}>
          <Image source={{ uri: media.uri }} style={StyleSheet.absoluteFill} resizeMode="cover" />
          <View style={[StyleSheet.absoluteFill, { backgroundColor: filter.overlay }]} pointerEvents="none" />
        </View>

        {/* Top bar */}
        <View style={[styles.editTop, { top: insets.top + 8 }]}>
          <TouchableOpacity onPress={() => setStage('pick')} style={styles.editIconBtn}>
            <Ionicons name="close" size={26} color="#fff" />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setStage('details')} style={styles.nextPill}>
            <Text style={styles.nextPillText}>Next →</Text>
          </TouchableOpacity>
        </View>

        {/* Filter bar */}
        <View style={[styles.filterBar, { bottom: insets.bottom + 20 }]}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 8 }}>
            {FILTERS.map(f => (
              <TouchableOpacity key={f.id} onPress={() => setFilter(f)}
                style={[styles.filterChip, filter.id === f.id && styles.filterChipActive]}>
                <Text style={[styles.filterChipText, filter.id === f.id && { color: '#000' }]}>{f.name}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
        </View>
      </View>
    );
  }

  // ── DETAILS STAGE ───────────────────────────────────────────────────────────
  if (stage === 'details') {
    return (
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={styles.container}>
        <StatusBar barStyle="light-content" />
        <View style={[styles.header, { paddingTop: insets.top + 8 }]}>
          <TouchableOpacity onPress={() => setStage('edit')}>
            <Ionicons name="chevron-back" size={24} color={GOLD} />
          </TouchableOpacity>
          <Text style={styles.headerTitle}>Post Details</Text>
          <TouchableOpacity onPress={handlePost} style={styles.postBtn}>
            <Text style={styles.postBtnText}>Post</Text>
          </TouchableOpacity>
        </View>

        <ScrollView contentContainerStyle={{ padding: 16, gap: 16 }}>
          {/* Preview */}
          <View style={styles.thumb}>
            <Image source={{ uri: media.uri }} style={StyleSheet.absoluteFill} resizeMode="cover" />
            <View style={[StyleSheet.absoluteFill, { backgroundColor: filter.overlay }]} pointerEvents="none" />
            {media.type === 'video' && (
              <View style={styles.videoIcon}>
                <Ionicons name="videocam" size={16} color="#fff" />
              </View>
            )}
          </View>

          <TextInput
            style={styles.captionInput}
            placeholder="Write a caption..."
            placeholderTextColor="#555"
            value={caption}
            onChangeText={setCaption}
            multiline
          />

          <View style={styles.hashRow}>
            <Text style={styles.hashSymbol}>#</Text>
            <TextInput
              style={styles.hashInput}
              placeholder="Add hashtags (e.g. flipstar ethiopia)"
              placeholderTextColor="#555"
              value={hashtags}
              onChangeText={setHashtags}
              autoCapitalize="none"
            />
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ── UPLOADING STAGE ─────────────────────────────────────────────────────────
  return (
    <View style={[styles.container, { justifyContent: 'center', alignItems: 'center' }]}>
      <View style={styles.uploadCard}>
        <ActivityIndicator size="large" color={GOLD} />
        <Text style={styles.uploadTitle}>Posting your content...</Text>
        <View style={styles.progressTrack}>
          <View style={[styles.progressFill, { width: `${progress}%` }]} />
        </View>
        <Text style={{ color: GOLD, fontSize: 14, fontWeight: '600' }}>{progress}%</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: {
    flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between',
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  headerTitle: { fontSize: 17, fontWeight: '800', color: GOLD },
  pickBody: { paddingHorizontal: 20, paddingBottom: 40 },
  heroSection: { alignItems: 'center', paddingTop: 48, paddingBottom: 32 },
  heroCircle: { position: 'relative', marginBottom: 16 },
  sparkle: {
    position: 'absolute', top: -2, right: -2,
    width: 22, height: 22, borderRadius: 11,
    backgroundColor: GOLD, alignItems: 'center', justifyContent: 'center',
    borderWidth: 2, borderColor: BG,
  },
  heroTitle: { fontSize: 22, fontWeight: '800', color: GOLD, marginBottom: 6 },
  heroSub: { fontSize: 13, color: '#888', textAlign: 'center' },
  actionCards: { gap: 16 },
  actionCard: {
    backgroundColor: CARD, borderRadius: 16, padding: 18,
    flexDirection: 'row', alignItems: 'center', gap: 16,
    borderWidth: 1.5, borderColor: GOLD + '40',
  },
  cardIcon: {
    width: 52, height: 52, borderRadius: 12,
    backgroundColor: BG, borderWidth: 1, borderColor: BORDER,
    alignItems: 'center', justifyContent: 'center',
  },
  cardText: { flex: 1 },
  cardTitle: { fontSize: 15, fontWeight: '700', color: GOLD, marginBottom: 3 },
  cardSub: { fontSize: 13, color: '#888' },
  editTop: {
    position: 'absolute', left: 0, right: 0,
    flexDirection: 'row', justifyContent: 'space-between',
    paddingHorizontal: 14, zIndex: 10,
  },
  editIconBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.5)', alignItems: 'center', justifyContent: 'center',
  },
  nextPill: { backgroundColor: GOLD, paddingHorizontal: 20, paddingVertical: 9, borderRadius: 22 },
  nextPillText: { color: '#000', fontWeight: '800', fontSize: 14 },
  filterBar: { position: 'absolute', left: 0, right: 0, zIndex: 10 },
  filterChip: {
    paddingHorizontal: 14, paddingVertical: 7, borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.2)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.3)',
  },
  filterChipActive: { backgroundColor: GOLD, borderColor: GOLD },
  filterChipText: { color: '#fff', fontWeight: '700', fontSize: 13 },
  thumb: {
    width: '100%', height: 220, borderRadius: 16,
    overflow: 'hidden', backgroundColor: '#111',
  },
  videoIcon: {
    position: 'absolute', top: 10, right: 10,
    backgroundColor: 'rgba(0,0,0,0.5)', borderRadius: 6, padding: 4,
  },
  captionInput: {
    fontSize: 15, color: '#fff',
    borderBottomWidth: 1, borderBottomColor: BORDER,
    paddingBottom: 12, minHeight: 80,
  },
  hashRow: {
    flexDirection: 'row', alignItems: 'center',
    backgroundColor: CARD, borderRadius: 12,
    paddingHorizontal: 12, height: 48,
  },
  hashSymbol: { fontSize: 20, fontWeight: '800', color: GOLD, marginRight: 6 },
  hashInput: { flex: 1, fontSize: 14, color: '#fff' },
  postBtn: { backgroundColor: GOLD, paddingHorizontal: 18, paddingVertical: 8, borderRadius: 20 },
  postBtnText: { color: '#000', fontWeight: '800', fontSize: 14 },
  uploadCard: { alignItems: 'center', padding: 32, gap: 16 },
  uploadTitle: { fontSize: 18, fontWeight: '800', color: '#fff' },
  progressTrack: {
    width: width * 0.7, height: 8,
    backgroundColor: '#333', borderRadius: 4, overflow: 'hidden',
  },
  progressFill: { height: '100%', backgroundColor: GOLD },
});
