import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, ScrollView, TouchableOpacity, Image, ActivityIndicator, Alert, Modal, FlatList } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useTheme } from '../contexts/ThemeContext';
import api from '../api';
import config from '../config';

const GOLD = '#8fc441';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

// Custom component for displaying images at original size without black spaces
const OriginalSizeImage = React.memo(({ imageUrl, style }) => {
  const [imageSize, setImageSize] = React.useState({ width: null, height: null });
  const [loading, setLoading] = React.useState(true);
  const [hasError, setHasError] = React.useState(false);
  
  const handleImageLoad = React.useCallback((e) => {
    const { width: imgWidth, height: imgHeight } = e.nativeEvent.source;
    console.log('OriginalSizeImage loaded with dimensions:', { imgWidth, imgHeight, imageUrl });
    setImageSize({ width: imgWidth, height: imgHeight });
    setLoading(false);
    setHasError(false);
  }, [imageUrl]);
  
  const handleImageError = React.useCallback((e) => {
    console.log('OriginalSizeImage failed to load:', { imageUrl, error: e.nativeEvent });
    setLoading(false);
    setHasError(true);
  }, [imageUrl]);
  
  // Calculate dynamic container size based on image aspect ratio
  const containerStyle = React.useMemo(() => {
    if (imageSize.width && imageSize.height) {
      return {
        width: '100%',
        aspectRatio: imageSize.width / imageSize.height,
        backgroundColor: '#000',
      };
    }
    return {
      width: '100%',
      height: 300, // Default height while loading
      backgroundColor: '#000',
    };
  }, [imageSize]);
  
  return (
    <View style={containerStyle}>
      {hasError ? (
        <View style={{ 
          width: '100%', 
          height: '100%',
          backgroundColor: '#1A1A1A',
          justifyContent: 'center',
          alignItems: 'center'
        }}>
          <Ionicons name='videocam' size={32} color='#666' />
          <Text style={{ color: '#666', fontSize: 12, marginTop: 8 }}>Failed to load</Text>
        </View>
      ) : (
        <Image
          source={{ uri: imageUrl }}
          style={{ 
            width: '100%', 
            height: '100%',
            backgroundColor: '#000',
          }}
          resizeMode="contain"
          onError={handleImageError}
          onLoad={handleImageLoad}
        />
      )}
      {loading && !hasError && (
        <View style={{ 
          position: 'absolute', 
          top: 0, 
          left: 0, 
          right: 0, 
          bottom: 0, 
          justifyContent: 'center', 
          alignItems: 'center',
          backgroundColor: '#000'
        }}>
          <ActivityIndicator size="small" color={GOLD} />
        </View>
      )}
    </View>
  );
});

const BASE = config.API_BASE_URL.replace('/api', '');
const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  // Ensure /media/ prefix is included
  return `${BASE}/media/${url}`;
};

function timeLeft(endDate) {
  if (!endDate) return '';
  const diff = new Date(endDate) - Date.now();
  if (diff <= 0) return 'Ended';
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  return d > 0 ? `${d}d ${h}h` : `${h}h`;
}

function formatDate(dateStr) {
  if (!dateStr) return 'N/A';
  const date = new Date(dateStr);
  if (isNaN(date.getTime())) return 'N/A';
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

const Accordion = ({ title, subtitle, icon, children, isOpen, onToggle, iconColor }) => (
  <View style={styles.accordion}>
    <TouchableOpacity style={styles.accordionHeader} onPress={onToggle}>
      <View style={[styles.accordionIcon, { backgroundColor: (iconColor || GOLD) + '22' }]}>
        <Ionicons name={icon} size={16} color={iconColor || GOLD} />
      </View>
      <View style={{ flex: 1 }}>
        <Text style={styles.accordionTitle}>{title}</Text>
        {subtitle && <Text style={styles.accordionSubtitle}>{subtitle}</Text>}
      </View>
      <Ionicons 
        name={isOpen ? 'chevron-up' : 'chevron-down'} 
        size={18} 
        color="#666" 
      />
    </TouchableOpacity>
    {isOpen && (
      <View style={styles.accordionContent}>
        {children}
      </View>
    )}
  </View>
);

export default function CampaignDetailScreen({ route, navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { campaignId } = route.params;
  const [campaign, setCampaign] = useState(null);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [joining, setJoining] = useState(false);
  const [showReelSelector, setShowReelSelector] = useState(false);
  const [userReels, setUserReels] = useState([]);
  const [loadingReels, setLoadingReels] = useState(false);
  const [selectedReel, setSelectedReel] = useState(null);
  const [userEntry, setUserEntry] = useState(null);
  const [activeTab, setActiveTab] = useState('about'); // about, leaderboard, feed
  const [feedPosts, setFeedPosts] = useState([]);
  const [loadingFeed, setLoadingFeed] = useState(false);
  const [lbEntries, setLbEntries] = useState([]);
  const [loadingLb, setLoadingLb] = useState(false);
  const [openSections, setOpenSections] = useState({
    desc: true,
    reqs: false,
    timeline: false,
    scoring: false,
  });

  useEffect(() => { loadCampaign(); }, [campaignId]);

  useEffect(() => {
    if (activeTab === 'feed' && feedPosts.length === 0) {
      loadFeed();
    }
    if (activeTab === 'leaderboard') {
      loadLeaderboard();
    }
  }, [activeTab]);

  const loadLeaderboard = async () => {
    setLoadingLb(true);
    try {
      const data = await api.request(`/campaigns/${campaignId}/leaderboard/?period=overall`);
      setLbEntries(data.entries || []);
    } catch (e) {
      console.error('Failed to load leaderboard:', e);
    } finally {
      setLoadingLb(false);
    }
  };

  const loadCampaign = async () => {
    try {
      const data = await api.request('/campaigns/' + campaignId + '/');
      console.log('[CAMPAIGN DETAIL] ========================================');
      console.log('[CAMPAIGN DETAIL] Loaded campaign:', data.title);
      console.log('[CAMPAIGN DETAIL] Campaign status:', data.status);
      console.log('[CAMPAIGN DETAIL] Total entries in response:', data.entries?.length || 0);
      console.log('[CAMPAIGN DETAIL] 🔑 Current logged-in user ID:', data.current_user_id);
      console.log('[CAMPAIGN DETAIL] Campaign total_entries field:', data.total_entries);
      
      // Log all entries
      if (data.entries && data.entries.length > 0) {
        console.log('[CAMPAIGN DETAIL] All entries:');
        data.entries.forEach((entry, index) => {
          const isCurrentUser = entry.user?.id === data.current_user_id;
          console.log(`  Entry ${index + 1}${isCurrentUser ? ' ⭐ (YOU)' : ''}:`, {
            id: entry.id,
            user_id: entry.user?.id,
            username: entry.user?.username,
            reel_id: entry.reel?.id,
            vote_count: entry.vote_count,
            rank: entry.rank,
          });
        });
      } else {
        console.log('[CAMPAIGN DETAIL] ⚠️ No entries in response!');
        console.log('[CAMPAIGN DETAIL] But total_entries says:', data.total_entries);
        if (data.total_entries > 0) {
          console.log('[CAMPAIGN DETAIL] ⚠️ MISMATCH: total_entries > 0 but entries array is empty!');
          console.log('[CAMPAIGN DETAIL] This means entries exist but are filtered out (not approved or disqualified)');
        }
      }
      
      setCampaign(data);
      setEntries(data.entries || []);
      
      // Check if user has already entered
      const userHasEntered = data.entries?.some(entry => {
        const match = entry.user?.id === data.current_user_id;
        console.log(`[CAMPAIGN DETAIL] Checking entry user ${entry.user?.id} vs current ${data.current_user_id}: ${match}`);
        return match;
      });
      const userEntryData = userHasEntered ? data.entries.find(entry => entry.user?.id === data.current_user_id) : null;
      
      console.log('[CAMPAIGN DETAIL] User has entered:', userHasEntered);
      if (userEntryData) {
        console.log('[CAMPAIGN DETAIL] ✓ User entry details:', userEntryData);
      } else {
        console.log('[CAMPAIGN DETAIL] ✗ User entry NOT FOUND in entries list');
        console.log('[CAMPAIGN DETAIL] 💡 You are logged in as user ID:', data.current_user_id);
        console.log('[CAMPAIGN DETAIL] 💡 Entries belong to user IDs:', data.entries?.map(e => e.user?.id).join(', ') || 'none');
      }
      console.log('[CAMPAIGN DETAIL] ========================================');
      
      setUserEntry(userEntryData);
    } catch (e) {
      console.error('[CAMPAIGN DETAIL] Error loading campaign:', e);
      Alert.alert('Error', 'Failed to load campaign.');
      navigation.goBack();
    } finally {
      setLoading(false);
    }
  };

  const loadFeed = async () => {
    setLoadingFeed(true);
    try {
      const data = await api.request(`/campaigns/${campaignId}/feed/?filter=all`);
      console.log('[CAMPAIGN FEED] Loaded', data.posts?.length || 0, 'posts');
      if (data.posts && data.posts.length > 0) {
        console.log('[CAMPAIGN FEED] First post sample:', {
          id: data.posts[0].id,
          image: data.posts[0].image,
          media: data.posts[0].media,
          user: data.posts[0].user?.username,
        });
      }
      setFeedPosts(data.posts || []);
    } catch (e) {
      console.error('Failed to load feed:', e);
      Alert.alert('Error', 'Failed to load campaign feed.');
    } finally {
      setLoadingFeed(false);
    }
  };

  const loadUserReels = async () => {
    setLoadingReels(true);
    try {
      // Get current user's reels - backend will filter by authenticated user
      // The ReelViewSet supports ?user=<id> parameter
      const profileData = await api.request('/profile/me/');
      const userId = profileData?.user?.id || profileData?.id;
      
      if (!userId) {
        throw new Error('Could not determine user ID');
      }
      
      const data = await api.request(`/reels/?user=${userId}`);
      const reels = Array.isArray(data) ? data : (data.results || []);
      setUserReels(reels);
    } catch (e) {
      console.error('Failed to load reels:', e);
      Alert.alert('Error', 'Failed to load your reels. Please try again.');
    } finally {
      setLoadingReels(false);
    }
  };

  const handleJoinClick = () => {
    setShowReelSelector(true);
    loadUserReels();
  };

  const handleSubmitEntry = async () => {
    if (!selectedReel) {
      Alert.alert('Error', 'Please select a reel to submit');
      return;
    }

    setJoining(true);
    try {
      const response = await api.request('/campaigns/' + campaignId + '/enter/', { 
        method: 'POST',
        body: JSON.stringify({ reel_id: selectedReel })
      });
      
      console.log('[CAMPAIGN JOIN] Success:', response);
      
      setShowReelSelector(false);
      setSelectedReel(null);
      
      // Wait a moment for backend to process, then reload
      await new Promise(resolve => setTimeout(resolve, 500));
      await loadCampaign();
      
      // Switch to leaderboard tab to show the entry
      setActiveTab('leaderboard');
      
      Alert.alert('Success!', 'You have successfully joined this campaign. Check the leaderboard!');
    } catch (e) {
      console.error('[CAMPAIGN JOIN] Error:', e);
      Alert.alert('Error', (e && e.message) ? e.message : 'Could not join campaign.');
    } finally {
      setJoining(false);
    }
  };

  const handleCreateNew = () => {
    setShowReelSelector(false);
    navigation.navigate('Create', { campaignId });
  };

  const handleVote = async (entryId) => {
    try {
      await api.request(`/campaigns/entries/${entryId}/vote/`, { method: 'POST' });
      loadCampaign();
    } catch (error) {
      Alert.alert('Error', error.message || 'Failed to vote');
    }
  };

  const toggleSection = (key) => {
    setOpenSections(prev => ({ ...prev, [key]: !prev[key] }));
  };

  if (loading) return <View style={[styles.centered, { backgroundColor: colors.bg }]}><ActivityIndicator size='large' color={colors.primary} /></View>;
  if (!campaign) return null;
  
  const isActive = campaign.status === 'active';
  const hasRequirements = (campaign.min_followers > 0 || campaign.min_level > 0 || campaign.min_votes_per_reel > 0 || campaign.required_hashtags || campaign.winner_count > 0);

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name='chevron-back' size={24} color={colors.primary} />
        </TouchableOpacity>
        <Text style={[styles.headerTitle, { color: colors.text }]} numberOfLines={1}>{campaign.title}</Text>
        <TouchableOpacity onPress={loadCampaign} style={{ padding: 4 }}>
          <Ionicons name='refresh' size={20} color={colors.primary} />
        </TouchableOpacity>
        <View style={[styles.statusBadge, 
          isActive && styles.statusActive, 
          campaign.status === 'ended' && styles.statusEnded,
          campaign.status === 'voting' && styles.statusVoting
        ]}>
          <Text style={styles.statusText}>{campaign.status?.toUpperCase()}</Text>
        </View>
      </View>

      <ScrollView contentContainerStyle={styles.content} showsVerticalScrollIndicator={false}>
        {/* Hero Image with Prize Overlay */}
        <View style={styles.heroContainer}>
          {campaign.image ? (
            <OriginalSizeImage imageUrl={mediaUrl(campaign.image)} style={styles.banner} />
          ) : (
            <View style={[styles.banner, styles.bannerPlaceholder]}>
              <Ionicons name='trophy' size={56} color={colors.primary} opacity={0.4} />
            </View>
          )}
          <View style={styles.heroOverlay} />
          
          {/* Prize Overlay */}
          <View style={styles.prizeOverlay}>
            <View style={[styles.prizeIcon, { backgroundColor: colors.primary }]}>
              <Ionicons name='trophy' size={22} color='#000' />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.prizeLabel, { color: colors.textSecondary }]}>PRIZE POOL</Text>
              <Text style={[styles.prizeValue, { color: colors.text }]}>
                {campaign.prize_value ? `${campaign.prize_value} ETB` : (campaign.prize_title || '—')}
              </Text>
            </View>
            <View style={[styles.timeChip, { backgroundColor: colors.cardBg }]}>
              <Ionicons name='time' size={12} color={colors.textSecondary} />
              <Text style={[styles.timeText, { color: colors.text }]}>{timeLeft(campaign.voting_end || campaign.entry_deadline)}</Text>
            </View>
          </View>
        </View>

        {/* Quick Stats */}
        <View style={styles.statsGrid}>
          <View style={[styles.statCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <Ionicons name='people' size={11} color={colors.primary} />
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>ENTRIES</Text>
            <Text style={[styles.statValue, { color: colors.primary }]}>{campaign.total_entries || 0}</Text>
          </View>
                    <View style={[styles.statCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <Ionicons name='trophy' size={11} color={colors.primary} />
            <Text style={[styles.statLabel, { color: colors.textSecondary }]}>WINNERS</Text>
            <Text style={[styles.statValue, { color: colors.primary }]}>{campaign.winner_count || 1}</Text>
          </View>
        </View>

        {/* CTA Button */}
        {isActive && !userEntry && (
          <TouchableOpacity style={[styles.joinBtn, { backgroundColor: colors.primary }]} onPress={handleJoinClick}>
            <Ionicons name='cloud-upload' size={18} color='#000' />
            <Text style={styles.joinBtnText}>Join Campaign</Text>
          </TouchableOpacity>
        )}

        {userEntry && (
          <View style={[styles.userEntryCard, { backgroundColor: colors.cardBg, borderColor: colors.border }]}>
            <View style={[styles.userEntryIcon, { backgroundColor: colors.primary }]}>
              <Ionicons name='checkmark' size={18} color='#fff' />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.userEntryTitle, { color: colors.text }]}>Your Entry is Live 🎉</Text>
            </View>
          </View>
        )}
        
        {/* Debug: Show if total_entries doesn't match entries.length */}
        {campaign.total_entries > 0 && entries.length === 0 && (
          <View style={[styles.userEntryCard, { backgroundColor: 'rgba(239,68,68,0.12)', borderColor: '#EF4444' }]}>
            <View style={[styles.userEntryIcon, { backgroundColor: '#EF4444' }]}>
              <Ionicons name='alert' size={18} color='#fff' />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.userEntryTitle, { color: '#EF4444' }]}>Entry Issue Detected</Text>
              <Text style={styles.userEntryStats}>
                {campaign.total_entries} entries exist but not showing. They may need approval.
              </Text>
            </View>
            <TouchableOpacity onPress={loadCampaign} style={{ padding: 8 }}>
              <Ionicons name='refresh' size={20} color='#EF4444' />
            </TouchableOpacity>
          </View>
        )}
        
        {/* Debug: Show if entries exist but none belong to current user */}
        {entries.length > 0 && !userEntry && campaign.current_user_id && (
          <View style={[styles.userEntryCard, { backgroundColor: 'rgba(59,130,246,0.12)', borderColor: '#3B82F6' }]}>
            <View style={[styles.userEntryIcon, { backgroundColor: '#3B82F6' }]}>
              <Ionicons name='information-circle' size={18} color='#fff' />
            </View>
            <View style={{ flex: 1 }}>
              <Text style={[styles.userEntryTitle, { color: '#3B82F6' }]}>You Haven't Joined Yet</Text>
              <Text style={styles.userEntryStats}>
                {entries.length} other {entries.length === 1 ? 'entry' : 'entries'} in this campaign. Join to compete!
              </Text>
            </View>
          </View>
        )}

        {/* Tabs */}
        <View style={styles.tabs}>
          <TouchableOpacity 
            style={[styles.tab, activeTab === 'about' && styles.tabActive]}
            onPress={() => setActiveTab('about')}
          >
            <Ionicons name='information-circle' size={16} color={activeTab === 'about' ? GOLD : '#666'} />
            <Text style={[styles.tabText, activeTab === 'about' && styles.tabTextActive]}>About</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.tab, activeTab === 'leaderboard' && styles.tabActive]}
            onPress={() => setActiveTab('leaderboard')}
          >
            <Ionicons name='bar-chart' size={16} color={activeTab === 'leaderboard' ? GOLD : '#666'} />
            <Text style={[styles.tabText, activeTab === 'leaderboard' && styles.tabTextActive]}>Leaderboard</Text>
          </TouchableOpacity>
          <TouchableOpacity 
            style={[styles.tab, activeTab === 'feed' && styles.tabActive]}
            onPress={() => setActiveTab('feed')}
          >
            <Ionicons name='list' size={16} color={activeTab === 'feed' ? GOLD : '#666'} />
            <Text style={[styles.tabText, activeTab === 'feed' && styles.tabTextActive]}>Feed</Text>
          </TouchableOpacity>
        </View>

        {/* Tab Content */}
        {activeTab === 'about' && (
          <View>
            {/* About Accordion */}
            <Accordion
              title="About this Campaign"
              subtitle="Description & rules"
              icon="document-text"
              isOpen={openSections.desc}
              onToggle={() => toggleSection('desc')}
            >
              <Text style={styles.descText}>{campaign.description || 'No description provided.'}</Text>
              <View style={styles.typeChip}>
                <Ionicons name='trophy-outline' size={14} color={GOLD} />
                <Text style={styles.typeText}>
                  Type: <Text style={{ fontWeight: '700' }}>
                    {campaign.campaign_type === 'grand' ? 'Grand Campaign' : 
                     campaign.campaign_type === 'daily' ? 'Daily' : 
                     campaign.campaign_type === 'weekly' ? 'Weekly' : 'Monthly'}
                  </Text>
                </Text>
              </View>
            </Accordion>

            {/* Requirements Accordion */}
            {hasRequirements && (
              <Accordion
                title="Entry Requirements"
                subtitle="What you need to qualify"
                icon="checkmark-circle"
                iconColor="#3B82F6"
                isOpen={openSections.reqs}
                onToggle={() => toggleSection('reqs')}
              >
                {campaign.required_hashtags && (
                  <View style={styles.reqRow}>
                    <Text style={styles.reqLabel}>Required tags</Text>
                    <Text style={[styles.reqValue, { color: GOLD }]}>{campaign.required_hashtags}</Text>
                  </View>
                )}
                {campaign.min_followers > 0 && (
                  <View style={styles.reqRow}>
                    <Text style={styles.reqLabel}>Min followers</Text>
                    <Text style={[styles.reqValue, { color: '#3B82F6' }]}>{campaign.min_followers}+</Text>
                  </View>
                )}
                {campaign.min_level > 0 && (
                  <View style={styles.reqRow}>
                    <Text style={styles.reqLabel}>Min level</Text>
                    <Text style={[styles.reqValue, { color: '#F97316' }]}>Level {campaign.min_level}</Text>
                  </View>
                )}
                              </Accordion>
            )}

            {/* Timeline Accordion */}
            <Accordion
              title="Timeline"
              subtitle="Key dates"
              icon="calendar"
              iconColor="#8B5CF6"
              isOpen={openSections.timeline}
              onToggle={() => toggleSection('timeline')}
            >
              <View style={styles.timelineItem}>
                <View style={[styles.timelineDot, { backgroundColor: '#10B981' }]} />
                <Text style={styles.timelineLabel}>Starts</Text>
                <Text style={styles.timelineDate}>{formatDate(campaign.start_date)}</Text>
              </View>
              <View style={styles.timelineItem}>
                <View style={[styles.timelineDot, { backgroundColor: '#F59E0B' }]} />
                <Text style={styles.timelineLabel}>Entry Deadline</Text>
                <Text style={styles.timelineDate}>{formatDate(campaign.entry_deadline)}</Text>
              </View>
              <View style={styles.timelineItem}>
                <View style={[styles.timelineDot, { backgroundColor: '#3B82F6' }]} />
                <Text style={styles.timelineLabel}>Voting Begins</Text>
                <Text style={styles.timelineDate}>{formatDate(campaign.voting_start)}</Text>
              </View>
              <View style={styles.timelineItem}>
                <View style={[styles.timelineDot, { backgroundColor: '#EF4444' }]} />
                <Text style={styles.timelineLabel}>Voting Ends</Text>
                <Text style={styles.timelineDate}>{formatDate(campaign.voting_end)}</Text>
              </View>
            </Accordion>

            {/* Scoring Accordion */}
            <Accordion
              title="How Scoring Works"
              subtitle="Engagement + votes"
              icon="trending-up"
              iconColor="#EC4899"
              isOpen={openSections.scoring}
              onToggle={() => toggleSection('scoring')}
            >
              <Text style={styles.scoringText}>
                Your total score is calculated from <Text style={{ fontWeight: '700', color: '#fff' }}>likes, comments, shares, and gifts</Text> on your entry during the campaign period.
              </Text>
              <View style={styles.scoringGrid}>
                <View style={styles.scoringItem}>
                  <Ionicons name='heart' size={14} color='#EF4444' />
                  <Text style={styles.scoringLabel}>Likes</Text>
                </View>
                <View style={styles.scoringItem}>
                  <Ionicons name='chatbubble' size={14} color='#3B82F6' />
                  <Text style={styles.scoringLabel}>Comments</Text>
                </View>
                <View style={styles.scoringItem}>
                  <Ionicons name='share-social' size={14} color='#8B5CF6' />
                  <Text style={styles.scoringLabel}>Shares</Text>
                </View>
                                <View style={styles.scoringItem}>
                  <Ionicons name='gift' size={14} color='#F59E0B' />
                  <Text style={styles.scoringLabel}>Gifts</Text>
                </View>
              </View>
            </Accordion>
          </View>
        )}

        {activeTab === 'leaderboard' && (() => {
          const MEDAL = { 1: '#FFD700', 2: '#A8A8A8', 3: '#CD7F32' };
          const allEntries = lbEntries.length > 0 ? lbEntries : entries;
          const top3 = allEntries.slice(0, 3);
          const rest  = allEntries.slice(3);

          const PodiumItem = ({ e, rank }) => {
            const isFirst = rank === 1;
            const color   = MEDAL[rank];
            const size    = isFirst ? 68 : 52;
            const score   = e.total_score ?? e.score ?? 0;
            return (
              <View style={[styles.lbPodiumCard, isFirst && { marginBottom: 16 }]}>
                {isFirst
                  ? <Ionicons name="trophy" size={20} color="#FFD700" style={{ marginBottom: 4 }} />
                  : <Ionicons name="medal"  size={16} color={color}   style={{ marginBottom: 4 }} />}
                <View style={[styles.lbPodiumAvatar, { width: size, height: size, borderRadius: size/2, borderColor: color }]}>
                  <Text style={[styles.lbPodiumLetter, { fontSize: isFirst ? 26 : 20 }]}>
                    {e.username?.[0]?.toUpperCase() || '?'}
                  </Text>
                </View>
                <Text style={styles.lbPodiumName} numberOfLines={1}>{e.username || '—'}</Text>
                <Text style={[styles.lbPodiumScore, { color, fontSize: isFirst ? 22 : 16 }]}>{score}</Text>
                <Text style={styles.lbPodiumPts}>score{isFirst ? ' · Champion' : ''}</Text>
              </View>
            );
          };

          const RankRow = ({ e, idx }) => {
            const rank  = e.rank || idx + 1;
            const color = MEDAL[rank];
            const score = e.total_score ?? e.score ?? 0;
            return (
              <View style={[styles.lbRow, rank === 1 && styles.lbRowFirst]}>
                <View style={styles.lbRankBox}>
                  {rank === 1 ? <Ionicons name="trophy" size={18} color="#FFD700" /> :
                   rank === 2 ? <Ionicons name="medal"  size={18} color="#A8A8A8" /> :
                   rank === 3 ? <Ionicons name="medal"  size={18} color="#CD7F32" /> :
                   <Text style={styles.lbRankNum}>#{rank}</Text>}
                </View>
                <View style={[styles.lbRowAvatar, color && { borderColor: color }]}>
                  <Text style={styles.lbRowLetter}>{e.username?.[0]?.toUpperCase() || '?'}</Text>
                </View>
                <View style={{ flex: 1, minWidth: 0 }}>
                  <Text style={styles.lbRowName} numberOfLines={1}>{e.username || 'Anonymous'}</Text>
                  {e.post_count > 0 && <Text style={styles.lbRowSub}>{e.post_count} posts</Text>}
                </View>
                <View style={{ alignItems: 'flex-end' }}>
                  <Text style={[styles.lbRowScore, rank <= 3 && { color: color || GOLD }]}>{score}</Text>
                  <Text style={styles.lbRowPts}>score</Text>
                </View>
              </View>
            );
          };

          return (
            <View style={{ marginTop: 16 }}>
              {loadingLb ? (
                <View style={{ padding: 40, alignItems: 'center' }}>
                  <ActivityIndicator size="large" color={GOLD} />
                  <Text style={styles.loadingText}>Loading rankings...</Text>
                </View>
              ) : allEntries.length === 0 ? (
                <View style={styles.emptyLeaderboard}>
                  <Ionicons name='trophy-outline' size={44} color='#444' />
                  <Text style={styles.emptyTitle}>No Rankings Yet</Text>
                  <Text style={styles.emptySubtitle}>Be the first to participate!</Text>
                </View>
              ) : (
                <>
                  {/* Podium */}
                  {top3.length > 0 && (
                    <View style={styles.lbPodiumWrap}>
                      <Text style={styles.lbSectionLabel}>TOP PERFORMERS</Text>
                      <View style={styles.lbPodiumRow}>
                        {top3[1] ? <PodiumItem e={top3[1]} rank={2} /> : <View style={{ flex: 1 }} />}
                        {top3[0] ? <PodiumItem e={top3[0]} rank={1} /> : null}
                        {top3[2] ? <PodiumItem e={top3[2]} rank={3} /> : <View style={{ flex: 1 }} />}
                      </View>
                    </View>
                  )}
                  {/* Full ranked list */}
                  <View style={styles.lbListWrap}>
                    {allEntries.map((e, i) => <RankRow key={e.id || i} e={e} idx={i} />)}
                  </View>
                </>
              )}
            </View>
          );
        })()}

        {activeTab === 'feed' && (
          <View style={{ marginTop: 16 }}>
            {loadingFeed ? (
              <View style={{ padding: 40, alignItems: 'center' }}>
                <ActivityIndicator size="large" color={GOLD} />
                <Text style={styles.loadingText}>Loading feed...</Text>
              </View>
            ) : feedPosts.length === 0 ? (
              <View style={styles.emptyLeaderboard}>
                <Ionicons name='videocam' size={36} color='#666' opacity={0.4} />
                <Text style={styles.emptyTitle}>No posts yet</Text>
                <Text style={styles.emptySubtitle}>Campaign posts will appear here</Text>
              </View>
            ) : (
              <View style={styles.feedGrid}>
                {feedPosts.map(post => {
                  const postImageUrl = post.reel?.thumbnail || post.reel?.image || post.reel?.media || post.image || post.media;
                  const fullPostUrl = mediaUrl(postImageUrl);
                  
                  console.log('[FEED CARD] Post:', post.id, 'Raw:', postImageUrl, 'Full:', fullPostUrl);
                  console.log('[FEED CARD] Post data:', JSON.stringify(post, null, 2));
                  
                  return (
                    <TouchableOpacity
                      key={post.id}
                      style={styles.feedCard}
                      onPress={() => {
                        if (post.reel?.id) {
                          navigation.navigate('Reels', { 
                            screen: 'ReelsDetail',
                            params: { id: post.reel.id }
                          });
                        }
                      }}
                    >
                      {fullPostUrl ? (
                        <>
                          <Image 
                            source={{ uri: fullPostUrl }} 
                            style={styles.feedImage}
                            resizeMode="cover"
                            onError={(e) => console.log('[FEED CARD] Image load error:', post.id, e.nativeEvent.error)}
                            onLoad={(e) => console.log('[FEED CARD] Image loaded:', post.id, e.nativeEvent.source)}
                          />
                          {/* Play icon for videos */}
                          {post.reel?.media && (
                            <View style={styles.feedPlayIcon}>
                              <Ionicons name='play-circle' size={32} color='rgba(255,255,255,0.9)' />
                            </View>
                          )}
                        </>
                      ) : (
                        <View style={[styles.feedImage, styles.feedImagePlaceholder]}>
                          <Ionicons name='videocam' size={32} color='#666' />
                        </View>
                      )}
                    <View style={styles.feedOverlay}>
                      <View style={styles.feedStats}>
                        <View style={styles.feedStat}>
                          <Ionicons name='heart' size={14} color='#fff' />
                          <Text style={styles.feedStatText}>{post.engagement?.likes || post.reel?.votes || 0}</Text>
                        </View>
                        <View style={styles.feedStat}>
                          <Ionicons name='chatbubble' size={14} color='#fff' />
                          <Text style={styles.feedStatText}>{post.engagement?.comments || post.reel?.comment_count || 0}</Text>
                        </View>
                      </View>
                    </View>
                    {post.user && (
                      <View style={styles.feedUser}>
                        <Text style={styles.feedUsername}>@{post.user.username}</Text>
                      </View>
                    )}
                  </TouchableOpacity>
                  );
                })}
              </View>
            )}
          </View>
        )}
      </ScrollView>

      {/* Reel Selector Modal */}
      <Modal
        visible={showReelSelector}
        animationType="slide"
        transparent
        onRequestClose={() => setShowReelSelector(false)}
      >
        <View style={styles.modalOverlay}>
          <View style={[styles.modalContent, { paddingBottom: insets.bottom + 20 }]}>
            {/* Modal Handle */}
            <View style={styles.modalHandle} />
            
            <View style={styles.modalHeader}>
              <View>
                <Text style={styles.modalTitle}>Submit Your Entry</Text>
                <Text style={styles.modalSubtitle}>Choose a reel or create new</Text>
              </View>
              <TouchableOpacity onPress={() => setShowReelSelector(false)} style={styles.closeBtn}>
                <Ionicons name="close" size={24} color="#fff" />
              </TouchableOpacity>
            </View>

            {loadingReels ? (
              <View style={{ padding: 40, alignItems: 'center' }}>
                <ActivityIndicator size="large" color={GOLD} />
                <Text style={styles.loadingText}>Loading your reels...</Text>
              </View>
            ) : (
              <ScrollView showsVerticalScrollIndicator={false}>
                {/* Create New Option */}
                <TouchableOpacity style={styles.createNewCard} onPress={handleCreateNew}>
                  <View style={styles.createNewIconContainer}>
                    <View style={styles.createNewIconBg}>
                      <Ionicons name="add" size={32} color="#000" />
                    </View>
                    <View style={styles.createNewSparkle1}>
                      <Ionicons name="sparkles" size={16} color={GOLD} />
                    </View>
                    <View style={styles.createNewSparkle2}>
                      <Ionicons name="sparkles" size={12} color={GOLD} />
                    </View>
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.createNewTitle}>Create New Reel</Text>
                    <Text style={styles.createNewDesc}>Record or upload a video for this campaign</Text>
                  </View>
                  <Ionicons name="chevron-forward" size={20} color={GOLD} />
                </TouchableOpacity>

                {/* Divider */}
                <View style={styles.divider}>
                  <View style={styles.dividerLine} />
                  <Text style={styles.dividerText}>OR SELECT EXISTING</Text>
                  <View style={styles.dividerLine} />
                </View>

                {/* Existing Reels */}
                {userReels.length === 0 ? (
                  <View style={styles.emptyState}>
                    <View style={styles.emptyIconContainer}>
                      <Ionicons name="videocam-off" size={48} color="#666" opacity={0.5} />
                    </View>
                    <Text style={styles.emptyTitle}>No Reels Yet</Text>
                    <Text style={styles.emptyDesc}>Create your first reel to join this campaign</Text>
                  </View>
                ) : (
                  <View style={styles.reelsList}>
                    {userReels.map((item) => (
                      <TouchableOpacity
                        key={item.id}
                        style={[
                          styles.reelCard,
                          selectedReel === item.id && styles.reelCardSelected
                        ]}
                        onPress={() => setSelectedReel(item.id)}
                        activeOpacity={0.7}
                      >
                        {/* Thumbnail */}
                        <View style={styles.reelThumbContainer}>
                          {item.image || item.thumbnail || item.media ? (
                            <OriginalSizeImage 
                              imageUrl={mediaUrl(item.image || item.thumbnail || item.media)} 
                              style={styles.reelThumb} 
                            />
                          ) : (
                            <View style={[styles.reelThumb, styles.reelThumbPlaceholder]}>
                              <Ionicons name="videocam" size={24} color="#666" />
                            </View>
                          )}
                          {selectedReel === item.id && (
                            <View style={styles.selectedOverlay}>
                              <View style={styles.selectedCheckmark}>
                                <Ionicons name="checkmark" size={20} color="#000" />
                              </View>
                            </View>
                          )}
                          <View style={styles.reelDuration}>
                            <Ionicons name="play" size={10} color="#fff" />
                          </View>
                        </View>

                        {/* Info */}
                        <View style={styles.reelInfo}>
                          <Text style={styles.reelCaption} numberOfLines={2}>
                            {item.caption || 'No caption'}
                          </Text>
                          <View style={styles.reelStatsRow}>
                            <View style={styles.reelStat}>
                              <Ionicons name="heart" size={12} color="#EF4444" />
                              <Text style={styles.reelStatText}>{item.votes || 0}</Text>
                            </View>
                            <View style={styles.reelStat}>
                              <Ionicons name="eye" size={12} color="#3B82F6" />
                              <Text style={styles.reelStatText}>{item.view_count || 0}</Text>
                            </View>
                            <View style={styles.reelStat}>
                              <Ionicons name="chatbubble" size={12} color="#8B5CF6" />
                              <Text style={styles.reelStatText}>{item.comment_count || 0}</Text>
                            </View>
                          </View>
                        </View>

                        {/* Selection Indicator */}
                        {selectedReel === item.id && (
                          <View style={styles.selectedBadge}>
                            <Ionicons name="checkmark-circle" size={24} color={GOLD} />
                          </View>
                        )}
                      </TouchableOpacity>
                    ))}
                  </View>
                )}

                {/* Submit Button */}
                {selectedReel && (
                  <TouchableOpacity
                    style={[styles.submitBtn, joining && { opacity: 0.6 }]}
                    onPress={handleSubmitEntry}
                    disabled={joining}
                  >
                    {joining ? (
                      <ActivityIndicator size="small" color="#000" />
                    ) : (
                      <>
                        <Ionicons name="rocket" size={20} color="#000" />
                        <Text style={styles.submitBtnText}>Submit Entry</Text>
                      </>
                    )}
                  </TouchableOpacity>
                )}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </View>
  );
}

const EntryCard = ({ entry, canVote, onVote }) => {
  const getRankBadge = () => {
    if (!entry.rank || entry.rank > 3) return null;
    const badges = {
      1: { color: '#FFD700', emoji: '🥇', label: '1st' },
      2: { color: '#C0C0C0', emoji: '🥈', label: '2nd' },
      3: { color: '#CD7F32', emoji: '🥉', label: '3rd' },
    };
    return badges[entry.rank];
  };

  const rankBadge = getRankBadge();
  
  // Get media URL - prefer entry.reel.media, fallback to entry.reel.image
  const entryMediaUrl = entry.reel?.media || entry.reel?.image;
  const fullMediaUrl = mediaUrl(entryMediaUrl);
  const isVideo = entryMediaUrl && (entryMediaUrl.endsWith('.mp4') || entryMediaUrl.endsWith('.mov') || entryMediaUrl.includes('/video/'));

  // Debug logging
  console.log('[ENTRY CARD] Entry:', entry.id, 'User:', entry.user?.username);
  console.log('[ENTRY CARD] Raw media:', entry.reel?.media);
  console.log('[ENTRY CARD] Raw image:', entry.reel?.image);
  console.log('[ENTRY CARD] Selected URL:', entryMediaUrl);
  console.log('[ENTRY CARD] Full URL:', fullMediaUrl);

  return (
    <View style={[styles.entryCard, rankBadge && { borderColor: rankBadge.color, borderWidth: 2 }]}>
      {rankBadge && (
        <View style={[styles.rankBadge, { backgroundColor: rankBadge.color }]}>
          <Text style={styles.rankEmoji}>{rankBadge.emoji}</Text>
          <Text style={styles.rankLabel}>{rankBadge.label}</Text>
        </View>
      )}
      
      {fullMediaUrl ? (
        <OriginalSizeImage imageUrl={fullMediaUrl} style={styles.entryImage} />
      ) : (
        <View style={[styles.entryImage, { backgroundColor: '#1A1A1A', justifyContent: 'center', alignItems: 'center' }]}>
          <Ionicons name='videocam' size={48} color='#666' />
          <Text style={{ color: '#666', fontSize: 12, marginTop: 8 }}>No media</Text>
        </View>
      )}
      
      <View style={styles.entryInfo}>
        <View style={styles.entryUser}>
          <View style={styles.entryAvatar}>
            <Text style={styles.entryAvatarText}>{entry.user?.username?.[0]?.toUpperCase()}</Text>
          </View>
          <View style={{ flex: 1 }}>
            <Text style={styles.entryUsername}>@{entry.user?.username}</Text>
            <Text style={styles.entryRank}>Rank #{entry.rank || '—'}</Text>
          </View>
        </View>
        
        {/* Engagement stats — only show non-zero values */}
        {(() => {
          const stats = [
            { icon: 'heart', color: '#EF4444', val: entry.likes_count ?? entry.reel?.votes },
            { icon: 'chatbubble', color: '#888', val: entry.comments_count },
            { icon: 'share-social', color: '#3B82F6', val: entry.shares_count },
            { icon: 'gift', color: GOLD, val: entry.gifts_count },
            { icon: 'thumbs-up', color: '#8B5CF6', val: entry.vote_count },
          ].filter(s => s.val > 0);
          return stats.length > 0 ? (
            <View style={styles.entryStats}>
              {stats.map((s, i) => (
                <View key={i} style={styles.entryStat}>
                  <Ionicons name={s.icon} size={13} color={s.color} />
                  <Text style={styles.entryStatText}>{s.val}</Text>
                </View>
              ))}
            </View>
          ) : null;
        })()}

        {/* Points + rank row at bottom */}
        <View style={styles.pointsRow}>
          {(entry.total_score > 0 || entry.score > 0) ? (
            <View style={styles.pointsBadge}>
              <Ionicons name='trophy' size={15} color='#000' />
              <Text style={styles.pointsNum}>{entry.total_score ?? entry.score}</Text>
              <Text style={styles.pointsLabel}>score</Text>
            </View>
          ) : (
            <View style={[styles.pointsBadge, { backgroundColor: '#2a2a2a' }]}>
              <Ionicons name='trophy' size={15} color={GOLD} />
              <Text style={[styles.pointsNum, { color: GOLD }]}>Rank #{entry.rank || '—'}</Text>
            </View>
          )}
          {canVote && !entry.user_voted && (
            <TouchableOpacity style={styles.voteBtn} onPress={onVote}>
              <Ionicons name='thumbs-up' size={15} color='#fff' />
              <Text style={styles.voteBtnText}>Vote</Text>
            </TouchableOpacity>
          )}
          {entry.user_voted && (
            <View style={styles.votedBadge}>
              <Ionicons name='checkmark-circle' size={15} color='#10B981' />
              <Text style={styles.votedText}>Voted</Text>
            </View>
          )}
        </View>
      </View>
    </View>
  );
};


const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  centered: { flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: BG },
  header: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 12, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 15, fontWeight: '800', color: '#fff', flex: 1, marginHorizontal: 12 },
  statusBadge: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 10, backgroundColor: '#333' },
  statusActive: { backgroundColor: '#14532D' },
  statusEnded: { backgroundColor: '#3B0000' },
  statusVoting: { backgroundColor: '#1E3A8A' },
  statusText: { color: '#fff', fontSize: 10, fontWeight: '800', letterSpacing: 0.5 },
  content: { paddingBottom: 20 },
  
  // Hero
  heroContainer: { position: 'relative', marginBottom: 14 },
  banner: { width: '100%', height: 220 },
  bannerPlaceholder: { backgroundColor: '#1A1200', justifyContent: 'center', alignItems: 'center' },
  heroOverlay: { position: 'absolute', inset: 0, backgroundColor: 'rgba(0,0,0,0.4)' },
  prizeOverlay: { position: 'absolute', bottom: 0, left: 0, right: 0, flexDirection: 'row', alignItems: 'center', padding: 14, gap: 12 },
  prizeIcon: { width: 42, height: 42, borderRadius: 21, backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center', shadowColor: GOLD, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.7, shadowRadius: 8, elevation: 8 },
  prizeLabel: { fontSize: 10, color: 'rgba(255,255,255,0.8)', fontWeight: '700', letterSpacing: 1 },
  prizeValue: { fontSize: 22, fontWeight: '900', color: GOLD, lineHeight: 24 },
  timeChip: { flexDirection: 'row', alignItems: 'center', gap: 5, paddingHorizontal: 10, paddingVertical: 6, borderRadius: 10, backgroundColor: 'rgba(0,0,0,0.5)' },
  timeText: { color: '#fff', fontSize: 11, fontWeight: '800' },
  
  // Stats Grid
  statsGrid: { flexDirection: 'row', gap: 8, paddingHorizontal: 12, marginBottom: 14 },
  statCard: { flex: 1, padding: 10, backgroundColor: CARD, borderRadius: 10, borderWidth: 1, borderColor: BORDER, alignItems: 'center' },
  statLabel: { fontSize: 9, color: '#666', fontWeight: '700', textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 4 },
  statValue: { fontSize: 16, fontWeight: '900', marginTop: 2 },
  
  // CTA
  joinBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginHorizontal: 12, marginBottom: 14, padding: 14, backgroundColor: GOLD, borderRadius: 12, shadowColor: GOLD, shadowOffset: { width: 0, height: 6 }, shadowOpacity: 0.5, shadowRadius: 8, elevation: 8 },
  joinBtnText: { color: '#000', fontWeight: '800', fontSize: 15 },
  
  // User Entry Card
  userEntryCard: { flexDirection: 'row', alignItems: 'center', gap: 12, marginHorizontal: 12, marginBottom: 14, padding: 14, backgroundColor: 'rgba(16,185,129,0.12)', borderWidth: 1.5, borderColor: '#10B981', borderRadius: 12 },
  userEntryIcon: { width: 38, height: 38, borderRadius: 19, backgroundColor: '#10B981', justifyContent: 'center', alignItems: 'center' },
  userEntryTitle: { fontSize: 14, fontWeight: '800', color: '#fff' },
  userEntryStats: { fontSize: 11, color: '#666', marginTop: 2 },
  
  // Tabs
  tabs: { flexDirection: 'row', marginHorizontal: 12, marginBottom: 16, backgroundColor: CARD, borderRadius: 12, padding: 4 },
  tab: { flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingVertical: 10, borderRadius: 8 },
  tabActive: { backgroundColor: BG },
  tabText: { fontSize: 13, fontWeight: '600', color: '#666' },
  tabTextActive: { color: GOLD, fontWeight: '700' },
  
  // Accordion
  accordion: { marginHorizontal: 12, marginBottom: 10, backgroundColor: CARD, borderRadius: 12, borderWidth: 1, borderColor: BORDER, overflow: 'hidden' },
  accordionHeader: { flexDirection: 'row', alignItems: 'center', gap: 12, padding: 14 },
  accordionIcon: { width: 32, height: 32, borderRadius: 10, justifyContent: 'center', alignItems: 'center' },
  accordionTitle: { fontSize: 14, fontWeight: '700', color: '#fff' },
  accordionSubtitle: { fontSize: 11, color: '#666', marginTop: 2 },
  accordionContent: { paddingHorizontal: 14, paddingBottom: 14, borderTopWidth: 1, borderTopColor: BORDER, paddingTop: 12 },
  
  // Description
  descText: { fontSize: 13, color: '#aaa', lineHeight: 20 },
  typeChip: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 12, padding: 10, backgroundColor: GOLD + '15', borderRadius: 8 },
  typeText: { fontSize: 11, color: '#fff' },
  
  // Requirements
  reqRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 10, backgroundColor: BG, borderRadius: 8, marginBottom: 8 },
  reqLabel: { fontSize: 11, color: '#666', fontWeight: '600' },
  reqValue: { fontSize: 13, fontWeight: '800' },
  
  // Timeline
  timelineItem: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 10 },
  timelineDot: { width: 8, height: 8, borderRadius: 4 },
  timelineLabel: { fontSize: 12, color: '#666', fontWeight: '600', minWidth: 110 },
  timelineDate: { fontSize: 13, fontWeight: '700', color: '#fff' },
  
  // Scoring
  scoringText: { fontSize: 13, color: '#aaa', lineHeight: 20, marginBottom: 10 },
  scoringGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  scoringItem: { flexDirection: 'row', alignItems: 'center', gap: 8, padding: 10, backgroundColor: BG, borderRadius: 8, width: '48%' },
  scoringLabel: { fontSize: 12, color: '#fff', fontWeight: '600' },
  
  // Leaderboard
  /* Inline leaderboard (campaign detail) */
  lbSectionLabel: { fontSize: 11, fontWeight: '700', color: '#666', letterSpacing: 1, marginBottom: 14 },
  lbPodiumWrap: { backgroundColor: '#1A1A1A', borderRadius: 16, borderWidth: 1, borderColor: '#262626', padding: 20, marginBottom: 12 },
  lbPodiumRow: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'center', gap: 8 },
  lbPodiumCard: { flex: 1, alignItems: 'center', paddingBottom: 4 },
  lbPodiumAvatar: { borderWidth: 3, backgroundColor: '#222', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  lbPodiumLetter: { fontWeight: '800', color: '#fff' },
  lbPodiumName: { fontSize: 12, fontWeight: '700', color: '#ddd', marginBottom: 2, textAlign: 'center' },
  lbPodiumScore: { fontWeight: '900', textAlign: 'center' },
  lbPodiumPts: { fontSize: 10, color: '#888', textAlign: 'center' },
  lbListWrap: { backgroundColor: '#1A1A1A', borderRadius: 14, borderWidth: 1, borderColor: '#262626', overflow: 'hidden', marginBottom: 12 },
  lbRow: { flexDirection: 'row', alignItems: 'center', padding: 14, gap: 10, borderBottomWidth: 1, borderBottomColor: '#262626' },
  lbRowFirst: { backgroundColor: '#1C1800' },
  lbRankBox: { width: 28, alignItems: 'center' },
  lbRankNum: { fontSize: 14, fontWeight: '800', color: '#666' },
  lbRowAvatar: { width: 40, height: 40, borderRadius: 20, backgroundColor: '#2a2a2a', borderWidth: 2, borderColor: '#262626', alignItems: 'center', justifyContent: 'center' },
  lbRowLetter: { fontSize: 15, fontWeight: '700', color: '#F9E08B' },
  lbRowName: { fontSize: 14, fontWeight: '700', color: '#F9E08B' },
  lbRowSub: { fontSize: 11, color: '#666', marginTop: 1 },
  lbRowScore: { fontSize: 18, fontWeight: '800', color: '#C8B56A' },
  lbRowPts: { fontSize: 10, color: '#888' },

  leaderboardHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginHorizontal: 12, marginBottom: 12 },
  leaderboardTitle: { flex: 1, fontSize: 16, fontWeight: '800', color: '#fff' },
  leaderboardCount: { fontSize: 11, color: '#666', fontWeight: '600' },
  emptyLeaderboard: { padding: 36, alignItems: 'center', marginHorizontal: 12, backgroundColor: CARD, borderRadius: 12, borderWidth: 1, borderColor: BORDER, borderStyle: 'dashed' },
  emptyTitle: { fontSize: 14, fontWeight: '700', color: '#fff', marginTop: 10, marginBottom: 4 },
  emptySubtitle: { fontSize: 12, color: '#666' },
  
  // Entry Card
  entryCard: { marginHorizontal: 12, marginBottom: 14, backgroundColor: CARD, borderRadius: 16, borderWidth: 1, borderColor: BORDER, overflow: 'hidden' },
  rankBadge: { position: 'absolute', top: 12, right: 12, flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 12, paddingVertical: 6, borderRadius: 20, zIndex: 10, shadowColor: '#000', shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.3, shadowRadius: 8, elevation: 8 },
  rankEmoji: { fontSize: 16 },
  rankLabel: { fontSize: 12, fontWeight: '700', color: '#fff' },
  entryImage: { width: '100%', height: 200, backgroundColor: '#000' },
  entryInfo: { padding: 16 },
  entryUser: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 12 },
  entryAvatar: { width: 42, height: 42, borderRadius: 21, backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center' },
  entryAvatarText: { fontSize: 18, fontWeight: '800', color: '#000' },
  entryUsername: { fontSize: 14, fontWeight: '700', color: '#fff' },
  entryRank: { fontSize: 11, color: '#666', marginTop: 2 },
  entryStats: { flexDirection: 'row', flexWrap: 'wrap', gap: 12, marginBottom: 12 },
  entryStat: { flexDirection: 'row', alignItems: 'center', gap: 5 },
  entryStatText: { fontSize: 12, fontWeight: '700', color: '#aaa' },
  pointsRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginTop: 4 },
  pointsBadge: { flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: GOLD, paddingHorizontal: 14, paddingVertical: 8, borderRadius: 20, flex: 1 },
  pointsNum: { fontSize: 18, fontWeight: '900', color: '#000' },
  pointsLabel: { fontSize: 12, fontWeight: '700', color: '#000', opacity: 0.7 },
  voteBtn: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, backgroundColor: '#3B82F6', borderRadius: 10 },
  voteBtnText: { fontSize: 13, fontWeight: '700', color: '#fff' },
  votedBadge: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 6, paddingHorizontal: 16, paddingVertical: 10, backgroundColor: 'rgba(16,185,129,0.15)', borderWidth: 1.5, borderColor: '#10B981', borderRadius: 10 },
  votedText: { fontSize: 13, fontWeight: '700', color: '#10B981' },
  
  // Modal
  modalOverlay: { flex: 1, backgroundColor: 'rgba(0,0,0,0.9)', justifyContent: 'flex-end' },
  modalContent: { backgroundColor: CARD, borderTopLeftRadius: 28, borderTopRightRadius: 28, paddingHorizontal: 20, paddingTop: 8, maxHeight: '90%' },
  modalHandle: { width: 40, height: 4, backgroundColor: '#444', borderRadius: 2, alignSelf: 'center', marginBottom: 16 },
  modalHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 24 },
  modalTitle: { fontSize: 24, fontWeight: '800', color: '#fff', marginBottom: 4 },
  modalSubtitle: { fontSize: 13, color: '#666', fontWeight: '500' },
  closeBtn: { padding: 4, marginTop: -4 },
  loadingText: { fontSize: 14, color: '#666', marginTop: 12 },
  
  // Create New Card
  createNewCard: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    gap: 16, 
    padding: 20, 
    backgroundColor: `linear-gradient(135deg, ${GOLD}22, #F59E0B22)`,
    borderRadius: 16, 
    borderWidth: 2, 
    borderColor: GOLD,
    borderStyle: 'dashed',
    marginBottom: 20,
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  createNewIconContainer: { position: 'relative', width: 56, height: 56 },
  createNewIconBg: { 
    width: 56, 
    height: 56, 
    borderRadius: 28, 
    backgroundColor: GOLD, 
    justifyContent: 'center', 
    alignItems: 'center',
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.5,
    shadowRadius: 8,
    elevation: 8,
  },
  createNewSparkle1: { position: 'absolute', top: -4, right: -4 },
  createNewSparkle2: { position: 'absolute', bottom: 0, left: -4 },
  createNewTitle: { fontSize: 17, fontWeight: '800', color: '#fff', marginBottom: 4 },
  createNewDesc: { fontSize: 13, color: '#999', lineHeight: 18 },
  
  // Divider
  divider: { flexDirection: 'row', alignItems: 'center', marginVertical: 24 },
  dividerLine: { flex: 1, height: 1, backgroundColor: BORDER },
  dividerText: { fontSize: 11, fontWeight: '700', color: '#666', letterSpacing: 1, marginHorizontal: 16 },
  
  // Empty State
  emptyState: { alignItems: 'center', paddingVertical: 40 },
  emptyIconContainer: { 
    width: 80, 
    height: 80, 
    borderRadius: 40, 
    backgroundColor: BG, 
    justifyContent: 'center', 
    alignItems: 'center',
    marginBottom: 16,
    borderWidth: 2,
    borderColor: BORDER,
    borderStyle: 'dashed',
  },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#fff', marginBottom: 6 },
  emptyDesc: { fontSize: 13, color: '#666', textAlign: 'center', paddingHorizontal: 32 },
  
  // Reels List
  reelsList: { gap: 12, marginBottom: 20 },
  reelCard: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    padding: 12, 
    backgroundColor: BG, 
    borderRadius: 16, 
    borderWidth: 2, 
    borderColor: 'transparent',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 4,
    elevation: 2,
  },
  reelCardSelected: { 
    borderColor: GOLD, 
    backgroundColor: GOLD + '08',
    shadowColor: GOLD,
    shadowOpacity: 0.3,
    shadowRadius: 8,
    elevation: 6,
  },
  reelThumbContainer: { position: 'relative', marginRight: 12 },
  reelThumb: { width: 80, height: 80, borderRadius: 12, backgroundColor: '#222' },
  reelThumbPlaceholder: { justifyContent: 'center', alignItems: 'center' },
  selectedOverlay: { 
    position: 'absolute', 
    inset: 0, 
    backgroundColor: 'rgba(0,0,0,0.6)', 
    borderRadius: 12, 
    justifyContent: 'center', 
    alignItems: 'center' 
  },
  selectedCheckmark: { 
    width: 36, 
    height: 36, 
    borderRadius: 18, 
    backgroundColor: GOLD, 
    justifyContent: 'center', 
    alignItems: 'center',
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.8,
    shadowRadius: 4,
    elevation: 4,
  },
  reelDuration: { 
    position: 'absolute', 
    bottom: 6, 
    right: 6, 
    backgroundColor: 'rgba(0,0,0,0.8)', 
    borderRadius: 6, 
    paddingHorizontal: 6, 
    paddingVertical: 3,
    flexDirection: 'row',
    alignItems: 'center',
  },
  reelInfo: { flex: 1 },
  reelCaption: { fontSize: 14, fontWeight: '600', color: '#fff', marginBottom: 8, lineHeight: 18 },
  reelStatsRow: { flexDirection: 'row', gap: 12 },
  reelStat: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  reelStatText: { fontSize: 12, fontWeight: '600', color: '#999' },
  selectedBadge: { marginLeft: 8 },
  
  // Submit Button
  submitBtn: { 
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 10,
    backgroundColor: GOLD, 
    borderRadius: 16, 
    padding: 18, 
    marginTop: 8,
    marginBottom: 12,
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 6 },
    shadowOpacity: 0.5,
    shadowRadius: 12,
    elevation: 8,
  },
  submitBtnText: { fontSize: 17, fontWeight: '800', color: '#000', letterSpacing: 0.5 },
  
  // Feed Grid
  feedGrid: { 
    flexDirection: 'row', 
    flexWrap: 'wrap', 
    gap: 8, 
    marginHorizontal: 12 
  },
  feedCard: { 
    width: '48.5%', 
    aspectRatio: 0.75, 
    borderRadius: 12, 
    overflow: 'hidden',
    backgroundColor: CARD,
    borderWidth: 1,
    borderColor: BORDER,
    position: 'relative',
  },
  feedImage: { 
    width: '100%', 
    height: 200,
    backgroundColor: '#000',
  },
  feedImagePlaceholder: { 
    justifyContent: 'center', 
    alignItems: 'center',
    backgroundColor: '#1A1A1A',
  },
  feedPlayIcon: {
    position: 'absolute',
    top: '50%',
    left: '50%',
    transform: [{ translateX: -16 }, { translateY: -16 }],
  },
  feedOverlay: { 
    position: 'absolute', 
    bottom: 0, 
    left: 0, 
    right: 0, 
    padding: 8,
    background: 'linear-gradient(180deg, transparent 0%, rgba(0,0,0,0.8) 100%)',
  },
  feedStats: { 
    flexDirection: 'row', 
    gap: 12,
  },
  feedStat: { 
    flexDirection: 'row', 
    alignItems: 'center', 
    gap: 4,
  },
  feedStatText: { 
    fontSize: 12, 
    fontWeight: '700', 
    color: '#fff',
  },
  feedUser: { 
    position: 'absolute', 
    top: 8, 
    left: 8, 
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 6,
  },
  feedUsername: { 
    fontSize: 11, 
    fontWeight: '700', 
    color: '#fff',
  },
  
  comingSoon: { fontSize: 14, color: '#666', textAlign: 'center', padding: 32 },
});
