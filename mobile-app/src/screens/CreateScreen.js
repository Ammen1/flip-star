import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, Alert,
  TextInput, ActivityIndicator, ScrollView, Dimensions,
  Platform, KeyboardAvoidingView, StatusBar, Modal,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import * as ImagePicker from 'expo-image-picker';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
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
export default function CreateScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const { user, hasActiveSubscription } = useAuth();
  const { colors } = useTheme();
  const [stage, setStage] = useState('pick');
  const [media, setMedia] = useState(null);
  const [caption, setCaption] = useState('');
  const [hashtags, setHashtags] = useState('');
  const [filter, setFilter] = useState(FILTERS[0]);
  const [progress, setProgress] = useState(0);
  const videoRef = useRef(null);
  
  // Get campaignId from route params if coming from campaign
  const campaignId = route?.params?.campaignId;
  
  // Wallet state for coin deduction
  const [walletConfig, setWalletConfig] = useState(null);
  const [userBalance, setUserBalance] = useState(0);
  const [postCost, setPostCost] = useState(0);
  const [showInsufficientCoinsModal, setShowInsufficientCoinsModal] = useState(false);
  const [loadingWallet, setLoadingWallet] = useState(true);

  // Load wallet config and user balance
  useEffect(() => {
    loadWalletData();
  }, []);

  const loadWalletData = async () => {
    try {
      setLoadingWallet(true);
      const [configData, balanceData] = await Promise.all([
        api.getWalletConfig(),
        api.getWalletBalance()
      ]);
      
      console.log('[CREATE] Wallet config:', configData);
      console.log('[CREATE] User balance:', balanceData);
      
      setWalletConfig(configData);
      
      // Get total balance from response (handle different response formats)
      const totalBalance = balanceData?.balance?.total || balanceData?.total || 0;
      setUserBalance(totalBalance);
      
      // Calculate post cost based on whether it's a campaign post
      const cost = campaignId 
        ? (configData?.cost_post_create || 0)
        : (configData?.cost_post_create_non_campaign || 0);
      setPostCost(cost);
      
      console.log('[CREATE] Post cost calculated:', cost, 'for campaign:', !!campaignId);
    } catch (error) {
      console.error('[CREATE] Failed to load wallet data:', error);
    } finally {
      setLoadingWallet(false);
    }
  };

  // Refresh balance after successful post
  const refreshBalance = async () => {
    try {
      const balanceData = await api.getWalletBalance();
      const totalBalance = balanceData?.balance?.total || balanceData?.total || 0;
      setUserBalance(totalBalance);
      console.log('[CREATE] Balance refreshed:', totalBalance);
    } catch (error) {
      console.error('[CREATE] Failed to refresh balance:', error);
    }
  };

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
    });
    if (!result.canceled && result.assets?.length) {
      const asset = result.assets[0];
      console.log('Asset info:', {
        type: asset.type,
        duration: asset.duration,
        fileName: asset.fileName,
        fileSize: asset.fileSize
      });
      
      // Temporarily disable duration check to allow all videos
      if (asset.type === 'video') {
        console.log('Video detected, allowing upload regardless of duration');
        console.log('Asset info:', {
          fileName: asset.fileName,
          duration: asset.duration,
          durationType: typeof asset.duration
        });
      }
      
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
      presentationStyle: 'fullScreen',
    });
    if (!result.canceled && result.assets?.length) {
      const asset = result.assets[0];
      console.log('Camera video asset info:', {
        type: asset.type,
        duration: asset.duration,
        fileName: asset.fileName,
        fileSize: asset.fileSize
      });
      
      // Temporarily disable duration check for camera videos
      console.log('Camera video detected, allowing upload regardless of duration');
      console.log('Camera asset info:', {
        fileName: asset.fileName,
        duration: asset.duration,
        durationType: typeof asset.duration
      });
      
      setMedia({ uri: asset.uri, type: 'video' });
      setStage('edit');
    }
  };

  
const handlePost = async () => {
    if (!media) return;
    if (!user) { Alert.alert('Login Required', 'Please login to post.'); return; }
    
    // Check subscription status before allowing post creation
    if (!hasActiveSubscription) {
      Alert.alert(
        'Subscription Required',
        'You need an active subscription to create posts. Subscribe now to unlock all features!',
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Subscribe', onPress: () => navigation.navigate('Subscription') }
        ]
      );
      return;
    }
    
    // Check if user has enough coins
    if (postCost > 0 && userBalance < postCost) {
      setShowInsufficientCoinsModal(true);
      return;
    }
    
    // Show confirmation for paid posts
    if (postCost > 0) {
      Alert.alert(
        'Confirm Post',
        `This will cost ${postCost} coins. Your current balance: ${userBalance.toLocaleString()} coins.\n\nDo you want to continue?`,
        [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Post', onPress: () => executePost() }
        ]
      );
    } else {
      executePost();
    }
  };

  const executePost = async () => {
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
      // Add campaignId if posting to a campaign
      if (campaignId) {
        fd.append('campaign_id', campaignId);
        console.log('[CREATE] Posting to campaign:', campaignId);
        console.log('[CREATE] FormData entries:');
        for (let [key, value] of fd.entries()) {
          console.log(`[CREATE] ${key}:`, value);
        }
        // Also add campaign flag for backend
        fd.append('is_campaign_post', 'true');
        console.log('[CREATE] Added is_campaign_post flag');
      } else {
        console.log('[CREATE] Regular post (no campaign)');
      }

      console.log('[CREATE] Uploading post with FormData keys:', Array.from(fd._parts.map(([key]) => key)));
      const postResponse = await api.createPost(fd, { onProgress: pct => setProgress(Math.min(pct, 99)) });
      console.log('[CREATE] Post creation response:', postResponse);
      setProgress(100);
      
      // Refresh balance after successful post
      if (postCost > 0) {
        await refreshBalance();
      }
      
      setTimeout(() => {
        setMedia(null); setCaption(''); setHashtags('');
        setFilter(FILTERS[0]); setStage('pick');
      // Navigate back to campaign detail if coming from campaign, otherwise go to Home
      if (campaignId) {
        console.log('[CREATE] Post created successfully, navigating back to campaign:', campaignId);
        
        // Check if this is an auto-submission for campaign
        if (route.params?.autoSubmitToCampaign && postResponse && campaignId) {
          console.log('[CREATE] Auto-submission flow detected, submitting to campaign');
          (async () => {
            try {
              // Use the post ID from the creation response
              const postId = postResponse.id || postResponse.post_id;
              if (postId) {
                console.log('[CREATE] Submitting post to campaign:', postId);
                // Submit to campaign directly
                const response = await api.request('/campaigns/' + campaignId + '/enter/', { 
                  method: 'POST',
                  body: JSON.stringify({ reel_id: postId })
                });
                console.log('[CREATE] Campaign entry successful:', response);
                
                Alert.alert('Success!', 'Your campaign entry has been submitted! Check the leaderboard!');
              } else {
                console.log('[CREATE] No post ID in response, trying fallback method');
                // Fallback: get latest post
                const userPosts = await api.request('/reels/?user=me&limit=1');
                const latestPost = Array.isArray(userPosts) ? userPosts[0] : (userPosts.results?.[0]);
                
                if (latestPost) {
                  console.log('[CREATE] Submitting latest post to campaign:', latestPost.id);
                  const response = await api.request('/campaigns/' + campaignId + '/enter/', { 
                    method: 'POST',
                    body: JSON.stringify({ reel_id: latestPost.id })
                  });
                  console.log('[CREATE] Campaign entry successful:', response);
                  
                  Alert.alert('Success!', 'Your campaign entry has been submitted! Check the leaderboard!');
                }
              }
            } catch (error) {
              console.error('[CREATE] Auto-submission failed:', error);
              Alert.alert('Error', 'Post created but failed to submit to campaign. Please try submitting manually.');
            }
          })();
        }
        
        // Add a small delay to ensure backend processes the campaign association
        setTimeout(() => {
          console.log('[CREATE] Navigating back to campaign and triggering refresh...');
          navigation.navigate('CampaignDetail', { campaignId, refresh: true });
        }, 500);
      } else {
        navigation.navigate('Home');
      }
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
      <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
        <StatusBar barStyle={colors.statusBarStyle} backgroundColor={colors.bg} />
        <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
          <Text style={[styles.headerTitle, { color: colors.text }]}>
            {campaignId ? 'Campaign Entry' : 'New Post'}
          </Text>
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
            <Text style={[styles.heroTitle, { color: colors.text }]}>
              {campaignId ? 'Create Campaign Entry' : 'Create Your Flip'}
            </Text>
            <Text style={[styles.heroSub, { color: colors.textSecondary }]}>
              {campaignId ? 'Submit your content to win prizes!' : 'Share your moments with the community'}
            </Text>
            {campaignId && (
              <View style={[styles.campaignBadge, { backgroundColor: colors.primary, borderColor: colors.primary }]}>
                <Ionicons name="trophy" size={16} color="#000" />
                <Text style={styles.campaignBadgeText}>Campaign Entry</Text>
              </View>
            )}
          </View>

          {/* Action cards */}
          <View style={styles.actionCards}>
            <TouchableOpacity style={[styles.actionCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]} onPress={pickPhotoFromCamera} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="camera" size={24} color={colors.primary} />
              </View>
              <View style={styles.cardText}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Take Photo</Text>
                <Text style={[styles.cardSub, { color: colors.textSecondary }]}>Use camera for photos</Text>
              </View>
            </TouchableOpacity>
            
            <TouchableOpacity style={[styles.actionCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]} onPress={pickVideoFromCamera} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="videocam" size={24} color={colors.primary} />
              </View>
              <View style={styles.cardText}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Record Video</Text>
                <Text style={[styles.cardSub, { color: colors.textSecondary }]}>Record up to 60 seconds</Text>
              </View>
            </TouchableOpacity>

            <TouchableOpacity style={[styles.actionCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]} onPress={pickFromLibrary} activeOpacity={0.85}>
              <View style={styles.cardIcon}>
                <Ionicons name="cloud-upload-outline" size={24} color={colors.primary} />
              </View>
              <View style={styles.cardText}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>Upload Photo/Video</Text>
                <Text style={[styles.cardSub, { color: colors.textSecondary }]}>From gallery or files</Text>
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
      <View style={{ flex: 1, backgroundColor: colors.bg }}>
        <StatusBar barStyle={colors.statusBarStyle} backgroundColor={colors.bg} />
        <View style={StyleSheet.absoluteFill}>
          <Image source={{ uri: media.uri }} style={StyleSheet.absoluteFill} resizeMode="cover" />
          <View style={[StyleSheet.absoluteFill, { backgroundColor: filter.overlay }]} pointerEvents="none" />
        </View>

        {/* Top bar */}
        <View style={[styles.editTop, { top: insets.top + 8 }]}>
          <TouchableOpacity onPress={() => setStage('pick')} style={styles.editIconBtn}>
            <Ionicons name="close" size={26} color={colors.text} />
          </TouchableOpacity>
          <TouchableOpacity onPress={() => setStage('details')} style={[styles.nextPill, { backgroundColor: colors.primary }]}>
            <Text style={[styles.nextPillText, { color: colors.text }]}>Next →</Text>
          </TouchableOpacity>
        </View>

        {/* Filter bar */}
        <View style={[styles.filterBar, { backgroundColor: colors.cardBg, bottom: insets.bottom + 20 }]}>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ paddingHorizontal: 12, gap: 8 }}>
            {FILTERS.map(f => (
              <TouchableOpacity key={f.id} onPress={() => setFilter(f)}
                style={[styles.filterChip, { backgroundColor: colors.bg, borderColor: colors.border }, filter.id === f.id && { backgroundColor: colors.primary }]}>
                <Text style={[styles.filterChipText, { color: colors.textSecondary }, filter.id === f.id && { color: colors.text }]}>{f.name}</Text>
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
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={[styles.container, { backgroundColor: colors.bg }]}>
        <StatusBar barStyle={colors.statusBarStyle} backgroundColor={colors.bg} />
        <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border, paddingTop: insets.top + 8 }]}>
          <TouchableOpacity onPress={() => setStage('edit')}>
            <Ionicons name="chevron-back" size={24} color={colors.primary} />
          </TouchableOpacity>
          <Text style={[styles.headerTitle, { color: colors.text }]}>Post Details</Text>
          <TouchableOpacity onPress={handlePost} style={[styles.postBtn, { backgroundColor: colors.primary }]}>
            <Text style={[styles.postBtnText, { color: colors.text }]}>Post</Text>
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
            style={[styles.captionInput, { color: colors.text, backgroundColor: colors.cardBg, borderColor: colors.border }]}
            placeholder="Write a caption..."
            placeholderTextColor={colors.textSecondary}
            value={caption}
            onChangeText={setCaption}
            multiline
          />

          <View style={[styles.hashRow, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <Text style={[styles.hashSymbol, { color: colors.primary }]}>#</Text>
            <TextInput
              style={[styles.hashInput, { color: colors.text }]}
              placeholder="Add hashtags (e.g. flipstar ethiopia)"
              placeholderTextColor={colors.textSecondary}
              value={hashtags}
              onChangeText={setHashtags}
              autoCapitalize="none"
            />
          </View>

          {/* Coin Cost and Balance Info */}
          {!loadingWallet && (postCost > 0 || userBalance > 0) && (
            <View style={[styles.coinInfoCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
              <View style={styles.coinInfoHeader}>
                <Ionicons name="wallet" size={20} color={colors.primary} />
                <Text style={[styles.coinInfoTitle, { color: colors.text }]}>Post Cost</Text>
              </View>
              <View style={styles.coinInfoRow}>
                <Text style={[styles.coinInfoLabel, { color: colors.textSecondary }]}>Cost:</Text>
                <Text style={[styles.coinInfoValue, { color: postCost > userBalance ? '#ff4444' : colors.primary }]}>
                  {postCost} coins
                </Text>
              </View>
              <View style={styles.coinInfoRow}>
                <Text style={[styles.coinInfoLabel, { color: colors.textSecondary }]}>Your Balance:</Text>
                <Text style={[styles.coinInfoValue, { color: colors.text }]}>
                  {userBalance.toLocaleString()} coins
                </Text>
              </View>
              {postCost > 0 && userBalance >= postCost && (
                <Text style={[styles.coinInfoNote, { color: colors.textSecondary }]}>
                  After posting: {(userBalance - postCost).toLocaleString()} coins
                </Text>
              )}
            </View>
          )}
        </ScrollView>
      </KeyboardAvoidingView>
    );
  }

  // ── UPLOADING STAGE ─────────────────────────────────────────────────────────
  return (
    <View style={[styles.container, { backgroundColor: colors.bg, justifyContent: 'center', alignItems: 'center' }]}>
      <View style={[styles.uploadCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
        <ActivityIndicator size="large" color={colors.primary} />
        <Text style={[styles.uploadTitle, { color: colors.text }]}>Posting your content...</Text>
        <View style={[styles.progressTrack, { backgroundColor: colors.border }]}>
          <View style={[styles.progressFill, { backgroundColor: colors.primary, width: `${progress}%` }]} />
        </View>
        <Text style={{ color: colors.primary, fontSize: 14, fontWeight: '600' }}>{progress}%</Text>
      </View>
    </View>
  );

  // ── INSUFFICIENT COINS MODAL ────────────────────────────────────────────────
  if (showInsufficientCoinsModal) {
    return (
      <Modal transparent animationType="fade">
        <View style={[styles.modalOverlay, { backgroundColor: 'rgba(0,0,0,0.7)' }]}>
          <View style={[styles.insufficientCoinsModal, { backgroundColor: colors.cardBg }]}>
            <View style={styles.modalHeader}>
              <Ionicons name="wallet" size={32} color="#ff4444" />
              <Text style={[styles.modalTitle, { color: colors.text }]}>Insufficient Coins</Text>
            </View>
            
            <View style={styles.modalContent}>
              <Text style={[styles.modalMessage, { color: colors.textSecondary }]}>
                You need {postCost} coins to create this post, but you only have {userBalance.toLocaleString()} coins.
              </Text>
              
              <View style={[styles.coinsSummary, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                <View style={styles.coinsRow}>
                  <Text style={[styles.coinsLabel, { color: colors.textSecondary }]}>Required:</Text>
                  <Text style={[styles.coinsRequired, { color: '#ff4444' }]}>{postCost} coins</Text>
                </View>
                <View style={styles.coinsRow}>
                  <Text style={[styles.coinsLabel, { color: colors.textSecondary }]}>Your Balance:</Text>
                  <Text style={[styles.coinsBalance, { color: colors.text }]}>{userBalance.toLocaleString()} coins</Text>
                </View>
                <View style={styles.coinsRow}>
                  <Text style={[styles.coinsLabel, { color: colors.textSecondary }]}>Need More:</Text>
                  <Text style={[styles.coinsNeeded, { color: colors.primary }]}>{Math.max(0, postCost - userBalance)} coins</Text>
                </View>
              </View>
            </View>
            
            <View style={styles.modalActions}>
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalCancelBtn, { borderColor: colors.border }]}
                onPress={() => setShowInsufficientCoinsModal(false)}
              >
                <Text style={[styles.modalCancelText, { color: colors.textSecondary }]}>Cancel</Text>
              </TouchableOpacity>
              
              <TouchableOpacity
                style={[styles.modalBtn, styles.modalBuyBtn, { backgroundColor: colors.primary }]}
                onPress={() => {
                  setShowInsufficientCoinsModal(false);
                  navigation.navigate('WebsiteCoin');
                }}
              >
                <Text style={[styles.modalBuyText, { color: colors.text }]}>Get Coins</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    );
  }
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
  campaignBadge: {
    flexDirection: 'row', alignItems: 'center', gap: 6,
    paddingHorizontal: 12, paddingVertical: 6,
    borderRadius: 16, borderWidth: 1,
    marginTop: 12,
  },
  campaignBadgeText: {
    color: '#000', fontSize: 12, fontWeight: '700',
  },
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

  // Coin Info Card
  coinInfoCard: {
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    marginTop: 8,
  },
  coinInfoHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
  },
  coinInfoTitle: {
    fontSize: 16,
    fontWeight: '700',
  },
  coinInfoRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 4,
  },
  coinInfoLabel: {
    fontSize: 14,
    fontWeight: '500',
  },
  coinInfoValue: {
    fontSize: 14,
    fontWeight: '700',
  },
  coinInfoNote: {
    fontSize: 12,
    fontStyle: 'italic',
    marginTop: 8,
    textAlign: 'center',
  },

  // Insufficient Coins Modal
  modalOverlay: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  insufficientCoinsModal: {
    width: width * 0.9,
    maxWidth: 400,
    borderRadius: 20,
    padding: 24,
  },
  modalHeader: {
    alignItems: 'center',
    marginBottom: 20,
  },
  modalTitle: {
    fontSize: 20,
    fontWeight: '800',
    marginTop: 12,
  },
  modalContent: {
    marginBottom: 24,
  },
  modalMessage: {
    fontSize: 15,
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 20,
  },
  coinsSummary: {
    borderRadius: 12,
    padding: 16,
    borderWidth: 1,
    gap: 12,
  },
  coinsRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  coinsLabel: {
    fontSize: 14,
    fontWeight: '500',
  },
  coinsRequired: {
    fontSize: 16,
    fontWeight: '800',
  },
  coinsBalance: {
    fontSize: 16,
    fontWeight: '700',
  },
  coinsNeeded: {
    fontSize: 16,
    fontWeight: '800',
  },
  modalActions: {
    flexDirection: 'row',
    gap: 12,
  },
  modalBtn: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 12,
    alignItems: 'center',
  },
  modalCancelBtn: {
    borderWidth: 1,
  },
  modalBuyBtn: {},
  modalCancelText: {
    fontSize: 15,
    fontWeight: '600',
  },
  modalBuyText: {
    fontSize: 15,
    fontWeight: '700',
  },
});
