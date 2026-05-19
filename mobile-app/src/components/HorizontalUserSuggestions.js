import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const TEXT = '#fff';
const SUB = '#666';

export default React.memo(function HorizontalUserSuggestions({ onUserClick, onDismiss }) {
  const [suggestions, setSuggestions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [followingStates, setFollowingStates] = useState({});
  const [dismissedUsers, setDismissedUsers] = useState(new Set());

  useEffect(() => {
    fetchSuggestions();
  }, []);

  const fetchSuggestions = async () => {
    try {
      setLoading(true);
      const raw = await api.getUserSuggestions();
      const all = Array.isArray(raw) ? raw : (raw.results || []);
      const data = all.filter(u => !u.is_staff && !u.is_superuser).slice(0, 10);
      
      if (!data || data.length === 0) {
        setSuggestions([]);
        setLoading(false);
        return;
      }
      
      setSuggestions(data);
      
      const states = {};
      data.forEach(user => {
        states[user.id] = user.is_following || false;
      });
      setFollowingStates(states);
    } catch (error) {
      console.error("Failed to fetch suggestions:", error);
      setSuggestions([]);
    } finally {
      setLoading(false);
    }
  };

  const handleFollowToggle = async (userId) => {
    try {
      const response = await api.toggleFollow(userId);
      setFollowingStates(prev => ({
        ...prev,
        [userId]: response.following
      }));
    } catch (error) {
      console.error("Failed to toggle follow:", error);
    }
  };

  const handleNotInterested = (userId, event) => {
    event.stopPropagation();
    setDismissedUsers(prev => new Set([...prev, userId]));
    // Remove from suggestions list
    setSuggestions(prev => prev.filter(user => user.id !== userId));
  };

  if (loading) return null;
  if (!suggestions || suggestions.length === 0) return null;

  return (
    <View style={styles.container}>
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Suggested for you</Text>
        <TouchableOpacity onPress={onDismiss} style={styles.dismissBtn}>
          <Ionicons name="close" size={18} color={SUB} />
        </TouchableOpacity>
      </View>

      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false}
        contentContainerStyle={styles.scrollContent}
      >
        {suggestions.map(user => {
          const isFollowing = followingStates[user.id];
          const avatar = user.profile_photo ? user.profile_photo : null;

          return (
            <TouchableOpacity
              key={user.id}
              onPress={() => onUserClick?.(user.id)}
              style={styles.suggestionCard}
              activeOpacity={0.7}
            >
              <View style={styles.avatarContainer}>
                {avatar ? (
                  <Image source={{ uri: avatar }} style={styles.avatarImage} />
                ) : (
                  <View style={styles.avatarPlaceholder}>
                    <Ionicons name="person" size={24} color={SUB} />
                  </View>
                )}
              </View>
              
              <Text style={styles.username} numberOfLines={1}>
                {user.username}
              </Text>
              
              <Text style={styles.fullName} numberOfLines={1}>
                {user.first_name ? `${user.first_name} ${user.last_name || ''}` : 'Suggested for you'}
              </Text>

              <TouchableOpacity
                onPress={() => handleFollowToggle(user.id)}
                style={[
                  styles.followBtn,
                  isFollowing && styles.followingBtn
                ]}
              >
                <Ionicons 
                  name={isFollowing ? "checkmark" : "person-add"} 
                  size={14} 
                  color={isFollowing ? GOLD : '#000'} 
                />
                <Text style={[
                  styles.followBtnText,
                  isFollowing && styles.followingBtnText
                ]}>
                  {isFollowing ? 'Following' : 'Follow'}
                </Text>
              </TouchableOpacity>

              <TouchableOpacity
                onPress={(e) => handleNotInterested(user.id, e)}
                style={styles.notInterestedBtn}
              >
                <Ionicons name="close" size={14} color={SUB} />
              </TouchableOpacity>
            </TouchableOpacity>
          );
        })}
      </ScrollView>
    </View>
  );
});

const styles = StyleSheet.create({
  container: {
    marginVertical: 12,
    backgroundColor: CARD,
    borderTopWidth: 1,
    borderTopColor: BORDER,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    paddingVertical: 16,
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    marginBottom: 12,
  },
  headerTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: TEXT,
  },
  dismissBtn: {
    padding: 4,
  },
  scrollContent: {
    paddingHorizontal: 16,
    gap: 12,
  },
  suggestionCard: {
    width: 150,
    minWidth: 150,
    backgroundColor: BG,
    borderWidth: 1.5,
    borderColor: 'rgba(200, 181, 106, 0.35)',
    borderRadius: 12,
    padding: 16,
    alignItems: 'center',
  },
  avatarContainer: {
    marginBottom: 10,
  },
  avatarImage: {
    width: 70,
    height: 70,
    borderRadius: 35,
  },
  avatarPlaceholder: {
    width: 70,
    height: 70,
    borderRadius: 35,
    backgroundColor: '#333',
    justifyContent: 'center',
    alignItems: 'center',
  },
  username: {
    fontSize: 13,
    fontWeight: '700',
    color: TEXT,
    marginBottom: 2,
  },
  fullName: {
    fontSize: 11,
    color: SUB,
    marginBottom: 12,
  },
  followBtn: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 4,
    paddingVertical: 7,
    borderRadius: 8,
    backgroundColor: GOLD,
  },
  followingBtn: {
    backgroundColor: 'rgba(200, 181, 106, 0.15)',
    borderWidth: 1.5,
    borderColor: 'rgba(200, 181, 106, 0.6)',
  },
  followBtnText: {
    fontSize: 12,
    fontWeight: '700',
    color: '#000',
  },
  followingBtnText: {
    color: GOLD,
  },
  notInterestedBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    padding: 4,
    borderRadius: 12,
    backgroundColor: 'rgba(102, 102, 102, 0.3)',
  },
});
