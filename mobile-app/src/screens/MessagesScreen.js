import React, { useState, useEffect, useRef, useCallback, memo } from 'react';
import {
  View, Text, StyleSheet, FlatList, TouchableOpacity, TouchableWithoutFeedback,
  Image, TextInput, ActivityIndicator, KeyboardAvoidingView, Platform, Modal,
  Alert, ScrollView, StatusBar, Pressable,
} from 'react-native';
import { Ionicons } from '@expo/vector-icons';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import * as ImagePicker from 'expo-image-picker';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';
import config from '../config';

const GOLD = '#C8B56A';
const BG = '#0D0D0D';
const CARD = '#1A1A1A';
const BORDER = '#262626';
const SUB = '#888';
const BASE = config.API_BASE_URL.replace('/api', '');
const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${BASE}${url}`;
};

function timeAgo(d) {
  if (!d) return '';
  const s = (Date.now() - new Date(d)) / 1000;
  if (s < 60) return `${Math.floor(s)}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h`;
  return `${Math.floor(s / 86400)}d`;
}

function clockTime(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

// ─── Avatar ───────────────────────────────────────────────────────────────────
const Avatar = memo(function Avatar({ uri, size = 44, name = '' }) {
  const [err, setErr] = useState(false);
  const u = uri ? mediaUrl(uri) : null;
  if (u && !err) {
    return (
      <Image
        source={{ uri: u }}
        style={{ width: size, height: size, borderRadius: size / 2 }}
        onError={() => setErr(true)}
      />
    );
  }
  return (
    <View style={{
      width: size, height: size, borderRadius: size / 2,
      backgroundColor: GOLD, justifyContent: 'center', alignItems: 'center',
    }}>
      <Text style={{ color: '#000', fontWeight: '700', fontSize: size * 0.38 }}>
        {(name || '?')[0].toUpperCase()}
      </Text>
    </View>
  );
});

// ─── New Chat Modal ────────────────────────────────────────────────────────────
function NewChatModal({ onClose, onSelectUser }) {
  const insets = useSafeAreaInsets();
  const [q, setQ] = useState('');
  const [results, setResults] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!q.trim()) { setResults([]); return; }
    let cancelled = false;
    setLoading(true);
    const t = setTimeout(async () => {
      try {
        const data = await api.request(`/messages/users/search/?q=${encodeURIComponent(q.trim())}`);
        if (!cancelled) setResults(Array.isArray(data) ? data : []);
      } catch { if (!cancelled) setResults([]); }
      finally { if (!cancelled) setLoading(false); }
    }, 250);
    return () => { cancelled = true; clearTimeout(t); };
  }, [q]);

  return (
    <Modal visible animationType="slide" transparent onRequestClose={onClose}>
      <TouchableWithoutFeedback onPress={onClose}>
        <View style={styles.modalOverlay} />
      </TouchableWithoutFeedback>
      <View style={[styles.newChatSheet, { paddingBottom: insets.bottom + 8 }]}>
        {/* Handle */}
        <View style={styles.sheetHandle} />
        <View style={styles.newChatHeader}>
          <Text style={styles.newChatTitle}>New Message</Text>
          <TouchableOpacity onPress={onClose} style={{ padding: 4 }}>
            <Ionicons name="close" size={22} color={SUB} />
          </TouchableOpacity>
        </View>
        {/* Search input */}
        <View style={styles.searchRow}>
          <Ionicons name="search" size={16} color={SUB} style={{ marginRight: 8 }} />
          <TextInput
            style={styles.searchInput}
            value={q}
            onChangeText={setQ}
            placeholder="Search users..."
            placeholderTextColor="#555"
            autoFocus
            returnKeyType="search"
          />
          {q.length > 0 && (
            <TouchableOpacity onPress={() => setQ('')}>
              <Ionicons name="close-circle" size={16} color={SUB} />
            </TouchableOpacity>
          )}
        </View>
        {/* Results */}
        <ScrollView style={{ flex: 1 }} keyboardShouldPersistTaps="handled">
          {loading && (
            <View style={{ padding: 24, alignItems: 'center' }}>
              <ActivityIndicator color={GOLD} />
            </View>
          )}
          {!loading && q.trim() && results.length === 0 && (
            <Text style={styles.emptyText}>No users found</Text>
          )}
          {!loading && !q.trim() && (
            <Text style={styles.emptyText}>Start typing to search users</Text>
          )}
          {results.map((u) => (
            <TouchableOpacity
              key={u.id}
              style={styles.userRow}
              onPress={() => onSelectUser(u)}
            >
              <Avatar uri={u.profile_photo} size={42} name={u.username} />
              <View style={{ flex: 1, marginLeft: 12 }}>
                <Text style={styles.userName}>{u.username}</Text>
                {(u.first_name || u.last_name) && (
                  <Text style={styles.userSub}>{u.first_name} {u.last_name}</Text>
                )}
              </View>
            </TouchableOpacity>
          ))}
        </ScrollView>
      </View>
    </Modal>
  );
}

// ─── Message Bubble ────────────────────────────────────────────────────────────
const MessageBubble = memo(function MessageBubble({ msg, onEdit, onDelete }) {
  const own = msg.is_own;

  const handleLongPress = () => {
    if (!own || msg.is_deleted) return;
    const opts = [];
    if (msg.is_editable && (!msg.media_type || msg.media_type === 'text')) {
      opts.push({ text: 'Edit', onPress: () => onEdit(msg) });
    }
    opts.push({
      text: 'Delete',
      style: 'destructive',
      onPress: () => {
        Alert.alert('Delete message', 'Delete this message?', [
          { text: 'Cancel', style: 'cancel' },
          { text: 'Delete', style: 'destructive', onPress: () => onDelete(msg) },
        ]);
      },
    });
    opts.push({ text: 'Cancel', style: 'cancel' });
    Alert.alert('Message options', undefined, opts);
  };

  const bubbleStyle = own
    ? [styles.bubble, styles.bubbleMine]
    : [styles.bubble, styles.bubbleOther];

  const textColor = own ? '#000' : '#fff';

  const renderContent = () => {
    if (msg.is_deleted) {
      return (
        <View style={bubbleStyle}>
          <Text style={{ color: own ? 'rgba(0,0,0,0.5)' : 'rgba(255,255,255,0.5)', fontStyle: 'italic', fontSize: 14 }}>
            Message deleted
          </Text>
        </View>
      );
    }
    if (msg.media_type === 'image' && msg.media_url) {
      return (
        <View>
          <Image
            source={{ uri: msg.media_url }}
            style={styles.msgImage}
            resizeMode="cover"
          />
          {!!msg.text && (
            <View style={[bubbleStyle, { marginTop: 4 }]}>
              <Text style={{ color: textColor, fontSize: 14, lineHeight: 19 }}>{msg.text}</Text>
            </View>
          )}
        </View>
      );
    }
    return (
      <View style={bubbleStyle}>
        <Text style={{ color: textColor, fontSize: 14, lineHeight: 19, flexWrap: 'wrap' }}>
          {msg.text}
        </Text>
      </View>
    );
  };

  return (
    <Pressable
      onLongPress={handleLongPress}
      style={[styles.msgRow, own && styles.msgRowMine]}
    >
      {!own && (
        <Avatar uri={msg.sender?.profile_photo} size={26} name={msg.sender?.username} />
      )}
      <View style={{ maxWidth: '75%' }}>
        {renderContent()}
        <View style={[styles.msgMeta, own && { alignItems: 'flex-end' }]}>
          {msg.edited_at && !msg.is_deleted && (
            <Text style={styles.editedTag}>Edited · </Text>
          )}
          <Text style={styles.msgTime}>{clockTime(msg.created_at)}</Text>
        </View>
      </View>
    </Pressable>
  );
});

// ─── Thread / Chat View ────────────────────────────────────────────────────────
function ChatView({ conversation, onBack, userId, navigation }) {
  const insets = useSafeAreaInsets();
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [editing, setEditing] = useState(null);
  const [attachment, setAttachment] = useState(null); // { uri, type, name }
  const flatRef = useRef(null);
  const pendingRef = useRef(0);
  const convId = conversation.id;
  const other = conversation.other_user;

  const fetchMessages = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await api.request(`/messages/conversations/${convId}/messages/`);
      const arr = Array.isArray(data) ? data : [];
      setMessages((prev) => {
        if (pendingRef.current > 0 && prev.length > arr.length) {
          const optimistic = prev.slice(arr.length);
          return [...arr, ...optimistic];
        }
        return arr;
      });
      // Mark as read
      api.request(`/messages/conversations/${convId}/read/`, { method: 'POST' }).catch(() => {});
    } catch {}
    finally { if (!silent) setLoading(false); }
  }, [convId]);

  useEffect(() => { fetchMessages(false); }, [fetchMessages]);

  // Poll every 30s
  useEffect(() => {
    if (!convId) return;
    const id = setInterval(() => fetchMessages(true), 30000);
    return () => clearInterval(id);
  }, [convId, fetchMessages]);

  // Auto-scroll to bottom
  useEffect(() => {
    if (!loading && messages.length > 0) {
      setTimeout(() => flatRef.current?.scrollToEnd({ animated: false }), 100);
    }
  }, [messages.length, loading]);

  // Cancel edit mode
  const cancelEdit = () => { setEditing(null); setText(''); };

  // Pick image from library
  const pickImage = async () => {
    const { status } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (status !== 'granted') {
      Alert.alert('Permission needed', 'Allow photo access to send images.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.8,
    });
    if (!result.canceled && result.assets?.[0]) {
      const asset = result.assets[0];
      setAttachment({ uri: asset.uri, type: 'image/jpeg', name: `photo_${Date.now()}.jpg` });
    }
  };

  const clearAttachment = () => setAttachment(null);

  const send = async () => {
    const trimmed = text.trim();

    // Edit mode
    if (editing) {
      if (!trimmed) return;
      setSending(true);
      try {
        await api.request(`/messages/${editing.id}/`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ text: trimmed }),
        });
        setMessages(prev => prev.map(m =>
          m.id === editing.id
            ? { ...m, text: trimmed, edited_at: new Date().toISOString() }
            : m,
        ));
        setEditing(null);
        setText('');
      } catch { Alert.alert('Error', 'Failed to edit message.'); }
      finally { setSending(false); }
      return;
    }

    // With image attachment
    if (attachment) {
      setSending(true);
      const att = attachment;
      setAttachment(null);
      setText('');
      try {
        pendingRef.current += 1;
        const formData = new FormData();
        formData.append('media', { uri: att.uri, type: att.type, name: att.name });
        formData.append('media_type', 'image');
        if (trimmed) formData.append('text', trimmed);
        const sent = await api.request(`/messages/conversations/${convId}/messages/`, {
          method: 'POST',
          body: formData,
        });
        setMessages(prev => [...prev, sent]);
        flatRef.current?.scrollToEnd({ animated: true });
      } catch { Alert.alert('Error', 'Failed to send image.'); }
      finally { setSending(false); pendingRef.current -= 1; }
      return;
    }

    // Plain text
    if (!trimmed) return;
    const optimistic = {
      id: `opt_${Date.now()}`, text: trimmed, is_own: true,
      sender: { id: userId }, created_at: new Date().toISOString(),
    };
    setMessages(prev => [...prev, optimistic]);
    setText('');
    setSending(true);
    try {
      pendingRef.current += 1;
      const sent = await api.request(`/messages/conversations/${convId}/messages/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: trimmed }),
      });
      setMessages(prev => prev.map(m => m.id === optimistic.id ? sent : m));
      flatRef.current?.scrollToEnd({ animated: true });
    } catch {
      setMessages(prev => prev.filter(m => m.id !== optimistic.id));
      Alert.alert('Error', 'Failed to send message.');
    } finally { setSending(false); pendingRef.current -= 1; }
  };

  const handleDelete = async (msg) => {
    try {
      await api.request(`/messages/${msg.id}/`, { method: 'DELETE' });
      setMessages(prev => prev.map(m =>
        m.id === msg.id ? { ...m, is_deleted: true, text: '' } : m,
      ));
    } catch { Alert.alert('Error', 'Failed to delete message.'); }
  };

  const handleEdit = (msg) => {
    setEditing(msg);
    setText(msg.text || '');
  };

  const renderMsg = useCallback(({ item }) => (
    <MessageBubble
      msg={item}
      onEdit={handleEdit}
      onDelete={handleDelete}
    />
  ), []);

  return (
    <KeyboardAvoidingView
      style={{ flex: 1, backgroundColor: BG }}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 0}
    >
      {/* Header */}
      <View style={[styles.chatHeader, { paddingTop: insets.top }]}>
        <TouchableOpacity onPress={onBack} style={{ padding: 4, marginRight: 4 }}>
          <Ionicons name="chevron-back" size={24} color={GOLD} />
        </TouchableOpacity>
        <Avatar uri={other?.profile_photo} size={36} name={other?.username} />
        <View style={{ flex: 1, marginLeft: 10 }}>
          <Text style={styles.chatName} numberOfLines={1}>{other?.username || 'Unknown'}</Text>
          {(other?.first_name || other?.last_name) ? (
            <Text style={styles.chatSub} numberOfLines={1}>{other.first_name} {other.last_name}</Text>
          ) : null}
        </View>
        <TouchableOpacity
          onPress={() => navigation.navigate('Profile', { userId: other?.id })}
          style={{ padding: 6 }}
        >
          <Ionicons name="person-outline" size={20} color={GOLD} />
        </TouchableOpacity>
      </View>

      {/* Messages */}
      {loading ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator color={GOLD} size="large" />
        </View>
      ) : (
        <FlatList
          ref={flatRef}
          data={messages}
          keyExtractor={m => String(m.id)}
          renderItem={renderMsg}
          contentContainerStyle={{ padding: 12, paddingBottom: 3, gap: 6 }}
          ListEmptyComponent={
            <View style={{ alignItems: 'center', marginTop: 60 }}>
              <Ionicons name="chatbubbles-outline" size={48} color="#333" />
              <Text style={{ color: SUB, marginTop: 12, fontSize: 14 }}>
                No messages yet. Say hello!
              </Text>
            </View>
          }
          removeClippedSubviews
          maxToRenderPerBatch={20}
        />
      )}

      {/* Attachment preview */}
      {attachment && (
        <View style={styles.attachPreview}>
          <Image source={{ uri: attachment.uri }} style={styles.attachThumb} />
          <Text style={{ color: '#fff', flex: 1, marginLeft: 10, fontSize: 13 }} numberOfLines={1}>
            {attachment.name}
          </Text>
          <TouchableOpacity onPress={clearAttachment} style={{ padding: 4 }}>
            <Ionicons name="close-circle" size={20} color={SUB} />
          </TouchableOpacity>
        </View>
      )}

      {/* Edit banner */}
      {editing && (
        <View style={styles.editBanner}>
          <Ionicons name="pencil" size={14} color={GOLD} />
          <Text style={{ color: GOLD, flex: 1, marginLeft: 8, fontSize: 13 }}>Editing message</Text>
          <TouchableOpacity onPress={cancelEdit} style={{ padding: 4 }}>
            <Ionicons name="close" size={16} color={SUB} />
          </TouchableOpacity>
        </View>
      )}

      {/* Composer */}
      <View style={styles.inputRow}>
        {!editing && (
          <TouchableOpacity onPress={pickImage} style={styles.attachBtn}>
            <Ionicons name="image-outline" size={22} color={SUB} />
          </TouchableOpacity>
        )}
        <TextInput
          style={styles.msgInput}
          value={text}
          onChangeText={setText}
          placeholder={editing ? 'Edit message…' : attachment ? 'Add a caption…' : 'Message…'}
          placeholderTextColor="#555"
          multiline
          maxLength={4000}
          returnKeyType="default"
        />
        <TouchableOpacity
          onPress={send}
          disabled={(!text.trim() && !attachment) || sending}
          style={[
            styles.sendBtn,
            { opacity: (!text.trim() && !attachment) || sending ? 0.5 : 1 },
          ]}
        >
          {sending
            ? <ActivityIndicator size="small" color="#000" />
            : <Ionicons name="send" size={16} color="#000" />}
        </TouchableOpacity>
      </View>
    </KeyboardAvoidingView>
  );
}

// ─── Conversation Row ─────────────────────────────────────────────────────────
const ConvRow = memo(function ConvRow({ conv, onPress, userId }) {
  const other = conv.other_user;
  const last = conv.last_message;
  const isOwn = last?.sender === userId || last?.sender_id === userId;
  const preview = last?.is_deleted
    ? 'Message deleted'
    : (last?.text || (last?.media_type ? '📷 Media' : 'No messages yet'));

  return (
    <TouchableOpacity style={styles.convoRow} onPress={onPress} activeOpacity={0.7}>
      <View>
        <Avatar uri={other?.profile_photo} size={50} name={other?.username} />
        {conv.unread_count > 0 && (
          <View style={styles.unreadDot}>
            <Text style={styles.unreadNum}>
              {conv.unread_count > 9 ? '9+' : conv.unread_count}
            </Text>
          </View>
        )}
      </View>
      <View style={{ flex: 1, marginLeft: 12 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 3 }}>
          <Text style={styles.convoName} numberOfLines={1}>{other?.username || 'Unknown'}</Text>
          <Text style={styles.convoTime}>{timeAgo(last?.created_at)}</Text>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center' }}>
          <Text
            style={[styles.convoPreview, conv.unread_count > 0 && styles.convoPreviewUnread]}
            numberOfLines={1}
          >
            {isOwn ? 'You: ' : ''}{preview}
          </Text>
        </View>
      </View>
    </TouchableOpacity>
  );
});

// ─── Main Screen ──────────────────────────────────────────────────────────────
export default function MessagesScreen({ navigation }) {
  const insets = useSafeAreaInsets();
  const { user: authUser } = useAuth();
  // authUser from /profile/me/ is UserProfileSerializer — actual user id is in .user.id
  const userId = authUser?.user?.id || authUser?.id;

  const [conversations, setConversations] = useState([]);
  const [filtered, setFiltered] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeConv, setActiveConv] = useState(null);
  const [showNewChat, setShowNewChat] = useState(false);

  const fetchConversations = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      const data = await api.request('/messages/conversations/');
      const arr = Array.isArray(data) ? data : [];
      setConversations(arr);
      setFiltered(prev => {
        if (!search.trim()) return arr;
        return arr.filter(c =>
          c.other_user?.username?.toLowerCase().includes(search.toLowerCase()),
        );
      });
    } catch {}
    finally { if (!silent) setLoading(false); }
  }, [search]);

  useEffect(() => { fetchConversations(false); }, []);

  // Poll every 2 minutes
  useEffect(() => {
    const id = setInterval(() => fetchConversations(true), 120000);
    return () => clearInterval(id);
  }, [fetchConversations]);

  // Filter on search change
  useEffect(() => {
    if (!search.trim()) {
      setFiltered(conversations);
    } else {
      setFiltered(
        conversations.filter(c =>
          c.other_user?.username?.toLowerCase().includes(search.toLowerCase()),
        ),
      );
    }
  }, [search, conversations]);

  const handleStartChat = async (u) => {
    try {
      const conv = await api.request('/messages/conversations/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ user_id: u.id }),
      });
      setShowNewChat(false);
      setActiveConv(conv);
      fetchConversations(true);
    } catch (e) {
      Alert.alert('Error', e?.message || 'Failed to start conversation');
    }
  };

  // If in a chat, show ChatView full-screen
  if (activeConv) {
    return (
      <View style={{ flex: 1, backgroundColor: BG }}>
        <StatusBar barStyle="light-content" backgroundColor={BG} />
        <ChatView
          conversation={activeConv}
          onBack={() => {
            setActiveConv(null);
            fetchConversations(true);
          }}
          userId={userId}
          navigation={navigation}
        />
      </View>
    );
  }

  return (
    <View style={[styles.container, { paddingTop: insets.top }]}>
      <StatusBar barStyle="light-content" backgroundColor={BG} />

      {/* Header */}
      <View style={styles.header}>
        <Text style={styles.headerTitle}>Messages</Text>
        <TouchableOpacity onPress={() => setShowNewChat(true)} style={{ padding: 4 }}>
          <Ionicons name="create-outline" size={22} color={GOLD} />
        </TouchableOpacity>
      </View>

      {/* Search */}
      <View style={styles.searchBar}>
        <Ionicons name="search" size={16} color={SUB} style={{ marginRight: 8 }} />
        <TextInput
          style={styles.searchInput}
          value={search}
          onChangeText={setSearch}
          placeholder="Search conversations..."
          placeholderTextColor="#555"
          returnKeyType="search"
        />
        {search.length > 0 && (
          <TouchableOpacity onPress={() => setSearch('')}>
            <Ionicons name="close-circle" size={16} color={SUB} />
          </TouchableOpacity>
        )}
      </View>

      {/* Conversation list */}
      {loading ? (
        <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center' }}>
          <ActivityIndicator color={GOLD} size="large" />
        </View>
      ) : (
        <FlatList
          data={filtered}
          keyExtractor={c => String(c.id)}
          renderItem={({ item }) => (
            <ConvRow
              conv={item}
              userId={userId}
              onPress={() => setActiveConv(item)}
            />
          )}
          ListEmptyComponent={
            <View style={styles.emptyState}>
              <Ionicons name="chatbubbles-outline" size={52} color="#333" />
              <Text style={styles.emptyTitle}>
                {search ? `No results for "${search}"` : 'No messages yet'}
              </Text>
              {!search && (
                <>
                  <Text style={styles.emptyBody}>
                    Start a conversation with anyone on the platform.
                  </Text>
                  <TouchableOpacity
                    style={styles.newMsgBtn}
                    onPress={() => setShowNewChat(true)}
                  >
                    <Text style={styles.newMsgBtnText}>Send message</Text>
                  </TouchableOpacity>
                </>
              )}
            </View>
          }
          refreshing={false}
          onRefresh={() => fetchConversations(false)}
        />
      )}

      {showNewChat && (
        <NewChatModal
          onClose={() => setShowNewChat(false)}
          onSelectUser={handleStartChat}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: BG },

  // Header
  header: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 14,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  headerTitle: { fontSize: 20, fontWeight: '800', color: '#fff' },

  // Search bar
  searchBar: {
    flexDirection: 'row', alignItems: 'center',
    margin: 12, padding: 10,
    backgroundColor: CARD, borderRadius: 22,
    borderWidth: 1, borderColor: BORDER,
  },
  searchInput: { flex: 1, color: '#fff', fontSize: 14, padding: 0 },

  // Conversation rows
  convoRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  convoName: { fontSize: 15, fontWeight: '700', color: '#fff', flex: 1 },
  convoTime: { fontSize: 12, color: SUB, marginLeft: 4 },
  convoPreview: { fontSize: 13, color: '#888', flex: 1 },
  convoPreviewUnread: { color: '#fff', fontWeight: '600' },
  unreadDot: {
    position: 'absolute', bottom: 0, right: 0,
    minWidth: 18, height: 18, borderRadius: 9,
    backgroundColor: GOLD,
    justifyContent: 'center', alignItems: 'center',
    paddingHorizontal: 3,
  },
  unreadNum: { fontSize: 10, color: '#000', fontWeight: '700' },

  // Chat header
  chatHeader: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 12, paddingBottom: 12,
    borderBottomWidth: 1, borderBottomColor: BORDER,
    backgroundColor: BG,
  },
  chatName: { fontSize: 15, fontWeight: '700', color: '#fff' },
  chatSub: { fontSize: 12, color: SUB },

  // Messages
  msgRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 6, marginBottom: 2 },
  msgRowMine: { flexDirection: 'row-reverse' },
  bubble: { borderRadius: 18, paddingHorizontal: 14, paddingVertical: 9, maxWidth: '100%' },
  bubbleMine: { backgroundColor: GOLD, borderBottomRightRadius: 4 },
  bubbleOther: { backgroundColor: CARD, borderBottomLeftRadius: 4 },
  msgMeta: { flexDirection: 'row', marginTop: 3, alignItems: 'center' },
  msgTime: { fontSize: 10, color: SUB },
  editedTag: { fontSize: 10, color: SUB },
  msgImage: { width: 220, height: 260, borderRadius: 14, backgroundColor: '#000' },

  // Composer
  inputRow: {
    flexDirection: 'row', alignItems: 'flex-end',
    paddingHorizontal: 10, paddingTop: 8, paddingBottom: 8,
    borderTopWidth: 1, borderTopColor: BORDER,
    gap: 8, backgroundColor: BG,
    position: 'absolute',
    bottom: 1,
    left: 0,
    right: 0,
    zIndex: 10,
    elevation: 10,
  },
  attachBtn: { padding: 6, alignSelf: 'flex-end', marginBottom: 2 },
  msgInput: {
    flex: 1, backgroundColor: CARD, borderRadius: 22,
    paddingHorizontal: 16, paddingVertical: 10,
    color: '#fff', fontSize: 15, maxHeight: 120,
    borderWidth: 1, borderColor: BORDER,
  },
  sendBtn: {
    width: 40, height: 40, borderRadius: 20,
    backgroundColor: GOLD,
    justifyContent: 'center', alignItems: 'center',
    alignSelf: 'flex-end',
  },

  // Attachment + edit banners
  attachPreview: {
    flexDirection: 'row', alignItems: 'center',
    padding: 10, borderTopWidth: 1, borderTopColor: BORDER,
    backgroundColor: CARD,
    position: 'absolute',
    bottom: 60,
    left: 0,
    right: 0,
    zIndex: 11,
    elevation: 11,
  },
  attachThumb: { width: 48, height: 48, borderRadius: 8, backgroundColor: '#000' },
  editBanner: {
    flexDirection: 'row', alignItems: 'center',
    padding: 10, borderTopWidth: 1, borderTopColor: BORDER,
    backgroundColor: CARD,
    position: 'absolute',
    bottom: 60,
    left: 0,
    right: 0,
    zIndex: 11,
    elevation: 11,
  },

  // New chat modal
  modalOverlay: {
    flex: 1, backgroundColor: 'rgba(0,0,0,0.6)',
  },
  newChatSheet: {
    position: 'absolute', bottom: 0, left: 0, right: 0,
    height: '75%', backgroundColor: CARD,
    borderTopLeftRadius: 20, borderTopRightRadius: 20,
    overflow: 'hidden',
  },
  sheetHandle: {
    width: 40, height: 4, borderRadius: 2,
    backgroundColor: BORDER, alignSelf: 'center', marginTop: 10, marginBottom: 4,
  },
  newChatHeader: {
    flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 12,
    borderBottomWidth: 1, borderBottomColor: BORDER,
  },
  newChatTitle: { fontSize: 17, fontWeight: '700', color: '#fff' },
  searchRow: {
    flexDirection: 'row', alignItems: 'center',
    margin: 12, padding: 10,
    backgroundColor: BG, borderRadius: 12,
    borderWidth: 1, borderColor: BORDER,
  },
  userRow: {
    flexDirection: 'row', alignItems: 'center',
    paddingHorizontal: 16, paddingVertical: 10,
  },
  userName: { fontSize: 14, fontWeight: '700', color: '#fff' },
  userSub: { fontSize: 12, color: SUB, marginTop: 2 },
  emptyText: { padding: 24, textAlign: 'center', color: SUB, fontSize: 14 },

  // Empty state
  emptyState: { alignItems: 'center', paddingTop: 60, paddingHorizontal: 24 },
  emptyTitle: { fontSize: 16, fontWeight: '700', color: '#fff', marginTop: 16 },
  emptyBody: { fontSize: 13, color: SUB, textAlign: 'center', marginTop: 8 },
  newMsgBtn: {
    marginTop: 16, backgroundColor: GOLD,
    paddingHorizontal: 24, paddingVertical: 10, borderRadius: 22,
  },
  newMsgBtnText: { color: '#000', fontWeight: '700', fontSize: 14 },
});
