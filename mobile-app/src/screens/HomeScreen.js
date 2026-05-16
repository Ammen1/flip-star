import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image, FlatList,
  ActivityIndicator, ScrollView, Dimensions, Alert, RefreshControl,
  StatusBar, Modal, TextInput, Share, KeyboardAvoidingView, Platform,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useBlock } from '../contexts/BlockContext';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import config from '../config';
import SoundManager from '../utils/SoundUtils';
import AsyncStorage from '@react-native-async-storage/async-storage';
import Avatar from '../components/Avatar';
import UserSuggestions from '../components/UserSuggestions';
import HorizontalUserSuggestions from '../components/HorizontalUserSuggestions';

const { width, height } = Dimensions.get('window');
const GOLD = '#8fc441';
const LIGHT_GOLD = '#F9E08B';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const TABS = ['For You', 'Explore', 'Campaigns'];

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = (Date.now() - new Date(dateStr)) / 1000;
  if (diff < 60) return `${Math.floor(diff)}s`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h`;
  return `${Math.floor(diff / 86400)}d`;
}

function generateThumbnailUrl(videoUrl) {
  if (!videoUrl) return null;
  
  console.log('Generating thumbnail for video URL:', videoUrl);
  
  // Try multiple thumbnail generation strategies
  const strategies = [];
  
  // Strategy 1: Use the video URL directly if it's already an image
  if (videoUrl.match(/\.(jpg|jpeg|png|gif|webp)(\?|$)/i)) {
    return videoUrl;
  }
  
  // Strategy 2: Replace video extension with image extension
  strategies.push(videoUrl.replace(/\.(mp4|webm|ogg|mov|avi|mkv|flv|wmv)(\?|$)/i, '.jpg'));
  
  // Strategy 3: Add _thumbnail suffix before extension
  strategies.push(videoUrl.replace(/(\.[^.]+)(\?|$)/i, '_thumbnail$1$2'));
  
  // Strategy 4: Replace video with image in path
  strategies.push(videoUrl.replace(/\/reels\//, '/reels/thumbnails/'));
  
  // Strategy 5: Add thumbnail folder
  strategies.push(videoUrl.replace(/\/media\/reels\//, '/media/reels/thumbnails/'));
  
  // Strategy 6: Try PNG format
  strategies.push(videoUrl.replace(/\.(mp4|webm|ogg|mov|avi|mkv|flv|wmv)(\?|$)/i, '.png'));
  
  console.log('Generated thumbnail strategies:', strategies);
  return strategies; // Return all strategies to try
}

const VideoThumbnail = React.memo(({ thumbnailUrl, style, postMedia }) => {
  const [showPlaceholder, setShowPlaceholder] = useState(false);
  const [imageSize, setImageSize] = useState({ width: null, height: null });
  
  // Debug thumbnailUrl value
  console.log('VideoThumbnail props:', { thumbnailUrl, postMedia });
  
  // Normalize thumbnail URL - handle both relative and absolute URLs
  const thumbnailUrls = useMemo(() => {
    let urls = [];
    if (thumbnailUrl && typeof thumbnailUrl === 'string') {
      if (Array.isArray(thumbnailUrl)) {
        urls = thumbnailUrl;
      } else {
        urls = generateThumbnailUrl(thumbnailUrl);
        if (typeof urls === 'string') {
          urls = [urls];
        }
      }
    } else {
      console.log('Invalid thumbnailUrl, showing placeholder:', thumbnailUrl);
      setShowPlaceholder(true);
    }
    return urls;
  }, [thumbnailUrl]);
  
  const normalizeUrl = useCallback((url) => {
    if (!url || typeof url !== 'string') return null;
    if (url.startsWith('http')) return url;
    const baseUrl = config.API_BASE_URL.replace('/api', '');
    return url.startsWith('/') ? `${baseUrl}${url}` : `${baseUrl}/${url}`;
  }, []);
  
  const normalizedUrl = thumbnailUrls.length > 0 ? normalizeUrl(thumbnailUrls[0]) : null;
  
  const handleImageError = useCallback((e) => {
    console.log('Thumbnail failed to load:', { 
      original: thumbnailUrl, 
      normalized: normalizedUrl, 
      postMedia,
      error: e.nativeEvent 
    });
    setShowPlaceholder(true);
  }, [thumbnailUrl, normalizedUrl, postMedia]);
  
  const handleImageLoad = useCallback((e) => {
    const { width: imgWidth, height: imgHeight } = e.nativeEvent.source;
    console.log('Image loaded with dimensions:', { imgWidth, imgHeight });
    setImageSize({ width: imgWidth, height: imgHeight });
  }, []);
  
  // Calculate dynamic container size based on image aspect ratio
  const containerStyle = useMemo(() => {
    if (imageSize.width && imageSize.height) {
      return {
        width: '100%',
        aspectRatio: imageSize.width / imageSize.height,
        backgroundColor: '#111',
      };
    }
    return {
      width: '100%',
      height: 300, // Default height while loading
      backgroundColor: '#111',
    };
  }, [imageSize]);
  
  if (showPlaceholder || !normalizedUrl) {
    return (
      <View style={[style, { backgroundColor: colors.cardBg, justifyContent: 'center', alignItems: 'center' }]}>
        <Ionicons name="videocam" size={64} color={colors.primary} />
        <Text style={[styles.videoPlaceholderText, { color: colors.textSecondary }]}>Video</Text>
      </View>
    );
  }
  
  return (
    <View style={containerStyle}>
      <Image
        source={{ uri: normalizedUrl }}
        style={{ 
          width: '100%', 
          height: '100%',
          backgroundColor: '#111',
        }}
        resizeMode="contain"
        onError={handleImageError}
        onLoad={handleImageLoad}
      />
      <View style={styles.playOverlay} pointerEvents="none">
        <View style={styles.playBtn}>
          <Ionicons name="play" size={24} color="#000" />
        </View>
      </View>
    </View>
  );
});

// Custom component for displaying images at original size without black spaces
const OriginalSizeImage = React.memo(({ imageUrl, style }) => {
  const [imageSize, setImageSize] = useState({ width: null, height: null });
  const [loading, setLoading] = useState(true);
  
  const handleImageLoad = useCallback((e) => {
    const { width: imgWidth, height: imgHeight } = e.nativeEvent.source;
    console.log('OriginalSizeImage loaded with dimensions:', { imgWidth, imgHeight });
    setImageSize({ width: imgWidth, height: imgHeight });
    setLoading(false);
  }, []);
  
  const handleImageError = useCallback((e) => {
    console.log('OriginalSizeImage failed to load:', e.nativeEvent);
    setLoading(false);
  }, []);
  
  // Calculate dynamic container size based on image aspect ratio
  const containerStyle = useMemo(() => {
    if (imageSize.width && imageSize.height) {
      return {
        width: '100%',
        aspectRatio: imageSize.width / imageSize.height,
        backgroundColor: '#111',
      };
    }
    return {
      width: '100%',
      height: 300, // Default height while loading
      backgroundColor: '#111',
    };
  }, [imageSize]);
  
  return (
    <View style={containerStyle} pointerEvents="box-none">
      <Image
        source={{ uri: imageUrl }}
        style={{ 
          width: '100%', 
          height: '100%',
          backgroundColor: '#111',
        }}
        resizeMode="cover"
        onError={handleImageError}
        onLoad={handleImageLoad}
      />
      {loading && (
        <View style={{ 
          position: 'absolute', 
          top: 0, 
          left: 0, 
          right: 0, 
          bottom: 0, 
          justifyContent: 'center', 
          alignItems: 'center',
          backgroundColor: '#111'
        }}>
          <ActivityIndicator size="small" color={GOLD} />
        </View>
      )}
    </View>
  );
});

const SkeletonPost = React.memo(() => {
  return (
    <View style={{ backgroundColor: CARD, marginBottom: 8, padding: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 12 }}>
        <View style={{ width: 38, height: 38, borderRadius: 19, backgroundColor: '#2a2a2a' }} />
        <View style={{ marginLeft: 10 }}>
          <View style={{ width: 100, height: 12, borderRadius: 6, backgroundColor: '#2a2a2a', marginBottom: 6 }} />
          <View style={{ width: 60, height: 10, borderRadius: 5, backgroundColor: '#222' }} />
        </View>
      </View>
      <View style={{ width: '100%', height: width * 0.75, borderRadius: 8, backgroundColor: '#2a2a2a' }} />
      <View style={{ flexDirection: 'row', marginTop: 10, gap: 16 }}>
        <View style={{ width: 48, height: 12, borderRadius: 6, backgroundColor: '#2a2a2a' }} />
        <View style={{ width: 48, height: 12, borderRadius: 6, backgroundColor: '#2a2a2a' }} />
      </View>
    </View>
  );
});


export default function HomeScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const auth = useAuth();
  const { colors } = useTheme();
  const { filterBlockedUsers } = useBlock();
  const user = auth?.user ?? null;
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [commentPost, setCommentPost] = useState(null);
  const [comments, setComments] = useState([]);
  const [commentText, setCommentText] = useState('');
  const [postingComment, setPostingComment] = useState(false);
  const [replyingTo, setReplyingTo] = useState(null);
  const [expandedReplies, setExpandedReplies] = useState(new Set());
  const [loadingComments, setLoadingComments] = useState(false);
  const [activeTab, setActiveTab] = useState('For You');
  const [showOptions, setShowOptions] = useState(null);
  const [optionsPosition, setOptionsPosition] = useState({ x: 0, y: 0 });
  const optionsButtonRef = useRef(null);
  const [followStates, setFollowStates] = useState({});
  const [viewCounts, setViewCounts] = useState({});
  const [shareToast, setShareToast] = useState('');
  const [showPostInfoModal, setShowPostInfoModal] = useState(null);
  const [showGiftModal, setShowGiftModal] = useState(false);
  const [showSuggestions, setShowSuggestions] = useState(true);
  const [localShareCounts, setLocalShareCounts] = useState({}); // Track local share increments
  const [showHorizontalSuggestions, setShowHorizontalSuggestions] = useState(true);
  const [suggestionPositions, setSuggestionPositions] = useState(new Set());
  const [showSearchDropdown, setShowSearchDropdown] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState({ users: [], posts: [], hashtags: [] });
  const [searchLoading, setSearchLoading] = useState(false);
  const searchTimeoutRef = useRef(null);
  const [giftRecipient, setGiftRecipient] = useState('');
  const [giftMessage, setGiftMessage] = useState('');
  const [sendingGift, setSendingGift] = useState(false);
  const [giftSent, setGiftSent] = useState(null);
  const [giftError, setGiftError] = useState('');
  const [userCoins, setUserCoins] = useState(0);
  const [gifts, setGifts] = useState([]);
  const [giftsSentToday, setGiftsSentToday] = useState(0);
  const [dailyGiftLimit, setDailyGiftLimit] = useState(10);
  const [giftHistory, setGiftHistory] = useState([]);
  const [selectedGift, setSelectedGift] = useState(null);
  const [giftQuantity, setGiftQuantity] = useState(1);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const flatListRef = useRef(null);
  const LIMIT = 5;

  // Handle navigation to specific post
  useEffect(() => {
    const postId = route?.params?.postId;
    if (postId) {
      console.log('HomeScreen - Navigating to post ID:', postId);
      // Always fetch the specific post and show it at the top
      fetchSpecificPost(postId);
      // Clear the param to avoid re-fetching on subsequent renders
      navigation.setParams({ postId: undefined });
    }
  }, [route?.params?.postId]);

  const fetchSpecificPost = async (postId) => {
    try {
      const post = await api.request(`/reels/${postId}/`);
      if (post) {
        console.log('Fetched specific post:', post.id);
        // Add the specific post to the top of the feed, removing duplicates
        setPosts(prev => {
          const filtered = prev.filter(p => p.id !== postId && p.type !== 'horizontal_suggestions');
          return [post, ...filtered];
        });
        // Scroll to top after a short delay
        setTimeout(() => {
          flatListRef.current?.scrollToOffset({ offset: 0, animated: true });
        }, 100);
      }
    } catch (error) {
      console.error('Failed to fetch specific post:', error);
    }
  };

  // Pause video when screen loses focus (e.g., navigating to login, settings, etc.)
  useEffect(() => {
    const unsubscribe = navigation.addListener('blur', () => {
      // Pause all videos when screen loses focus
      setPosts(prev => prev.map(post => ({ ...post, paused: true })));
    });
    return unsubscribe;
  }, [navigation]);

  const CATEGORY_ICONS = {
    flowers: '🌹',
    hearts: '❤️',
    gems: '💎',
    special: '⭐',
    animals: '🐻',
  };

  const DEFAULT_GIFTS = [
    { id: 1, name: 'Rose', description: 'A beautiful red rose', coin_value: 10, rarity: 'common', category: 'flowers' },
    { id: 2, name: 'Heart', description: 'A heart symbol', coin_value: 20, rarity: 'common', category: 'hearts' },
    { id: 3, name: 'Medal', description: 'A gold medal', coin_value: 50, rarity: 'rare', category: 'special' },
    { id: 4, name: 'Diamond', description: 'A sparkling diamond', coin_value: 100, rarity: 'epic', category: 'gems' },
    { id: 5, name: 'Teddy Bear', description: 'A cute teddy bear', coin_value: 30, rarity: 'common', category: 'animals' },
  ];

  useEffect(() => {
    if (activeTab === 'For You') {
      // Show stale cache immediately, refresh in background
      const stale = api.requestStale(`/reels/?limit=${LIMIT}&offset=0`, (fresh) => {
        const results = Array.isArray(fresh) ? fresh : (fresh.results || []);
        
        // DEBUG: Log first post to see what URLs we're getting
        if (results.length > 0) {
          console.log('=== FEED DATA DEBUG ===');
          console.log('First post data:', JSON.stringify(results[0], null, 2));
          console.log('Image URL:', results[0].image);
          console.log('Media URL:', results[0].media);
          console.log('Thumbnail URL:', results[0].thumbnail);
          console.log('User profile_photo:', results[0].user?.profile_photo);
        }
        
        // Insert suggestions at dynamic positions
        let finalResults = results;
        if (results.length >= 3) {
          const positions = calculateSuggestionPositions(results.length);
          setSuggestionPositions(positions);
          
          // Insert suggestions at calculated positions
          const withSuggestions = [];
          results.forEach((post, index) => {
            withSuggestions.push(post);
            if (positions.has(index)) {
              // Generate unique ID for each suggestion to avoid duplicates
              const uniqueId = `suggestions-${index}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
              withSuggestions.push({ type: 'horizontal_suggestions', id: uniqueId });
            }
          });
          finalResults = withSuggestions;
        }
        // Preserve local share counts and filter blocked users
        const updatedFinalResults = finalResults.map(post => ({
          ...post,
          shares: (post.shares || 0) + (localShareCounts[post.id] || 0)
        }));
        // Filter out posts from blocked users
        const filteredFinalResults = filterBlockedUsers(updatedFinalResults);
        setPosts(filteredFinalResults);
        setHasMore(results.length === LIMIT);
        setPage(0);
      });
      if (stale) {
        const results = Array.isArray(stale) ? stale : (stale.results || []);
        // Insert suggestions at dynamic positions for stale cache
        let finalResults = results;
        if (results.length >= 3) {
          const positions = calculateSuggestionPositions(results.length);
          setSuggestionPositions(positions);
          
          const withSuggestions = [];
          results.forEach((post, index) => {
            withSuggestions.push(post);
            if (positions.has(index)) {
              // Generate unique ID for each suggestion to avoid duplicates
              const uniqueId = `suggestions-stale-${index}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
              withSuggestions.push({ type: 'horizontal_suggestions', id: uniqueId });
            }
          });
          finalResults = withSuggestions;
        }
        // Preserve local share counts and filter blocked users
        const updatedFinalResults = finalResults.map(post => ({
          ...post,
          shares: (post.shares || 0) + (localShareCounts[post.id] || 0)
        }));
        // Filter out posts from blocked users
        const filteredFinalResults = filterBlockedUsers(updatedFinalResults);
        setPosts(filteredFinalResults);
        setHasMore(results.length === LIMIT);
        setPage(0);
        setLoading(false);
      } else {
        fetchPosts(0, true);
      }
    }
  }, [activeTab]);

  useEffect(() => {
    const loadUserCoins = async () => {
      try {
        // Use wallet API to get purchased balance for gifting (web app logic)
        const wallet = await api.request('/wallet/');
        setUserCoins(wallet.balance?.purchased || 0);
        
        // Load gamification status for daily gift limit
        const status = await api.request('/gamification/status/');
        setGiftsSentToday(status.gifts?.sent_today || 0);
        
        // Load gift history
        const history = await api.request('/gamification/gifts/history/');
        setGiftHistory(history.received || []);
      } catch (error) {
        console.error('Failed to load user coins:', error);
        setUserCoins(0);
      }
    };
    loadUserCoins();
  }, [showGiftModal]);

  // Auto-claim daily login bonus on app open (once per day)
  useEffect(() => {
    const claimDailyBonus = async () => {
      try {
        // Check if we already tried today
        const lastAttempt = await AsyncStorage.getItem('lastBonusAttempt');
        const today = new Date().toDateString();
        
        if (lastAttempt === today) {
          // Already tried today, skip
          return;
        }
        
        const response = await api.request('/gamification/login-bonus/', {
          method: 'POST',
        });
        
        // Mark as attempted today
        await AsyncStorage.setItem('lastBonusAttempt', today);
        console.log('Daily login bonus claimed:', response);
      } catch (error) {
        // Mark as attempted even on error to avoid repeated attempts
        const today = new Date().toDateString();
        await AsyncStorage.setItem('lastBonusAttempt', today);
      }
    };
    claimDailyBonus();
  }, []);

  useEffect(() => {
    const loadGifts = async () => {
      try {
        const response = await api.request('/gifts/');
        const giftsData = response.results || response;
        if (Array.isArray(giftsData) && giftsData.length > 0) {
          setGifts(giftsData);
        } else {
          setGifts(DEFAULT_GIFTS);
        }
      } catch (error) {
        console.error('Failed to load gifts:', error);
        setGifts(DEFAULT_GIFTS);
      }
    };
    loadGifts();
  }, []);

  // Auto-refresh content when block state changes
  useEffect(() => {
    // Refresh the current tab to reflect block/unblock changes
    if (activeTab === 'For You') {
      fetchPosts(0, true);
    }
  }, [filterBlockedUsers]);

  const fetchPosts = async (offset = 0, reset = false) => {
    try {
      if (reset) setLoading(true); else setLoadingMore(true);
      const data = await api.request(`/reels/?limit=${LIMIT}&offset=${offset}`);
      const results = Array.isArray(data) ? data : (data.results || []);
      
      // Debug logging for first post to see exact structure
      if (results.length > 0 && offset === 0) {
        console.log('=== API RESPONSE DEBUG ===');
        console.log('Full API response:', JSON.stringify(data, null, 2));
        console.log('First post structure:', JSON.stringify(results[0], null, 2));
        console.log('First post user:', results[0]?.user);
        console.log('First post user fields:', Object.keys(results[0]?.user || {}));
      }
      
      // Insert suggestions at dynamic positions
      let finalResults = results;
      if (reset && results.length >= 3) {
        const positions = calculateSuggestionPositions(results.length);
        setSuggestionPositions(positions);
        
        const withSuggestions = [];
        results.forEach((post, index) => {
          withSuggestions.push(post);
          if (positions.has(index)) {
            // Generate unique ID for each suggestion to avoid duplicates
            const uniqueId = `suggestions-fetch-${index}-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
            withSuggestions.push({ type: 'horizontal_suggestions', id: uniqueId });
          }
        });
        finalResults = withSuggestions;
      }
      
      // Preserve local share counts and filter blocked users
      const updatedFinalResults = finalResults.map(post => ({
        ...post,
        shares: (post.shares || 0) + (localShareCounts[post.id] || 0)
      }));
      const updatedResults = results.map(post => ({
        ...post,
        shares: (post.shares || 0) + (localShareCounts[post.id] || 0)
      }));
      
      // Filter out posts from blocked users
      const filteredFinalResults = filterBlockedUsers(updatedFinalResults);
      const filteredResults = filterBlockedUsers(updatedResults);
      
      setPosts(prev => reset ? filteredFinalResults : [...prev, ...filteredResults]);
      setHasMore(results.length === LIMIT);
      setPage(offset);
    } catch (e) {
      console.error('Feed error:', e);
    } finally {
      setLoading(false);
      setRefreshing(false);
      setLoadingMore(false);
    }
  };

  const onRefresh = useCallback(() => { setRefreshing(true); fetchPosts(0, true); }, []);
  const onEndReached = useCallback(() => { if (!loadingMore && hasMore && activeTab === 'For You') fetchPosts(page + LIMIT); }, [loadingMore, hasMore, activeTab, page]);

  const sharePost = useCallback(async (post) => {
    // Use both web URL and app URL for better compatibility
    const webUrl = `https://uat.flipstar.et/post/${post.id}`;
    const appUrl = `flipstar://post/${post.id}`;
    const title = post.caption ? post.caption.slice(0, 80) : 'Check out this post on FlipStar';
    
    try {
      await Share.share({
        message: `${title}\n\n${webUrl}\n\nOr open in app: ${appUrl}`,
        url: webUrl,
        title: 'FlipStar Post',
      });
      // Increment share count on backend
      try { 
        console.log('HomeScreen share - before - post shares:', post.shares);
        console.log('HomeScreen share - before - localShareCounts:', localShareCounts[post.id]);
        
        await api.request(`/reels/${post.id}/share/`, { method: 'POST' });
        
        // Update persistent local share count
        setLocalShareCounts(prev => {
          const updated = {
            ...prev,
            [post.id]: (prev[post.id] || 0) + 1
          };
          console.log('HomeScreen share - updated localShareCounts:', updated[post.id]);
          return updated;
        });
        
        // Update local share count
        setPosts(prev => {
          const updated = prev.map(p => 
            p.id === post.id ? { ...p, shares: (p.shares || 0) + 1 } : p
          );
          console.log('HomeScreen share - updated posts share count for post', post.id);
          return updated;
        });
        
        console.log('HomeScreen share increment successful');
      } catch (err) {
        console.log('HomeScreen share increment failed:', err);
      }
    } catch (error) {
      console.log('Share error:', error);
    }
  }, []);

  const toggleFollow = useCallback(async (userId) => {
    if (!user) {
      Alert.alert('Login Required', 'Please login to follow users');
      return;
    }
    
    setFollowStates(prev => ({ ...prev, [userId]: true }));
    try {
      const response = await api.request('/follows/toggle/', {
        method: 'POST',
        body: JSON.stringify({ following_id: userId }),
      });
      
      setFollowStates(prev => ({ ...prev, [userId]: response.following }));
      
      // Activity-based trigger: after following, show suggestions
      if (response.following) {
        // Insert suggestions near the current position after a short delay
        setTimeout(() => {
          setPosts(prev => {
            const currentIndex = prev.findIndex(p => p.user?.id === userId);
            if (currentIndex !== -1 && currentIndex + 1 < prev.length) {
              const newPosts = [...prev];
              // Generate a truly unique ID using both timestamp and random number
              const uniqueId = `suggestions-follow-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
              newPosts.splice(currentIndex + 1, 0, { type: 'horizontal_suggestions', id: uniqueId });
              return newPosts;
            }
            return prev;
          });
        }, 500);
      }
    } catch (error) {
      console.error('Follow error:', error);
      setFollowStates(prev => ({ ...prev, [userId]: false }));
    }
  }, [user]);

  const trackView = async (postId) => {
    if (viewCounts[postId]) return;
    
    setViewCounts(prev => ({ ...prev, [postId]: true }));
    try {
      const res = await api.request(`/reels/${postId}/view/`, { method: 'POST' });
      if (res?.view_count !== undefined) {
        setPosts(prev => prev.map(p => 
          p.id === postId ? { ...p, view_count: res.view_count } : p
        ));
      }
    } catch {}
  };

  // Build comment tree from flat list (like web app)
  const buildCommentTree = (flatList) => {
    if (!Array.isArray(flatList)) return [];
    const map = {};
    const roots = [];
    
    flatList.forEach(c => {
      map[c.id] = { ...c };
      if (!map[c.id].replies) map[c.id].replies = [];
    });
    
    flatList.forEach(c => {
      const node = map[c.id];
      const parentVal = c.parent_id || c.parent;
      const parentId = (parentVal && typeof parentVal === 'object') ? parentVal.id : parentVal;
      
      if (parentId && String(parentId) !== '0') {
        const parent = map[parentId];
        if (parent) {
          if (!parent.replies.some(r => String(r.id) === String(node.id))) {
            parent.replies.push(node);
          }
        } else {
          roots.push(node);
        }
      } else {
        roots.push(node);
      }
    });
    return roots;
  };

  const toggleReplies = (commentId) => {
    setExpandedReplies(prev => {
      const next = new Set(prev);
      if (next.has(commentId)) next.delete(commentId);
      else next.add(commentId);
      return next;
    });
  };

  const findRootId = (list, targetId) => {
    for (const c of list) {
      if (String(c.id) === String(targetId)) return c.id;
      if (c.replies?.length) {
        const found = findRootId(c.replies, targetId);
        if (found !== null) return found;
      }
    }
    return null;
  };

  const showPostOptions = (post) => {
    // Position dropdown in upper right corner of the card (Instagram-style)
    // Fixed position from top-right of screen
    setOptionsPosition({ 
      x: Dimensions.get('window').width - 200, // 200px from left (right-aligned)
      y: 60 // 60px from top (below header)
    });
    setShowOptions(post);
  };

  const handleTabPress = (tab) => {
    if (tab === 'Explore') {
      navigation.navigate('Explore');
      return;
    }
    if (tab === 'Campaigns') {
      navigation.navigate('Campaigns');
      return;
    }
    setActiveTab(tab);
  };

  // Calculate dynamic suggestion positions based on Instagram-style algorithm
  const calculateSuggestionPositions = (postCount) => {
    const positions = new Set();
    if (postCount < 3) return positions;
    
    // Insert suggestions at random intervals (every 3-5 posts)
    // Instagram uses dynamic positioning based on user activity
    let position = 2 + Math.floor(Math.random() * 3); // Start between 2-4
    while (position < postCount) {
      positions.add(position);
      position += 3 + Math.floor(Math.random() * 3); // Add 3-5 posts between suggestions
    }
    
    return positions;
  };

  const copyPostLink = (post) => {
    const url = `https://uat.flipstar.et/post/${post.id}`;
    Share.share({
      message: url,
      title: 'FlipStar Post',
    }).catch(() => {});
    setShowOptions(null);
  };

  const showPostInfo = (post) => {
    setShowPostInfoModal(post);
    setShowOptions(null);
  };

  const downloadPost = async (post) => {
    const url = post.media || post.image;
    if (!url) return;
    
    try {
      // For Cloudinary URLs, add fl_attachment to force download
      let downloadUrl = url;
      if (url.includes('res.cloudinary.com') && url.includes('/upload/')) {
        downloadUrl = url.replace('/upload/', '/upload/fl_attachment/');
      }
      
      // In React Native, we can't directly download files to device storage
      // We'll show a toast with the download URL
      setShareToast('Download link copied to clipboard');
      setTimeout(() => setShareToast(''), 2000);
      setShowOptions(null);
    } catch (error) {
      console.error('Download error:', error);
    }
  };

  const deletePost = async (post) => {
    if (!user || user.id !== post.user?.id) return;
    
    try {
      await api.request(`/reels/${post.id}/`, { method: 'DELETE' });
      setPosts(prev => prev.filter(p => p.id !== post.id));
      setShowOptions(null);
      setShareToast('Post deleted successfully');
      setTimeout(() => setShareToast(''), 2000);
    } catch (error) {
      console.error('Delete error:', error);
      setShareToast('Failed to delete post');
      setTimeout(() => setShareToast(''), 2000);
    }
  };

  const reportPost = (post) => {
    Alert.alert(
      'Report Post',
      'Why are you reporting this post?',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Spam', onPress: () => submitReport(post, 'spam') },
        { text: 'Inappropriate', onPress: () => submitReport(post, 'inappropriate') },
        { text: 'Other', onPress: () => submitReport(post, 'other') },
      ]
    );
    setShowOptions(null);
  };

  const submitReport = async (post, reason) => {
    try {
      await api.request('/reports/create/', {
        method: 'POST',
        body: JSON.stringify({
          reported_reel_id: post.id,
          report_type: reason,
          description: `Reported as ${reason}`,
        }),
      });
      Alert.alert('Success', 'Report submitted successfully');
    } catch (error) {
      Alert.alert('Error', 'Failed to submit report');
    }
  };

  const goToReel = useCallback((postId) => {
    console.log('goToReel called with postId:', postId);
    trackView(postId);
    console.log('Navigating to ReelsDetail with initialVideoId:', postId);
    navigation.navigate('ReelsDetail', { initialVideoId: postId });
  }, [navigation]);

  const toggleLike = useCallback(async (post) => {
    const newLiked = !post.is_liked;
    setPosts(prev => prev.map(p => p.id === post.id
      ? { ...p, is_liked: newLiked, votes: newLiked ? (p.votes + 1) : Math.max(0, p.votes - 1) }
      : p));
    try { 
      await api.request(`/reels/${post.id}/vote/`, { method: 'POST' });
    } catch { 
      setPosts(prev => prev.map(p => p.id === post.id ? { ...p, is_liked: post.is_liked, votes: post.votes } : p));
    }
  }, []);

  const toggleSave = useCallback(async (post) => {
    const newSaved = !post.is_saved;
    setPosts(prev => prev.map(p => p.id === post.id ? { ...p, is_saved: newSaved } : p));
    try {
      await api.request(`/reels/${post.id}/save/`, { method: 'POST' });
    } catch {
      setPosts(prev => prev.map(p => p.id === post.id ? { ...p, is_saved: post.is_saved } : p));
    }
  }, []);

  const openGiftModal = (postUser) => {
    setGiftRecipient(postUser?.username || '');
    setSelectedGift(null);
    setGiftQuantity(1);
    setGiftMessage('');
    setGiftError('');
    setGiftSent(null);
    setSelectedCategory('all');
    setShowGiftModal(true);
  };

  const sendGift = async () => {
    if (!giftRecipient.trim()) {
      setGiftError('Enter a recipient username');
      return;
    }
    if (!selectedGift) {
      setGiftError('Select a gift to send');
      return;
    }
    const totalCost = selectedGift.coin_value * giftQuantity;
    
    // Check daily gift limit (web app logic: 10 gifts per day)
    if (giftsSentToday >= dailyGiftLimit) {
      setGiftError(`Daily gift limit reached (${dailyGiftLimit} per day)`);
      return;
    }
    
    // Check purchased coins balance (web app logic: only purchased coins can be gifted)
    if (totalCost > userCoins) {
      setGiftError(`Insufficient purchased coins. Need ${totalCost}, have ${userCoins}`);
      return;
    }
    
    setSendingGift(true);
    setGiftError('');
    try {
      // Use gifts/send endpoint (web app logic)
      await api.request('/gifts/send/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gift_id: selectedGift.id,
          recipient_username: giftRecipient,
          quantity: giftQuantity,
          message: giftMessage,
        }),
      });
      setGiftSent(true);
      setUserCoins(prev => prev - totalCost);
      setGiftsSentToday(prev => prev + 1);
      
      // Play coin sound for successful gift
      SoundManager.playCoinSound();
      
      setTimeout(() => {
        setShowGiftModal(false);
        setGiftSent(null);
      }, 2000);
    } catch (error) {
      const errMsg = error?.message || '';
      const needsRecharge = errMsg.includes('Insufficient') || errMsg.includes('needs_recharge');
      
      if (needsRecharge) {
        const match = errMsg.match(/need (\d+).*have (\d+)/i);
        const needed = match ? match[1] : totalCost;
        const have = match ? match[2] : userCoins;
        Alert.alert(
          'Insufficient Coins',
          `You need ${needed} purchased coins but only have ${have}.\n\nOnly purchased coins can be used for gifting. Please top up your coins.`,
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Buy Coins', onPress: () => navigation.navigate('WebsiteCoin') },
          ]
        );
      } else {
        setGiftError(errMsg || 'Failed to send gift');
      }
    } finally {
      setSendingGift(false);
    }
  };

  const openComments = async (post) => {
    setCommentPost(post);
    setLoadingComments(true);
    try {
      // Fetch comments with replies for tree structure
      const data = await api.request(`/reels/${post.id}/comments/?include_replies=true&depth=2`);
      const full = Array.isArray(data) ? data : (data?.results || []);
      setComments(buildCommentTree(full));
    } catch (e) {
      console.error('Failed to fetch comments:', e);
      setComments(buildCommentTree(post.recent_comments || []));
    } finally {
      setLoadingComments(false);
    }
  };

  const postComment = async () => {
    if (!commentText.trim() || !commentPost) return;
    setPostingComment(true);
    
    const temp = {
      id: `temp-${Date.now()}`,
      text: commentText.trim(),
      user: user || { username: 'you', profile_photo: null },
      created_at: new Date().toISOString(),
      likes: 0,
      replies: [],
      pending: true,
    };

    try {
      if (replyingTo) {
        // Add as reply
        const updateDeep = (list) => list.map(c => {
          if (String(c.id) === String(replyingTo.id)) {
            return { ...c, replies: [...(c.replies || []), temp] };
          }
          if (c.replies && c.replies.length) {
            return { ...c, replies: updateDeep(c.replies) };
          }
          return c;
        });
        setComments(updateDeep(comments));
        
        // Auto-expand the root ancestor
        const rootId = findRootId(comments, replyingTo.id);
        if (rootId != null) {
          setExpandedReplies(prev => {
            const next = new Set(prev);
            next.add(rootId);
            return next;
          });
        }
        
        const res = await api.request(`/reels/${commentPost.id}/comments/`, {
          method: 'POST',
          body: JSON.stringify({ text: commentText.trim(), parent_id: replyingTo.id }),
        });
        if (!res.replies) res.replies = [];
        
        const swapDeep = (list) => list.map(c => {
          if (String(c.id) === String(replyingTo.id)) {
            return { ...c, replies: (c.replies || []).map(r => String(r.id) === String(temp.id) ? { ...res, replies: res.replies || [] } : r) };
          }
          if (c.replies && c.replies.length) {
            return { ...c, replies: swapDeep(c.replies) };
          }
          return c;
        });
        setComments(prev => swapDeep(prev));
      } else {
        // Add as top-level comment
        setComments([temp, ...comments]);
        const c = await api.request(`/reels/${commentPost.id}/comments/`, {
          method: 'POST', body: JSON.stringify({ text: commentText.trim() }),
        });
        if (!c.replies) c.replies = [];
        setComments(prev => prev.map(cm => cm.id === temp.id ? c : cm));
      }
      
      setCommentText('');
      setReplyingTo(null);
      setPosts(prev => prev.map(p => p.id === commentPost.id
        ? { ...p, comment_count: (p.comment_count || 0) + 1 } : p));
    } catch (e) {
      Alert.alert('Error', 'Failed to post comment');
      // Roll back
      setComments(prev => {
        const removeDeep = (list) => list.filter(c => {
          if (c.id === temp.id) return false;
          if (c.replies?.length) c.replies = removeDeep(c.replies);
          return true;
        });
        return removeDeep(prev);
      });
    } finally {
      setPostingComment(false);
    }
  };

  const renderHashtags = (hashtags) => {
    if (!hashtags) return null;
    const tags = String(hashtags).split(/[\s,]+/).filter(Boolean)
      .map(t => t.startsWith('#') ? t : `#${t}`).join('  ');
    return <Text style={styles.hashtags}>{tags}</Text>;
  };

  const handleSearch = (query) => {
    setSearchQuery(query);
    
    // Clear previous timeout
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
    
    if (!query.trim()) {
      setSearchResults({ users: [], posts: [], hashtags: [] });
      setShowSearchDropdown(false);
      return;
    }
    
    // Debounce search by 300ms (like web version)
    searchTimeoutRef.current = setTimeout(async () => {
      setSearchLoading(true);
      try {
        const data = await api.request(`/search/?q=${encodeURIComponent(query)}`);
        setSearchResults(data);
        setShowSearchDropdown(true);
      } catch (error) {
        console.error('Search error:', error);
      } finally {
        setSearchLoading(false);
      }
    }, 300);
  };

  const clearSearch = () => {
    setSearchQuery('');
    setSearchResults({ users: [], posts: [], hashtags: [] });
    setShowSearchDropdown(false);
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current);
    }
  };

  // Function to open profile by username (for mentions)
  const openProfileByUsername = async (username) => {
    try {
      const res = await api.request(`/search/?q=${encodeURIComponent(username)}`);
      const found = (res?.users || []).find(
        (u) => (u.username || '').toLowerCase() === username.toLowerCase()
      );
      if (found?.id) {
        navigation.navigate('Profile', { userId: found.id });
      }
    } catch (err) {
      console.warn('Failed to resolve mention to profile:', err);
    }
  };

  // Component to render text with clickable mentions
  const TextWithMentions = ({ text, style }) => {
    if (!text) return null;
    
    const parts = [];
    const regex = /@(\w+)/g;
    let lastIndex = 0;
    let match;
    let key = 0;
    
    while ((match = regex.exec(text)) !== null) {
      // Add text before mention
      if (match.index > lastIndex) {
        parts.push(
          <Text key={`text-${key++}`} style={style}>
            {text.slice(lastIndex, match.index)}
          </Text>
        );
      }
      
      // Add mention as clickable text
      const username = match[1];
      parts.push(
        <Text
          key={`mention-${key++}`}
          style={[style, { color: GOLD, fontWeight: '700' }]}
          onPress={() => openProfileByUsername(username)}
        >
          @{username}
        </Text>
      );
      
      lastIndex = match.index + match[0].length;
    }
    
    // Add remaining text
    if (lastIndex < text.length) {
      parts.push(
        <Text key={`text-${key++}`} style={style}>
          {text.slice(lastIndex)}
        </Text>
      );
    }
    
    return <Text>{parts}</Text>;
  };

  // Recursive comment item component for tree structure
  const CommentItem = ({ comment, depth = 0 }) => {
    const isReply = depth > 0;
    const avatarSize = isReply ? 28 : 34;
    const hasReplies = comment.replies && comment.replies.length > 0;
    const isExpanded = expandedReplies.has(comment.id);
    const showRepliesToggle = !isReply && hasReplies;

    return (
      <View style={{ marginBottom: 16 }}>
        <View style={{ flexDirection: 'row', alignItems: 'flex-start', gap: 10 }}>
          <Avatar uri={comment.user?.profile_photo} size={avatarSize} name={comment.user?.username} />
          <View style={{ flex: 1 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
              <Text style={styles.commentUser}>{comment.user?.username}</Text>
              <Text style={{ color: '#666', fontSize: 11 }}>{timeAgo(comment.created_at)}</Text>
            </View>
            <TextWithMentions text={comment.text} style={styles.commentText} />
            <View style={{ flexDirection: 'row', gap: 16, marginTop: 6 }}>
              <TouchableOpacity onPress={() => {}}>
                <Ionicons name="heart-outline" size={16} color={colors.textSecondary} />
              </TouchableOpacity>
              <TouchableOpacity onPress={() => setReplyingTo(comment)}>
                <Text style={{ color: colors.primary, fontSize: 13, fontWeight: '600' }}>Reply</Text>
              </TouchableOpacity>
            </View>
          </View>
        </View>
        
        {/* View/Hide replies button */}
        {showRepliesToggle && (
          <TouchableOpacity 
            onPress={() => toggleReplies(comment.id)}
            style={{ marginLeft: avatarSize + 10, marginTop: 8 }}
          >
            <Text style={{ color: GOLD, fontSize: 13, fontWeight: '600' }}>
              {isExpanded 
                ? `Hide ${comment.replies.length} ${comment.replies.length === 1 ? 'reply' : 'replies'}`
                : `View ${comment.replies.length} ${comment.replies.length === 1 ? 'reply' : 'replies'}`
              }
            </Text>
          </TouchableOpacity>
        )}

        {/* Recursive replies with tree line */}
        {hasReplies && (isReply || isExpanded) && (
          <View style={{ 
            marginLeft: depth === 0 ? 18 : 12, 
            paddingLeft: depth === 0 ? 26 : 18, 
            borderLeftWidth: 2, 
            borderLeftColor: 'rgba(200, 181, 106, 0.2)',
            marginTop: 12,
          }}>
            {comment.replies.map(r => (
              <CommentItem key={r.id} comment={r} depth={depth + 1} />
            ))}
          </View>
        )}
      </View>
    );
  };

  const renderPost = useCallback(({ item: post, index }) => {
    // Render horizontal suggestions after 2nd post (index 1)
    if (post.type === 'horizontal_suggestions' || post.type === 'suggestions') {
      return showHorizontalSuggestions ? (
        <HorizontalUserSuggestions 
          onUserClick={(userId) => navigation.navigate('Profile', { userId })}
          onDismiss={() => setShowHorizontalSuggestions(false)}
        />
      ) : null;
    }

    // Website logic: don't detect video type, just check if media exists vs image
    console.log('=== POST DEBUG ===');
    console.log('Post ID:', post.id);
    console.log('Post media:', post.media);
    console.log('Post image:', post.image);
    console.log('Post thumbnail:', post.thumbnail);
    console.log('Post user object:', post.user);
    console.log('Post user fields:', Object.keys(post.user || {}));
    console.log('Post user profile_photo:', post.user?.profile_photo);
    console.log('Post user avatar:', post.user?.avatar);
    console.log('Post user username:', post.user?.username);
    console.log('Post user first_name:', post.user?.first_name);
    const isOwnPost = user?.id === post.user?.id;
    const isFollowing = post.user?.is_following || followStates[post.user?.id];
    const isCampaignPost = !!(post.is_campaign_post || post.campaign_id || post.campaign);
    
    return (
      <View 
        style={[styles.postCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}
      >
        {/* Header */}
        <View style={styles.postHeader}>
          <TouchableOpacity
            style={styles.postUser}
            onPress={() => navigation.navigate('Profile', { userId: post.user?.id })}
          >
            <Avatar uri={post.user?.profile_photo} size={36} name={post.user?.username || post.user?.full_name || 'User'} />
            <View style={{ marginLeft: 10, flex: 1 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 4 }}>
                <Text style={[styles.username, { color: '#8fc441' }]}>{post.user?.username || post.user?.full_name || 'User'}</Text>
              </View>
              {post.created_at ? (
                <Text style={[styles.timeAgo, { color: colors.textSecondary }]}>{timeAgo(post.created_at)}</Text>
              ) : null}
            </View>
          </TouchableOpacity>
            
          {/* Follow/Unfollow button - only show for other users' posts */}
          {user && post.user?.id !== user.id && (
            <TouchableOpacity
              style={[
                styles.followBtn,
                { backgroundColor: isFollowing ? colors.border + '40' : colors.primary }
              ]}
              onPress={() => toggleFollow(post.user?.id)}
            >
              <Text style={[
                styles.followBtnText,
                { color: isFollowing ? colors.text : colors.text === '#FFFFFF' ? '#000' : '#fff' }
              ]}>
                {isFollowing ? 'Following' : 'Follow'}
              </Text>
            </TouchableOpacity>
          )}
          
          {/* Options - moved to header upper right */}
          <TouchableOpacity
            style={styles.headerOptionsBtn}
            onPress={() => showPostOptions(post)}
          >
            <Ionicons name="ellipsis-horizontal" size={20} color={colors.text} />
          </TouchableOpacity>
        </View>

        {/* Media */}
        {(post.thumbnail || post.media || post.image) && (
          <View style={styles.mediaWrapper}>
            {post.thumbnail ? (
              <>
                {/* If there's media (video), make it clickable */}
                {post.media ? (
                  <TouchableOpacity onPress={() => goToReel(post.id)} activeOpacity={0.9}>
                    <OriginalSizeImage imageUrl={post.thumbnail} />
                    {/* Play icon overlay for videos */}
                    <View style={styles.playOverlay}>
                      <Ionicons name="play-circle" size={48} color="rgba(255,255,255,0.9)" />
                    </View>
                  </TouchableOpacity>
                ) : (
                  /* Just thumbnail, no video - not clickable */
                  <OriginalSizeImage imageUrl={post.thumbnail} />
                )}
              </>
            ) : post.media ? (
              /* Has video media - make it clickable */
              <TouchableOpacity onPress={() => goToReel(post.id)} activeOpacity={0.9}>
                {post.image ? (
                  <OriginalSizeImage imageUrl={post.image} />
                ) : (
                  <View style={[styles.mediaImage, { justifyContent: 'center', alignItems: 'center', backgroundColor: colors.cardBg }]}>
                    <Ionicons name="videocam" size={64} color={colors.textSecondary} />
                  </View>
                )}
                {/* Play icon overlay for videos */}
                <View style={styles.playOverlay}>
                  <Ionicons name="play-circle" size={48} color="rgba(255,255,255,0.9)" />
                </View>
              </TouchableOpacity>
            ) : post.image ? (
              /* Just image, no video - not clickable */
              <OriginalSizeImage imageUrl={post.image} />
            ) : (
              <View style={[styles.mediaImage, { justifyContent: 'center', alignItems: 'center', backgroundColor: '#2a2a2a' }]}>
                <Text style={{ color: '#666', fontSize: 16 }}>No media</Text>
              </View>
            )}
            
            {/* View count badge */}
            <View style={styles.viewBadge}>
              <Ionicons name="eye" size={12} color="#fff" />
              <Text style={styles.viewCount}>{(post.view_count || 0).toLocaleString()}</Text>
            </View>
          </View>
        )}

        {/* Actions */}
        <View style={styles.actions}>
          <View style={styles.leftActions}>
            {/* Like */}
            <TouchableOpacity style={styles.actionBtn} onPress={() => toggleLike(post)}>
              <Ionicons
                name={
                  post.is_campaign || post.campaign_id 
                    ? (post.is_liked ? 'trophy' : 'trophy-outline')
                    : (post.is_liked ? 'heart' : 'heart-outline')
                }
                size={24}
                color={post.is_liked ? '#8fc441' : colors.text}
                fill={post.is_liked ? '#8fc441' : 'none'}
              />
              {post.votes > 0 && <Text style={[styles.actionCount, { color: colors.text }]}>{post.votes}</Text>}
            </TouchableOpacity>
            
            {/* Comment */}
            <TouchableOpacity style={styles.actionBtn} onPress={() => openComments(post)}>
              <Ionicons name="chatbubble-outline" size={22} color={colors.primary} />
              {(post.comment_count || 0) > 0 && <Text style={[styles.actionCount, { color: colors.text }]}>{post.comment_count || 0}</Text>}
            </TouchableOpacity>
            
            {/* Share */}
            <TouchableOpacity style={styles.actionBtn} onPress={() => sharePost(post)}>
              <Ionicons name="share-social-outline" size={22} color={colors.primary} />
              {post.shares > 0 && <Text style={[styles.actionCount, { color: colors.text }]}>{(post.shares || 0) + (localShareCounts[post.id] || 0)}</Text>}
            </TouchableOpacity>
            
            {/* Gift - only for other people's posts */}
            {post.user?.username !== user?.username && (
              <TouchableOpacity style={styles.actionBtn} onPress={() => openGiftModal(post.user)}>
                <Ionicons name="gift-outline" size={22} color={colors.primary} />
              </TouchableOpacity>
            )}
          </View>
          
          <View style={styles.rightActions}>
            {/* Save */}
            <TouchableOpacity
              style={styles.actionBtn}
              onPress={() => toggleSave(post)}
            >
              <Ionicons
                name={post.is_saved ? 'bookmark' : 'bookmark-outline'}
                size={22}
                color={post.is_saved ? colors.primary : colors.text}
              />
            </TouchableOpacity>
          </View>
        </View>

        {/* Caption */}
        {post.caption && (
          <TouchableOpacity 
            style={styles.captionContainer}
            onPress={() => {}} // Could expand caption
          >
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              <Text style={styles.captionUsername}>{post.user?.username} </Text>
              <TextWithMentions 
                text={post.caption} 
                style={styles.caption}
              />
            </View>
            {post.caption.length > 100 && (
              <Text style={styles.captionMore}> more</Text>
            )}
          </TouchableOpacity>
        )}

        {/* Recent comments */}
        {post.recent_comments && post.recent_comments.length > 0 && (
          <TouchableOpacity 
            style={styles.recentComments}
            onPress={() => openComments(post)}
          >
            <View style={{ flexDirection: 'row', flexWrap: 'wrap' }}>
              <Text style={styles.commentUsername}>{post.recent_comments[0].user?.username} </Text>
              <TextWithMentions 
                text={post.recent_comments[0].text} 
                style={styles.recentComment}
              />
            </View>
          </TouchableOpacity>
        )}

        {/* Comments link */}
        <TouchableOpacity onPress={() => openComments(post)}>
          <Text style={styles.commentsLink}>
            {(post.comment_count || 0) > 0 ? `View all ${post.comment_count || 0} comments` : 'Add a comment...'}
          </Text>
        </TouchableOpacity>

        {/* Hashtags */}
        {renderHashtags(post.hashtags_list || post.hashtags)}
      </View>
    );
  }, [user, followStates, navigation, toggleLike, toggleSave, sharePost, goToReel, openComments, openGiftModal, showPostOptions]);

  return (
    <View style={[styles.container, { backgroundColor: colors.bg }]}>
      <StatusBar barStyle={colors.text === '#FFFFFF' ? 'light-content' : 'dark-content'} />
      
      {/* Tab Navigation with Search Icon */}
      <View style={[styles.tabContainer, { backgroundColor: colors.cardBg, paddingTop: insets.top + 8 }]}>
        {TABS.map(tab => {
          const isActive = activeTab === tab;
          return (
            <TouchableOpacity
              key={tab}
              style={[styles.tab, isActive && { backgroundColor: colors.primary }]}
              onPress={() => handleTabPress(tab)}
            >
              <Text style={[styles.tabText, { color: colors.text }, isActive && { color: colors.text === '#FFFFFF' ? '#000' : '#fff' }]}>
                {tab}
              </Text>
            </TouchableOpacity>
          );
        })}
        
        {/* Search Icon - same size as tabs */}
        <TouchableOpacity 
          style={[styles.searchIconBtn, { backgroundColor: colors.border + '40' }]}
          onPress={() => setShowSearchDropdown(!showSearchDropdown)}
        >
          <Ionicons name="search" size={20} color={colors.primary} />
        </TouchableOpacity>
      </View>

      {/* Search Dropdown */}
      {showSearchDropdown && (
        <View style={[styles.searchDropdown, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
          <View style={[styles.searchInputContainer, { backgroundColor: colors.bg, borderColor: colors.border }]}>
            <Ionicons name="search" size={18} color={colors.textSecondary} style={styles.searchIcon} />
            <TextInput
              style={[styles.searchInput, { color: colors.text, backgroundColor: colors.bg }]}
              placeholder="Search users, posts, hashtags..."
              placeholderTextColor={colors.textSecondary}
              value={searchQuery}
              onChangeText={handleSearch}
              autoFocus
            />
            {searchQuery !== '' && (
              <TouchableOpacity onPress={clearSearch} style={styles.searchClearBtn}>
                <Ionicons name="close-circle" size={18} color={colors.textSecondary} />
              </TouchableOpacity>
            )}
          </View>
          
          {searchLoading ? (
            <View style={{ padding: 20, alignItems: 'center' }}>
              <ActivityIndicator size="small" color={colors.primary} />
              <Text style={[styles.searchLoadingText, { color: colors.textSecondary }]}>Searching...</Text>
            </View>
          ) : (searchResults.users?.length > 0 || searchResults.posts?.length > 0 || searchResults.hashtags?.length > 0) ? (
            <ScrollView showsVerticalScrollIndicator={false} style={{ maxHeight: 350 }}>
              {/* Users */}
              {searchResults.users?.length > 0 && (
                <View style={[styles.searchSection, { borderBottomColor: colors.border }]}>
                  <View style={styles.searchSectionHeader}>
                    <Ionicons name="person" size={14} color={colors.primary} />
                    <Text style={[styles.searchSectionTitle, { color: colors.text }]}>Users</Text>
                  </View>
                  {searchResults.users.map(user => (
                    <TouchableOpacity
                      key={user.id}
                      style={[styles.searchUserItem, { borderBottomColor: colors.border }]}
                      onPress={() => {
                        clearSearch();
                        navigation.navigate('Profile', { userId: user.id });
                      }}
                    >
                      <Avatar uri={user.profile_photo} size={36} name={user.username} />
                      <View style={{ marginLeft: 10, flex: 1 }}>
                        <Text style={[styles.searchUserName, { color: colors.text }]}>{user.username}</Text>
                        <Text style={[styles.searchUserFollowers, { color: colors.textSecondary }]}>
                          {user.followers_count || 0} followers
                        </Text>
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              
              {/* Hashtags */}
              {searchResults.hashtags?.length > 0 && (
                <View style={[styles.searchSection, { borderBottomColor: colors.border }, (searchResults.users?.length > 0) && styles.searchSectionBorder]}>
                  <View style={styles.searchSectionHeader}>
                    <Ionicons name="pricetag" size={14} color={colors.primary} />
                    <Text style={[styles.searchSectionTitle, { color: colors.text }]}>Hashtags</Text>
                  </View>
                  {searchResults.hashtags.map((tag, idx) => (
                    <TouchableOpacity
                      key={idx}
                      style={styles.searchHashtagItem}
                      onPress={() => {
                        clearSearch();
                        navigation.navigate('Explore', { hashtag: tag });
                      }}
                    >
                      <Text style={[styles.searchHashtagText, { color: colors.primary }]}>#{tag}</Text>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
              
              {/* Posts */}
              {searchResults.posts?.length > 0 && (
                <View style={[styles.searchSection, { borderBottomColor: colors.border }, (searchResults.users?.length > 0 || searchResults.hashtags?.length > 0) && styles.searchSectionBorder]}>
                  <View style={styles.searchSectionHeader}>
                    <Ionicons name="image" size={14} color={colors.primary} />
                    <Text style={[styles.searchSectionTitle, { color: colors.text }]}>Posts</Text>
                  </View>
                  {searchResults.posts.slice(0, 5).map(post => (
                    <TouchableOpacity
                      key={post.id}
                      style={[styles.searchPostItem, { borderBottomColor: colors.border }]}
                      onPress={() => {
                        clearSearch();
                        goToReel(post.id);
                      }}
                    >
                      <View style={{ flex: 1 }}>
                        <Text style={[styles.searchPostCaption, { color: colors.text }]} numberOfLines={2}>
                          {post.caption ? (post.caption.length > 60 ? post.caption.substring(0, 60) + '...' : post.caption) : 'No caption'}
                        </Text>
                        <Text style={[styles.searchPostUser, { color: colors.textSecondary }]}>
                          by @{post.user?.username} • {post.votes || 0} likes
                        </Text>
                      </View>
                    </TouchableOpacity>
                  ))}
                </View>
              )}
            </ScrollView>
          ) : searchQuery ? (
            <View style={{ padding: 20, alignItems: 'center' }}>
              <Text style={{ color: colors.textSecondary, fontSize: 14 }}>No results found</Text>
            </View>
          ) : null}
        </View>
      )}

      {/* Content */}
      {loading && posts.length === 0 ? (
        <View style={{ paddingTop: 8 }}>
          <SkeletonPost />
          <SkeletonPost />
          <SkeletonPost />
        </View>
      ) : activeTab === 'For You' ? (
        <FlatList
          ref={flatListRef}
          data={posts}
          keyExtractor={(p, index) => {
          // Ensure we always have a valid, unique key
          if (!p || !p.id) {
            return `post-${index}-${Date.now()}`;
          }
          // Handle suggestion items differently to avoid conflicts
          if (p.type === 'horizontal_suggestions' || p.type === 'suggestions') {
            return `suggestions-${p.id}`;
          }
          return `post-${p.id}`;
        }}
          renderItem={renderPost}
          scrollEventThrottle={16}
          refreshControl={
            <RefreshControl refreshing={refreshing} onRefresh={onRefresh} tintColor={colors.primary} />
          }
          onEndReached={onEndReached}
          onEndReachedThreshold={0.5}
          ListHeaderComponent={null}
          ListFooterComponent={loadingMore ? <ActivityIndicator color={colors.primary} style={{ padding: 16 }} /> : null}
          ListEmptyComponent={
            <View style={styles.centered}>
              <Text style={{ color: colors.textSecondary, fontSize: 16 }}>No posts yet</Text>
              <Text style={{ color: colors.textSecondary, marginTop: 8 }}>Be the first to share something!</Text>
            </View>
          }
          showsVerticalScrollIndicator={false}
          contentContainerStyle={{ paddingBottom: 80 + insets.bottom }}
          removeClippedSubviews={true}
          maxToRenderPerBatch={5}
          windowSize={3}
          initialNumToRender={3}
          updateCellsBatchingPeriod={50}
          disableIntervalMomentum={true}
          decelerationRate="normal"
          bounces={false}
          overScrollMode="never"
        />
      ) : null}

      {/* Share Toast */}
      {shareToast !== '' && (
        <View style={styles.toast}>
          <Text style={styles.toastText}>{shareToast}</Text>
        </View>
      )}

      {/* Post Info Modal */}
      {showPostInfoModal && (
        <Modal
          visible={!!showPostInfoModal}
          transparent
          animationType="fade"
          onRequestClose={() => setShowPostInfoModal(null)}
        >
          <TouchableOpacity
            style={styles.modalOverlay}
            activeOpacity={1}
            onPress={() => setShowPostInfoModal(null)}
          >
            <View style={styles.infoSheet}>
              <View style={styles.sheetHandle} />
              <View style={styles.sheetHeader}>
                <Text style={styles.sheetTitle}>Post Info</Text>
                <TouchableOpacity onPress={() => setShowPostInfoModal(null)}>
                  <Ionicons name="close" size={24} color="#fff" />
                </TouchableOpacity>
              </View>
              <View style={{ padding: 20 }}>
                <View style={{ flexDirection: 'row', alignItems: 'center', marginBottom: 16 }}>
                  <Avatar uri={showPostInfoModal.user?.profile_photo} size={44} name={showPostInfoModal.user?.username} />
                  <View style={{ marginLeft: 12 }}>
                    <Text style={{ color: GOLD, fontWeight: '700', fontSize: 16 }}>
                      @{showPostInfoModal.user?.username}
                    </Text>
                    <Text style={{ color: '#666', fontSize: 12 }}>
                      {showPostInfoModal.user?.first_name} {showPostInfoModal.user?.last_name || ''}
                    </Text>
                  </View>
                </View>
                <View style={{ flexDirection: 'row', justifyContent: 'space-around', marginBottom: 16 }}>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: '#666', fontSize: 12 }}>Likes</Text>
                    <Text style={{ color: '#fff', fontWeight: '700', fontSize: 18 }}>{showPostInfoModal.votes || 0}</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: '#666', fontSize: 12 }}>Comments</Text>
                    <Text style={{ color: '#fff', fontWeight: '700', fontSize: 18 }}>{showPostInfoModal.comment_count || 0}</Text>
                  </View>
                  <View style={{ alignItems: 'center' }}>
                    <Text style={{ color: '#666', fontSize: 12 }}>Views</Text>
                    <Text style={{ color: '#fff', fontWeight: '700', fontSize: 18 }}>{showPostInfoModal.view_count || 0}</Text>
                  </View>
                </View>
                <Text style={{ color: '#666', fontSize: 12, marginBottom: 8 }}>
                  {showPostInfoModal.media ? '🎬 Video' : '🖼️ Image'} · {timeAgo(showPostInfoModal.created_at)}
                </Text>
                {showPostInfoModal.caption && (
                  <Text style={{ color: '#fff', fontSize: 14, lineHeight: 1.5 }}>
                    <Text style={{ color: GOLD, fontWeight: '700' }}>@{showPostInfoModal.user?.username} </Text>
                    {showPostInfoModal.caption}
                  </Text>
                )}
              </View>
              <TouchableOpacity
                style={{ padding: 16, borderTopWidth: 1, borderTopColor: BORDER, alignItems: 'center' }}
                onPress={() => setShowPostInfoModal(null)}
              >
                <Text style={{ color: GOLD, fontWeight: '600' }}>Close</Text>
              </TouchableOpacity>
            </View>
          </TouchableOpacity>
        </Modal>
      )}

      {/* Post Options Modal */}
      <Modal
        visible={!!showOptions}
        transparent
        animationType="fade"
        onRequestClose={() => setShowOptions(null)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowOptions(null)}
        >
          <View style={[styles.optionsDropdown, { top: optionsPosition.y, left: optionsPosition.x }]}>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => showPostInfo(showOptions)}>
              <Ionicons name="information-circle-outline" size={18} color={GOLD} />
              <Text style={styles.dropdownText}>Post Info</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => copyPostLink(showOptions)}>
              <Ionicons name="link-outline" size={18} color={GOLD} />
              <Text style={styles.dropdownText}>Copy Link</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => toggleSave(showOptions)}>
              <Ionicons name="bookmark-outline" size={18} color={GOLD} />
              <Text style={styles.dropdownText}>{showOptions?.is_saved ? 'Saved' : 'Save to Favorites'}</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => downloadPost(showOptions)}>
              <Ionicons name="download-outline" size={18} color={GOLD} />
              <Text style={styles.dropdownText}>Download</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => reportPost(showOptions)}>
              <Ionicons name="eye-off-outline" size={18} color="#78716C" />
              <Text style={styles.dropdownText}>Not Interested</Text>
            </TouchableOpacity>
            <TouchableOpacity style={styles.dropdownItem} onPress={() => reportPost(showOptions)}>
              <Ionicons name="alert-circle-outline" size={18} color="#EF4444" />
              <Text style={[styles.dropdownText, { color: '#EF4444' }]}>Report</Text>
            </TouchableOpacity>
            {user?.id === showOptions?.user?.id && (
              <TouchableOpacity style={styles.dropdownItem} onPress={() => deletePost(showOptions)}>
                <Ionicons name="trash-outline" size={18} color="#EF4444" />
                <Text style={[styles.dropdownText, { color: '#EF4444' }]}>Delete Post</Text>
              </TouchableOpacity>
            )}
          </View>
        </TouchableOpacity>
      </Modal>

      {/* Comments Modal */}
      <Modal
        visible={!!commentPost}
        animationType="slide"
        transparent
        onRequestClose={() => setCommentPost(null)}
      >
        <KeyboardAvoidingView 
          behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
          keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 80}
          style={styles.modalOverlay}
        >
          <View style={styles.commentsSheet}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>Comments</Text>
              <TouchableOpacity onPress={() => setCommentPost(null)}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>
            <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
              {loadingComments ? (
                <View style={{ padding: 32, alignItems: 'center' }}>
                  <ActivityIndicator color={GOLD} />
                  <Text style={{ color: '#666', marginTop: 12 }}>Loading comments...</Text>
                </View>
              ) : comments.length === 0 ? (
                <Text style={{ color: '#666', textAlign: 'center', padding: 32 }}>
                  No comments yet. Be the first!
                </Text>
              ) : (
                <View style={{ padding: 12 }}>
                  {comments.map(c => (
                    <CommentItem key={c.id} comment={c} depth={0} />
                  ))}
                </View>
              )}
            </ScrollView>
            
            {/* Reply indicator */}
            {replyingTo && (
              <View style={{ flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 8, backgroundColor: CARD, borderBottomWidth: 1, borderBottomColor: BORDER }}>
                <Text style={{ color: colors.primary, fontSize: 12 }}>Replying to </Text>
                <Text style={{ color: colors.text, fontSize: 12, fontWeight: '600' }}>{replyingTo.user?.username}</Text>
                <TouchableOpacity onPress={() => setReplyingTo(null)} style={{ marginLeft: 'auto' }}>
                  <Ionicons name="close-circle" size={16} color={colors.textSecondary} />
                </TouchableOpacity>
              </View>
            )}
            
            <View style={styles.commentInput}>
              <Avatar uri={user?.profile_photo} size={32} name={user?.username} />
              <TextInput
                style={styles.commentTextInput}
                placeholder={replyingTo ? `Reply to ${replyingTo.user?.username}...` : "Add a comment..."}
                placeholderTextColor={colors.textSecondary}
                value={commentText}
                onChangeText={setCommentText}
                multiline
              />
              <TouchableOpacity
                onPress={() => setCommentText(prev => prev + '@')}
                style={styles.commentIconButton}
              >
                <Ionicons name="at" size={20} color={colors.primary} />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={() => openGiftModal(commentPost)}
                style={styles.commentIconButton}
              >
                <Ionicons name="gift" size={20} color={colors.primary} />
              </TouchableOpacity>
              <TouchableOpacity
                onPress={postComment}
                disabled={!commentText.trim() || postingComment}
              >
                {postingComment ? (
                  <ActivityIndicator size="small" color={colors.primary} />
                ) : (
                  <Ionicons
                    name="send"
                    size={22}
                    color={commentText.trim() ? colors.primary : colors.textSecondary}
                  />
                )}
              </TouchableOpacity>
            </View>
          </View>
        </KeyboardAvoidingView>
      </Modal>

      {/* Gift Modal */}
      <Modal
        visible={showGiftModal}
        transparent
        animationType="slide"
        onRequestClose={() => setShowGiftModal(false)}
      >
        <TouchableOpacity
          style={styles.modalOverlay}
          activeOpacity={1}
          onPress={() => setShowGiftModal(false)}
        >
          <TouchableOpacity style={styles.giftSheet} activeOpacity={1}>
            <View style={styles.sheetHandle} />
            <View style={styles.sheetHeader}>
              <Text style={styles.sheetTitle}>🎁 Gift to @{giftRecipient}</Text>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={styles.coinBalance}>🪙 {userCoins}</Text>
                  <Text style={styles.coinLabel}>Purchased Coins</Text>
                  <Text style={styles.giftLimitLabel}>{giftsSentToday}/{dailyGiftLimit} gifts today</Text>
                </View>
                <TouchableOpacity onPress={() => setShowGiftModal(false)}>
                  <Ionicons name="close" size={24} color="#fff" />
                </TouchableOpacity>
              </View>
            </View>

            {giftSent ? (
              <View style={{ alignItems: 'center', padding: 32 }}>
                <Text style={{ fontSize: 64, marginBottom: 12 }}>🎉</Text>
                <Text style={{ fontSize: 20, fontWeight: '800', color: GOLD, marginBottom: 4 }}>Gift Sent!</Text>
                <Text style={{ fontSize: 14, color: '#78716C', marginBottom: 24, textAlign: 'center' }}>
                  Your gift has been sent successfully
                </Text>
                <TouchableOpacity
                  style={styles.sendButton}
                  onPress={() => setShowGiftModal(false)}
                >
                  <Text style={styles.sendButtonText}>Done 🎊</Text>
                </TouchableOpacity>
              </View>
            ) : (
              <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
                {/* Category Filter */}
                <ScrollView
                  horizontal
                  showsHorizontalScrollIndicator={false}
                  style={styles.categoryFilter}
                  contentContainerStyle={{ paddingHorizontal: 12 }}
                >
                  {['all', ...new Set(gifts.map(g => g.category))].map(cat => (
                    <TouchableOpacity
                      key={cat}
                      style={[styles.categoryButton, selectedCategory === cat && styles.categoryButtonActive]}
                      onPress={() => setSelectedCategory(cat)}
                    >
                      <Text style={[styles.categoryButtonText, selectedCategory === cat && styles.categoryButtonTextActive]}>
                        {cat !== 'all' && CATEGORY_ICONS[cat]} {cat.charAt(0).toUpperCase() + cat.slice(1)}
                      </Text>
                    </TouchableOpacity>
                  ))}
                </ScrollView>

                {/* Gift Selection Grid */}
                <View style={styles.giftGrid}>
                  {(selectedCategory === 'all' ? gifts : gifts.filter(g => g.category === selectedCategory)).map(gift => (
                    <TouchableOpacity
                      key={gift.id}
                      style={[styles.giftItem, selectedGift?.id === gift.id && styles.giftItemActive]}
                      onPress={() => { setSelectedGift(gift); setGiftQuantity(1); }}
                    >
                      <Text style={styles.giftEmoji}>{gift.image_url ? '🎁' : (CATEGORY_ICONS[gift.category] || '🎁')}</Text>
                      <Text style={styles.giftCoinValue}>{gift.coin_value}🪙</Text>
                    </TouchableOpacity>
                  ))}
                </View>

                {/* Selected Gift Info & Quantity */}
                {selectedGift && (
                  <View style={styles.selectedGiftContainer}>
                    <Text style={styles.selectedGiftName}>{selectedGift.name}</Text>
                    <View style={styles.quantitySelector}>
                      <TouchableOpacity
                        style={styles.quantityButton}
                        onPress={() => setGiftQuantity(Math.max(1, giftQuantity - 1))}
                      >
                        <Text style={styles.quantityButtonText}>−</Text>
                      </TouchableOpacity>
                      <Text style={styles.quantityValue}>{giftQuantity}</Text>
                      <TouchableOpacity
                        style={styles.quantityButton}
                        onPress={() => setGiftQuantity(giftQuantity + 1)}
                      >
                        <Text style={styles.quantityButtonText}>+</Text>
                      </TouchableOpacity>
                    </View>
                  </View>
                )}

                {/* Message Input */}
                <Text style={styles.fieldLabel}>Message (optional)</Text>
                <TextInput
                  style={styles.input}
                  placeholder="Add a message..."
                  placeholderTextColor="#666"
                  value={giftMessage}
                  onChangeText={setGiftMessage}
                />

                {giftError ? <Text style={styles.errorText}>{giftError}</Text> : null}

                {/* Send Button */}
                <TouchableOpacity
                  style={[styles.sendButton, sendingGift && { opacity: 0.6 }]}
                  onPress={sendGift}
                  disabled={sendingGift || !selectedGift}
                >
                  {sendingGift ? (
                    <ActivityIndicator size="small" color="#000" />
                  ) : (
                    <Text style={styles.sendButtonText}>
                      Send Gift · 🪙 {selectedGift ? selectedGift.coin_value * giftQuantity : 0}
                    </Text>
                  )}
                </TouchableOpacity>
              </ScrollView>
            )}
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>

    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  searchIcon: {
    marginRight: 8,
  },
  searchInput: {
    flex: 1,
    color: '#000',
    fontSize: 14,
    paddingVertical: 10,
  },
  searchClearBtn: {
    padding: 4,
  },
  searchDropdown: {
    position: 'absolute',
    top: 70, // Below tabs
    left: 16,
    right: 16,
    backgroundColor: '#fff',
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 8,
    zIndex: 1000,
  },
  searchInputContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#f5f5f5',
    borderRadius: 8,
    margin: 12,
    paddingHorizontal: 12,
  },
  searchLoadingDropdown: {
    position: 'absolute',
    top: 120,
    left: 16,
    right: 16,
    backgroundColor: '#fff',
    borderRadius: 12,
    padding: 20,
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.2,
    shadowRadius: 8,
    elevation: 8,
    zIndex: 1000,
  },
  searchLoadingText: {
    color: '#666',
    fontSize: 13,
    marginTop: 8,
  },
  searchSection: {
    paddingVertical: 12,
  },
  searchSectionBorder: {
    borderTopWidth: 1,
    borderTopColor: '#e5e5e5',
  },
  searchSectionHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    paddingHorizontal: 16,
    paddingBottom: 8,
  },
  searchSectionTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: GOLD,
  },
  searchUserItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 10,
    paddingHorizontal: 16,
  },
  searchUserName: {
    color: '#000',
    fontSize: 14,
    fontWeight: '600',
  },
  searchUserFollowers: {
    color: '#666',
    fontSize: 12,
    marginTop: 2,
  },
  searchHashtagItem: {
    padding: 10,
    paddingHorizontal: 16,
  },
  searchHashtagText: {
    color: '#8fc441',
    fontSize: 14,
  },
  searchPostItem: {
    flexDirection: 'row',
    padding: 10,
    paddingHorizontal: 16,
  },
  searchPostCaption: {
    color: '#000',
    fontSize: 13,
    marginBottom: 4,
  },
  searchPostUser: {
    color: '#666',
    fontSize: 11,
  },
  headerTitle: { fontSize: 20, fontWeight: '900', color: GOLD },
  coinBalance: { fontSize: 16, fontWeight: '700', color: GOLD },
  coinLabel: { fontSize: 10, color: '#666', fontWeight: '600' },
  giftLimitLabel: { fontSize: 9, color: '#888', fontWeight: '500' },
  headerLogo: { width: 120, height: 30 },
  
  // Tab Navigation
  tabContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-evenly',
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderBottomWidth: 1,
  },
  tab: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    alignItems: 'center',
    minWidth: 80,
  },
  activeTab: {
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  tabText: {
    fontSize: 13,
    fontWeight: '600',
  },
  activeTabText: {
    color: '#000',
    fontWeight: '700',
  },
  searchIconBtn: {
    paddingVertical: 8,
    paddingHorizontal: 16,
    borderRadius: 20,
    backgroundColor: CARD,
    alignItems: 'center',
    justifyContent: 'center',
    minWidth: 50,
  },
  
  // Post Card
  postCard: { 
    backgroundColor: CARD, 
    marginHorizontal: 8,
    marginBottom: 16,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: BORDER,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  postHeader: {
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between', 
    padding: 12,
  },
  postUser: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  username: { fontSize: 14, fontWeight: '700', color: '#fff' },
  timeAgo: { fontSize: 12, color: LIGHT_GOLD, marginTop: 1 },
  followBtn: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: GOLD,
    borderRadius: 6,
    paddingVertical: 4,
    paddingHorizontal: 12,
  },
  headerOptionsBtn: {
    padding: 8,
    marginLeft: 8,
  },
  followingBtn: {
    backgroundColor: 'rgba(249,224,139,0.15)',
    borderColor: GOLD,
  },
  followBtnText: {
    color: GOLD,
    fontSize: 12,
    fontWeight: '700',
  },
  followingBtnText: {
    color: GOLD,
  },
  optionsBtn: {
    padding: 4,
  },
  
  // Caption
  captionContainer: {
    paddingHorizontal: 12,
    paddingBottom: 6,
  },
  caption: { 
    fontSize: 14, 
    color: '#ddd', 
    lineHeight: 18,
  },
  captionUsername: {
    fontWeight: '700',
    color: '#8fc441',
  },
  captionMore: {
    color: '#666',
    fontWeight: '600',
    fontSize: 12,
  },
  
  // Media
  mediaWrapper: { position: 'relative' },
  mediaImage: { 
    width: '100%', 
    minHeight: 200, 
    maxHeight: width * 1.2, 
    backgroundColor: '#111',
    aspectRatio: undefined, // Let image determine its own aspect ratio
  },
  playOverlay: {
    position: 'absolute', 
    top: 0, 
    left: 0, 
    right: 0, 
    bottom: 0,
    justifyContent: 'center', 
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.3)',
  },
  playBtn: {
    width: 56, 
    height: 56, 
    borderRadius: 28,
    backgroundColor: 'rgba(249,224,139,0.9)',
    justifyContent: 'center', 
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
  },
  videoContainer: {
    flex: 1,
    backgroundColor: '#2a2a2a',
    justifyContent: 'center',
    alignItems: 'center',
    minHeight: 200,
  },
  videoPlaceholderText: {
    color: '#C8B56A',
    fontSize: 18,
    fontWeight: '600',
    marginTop: 12,
  },
  viewBadge: {
    position: 'absolute',
    bottom: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.7)',
    borderRadius: 12,
    paddingHorizontal: 6,
    paddingVertical: 3,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  viewCount: {
    color: '#fff',
    fontSize: 11,
    fontWeight: '600',
  },
  
  // Actions
  actions: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between',
    paddingHorizontal: 12, 
    paddingVertical: 10,
  },
  leftActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
  },
  rightActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  actionBtn: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    paddingHorizontal: 6,
    paddingVertical: 4,
    borderRadius: 8,
  },
  actionCount: { 
    fontSize: 13, 
    color: LIGHT_GOLD, 
    marginLeft: 3,
    fontWeight: '600',
  },
  
  // Comments
  recentComments: {
    paddingHorizontal: 12,
    paddingBottom: 4,
  },
  recentComment: {
    fontSize: 12,
    color: '#ddd',
    lineHeight: 16,
  },
  commentUsername: {
    fontWeight: '700',
    color: '#8fc441',
  },
  commentsLink: {
    fontSize: 12,
    color: '#fff',
    paddingHorizontal: 12,
    paddingBottom: 8,
    fontWeight: '600',
  },
  
  // Hashtags
  hashtags: { 
    fontSize: 13, 
    color: '#8fc441', 
    paddingHorizontal: 12, 
    paddingBottom: 12, 
    fontWeight: '600', 
    lineHeight: 20,
  },
  
  // Modals
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.5)', justifyContent: 'flex-end' },
  optionsDropdown: {
    position: 'absolute',
    backgroundColor: CARD,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BORDER,
    minWidth: 180,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 8,
    elevation: 8,
    zIndex: 1000,
  },
  dropdownItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: 14,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  dropdownText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
  
  // Comments Modal
  commentsSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    height: '75%',
    paddingBottom: 20,
  },
  infoSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    maxHeight: '60%',
    marginTop: 'auto',
  },
  sheetHandle: { 
    width: 40, 
    height: 4, 
    backgroundColor: '#444', 
    borderRadius: 2, 
    alignSelf: 'center', 
    marginTop: 10 
  },
  sheetHeader: {
    flexDirection: 'row', 
    justifyContent: 'space-between', 
    alignItems: 'center',
    padding: 16, 
    borderBottomWidth: 1, 
    borderBottomColor: BORDER,
  },
  sheetTitle: { 
    fontSize: 16, 
    fontWeight: '700', 
    color: '#fff' 
  },
  commentItem: { 
    flexDirection: 'row', 
    padding: 12, 
    borderBottomWidth: 1, 
    borderBottomColor: '#1a1a1a' 
  },
  commentUser: { 
    fontSize: 13, 
    fontWeight: '700', 
    color: LIGHT_GOLD, 
    marginBottom: 2 
  },
  commentText: {
    fontSize: 14,
    color: '#fff',
    lineHeight: 18
  },

  // Gift Modal
  giftSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    height: '80%',
    paddingBottom: 20,
  },
  coinBalance: {
    fontSize: 13,
    fontWeight: '700',
    color: GOLD,
  },
  categoryFilter: {
    marginBottom: 12,
  },
  categoryButton: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: '#1a1a1a',
    marginRight: 6,
  },
  categoryButtonActive: {
    borderColor: GOLD,
    backgroundColor: 'rgba(249,224,139,0.15)',
  },
  categoryButtonText: {
    fontSize: 11,
    fontWeight: '600',
    color: '#888',
  },
  categoryButtonTextActive: {
    color: GOLD,
  },
  giftGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    paddingHorizontal: 12,
    marginBottom: 12,
  },
  giftItem: {
    width: '23%',
    aspectRatio: 1,
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: BORDER,
    backgroundColor: '#1a1a1a',
    alignItems: 'center',
    justifyContent: 'center',
    margin: '1%',
  },
  giftItemActive: {
    borderColor: GOLD,
    backgroundColor: 'rgba(249,224,139,0.15)',
  },
  giftEmoji: {
    fontSize: 24,
    marginBottom: 4,
  },
  giftCoinValue: {
    fontSize: 11,
    fontWeight: '700',
    color: GOLD,
  },
  selectedGiftContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 12,
    paddingVertical: 10,
    backgroundColor: '#1a1a1a',
    borderRadius: 10,
    borderWidth: 1,
    borderColor: BORDER,
    marginHorizontal: 12,
    marginBottom: 12,
  },
  selectedGiftName: {
    fontSize: 13,
    fontWeight: '600',
    color: '#fff',
  },
  quantitySelector: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  quantityButton: {
    width: 28,
    height: 28,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: CARD,
    justifyContent: 'center',
    alignItems: 'center',
  },
  quantityButtonText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
  },
  quantityValue: {
    minWidth: 20,
    textAlign: 'center',
    fontSize: 14,
    fontWeight: '700',
    color: '#fff',
  },
  fieldLabel: {
    fontSize: 13,
    fontWeight: '600',
    color: '#aaa',
    marginBottom: 8,
    marginTop: 12,
    paddingHorizontal: 12,
  },
  input: {
    backgroundColor: '#1a1a1a',
    borderRadius: 12,
    padding: 14,
    color: '#fff',
    fontSize: 15,
    borderWidth: 1,
    borderColor: BORDER,
    marginHorizontal: 12,
  },
  errorText: {
    color: '#EF4444',
    fontSize: 13,
    marginBottom: 12,
    padding: 10,
    backgroundColor: '#FEF2F2',
    borderRadius: 10,
    marginHorizontal: 12,
  },
  sendButton: {
    width: '92%',
    padding: 14,
    borderRadius: 12,
    backgroundColor: GOLD,
    marginTop: 16,
    alignSelf: 'center',
  },
  sendButtonText: {
    color: '#000',
    fontSize: 14,
    fontWeight: '700',
    textAlign: 'center',
  },
  commentInput: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 12,
    borderTopWidth: 1,
    borderTopColor: BORDER,
    gap: 10,
  },
  commentTextInput: {
    flex: 1,
    backgroundColor: '#1a1a1a',
    borderRadius: 20,
    paddingHorizontal: 14,
    paddingVertical: 8,
    color: '#fff',
    fontSize: 14,
  },
  commentIconButton: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: 'rgba(249,224,139,0.1)',
    justifyContent: 'center',
    alignItems: 'center',
  },

  // Toast
  toast: {
    position: 'absolute',
    bottom: 80,
    left: width / 2 - 60,
    backgroundColor: 'rgba(0,0,0,0.8)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
    alignItems: 'center',
  },
  toastText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '600',
  },
});


