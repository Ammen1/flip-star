import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import {
  View, Text, FlatList, StyleSheet, TouchableOpacity, Image,
  Dimensions, ActivityIndicator, StatusBar, TextInput, Modal,
  ScrollView, Alert, Animated, RefreshControl, Share, Platform,
  KeyboardAvoidingView,
} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import { useVideoPlayer, VideoView } from 'expo-video';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import { useBlock } from '../contexts/BlockContext';
import api from '../api';
import config from '../config';
import SoundManager from '../utils/SoundUtils';

const MEDIA_BASE = config.API_BASE_URL.replace('/api', '');

const { width, height } = Dimensions.get('window');
const GOLD = '#8fc441';
const BRAND_GREEN = '#8fc441';
const DARK_GOLD = '#6ba835';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const LIGHT_GOLD = '#b5dd8f';
const BORDER = '#262626';

// Helper to shuffle array for randomized feed
const shuffleArray = (array) => {
  const newArr = [...array];
  for (let i = newArr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArr[i], newArr[j]] = [newArr[j], newArr[i]];
  }
  return newArr;
};

// CaptionWithLessMore component for truncating long captions
const CaptionWithLessMore = React.memo(({ caption, maxLength = 100 }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  if (!caption || caption.length <= maxLength) {
    return <Text style={styles.caption}>{caption}</Text>;
  }
  
  return (
    <View>
      <Text style={styles.caption}>
        {isExpanded ? caption : caption.slice(0, maxLength) + '...'}
        <Text
          style={styles.moreLessBtn}
          onPress={() => setIsExpanded(!isExpanded)}
        >
          {isExpanded ? ' less' : ' more'}
        </Text>
      </Text>
    </View>
  );
});

function timeAgo(d) {
  if (!d) return '';
  const s = (Date.now() - new Date(d)) / 1000;
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

const Avatar = React.memo(({ uri, size = 36, name = '', showBorder = false }) => {
  const [err, setErr] = useState(false);
  const safeName = name || '?';
  if (uri && !err) {
    return (
      <Image
        source={{ uri }}
        style={{ 
          width: size, 
          height: size, 
          borderRadius: size / 2,
          borderWidth: showBorder ? 2 : 0,
          borderColor: GOLD
        }}
        onError={() => setErr(true)}
      />
    );
  }
  return (
    <View style={{ 
      width: size, 
      height: size, 
      borderRadius: size / 2, 
      backgroundColor: GOLD, 
      justifyContent: 'center', 
      alignItems: 'center',
      borderWidth: showBorder ? 2 : 0,
      borderColor: '#fff'
    }}>
      <Text style={{ color: '#000', fontWeight: '700', fontSize: size * 0.4 }}>
        {safeName[0].toUpperCase()}
      </Text>
    </View>
  );
});

// Enhanced ReelItem component matching website's TikTok-style layout
const ReelItem = React.memo(function ReelItem({ 
  item, 
  isActive, 
  onLike, 
  onComment, 
  onSave, 
  onFollow,
  onShare,
  onReport,
  onShowProfile,
  onNavigate,
  onOpenGiftModal,
  followStates,
  user,
  index,
  videos,
  setVideos,
  fromDeepLink,
  localShareCounts
}) {
  const [showPauseIcon, setShowPauseIcon] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [showReportModal, setShowReportModal] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [showLongPressMenu, setShowLongPressMenu] = useState(null);
  const [likeAnimation, setLikeAnimation] = useState(false);
  const [doubleTapLike, setDoubleTapLike] = useState(false);
  const longPressTimer = useRef(null);
  
  const lastTapRef = useRef(0);
  const DOUBLE_TAP_WINDOW = 280;

  const isVideo = !!(item.media);
  const videoUri = item.media
    ? (item.media.startsWith('http') ? item.media : `${MEDIA_BASE}${item.media}`)
    : null;

  // Check if this is a campaign post
  const isCampaignPost = item.is_campaign || item.campaign_id || item.campaign || item.competition;
  console.log('Post data:', { 
    id: item.id, 
    is_campaign: item.is_campaign, 
    campaign_id: item.campaign_id, 
    campaign: item.campaign,
    competition: item.competition,
    isCampaignPost 
  });

  // Use expo-video player
  const player = useVideoPlayer(videoUri, player => {
    player.loop = true;
    player.muted = false; // Start unmuted by default
  });

  const [isMuted, setIsMuted] = useState(false); // Track mute state for UI

  // Auto-play when video becomes active
  useEffect(() => {
    if (!player) return;
    
    console.log('Video', item.id, 'isActive:', isActive);
    
    try {
      if (isActive) {
        player.play();
      } else {
        player.pause();
        player.muted = true; // Mute when not active to prevent sound leaking
      }
    } catch (error) {
      // Player might be released, ignore error
      console.log('Player control error (safe to ignore):', error.message);
    }
  }, [isActive, player]);

  // Cleanup: pause and mute when component unmounts
  useEffect(() => {
    return () => {
      try {
        if (player) {
          player.pause();
          player.muted = true;
        }
      } catch (error) {
        // Player already released, ignore
      }
    };
  }, [player]);

  const handleVideoTouch = () => {
    const now = Date.now();
    const last = lastTapRef.current || 0;
    
    if (now - last < DOUBLE_TAP_WINDOW) {
      lastTapRef.current = 0;
      handleDoubleTap();
    } else {
      lastTapRef.current = now;
      if (isVideo && player) {
        if (player.playing) {
          player.pause();
          setShowPauseIcon(true);
          setTimeout(() => setShowPauseIcon(false), 600);
        } else {
          player.play();
        }
      }
    }
  };

  const handleDoubleTap = () => {
    if (!user) return;
    
    // Trigger like animation
    setDoubleTapLike(true);
    setTimeout(() => setDoubleTapLike(false), 1000);
    
    // Like the video if not already liked
    if (!item.is_liked) {
      onLike();
    }
  };

  const handleLike = async () => {
    if (!user) return;
    
    setLikeAnimation(true);
    setTimeout(() => setLikeAnimation(false), 400);
    
    // Optimistic UI update
    const newLiked = !item.is_liked;
    const newLikes = newLiked ? item.votes + 1 : Math.max(0, item.votes - 1);
    
    // Update local state immediately
    if (setVideos) {
      setVideos(prev => prev.map(v => 
        v.id === item.id 
          ? { ...v, is_liked: newLiked, votes: newLikes }
          : v
      ));
    }
    
    try {
      await api.request(`/reels/${item.id}/vote/`, { method: 'POST' });
    } catch (error) {
      // Revert on error
      if (setVideos) {
        setVideos(prev => prev.map(v => 
          v.id === item.id 
            ? { ...v, is_liked: item.is_liked, votes: item.votes }
            : v
        ));
      }
    }
  };

  const handleSave = async () => {
    if (!user) return;
    
    const newSaved = !item.is_saved;
    
    // Update local state immediately
    if (setVideos) {
      setVideos(prev => prev.map(v => 
        v.id === item.id 
          ? { ...v, is_saved: newSaved }
          : v
      ));
    }
    
    try {
      await api.request(`/reels/${item.id}/save/`, { method: 'POST' });
    } catch (error) {
      // Revert on error
      if (setVideos) {
        setVideos(prev => prev.map(v => 
          v.id === item.id 
            ? { ...v, is_saved: item.is_saved }
            : v
        ));
      }
    }
  };

  
  const handleComment = () => {
    setShowComments(true);
  };

  const handleReport = () => {
    setShowReportModal(true);
  };

  const handleShareVideo = async () => {
    // Use both web URL and app URL for better compatibility
    const webUrl = `https://uat.flipstar.et/post/${item.id}`;
    const appUrl = `flipstar://post/${item.id}`;
    const title = item.caption ? item.caption.slice(0, 80) : 'Check out this reel on FlipStar';
    
    try {
      await Share.share({
        message: `${title}\n\n${webUrl}\n\nOr open in app: ${appUrl}`,
        title: 'FlipStar Reel',
        url: webUrl,
      });
      
      // Increment share count
      try {
        console.log('Before share - item shares:', item.shares);
        console.log('Before share - localShareCounts:', localShareCounts[item.id]);
        
        await api.request(`/reels/${item.id}/share/`, { method: 'POST' });
        
        // Update persistent local share count
        setLocalShareCounts(prev => {
          const updated = {
            ...prev,
            [item.id]: (prev[item.id] || 0) + 1
          };
          console.log('Updated localShareCounts:', updated[item.id]);
          return updated;
        });
        
        // Update local share count
        setVideos(prev => {
          const updated = prev.map(v => 
            v.id === item.id ? { ...v, shares: (v.shares || 0) + 1 } : v
          );
          console.log('Updated videos share count for item', item.id);
          return updated;
        });
        
        console.log('Share increment successful');
      } catch (error) {
        console.log('Share increment failed:', error);
      }
    } catch (error) {
      console.log('Share error:', error);
    }
    setShowMenu(false);
  };

  // Long-press handlers for TikTok-style context menu
  const handleLongPressStart = () => {
    longPressTimer.current = setTimeout(() => {
      setShowMenu(null);
      setShowLongPressMenu({ videoId: item.id });
    }, 500);
  };

  const handleLongPressEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const handleLongPressMove = () => {
    handleLongPressEnd();
  };

  // Download video functionality
  const handleDownload = async () => {
    setShowLongPressMenu(null);
    setShowMenu(null);
    
    if (!user) {
      Alert.alert('Login Required', 'Please login to download videos');
      return;
    }
    
    let mediaUrl = item.media;
    
    // Apply Cloudinary transformations for smaller file size
    if (mediaUrl?.includes('cloudinary.com')) {
      if (mediaUrl.includes('/video/upload/')) {
        mediaUrl = mediaUrl.replace(
          '/video/upload/',
          '/video/upload/h_720,q_70,vc_h264/'
        );
      } else if (mediaUrl.includes('/image/upload/')) {
        mediaUrl = mediaUrl.replace(
          '/image/upload/',
          '/image/upload/h_1080,q_80,f_jpg/'
        );
      }
    }
    
    try {
      Alert.alert('Downloading', 'Preparing download...');
      
      const response = await fetch(mediaUrl);
      const blob = await response.blob();
      
      // For React Native, we need to use a different approach
      // This is a simplified version - in production you'd use expo-file-system
      Alert.alert('Download', 'Download feature requires expo-file-system');
    } catch (err) {
      console.error('Download failed:', err);
      Alert.alert('Download Failed', 'Could not download the video. Please try again.');
    }
  };

  // Save to favorites
  const handleSaveToFavorites = async () => {
    setShowLongPressMenu(null);
    setShowMenu(null);
    
    if (!user) {
      Alert.alert('Login Required', 'Please login to save to favorites');
      return;
    }
    
    try {
      await api.request(`/saved/`, {
        method: 'POST',
        body: JSON.stringify({ reel: item.id }),
      });
      Alert.alert('Success', 'Saved to favorites!');
    } catch (err) {
      console.error('Save failed:', err);
    }
  };

  // Delete own reel
  const handleDelete = () => {
    setShowMenu(false);
    Alert.alert('Delete Reel', 'Are you sure you want to delete this reel?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          try {
            await api.request(`/reels/${item.id}/`, { method: 'DELETE' });
            if (setVideos) setVideos(prev => prev.filter(v => v.id !== item.id));
          } catch {
            Alert.alert('Error', 'Failed to delete reel');
          }
        },
      },
    ]);
  };

  // Not interested
  const handleNotInterested = async () => {
    setShowLongPressMenu(null);
    setShowMenu(null);
    
    try {
      await api.request('/reels/not-interested/', {
        method: 'POST',
        body: JSON.stringify({ reel_id: item.id }),
      });
      // Remove video from feed locally
      if (setVideos) {
        setVideos(prev => prev.filter(v => v.id !== item.id));
      }
      Alert.alert('Video Removed', "This video won't appear in your feed anymore.");
    } catch (error) {
      console.error('Failed to mark not interested:', error);
      // Still remove from local feed even if API fails
      if (setVideos) {
        setVideos(prev => prev.filter(v => v.id !== item.id));
      }
    }
  };

  // Show video info
  const handleShowVideoInfo = () => {
    setShowLongPressMenu(null);
    setShowMenu(null);
    
    Alert.alert(
      'Video Information',
      `Creator: ${item.user?.username}\nLikes: ${item.votes}\nComments: ${item.comment_count}\nPosted: ${timeAgo(item.created_at)}`,
      [{ text: 'OK' }]
    );
  };

  // Handle hashtag click to search
  const handleHashtagClick = async (hashtag) => {
    if (!hashtag) return;
    const cleanTag = hashtag.startsWith('#') ? hashtag.slice(1) : hashtag;
    try {
      const response = await api.request(`/reels/hashtag/${cleanTag}/`);
      const results = response.results || response || [];
      
      // Navigate to explore with hashtag filter
      // For now, just update the current feed with hashtag results
      if (setVideos) {
        const filteredResults = results.filter(reel => {
          if (!reel.media) return false;
          const isVideoFile = /\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(reel.media) || 
                              reel.media.includes('/video/upload/');
          return isVideoFile;
        });
        setVideos(shuffleArray(filteredResults));
      }
    } catch (error) {
      console.error('Failed to search hashtag:', error);
      Alert.alert('Error', 'Failed to load hashtag posts');
    }
  };

  const isOwnPost = user?.id === item.user?.id;
  const isFollowing = item.user?.is_following || followStates[item.user?.id] || false;

  const handleFollowUser = () => {
    if (item.user?.id && onFollow) {
      onFollow(item.user.id);
    }
  };

  return (
    <View style={styles.reelContainer}>
      {/* Video Background */}
      <View style={[StyleSheet.absoluteFill, { backgroundColor: '#000' }]}>
        {videoUri && player ? (
          <VideoView
            player={player}
            style={{ flex: 1 }}
            contentFit="contain"
            nativeControls={false}
          />
        ) : (
          <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
            <Text style={{ color: '#fff' }}>No video</Text>
          </View>
        )}
      </View>
      
      <TouchableOpacity
        style={StyleSheet.absoluteFill}
        onPress={handleVideoTouch}
        onLongPress={handleLongPressStart}
        onPressOut={handleLongPressEnd}
        onMoveShouldSetResponder={handleLongPressMove}
        activeOpacity={1}
        delayLongPress={500}
      >

        {/* Pause Icon Overlay - Cleaner design */}
        {showPauseIcon && isVideo && (
          <View style={[StyleSheet.absoluteFill, { justifyContent: 'center', alignItems: 'center', pointerEvents: 'none' }]}>
            <View style={styles.pauseIconContainer}>
              <Ionicons name="pause" size={40} color="#fff" />
            </View>
          </View>
        )}

        {/* Double Tap Heart Animation */}
        {doubleTapLike && (
          <View style={[StyleSheet.absoluteFill, { justifyContent: 'center', alignItems: 'center', pointerEvents: 'none' }]}>
            <Animated.View style={styles.doubleTapHeart}>
              <Ionicons 
                name={isCampaignPost ? "trophy" : "heart"} 
                size={100} 
                color="#fff" 
              />
            </Animated.View>
          </View>
        )}
      </TouchableOpacity>

      {/* Dark gradient overlay */}
      <View style={styles.gradient} pointerEvents="none" />


      {/* Right Side Actions */}
      <View style={styles.rightActions}>
        {/* Avatar with Follow Button */}
        <View style={styles.avatarContainer}>
          <TouchableOpacity onPress={() => onShowProfile?.(item.user?.id)}>
            <Avatar 
              uri={item.user?.profile_photo?.startsWith('http') 
                ? item.user.profile_photo 
                : item.user?.profile_photo 
                  ? `${MEDIA_BASE}${item.user.profile_photo}` 
                  : null
              } 
              size={48} 
              name={item.user?.username} 
              showBorder={true} 
            />
          </TouchableOpacity>
          {!isOwnPost && (
            <TouchableOpacity 
              style={[
                styles.followBadge, 
                isFollowing && styles.followingBadge
              ]} 
              onPress={handleFollowUser}
            >
              {isFollowing ? (
                <Ionicons name="checkmark" size={14} color="#fff" />
              ) : (
                <Ionicons name="add" size={14} color="#000" />
              )}
            </TouchableOpacity>
          )}
        </View>

        {/* Sound Toggle Button */}
        <TouchableOpacity 
          style={[
            styles.actionItem,
            fromDeepLink && styles.deepLinkSoundButton // Enhanced style for deep link
          ]} 
          onPress={() => {
            if (player) {
              const newMuted = !isMuted;
              setIsMuted(newMuted);
              player.muted = newMuted;
              console.log('Sound toggled:', newMuted ? 'muted' : 'unmuted');
            }
          }}
        >
          <View style={styles.actionIconRow}>
            <Ionicons 
              name={isMuted ? 'volume-mute' : 'volume-high'}
              size={fromDeepLink ? 32 : 28} // Larger icon for deep link
              color={fromDeepLink ? BRAND_GREEN : DARK_GOLD} // Use brand green for deep link
              style={styles.iconShadow}
            />
            {fromDeepLink && (
              <Text style={styles.soundButtonText}>
                {isMuted ? 'Sound Off' : 'Sound On'}
              </Text>
            )}
          </View>
        </TouchableOpacity>

        {/* Like Button */}
        <TouchableOpacity style={styles.actionItem} onPress={handleLike}>
          <View style={[
            styles.actionIconRow,
            likeAnimation && styles.likeAnimation
          ]}>
            <Ionicons 
              name={
                isCampaignPost 
                  ? (item.is_liked ? 'trophy' : 'trophy-outline')
                  : (item.is_liked ? 'heart' : 'heart-outline')
              }
              size={28}
              color={item.is_liked ? '#EF4444' : DARK_GOLD}
              fill={item.is_liked ? '#EF4444' : 'none'}
              style={styles.iconShadow}
            />
            <Text style={styles.actionLabelInline}>{(item.votes || 0) + 1}</Text>
          </View>
        </TouchableOpacity>

        {/* Comment Button */}
        <TouchableOpacity style={styles.actionItem} onPress={() => setShowComments(true)}>
          <View style={styles.actionIconRow}>
            <Ionicons name="chatbubble-outline" size={26} color={DARK_GOLD} style={styles.iconShadow} />
            <Text style={styles.actionLabelInline}>{(item.comment_count || 0) + 1}</Text>
          </View>
        </TouchableOpacity>

        {/* Share Button */}
        <TouchableOpacity style={styles.actionItem} onPress={handleShareVideo}>
          <View style={styles.actionIconRow}>
            <Ionicons name="share-outline" size={26} color={DARK_GOLD} style={styles.iconShadow} />
            <Text style={styles.actionLabelInline}>
          {(() => {
            const shares = item.shares || 0;
            const localShares = localShareCounts[item.id] || 0;
            const total = shares + localShares;
            console.log('Share display - item:', item.id, 'shares:', shares, 'localShares:', localShares, 'total:', total);
            return total;
          })()}
        </Text>
          </View>
        </TouchableOpacity>

        {/* Save Button */}
        <TouchableOpacity style={styles.actionItem} onPress={handleSave}>
          <View style={styles.actionIconRow}>
            <Ionicons 
              name={item.is_saved ? 'bookmark' : 'bookmark-outline'}
              size={26}
              color={item.is_saved ? LIGHT_GOLD : DARK_GOLD}
              style={styles.iconShadow}
            />
          </View>
        </TouchableOpacity>

        {/* Gift Button */}
        <TouchableOpacity style={styles.actionItem} onPress={() => onOpenGiftModal(item.user)}>
          <View style={styles.actionIconRow}>
            <Ionicons name="gift-outline" size={26} color={DARK_GOLD} style={styles.iconShadow} />
          </View>
        </TouchableOpacity>

        </View>

      {/* Bottom Info */}
      <View style={styles.bottomInfo}>
        <TouchableOpacity 
          style={styles.userInfo}
          onPress={() => onShowProfile?.(item.user?.id)}
        >
          <Text style={styles.username}>@{item.user?.username}</Text>
          {item.user?.verified && (
            <Ionicons name="checkmark-circle" size={14} color={LIGHT_GOLD} />
          )}
        </TouchableOpacity>
        
        {/* Caption with expand/collapse */}
        {item.caption && (
          <CaptionWithLessMore caption={item.caption} maxLength={100} />
        )}
        
        {/* Hashtags */}
        {item.hashtags && (
          <View style={styles.hashtagsContainer}>
            {String(item.hashtags).split(/[\s,]+/).filter(Boolean)
              .slice(0, 3)
              .map((tag, idx) => (
                <TouchableOpacity key={idx} onPress={() => handleHashtagClick(tag)}>
                  <Text style={styles.hashtag}>
                    {tag.startsWith('#') ? tag : `#${tag}`}
                  </Text>
                </TouchableOpacity>
              ))}
          </View>
        )}
        
        {/* Music/Track Info */}
        {item.music && (
          <View style={styles.musicInfo}>
            <Ionicons name="musical-note" size={12} color={LIGHT_GOLD} />
            <Text style={styles.musicText}>{item.music}</Text>
          </View>
        )}
      </View>

      {/* Comments Modal */}
      <Modal
        visible={showComments}
        animationType="slide"
        transparent
        onRequestClose={() => setShowComments(false)}
      >
        <CommentsModal 
          reel={item}
          user={user}
          onClose={() => setShowComments(false)}
          onOpenGiftModal={openGiftModal}
          onShare={handleShareVideo}
          onLike={handleLike}
        />
      </Modal>

      {/* Report Modal */}
      <Modal
        visible={showReportModal}
        transparent
        animationType="fade"
        onRequestClose={() => setShowReportModal(false)}
      >
        <ReportModal 
          reel={item}
          onClose={() => setShowReportModal(false)}
        />
      </Modal>

      {/* Long-Press Context Menu */}
      {showLongPressMenu && (
        <Modal
          visible={!!showLongPressMenu}
          transparent
          animationType="slide"
          onRequestClose={() => setShowLongPressMenu(null)}
        >
          <TouchableOpacity 
            style={styles.modalOverlay}
            activeOpacity={1}
            onPress={() => setShowLongPressMenu(null)}
          >
            <View style={styles.longPressSheet}>
              <View style={styles.sheetHandle} />
              <View style={styles.sheetHeader}>
                <Text style={styles.sheetTitle}>Options</Text>
                <TouchableOpacity onPress={() => setShowLongPressMenu(null)}>
                  <Ionicons name="close" size={24} color="#fff" />
                </TouchableOpacity>
              </View>
              
              <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
                <TouchableOpacity style={styles.longPressMenuItem} onPress={handleDownload}>
                  <Ionicons name="download-outline" size={20} color={LIGHT_GOLD} />
                  <Text style={styles.longPressMenuText}>Download</Text>
                </TouchableOpacity>
                
                <TouchableOpacity style={styles.longPressMenuItem} onPress={handleSaveToFavorites}>
                  <Ionicons name="star-outline" size={20} color={LIGHT_GOLD} />
                  <Text style={styles.longPressMenuText}>Save to Favorites</Text>
                </TouchableOpacity>
                
                <TouchableOpacity style={styles.longPressMenuItem} onPress={handleShareVideo}>
                  <Ionicons name="share-outline" size={20} color={LIGHT_GOLD} />
                  <Text style={styles.longPressMenuText}>Share</Text>
                </TouchableOpacity>
                
                <TouchableOpacity style={styles.longPressMenuItem} onPress={handleNotInterested}>
                  <Ionicons name="eye-off-outline" size={20} color="#EF4444" />
                  <Text style={[styles.longPressMenuText, { color: '#EF4444' }]}>Not Interested</Text>
                </TouchableOpacity>
                
                <TouchableOpacity style={styles.longPressMenuItem} onPress={handleShowVideoInfo}>
                  <Ionicons name="information-circle-outline" size={20} color={LIGHT_GOLD} />
                  <Text style={styles.longPressMenuText}>Video Info</Text>
                </TouchableOpacity>
                
                <TouchableOpacity 
                  style={styles.longPressMenuItem} 
                  onPress={() => { setShowLongPressMenu(null); setShowReportModal(true); }}
                >
                  <Ionicons name="flag-outline" size={20} color="#EF4444" />
                  <Text style={[styles.longPressMenuText, { color: '#EF4444' }]}>Report</Text>
                </TouchableOpacity>
              </ScrollView>
            </View>
          </TouchableOpacity>
        </Modal>
      )}
    </View>
  );
});

// Comments Modal Component
const CommentsModal = React.memo(function CommentsModal({ reel, user, onClose, onOpenGiftModal, onShare, onLike }) {
  const [comments, setComments] = useState([]);
  const [commentText, setCommentText] = useState('');
  const [postingComment, setPostingComment] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadComments();
  }, []);

  const loadComments = async () => {
    try {
      setLoading(true);
      const data = await api.request(`/reels/${reel.id}/comments/?include_replies=true`);
      setComments(Array.isArray(data) ? data : (data.results || []));
    } catch (error) {
      console.error('Failed to load comments:', error);
      setComments([]);
    } finally {
      setLoading(false);
    }
  };

  const postComment = async () => {
    if (!commentText.trim() || !user) return;
    
    setPostingComment(true);
    try {
      const c = await api.request(`/reels/${reel.id}/comments/`, {
        method: 'POST', 
        body: JSON.stringify({ text: commentText.trim() }),
      });
      setComments(prev => [c, ...prev]);
      setCommentText('');
    } catch (error) {
      Alert.alert('Error', 'Failed to post comment');
    } finally {
      setPostingComment(false);
    }
  };

  return (
    <KeyboardAvoidingView 
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 0 : 80}
      style={styles.modalOverlay}
    >
      <View style={styles.commentsSheet}>
        <View style={styles.sheetHandle} />
        <View style={styles.sheetHeader}>
          <View style={styles.sheetHeaderLeft}>
            <Text style={styles.sheetTitle}>Comments</Text>
            <View style={styles.sheetActions}>
              <TouchableOpacity 
                onPress={() => onLike && onLike(reel)} 
                style={styles.sheetActionButton}
              >
                <Ionicons 
                  name={reel.is_liked ? "heart" : "heart-outline"} 
                  size={20} 
                  color={reel.is_liked ? "#ff6b6b" : "#fff"} 
                />
              </TouchableOpacity>
              <TouchableOpacity 
                onPress={() => onShare && onShare(reel)} 
                style={styles.sheetActionButton}
              >
                <Ionicons 
                  name="share-outline" 
                  size={20} 
                  color="#fff" 
                />
              </TouchableOpacity>
            </View>
          </View>
          <TouchableOpacity onPress={onClose}>
            <Ionicons name="close" size={24} color="#fff" />
          </TouchableOpacity>
        </View>
        
        <ScrollView style={{ flex: 1 }} showsVerticalScrollIndicator={false}>
          {loading ? (
            <View style={{ padding: 32, alignItems: 'center' }}>
              <ActivityIndicator size="small" color={GOLD} />
            </View>
          ) : comments.length === 0 ? (
            <Text style={{ color: '#666', textAlign: 'center', padding: 32 }}>
              No comments yet
            </Text>
          ) : (
            comments.map(c => (
              <View key={c.id} style={styles.commentItem}>
                <Avatar 
                  uri={c.user?.profile_photo?.startsWith('http') 
                    ? c.user.profile_photo 
                    : c.user?.profile_photo 
                      ? `${MEDIA_BASE}${c.user.profile_photo}` 
                      : null
                  } 
                  size={32} 
                  name={c.user?.username} 
                />
                <View style={{ flex: 1, marginLeft: 10 }}>
                  <Text style={styles.commentUser}>{c.user?.username}</Text>
                  <Text style={styles.commentText}>{c.text}</Text>
                </View>
              </View>
            ))
          )}
        </ScrollView>
        
        <View style={styles.commentInput}>
          <Avatar 
            uri={user?.profile_photo?.startsWith('http') 
              ? user.profile_photo 
              : user?.profile_photo 
                ? `${MEDIA_BASE}${user.profile_photo}` 
                : null
            } 
            size={32} 
            name={user?.username} 
          />
          <TextInput
            style={styles.commentTextInput}
            placeholder="Add a comment..."
            placeholderTextColor="#666"
            value={commentText}
            onChangeText={setCommentText}
            multiline
          />
          <TouchableOpacity 
            onPress={() => onOpenGiftModal && onOpenGiftModal(reel.user)} 
            style={{ marginRight: 8 }}
          >
            <Ionicons 
              name="gift-outline" 
              size={22} 
              color={GOLD} 
            />
          </TouchableOpacity>
          <TouchableOpacity 
            onPress={postComment} 
            disabled={!commentText.trim() || postingComment}
          >
            {postingComment ? (
              <ActivityIndicator size="small" color={GOLD} />
            ) : (
              <Ionicons 
                name="send" 
                size={22} 
                color={commentText.trim() ? GOLD : '#444'} 
              />
            )}
          </TouchableOpacity>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
});

// Report Modal Component
function ReportModal({ reel, onClose }) {
  const { colors } = useTheme();
  const [selectedReason, setSelectedReason] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const reportReasons = [
    { id: 'spam', label: 'Spam', icon: 'alert-circle-outline', description: 'Unwanted or repetitive content' },
    { id: 'inappropriate', label: 'Inappropriate Content', icon: 'warning-outline', description: 'Offensive or harmful content' },
    { id: 'harassment', label: 'Harassment', icon: 'person-outline', description: 'Bullying or targeting individuals' },
    { id: 'copyright', label: 'Copyright Violation', icon: 'lock-closed-outline', description: 'Using someone else\'s content' },
    { id: 'violence', label: 'Violence', icon: 'flash-outline', description: 'Violent or dangerous content' },
    { id: 'other', label: 'Other', icon: 'ellipsis-horizontal-outline', description: 'Other issues not listed' },
  ];

  const submitReport = useCallback(async () => {
    if (!selectedReason) {
      Alert.alert('Error', 'Please select a reason for reporting');
      return;
    }

    setSubmitting(true);
    try {
      await api.request('/reports/create/', {
        method: 'POST',
        body: JSON.stringify({
          reported_reel_id: reel.id,
          report_type: selectedReason,
          description: `Reported as ${selectedReason}`,
        }),
      });
      Alert.alert('Success', 'Report submitted successfully');
      onClose();
    } catch (error) {
      console.log('Report error:', error);
      Alert.alert('Error', 'Failed to submit report');
    } finally {
      setSubmitting(false);
    }
  }, [selectedReason, reel, onClose]);

  return (
    <View style={styles.modalOverlay}>
      <View style={styles.reportSheet}>
        {/* Header */}
        <View style={styles.reportHeader}>
          <View style={styles.reportHeaderContent}>
            <View style={styles.reportIconContainer}>
              <Ionicons name="flag-outline" size={24} color={GOLD} />
            </View>
            <View>
              <Text style={styles.reportTitle}>Report Content</Text>
              <Text style={styles.reportSubtitle}>Help keep our community safe</Text>
            </View>
          </View>
          <TouchableOpacity 
            style={styles.reportCloseButton}
            onPress={onClose}
          >
            <Ionicons name="close" size={24} color={colors.textSecondary} />
          </TouchableOpacity>
        </View>
        
        {/* Content */}
        <ScrollView style={styles.reportContent} showsVerticalScrollIndicator={false}>
          <View style={styles.reportSection}>
            <Text style={styles.reportSectionTitle}>
              Why are you reporting this content?
            </Text>
            <Text style={styles.reportSectionDescription}>
              Select the reason that best describes your concern
            </Text>
          </View>
          
          <View style={styles.reportReasonsContainer}>
            {reportReasons.map(reason => (
              <TouchableOpacity
                key={reason.id}
                style={[
                  styles.reportReasonItem,
                  selectedReason === reason.id && styles.reportReasonItemSelected
                ]}
                onPress={() => setSelectedReason(reason.id)}
                activeOpacity={0.7}
              >
                <View style={styles.reportReasonIcon}>
                  <Ionicons 
                    name={reason.icon} 
                    size={22} 
                    color={selectedReason === reason.id ? GOLD : '#666'} 
                  />
                </View>
                <View style={styles.reportReasonContent}>
                  <Text style={[
                    styles.reportReasonText,
                    selectedReason === reason.id && styles.reportReasonTextSelected
                  ]}>
                    {reason.label}
                  </Text>
                  <Text style={styles.reportReasonDescription}>
                    {reason.description}
                  </Text>
                </View>
                <View style={styles.reportReasonCheck}>
                  {selectedReason === reason.id && (
                    <Ionicons name="checkmark-circle" size={22} color={GOLD} />
                  )}
                </View>
              </TouchableOpacity>
            ))}
          </View>
        </ScrollView>
        
        {/* Actions */}
        <View style={styles.reportActions}>
          <TouchableOpacity 
            style={styles.reportCancelBtn} 
            onPress={onClose}
            activeOpacity={0.8}
          >
            <Text style={styles.reportCancelText}>Cancel</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[
              styles.reportSubmitBtn,
              !selectedReason && styles.reportSubmitBtnDisabled
            ]}
            onPress={submitReport}
            disabled={!selectedReason || submitting}
            activeOpacity={0.8}
          >
            {submitting ? (
              <ActivityIndicator size="small" color="#000" />
            ) : (
              <Text style={styles.reportSubmitText}>Submit Report</Text>
            )}
          </TouchableOpacity>
        </View>
      </View>
    </View>
  );
}
export default function ReelsScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const auth = useAuth();
  const { filterBlockedUsers } = useBlock();
  const user = auth?.user ?? null;
  const [reels, setReels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeIndex, setActiveIndex] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [localShareCounts, setLocalShareCounts] = useState({}); // Track local share increments
  const [loadingMore, setLoadingMore] = useState(false);
  const [activeTab, setActiveTab] = useState('for_you');
  const [screenMenuVisible, setScreenMenuVisible] = useState(false);
  const [screenShowReport, setScreenShowReport] = useState(false);
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [followStates, setFollowStates] = useState({});
  const [showGiftModal, setShowGiftModal] = useState(false);
  const [giftRecipient, setGiftRecipient] = useState('');
  const [giftMessage, setGiftMessage] = useState('');
  const [sendingGift, setSendingGift] = useState(false);
  const [giftSent, setGiftSent] = useState(null);
  const [giftError, setGiftError] = useState('');
  const [userCoins, setUserCoins] = useState(0);
  const [gifts, setGifts] = useState([]);
  const [giftsSentToday, setGiftsSentToday] = useState(0);
  const [dailyGiftLimit, setDailyGiftLimit] = useState(10);
  const [selectedGift, setSelectedGift] = useState(null);
  const [giftQuantity, setGiftQuantity] = useState(1);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const LIMIT = 10;
  const initialVideoId = route?.params?.initialVideoId;
  const fromDeepLink = route?.params?.fromDeepLink;
  const flatListRef = useRef(null);

  // Follow/Unfollow handler
  const handleFollow = useCallback(async (userId) => {
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
      
      // Update the reel item to reflect the follow state
      setReels(prev => prev.map(reel => 
        reel.user?.id === userId 
          ? { ...reel, user: { ...reel.user, is_following: response.following } }
          : reel
      ));
      
    } catch (error) {
      console.error('Follow error:', error);
      setFollowStates(prev => ({ ...prev, [userId]: false }));
    }
  }, [user]);

  // Gift modal handler
  const openGiftModal = (postUser) => {
    setGiftRecipient(postUser?.username || '');
    setSelectedGift(null);
    setGiftQuantity(1);
    setGiftMessage('');
    setGiftError('');
    setShowGiftModal(true);
  };

  const loadUserCoins = async () => {
    try {
      const wallet = await api.request('/wallet/');
      setUserCoins(wallet.balance?.purchased || 0);
    } catch (error) {
      console.error('Failed to load user coins:', error);
      setUserCoins(0);
    }
  };

  const loadGifts = async () => {
    try {
      const response = await api.request('/gifts/');
      if (Array.isArray(response) && response.length > 0) {
        setGifts(response);
      } else {
        // Use fallback gifts if API returns empty or fails
        setGifts([
          { id: 1, name: 'Rose', emoji: '🌹', coin_cost: 10 },
          { id: 2, name: 'Heart', emoji: '❤️', coin_cost: 5 },
          { id: 3, name: 'Star', emoji: '⭐', coin_cost: 15 },
          { id: 4, name: 'Fire', emoji: '🔥', coin_cost: 20 },
          { id: 5, name: 'Diamond', emoji: '💎', coin_cost: 50 },
          { id: 6, name: 'Crown', emoji: '👑', coin_cost: 100 },
          { id: 7, name: 'Rocket', emoji: '🚀', coin_cost: 30 },
          { id: 8, name: 'Gift Box', emoji: '🎁', coin_cost: 25 },
        ]);
      }
    } catch (error) {
      console.error('Failed to load gifts:', error);
      // Use fallback gifts on error
      setGifts([
        { id: 1, name: 'Rose', emoji: '🌹', coin_cost: 10 },
        { id: 2, name: 'Heart', emoji: '❤️', coin_cost: 5 },
        { id: 3, name: 'Star', emoji: '⭐', coin_cost: 15 },
        { id: 4, name: 'Fire', emoji: '🔥', coin_cost: 20 },
        { id: 5, name: 'Diamond', emoji: '💎', coin_cost: 50 },
        { id: 6, name: 'Crown', emoji: '👑', coin_cost: 100 },
        { id: 7, name: 'Rocket', emoji: '🚀', coin_cost: 30 },
        { id: 8, name: 'Gift Box', emoji: '🎁', coin_cost: 25 },
      ]);
    }
  };

  // Load gifts on component mount
  useEffect(() => {
    loadGifts();
    loadUserCoins();
  }, []);

  // Reload coins when gift modal opens
  useEffect(() => {
    if (showGiftModal) loadUserCoins();
  }, [showGiftModal]);

  const sendGift = async () => {
    if (!giftRecipient.trim()) {
      setGiftError('Enter a recipient username');
      return;
    }
    if (!selectedGift) {
      setGiftError('Select a gift');
      return;
    }
    if (giftQuantity < 1 || giftQuantity > 99) {
      setGiftError('Quantity must be between 1 and 99');
      return;
    }
    const totalCost = selectedGift.coin_cost * giftQuantity;
    if (totalCost > userCoins) {
      setGiftError('Insufficient coins');
      return;
    }

    setSendingGift(true);
    setGiftError('');
    try {
      console.log('Sending gift with data:', {
        gift_id: selectedGift.id,
        recipient_username: giftRecipient,
        quantity: giftQuantity,
        message: giftMessage,
      });
      
      const response = await api.request('/gifts/send/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gift_id: selectedGift.id,
          recipient_username: giftRecipient,
          quantity: giftQuantity,
          message: giftMessage,
        }),
      });

      console.log('Gift send response:', response);

      if (response && response.id) {
        // Gift was sent successfully - API returns gift data directly
        setUserCoins(prev => prev - totalCost);
        setGiftsSentToday(prev => prev + 1);
        setGiftSent(response);
        
        // Play coin sound for successful gift
        SoundManager.playCoinSound();
        
        setTimeout(() => {
          setShowGiftModal(false);
          setGiftSent(null);
        }, 2000);
      } else {
        console.error('Gift send failed:', response);
        setGiftError(response?.message || 'Failed to send gift');
      }
    } catch (error) {
      const errMsg = error?.message || '';
      const needsRecharge = errMsg.includes('Insufficient') || errMsg.includes('needs_recharge');
      
      if (needsRecharge) {
        const match = errMsg.match(/need (\d+).*have (\d+)/i);
        const needed = match ? match[1] : '';
        const have = match ? match[2] : '';
        Alert.alert(
          'Insufficient Coins',
          `You need ${needed || 'more'} purchased coins but only have ${have || '0'}.\n\nOnly purchased coins can be used for gifting. Please top up your coins.`,
          [
            { text: 'Cancel', style: 'cancel' },
            { text: 'Buy Coins', onPress: () => navigation.navigate('WebsiteCoin') },
          ]
        );
      } else {
        setGiftError(errMsg || 'Failed to send gift. Please try again.');
      }
    } finally {
      setSendingGift(false);
    }
  };

  // Pause video when screen loses focus (e.g., navigating to login, settings, etc.)
  useEffect(() => {
    if (!navigation?.addListener) return;
    
    const unsubscribe = navigation.addListener('blur', () => {
      // Pause all videos when screen loses focus
      setReels(prev => prev.map(reel => ({ ...reel, paused: true })));
      // Force set active index to -1 to ensure all videos stop
      setActiveIndex(-1);
    });
    
    const focusUnsubscribe = navigation.addListener('focus', () => {
      // Resume when coming back
      setActiveIndex(0);
    });
    
    return () => {
      unsubscribe();
      focusUnsubscribe();
    };
  }, [navigation]);

  // -- Feed cache helpers (stale-while-revalidate) --------------------------
  const CACHE_KEY = (tab) => `feed_cache_${tab}`;
  const CACHE_TTL = 2 * 60 * 1000; // 2 min for faster post distribution
  const readFeedCache = async (tab) => {
    try {
      const raw = await AsyncStorage.getItem(CACHE_KEY(tab));
      if (!raw) return null;
      const { ts, data } = JSON.parse(raw);
      if (Date.now() - ts > CACHE_TTL) { await AsyncStorage.removeItem(CACHE_KEY(tab)); return null; }
      return data;
    } catch { return null; }
  };
  const writeFeedCache = async (tab, data) => {
    try { await AsyncStorage.setItem(CACHE_KEY(tab), JSON.stringify({ ts: Date.now(), data })); } catch {}
  };

  useEffect(() => {
    const loadFeed = async () => {
      // If initialVideoId is provided, fetch that specific video first
      if (initialVideoId) {
        console.log('Fetching specific video:', initialVideoId);
        try {
          // Force fresh data fetch for deep link
          const specificVideo = await api.request(`/reels/${initialVideoId}/`, { 
            headers: { 'Cache-Control': 'no-cache' },
            cache: 'no-cache'
          });
          if (specificVideo && specificVideo.media) {
            console.log('Specific video loaded:', specificVideo.id);
            console.log('Video stats:', {
              likes: specificVideo.likes_count,
              comments: specificVideo.comments_count,
              shares: specificVideo.shares_count
            });
            // Set the specific video as the first item with preserved share counts
            setReels(prev => {
              const updatedVideo = {
                ...specificVideo,
                shares: (specificVideo.shares || 0) + (localShareCounts[specificVideo.id] || 0)
              };
              return [updatedVideo];
            });
            setLoading(false);
            
            // Then load the rest of the feed in the background
            const endpoint = activeTab === 'following' 
              ? `/reels/following/?limit=${LIMIT}&offset=0`
              : `/reels/?limit=${LIMIT}&offset=0`;
            
            const data = await api.request(endpoint);
            const results = Array.isArray(data) ? data : (data.results || []);
            const filteredResults = results.filter(reel => reel && reel.media && String(reel.id) !== String(initialVideoId));
            
            // Add the rest of the videos after the specific one with preserved share counts
            setReels(prev => {
              const updatedSpecificVideo = {
                ...specificVideo,
                shares: (specificVideo.shares || 0) + (localShareCounts[specificVideo.id] || 0)
              };
              const updatedFilteredResults = filteredResults.map(reel => ({
                ...reel,
                shares: (reel.shares || 0) + (localShareCounts[reel.id] || 0)
              }));
              return [updatedSpecificVideo, ...updatedFilteredResults];
            });
            setHasMore(filteredResults.length === LIMIT);
            return;
          }
        } catch (error) {
          console.error('Failed to fetch specific video:', error);
          // Continue to load normal feed if specific video fails
        }
      }
      
      // Normal feed loading (no specific video or specific video failed)
      const endpoint = activeTab === 'following'
        ? `/reels/following/?limit=${LIMIT}&offset=0`
        : `/reels/?limit=${LIMIT}&offset=0`;
      
      console.log('Loading reels feed');
      
      // Show cached data immediately so it's visible instantly
      const cached = await readFeedCache(activeTab);
      if (cached?.length > 0) {
        let results = cached;
        
        // Only show video content in reels
        const filteredResults = results.filter(reel => reel && reel.media);
        const shuffled = shuffleArray(filteredResults);
        // Preserve local share counts
        const updatedShuffled = shuffled.map(reel => ({
          ...reel,
          shares: (reel.shares || 0) + (localShareCounts[reel.id] || 0)
        }));
        setReels(updatedShuffled);
        setLoading(false);
      }
      
      // Then fetch fresh data in background
      const stale = api.requestStale(endpoint, (fresh) => {
        let results = Array.isArray(fresh) ? fresh : (fresh.results || []);
        
        // Only show video content in reels
        const filteredResults = results.filter(reel => reel && reel.media);
        const shuffledResults = shuffleArray(filteredResults);
        // Preserve local share counts and filter blocked users
        const updatedShuffledResults = shuffledResults.map(reel => ({
          ...reel,
          shares: (reel.shares || 0) + (localShareCounts[reel.id] || 0)
        }));
        // Filter out reels from blocked users
        const filteredShuffledResults = filterBlockedUsers(updatedShuffledResults);
        setReels(filteredShuffledResults);
        setHasMore(filteredResults.length === LIMIT);
        
        // Persist fresh data so next load is instant
        if (filteredResults.length > 0) {
          writeFeedCache(activeTab, filteredResults);
        }
      });
      
      if (!cached) {
        fetchReels(0, true);
      }
    };
    
    loadFeed();
  }, [activeTab, initialVideoId]);

  // Auto-refresh content when block state changes
  useEffect(() => {
    // Refresh the current tab to reflect block/unblock changes
    fetchReels(0, true);
  }, [filterBlockedUsers]);

  const fetchReels = async (offset = 0, reset = false) => {
    try {
      if (reset) setLoading(true); else setLoadingMore(true);
      
      let endpoint = activeTab === 'following'
        ? `/reels/following/?limit=${LIMIT}&offset=${offset}`
        : `/reels/?limit=${LIMIT}&offset=${offset}`;
      
      const data = await api.request(endpoint);
      let results = Array.isArray(data) ? data : (data.results || []);
      
      // Only show video content in reels
      const filteredResults = results.filter(reel => reel && reel.media);
      
      // Always shuffle for normal feed loading
      const shuffledResults = shuffleArray(filteredResults);
      // Preserve local share counts and filter blocked users
      const updatedShuffledResults = shuffledResults.map(reel => ({
        ...reel,
        shares: (reel.shares || 0) + (localShareCounts[reel.id] || 0)
      }));
      // Filter out reels from blocked users
      const filteredShuffledResults = filterBlockedUsers(updatedShuffledResults);
      setReels(prev => reset ? filteredShuffledResults : [...prev, ...filteredShuffledResults]);
      
      setHasMore(filteredResults.length === LIMIT);
    } catch (e) { 
      console.error('Reels error:', e); 
    } finally { 
      setLoading(false); 
      setLoadingMore(false); 
    }
  };

  const onViewableChanged = useCallback(({ viewableItems }) => {
    if (viewableItems.length > 0) {
      const newIndex = viewableItems[0].index ?? 0;
      console.log('Video became visible at index:', newIndex);
      setActiveIndex(newIndex);
    }
  }, []);

  const viewabilityConfigRef = useRef({
    itemVisiblePercentThreshold: 50,
    minimumViewTime: 0,
  });

  const onEndReached = () => {
    if (!loadingMore && hasMore) {
      fetchReels(reels.length, false);
    }
  };

  const onRefresh = async () => {
    setIsRefreshing(true);
    setPullDistance(80);
    try {
      // Clear cache and fetch fresh data
      try { await AsyncStorage.removeItem(CACHE_KEY(activeTab)); } catch {}
      await fetchReels(0, true);
    } catch (error) {
      console.error('Refresh error:', error);
    } finally {
      setTimeout(() => {
        setIsRefreshing(false);
        setPullDistance(0);
      }, 500);
    }
  };

  // Handle tab reselect to scroll to top and refresh
  const handleTabReselect = (tab) => {
    if (tab === activeTab) {
      // Scroll to top
      flatListRef.current?.scrollToOffset({ offset: 0, animated: true });
      // Refresh feed
      onRefresh();
    }
  };

  const handleShowProfile = (userId) => {
    navigation.navigate('Profile', { userId });
  };

  const handleTabPress = (tab) => {
    if (tab === 'explore') {
      navigation.navigate('Explore');
      return;
    }
    setActiveTab(tab);
  };

  const handleNavigate = useCallback((screen, params) => {
    navigation.navigate(screen, params);
  }, [navigation]);

  const currentReel = reels[activeIndex];
  const isOwnCurrentReel = user?.id === currentReel?.user?.id;

  const screenHandleShare = useCallback(async () => {
    setScreenMenuVisible(false);
    if (!currentReel) return;
    try {
      await Share.share({ message: `Check out this reel on FlipStar!` });
    } catch {}
  }, [currentReel]);

  const screenHandleNotInterested = useCallback(async () => {
    setScreenMenuVisible(false);
    if (!currentReel) return;
    try {
      await api.request('/reels/not-interested/', {
        method: 'POST',
        body: JSON.stringify({ reel_id: currentReel.id }),
      });
    } catch {}
    setReels(prev => prev.filter(v => v.id !== currentReel.id));
  }, [currentReel]);

  const screenHandleDelete = useCallback(() => {
    setScreenMenuVisible(false);
    if (!currentReel) return;
    Alert.alert('Delete Reel', 'Are you sure you want to delete this reel?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete', style: 'destructive',
        onPress: async () => {
          try {
            await api.request(`/reels/${currentReel.id}/`, { method: 'DELETE' });
            setReels(prev => prev.filter(v => v.id !== currentReel.id));
          } catch {
            Alert.alert('Error', 'Failed to delete reel');
          }
        },
      },
    ]);
  }, [currentReel]);

  const renderReel = useCallback(({ item, index }) => (
    <ReelItem
      item={item}
      index={index}
      isActive={index === activeIndex}
      user={user}
      videos={reels}
      setVideos={setReels}
      onShowProfile={handleShowProfile}
      onNavigate={handleNavigate}
      onOpenGiftModal={openGiftModal}
      onFollow={handleFollow}
      followStates={followStates}
      fromDeepLink={fromDeepLink}
      localShareCounts={localShareCounts}
      onLike={handleLike}
      onComment={handleComment}
      onSave={handleSave}
      onShare={handleShareVideo}
      onReport={handleReport}
    />
  ), [activeIndex, user, reels, handleShowProfile, handleNavigate, openGiftModal, handleFollow, followStates, fromDeepLink, localShareCounts, handleLike, handleComment, handleSave, handleShareVideo, handleReport]);

  if (loading) {
    return (
      <View style={[styles.container, { backgroundColor: BG, justifyContent: 'center', alignItems: 'center' }]}>
        <ActivityIndicator size="large" color={GOLD} />
      </View>
    );
  }

  return (
    <View style={[styles.container, { backgroundColor: BG }]}>
      <StatusBar barStyle={'#fff' === '#FFFFFF' ? 'light-content' : 'dark-content'} translucent backgroundColor="transparent" />
      
      {/* Pull to Refresh Indicator */}
      {pullDistance > 0 && (
        <View style={[
          styles.refreshIndicator,
          { height: Math.min(pullDistance, 120) }
        ]}>
          <View style={[
            styles.spinner,
            isRefreshing && styles.spinnerSpinning,
            { transform: [{ rotate: `${(pullDistance / 80) * 360}deg` }] }
          ]}>
            <Ionicons name="refresh" size={20} color={GOLD} />
          </View>
        </View>
      )}

      {/* Tab Navigation */}
      <View style={[styles.tabContainer, { backgroundColor: CARD + '80', top: insets.top + 8 }]}>
        {['for_you', 'following'].map(tab => (
          <TouchableOpacity 
            key={tab} 
            onPress={() => handleTabPress(tab)} 
            style={styles.tabBtn}
          >
            <Text style={[
              styles.tabText, 
              activeTab === tab && styles.tabTextActive
            ]}>
              {tab === 'for_you' ? 'For You' : 'Following'}
            </Text>
            {activeTab === tab && <View style={styles.tabIndicator} />}
          </TouchableOpacity>
        ))}
      </View>

      {/* Video Feed - TikTok Style */}
      <FlatList
        ref={flatListRef}
        data={reels}
        keyExtractor={r => String(r.id)}
        renderItem={renderReel}
        pagingEnabled
        showsVerticalScrollIndicator={false}
        snapToInterval={height}
        snapToAlignment="center"
        decelerationRate="fast"
        onViewableItemsChanged={onViewableChanged}
        viewabilityConfig={viewabilityConfigRef.current}
        onEndReached={onEndReached}
        onEndReachedThreshold={0.1}
        removeClippedSubviews={false}
        maxToRenderPerBatch={5}
        windowSize={7}
        initialNumToRender={3}
        initialScrollIndex={0}
        getItemLayout={(data, index) => ({
          length: height,
          offset: height * index,
          index,
        })}
        refreshControl={
          <RefreshControl 
            refreshing={isRefreshing} 
            onRefresh={onRefresh} 
            tintColor={GOLD} 
            colors={[GOLD]}
          />
        }
        ListFooterComponent={
          loadingMore ? (
            <View style={{ padding: 20, alignItems: 'center', backgroundColor: '#000' }}>
              <ActivityIndicator size="small" color={GOLD} />
              <Text style={{ color: GOLD, marginTop: 8, fontSize: 12 }}>Loading more videos...</Text>
            </View>
          ) : null
        }
        ListEmptyComponent={
          <View style={{ justifyContent: 'center', alignItems: 'center', flex: 1, backgroundColor: '#000' }}>
            <Text style={{ color: '#666', fontSize: 16 }}>No reels yet</Text>
            <Text style={{ color: '#666', marginTop: 8 }}>Be the first to share a reel!</Text>
          </View>
        }
      />

      {/* Fixed top-right overlay � AFTER FlatList so it renders on top */}
      <View style={[styles.topRightActions, { top: insets.top + 10, zIndex: 999, elevation: 20 }]}>
        <TouchableOpacity style={styles.topActionBtn} onPress={() => navigation.navigate('Notifications')}>
          <Ionicons name="notifications-outline" size={24} color={LIGHT_GOLD} />
        </TouchableOpacity>
        <TouchableOpacity style={styles.topActionBtn} onPress={() => setScreenMenuVisible(v => !v)}>
          <Ionicons name="ellipsis-horizontal" size={20} color="#fff" />
        </TouchableOpacity>
      </View>

      {/* Dropdown rendered separately so it's never clipped */}
      {screenMenuVisible && (
        <View style={[styles.dropdownMenu, { top: insets.top + 70, right: 16, zIndex: 1000, elevation: 25 }]}>
          <TouchableOpacity style={styles.menuItem} onPress={screenHandleShare}>
            <Ionicons name="share-outline" size={18} color={LIGHT_GOLD} />
            <Text style={styles.menuText}>Share</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.menuItem} onPress={screenHandleNotInterested}>
            <Ionicons name="eye-off-outline" size={18} color="#78716C" />
            <Text style={styles.menuText}>Not Interested</Text>
          </TouchableOpacity>
          <TouchableOpacity style={styles.menuItem} onPress={() => { setScreenMenuVisible(false); setScreenShowReport(true); }}>
            <Ionicons name="alert-circle-outline" size={18} color="#EF4444" />
            <Text style={[styles.menuText, { color: '#EF4444' }]}>Report</Text>
          </TouchableOpacity>
          {isOwnCurrentReel && (
            <TouchableOpacity style={styles.menuItem} onPress={screenHandleDelete}>
              <Ionicons name="trash-outline" size={18} color="#EF4444" />
              <Text style={[styles.menuText, { color: '#EF4444' }]}>Delete</Text>
            </TouchableOpacity>
          )}
        </View>
      )}

      {/* Screen-level Report Modal */}
      {screenShowReport && currentReel && (
        <Modal visible transparent animationType="slide" onRequestClose={() => setScreenShowReport(false)}>
          <View style={styles.modalOverlay}>
            <ReportModal reel={currentReel} onClose={() => setScreenShowReport(false)} />
          </View>
        </Modal>
      )}

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
              <View style={{ padding: 20 }}>
                  {/* Gift Selection */}
                  <View style={{ marginBottom: 20 }}>
                    <Text style={{ fontSize: 16, fontWeight: '700', color: '#fff', marginBottom: 12 }}>Select a Gift</Text>
                    <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                      {gifts.map((gift) => (
                        <TouchableOpacity
                          key={gift.id}
                          style={[
                            { 
                              alignItems: 'center', 
                              marginRight: 15, 
                              padding: 10,
                              borderRadius: 12,
                              borderWidth: 2,
                              borderColor: selectedGift?.id === gift.id ? GOLD : '#333',
                              backgroundColor: selectedGift?.id === gift.id ? 'rgba(200, 181, 106, 0.1)' : 'transparent'
                            }
                          ]}
                          onPress={() => setSelectedGift(gift)}
                        >
                          <Text style={{ fontSize: 32, marginBottom: 4 }}>{gift.emoji || '🎁'}</Text>
                          <Text style={{ fontSize: 12, color: '#aaa', textAlign: 'center' }}>{gift.name}</Text>
                          <Text style={{ fontSize: 12, fontWeight: '700', color: GOLD, marginTop: 2 }}>
                            {gift.coin_cost} 🪙
                          </Text>
                        </TouchableOpacity>
                      ))}
                    </ScrollView>
                  </View>

                  {/* Quantity Selector */}
                  {selectedGift && (
                    <View style={{ marginBottom: 20 }}>
                      <Text style={{ fontSize: 16, fontWeight: '700', color: '#fff', marginBottom: 12 }}>Quantity</Text>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 15 }}>
                        <TouchableOpacity
                          style={{ 
                            width: 36, height: 36, borderRadius: 18, 
                            backgroundColor: '#333', justifyContent: 'center', alignItems: 'center' 
                          }}
                          onPress={() => setGiftQuantity(Math.max(1, giftQuantity - 1))}
                        >
                          <Text style={{ color: '#fff', fontSize: 18 }}>-</Text>
                        </TouchableOpacity>
                        <Text style={{ fontSize: 18, fontWeight: '700', color: '#fff', minWidth: 40, textAlign: 'center' }}>
                          {giftQuantity}
                        </Text>
                        <TouchableOpacity
                          style={{ 
                            width: 36, height: 36, borderRadius: 18, 
                            backgroundColor: '#333', justifyContent: 'center', alignItems: 'center' 
                          }}
                          onPress={() => setGiftQuantity(Math.min(99, giftQuantity + 1))}
                        >
                          <Text style={{ color: '#fff', fontSize: 18 }}>+</Text>
                        </TouchableOpacity>
                        <View style={{ marginLeft: 10 }}>
                          <Text style={{ fontSize: 14, color: GOLD, fontWeight: '700' }}>
                            Total: {selectedGift.coin_cost * giftQuantity} 🪙
                          </Text>
                        </View>
                      </View>
                    </View>
                  )}

                  {/* Message Input */}
                  <View style={{ marginBottom: 20 }}>
                    <Text style={{ fontSize: 16, fontWeight: '700', color: '#fff', marginBottom: 12 }}>Message (Optional)</Text>
                    <TextInput
                      style={{
                        backgroundColor: '#1A1A1A',
                        borderRadius: 10,
                        padding: 12,
                        color: '#fff',
                        borderWidth: 1,
                        borderColor: '#333',
                        minHeight: 60,
                        textAlignVertical: 'top'
                      }}
                      placeholder="Add a message..."
                      placeholderTextColor="#666"
                      value={giftMessage}
                      onChangeText={setGiftMessage}
                      multiline
                      maxLength={100}
                    />
                  </View>

                  {/* Error Display */}
                  {giftError ? (
                    <View style={{ 
                      backgroundColor: '#2D1010', 
                      borderWidth: 1, 
                      borderColor: '#EF4444', 
                      borderRadius: 8, 
                      padding: 10, 
                      marginBottom: 16 
                    }}>
                      <Text style={{ color: '#EF4444', fontSize: 13, fontWeight: '600' }}>
                        ⚠️ {giftError}
                      </Text>
                    </View>
                  ) : null}

                  {/* Send Button */}
                  <TouchableOpacity
                    style={[
                      styles.sendButton,
                      (!selectedGift || sendingGift) && { backgroundColor: '#444' }
                    ]}
                    onPress={sendGift}
                    disabled={!selectedGift || sendingGift}
                  >
                    {sendingGift ? (
                      <ActivityIndicator size="small" color="#000" />
                    ) : (
                      <Text style={styles.sendButtonText}>
                        Send Gift 🎁 {selectedGift && `(${selectedGift.coin_cost * giftQuantity} 🪙)`}
                      </Text>
                    )}
                  </TouchableOpacity>
                </View>
            )}
          </TouchableOpacity>
        </TouchableOpacity>
      </Modal>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: '#000' },
  
  // Reel Container
  reelContainer: { 
    width, 
    height, 
    backgroundColor: '#000',
    position: 'relative',
  },
  
  // Gradient Overlay
  gradient: {
    position: 'absolute', 
    bottom: 0, 
    left: 0, 
    right: 0, 
    height: 280,
    backgroundColor: 'transparent',
    backgroundImage: 'linear-gradient(to top, rgba(0,0,0,0.8) 0%, transparent 100%)',
  },
  
  // Top Right Actions
  topRightActions: {
    position: 'absolute',
    top: 50,
    right: 16,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    zIndex: 10,
  },
  topActionBtn: {
    padding: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.6)',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.9,
    shadowRadius: 6,
    elevation: 8,
  },
  dropdownMenu: {
    position: 'absolute',
    top: 40,
    right: 0,
    backgroundColor: CARD,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BORDER,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 8,
    minWidth: 160,
    zIndex: 100,
  },
  menuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 14,
    gap: 12,
  },
  menuText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '500',
  },
  
  // Right Side Actions
  rightActions: { 
    position: 'absolute', 
    right: 8, 
    top: 280, 
    alignItems: 'center', 
    gap: 18,
  },
  avatarContainer: {
    marginBottom: 12,
  },
  followBadge: {
    position: 'absolute', 
    bottom: -6, 
    left: '50%', 
    marginLeft: -10,
    width: 20, 
    height: 20, 
    borderRadius: 10, 
    backgroundColor: GOLD,
    justifyContent: 'center', 
    alignItems: 'center',
    borderWidth: 2,
    borderColor: '#000',
  },
  followingBadge: {
    backgroundColor: 'rgba(255,255,255,0.2)',
    borderColor: '#fff',
  },
  actionItem: { 
    alignItems: 'center',
    marginBottom: 8,
    marginTop: 0,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 3 },
    shadowOpacity: 0.9,
    shadowRadius: 6,
    elevation: 8,
  },
  actionIcon: {
    width: 56,
    height: 56,
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.4)',
    borderRadius: 28,
  },
  actionIconRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  iconShadow: {
    textShadowColor: 'rgba(0,0,0,1)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 8,
  },
  likeAnimation: {
    transform: [{ scale: 1.2 }],
  },
  actionLabel: { 
    color: GOLD, 
    fontSize: 12, 
    fontWeight: '600',
    marginTop: 2,
    textShadowColor: 'rgba(0,0,0,1)',
    textShadowOffset: { width: 0, height: 2 },
    textShadowRadius: 4,
    backgroundColor: 'rgba(0,0,0,0.5)',
    paddingHorizontal: 6,
    paddingVertical: 2,
    borderRadius: 4,
  },
  actionLabelInline: {
    color: DARK_GOLD,
    fontSize: 13,
    fontWeight: '700',
    textShadowColor: 'rgba(0,0,0,1)',
    textShadowOffset: { width: 0, height: 0 },
    textShadowRadius: 6,
  },
  
  // Bottom Info
  bottomInfo: { 
    position: 'absolute', 
    bottom: 80, 
    left: 12, 
    right: 90,
    paddingBottom: 10,
  },
  userInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    marginBottom: 8,
  },
  username: {
    color: '#fff', 
    fontWeight: '700', 
    fontSize: 16,
    textShadowColor: 'rgba(0,0,0,0.5)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  caption: {
    color: 'rgba(255,255,255,0.9)', 
    fontSize: 14, 
    lineHeight: 18, 
    marginBottom: 8,
    textShadowColor: 'rgba(0,0,0,0.5)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 4,
  },
  moreLessBtn: {
    color: LIGHT_GOLD,
    fontWeight: '600',
    fontSize: 12,
  },
  hashtagsContainer: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 6,
    marginBottom: 8,
  },
  hashtag: {
    color: LIGHT_GOLD, 
    fontSize: 13, 
    fontWeight: '600',
  },
  musicInfo: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  musicText: {
    color: LIGHT_GOLD,
    fontSize: 12,
    fontWeight: '600',
  },
  
  // Video Controls
  pauseIconContainer: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: 'rgba(0,0,0,0.5)',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: 'rgba(255,255,255,0.3)',
  },
  doubleTapHeart: {
    opacity: 0.9,
  },
  
  // Tab Navigation
  tabContainer: {
    position: 'absolute', 
    left: 0, 
    right: 0,
    flexDirection: 'row', 
    justifyContent: 'center', 
    gap: 24, 
    zIndex: 10,
  },
  tabBtn: { 
    alignItems: 'center', 
    paddingVertical: 8,
  },
  tabText: { 
    color: 'rgba(255,255,255,0.6)', 
    fontSize: 15, 
    fontWeight: '600' 
  },
  tabTextActive: { 
    color: '#fff', 
    fontWeight: '800' 
  },
  tabIndicator: { 
    width: 20, 
    height: 2, 
    backgroundColor: '#fff', 
    borderRadius: 1, 
    marginTop: 4 
  },
  
  // Refresh Indicator
  refreshIndicator: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    backgroundColor: 'rgba(226,179,85,0.15)',
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 5,
  },
  spinner: {
    width: 32,
    height: 32,
    borderRadius: 16,
    borderWidth: 3,
    borderColor: GOLD,
    borderTopColor: 'transparent',
  },
  spinnerSpinning: {
    // Animation would be added here with Animated API
  },
  
  // Modals
  modalOverlay: { 
    flex: 1, 
    backgroundColor: 'rgba(0,0,0,0.6)', 
    justifyContent: 'flex-end' 
  },
  
  // Comments Modal
  commentsSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    height: '75%',
    paddingBottom: 20,
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
    maxHeight: 80,
  },
  
  // Report Modal
  reportSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 24,
    borderTopRightRadius: 24,
    height: '75%',
    paddingBottom: 24,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: -4 },
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 12,
  },
  reportHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  reportHeaderContent: {
    flexDirection: 'row',
    alignItems: 'center',
    flex: 1,
  },
  reportIconContainer: {
    width: 48,
    height: 48,
    borderRadius: 24,
    backgroundColor: 'rgba(143, 196, 65, 0.1)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  reportTitle: {
    color: '#fff',
    fontSize: 20,
    fontWeight: '700',
    marginBottom: 2,
  },
  reportSubtitle: {
    color: '#666',
    fontSize: 14,
    fontWeight: '500',
  },
  reportCloseButton: {
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  reportContent: {
    flex: 1,
    paddingHorizontal: 24,
  },
  reportSection: {
    paddingTop: 20,
    paddingBottom: 12,
  },
  reportSectionTitle: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '600',
    marginBottom: 4,
  },
  reportSectionDescription: {
    color: '#666',
    fontSize: 14,
    lineHeight: 20,
  },
  reportReasonsContainer: {
    paddingTop: 8,
  },
  reportReasonItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderRadius: 12,
    marginBottom: 8,
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    borderWidth: 1,
    borderColor: BORDER,
  },
  reportReasonItemSelected: {
    backgroundColor: 'rgba(143, 196, 65, 0.15)',
    borderColor: GOLD,
  },
  reportReasonIcon: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 16,
  },
  reportReasonContent: {
    flex: 1,
  },
  reportReasonText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginBottom: 2,
  },
  reportReasonTextSelected: {
    color: GOLD,
  },
  reportReasonDescription: {
    color: '#666',
    fontSize: 13,
    lineHeight: 18,
  },
  reportReasonCheck: {
    marginLeft: 12,
  },
  reportActions: {
    flexDirection: 'row',
    paddingHorizontal: 24,
    paddingTop: 16,
    paddingBottom: 8,
    gap: 12,
  },
  reportCancelBtn: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    alignItems: 'center',
  },
  reportCancelText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
  },
  reportSubmitBtn: {
    flex: 1,
    padding: 16,
    borderRadius: 12,
    backgroundColor: GOLD,
    alignItems: 'center',
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.3,
    shadowRadius: 4,
    elevation: 4,
  },
  reportSubmitBtnDisabled: {
    backgroundColor: '#444',
    shadowOpacity: 0,
    elevation: 0,
  },
  reportSubmitText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
  
  // Long-Press Menu
  longPressSheet: {
    backgroundColor: CARD,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    height: '50%',
    paddingBottom: 20,
  },
  longPressMenuItem: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    gap: 12,
  },
  longPressMenuText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '500',
  },
  
  // Gift Modal Styles
  giftSheet: {
    backgroundColor: '#1A1A1A',
    borderRadius: 20,
    margin: 20,
    maxHeight: '80%',
    position: 'absolute',
    top: 180,
    left: 0,
    right: 0,
  },
  sheetHandle: {
    width: 40,
    height: 4,
    backgroundColor: '#666',
    borderRadius: 2,
    alignSelf: 'center',
    marginTop: 8,
    marginBottom: 16,
  },
  sheetHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingBottom: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#333',
  },
  sheetTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: '#fff',
  },
  coinBalance: {
    fontSize: 16,
    fontWeight: '800',
    color: GOLD,
  },
  coinLabel: {
    fontSize: 12,
    color: '#888',
  },
  giftLimitLabel: {
    fontSize: 11,
    color: '#666',
  },
  sendButton: {
    backgroundColor: GOLD,
    paddingVertical: 12,
    paddingHorizontal: 24,
    borderRadius: 8,
    alignItems: 'center',
  },
  sendButtonText: {
    color: '#000',
    fontSize: 16,
    fontWeight: '700',
  },
  deepLinkSoundButton: {
    backgroundColor: 'rgba(143, 196, 65, 0.2)',
    borderRadius: 12,
    padding: 4,
    borderWidth: 2,
    borderColor: BRAND_GREEN,
  },
  soundButtonText: {
    color: BRAND_GREEN,
    fontSize: 10,
    fontWeight: '700',
    marginTop: 2,
    textShadowColor: 'rgba(0,0,0,0.8)',
    textShadowOffset: { width: 0, height: 1 },
    textShadowRadius: 2,
  },
  sheetHeaderLeft: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  sheetActions: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
  },
  sheetActionButton: {
    padding: 8,
    borderRadius: 20,
    backgroundColor: 'rgba(255,255,255,0.1)',
  },
});
