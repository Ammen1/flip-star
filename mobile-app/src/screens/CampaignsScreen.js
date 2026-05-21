import React, { useState, useEffect, useCallback } from "react";
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, ActivityIndicator, RefreshControl, ScrollView, Dimensions } from "react-native";
import { Ionicons } from "@expo/vector-icons";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import { useTheme } from "../contexts/ThemeContext";
import api from "../api";
import config from "../config";

const { width } = Dimensions.get('window');
const GOLD = "#8fc441";
const LIGHT_GOLD = "#b5dd8f";
const BG = "#0D0D0D";
const CARD = "#1A1A1A";
const BORDER = "#262626";

const TABS = [
  { id: 'all',       label: 'All',       icon: 'trophy-outline' },
  { id: 'active',    label: 'Active',    icon: 'flame-outline' },
  { id: 'voting',    label: 'Voting',    icon: 'award-outline' },
  { id: 'upcoming',  label: 'Soon',      icon: 'time-outline' },
  { id: 'completed', label: 'Completed', icon: 'calendar-outline' },
];

const STATUS_META = {
  active:    { color: '#10B981', label: 'Active', icon: 'flame-outline' },
  voting:    { color: '#3B82F6', label: 'Voting', icon: 'award-outline' },
  upcoming:  { color: '#F59E0B', label: 'Soon',   icon: 'time-outline' },
  completed: { color: '#94A3B8', label: 'Ended',  icon: 'calendar-outline' },
};

function timeLeft(endDate) {
  if (!endDate) return "";
  const diff = new Date(endDate) - Date.now();
  if (diff <= 0) return "Ended";
  const d = Math.floor(diff / 86400000);
  const h = Math.floor((diff % 86400000) / 3600000);
  return d > 0 ? `${d}d ${h}h left` : `${h}h left`;
}

const BASE = config.API_BASE_URL.replace('/api', '');
function mediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${BASE}${url}`;
}

export default function CampaignsScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState('all');

  useEffect(() => { loadCampaigns(); }, [filter]);

  const loadCampaigns = async () => {
    try {
      setLoading(true);
      const status = filter === 'all' ? '' : filter;
      const data = await api.request(`/campaigns/?status=${status}`);
      const campaignsData = Array.isArray(data) ? data : (data.results || []);
      setCampaigns(campaignsData);
    } catch (error) {
      console.error('Failed to load campaigns:', error);
      setCampaigns([]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  const renderCampaignCard = useCallback(({ item }) => {
    const statusInfo = STATUS_META[item.status] || STATUS_META.active;
    const isActive = item.status === 'active';
    const hasEntered = item.has_entered; // Check if user has already joined
    
    const btnLabel = isActive ? (hasEntered ? 'View Campaign' : 'View & Join') : 
                    item.status === 'upcoming' ? 'Coming Soon' : 
                    item.status === 'voting' ? 'Vote Now' : 'View Results';
    
    return (
      <TouchableOpacity 
        style={styles.campaignCard}
        onPress={() => navigation.navigate('CampaignDetail', { campaignId: item.id })} 
        activeOpacity={0.85}
      >
        {/* Banner Image */}
        <View style={styles.imageContainer}>
          {item.image ? (
            <Image 
              source={{ uri: mediaUrl(item.image) }} 
              style={styles.banner} 
              resizeMode="cover"
            />
          ) : (
            <View style={[styles.banner, styles.bannerPlaceholder]}>
              <Ionicons name="trophy" size={56} color={GOLD} opacity={0.5} />
            </View>
          )}
          
          {/* Gradient overlay */}
          <View style={styles.gradientOverlay} />
          
          {/* Status pill */}
          <View style={[styles.statusPill, { backgroundColor: statusInfo.color }]}>
            <Ionicons name={statusInfo.icon} size={10} color="#fff" strokeWidth={3} />
            <Text style={styles.statusPillText}>{statusInfo.label}</Text>
          </View>
          
          {/* Campaign type pill */}
          <View style={styles.typePill}>
            <Ionicons name="trophy-outline" size={10} color="#fff" />
            <Text style={styles.typePillText}>Campaign</Text>
          </View>
        </View>
        
        {/* Content */}
        <View style={styles.cardContent}>
          <Text style={styles.cardTitle} numberOfLines={2}>{item.title}</Text>
          {item.description && (
            <Text style={styles.cardDescription} numberOfLines={3}>{item.description}</Text>
          )}
          
          {/* Meta Info */}
          <View style={styles.metaRow}>
            <View style={styles.metaItem}>
              <Ionicons name="trophy-outline" size={14} color={GOLD} />
              <Text style={styles.metaText}>
                {item.prize_description || (item.prize_amount ? `${item.prize_amount} ETB` : 'Prize')}
              </Text>
            </View>
            <View style={styles.metaItem}>
              <Ionicons name="people-outline" size={14} color="#888" />
              <Text style={styles.metaText}>{(item.entries_count || 0)} entries</Text>
            </View>
          </View>
          
          <View style={styles.metaRow}>
            <View style={styles.metaItem}>
              <Ionicons name="time-outline" size={14} color="#888" />
              <Text style={styles.metaText}>{timeLeft(item.end_date)}</Text>
            </View>
          </View>
          
          {/* Action Button */}
          <TouchableOpacity 
            style={[
              styles.actionButton,
              !isActive && styles.actionButtonDisabled,
              item.status === 'voting' && styles.votingButton
            ]} 
            onPress={() => navigation.navigate('CampaignDetail', { campaignId: item.id })}
          >
            <Text style={[
              styles.actionButtonText,
              !isActive && styles.actionButtonTextDisabled,
              item.status === 'voting' && styles.votingButtonText
            ]}>
              {btnLabel}
            </Text>
          </TouchableOpacity>
        </View>
      </TouchableOpacity>
    );
  }, [navigation]);

  return (
    <View style={[styles.container, { backgroundColor: colors.bg, paddingTop: insets.top }]}>
      {/* Sticky Header */}
      <View style={[styles.header, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}>
        <TouchableOpacity onPress={() => navigation.goBack()} style={styles.backButton}>
          <Ionicons name="chevron-back" size={24} color={colors.primary} />
        </TouchableOpacity>
        <View style={styles.headerTitle}>
          <Ionicons name="trophy" size={20} color={colors.primary} />
          <Text style={[styles.headerTitleText, { color: colors.text }]}>Campaigns</Text>
        </View>
        <View style={{ width: 24 }} />
      </View>

      {/* Filter Pills */}
      <ScrollView 
        horizontal 
        showsHorizontalScrollIndicator={false} 
        style={[styles.filterContainer, { backgroundColor: colors.cardBg, borderBottomColor: colors.border }]}
        contentContainerStyle={styles.filterContent}
      >
        {TABS.map(tab => {
          const isActive = filter === tab.id;
          return (
            <TouchableOpacity
              key={tab.id}
              style={[
                styles.filterChip,
                { backgroundColor: colors.cardBg, borderColor: colors.border },
                isActive && { backgroundColor: colors.primary, borderColor: colors.primary }
              ]}
              onPress={() => setFilter(tab.id)}
            >
              <Ionicons 
                name={tab.icon} 
                size={13} 
                color={isActive ? (colors.text === '#FFFFFF' ? '#000' : '#fff') : colors.primary} 
              />
              <Text style={[
                styles.filterText,
                { color: colors.primary },
                isActive && { color: colors.text === '#FFFFFF' ? '#000' : '#fff' }
              ]}>
                {tab.label}
              </Text>
            </TouchableOpacity>
          );
        })}
      </ScrollView>

      {/* Hero Section */}
      <View style={[styles.heroSection, { backgroundColor: colors.primary + '15', borderColor: colors.primary + '25' }]}>
        <View style={[styles.heroIcon, { backgroundColor: colors.primary }]}>
          <Ionicons name="trophy" size={28} color="#000" />
        </View>
        <Text style={[styles.heroTitle, { color: colors.primaryDark || colors.primary }]}>Win Real Prizes</Text>
        <Text style={[styles.heroSubtitle, { color: colors.textSecondary }]}>
          Join campaigns, submit your best content, and win amazing rewards.
        </Text>
      </View>

      {/* Campaigns List */}
      {loading ? (
        <View style={styles.loadingContainer}>
          <ActivityIndicator size="large" color={colors.primary} />
          <Text style={[styles.loadingText, { color: colors.textSecondary }]}>Loading campaigns...</Text>
        </View>
      ) : (
        <FlatList
          data={campaigns}
          renderItem={renderCampaignCard}
          keyExtractor={item => String(item.id)}
          removeClippedSubviews={true}
          maxToRenderPerBatch={5}
          windowSize={5}
          initialNumToRender={4}
          refreshControl={
            <RefreshControl 
              refreshing={refreshing} 
              onRefresh={() => {
                setRefreshing(true);
                loadCampaigns();
              }} 
              tintColor={GOLD} 
            />
          }
          contentContainerStyle={styles.listContainer}
          ListEmptyComponent={
            <View style={styles.emptyContainer}>
              <Ionicons name="trophy-outline" size={48} color="#666" />
              <Text style={styles.emptyText}>No campaigns found</Text>
              <Text style={styles.emptySubtext}>Check back later for new opportunities!</Text>
            </View>
          }
          showsVerticalScrollIndicator={false}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { 
    flex: 1, 
    backgroundColor: BG 
  },
  // Header Styles
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
  headerTitle: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  headerTitleText: {
    fontSize: 18,
    fontWeight: '800',
    color: GOLD,
  },
  // Filter Styles
  filterContainer: {
    paddingHorizontal: 16,
    paddingVertical: 8,
    borderBottomWidth: 1,
    borderBottomColor: BORDER,
  },
  filterContent: {
    gap: 6,
  },
  filterChip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    paddingHorizontal: 12,
    paddingVertical: 7,
    borderRadius: 18,
    backgroundColor: CARD,
    borderWidth: 1.5,
    borderColor: BORDER,
  },
  filterChipActive: {
    backgroundColor: GOLD,
    borderColor: GOLD,
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.25,
    shadowRadius: 12,
    elevation: 8,
  },
  filterText: {
    fontSize: 12,
    fontWeight: '700',
    color: GOLD,
  },
  filterTextActive: {
    color: '#000',
  },
  // Hero Section
  heroSection: {
    margin: 12,
    marginVertical: 16,
    padding: 28,
    backgroundColor: `${GOLD}15`,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: `${GOLD}25`,
    alignItems: 'center',
  },
  heroIcon: {
    width: 56,
    height: 56,
    borderRadius: 28,
    backgroundColor: GOLD,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 12,
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 8 },
    shadowOpacity: 0.5,
    shadowRadius: 24,
    elevation: 12,
  },
  heroTitle: {
    fontSize: 26,
    fontWeight: '900',
    color: LIGHT_GOLD,
    marginBottom: 6,
  },
  heroSubtitle: {
    fontSize: 13,
    color: '#888',
    textAlign: 'center',
    lineHeight: 18,
  },
  // Campaign Card Styles
  campaignCard: {
    backgroundColor: CARD,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: BORDER,
    marginHorizontal: 12,
    marginBottom: 14,
    overflow: 'hidden',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 4,
  },
  imageContainer: {
    width: '100%',
    height: 150,
    position: 'relative',
    overflow: 'hidden',
  },
  banner: {
    width: '100%',
    height: '100%',
    backgroundColor: '#000',
  },
  bannerPlaceholder: {
    justifyContent: 'center',
    alignItems: 'center',
    backgroundColor: `linear-gradient(135deg, ${GOLD}30, #F59E0B30)`,
  },
  gradientOverlay: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    backgroundColor: 'transparent',
  },
  statusPill: {
    position: 'absolute',
    top: 10,
    left: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 12,
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 4,
  },
  statusPillText: {
    color: '#fff',
    fontSize: 10,
    fontWeight: '800',
    textTransform: 'uppercase',
    letterSpacing: 0.5,
  },
  typePill: {
    position: 'absolute',
    top: 10,
    right: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 8,
    paddingVertical: 4,
    borderRadius: 10,
    backgroundColor: 'rgba(0,0,0,0.6)',
  },
  typePillText: {
    color: '#fff',
    fontSize: 9,
    fontWeight: '700',
  },
  cardContent: {
    padding: 14,
  },
  cardTitle: {
    fontSize: 16,
    fontWeight: '800',
    color: LIGHT_GOLD,
    marginBottom: 8,
    lineHeight: 22,
  },
  cardDescription: {
    fontSize: 13,
    color: '#888',
    marginBottom: 12,
    lineHeight: 18,
  },
  metaRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 8,
  },
  metaItem: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    flex: 1,
  },
  metaText: {
    fontSize: 11,
    color: '#888',
    fontWeight: '500',
  },
  actionButton: {
    backgroundColor: GOLD,
    borderRadius: 8,
    paddingVertical: 10,
    alignItems: 'center',
    marginTop: 8,
    shadowColor: GOLD,
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 12,
    elevation: 8,
  },
  actionButtonDisabled: {
    backgroundColor: '#333',
    shadowOpacity: 0,
    elevation: 0,
  },
  votingButton: {
    backgroundColor: '#3B82F6',
    shadowColor: '#3B82F6',
  },
  actionButtonText: {
    color: '#000',
    fontSize: 14,
    fontWeight: '700',
  },
  actionButtonTextDisabled: {
    color: '#666',
  },
  votingButtonText: {
    color: '#fff',
  },
  // Loading and Empty States
  loadingContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 60,
  },
  loadingText: {
    color: '#888',
    fontSize: 14,
    marginTop: 12,
  },
  listContainer: {
    paddingHorizontal: 0,
    paddingBottom: 80,
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 80,
  },
  emptyText: {
    fontSize: 16,
    fontWeight: '700',
    color: '#666',
    marginTop: 12,
  },
  emptySubtext: {
    fontSize: 13,
    color: '#888',
    marginTop: 4,
    textAlign: 'center',
  },
});
