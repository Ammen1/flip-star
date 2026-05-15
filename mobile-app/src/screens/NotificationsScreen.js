import React, { useState, useEffect, useRef } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, ActivityIndicator, RefreshControl, ScrollView, Animated } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import api from '../api';
import config from '../config';
import SoundManager from '../utils/SoundUtils';

const GOLD = '#8fc441';
const LIGHT_GOLD = '#b5dd8f';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  const baseUrl = config.API_BASE_URL.replace('/api', '');
  // Ensure proper URL construction with slash
  return url.startsWith('/') ? `${baseUrl}${url}` : `${baseUrl}/${url}`;
};

function timeAgo(d) {
  if (!d) return '';
  const s = (Date.now() - new Date(d)) / 1000;
  if (s < 60) return `${Math.floor(s)}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
}

// Parse notification type from message content
function getNotificationType(message, type) {
  // If backend already provides proper type, use it
  if (type !== 'general') return type;
  
  // Parse from message text
  const lowerMessage = message.toLowerCase();
  
  if (lowerMessage.includes('liked your') || lowerMessage.includes('likes')) {
    return 'like';
  } else if (lowerMessage.includes('commented on') || lowerMessage.includes('comment')) {
    return 'comment';
  } else if (lowerMessage.includes('started following') || lowerMessage.includes('follow')) {
    return 'follow';
  } else if (lowerMessage.includes('sent you') || lowerMessage.includes('gift')) {
    return 'gift';
  } else if (lowerMessage.includes('campaign') || lowerMessage.includes('approved')) {
    return 'campaign';
  } else if (lowerMessage.includes('mention') || lowerMessage.includes('@')) {
    return 'mention';
  }
  
  return 'general';
}

// Group notifications by type and time
function groupNotifications(notifs) {
  const groups = [];
  const seen = {};
  for (const n of notifs) {
    const key = `${n.type}__${n.reel_id || ''}`;
    const ONE_HOUR = 60 * 60 * 1000;
    if (seen[key] && n.actor && (new Date(n.created_at) - new Date(seen[key].created_at)) < ONE_HOUR) {
      seen[key].extras = (seen[key].extras || 0) + 1;
    } else {
      // Create a unique entry with original ID to prevent key conflicts
      const entry = { 
        ...n, 
        extras: 0,
        uniqueKey: `${n.id}_${n.type}_${n.reel_id || 'no-reel'}`
      };
      seen[key] = entry;
      groups.push(entry);
    }
  }
  return groups;
}

function NotifIcon({ type, size = 10 }) {
  const iconMap = {
    like: 'heart',
    comment: 'chatbubble',
    follow: 'person-add',
    mention: 'at',
    campaign: 'trophy',
    gift: 'gift',
  };
  return <Ionicons name={iconMap[type] || 'notifications'} size={size} color="#fff" />;
}

const FILTERS = [
  { id: 'all', label: 'All', icon: 'notifications' },
  { id: 'like', label: 'Likes', icon: 'heart' },
  { id: 'comment', label: 'Comments', icon: 'chatbubble' },
  { id: 'follow', label: 'Follows', icon: 'person-add' },
  { id: 'mention', label: 'Mentions', icon: 'at' },
  { id: 'campaign', label: 'Campaigns', icon: 'trophy' },
  { id: 'gift', label: 'Gifts', icon: 'gift' },
];

export default function NotificationsScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const [notifications, setNotifications] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [activeFilter, setActiveFilter] = useState('all');
  const pollingRef = useRef(null);
  const pulseAnim = useRef(new Animated.Value(1)).current;

  useEffect(() => {
    loadNotifications();
    
    // Auto-mark all read after 2s
    const markTimer = setTimeout(() => {
      api.request('/notifications/read/', { method: 'POST', body: JSON.stringify({}) }).catch(() => {});
      setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
    }, 2000);
    
    // Poll every 30s
    pollingRef.current = setInterval(() => loadNotifications(true), 30000);
    
    return () => {
      clearTimeout(markTimer);
      clearInterval(pollingRef.current);
    };
  }, []);

  // Pulse animation for unread badge
  useEffect(() => {
    const hasUnread = notifications.some(n => !n.is_read);
    if (hasUnread) {
      Animated.loop(
        Animated.sequence([
          Animated.timing(pulseAnim, { toValue: 0.4, duration: 1000, useNativeDriver: true }),
          Animated.timing(pulseAnim, { toValue: 1, duration: 1000, useNativeDriver: true }),
        ])
      ).start();
    }
  }, [notifications]);

  const loadNotifications = async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await api.request('/notifications/');
      const newNotifications = Array.isArray(data) ? data : (data.results || []);
      
      // Play notification sound for new unread notifications
      const hasNewNotifications = newNotifications.some(n => !n.is_read);
      if (hasNewNotifications && !silent) {
        SoundManager.playNotificationSound();
      }
      
      setNotifications(newNotifications);
    } catch { 
      setNotifications([]); 
    } finally { 
      setLoading(false); 
      setRefreshing(false); 
    }
  };

  const handleMarkAllRead = () => {
    api.request('/notifications/read/', { method: 'POST', body: JSON.stringify({}) }).catch(() => {});
    setNotifications(prev => prev.map(n => ({ ...n, is_read: true })));
  };

  const handleNotifClick = (notif) => {
    if (!notif.is_read) {
      api.request(`/notifications/${notif.id}/read/`, { method: 'POST' }).catch(() => {});
      setNotifications(prev => prev.map(n => n.id === notif.id ? { ...n, is_read: true } : n));
    }
    
    if (notif.type === 'follow' && notif.actor?.id) {
      const actor = notif.sender || notif.actor;
      navigation.navigate('Profile', { userId: actor.id });
    } else if (notif.reel_id) {
      navigation.navigate('ReelsDetail', { initialVideoId: notif.reel_id });
    } else if (notif.campaign_id) {
      navigation.navigate('Campaigns');
    }
  };

  // Parse notification types and filter
  const notificationsWithParsedTypes = notifications.map(n => ({
    ...n,
    parsedType: getNotificationType(n.message || '', n.type || 'general')
  }));
  
  const filtered = groupNotifications(
    notificationsWithParsedTypes.filter(n => {
      const matches = activeFilter === 'all' || n.parsedType === activeFilter;
      return matches;
    })
  );
  
  const hasUnread = notifications.some(n => !n.is_read);
  const unreadCount = notifications.filter(n => !n.is_read).length;

  const renderItem = ({ item }) => {
    // Backend sends 'sender', not 'actor'
    const actor = item.sender || item.actor;
    const profilePhotoUrl = actor?.profile_photo ? mediaUrl(actor.profile_photo) : null;
    console.log('NotificationsScreen - Profile photo URL:', profilePhotoUrl);
    
    return (
      <TouchableOpacity
        style={[styles.item, !item.is_read && styles.unread]}
        onPress={() => handleNotifClick(item)}
        activeOpacity={0.7}
      >
        {/* Avatar with type badge */}
        <View style={styles.avatarContainer}>
          {profilePhotoUrl ? (
            <Image 
              source={{ uri: profilePhotoUrl }} 
              style={styles.avatar}
              onError={(e) => console.log('NotificationsScreen - Image load error:', e.nativeEvent.error)}
            />
          ) : (
            <View style={[styles.avatar, styles.avatarPlaceholder]}>
              <Text style={styles.avatarText}>
                {(actor?.username || '?')[0].toUpperCase()}
              </Text>
            </View>
          )}
          {/* Type badge overlay */}
        <View style={styles.typeBadge}>
          <NotifIcon type={item.parsedType || item.type} size={16} />
        </View>
      </View>

      {/* Content */}
      <View style={styles.content}>
        <Text style={styles.message} numberOfLines={2}>
          {actor && (
            <Text style={styles.username}>{actor.username} </Text>
          )}
          <Text style={[styles.messageText, !item.is_read && styles.messageUnread]}>
            {item.message || item.text}
            {item.extras > 0 && (
              <Text style={styles.extras}> and {item.extras} other{item.extras > 1 ? 's' : ''}</Text>
            )}
          </Text>
        </Text>
        
        {item.comment && (
          <Text style={styles.comment} numberOfLines={1}>
            "{item.comment}"
          </Text>
        )}
        
        <Text style={[styles.time, !item.is_read && styles.timeUnread]}>
          {timeAgo(item.created_at)}
        </Text>
      </View>

      {/* Thumbnail */}
      {item.reel?.thumbnail_url && (
        <Image 
          source={{ uri: mediaUrl(item.reel.thumbnail_url) }} 
          style={styles.thumb} 
        />
      )}
    </TouchableOpacity>
  );
};

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      {/* Header */}
      <View style={styles.header}>
        <View style={styles.headerLeft}>
          <View style={styles.iconContainer}>
            <Ionicons name="notifications" size={18} color={LIGHT_GOLD} />
            {hasUnread && (
              <Animated.View style={[styles.unreadDot, { opacity: pulseAnim }]} />
            )}
          </View>
          <Text style={styles.headerTitle}>Notifications</Text>
        </View>
        
        <View style={styles.headerRight}>
          {hasUnread && (
            <TouchableOpacity onPress={handleMarkAllRead} style={styles.markReadBtn}>
              <Ionicons name="checkmark" size={10} color={LIGHT_GOLD} />
              <Text style={styles.markReadText}>Mark all read</Text>
            </TouchableOpacity>
          )}
          <TouchableOpacity onPress={() => loadNotifications(false)} style={styles.refreshBtn}>
            <Ionicons name="refresh" size={14} color="#666" />
          </TouchableOpacity>
        </View>
      </View>

      {/* Filter Tabs */}
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        style={styles.filterContainer}
        contentContainerStyle={styles.filterContent}
      >
        {FILTERS.map(filter => {
          const isActive = activeFilter === filter.id;
          const typeCount = filter.id === 'all' 
            ? unreadCount
            : notificationsWithParsedTypes.filter(n => n.parsedType === filter.id && !n.is_read).length;
          
          return (
            <TouchableOpacity
              key={filter.id}
              onPress={() => setActiveFilter(filter.id)}
              style={[styles.filterTab, isActive && styles.filterTabActive]}
            >
              <Ionicons 
                name={filter.icon} 
                size={10} 
                color={isActive ? LIGHT_GOLD : '#666'} 
                style={{ marginRight: 1 }}
              />
              <Text style={[styles.filterLabel, isActive && styles.filterLabelActive]}>
                {filter.label}
              </Text>
              {typeCount > 0 && (
                <View style={styles.filterBadge}>
                  <Text style={styles.filterBadgeText}>{typeCount}</Text>
                </View>
              )}
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* List */}
      {loading ? (
        <View style={styles.centered}>
          <ActivityIndicator size="large" color={GOLD} />
        </View>
      ) : (
        <View style={styles.listContainer}>
          <FlatList
            data={filtered}
            keyExtractor={n => n.uniqueKey || String(n.id)}
            renderItem={renderItem}
          refreshControl={
            <RefreshControl 
              refreshing={refreshing} 
              onRefresh={() => { setRefreshing(true); loadNotifications(); }} 
              tintColor={GOLD} 
            />
          }
          ListEmptyComponent={
            <View style={styles.empty}>
              <View style={styles.emptyIcon}>
                <Ionicons name="notifications-off-outline" size={32} color="#666" />
              </View>
              <Text style={styles.emptyTitle}>
                {activeFilter === 'all' ? 'No notifications yet' : `No ${activeFilter} notifications`}
              </Text>
              <Text style={styles.emptyText}>
                {activeFilter === 'all'
                  ? "When someone likes, comments, or follows you, it'll show up here."
                  : 'Switch to All to see everything.'}
              </Text>
            </View>
          }
        />
        </View>
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: BG 
  },
  
  // Header
  header: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    justifyContent: 'space-between',
    paddingHorizontal: 16, 
    paddingVertical: 12,
    borderBottomWidth: 1, 
    borderBottomColor: BORDER,
    backgroundColor: CARD,
  },
  headerLeft: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  iconContainer: {
    position: 'relative',
  },
  unreadDot: {
    position: 'absolute',
    top: -2,
    right: -2,
    width: 6,
    height: 6,
    borderRadius: 3,
    backgroundColor: '#EF4444',
    borderWidth: 1.5,
    borderColor: CARD,
  },
  headerTitle: { 
    fontSize: 16, 
    fontWeight: '700', 
    color: '#fff' 
  },
  headerRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  markReadBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 16,
  },
  markReadText: {
    fontSize: 11,
    fontWeight: '600',
    color: LIGHT_GOLD,
  },
  refreshBtn: {
    padding: 6,
    borderWidth: 1,
    borderColor: BORDER,
    borderRadius: 16,
  },
  
  // Filters
  filterContainer: {
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    backgroundColor: BG,
    maxHeight: 44,
  },
  filterContent: {
    paddingHorizontal: 8,
    flexDirection: 'row',
    alignItems: 'center',
  },
  filterTab: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
    paddingHorizontal: 10,
    paddingVertical: 10,
    borderBottomWidth: 2,
    borderBottomColor: 'transparent',
  },
  filterTabActive: {
    borderBottomColor: LIGHT_GOLD,
  },
  filterLabel: {
    fontSize: 12,
    fontWeight: '500',
    color: '#666',
    lineHeight: 18,
  },
  filterLabelActive: {
    fontSize: 12,
    fontWeight: '700',
    color: LIGHT_GOLD,
    lineHeight: 18,
  },
  filterBadge: {
    backgroundColor: '#EF4444',
    borderRadius: 8,
    paddingHorizontal: 4,
    paddingVertical: 1,
    minWidth: 16,
    alignItems: 'center',
    justifyContent: 'center',
  },
  filterBadgeText: {
    fontSize: 9,
    fontWeight: '800',
    color: '#fff',
  },
  
  // List container
  listContainer: {
    flex: 1,
    backgroundColor: BG,
  },
  
  // List items
  item: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    paddingVertical: 12,
    paddingHorizontal: 16,
    borderBottomWidth: 1, 
    borderBottomColor: BORDER,
    backgroundColor: CARD,
    marginHorizontal: 16,
    marginVertical: 2,
    borderRadius: 8,
  },
  unread: { 
    backgroundColor: LIGHT_GOLD + '15',
    borderLeftWidth: 3,
    borderLeftColor: LIGHT_GOLD,
  },
  
  // Avatar
  avatarContainer: {
    position: 'relative',
    marginRight: 12,
  },
  avatar: { 
    width: 48, 
    height: 48, 
    borderRadius: 24 
  },
  avatarPlaceholder: {
    backgroundColor: GOLD + '30',
    justifyContent: 'center',
    alignItems: 'center',
  },
  avatarText: {
    fontSize: 18,
    fontWeight: '700',
    color: GOLD,
  },
  typeBadge: {
    position: 'absolute',
    bottom: -2,
    right: -2,
    width: 20,
    height: 20,
    borderRadius: 10,
    backgroundColor: GOLD,
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: BG,
  },
  
  // Content
  content: {
    flex: 1,
  },
  message: {
    fontSize: 14,
    lineHeight: 19,
  },
  username: {
    fontWeight: '700',
    color: '#fff',
  },
  messageText: {
    color: '#999',
  },
  messageUnread: {
    color: '#ddd',
  },
  extras: {
    color: '#666',
  },
  comment: {
    fontSize: 12,
    color: '#666',
    fontStyle: 'italic',
    marginTop: 3,
  },
  time: { 
    fontSize: 11, 
    color: '#666', 
    marginTop: 3,
    fontWeight: '400',
  },
  timeUnread: {
    fontWeight: '600',
  },
  
  // Thumbnail
  thumb: { 
    width: 44, 
    height: 44, 
    borderRadius: 6, 
    marginLeft: 10 
  },
  
  // Empty state
  centered: { 
    flex: 1, 
    justifyContent: 'center', 
    alignItems: 'center', 
    padding: 40 
  },
  empty: {
    alignItems: 'center',
    padding: 60,
    paddingTop: 80,
  },
  emptyIcon: {
    width: 72,
    height: 72,
    borderRadius: 36,
    backgroundColor: CARD,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 16,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 6,
  },
  emptyText: {
    fontSize: 13,
    color: '#666',
    textAlign: 'center',
    lineHeight: 18,
  },
});
