import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  View, Text, StyleSheet, TextInput, TouchableOpacity, FlatList,
  Image, ActivityIndicator, Dimensions, ScrollView,
  StatusBar, Alert,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import config from '../config';

const { width, height } = Dimensions.get('window');
const GOLD = '#C8B56A';
const LIGHT_GOLD = '#F9E08B';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const COLS = 3;
const GAP = 1; // Minimal gap between items
const ITEM_SIZE = Math.floor((width - (GAP * (COLS - 1))) / COLS); // Calculate exact size for 3 columns

// Categories matching website
const CATEGORIES = [
  { id: 'all', label: 'Trending', icon: 'flame', emoji: '🔥' },
  { id: 'dance', label: 'Dance', icon: 'musical-note', emoji: '💃' },
  { id: 'comedy', label: 'Comedy', icon: 'happy', emoji: '😂' },
  { id: 'sports', label: 'Sports', icon: 'football', emoji: '⚽' },
  { id: 'food', label: 'Food', icon: 'restaurant', emoji: '🍕' },
  { id: 'travel', label: 'Travel', icon: 'airplane', emoji: '✈️' },
  { id: 'art', label: 'Art', icon: 'palette', emoji: '🎨' },
  { id: 'gaming', label: 'Gaming', icon: 'game-controller', emoji: '🎮' },
  { id: 'beauty', label: 'Beauty', icon: 'sparkles', emoji: '✨' },
  { id: 'fashion', label: 'Fashion', icon: 'shirt', emoji: '👗' },
  { id: 'education', label: 'Learn', icon: 'book', emoji: '📚' },
];

const TIME_RANGES = [
  { id: '24h', label: '24h' },
  { id: '7d', label: '7 days' },
  { id: '30d', label: '30d' },
];

// Helper functions
const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

const fmt = (n) => {
  if (!n && n !== 0) return '0';
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
  return String(n);
};

// Avatar component
const Avatar = React.memo(function Avatar({ uri, size = 40, name = '' }) {
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
          borderWidth: 2,
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
      borderWidth: 2,
      borderColor: '#fff'
    }}>
      <Text style={{ color: '#000', fontWeight: '700', fontSize: size * 0.4 }}>
        {safeName[0].toUpperCase()}
      </Text>
    </View>
  );
});

// Video thumbnail component matching website
const VideoThumb = React.memo(function VideoThumb({ reel, rank, index = 0, hero = false, onOpen }) {
  const videoUrl = reel.file_url || reel.media;
  const imageUrl = reel.image || reel.media;
  const isVid = !!(videoUrl || '').match(/\.(mp4|webm|ogg|mov)/i) || (videoUrl && videoUrl.includes('/video/'));
  
  // Try different URL patterns for thumbnail
  let thumb = null;
  
  // Priority: 1) thumbnail, 2) image, 3) media, 4) file_url
  if (reel.thumbnail) {
    thumb = mediaUrl(reel.thumbnail);
  } else if (imageUrl) {
    thumb = mediaUrl(imageUrl);
  } else if (videoUrl) {
    thumb = mediaUrl(videoUrl);
  } else if (reel.file_url) {
    thumb = mediaUrl(reel.file_url);
  }

  // If still no thumbnail, try to construct from common patterns
  if (!thumb && reel.id) {
    thumb = `${config.API_BASE_URL.replace('/api', '')}/media/thumbnails/${reel.id}.jpg`;
  }

  return (
    <TouchableOpacity
      style={[
        styles.gridItem,
        hero && styles.heroItem
      ]}
      onPress={() => onOpen?.(reel)}
    >
      {thumb ? (
        <Image
          source={{ uri: thumb }}
          style={styles.gridImage}
          resizeMode="cover"
        />
      ) : (
        <View style={[styles.gridImage, styles.fallbackContainer]}>
          <Ionicons
            name={isVid ? 'play' : 'image'}
            size={hero ? 48 : 28}
            color="#666"
          />
          <Text style={styles.fallbackText}>
            {isVid ? 'Video' : 'Image'}
          </Text>
        </View>
      )}

      {/* Video indicator */}
      {isVid && (
        <View style={styles.videoIcon}>
          <Ionicons name="play" size={hero ? 12 : 9} color="#fff" />
        </View>
      )}

      {/* Rank medal (top 3) */}
      {rank !== undefined && rank < 3 && (
        <View style={[
          styles.rankBadge,
          { backgroundColor: rank === 0 ? '#FFD700' : rank === 1 ? '#C0C0C0' : '#CD7F32' }
        ]}>
          <Text style={[styles.rankText, { color: '#000' }]}>{rank + 1}</Text>
        </View>
      )}

      {/* Bottom stats */}
      <View style={styles.gridOverlay}>
        {hero && reel.user?.username && (
          <Text style={styles.heroUsername}>@{reel.user.username}</Text>
        )}
        <View style={styles.statsRow}>
          <Ionicons name="heart" size={hero ? 13 : 10} color={LIGHT_GOLD} />
          <Text style={[styles.gridStat, { color: LIGHT_GOLD }]}>
            {fmt(reel.votes || 0)}
          </Text>
        </View>
        {(reel.comment_count > 0 || reel.comments > 0) && (
          <View style={styles.statsRow}>
            <Ionicons name="eye" size={hero ? 12 : 10} color="rgba(255,255,255,0.8)" />
            <Text style={styles.gridStat}>
              {fmt(reel.comment_count || reel.comments || 0)}
            </Text>
          </View>
        )}
      </View>
    </TouchableOpacity>
  );
});

// Skeleton loader component
function GridSkeleton() {
  return (
    <View style={styles.grid}>
      {Array.from({ length: 9 }).map((_, i) => (
        <View key={i} style={styles.skeletonItem} />
      ))}
    </View>
  );
}

export default function ExploreScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const auth = useAuth();
  const { colors } = useTheme();
  const user = auth?.user ?? null;

  // Explore state
  const [activeCategory, setActiveCategory] = useState('all');
  const [timeRange, setTimeRange] = useState('7d');
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [hashtags, setHashtags] = useState([]);
  const [hashLoading, setHashLoading] = useState(true);
  const [showHashtagDropdown, setShowHashtagDropdown] = useState(false);
  const [hashtagView, setHashtagView] = useState(null);

  // Search state
  const [query, setQuery] = useState('');
  const [debouncedQ, setDebouncedQ] = useState('');
  const [searchFocused, setSearchFocused] = useState(false);
  const [searchResults, setSearchResults] = useState({ users: [], posts: [], hashtags: [] });
  const [searchLoading, setSearchLoading] = useState(false);

  // Pagination
  const [loadingMore, setLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const INITIAL_LIMIT = 12;
  const PAGE_LIMIT = 12;

  const inSearchMode = debouncedQ.trim().length > 0;

  // Fetch trending videos
  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setHasMore(true);
    
    const category = activeCategory === 'all' ? 'all' : activeCategory;
    api.request(`/explorer/trending/?category=${category}&time_range=${timeRange}&limit=${INITIAL_LIMIT}`)
      .then(d => {
        if (cancelled) return;
        const list = Array.isArray(d) ? d : (d?.results || []);
        setVideos(list);
        setHasMore(list.length >= INITIAL_LIMIT);
      })
      .catch(() => { if (!cancelled) setVideos([]); })
      .finally(() => { if (!cancelled) setLoading(false); });
    
    return () => { cancelled = true; };
  }, [activeCategory, timeRange]);

  // Load more videos
  const loadMore = useCallback(() => {
    if (inSearchMode || loadingMore || !hasMore || loading) return;
    
    setLoadingMore(true);
    const category = activeCategory === 'all' ? 'all' : activeCategory;
    const offset = videos.length;
    
    api.request(`/explorer/trending/?category=${category}&time_range=${timeRange}&limit=${PAGE_LIMIT}&offset=${offset}`)
      .then(d => {
        const page = Array.isArray(d) ? d : (d?.results || []);
        if (page.length === 0) {
          setHasMore(false);
        } else {
          // Dedup by id
          setVideos(prev => {
            const seen = new Set(prev.map(v => v.id));
            return [...prev, ...page.filter(v => !seen.has(v.id))];
          });
          if (page.length < PAGE_LIMIT) setHasMore(false);
        }
      })
      .catch(() => { /* keep what we have */ })
      .finally(() => setLoadingMore(false));
  }, [activeCategory, timeRange, videos.length, hasMore, loading, loadingMore, inSearchMode]);

  // Fetch trending hashtags
  useEffect(() => {
    let cancelled = false;
    setHashLoading(true);
    
    api.request(`/explorer/trending-hashtags/?time_range=${timeRange}&limit=15`)
      .then(d => { if (!cancelled) setHashtags(Array.isArray(d) ? d : []); })
      .catch(() => { if (!cancelled) setHashtags([]); })
      .finally(() => { if (!cancelled) setHashLoading(false); });
    
    return () => { cancelled = true; };
  }, [timeRange]);

  // Debounce search query
  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(query), 300);
    return () => clearTimeout(t);
  }, [query]);

  // Live search
  useEffect(() => {
    if (!debouncedQ.trim()) { 
      setSearchResults({ users: [], posts: [], hashtags: [] }); 
      return; 
    }
    
    let cancelled = false;
    setSearchLoading(true);
    
    api.request(`/search/?q=${encodeURIComponent(debouncedQ.trim())}`)
      .then(d => { if (!cancelled) setSearchResults(d || { users: [], posts: [], hashtags: [] }); })
      .catch(() => { if (!cancelled) setSearchResults({ users: [], posts: [], hashtags: [] }); })
      .finally(() => { if (!cancelled) setSearchLoading(false); });
    
    return () => { cancelled = true; };
  }, [debouncedQ]);

  const clearSearch = () => {
    setQuery('');
    setDebouncedQ('');
    setSearchFocused(false);
  };

  const handleHashtagClick = async (tag) => {
    const cleanTag = tag.replace(/^#/, '');
    setLoading(true);
    try {
      const data = await api.request(`/explorer/hashtag/?tag=${encodeURIComponent(cleanTag)}&limit=30`);
      const results = data?.results || [];
      setHashtagView({ tag: cleanTag, videos: results, count: data?.count || results.length });
      setVideos(results);
    } catch (e) {
      console.error('Failed to fetch hashtag:', e);
      setHashtagView({ tag: cleanTag, videos: [], count: 0 });
      setVideos([]);
    } finally {
      setLoading(false);
    }
  };

  const clearHashtagView = () => {
    setHashtagView(null);
    // Re-fetch trending
    setLoading(true);
    const category = activeCategory === 'all' ? 'all' : activeCategory;
    api.request(`/explorer/trending/?category=${category}&time_range=${timeRange}&limit=30`)
      .then(d => setVideos(Array.isArray(d) ? d : (d?.results || [])))
      .catch(() => setVideos([]))
      .finally(() => setLoading(false));
  };

  const openReel = useCallback((reel) => {
    console.log('ExploreScreen - openReel called with:', { 
      id: reel.id, 
      media: reel.media, 
      file_url: reel.file_url,
      image: reel.image, 
      thumbnail: reel.thumbnail 
    });
    
    // Check both media and file_url like VideoThumb does
    const videoUrl = reel.file_url || reel.media;
    const isVideo = !!(videoUrl || '').match(/\.(mp4|webm|ogg|mov)/i) || (videoUrl && videoUrl.includes('/video/'));
    
    console.log('ExploreScreen - isVideo:', isVideo, 'videoUrl:', videoUrl);
    
    if (isVideo) {
      // Videos go to ReelsDetail
      console.log('ExploreScreen - Navigating to ReelsDetail for video');
      navigation.navigate('ReelsDetail', { initialVideoId: reel.id });
    } else {
      // Images go to Home screen with post detail
      console.log('ExploreScreen - Navigating to Home for image post');
      navigation.navigate('Home', { postId: reel.id });
    }
  }, [navigation]);

  const openProfile = (userId) => {
    navigation.navigate('Profile', { userId });
  };

  const renderGridItem = useCallback(({ item, index }) => (
    <VideoThumb
      reel={item}
      rank={index}
      index={index}
      hero={index === 0 && !inSearchMode}
      onOpen={openReel}
    />
  ), [inSearchMode, openReel]);

  return (
    <View style={[styles.container, { backgroundColor: colors.bg }]}>
      <StatusBar barStyle={colors.text === '#FFFFFF' ? 'light-content' : 'dark-content'} backgroundColor="transparent" translucent={true} />
      
      {/* Sticky Header - Overlays with status bar */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, paddingTop: insets.top }]}>
        {/* Row 1 - Header with search */}
        <View style={styles.headerRow1}>
          {/* Back button */}
          <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
            <Ionicons name="chevron-back" size={20} color={colors.primary} />
          </TouchableOpacity>
          
          {/* Search bar */}
          <View style={[styles.searchContainer, { backgroundColor: colors.bg, borderColor: colors.border }]}>
            <Ionicons name="search" size={16} color={colors.textSecondary} style={styles.searchIcon} />
            <TextInput
              style={[styles.searchInput, { color: colors.text, backgroundColor: colors.bg }]}
              placeholder="Search videos, users, hashtags..."
              placeholderTextColor={colors.textSecondary}
              value={query}
              onChangeText={setQuery}
              onFocus={() => setShowHashtagDropdown(false)}
            />
            {query && (
              <TouchableOpacity onPress={clearSearch} style={styles.clearButton}>
                <Ionicons name="close" size={12} color={colors.textSecondary} />
              </TouchableOpacity>
            )}
          </View>
          
          {/* Time range pills */}
          {!inSearchMode && !searchFocused && (
            <View style={styles.timeRangeContainer}>
              {TIME_RANGES.map(r => (
                <TouchableOpacity
                  key={r.id}
                  onPress={() => { setTimeRange(r.id); setHashtagView(null); }}
                  style={[
                    styles.timeChip,
                    { backgroundColor: colors.cardBg, borderColor: colors.border },
                    timeRange === r.id && { backgroundColor: colors.primary }
                  ]}
                >
                  <Text style={[
                    styles.timeText,
                    { color: colors.textSecondary },
                    timeRange === r.id && { color: '#000' }
                  ]}>
                    {r.label}
                  </Text>
                </TouchableOpacity>
              ))}
            </View>
          )}
        </View>

        {/* Row 2 - Category navigation */}
        {!inSearchMode && (
          <View style={styles.categoryRow}>
            <ScrollView 
              horizontal 
              showsHorizontalScrollIndicator={false}
              contentContainerStyle={styles.categoryScroll}
            >
              {CATEGORIES.map(cat => {
                const isActive = activeCategory === cat.id;
                return (
                  <TouchableOpacity
                    key={cat.id}
                    onPress={() => { setActiveCategory(cat.id); setHashtagView(null); }}
                    style={[
                      styles.categoryChip,
                      { backgroundColor: colors.cardBg, borderColor: colors.border },
                      isActive && { backgroundColor: colors.primary }
                    ]}
                  >
                    <Text style={styles.categoryEmoji}>{cat.emoji}</Text>
                    <Text style={[
                      styles.categoryText,
                      { color: colors.textSecondary },
                      isActive && { color: '#000' }
                    ]}>
                      {cat.label}
                    </Text>
                  </TouchableOpacity>
                );
              })}
            </ScrollView>
          </View>
        )}
      </View>

      {/* Scrollable Content */}
      <ScrollView style={styles.content} showsVerticalScrollIndicator={false}>
        {inSearchMode ? (
          // Search Results
          <View style={styles.searchResults}>
            {searchLoading ? (
              <View style={styles.searchLoading}>
                {[0,1,2,3].map(i => (
                  <View key={i} style={styles.searchSkeleton} />
                ))}
              </View>
            ) : (
              <>
                {/* Users */}
                {searchResults.users?.length > 0 && (
                  <View style={styles.searchSection}>
                    <Text style={styles.sectionTitle}>PEOPLE</Text>
                    {searchResults.users.map(u => (
                      <TouchableOpacity
                        key={u.id}
                        onPress={() => openProfile(u.id)}
                        style={styles.userRow}
                      >
                        <Avatar uri={u.profile_photo} size={42} name={u.username} />
                        <View style={styles.userInfo}>
                          <Text style={styles.userName}>@{u.username}</Text>
                          {u.followers_count > 0 && (
                            <Text style={styles.userFollowers}>
                              {fmt(u.followers_count)} followers
                            </Text>
                          )}
                        </View>
                        <Ionicons name="chevron-forward" size={16} color="#666" />
                      </TouchableOpacity>
                    ))}
                  </View>
                )}

                {/* Hashtags */}
                {searchResults.hashtags?.length > 0 && (
                  <View style={styles.searchSection}>
                    <Text style={styles.sectionTitle}>HASHTAGS</Text>
                    <View style={styles.hashtagGrid}>
                      {searchResults.hashtags.map(tag => (
                        <TouchableOpacity
                          key={tag}
                          onPress={() => handleHashtagClick(tag)}
                          style={styles.hashtagChip}
                        >
                          <Text style={styles.hashtagText}>#{tag}</Text>
                        </TouchableOpacity>
                      ))}
                    </View>
                  </View>
                )}

                {/* Posts */}
                {searchResults.posts?.length > 0 && (
                  <View style={styles.searchSection}>
                    <Text style={styles.sectionTitle}>POSTS</Text>
                    <View style={styles.grid}>
                      {searchResults.posts.map((r, i) => (
                        <VideoThumb
                          key={r.id ?? i}
                          reel={r}
                          rank={i}
                          index={i}
                          hero={false}
                          onOpen={openReel}
                        />
                      ))}
                    </View>
                  </View>
                )}

                {/* No results */}
                {!searchResults.users?.length && !searchResults.hashtags?.length && !searchResults.posts?.length && (
                  <View style={styles.noResults}>
                    <Ionicons name="search" size={40} color="#666" style={{ opacity: 0.3, marginBottom: 12 }} />
                    <Text style={styles.noResultsTitle}>No results for "{debouncedQ}"</Text>
                    <Text style={styles.noResultsText}>Try different keywords or browse trending below</Text>
                  </View>
                )}
              </>
            )}
          </View>
        ) : (
          // Explore Mode
          <View style={styles.exploreContent}>
            {/* Trending hashtags dropdown */}
            {!hashLoading && hashtags.length > 0 && (
              <View style={styles.hashtagSection}>
                <TouchableOpacity
                  onPress={() => setShowHashtagDropdown(!showHashtagDropdown)}
                  style={styles.hashtagHeader}
                >
                  <View style={styles.hashtagTitleContainer}>
                    <Ionicons name="trending-up" size={13} color={LIGHT_GOLD} />
                    <Text style={styles.hashtagTitle}>TRENDING HASHTAGS</Text>
                  </View>
                  <Ionicons 
                    name="chevron-down" 
                    size={16} 
                    color={LIGHT_GOLD} 
                    style={{
                      transform: [{ rotate: showHashtagDropdown ? '180deg' : '0deg' }]
                    }}
                  />
                </TouchableOpacity>
                
                {showHashtagDropdown && (
                  <View style={styles.hashtagDropdown}>
                    {hashtags.map(h => (
                      <TouchableOpacity
                        key={h.tag}
                        onPress={() => handleHashtagClick(h.tag)}
                        style={styles.trendingHashtagChip}
                      >
                        <Text style={styles.trendingHashtagText}>#{h.tag}</Text>
                        <Text style={styles.trendingHashtagCount}>{fmt(h.posts)} posts</Text>
                      </TouchableOpacity>
                    ))}
                  </View>
                )}
              </View>
            )}
            
            {hashLoading && (
              <View style={styles.hashtagLoading}>
                {[0,1,2,3,4].map(i => (
                  <View key={i} style={styles.hashtagSkeleton} />
                ))}
              </View>
            )}

            {/* Hashtag view header */}
            {hashtagView && (
              <View style={styles.hashtagViewHeader}>
                <TouchableOpacity onPress={clearHashtagView} style={styles.hashtagBackButton}>
                  <Ionicons name="close" size={20} color="#fff" />
                </TouchableOpacity>
                <View style={styles.hashtagViewInfo}>
                  <Text style={styles.hashtagViewTitle}>#{hashtagView.tag}</Text>
                  <Text style={styles.hashtagViewCount}>{fmt(hashtagView.count)} posts</Text>
                </View>
                <Ionicons name="hash" size={28} color={LIGHT_GOLD} style={{ opacity: 0.5 }} />
              </View>
            )}

            {/* Trending video grid */}
            {loading ? (
              <GridSkeleton />
            ) : videos.length === 0 ? (
              <View style={styles.emptyState}>
                {hashtagView ? (
                  <>
                    <Ionicons name="hash" size={44} color="#666" style={{ opacity: 0.3, marginBottom: 12 }} />
                    <Text style={styles.emptyTitle}>No posts with #{hashtagView.tag}</Text>
                    <Text style={styles.emptyText}>Be the first to post with this hashtag!</Text>
                  </>
                ) : (
                  <>
                    <Ionicons name="trending-up" size={44} color="#666" style={{ opacity: 0.3, marginBottom: 12 }} />
                    <Text style={styles.emptyTitle}>Nothing trending yet</Text>
                    <Text style={styles.emptyText}>Check back soon or try a different category</Text>
                  </>
                )}
              </View>
            ) : (
              <>
                <View style={styles.grid}>
                  {videos.map((reel, idx) => (
                    <VideoThumb
                      key={reel.id ?? idx}
                      reel={reel}
                      rank={idx}
                      index={idx}
                      hero={idx === 0 && !inSearchMode}
                      onOpen={openReel}
                    />
                  ))}
                </View>
                
                {/* Load more indicator */}
                {hasMore && !hashtagView && (
                  <View style={styles.loadMoreContainer}>
                    {loadingMore && (
                      <ActivityIndicator size="small" color={LIGHT_GOLD} />
                    )}
                    <Text style={styles.loadMoreText}>
                      {loadingMore ? 'Loading more…' : 'Scroll for more'}
                    </Text>
                  </View>
                )}
                
                {!hasMore && videos.length > INITIAL_LIMIT && (
                  <View style={styles.endMessage}>
                    <Text style={styles.endText}>You're all caught up</Text>
                  </View>
                )}
              </>
            )}
          </View>
        )}
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  
  // Header Styles
  header: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    zIndex: 20,
    backgroundColor: 'rgba(13, 13, 13, 0.95)', // Semi-transparent background
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
    paddingBottom: 4,
  },
  headerRow1: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    paddingHorizontal: 16,
    paddingTop: 16,
    paddingBottom: 12,
  },
  backButton: {
    padding: 4,
  },
  titleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    fontSize: 20,
    fontWeight: '800',
    color: LIGHT_GOLD,
  },
  searchContainer: {
    flex: 1,
    position: 'relative',
  },
  searchIcon: {
    position: 'absolute',
    left: 12,
    top: '50%',
    transform: [{ translateY: -8 }],
  },
  searchInput: {
    width: '100%',
    padding: '10px 36px 10px 40px',
    borderRadius: 24,
    borderWidth: 1.5,
    borderColor: BORDER,
    fontSize: 14,
    backgroundColor: BG,
    color: '#fff',
  },
  clearButton: {
    position: 'absolute',
    right: 10,
    top: '50%',
    transform: [{ translateY: -8 }],
    padding: 4,
  },
  timeRangeContainer: {
    flexDirection: 'row',
    gap: 6,
  },
  timeChip: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 18,
    borderWidth: 1.5,
    borderColor: BORDER,
    backgroundColor: 'transparent',
  },
  timeChipActive: {
    borderColor: LIGHT_GOLD,
    backgroundColor: LIGHT_GOLD,
  },
  timeText: {
    fontSize: 11,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  timeTextActive: {
    color: '#000',
  },
  
  // Category Navigation
  categoryRow: {
    paddingHorizontal: 16,
    paddingBottom: 12,
    paddingTop: 4,
  },
  categoryScroll: {
    gap: 6,
  },
  categoryChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: BORDER,
    backgroundColor: BG,
  },
  categoryChipActive: {
    backgroundColor: LIGHT_GOLD + '15',
    borderColor: LIGHT_GOLD + '30',
  },
  categoryEmoji: {
    fontSize: 14,
  },
  categoryText: {
    fontSize: 12,
    fontWeight: '600',
    color: '#fff',
  },
  categoryTextActive: {
    color: LIGHT_GOLD,
  },
  
  // Content
  content: {
    flex: 1,
    marginTop: 0, // Content starts from top since header is absolute
  },
  
  // Search Results
  searchResults: {
    paddingTop: 120, // Add top padding to account for absolute header
    paddingHorizontal: 0, // Remove side padding to fill full width
    paddingBottom: 32,
  },
  searchLoading: {
    flexDirection: 'column',
    gap: 10,
    paddingTop: 8,
  },
  searchSkeleton: {
    height: 56,
    borderRadius: 12,
    backgroundColor: BORDER,
  },
  searchSection: {
    marginBottom: 28,
  },
  sectionTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: LIGHT_GOLD,
    marginBottom: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  userRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: '10px 12px',
    borderRadius: 12,
  },
  userInfo: {
    flex: 1,
  },
  userName: {
    fontSize: 14,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  userFollowers: {
    fontSize: 12,
    color: LIGHT_GOLD,
  },
  hashtagGrid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  hashtagChip: {
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
    backgroundColor: LIGHT_GOLD + '18',
    borderWidth: 1,
    borderColor: LIGHT_GOLD + '40',
  },
  hashtagText: {
    fontSize: 14,
    fontWeight: '700',
    color: LIGHT_GOLD,
  },
  noResults: {
    alignItems: 'center',
    padding: '60px 20px',
  },
  noResultsTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: LIGHT_GOLD,
    marginBottom: 6,
  },
  noResultsText: {
    fontSize: 13,
    color: '#666',
  },
  
  // Explore Content
  exploreContent: {
    paddingTop: 120, // Add top padding to account for absolute header
    paddingHorizontal: 0, // Remove side padding to fill full width
    paddingBottom: 32,
  },
  
  // Hashtag Section
  hashtagSection: {
    marginBottom: 20,
  },
  hashtagHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '10px 14px',
    borderRadius: 10,
    backgroundColor: LIGHT_GOLD + '15',
    borderWidth: 1,
    borderColor: LIGHT_GOLD + '35',
    marginBottom: 10,
  },
  hashtagTitleContainer: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  hashtagTitle: {
    fontSize: 13,
    fontWeight: '800',
    color: LIGHT_GOLD,
  },
  hashtagDropdown: {
    flexDirection: 'row',
    gap: 8,
    flexWrap: 'wrap',
    paddingVertical: 4,
  },
  trendingHashtagChip: {
    flexDirection: 'row',
    gap: 1,
    paddingHorizontal: 14,
    paddingVertical: 7,
    borderRadius: 20,
    backgroundColor: LIGHT_GOLD + '12',
    borderWidth: 1,
    borderColor: LIGHT_GOLD + '35',
  },
  trendingHashtagText: {
    fontSize: 13,
    fontWeight: '800',
    color: LIGHT_GOLD,
  },
  trendingHashtagCount: {
    fontSize: 10,
    color: '#666',
  },
  hashtagLoading: {
    flexDirection: 'row',
    gap: 8,
    overflowX: 'auto',
    marginBottom: 20,
  },
  hashtagSkeleton: {
    width: 80,
    height: 46,
    borderRadius: 20,
    backgroundColor: BORDER,
  },
  
  // Hashtag View
  hashtagViewHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    padding: '12px 16px',
    backgroundColor: LIGHT_GOLD + '15',
    borderRadius: 12,
    marginBottom: 16,
  },
  hashtagBackButton: {
    padding: 4,
  },
  hashtagViewInfo: {
    flex: 1,
  },
  hashtagViewTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: LIGHT_GOLD,
  },
  hashtagViewCount: {
    fontSize: 12,
    color: '#666',
  },
  
  // Grid
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: GAP, // Use the defined gap
  },
  gridItem: {
    width: ITEM_SIZE,
    height: ITEM_SIZE * 1.78, // 9:16 aspect ratio for vertical videos
    backgroundColor: LIGHT_GOLD + '15',
    borderRadius: 10,
    borderWidth: 1.5,
    borderColor: LIGHT_GOLD + '30',
    overflow: 'hidden',
  },
  heroItem: {
    width: width, // Full screen width
    height: width * 0.56, // 16:9 aspect ratio for hero item
    marginBottom: GAP,
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
  fallbackText: {
    color: '#666',
    fontSize: 10,
    marginTop: 4,
  },
  videoIcon: {
    position: 'absolute',
    top: 7,
    left: 7,
    backgroundColor: 'rgba(0,0,0,0.58)',
    borderRadius: 4,
    padding: '2px 5px',
    flexDirection: 'row',
    alignItems: 'center',
  },
  rankBadge: {
    position: 'absolute',
    top: 7,
    right: 7,
    width: 20,
    height: 20,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  heroItem: {
    rankBadge: {
      width: 28,
      height: 28,
      borderRadius: 14,
    },
  },
  rankText: {
    fontSize: 10,
    fontWeight: 900,
  },
  heroItem: {
    rankText: {
      fontSize: 13,
    },
  },
  gridOverlay: {
    position: 'absolute',
    bottom: 0,
    left: 0,
    right: 0,
    background: 'linear-gradient(transparent, rgba(0,0,0,0.72))',
    padding: '12px 6px 6px',
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  heroItem: {
    gridOverlay: {
      padding: '24px 12px 10px',
    },
  },
  heroUsername: {
    flex: 1,
    fontSize: 12,
    fontWeight: 700,
    color: LIGHT_GOLD,
  },
  statsRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 3,
  },
  gridStat: {
    fontSize: 10,
    fontWeight: 600,
    color: 'rgba(255,255,255,0.8)',
  },
  
  // Skeleton
  skeletonItem: {
    aspectRatio: '9/16',
    borderRadius: 8,
    backgroundColor: BORDER,
  },

  // Fallback when no thumbnail
  fallbackContainer: {
    backgroundColor: '#1a1a1a',
    justifyContent: 'center',
    alignItems: 'center',
  },
  fallbackText: {
    fontSize: 10,
    color: '#666',
    marginTop: 4,
  },
  
  // Empty State
  emptyState: {
    alignItems: 'center',
    padding: '60px 20px',
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: LIGHT_GOLD,
    marginBottom: 6,
  },
  emptyText: {
    fontSize: 13,
    color: '#666',
  },
  
  // Load More
  loadMoreContainer: {
    padding: '16px 0',
    alignItems: 'center',
  },
  loadMoreText: {
    fontSize: 13,
    color: '#666',
    marginTop: 4,
  },
  endMessage: {
    alignItems: 'center',
    padding: '18px 0',
  },
  endText: {
    fontSize: 12,
    color: '#666',
  },
});
