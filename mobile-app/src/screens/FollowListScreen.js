import React, { useState, useEffect } from 'react';
import { View, Text, StyleSheet, FlatList, TouchableOpacity, Image, ActivityIndicator } from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';

export default function FollowListScreen({ navigation, route }) {
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const { userId, type } = route.params || {};
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [following, setFollowing] = useState({});

  useEffect(() => { loadList(); }, [userId, type]);

  const loadList = async () => {
    try {
      const endpoint = type === 'followers' ? `/follows/?following=${userId}` : `/follows/?follower=${userId}`;
      const data = await api.request(endpoint);
      const list = Array.isArray(data) ? data : (data.results || []);
      const users = list.map(f => type === 'followers' ? f.follower_user || f.follower : f.following_user || f.following);
      setUsers(users.filter(Boolean));
      const fMap = {};
      users.forEach(u => { if (u?.is_following) fMap[u.id] = true; });
      setFollowing(fMap);
    } catch { setUsers([]); }
    finally { setLoading(false); }
  };

  const toggleFollow = async (targetUser) => {
    const prev = following[targetUser.id];
    setFollowing(f => ({ ...f, [targetUser.id]: !prev }));
    try {
      await api.request('/follows/toggle/', { method: 'POST', body: JSON.stringify({ following_id: targetUser.id }) });
    } catch { setFollowing(f => ({ ...f, [targetUser.id]: prev })); }
  };

  const renderItem = ({ item }) => (
    <View style={styles.row}>
      <TouchableOpacity style={styles.userInfo} onPress={() => navigation.navigate('Profile', { userId: item.id })}>
        {item.profile_photo
          ? <Image source={{ uri: item.profile_photo }} style={styles.avatar} />
          : <View style={[styles.avatar, { backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center' }]}>
              <Text style={{ color: '#000', fontWeight: '700', fontSize: 16 }}>{(item.username || '?')[0].toUpperCase()}</Text>
            </View>}
        <View style={{ marginLeft: 12 }}>
          <Text style={styles.username}>{item.username}</Text>
          {item.bio && <Text style={styles.bio} numberOfLines={1}>{item.bio}</Text>}
        </View>
      </TouchableOpacity>
      {item.id !== user?.id && (
        <TouchableOpacity
          style={[styles.followBtn, following[item.id] && styles.followingBtn]}
          onPress={() => toggleFollow(item)}
        >
          <Text style={[styles.followBtnText, following[item.id] && styles.followingBtnText]}>
            {following[item.id] ? 'Following' : 'Follow'}
          </Text>
        </TouchableOpacity>
      )}
    </View>
  );

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <View style={styles.header}>
        <TouchableOpacity onPress={() => navigation.goBack()}>
          <Ionicons name="chevron-back" size={24} color={GOLD} />
        </TouchableOpacity>
        <Text style={styles.headerTitle}>{type === 'followers' ? 'Followers' : 'Following'}</Text>
        <View style={{ width: 24 }} />
      </View>
      {loading
        ? <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}><ActivityIndicator size="large" color={GOLD} /></View>
        : <FlatList
            data={users}
            keyExtractor={u => String(u.id)}
            renderItem={renderItem}
            ListEmptyComponent={<View style={{ padding: 40, alignItems: 'center' }}><Text style={{ color: '#666' }}>No {type} yet</Text></View>}
          />}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: BORDER },
  headerTitle: { fontSize: 17, fontWeight: '700', color: '#fff' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 14, borderBottomWidth: 1, borderBottomColor: BORDER },
  userInfo: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  avatar: { width: 46, height: 46, borderRadius: 23 },
  username: { fontSize: 15, fontWeight: '700', color: '#fff' },
  bio: { fontSize: 12, color: '#888', marginTop: 2 },
  followBtn: { paddingHorizontal: 18, paddingVertical: 7, borderRadius: 8, backgroundColor: GOLD },
  followingBtn: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: BORDER },
  followBtnText: { color: '#000', fontWeight: '700', fontSize: 13 },
  followingBtnText: { color: '#fff' },
});
