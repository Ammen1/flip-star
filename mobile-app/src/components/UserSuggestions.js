import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, TouchableOpacity, ScrollView, ActivityIndicator, Image } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

const GOLD = '#C8B56A', BG = '#0D0D0D', CARD = '#1A1A1A', BORDER = '#262626';

export default React.memo(function UserSuggestions({ onUserClick }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [followingStates, setFollowingStates] = useState({});

  useEffect(() => {
    if (api.hasToken()) {
      fetchSuggestionsWithCache();
    } else {
      setLoading(false);
    }
  }, [fetchSuggestionsWithCache]);

  // Cache suggestions for 5 minutes to avoid repeated fetches
  const CACHE_DURATION = 5 * 60 * 1000; // 5 minutes
  const [lastFetchTime, setLastFetchTime] = useState(null);

  const fetchSuggestionsWithCache = useCallback(async () => {
    const now = Date.now();
    if (lastFetchTime && (now - lastFetchTime < CACHE_DURATION) && suggestions.length > 0) {
      return; // Use cached data
    }
    await fetchSuggestions();
    setLastFetchTime(now);
  }, [lastFetchTime, suggestions.length, fetchSuggestions]);

  const fetchSuggestions = async () => {
    try {
      setLoading(true);
      const raw = await api.getUserSuggestions();
      const all = Array.isArray(raw) ? raw : (raw.results || []);
      const data = all.filter(u => !u.is_staff && !u.is_superuser).slice(0, 10);
      setSuggestions(data);

      const states = {};
      data.forEach(user => {
        states[user.id] = user.is_following || false;
      });
      setFollowingStates(states);
    } catch (error) {
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFollowToggle = useCallback(async (userId) => {
    try {
      const response = await api.toggleFollow(userId);
      setFollowingStates(prev => ({
        ...prev,
        [userId]: response.following
      }));

      setSuggestions(prev => prev.map(user => 
        user.id === userId 
          ? { ...user, followers_count: user.followers_count + (response.following ? 1 : -1) }
          : user
      ));
    } catch (error) {
      console.error("Failed to toggle follow:", error);
    }
  }, []);

  const renderSuggestion = useCallback((user) => {
    const isFollowing = followingStates[user.id];
    return (
      <TouchableOpacity
        key={user.id}
        style={styles.suggestionCard}
        onPress={() => onUserClick?.(user)}
        activeOpacity={0.8}
      >
        <View style={styles.avatarContainer}>
          {user.profile_photo ? (
            <Image source={{ uri: user.profile_photo }} style={styles.avatar} />
          ) : (
            <Text style={styles.avatarText}>👤</Text>
          )}
        </View>
        <Text style={styles.username} numberOfLines={1}>{user.username}</Text>
        <Text style={styles.fullname} numberOfLines={1}>
          {user.first_name ? `${user.first_name} ${user.last_name || ''}` : 'Suggested for you'}
        </Text>
        <TouchableOpacity
          style={[styles.followButton, isFollowing && styles.followingButton]}
          onPress={(e) => {
            e.stopPropagation();
            handleFollowToggle(user.id);
          }}
        >
          <Ionicons 
            name={isFollowing ? "checkmark" : "add"} 
            size={14} 
            color={isFollowing ? GOLD : '#000'} 
          />
          <Text style={[styles.followButtonText, isFollowing && styles.followingButtonText]}>
            {isFollowing ? 'Following' : 'Follow'}
          </Text>
        </TouchableOpacity>
      </TouchableOpacity>
    );
  }, [followingStates, onUserClick, handleFollowToggle]);

  if (loading) {
    return (
      <View style={styles.container}>
        <View style={styles.header}>
          <Text style={styles.title}>Suggested for you</Text>
        </View>
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="small" color={GOLD} />
        </View>
      </View>
    );
  }

  if (suggestions.length === 0) {
    return null;
  }

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.title}>Suggested for you</Text>
      </View>
      <ScrollView
        horizontal
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {suggestions.map(renderSuggestion)}
      </ScrollView>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    marginVertical: 8,
    backgroundColor: CARD,
    borderTopWidth: 1,
    borderBottomWidth: 1,
    borderColor: BORDER,
    paddingVertical: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  title: {
    fontSize: 14,
    fontWeight: '700',
    color: '#fff',
  },
  loadingContainer: {
    padding: 20,
    alignItems: 'center',
  },
  scrollContent: {
    paddingHorizontal: 16,
    gap: 12,
  },
  suggestionCard: {
    width: 150,
    minWidth: 150,
    backgroundColor: '#1A1A1A',
    borderWidth: 1.5,
    borderColor: 'rgba(200,181,106,0.35)',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  avatarContainer: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: GOLD + '20',
    marginBottom: 10,
    overflow: 'hidden',
    justifyContent: 'center',
    alignItems: 'center',
    borderWidth: 2,
    borderColor: CARD,
  },
  avatar: {
    width: '100%',
    height: '100%',
  },
  avatarText: {
    fontSize: 24,
  },
  username: {
    fontSize: 13,
    fontWeight: '700',
    color: '#fff',
    marginBottom: 2,
  },
  fullname: {
    fontSize: 11,
    color: '#888',
    marginBottom: 12,
  },
  followButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 8,
    backgroundColor: GOLD,
    width: '100%',
    justifyContent: 'center',
  },
  followingButton: {
    backgroundColor: 'rgba(249,224,139,0.15)',
    borderWidth: 1.5,
    borderColor: 'rgba(249,224,139,0.6)',
  },
  followButtonText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#000',
  },
  followingButtonText: {
    color: GOLD,
  },
});
