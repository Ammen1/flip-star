import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, FlatList,
  ActivityIndicator, ScrollView, Dimensions, Alert, RefreshControl,
  StatusBar, Modal, TextInput, Share,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import config from '../config';

const { width, height } = Dimensions.get('window');
const GOLD = '#8fc441';
const LIGHT_GOLD = '#b5dd8f';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const COLS = 3;

const BASE = config.API_BASE_URL.replace('/api', '');
const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${BASE}${url}`;
};

// Format phone number to start with +251
const formatPhoneNumber = (phoneNumber) => {
  if (!phoneNumber) return '';
  
  // Remove all non-digit characters
  const digits = phoneNumber.replace(/\D/g, '');
  
  // If already starts with 251, just add +
  if (digits.startsWith('251')) {
    return `+${digits}`;
  }
  
  // If starts with 0 (Ethiopian format), replace 0 with +251
  if (digits.startsWith('0') && digits.length >= 9) {
    return `+251${digits.substring(1)}`;
  }
  
  // If just 9 digits, assume Ethiopian format and add +251
  if (digits.length === 9) {
    return `+251${digits}`;
  }
  
  // Default: add +251 prefix
  return `+251${digits}`;
};
const GAP = 1;
const ITEM_SIZE = Math.floor((width - (GAP * (COLS - 1)) - 32) / COLS);

export default function ProfileScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const { user: authUser, logout } = useAuth();
  const { colors } = useTheme();
  // authUser from /profile/me/ (UserProfileSerializer):
  //   authUser.id      = UserProfile.pk
  //   authUser.user.id = User.pk (or authUser.id if flat login response)
  const authProfileId = authUser?.id;
  const authUserId    = authUser?.user?.id || authUser?.id;
  const routeUserId   = route?.params?.userId;

  // isOwnProfile is STATE — set definitively after profile data loads so there
  // is zero chance of a stale/wrong value from timing or ID format differences.
  const [isOwnProfile, setIsOwnProfile] = useState(!routeUserId); // best initial guess

  // targetProfileId / targetUserId — best-effort before data loads
  const targetProfileId = !routeUserId ? authProfileId : routeUserId;
  const targetUserId    = !routeUserId ? authUserId    : routeUserId;

  // Seed own profile immediately from cached authUser so name/username appear at once
  const [profile, setProfile] = useState(!routeUserId ? authUser : null);
  const [posts, setPosts] = useState([]);
  const [reels, setReels] = useState([]);
  const [savedPosts, setSavedPosts] = useState([]);
  const [campaignStats, setCampaignStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [isFollowing, setIsFollowing] = useState(false);
  const [activeTab, setActiveTab] = useState('posts');
  const [postsCount, setPostsCount] = useState(0);
  const [followersCount, setFollowersCount] = useState(0);
  const [followingCount, setFollowingCount] = useState(0);
  const [showOptions, setShowOptions] = useState(false);
  const [isBlocked, setIsBlocked] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [reportingUser, setReportingUser] = useState(false);
  const [reportMessage, setReportMessage] = useState('');
  const [showProfileZoom, setShowProfileZoom] = useState(false);
  const [editingBio, setEditingBio] = useState(false);
  const [bioText, setBioText] = useState('');
  const [showEditProfile, setShowEditProfile] = useState(false);
  const [editForm, setEditForm] = useState({
    first_name: '',
    last_name: '',
    username: '',
    bio: '',
    email: '',
  });
  const [savingProfile, setSavingProfile] = useState(false);
  const [postMenuId, setPostMenuId] = useState(null);
  const [confirmDeleteId, setConfirmDeleteId] = useState(null);
  const [editingPost, setEditingPost] = useState(null);
  const [editCaption, setEditCaption] = useState('');
  const [editHashtags, setEditHashtags] = useState('');
  const [editMediaFile, setEditMediaFile] = useState(null);
  const [editMediaPreview, setEditMediaPreview] = useState(null);
  const [isSaving, setIsSaving] = useState(false);
  const [successMessage, setSuccessMessage] = useState('');

  // Report reasons matching website
  const REPORT_REASONS = [
    { id: 'harassment', label: 'Harassment or Bullying', emoji: '😡' },
    { id: 'spam', label: 'Spam or Fake Account', emoji: '⚠️' },
    { id: 'inappropriate', label: 'Inappropriate Content', emoji: '😢' },
    { id: 'hate_speech', label: 'Hate Speech', emoji: '🚫' },
    { id: 'scam', label: 'Scam or Fraud', emoji: '💸' },
    { id: 'other', label: 'Other', emoji: '📋' },
  ];

  useEffect(() => { 
    // Reset state when targetProfileId changes to prevent profile mixing
    setProfile(null);
    setPosts([]);
    setReels([]);
    setSavedPosts([]);
    setCampaignStats(null);
    setIsFollowing(false);
    setActiveTab('posts');
    loadProfile(); 
  }, [targetProfileId]);

  // Reload profile when screen comes back into focus (e.g. after EditProfile)
  useEffect(() => {
    const unsubscribe = navigation.addListener('focus', () => {
      // Always reload profile when screen focuses to ensure correct profile is shown
      loadProfile();
    });
    return unsubscribe;
  }, [navigation]);

  useEffect(() => { 
    if (activeTab === 'reels') loadReels();
    else if (activeTab === 'saved') loadSavedPosts();
    else if (activeTab === 'campaigns') loadCampaignStats();
  }, [activeTab]);

  const loadProfile = async () => {
    try {
      setLoading(true);
      // Use targetProfileId to determine endpoint, not isOwnProfile state
      const isOwnProfileCheck = !routeUserId || String(targetProfileId) === String(authProfileId) || String(targetProfileId) === String(authUserId);
      const profileEndpoint = isOwnProfileCheck ? '/profile/me/' : `/profile/${targetProfileId}/`;

      // Fetch profile first to get the real userId reliably
      const profileData = await api.request(profileEndpoint);
      setProfile(profileData);

      const nestedUserEarly = profileData.user || profileData;
      const realUserId = nestedUserEarly.id ?? profileData.id ?? targetUserId;

      // Load profile data with error handling for each endpoint
      const [postsData, followersData, followingData] = await Promise.allSettled([
        api.request(`/reels/?user=${realUserId}`),
        api.request(`/follows/?following=${realUserId}`).catch(e => {
          console.warn('Followers API failed:', e?.message);
          // Try alternative endpoint format
          return api.request(`/api/follows/?following=${realUserId}`).catch(altE => {
            console.warn('Alternative followers API failed:', altE?.message);
            return { results: [], count: 0 };
          });
        }),
        api.request(`/follows/?follower=${realUserId}`).catch(e => {
          console.warn('Following API failed:', e?.message);
          // Try alternative endpoint format
          return api.request(`/api/follows/?follower=${realUserId}`).catch(altE => {
            console.warn('Alternative following API failed:', altE?.message);
            return { results: [], count: 0 };
          });
        }),
      ]);

      // Extract data from settled promises
      const postsResult = postsData.status === 'fulfilled' ? postsData.value : { results: [] };
      const followersResult = followersData.status === 'fulfilled' ? followersData.value : { results: [], count: 0 };
      const followingResult = followingData.status === 'fulfilled' ? followingData.value : { results: [], count: 0 };

      const postsList = Array.isArray(postsResult) ? postsResult : (postsResult.results || []);
      setPosts(postsList);
      setPostsCount(postsResult.count ?? postsList.length);
      setReels(postsList.filter(p => p.media));

      // followers_count and following_count come from the nested user object in UserProfileSerializer
      const nestedUser = nestedUserEarly;
      const followersFromProfile = nestedUser.followers_count ?? null;
      const followingFromProfile = nestedUser.following_count ?? null;

      // Use API list counts as secondary source
      const followersList = Array.isArray(followersResult) ? followersResult : (followersResult.results || []);
      const followingList = Array.isArray(followingResult) ? followingResult : (followingResult.results || []);

      setFollowersCount(followersFromProfile !== null ? followersFromProfile : followersList.length);
      setFollowingCount(followingFromProfile !== null ? followingFromProfile : followingList.length);

      // ── Determine ownership from the ACTUAL returned profile data ──────────
      // Compare the profile's real User.id against every known auth ID.
      // This is the only 100 % reliable check — it works regardless of which
      // ID format was passed in route.params or stored in authUser.
      const profileUserId = nestedUser.id ?? profileData.id;
      const amOwner = !routeUserId
        || String(profileUserId) === String(authUserId)
        || String(profileUserId) === String(authProfileId)
        || String(profileData.id) === String(authProfileId);
      setIsOwnProfile(Boolean(amOwner));
      // ────────────────────────────────────────────────────────────────────────

      setIsFollowing(amOwner ? false : (nestedUser.is_following || profileData.is_following || false));
      setBioText(profileData.bio || nestedUser.bio || '');
      setEditForm({
        first_name: nestedUser.first_name || profileData.first_name || '',
        last_name: nestedUser.last_name || profileData.last_name || '',
        username: nestedUser.username || profileData.username || '',
        bio: profileData.bio || nestedUser.bio || '',
        email: nestedUser.email || profileData.email || '',
      });
    } catch (e) { console.warn('loadProfile error:', e?.message); }
    finally { setLoading(false); setRefreshing(false); }
  };

  const loadReels = async () => {
    try {
      const reelsData = await api.request(`/reels/?user=${targetUserId}`);
      const reelsList = Array.isArray(reelsData) ? reelsData : (reelsData.results || []);
      setReels(reelsList.filter(p => p.media));
    } catch (e) { /* silent */ }
  };

  const loadSavedPosts = async () => {
    if (!isOwnProfile) return;
    try {
      const savedData = await api.request(`/reels/?saved=true`);
      setSavedPosts(Array.isArray(savedData) ? savedData : (savedData.results || []));
    } catch (e) { /* silent */ }
  };

  const loadCampaignStats = async () => {
    try {
      const campaignData = await api.request(`/campaigns/profile/${targetUserId || ''}`);
      setCampaignStats(campaignData);
    } catch (e) { /* silent */ }
  };

  const onRefresh = () => {
    setRefreshing(true);
    loadProfile();
  };

  const toggleFollow = async () => {
    // Hard guard: never let a user follow themselves regardless of UI state
    const tId = String(targetUserId);
    if (tId === String(authUserId) || tId === String(authProfileId)) return;
    const prev = isFollowing;
    setIsFollowing(!prev);
    setFollowersCount(c => prev ? c - 1 : c + 1);
    try {
      await api.toggleFollow(targetUserId);
    } catch (error) {
      console.error('Follow toggle error:', error);
      setIsFollowing(prev);
      setFollowersCount(c => prev ? c + 1 : c - 1);
    }
  };

  const handleBlockUser = async () => {
    if (!user || user.id === targetUserId) return;
    
    Alert.alert(
      'Block User',
      `Block ${profileUser?.username}? They won't be able to find your profile, posts, or interact with you.`,
      [
        { text: 'Cancel', style: 'cancel' },
        { 
          text: 'Block', 
          style: 'destructive',
          onPress: async () => {
            try {
              await api.blockUser(targetUserId);
              setIsBlocked(true);
              Alert.alert('Blocked', `Blocked ${profileUser?.username}`);
            } catch (error) {
              Alert.alert('Error', 'Failed to block user');
            }
          }
        },
      ]
    );
  };

  const handleUnblockUser = async () => {
    try {
      await api.unblockUser(targetUserId);
      setIsBlocked(false);
      Alert.alert('Unblocked', `Unblocked ${profileUser?.username}`);
    } catch (error) {
      Alert.alert('Error', 'Failed to unblock user');
    }
  };

  const handleReportUser = async (reason) => {
    setShowReportModal(false);
    setReportingUser(true);
    try {
      await api.request('/reports/create/', {
        method: 'POST',
        body: JSON.stringify({
          reported_user_id: targetUserId,
          report_type: reason,
          description: `User reported as: ${reason}`,
          target_type: 'user',
        }),
      });
      Alert.alert('Success', 'Report submitted. Thank you for keeping the community safe.');
    } catch (err) {
      Alert.alert('Error', 'Failed to submit report. Please try again.');
    } finally {
      setReportingUser(false);
    }
  };

  const handleShareProfile = async () => {
    try {
      const profileUrl = `${config.WEB_BASE_URL}/profile/${profile?.username || targetUserId}`;
      
      await Share.share({
        message: `Check out ${profile?.username || 'this user'}'s profile on FlipStar!\n${profileUrl}`,
        url: profileUrl,
        title: `${profile?.username || 'User'} Profile - FlipStar`
      });
    } catch (error) {
      console.error('Share error:', error);
      Alert.alert('Share', 'Could not share profile. Please try again.');
    }
  };

  const handleEditBio = async () => {
    if (!isOwnProfile) return;
    try {
      setSavingProfile(true);
      // Use the dedicated update_profile endpoint so bio is saved on the profile model
      const saved = await api.request('/profile/update_profile/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bio: bioText }),
      });
      // Update profile state with the new bio
      setProfile(prev => ({ 
        ...prev, 
        bio: saved.bio || bioText,
        user: {
          ...(prev.user || {}),
          bio: saved.bio || bioText,
        }
      }));
      setEditingBio(false);
      Alert.alert('Success', 'Bio updated!');
    } catch (err) {
      console.error('Bio update error:', err);
      Alert.alert('Error', 'Failed to update bio. Please try again.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleEditProfile = async () => {
    if (!isOwnProfile) return;
    // Basic validation
    if (!editForm.username.trim()) {
      Alert.alert('Error', 'Username cannot be empty.');
      return;
    }
    try {
      setSavingProfile(true);
      // /profile/update_profile/ correctly saves both User fields (username, email,
      // first_name, last_name) AND the UserProfile bio field in one request.
      const saved = await api.request('/profile/update_profile/', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(editForm),
      });
      // saved = { id, username, email, first_name, last_name, bio, profile_photo }
      // Merge into the nested structure that the display reads from
      setProfile(prev => ({
        ...prev,
        bio: saved.bio ?? editForm.bio ?? prev.bio,
        profile_photo: saved.profile_photo ?? prev.profile_photo,
        username: saved.username ?? editForm.username ?? prev.username,
        user: {
          ...(prev.user || {}),
          username:   saved.username   ?? editForm.username   ?? prev.user?.username,
          email:      saved.email      ?? editForm.email      ?? prev.user?.email,
          first_name: saved.first_name ?? editForm.first_name ?? prev.user?.first_name,
          last_name:  saved.last_name  ?? editForm.last_name  ?? prev.user?.last_name,
        },
      }));
      setBioText(saved.bio ?? editForm.bio ?? '');
      setShowEditProfile(false);
      Alert.alert('Success', 'Profile updated successfully!');
    } catch (err) {
      Alert.alert('Error', err?.message || 'Failed to update profile. Please try again.');
    } finally {
      setSavingProfile(false);
    }
  };

  const handleDeletePost = async (postId) => {
    setConfirmDeleteId(null);
    setPostMenuId(null);
    
    // Optimistic UI: remove immediately; rollback on error
    const prevPosts = posts;
    setPosts(prev => prev.filter(p => p.id !== postId));
    setReels(prev => prev.filter(p => p.id !== postId));
    
    try {
      await api.deletePost(postId);
      setSuccessMessage('Post deleted successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
      // Refresh counts
      setPostsCount(prev => Math.max(0, prev - 1));
    } catch (error) {
      console.error('Failed to delete post:', error);
      // Rollback optimistic update
      setPosts(prevPosts);
      setReels(prevPosts.filter(p => p.media));
      Alert.alert('Error', 'Could not delete this post. Please try again.');
    }
  };

  const handleRemoveFromSaved = async (postId) => {
    setConfirmDeleteId(null);
    setPostMenuId(null);
    
    // Remove from saved posts immediately (no rollback needed)
    setSavedPosts(prev => prev.filter(p => p.id !== postId));
    
    // Try to call API but don't show errors to user
    try {
      await api.request(`/reels/${postId}/unsave/`, { method: 'POST' });
      setSuccessMessage('Removed from saved posts!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (error) {
      console.log('API unsave failed, but post removed from UI:', error);
      // Don't show error to user - just remove from UI
      setSuccessMessage('Removed from saved posts!');
      setTimeout(() => setSuccessMessage(''), 3000);
    }
  };

  const handleRequestDelete = (postId) => {
    setPostMenuId(null);
    setConfirmDeleteId(postId);
  };

  const handleEditPost = (post) => {
    setPostMenuId(null);
    setEditingPost(post);
    setEditCaption(post.caption || '');
    setEditHashtags(post.hashtags || '');
    setEditMediaFile(null);
    setEditMediaPreview(null);
  };

  const handleEditSave = async () => {
    if (!editingPost) return;
    
    // Validate inputs
    if (!editCaption.trim() && !editHashtags.trim()) {
      Alert.alert('Error', 'Please add a caption or hashtags');
      return;
    }
    
    setIsSaving(true);
    try {
      // For now, only update caption and hashtags (media update requires file picker)
      await api.updatePost(editingPost.id, { 
        caption: editCaption.trim(),
        hashtags: editHashtags.trim()
      });
      
      // Update local state
      setPosts(prev => prev.map(p => 
        p.id === editingPost.id 
          ? { ...p, caption: editCaption.trim(), hashtags: editHashtags.trim() }
          : p
      ));
      setReels(prev => prev.map(p => 
        p.id === editingPost.id 
          ? { ...p, caption: editCaption.trim(), hashtags: editHashtags.trim() }
          : p
      ));
      
      setEditingPost(null);
      setSuccessMessage('Post updated successfully!');
      setTimeout(() => setSuccessMessage(''), 3000);
    } catch (err) {
      console.error('Failed to update post:', err);
      Alert.alert('Error', 'Failed to update post. Please try again.');
    } finally {
      setIsSaving(false);
    }
  };

  const currentTabContent = useMemo(() => {
    switch (activeTab) {
      case 'posts': return posts;
      case 'reels': return reels;
      case 'saved': return savedPosts;
      case 'campaigns': return [];
      default: return posts;
    }
  }, [activeTab, posts, reels, savedPosts]);

  const renderPost = useCallback(({ item, index }) => {
    const isVideo = !!(item.media || '').match(/\.(mp4|webm|ogg|mov)/i) || (item.media && item.media.includes('/video/'));
    const thumbnail = item.thumbnail || item.image || item.media;
    
    console.log('ProfileScreen - renderPost item:', { id: item.id, media: item.media, thumbnail, isVideo });
    
    return (
      <View key={item.id} style={styles.gridItemWrapper}>
        <TouchableOpacity
          style={styles.gridItem}
          onPress={() => {
            console.log('ProfileScreen - Opening post with ID:', item.id, 'isVideo:', isVideo);
            if (isVideo) {
              // Videos go to ReelsDetail
              navigation.navigate('ReelsDetail', { initialVideoId: item.id });
            } else {
              // Images go to Home screen with post detail
              navigation.navigate('Home', { postId: item.id });
            }
          }}
          onLongPress={() => isOwnProfile && setPostMenuId(item.id)}
        >
          {thumbnail ? (
            <Image source={{ uri: mediaUrl(thumbnail) }} style={styles.gridImage} resizeMode="cover" />
          ) : (
            <View style={[styles.gridImage, styles.fallbackContainer]}>
              <Ionicons name={isVideo ? 'play' : 'image'} size={28} color={colors.textSecondary} />
            </View>
          )}
          
          {isVideo && (
            <View style={styles.videoIcon}>
              <Ionicons name="play" size={9} color="#fff" />
            </View>
          )}
          
          {/* Options button for own posts */}
          {isOwnProfile && (
            <TouchableOpacity
              style={styles.postOptionsBtn}
              onPress={() => setPostMenuId(item.id)}
            >
              <Ionicons name="ellipsis-vertical" size={16} color="#fff" />
            </TouchableOpacity>
          )}
        </TouchableOpacity>
      </View>
    );
  }, [navigation, isOwnProfile]);

  if (loading) {
    return (
      <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
        <StatusBar barStyle={colors.statusBarStyle} backgroundColor={colors.bg} />
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading profile...</Text>
        </View>
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      <StatusBar barStyle={colors.statusBarStyle} backgroundColor={colors.bg} />
      
      {/* Success Toast */}
      {successMessage && (
        <View style={styles.successToast}>
          <Text style={[styles.successToastText, { color: '#fff' }]}>{successMessage}</Text>
        </View>
      )}
      
      {/* Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.primary} />
        </TouchableOpacity>
        <View style={styles.headerSpacer} />
        {isOwnProfile && (
          <View style={styles.headerActions}>
            <TouchableOpacity onPress={() => navigation.navigate('CoinPurchase')} style={styles.headerButton}>
              <Ionicons name="star" size={24} color={colors.primary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => navigation.navigate('Wallet')} style={styles.headerButton}>
              <Ionicons name="wallet-outline" size={24} color={colors.primary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => navigation.navigate('Subscription')} style={styles.headerButton}>
              <Ionicons name="ribbon" size={24} color={colors.primary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => navigation.navigate('Gamification')} style={styles.headerButton}>
              <Ionicons name="game-controller-outline" size={24} color={colors.primary} />
            </TouchableOpacity>
            <TouchableOpacity onPress={() => navigation.navigate('Settings')} style={styles.headerButton}>
              <Ionicons name="settings-outline" size={24} color={colors.primary} />
            </TouchableOpacity>
          </View>
        )}
      </View>

      <ScrollView 
        style={[styles.content, { backgroundColor: colors.bg }]} 
        showsVerticalScrollIndicator={false}
        scrollEventThrottle={16}
        nestedScrollEnabled={false}
        refreshControl={
          <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
        }
      >
        {/* Profile Header */}
        <View style={[styles.profileHeader, { backgroundColor: colors.cardBg }]}>
          <View style={styles.profileInfo}>
            <View style={styles.avatarContainer}>
              {profile?.profile_photo ? (
                <TouchableOpacity onPress={() => setShowProfileZoom(true)}>
                  <Image 
                    source={{ uri: mediaUrl(profile.profile_photo) }} 
                    style={styles.avatar}
                  />
                </TouchableOpacity>
              ) : (
                <View style={[styles.avatar, styles.avatarPlaceholder, { backgroundColor: colors.border }]}>
                  <Text style={styles.avatarText}>👤</Text>
                </View>
              )}
            </View>
            
            <View style={styles.statsContainer}>
              <View style={styles.statItem}>
                <Text style={[styles.statNumber, { color: colors.text }]}>{postsCount}</Text>
                <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Posts</Text>
              </View>
              <TouchableOpacity 
                onPress={() => navigation.navigate('FollowList', { userId: targetUserId, type: 'followers' })}
                style={styles.statItem}
              >
                <Text style={[styles.statNumber, { color: colors.text }]}>{followersCount}</Text>
                <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Followers</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                onPress={() => navigation.navigate('FollowList', { userId: targetUserId, type: 'following' })}
                style={styles.statItem}
              >
                <Text style={[styles.statNumber, { color: colors.text }]}>{followingCount}</Text>
                <Text style={[styles.statLabel, { color: colors.textSecondary }]}>Following</Text>
              </TouchableOpacity>
            </View>
          </View>
          
          <View style={styles.profileDetails}>
            <Text style={[styles.profileName, { color: colors.text }]}>
              {(profile?.user?.first_name || profile?.first_name)} {(profile?.user?.last_name || profile?.last_name)}
            </Text>
            <Text style={[styles.profileUsername, { color: '#fff' }]}>@{profile?.username || profile?.user?.username}</Text>
            
            {/* Phone Number - Only show in own profile */}
            {isOwnProfile && (
              <View style={[styles.phoneContainer, { backgroundColor: colors.cardBg, borderColor: colors.border, borderWidth: 1, borderRadius: 8, paddingHorizontal: 12, paddingVertical: 6, marginTop: 4 }]}>
                <Text style={[styles.phoneNumber, { color: colors.primary }]}>
                  {formatPhoneNumber(profile?.user?.phone_number || profile?.phone_number || 'No phone number')}
                </Text>
              </View>
            )}
            
            {isOwnProfile && editingBio ? (
              <View style={styles.bioEditContainer}>
                <TextInput
                  style={[styles.bioInput, { color: colors.text, backgroundColor: colors.bg, borderColor: colors.border }]}
                  value={bioText}
                  onChangeText={setBioText}
                  placeholder="Add a bio..."
                  placeholderTextColor={colors.textSecondary}
                  multiline
                  maxLength={200}
                />
                <View style={styles.bioEditActions}>
                  <TouchableOpacity 
                    onPress={() => setEditingBio(false)} 
                    style={styles.bioCancelButton}
                  >
                    <Text style={styles.bioCancelText}>Cancel</Text>
                  </TouchableOpacity>
                  <TouchableOpacity 
                    onPress={handleEditBio} 
                    disabled={savingProfile}
                    style={[styles.bioSaveButton, savingProfile && styles.bioSaveButtonDisabled]}
                  >
                    <Text style={styles.bioSaveText}>
                      {savingProfile ? 'Saving...' : 'Save'}
                    </Text>
                  </TouchableOpacity>
                </View>
              </View>
            ) : (
              <TouchableOpacity onPress={() => isOwnProfile && setEditingBio(true)}>
                {profile?.bio ? (
                  <Text style={styles.profileBio}>{profile.bio}</Text>
                ) : (
                  isOwnProfile && (
                    <Text style={styles.addBioText}>Add a bio...</Text>
                  )
                )}
              </TouchableOpacity>
            )}
          </View>
          
          {/* Edit Profile Button for Own Profile */}
          {isOwnProfile && (
            <TouchableOpacity 
              onPress={() => navigation.navigate('EditProfile')}
              style={styles.editProfileButton}
            >
              <Ionicons name="create-outline" size={16} color={colors.primary} />
              <Text style={styles.editProfileButtonText}>Edit Profile</Text>
            </TouchableOpacity>
          )}
          
          {/* Action Buttons for Other Profiles */}
          {!isOwnProfile && (
            <View style={styles.actionButtons}>
              <TouchableOpacity 
                onPress={toggleFollow}
                style={[
                  styles.followButton,
                  isFollowing && styles.followingButton
                ]}
              >
                <Ionicons 
                  name={isFollowing ? "checkmark" : "add"} 
                  size={18} 
                  color={isFollowing ? colors.primary : colors.text} 
                />
                <Text style={[
                  styles.followButtonText,
                  isFollowing && styles.followingButtonText
                ]}>
                  {isFollowing ? 'Following' : 'Follow'}
                </Text>
              </TouchableOpacity>
              
              <TouchableOpacity onPress={handleShareProfile} style={styles.actionButton}>
                <Ionicons name="share-outline" size={18} color={colors.primary} />
              </TouchableOpacity>
              
              {!isBlocked ? (
                <TouchableOpacity 
                  onPress={handleBlockUser} 
                  style={styles.actionButton}
                >
                  <Ionicons name="person-remove-outline" size={18} color={colors.error} />
                </TouchableOpacity>
              ) : (
                <TouchableOpacity 
                  onPress={handleUnblockUser} 
                  style={styles.actionButton}
                >
                  <Ionicons name="person-add-outline" size={18} color={colors.primary} />
                </TouchableOpacity>
              )}
              
              <TouchableOpacity 
                onPress={() => setShowReportModal(true)} 
                disabled={reportingUser}
                style={styles.actionButton}
              >
                <Ionicons name="flag-outline" size={18} color={colors.error} />
              </TouchableOpacity>
            </View>
          )}
        </View>

        {/* Tabs */}
        <View style={[styles.tabs, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
          {[
            { id: 'posts', icon: 'grid-outline', label: 'Posts' },
            { id: 'reels', icon: 'film-outline', label: 'Reels' },
            { id: 'saved', icon: 'bookmark-outline', label: 'Saved' },
            { id: 'campaigns', icon: 'trophy-outline', label: 'Campaigns' },
          ]
            .filter(tab => isOwnProfile || tab.id !== 'saved')
            .map((tab) => (
              <TouchableOpacity
                key={tab.id}
                onPress={() => setActiveTab(tab.id)}
                style={[
                  styles.tab,
                  activeTab === tab.id && { backgroundColor: colors.primary + '20' }
                ]}
              >
                <Ionicons 
                  name={tab.icon} 
                  size={22} 
                  color={activeTab === tab.id ? colors.primary : colors.text} 
                />
                <Text style={[
                  styles.tabLabel,
                  { color: colors.textSecondary },
                  activeTab === tab.id && { color: colors.primary, fontWeight: '700' }
                ]}>
                  {tab.label}
                </Text>
              </TouchableOpacity>
            ))}
        </View>

        {/* Campaign Stats Content */}
        {activeTab === 'campaigns' && (
          <View style={[styles.campaignsContent, { backgroundColor: colors.cardBg }]}>
            {!campaignStats ? (
              <View style={styles.loadingContainer}>
                <ActivityIndicator size="large" color={colors.primary} />
                <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading campaign stats...</Text>
              </View>
            ) : !campaignStats.campaigns || campaignStats.campaigns.length === 0 ? (
              <View style={styles.emptyCampaigns}>
                <Ionicons name="trophy-outline" size={48} color={colors.textSecondary} />
                <Text style={[styles.emptyCampaignsTitle, { color: colors.text }]}>No campaigns yet</Text>
                <Text style={[styles.emptyCampaignsText, { color: colors.textSecondary }]}>Join a campaign to see your stats here!</Text>
              </View>
            ) : (
              <View>
                {/* Header */}
                <View style={[styles.campaignHeader, { borderBottomColor: colors.border }]}>
                  <Ionicons name="trophy" size={22} color={colors.primary} />
                  <Text style={[styles.campaignTitle, { color: colors.text }]}>Campaign Achievements</Text>
                </View>

                
                {/* Campaign List */}
                <View style={[styles.campaignList, { backgroundColor: colors.cardBg }]}>
                  <Text style={[styles.campaignListTitle, { color: colors.text }]}>Active Campaigns</Text>
                  {campaignStats.campaigns.map((campaign) => (
                    <View key={campaign.campaign_id} style={[styles.campaignItem, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                      <Text style={[styles.campaignName, { color: colors.text }]}>{campaign.campaign_title}</Text>
                    </View>
                  ))}
                </View>

                {/* Badges */}
                {campaignStats.badges && campaignStats.badges.length > 0 && (
                  <View style={[styles.badgesSection, { backgroundColor: colors.cardBg }]}>
                    <Text style={[styles.badgesTitle, { color: colors.text }]}>Badges Earned</Text>
                    <View style={styles.badgesList}>
                      {campaignStats.badges.map((badge) => (
                        <View key={`badge-${badge.title}-${badge.id || Math.random()}`} style={[styles.badgeItem, { backgroundColor: colors.bg, borderColor: colors.border }]}>
                          <Ionicons name="award" size={13} color={colors.primary} />
                          <Text style={[styles.badgeText, { color: colors.text }]}>{badge.title}</Text>
                        </View>
                      ))}
                    </View>
                  </View>
                )}
              </View>
            )}
          </View>
        )}

        {/* Posts Grid */}
        {activeTab !== 'campaigns' && (
          <View style={styles.postsGrid}>
            {currentTabContent.length === 0 ? (
              <View style={[styles.emptyState, { backgroundColor: colors.cardBg }]}>
                <Ionicons 
                  name={
                    activeTab === 'posts' ? 'grid-outline' : 
                    activeTab === 'reels' ? 'film-outline' : 
                    'bookmark-outline'
                  } 
                  size={48} 
                  color={colors.textSecondary} 
                />
                <Text style={[styles.emptyText, { color: colors.textSecondary }]}>
                  {activeTab === 'posts' ? 'No posts yet' : 
                   activeTab === 'reels' ? 'No reels yet' : 
                   'No saved posts yet'}
                </Text>
              </View>
            ) : (
              <FlatList
                data={currentTabContent}
                renderItem={renderPost}
                keyExtractor={(item, index) => `${activeTab}-${item.id}-${index}`}
                numColumns={3}
                scrollEnabled={false}
                columnWrapperStyle={styles.gridRow}
                removeClippedSubviews={true}
                maxToRenderPerBatch={9}
                windowSize={5}
                initialNumToRender={9}
              />
            )}
          </View>
        )}
      </ScrollView>

      {/* Profile Zoom Modal */}
      <Modal
        visible={showProfileZoom}
        transparent={true}
        onRequestClose={() => setShowProfileZoom(false)}
      >
        <TouchableOpacity 
          style={styles.modalOverlay} 
          activeOpacity={1}
          onPress={() => setShowProfileZoom(false)}
        >
          {profile?.profile_photo && (
            <Image 
              source={{ uri: mediaUrl(profile.profile_photo) }} 
              style={styles.zoomedImage}
              resizeMode="contain"
            />
          )}
        </TouchableOpacity>
      </Modal>

      {/* Edit Profile Modal */}
      <Modal
        visible={showEditProfile}
        transparent={true}
        animationType="fade"
        onRequestClose={() => setShowEditProfile(false)}
      >
        <TouchableOpacity 
          style={styles.modalOverlay} 
          activeOpacity={1}
          onPress={() => setShowEditProfile(false)}
        >
          <TouchableOpacity 
            style={styles.editProfileModal} 
            activeOpacity={1}
            onPress={(e) => e.stopPropagation()}
          >
            <View style={styles.editProfileHeader}>
              <Text style={styles.editProfileTitle}>Edit Profile</Text>
              <TouchableOpacity onPress={() => setShowEditProfile(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.editProfileContent} showsVerticalScrollIndicator={false}>
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>First Name</Text>
                <TextInput
                  style={styles.input}
                  value={editForm.first_name}
                  onChangeText={(text) => setEditForm(prev => ({ ...prev, first_name: text }))}
                  placeholder="First name"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
              
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Last Name</Text>
                <TextInput
                  style={styles.input}
                  value={editForm.last_name}
                  onChangeText={(text) => setEditForm(prev => ({ ...prev, last_name: text }))}
                  placeholder="Last name"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
              
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Username</Text>
                <TextInput
                  style={styles.input}
                  value={editForm.username}
                  onChangeText={(text) => setEditForm(prev => ({ ...prev, username: text }))}
                  placeholder="Username"
                  placeholderTextColor={colors.textSecondary}
                  autoCapitalize="none"
                />
              </View>
              
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Email</Text>
                <TextInput
                  style={styles.input}
                  value={editForm.email}
                  onChangeText={(text) => setEditForm(prev => ({ ...prev, email: text }))}
                  placeholder="Email"
                  placeholderTextColor={colors.textSecondary}
                  keyboardType="email-address"
                  autoCapitalize="none"
                />
              </View>
              
              <View style={styles.inputGroup}>
                <Text style={styles.inputLabel}>Bio</Text>
                <TextInput
                  style={[styles.input, styles.bioInput]}
                  value={editForm.bio}
                  onChangeText={(text) => setEditForm(prev => ({ ...prev, bio: text }))}
                  placeholder="Tell us about yourself..."
                  placeholderTextColor={colors.textSecondary}
                  multiline
                  maxLength={200}
                />
              </View>
            </ScrollView>
            
            <View style={styles.editProfileActions}>
              <TouchableOpacity 
                onPress={() => setShowEditProfile(false)} 
                style={styles.cancelButton}
              >
                <Text style={styles.cancelButtonText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity 
                onPress={handleEditProfile} 
                disabled={savingProfile}
                style={[styles.saveButton, savingProfile && styles.saveButtonDisabled]}
              >
                <Text style={styles.saveButtonText}>
                  {savingProfile ? 'Saving...' : 'Save'}
                </Text>
              </TouchableOpacity>
            </View>
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
      <Modal
        visible={showReportModal}
        transparent={true}
        animationType="slide"
        onRequestClose={() => setShowReportModal(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={styles.reportModal}>
            <View style={styles.reportHeader}>
              <Text style={styles.reportTitle}>Report User</Text>
              <TouchableOpacity onPress={() => setShowReportModal(false)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            
            <ScrollView style={styles.reportReasons}>
              {REPORT_REASONS.map((reason) => (
                <TouchableOpacity
                  key={reason.id}
                  onPress={() => handleReportUser(reason.id)}
                  style={styles.reportReason}
                >
                  <Text style={styles.reportEmoji}>{reason.emoji}</Text>
                  <Text style={styles.reportReasonText}>{reason.label}</Text>
                </TouchableOpacity>
              ))}
            </ScrollView>
          </View>
        </View>
      </Modal>

      {/* Post Options Menu */}
      {postMenuId && (
        <Modal
          visible={true}
          transparent={true}
          animationType="fade"
          onRequestClose={() => setPostMenuId(null)}
        >
          <TouchableOpacity 
            style={styles.modalOverlay} 
            activeOpacity={1} 
            onPress={() => setPostMenuId(null)}
          >
            <View style={styles.postMenuSheet}>
              <View style={styles.sheetHandle} />
              
              {/* Show different options based on active tab */}
              {activeTab === 'saved' ? (
                // Saved posts: only show "Remove from Saved" option
                <TouchableOpacity
                  onPress={() => handleRequestDelete(postMenuId)}
                  style={[styles.postMenuOption, styles.postMenuDanger]}
                >
                  <Ionicons name="bookmark-outline" size={20} color="#ff4444" />
                  <Text style={[styles.postMenuText, styles.postMenuDangerText]}>Remove from Saved</Text>
                </TouchableOpacity>
              ) : (
                // Regular posts: show Edit and Delete options
                <>
                  <TouchableOpacity
                    onPress={() => {
                      const post = posts.find(p => p.id === postMenuId);
                      if (post) handleEditPost(post);
                    }}
                    style={styles.postMenuOption}
                  >
                    <Ionicons name="create-outline" size={20} color={GOLD} />
                    <Text style={styles.postMenuText}>Edit Post</Text>
                  </TouchableOpacity>
                  <TouchableOpacity
                    onPress={() => handleRequestDelete(postMenuId)}
                    style={[styles.postMenuOption, styles.postMenuDanger]}
                  >
                    <Ionicons name="trash-outline" size={20} color="#ff4444" />
                    <Text style={[styles.postMenuText, styles.postMenuDangerText]}>Delete Post</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          </TouchableOpacity>
        </Modal>
      )}

      {/* Edit Post Modal */}
      {editingPost && (
        <Modal
          visible={true}
          animationType="slide"
          onRequestClose={() => setEditingPost(null)}
        >
          <View style={[styles.editPostModal, { paddingTop: insets.top }]}>
            <StatusBar barStyle="light-content" backgroundColor={BG} />
            
            <View style={styles.editPostHeader}>
              <TouchableOpacity onPress={() => setEditingPost(null)}>
                <Ionicons name="close" size={28} color={GOLD} />
              </TouchableOpacity>
              <Text style={styles.editPostTitle}>Edit Post</Text>
              <TouchableOpacity 
                onPress={handleEditSave} 
                disabled={isSaving}
                style={{ opacity: isSaving ? 0.5 : 1 }}
              >
                <Text style={styles.editPostSaveBtn}>
                  {isSaving ? 'Saving...' : 'Save'}
                </Text>
              </TouchableOpacity>
            </View>

            <ScrollView style={styles.editPostContent} showsVerticalScrollIndicator={false}>
              {/* Media Preview */}
              {(editingPost.thumbnail || editingPost.media || editingPost.image) && (
                <View style={styles.editMediaPreview}>
                  {editingPost.thumbnail ? (
                    <View style={styles.videoPreviewContainer}>
                      <Image 
                        source={{ uri: mediaUrl(editingPost.thumbnail) }} 
                        style={styles.editMediaImage}
                        resizeMode="cover"
                      />
                      {editingPost.media && (
                        <View style={styles.videoOverlay}>
                          <Ionicons name="play-circle" size={64} color="rgba(255,255,255,0.9)" />
                        </View>
                      )}
                    </View>
                  ) : editingPost.media ? (
                    <View style={styles.videoPreviewContainer}>
                      <Image 
                        source={{ uri: mediaUrl(editingPost.image) }} 
                        style={styles.editMediaImage}
                        resizeMode="cover"
                      />
                      <View style={styles.videoOverlay}>
                        <Ionicons name="play-circle" size={64} color="rgba(255,255,255,0.9)" />
                      </View>
                    </View>
                  ) : (
                    <Image 
                      source={{ uri: mediaUrl(editingPost.image) }} 
                      style={styles.editMediaImage}
                      resizeMode="cover"
                    />
                  )}
                </View>
              )}

              {/* Caption Input */}
              <View style={styles.editInputGroup}>
                <Text style={styles.editInputLabel}>Caption</Text>
                <TextInput
                  style={[styles.editInput, styles.editCaptionInput]}
                  value={editCaption}
                  onChangeText={setEditCaption}
                  placeholder="Write a caption..."
                  placeholderTextColor={colors.textSecondary}
                  multiline
                  maxLength={500}
                />
                <Text style={styles.charCount}>{editCaption.length}/500</Text>
              </View>

              {/* Hashtags Input */}
              <View style={styles.editInputGroup}>
                <Text style={styles.editInputLabel}>Hashtags</Text>
                <TextInput
                  style={styles.editInput}
                  value={editHashtags}
                  onChangeText={setEditHashtags}
                  placeholder="#hashtag1 #hashtag2"
                  placeholderTextColor={colors.textSecondary}
                />
              </View>
            </ScrollView>
          </View>
        </Modal>
      )}

      {/* Delete Confirmation Modal */}
      {confirmDeleteId && (
        <Modal
          visible={true}
          transparent={true}
          animationType="fade"
          onRequestClose={() => setConfirmDeleteId(null)}
        >
          <View style={styles.modalOverlay}>
            <View style={styles.deleteConfirmModal}>
              <View style={styles.deleteModalHeader}>
                <Ionicons name={activeTab === 'saved' ? "bookmark-outline" : "trash-outline"} size={24} color="#ff4444" />
                <Text style={styles.deleteModalTitle}>
                  {activeTab === 'saved' ? 'Remove from Saved' : 'Delete Post'}
                </Text>
              </View>
              <Text style={styles.deleteModalMessage}>
                {activeTab === 'saved' 
                  ? 'Are you sure you want to remove this post from your saved posts?'
                  : 'Are you sure you want to delete this post? This action cannot be undone.'
                }
              </Text>
              
              <View style={styles.deleteActions}>
                <TouchableOpacity 
                  onPress={() => setConfirmDeleteId(null)} 
                  style={styles.deleteCancelButton}
                >
                  <Text style={styles.deleteCancelButtonText}>Cancel</Text>
                </TouchableOpacity>
                <TouchableOpacity 
                  onPress={() => activeTab === 'saved' ? handleRemoveFromSaved(confirmDeleteId) : handleDeletePost(confirmDeleteId)} 
                  style={styles.deleteConfirmButton}
                >
                  <Text style={styles.deleteConfirmButtonText}>
                    {activeTab === 'saved' ? 'Remove' : 'Delete'}
                  </Text>
                </TouchableOpacity>
              </View>
            </View>
          </View>
        </Modal>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: BG,
  },
  successToast: {
    position: 'absolute',
    top: 10,
    left: 20,
    right: 20,
    backgroundColor: '#10b981',
    borderRadius: 12,
    padding: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    zIndex: 9999,
    elevation: 10,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
  },
  successToastText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
    flex: 1,
  },
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  backButton: {
    padding: 4,
  },
  headerSpacer: {
    flex: 1,
  },
  headerActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  headerButton: {
    padding: 8,
  },
  content: {
    flex: 1,
  },
  profileHeader: {
    padding: 20,
  },
  profileInfo: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 20,
    marginBottom: 20,
  },
  avatarContainer: {
    position: 'relative',
    flexShrink: 0,
  },
  avatar: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: CARD,
    borderWidth: 2,
    borderColor: GOLD,
  },
  avatarPlaceholder: {
    backgroundColor: GOLD + '30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 32,
  },
  statsContainer: {
    flexDirection: 'row',
    gap: 20,
    flex: 1,
  },
  statItem: {
    alignItems: 'center',
    flex: 1,
  },
  statNumber: {
    fontSize: 18,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  statLabel: {
    fontSize: 13,
    color: LIGHT_GOLD,
    marginTop: 2,
  },
  profileDetails: {
    marginBottom: 16,
  },
  profileName: {
    fontSize: 15,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 4,
  },
  profileUsername: {
    fontSize: 14,
    color: '#fff',
    marginBottom: 8,
  },
  phoneContainer: {
    marginBottom: 8,
    paddingHorizontal: 12,
    paddingVertical: 6,
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 8,
    alignSelf: 'flex-start',
    borderWidth: 1,
    borderColor: GOLD,
  },
  phoneNumber: {
    fontSize: 14,
    color: '#fff',
    fontWeight: '500',
  },
  profileBio: {
    fontSize: 14,
    color: '#fff',
    lineHeight: 20,
  },
  addBioText: {
    fontSize: 14,
    color: '#666',
    fontStyle: 'italic',
  },
  bioEditContainer: {
    marginTop: 8,
  },
  bioInput: {
    backgroundColor: CARD,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 8,
    padding: 12,
    color: '#fff',
    fontSize: 14,
    minHeight: 80,
    textAlignVertical: 'top',
  },
  bioEditActions: {
    flexDirection: 'row',
    gap: 8,
    marginTop: 8,
  },
  bioCancelButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: BORDER,
  },
  bioCancelText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  bioSaveButton: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderRadius: 6,
    backgroundColor: GOLD,
  },
  bioSaveButtonDisabled: {
    backgroundColor: '#444',
  },
  bioSaveText: {
    color: '#000',
    fontSize: 14,
    fontWeight: '600',
  },
  editProfileButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    width: '100%',
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: GOLD,
    backgroundColor: 'transparent',
  },
  editProfileButtonText: {
    color: GOLD,
    fontSize: 14,
    fontWeight: '700',
  },
  actionButtons: {
    flexDirection: 'row',
    gap: 8,
    alignItems: 'center',
  },
  followButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: GOLD,
  },
  followingButton: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: BORDER,
  },
  followButtonText: {
    fontSize: 14,
    fontWeight: '700',
    color: '#000',
  },
  followingButtonText: {
    color: LIGHT_GOLD,
  },
  actionButton: {
    padding: 10,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 8,
    backgroundColor: CARD,
  },
  tabs: {
    flexDirection: 'row',
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: BORDER,
  },
  tab: {
    flex: 1,
    paddingVertical: 12,
    alignItems: 'center',
  },
  activeTab: {
    borderTopWidth: 2,
    borderTopColor: GOLD,
  },
  tabLabel: {
    fontSize: 10,
    fontWeight: '400',
    color: '#fff',
    marginTop: 2,
    letterSpacing: 0.3,
  },
  activeTabLabel: {
    fontWeight: '700',
    color: GOLD,
  },
  postsGrid: {
    flex: 1,
  },
  gridContainer: {
    paddingHorizontal: 1,
  },
  gridRow: {
    justifyContent: 'flex-start',
    gap: 2,
    paddingHorizontal: 1,
  },
  gridItemWrapper: {
    width: (width - 6) / 3,
    marginBottom: 2,
  },
  gridItem: {
    width: '100%',
    aspectRatio: 9 / 16,
    backgroundColor: CARD,
    borderRadius: 4,
    overflow: 'hidden',
    borderWidth: 1.5,
    borderColor: GOLD,
  },
  heroItem: {
    width: width - 32,
    height: (width - 32) * 0.56,
    marginHorizontal: 16,
    marginTop: 16,
  },
  gridImage: {
    width: '100%',
    height: '100%',
  },
  fallbackContainer: {
    backgroundColor: '#222',
    justifyContent: 'center',
    alignItems: 'center',
  },
  videoIcon: {
    position: 'absolute',
    top: 7,
    left: 7,
    backgroundColor: 'rgba(0,0,0,0.58)',
    borderRadius: 4,
    padding: '2px 5px',
  },
  postOptionsBtn: {
    position: 'absolute',
    top: 4,
    right: 4,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: 12,
    width: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyState: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyText: {
    color: '#666',
    fontSize: 16,
    marginTop: 12,
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.8)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  zoomedImage: {
    width: width * 0.8,
    height: width * 0.8,
    borderRadius: 20,
  },
  reportModal: {
    backgroundColor: CARD,
    width: width * 0.9,
    maxHeight: height * 0.7,
    borderRadius: 20,
  },
  reportHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  reportTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  reportReasons: {
    flex: 1,
    padding: 20,
  },
  reportReason: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  reportEmoji: {
    fontSize: 20,
  },
  reportReasonText: {
    fontSize: 16,
    color: LIGHT_GOLD,
    flex: 1,
  },
  // Edit Profile Modal Styles
  editProfileModal: {
    backgroundColor: CARD,
    width: width * 0.9,
    maxHeight: height * 0.85,
    borderRadius: 20,
  },
  editProfileHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  editProfileTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  editProfileContent: {
    flex: 1,
    padding: 20,
    paddingBottom: 0,
  },
  inputGroup: {
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: LIGHT_GOLD,
    marginBottom: 8,
  },
  input: {
    backgroundColor: BG,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 10,
    padding: 14,
    color: '#fff',
    fontSize: 16,
  },
  editProfileActions: {
    flexDirection: 'row',
    gap: 12,
    padding: 20,
    paddingTop: 16,
    borderTopWidth: 1,
    borderTopColor: BORDER,
  },
  cancelButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: 'transparent',
    borderWidth: 1.5,
    borderColor: BORDER,
    alignItems: 'center',
  },
  cancelButtonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '700',
  },
  saveButton: {
    flex: 1,
    paddingVertical: 14,
    borderRadius: 10,
    backgroundColor: GOLD,
    alignItems: 'center',
  },
  saveButtonDisabled: {
    backgroundColor: '#444',
  },
  saveButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
  // Campaign Stats Styles
  campaignsContent: {
    padding: 20,
  },
  loadingText: {
    color: '#666',
    fontSize: 14,
    marginTop: 8,
    textAlign: 'center',
  },
  emptyCampaigns: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 60,
  },
  emptyCampaignsTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: LIGHT_GOLD,
    marginTop: 12,
    marginBottom: 6,
  },
  emptyCampaignsText: {
    fontSize: 13,
    color: '#666',
    textAlign: 'center',
  },
  campaignHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    marginBottom: 20,
  },
  campaignTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: LIGHT_GOLD,
  },
  statsGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 12,
    marginBottom: 24,
  },
  statCard: {
    backgroundColor: CARD,
    borderWidth: 1.5,
    borderColor: BORDER,
    borderRadius: 14,
    padding: 16,
    alignItems: 'center',
    width: (width - 40) / 2 - 6,
  },
  statValue: {
    fontSize: 22,
    fontWeight: '800',
    color: LIGHT_GOLD,
    marginTop: 8,
    marginBottom: 4,
  },
  campaignList: {
    marginBottom: 24,
  },
  campaignListTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 12,
  },
  campaignItem: {
    backgroundColor: CARD,
    borderWidth: 1.5,
    borderColor: BORDER,
    borderRadius: 14,
    padding: 14,
    marginBottom: 10,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  campaignInfo: {
    flex: 1,
  },
  campaignName: {
    fontSize: 14,
    fontWeight: '700',
    color: LIGHT_GOLD,
    marginBottom: 3,
  },
  campaignDetails: {
    fontSize: 12,
    color: '#666',
  },
  campaignScore: {
    backgroundColor: `${GOLD}18`,
    borderWidth: 1.5,
    borderColor: `${GOLD}40`,
    padding: 6,
    paddingHorizontal: 14,
    borderRadius: 20,
  },
  campaignScoreText: {
    fontSize: 13,
    fontWeight: '700',
    color: GOLD,
  },
  badgesSection: {
    marginTop: 20,
  },
  badgesTitle: {
    fontSize: 13,
    fontWeight: '700',
    color: '#666',
    textTransform: 'uppercase',
    letterSpacing: 0.8,
    marginBottom: 12,
  },
  badgesList: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  badgeItem: {
    backgroundColor: `${GOLD}15`,
    borderWidth: 1.5,
    borderColor: `${GOLD}35`,
    padding: 6,
    paddingHorizontal: 12,
    borderRadius: 20,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '700',
    color: GOLD,
  },
  // Post Menu Styles
  postMenuSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
  },
  sheetHandle: {
    width: 36,
    height: 4,
    backgroundColor: '#444',
    borderRadius: 2,
    alignSelf: 'center',
    marginBottom: 20,
  },
  postMenuOption: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingVertical: 16,
    paddingHorizontal: 20,
    borderRadius: 12,
    backgroundColor: BG,
    marginBottom: 8,
  },
  postMenuDanger: {
    backgroundColor: '#2a1515',
  },
  postMenuText: {
    fontSize: 16,
    fontWeight: '600',
    color: GOLD,
  },
  postMenuDangerText: {
    color: '#ff4444',
  },
  // Edit Post Modal Styles
  editPostModal: {
    flex: 1,
    backgroundColor: BG,
  },
  editPostHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: 20,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  editPostTitle: {
    fontSize: 20,
    fontWeight: '700',
    color: GOLD,
  },
  editPostContent: {
    flex: 1,
    padding: 20,
  },
  editMediaPreview: {
    marginBottom: 20,
    borderRadius: 12,
    overflow: 'hidden',
  },
  videoPreviewContainer: {
    position: 'relative',
  },
  editMediaImage: {
    width: '100%',
    height: 300,
    backgroundColor: '#222',
    borderRadius: 12,
  },
  videoOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  editInputGroup: {
    marginBottom: 16,
  },
  editInputLabel: {
    fontSize: 14,
    fontWeight: '600',
    color: GOLD,
    marginBottom: 8,
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  editInput: {
    backgroundColor: BG,
    borderWidth: 1.5,
    borderColor: GOLD + '40',
    borderRadius: 12,
    padding: 14,
    fontSize: 15,
    color: '#fff',
    fontWeight: '400',
  },
  editCaptionInput: {
    minHeight: 150,
    textAlignVertical: 'top',
  },
  charCount: {
    fontSize: 12,
    color: '#666',
    textAlign: 'right',
    marginTop: 4,
  },
  editPostSaveBtn: {
    fontSize: 16,
    fontWeight: '700',
    color: GOLD,
  },
  editPostActions: {
    flexDirection: 'row',
    gap: 12,
    padding: 20,
    borderTopWidth: 1,
    borderTopColor: BORDER,
  },
  editCancelButton: {
    flex: 1,
    padding: 14,
    borderRadius: 12,
    backgroundColor: BG,
    alignItems: 'center',
  },
  editCancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#999',
  },
  editSaveButton: {
    flex: 1,
    padding: 14,
    borderRadius: 12,
    backgroundColor: GOLD,
    alignItems: 'center',
  },
  editSaveButtonDisabled: {
    opacity: 0.5,
  },
  editSaveButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#000',
  },
  // Delete Confirmation Modal Styles
  deleteConfirmModal: {
    backgroundColor: CARD,
    borderRadius: 20,
    marginHorizontal: 40,
    padding: 30,
    alignItems: 'center',
  },
  deleteIconContainer: {
    width: 80,
    height: 80,
    borderRadius: 40,
    backgroundColor: '#2a1515',
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 20,
  },
  deleteTitle: {
    fontSize: 22,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 12,
  },
  deleteMessage: {
    fontSize: 15,
    color: '#999',
    textAlign: 'center',
    lineHeight: 22,
    marginBottom: 24,
  },
  deleteActions: {
    flexDirection: 'row',
    gap: 12,
    width: '100%',
  },
  deleteCancelButton: {
    flex: 1,
    padding: 14,
    borderRadius: 12,
    backgroundColor: BG,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: BORDER,
  },
  deleteCancelButtonText: {
    fontSize: 16,
    fontWeight: '600',
    color: '#fff',
  },
  deleteConfirmButton: {
    flex: 1,
    padding: 14,
    borderRadius: 12,
    backgroundColor: '#ff4444',
    alignItems: 'center',
  },
  deleteConfirmButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
});
