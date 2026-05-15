import { useState, useEffect, useRef, useCallback, memo } from 'react';
import {
  ChevronLeft, Send, Search, Edit3, Trash2, MoreVertical, X, PenSquare,
  Paperclip, Mic, Image as ImageIcon, FileText, Play, Pause, Download,
  Trash,
} from 'lucide-react';
import api from '../api';
import config from '../config';
import { useTheme } from '../contexts/ThemeContext';

// ─── Helpers ──────────────────────────────────────────────────────────────────
const relTime = (iso) => {
  if (!iso) return '';
  const d = new Date(iso);
  const now = Date.now();
  const s = Math.max(1, Math.round((now - d.getTime()) / 1000));
  if (s < 60) return `${s}s`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h`;
  const days = Math.round(h / 24);
  if (days < 7) return `${days}d`;
  return d.toLocaleDateString();
};

const clockTime = (iso) => {
  if (!iso) return '';
  return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
};

const getPhotoUrl = (photo) => {
  if (!photo) return null;
  if (photo.startsWith('http')) return photo;
  return `${config.API_BASE_URL.replace('/api', '')}${photo}`;
};

const formatBytes = (bytes) => {
  if (!bytes && bytes !== 0) return '';
  const units = ['B', 'KB', 'MB', 'GB'];
  let n = bytes; let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n < 10 && i > 0 ? 1 : 0)} ${units[i]}`;
};

const formatDuration = (secs) => {
  if (!secs && secs !== 0) return '';
  const s = Math.max(0, Math.round(secs));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return `${m}:${r.toString().padStart(2, '0')}`;
};

// ─── Voice / audio player (used in message bubbles) ───────────────────────────
const AudioPlayer = memo(function AudioPlayer({ url, duration, own, T, priColor }) {
  const audioRef = useRef(null);
  const [playing, setPlaying] = useState(false);
  const [pos, setPos] = useState(0);
  const [dur, setDur] = useState(duration || 0);

  const onToggle = () => {
    const a = audioRef.current;
    if (!a) return;
    if (a.paused) { 
      a.play().catch((err) => {
        if (err.name !== 'AbortError') console.log('Play error:', err);
      }); 
    } else { 
      a.pause(); 
    }
  };

  useEffect(() => {
    const a = audioRef.current;
    if (!a) return;
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnd = () => { setPlaying(false); setPos(0); };
    const onTime = () => setPos(a.currentTime || 0);
    const onMeta = () => { if (!dur && a.duration && isFinite(a.duration)) setDur(a.duration); };
    a.addEventListener('play', onPlay);
    a.addEventListener('pause', onPause);
    a.addEventListener('ended', onEnd);
    a.addEventListener('timeupdate', onTime);
    a.addEventListener('loadedmetadata', onMeta);
    return () => {
      a.removeEventListener('play', onPlay);
      a.removeEventListener('pause', onPause);
      a.removeEventListener('ended', onEnd);
      a.removeEventListener('timeupdate', onTime);
      a.removeEventListener('loadedmetadata', onMeta);
    };
  }, [url]); // eslint-disable-line

  const pct = dur > 0 ? Math.min(100, (pos / dur) * 100) : 0;
  const trackBg = own ? 'rgba(255,255,255,0.28)' : (T.border || '#ccc');
  const fillBg = own ? '#fff' : priColor;
  const iconColor = own ? '#fff' : (T.txt || '#000');

  // Tiny fake "waveform" bars for style — purely visual
  const bars = 26;
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 10,
      minWidth: 210, padding: '2px 2px',
    }}>
      <button
        type="button"
        onClick={onToggle}
        style={{
          width: 32, height: 32, borderRadius: '50%',
          background: own ? 'rgba(255,255,255,0.22)' : (T.cardBg || '#fff'),
          border: 'none', cursor: 'pointer',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          color: iconColor, flexShrink: 0,
        }}
        aria-label={playing ? 'Pause' : 'Play'}
      >
        {playing ? <Pause size={16} /> : <Play size={16} />}
      </button>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 2, height: 20 }}>
          {Array.from({ length: bars }).map((_, i) => {
            const active = (i / bars) * 100 <= pct;
            const h = 4 + ((i * 7) % 14); // pseudo-random heights
            return (
              <div key={i} style={{
                width: 2, height: h,
                background: active ? fillBg : trackBg,
                borderRadius: 1,
                transition: 'background 0.1s',
              }} />
            );
          })}
        </div>
        <div style={{
          fontSize: 10, marginTop: 3,
          color: own ? 'rgba(255,255,255,0.85)' : T.sub,
        }}>
          {formatDuration(pos || dur)}
        </div>
      </div>
      <audio ref={audioRef} src={url} preload="metadata" />
    </div>
  );
});

const Avatar = ({ user, size = 44 }) => {
  const url = getPhotoUrl(user?.profile_photo);
  if (url) {
    return (
      <img
        src={url}
        alt={user?.username || ''}
        style={{
          width: size, height: size, borderRadius: '50%',
          objectFit: 'cover', flexShrink: 0,
          background: '#e5e5e5',
        }}
      />
    );
  }
  const initial = (user?.username || '?')[0].toUpperCase();
  return (
    <div
      style={{
        width: size, height: size, borderRadius: '50%',
        background: 'linear-gradient(135deg,#8fc441,#8fc441)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        color: '#fff', fontWeight: 800, fontSize: size * 0.38, flexShrink: 0,
      }}
    >
      {initial}
    </div>
  );
};

// ─── New Chat Modal: search users + start conversation ────────────────────────
function NewChatModal({ onClose, onSelectUser, T }) {
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
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.55)', zIndex: 5000,
        display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: T.cardBg, borderRadius: 18, width: '100%', maxWidth: 480,
          maxHeight: '85vh', display: 'flex', flexDirection: 'column', overflow: 'hidden',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{
          padding: '16px 20px', borderBottom: `1px solid ${T.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        }}>
          <div style={{ fontSize: 17, fontWeight: 700, color: T.txt }}>New Message</div>
          <button onClick={onClose} style={{
            background: 'none', border: 'none', cursor: 'pointer',
            color: T.sub, padding: 4, display: 'flex',
          }}>
            <X size={22} />
          </button>
        </div>
        <div style={{ padding: '12px 16px', borderBottom: `1px solid ${T.border}` }}>
          <div style={{
            display: 'flex', alignItems: 'center', gap: 10,
            background: T.bg, borderRadius: 12, padding: '10px 14px',
          }}>
            <Search size={18} color={T.sub} />
            <input
              autoFocus
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search users..."
              style={{
                flex: 1, border: 'none', outline: 'none',
                background: 'transparent', color: T.txt, fontSize: 16,
              }}
            />
          </div>
        </div>
        <div style={{ flex: 1, overflowY: 'auto', padding: '8px 0' }}>
          {loading && <div style={{ padding: 24, textAlign: 'center', color: T.sub, fontSize: 14 }}>Searching...</div>}
          {!loading && q.trim() && results.length === 0 && (
            <div style={{ padding: 24, textAlign: 'center', color: T.sub, fontSize: 14 }}>
              No users found
            </div>
          )}
          {!loading && !q.trim() && (
            <div style={{ padding: 24, textAlign: 'center', color: T.sub, fontSize: 14 }}>
              Start typing a username to search
            </div>
          )}
          {results.map((u) => (
            <button
              key={u.id}
              onClick={() => onSelectUser(u)}
              style={{
                width: '100%', display: 'flex', alignItems: 'center', gap: 12,
                padding: '10px 18px', border: 'none', background: 'none',
                cursor: 'pointer', textAlign: 'left', color: T.txt,
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = T.bg)}
              onMouseLeave={(e) => (e.currentTarget.style.background = 'none')}
            >
              <Avatar user={u} size={40} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 700 }}>{u.username}</div>
                {(u.first_name || u.last_name) && (
                  <div style={{ fontSize: 12, color: T.sub }}>
                    {u.first_name} {u.last_name}
                  </div>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Message Bubble ────────────────────────────────────────────────────────────
const MessageBubble = memo(function MessageBubble({ msg, T, onEdit, onDelete, priColor }) {
  const [menuOpen, setMenuOpen] = useState(false);
  const own = msg.is_own;

  const bubbleStyle = own
    ? {
        background: priColor,
        color: '#fff',
        borderRadius: '18px 18px 4px 18px',
      }
    : {
        background: T.cardBg === '#FFF' || T.cardBg === '#FFFFFF' ? '#F1F1F3' : T.bg,
        color: T.txt,
        borderRadius: '18px 18px 18px 4px',
      };

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: own ? 'row-reverse' : 'row',
        alignItems: 'flex-end',
        gap: 6,
        marginBottom: 6,
      }}
    >
      <div style={{ position: 'relative', maxWidth: '78%' }}>
        {(() => {
          if (msg.is_deleted) {
            return (
              <div style={{
                padding: '10px 14px',
                fontSize: 14, lineHeight: 1.4,
                fontStyle: 'italic', opacity: 0.65,
                ...bubbleStyle,
              }}>
                Message deleted
              </div>
            );
          }

          const mt = msg.media_type;
          const mediaUrl = msg.media_url;

          // Image
          if (mt === 'image' && mediaUrl) {
            return (
              <div>
                <a href={mediaUrl} target="_blank" rel="noreferrer"
                   style={{ display: 'block', lineHeight: 0 }}>
                  <img
                    src={mediaUrl}
                    alt={msg.media_name || 'image'}
                    style={{
                      maxWidth: 260, maxHeight: 340,
                      width: '100%', height: 'auto',
                      borderRadius: 16,
                      display: 'block',
                      background: '#000',
                    }}
                  />
                </a>
                {msg.text && (
                  <div style={{
                    padding: '8px 12px', marginTop: 4,
                    fontSize: 14, lineHeight: 1.4,
                    wordBreak: 'break-word', whiteSpace: 'pre-wrap',
                    ...bubbleStyle,
                  }}>{msg.text}</div>
                )}
              </div>
            );
          }

          // Video
          if (mt === 'video' && mediaUrl) {
            return (
              <div>
                <video
                  src={mediaUrl}
                  controls
                  playsInline
                  style={{
                    maxWidth: 280, maxHeight: 360,
                    width: '100%',
                    borderRadius: 16,
                    background: '#000',
                  }}
                />
                {msg.text && (
                  <div style={{
                    padding: '8px 12px', marginTop: 4,
                    fontSize: 14, lineHeight: 1.4,
                    wordBreak: 'break-word', whiteSpace: 'pre-wrap',
                    ...bubbleStyle,
                  }}>{msg.text}</div>
                )}
              </div>
            );
          }

          // Audio / voice note
          if (mt === 'audio' && mediaUrl) {
            return (
              <div style={{
                padding: '8px 12px',
                ...bubbleStyle,
              }}>
                <AudioPlayer
                  url={mediaUrl}
                  duration={msg.media_duration}
                  own={own}
                  T={T}
                  priColor={priColor}
                />
              </div>
            );
          }

          // Generic file
          if (mt === 'file' && mediaUrl) {
            return (
              <a
                href={mediaUrl}
                target="_blank" rel="noreferrer"
                download={msg.media_name || undefined}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: '10px 14px',
                  textDecoration: 'none',
                  color: own ? '#fff' : T.txt,
                  ...bubbleStyle,
                  minWidth: 200, maxWidth: 300,
                }}
              >
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: own ? 'rgba(255,255,255,0.22)' : (T.cardBg || '#fff'),
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  <FileText size={18} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{
                    fontSize: 13, fontWeight: 600,
                    overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {msg.media_name || 'File'}
                  </div>
                  <div style={{
                    fontSize: 11, opacity: 0.8, marginTop: 2,
                  }}>
                    {formatBytes(msg.media_size)}
                  </div>
                </div>
                <Download size={16} style={{ opacity: 0.8, flexShrink: 0 }} />
              </a>
            );
          }

          // Plain text
          return (
            <div style={{
              padding: '10px 14px',
              fontSize: 14, lineHeight: 1.4,
              wordBreak: 'break-word', whiteSpace: 'pre-wrap',
              ...bubbleStyle,
            }}>
              {msg.text}
            </div>
          );
        })()}
        <div
          style={{
            fontSize: 10,
            color: T.sub,
            marginTop: 3,
            textAlign: own ? 'right' : 'left',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
            justifyContent: own ? 'flex-end' : 'flex-start',
          }}
        >
          {msg.edited_at && !msg.is_deleted && <span>Edited ·</span>}
          <span>{clockTime(msg.created_at)}</span>
        </div>

        {/* Action menu for own, non-deleted messages */}
        {own && !msg.is_deleted && (
          <button
            onClick={() => setMenuOpen((v) => !v)}
            style={{
              position: 'absolute',
              top: 4,
              left: -30,
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              color: T.sub,
              padding: 4,
              opacity: 0.6,
            }}
            onMouseEnter={(e) => (e.currentTarget.style.opacity = '1')}
            onMouseLeave={(e) => (e.currentTarget.style.opacity = '0.6')}
            title="Options"
          >
            <MoreVertical size={16} />
          </button>
        )}

        {menuOpen && (
          <>
            <div
              onClick={() => setMenuOpen(false)}
              style={{ position: 'fixed', inset: 0, zIndex: 20 }}
            />
            <div
              style={{
                position: 'absolute',
                top: 28,
                // Own messages are right-aligned; anchor the menu to the bubble's
                // right edge so short messages don't push the dropdown off-screen.
                right: 0,
                background: T.cardBg,
                border: `1px solid ${T.border}`,
                borderRadius: 10,
                boxShadow: '0 6px 20px rgba(0,0,0,0.2)',
                zIndex: 21,
                overflow: 'hidden',
                minWidth: 130,
                maxWidth: 'calc(100vw - 24px)',
              }}
            >
              {msg.is_editable && (msg.media_type === 'text' || !msg.media_type) && (
                <button
                  onClick={() => { setMenuOpen(false); onEdit(msg); }}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 8,
                    width: '100%', padding: '10px 14px',
                    border: 'none', background: 'none', cursor: 'pointer',
                    color: T.txt, fontSize: 13, textAlign: 'left',
                  }}
                >
                  <Edit3 size={14} /> Edit
                </button>
              )}
              <button
                onClick={() => { setMenuOpen(false); onDelete(msg); }}
                style={{
                  display: 'flex', alignItems: 'center', gap: 8,
                  width: '100%', padding: '10px 14px',
                  border: 'none', background: 'none', cursor: 'pointer',
                  color: '#ef4444', fontSize: 13, textAlign: 'left',
                }}
              >
                <Trash2 size={14} /> Delete
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
});

// ─── Composer ─────────────────────────────────────────────────────────────────
// Isolated so typing does NOT re-render the thread + message list.
const MAX_UPLOAD_BYTES = 25 * 1024 * 1024;

const Composer = memo(function Composer({
  onSend, onSendMedia, onEditSubmit, onCancelEdit, editing, T, priColor, inputRef,
}) {
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [attachment, setAttachment] = useState(null); // { file, kind, previewUrl, name, size }
  const [menuOpen, setMenuOpen] = useState(false);

  // Voice recording state
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const mediaRecRef = useRef(null);
  const recChunksRef = useRef([]);
  const recStartRef = useRef(0);
  const recTickRef = useRef(null);
  const streamRef = useRef(null);

  const imageInputRef = useRef(null);
  const fileInputRef = useRef(null);

  // When entering edit mode, prefill text. When leaving, clear.
  const editingId = editing?.id || null;
  useEffect(() => {
    if (editing) {
      setText(editing.text || '');
      setAttachment(null);
      setTimeout(() => inputRef.current?.focus(), 0);
    } else {
      setText('');
    }
  }, [editingId]); // eslint-disable-line react-hooks/exhaustive-deps

  // Cleanup preview URL and recorder on unmount
  useEffect(() => {
    return () => {
      if (attachment?.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
      if (recTickRef.current) clearInterval(recTickRef.current);
      if (streamRef.current) streamRef.current.getTracks().forEach((t) => t.stop());
    };
  }, []); // eslint-disable-line

  const pickAttachment = (kind) => {
    setMenuOpen(false);
    if (kind === 'image') imageInputRef.current?.click();
    else fileInputRef.current?.click();
  };

  const handleFilePicked = (e, kind) => {
    const f = e.target.files?.[0];
    e.target.value = ''; // allow picking the same file again later
    if (!f) return;
    if (f.size > MAX_UPLOAD_BYTES) {
      alert(`File too large. Max ${Math.round(MAX_UPLOAD_BYTES / 1024 / 1024)} MB.`);
      return;
    }
    let resolvedKind = kind;
    if (kind === 'any') {
      if (f.type.startsWith('image/')) resolvedKind = 'image';
      else if (f.type.startsWith('video/')) resolvedKind = 'video';
      else if (f.type.startsWith('audio/')) resolvedKind = 'audio';
      else resolvedKind = 'file';
    }
    const previewUrl = (resolvedKind === 'image' || resolvedKind === 'video')
      ? URL.createObjectURL(f) : null;
    if (attachment?.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
    setAttachment({
      file: f, kind: resolvedKind, previewUrl,
      name: f.name, size: f.size,
    });
  };

  const clearAttachment = () => {
    if (attachment?.previewUrl) URL.revokeObjectURL(attachment.previewUrl);
    setAttachment(null);
  };

  // ── Voice recording ──────────────────────────────────────────────────────
  const startRecording = async () => {
    if (recording) return;
    if (!navigator.mediaDevices?.getUserMedia || typeof MediaRecorder === 'undefined') {
      alert('Voice recording is not supported on this device/browser.');
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      // Pick a reasonable mime type that most backends accept
      let mime = '';
      if (MediaRecorder.isTypeSupported('audio/webm;codecs=opus')) mime = 'audio/webm;codecs=opus';
      else if (MediaRecorder.isTypeSupported('audio/webm')) mime = 'audio/webm';
      else if (MediaRecorder.isTypeSupported('audio/mp4')) mime = 'audio/mp4';
      const rec = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
      recChunksRef.current = [];
      rec.ondataavailable = (e) => { if (e.data && e.data.size > 0) recChunksRef.current.push(e.data); };
      rec.start();
      mediaRecRef.current = rec;
      recStartRef.current = Date.now();
      setRecSecs(0);
      setRecording(true);
      recTickRef.current = setInterval(() => {
        setRecSecs(Math.floor((Date.now() - recStartRef.current) / 1000));
      }, 250);
    } catch (err) {
      console.error('mic error', err);
      alert('Could not access microphone. Please allow microphone access.');
    }
  };

  const MIN_RECORD_MS = 400; // below this = treat as accidental tap, cancel silently

  const stopRecording = (cancel = false) => {
    const rec = mediaRecRef.current;
    if (!rec) return;
    const durationMs = Date.now() - recStartRef.current;
    // Too-short holds are treated as accidental taps — cancel quietly
    const tooShort = !cancel && durationMs < MIN_RECORD_MS;
    if (tooShort) cancel = true;
    const cleanup = () => {
      if (recTickRef.current) { clearInterval(recTickRef.current); recTickRef.current = null; }
      if (streamRef.current) { streamRef.current.getTracks().forEach((t) => t.stop()); streamRef.current = null; }
      mediaRecRef.current = null;
      setRecording(false);
      setRecSecs(0);
    };

    rec.onstop = async () => {
      try {
        if (cancel) { cleanup(); return; }
        const chunks = recChunksRef.current;
        if (!chunks.length) { cleanup(); return; }
        const mime = rec.mimeType || 'audio/webm';
        const blob = new Blob(chunks, { type: mime });
        const ext = mime.includes('mp4') ? 'm4a' : (mime.includes('ogg') ? 'ogg' : 'webm');
        const file = new File([blob], `voice-${Date.now()}.${ext}`, { type: mime });
        cleanup();
        // Send immediately — voice notes are fire-and-send in Instagram
        setSending(true);
        try {
          await onSendMedia({
            file, kind: 'audio',
            duration: durationMs / 1000,
            name: file.name, size: file.size,
          });
        } finally {
          setSending(false);
        }
      } catch (err) {
        console.error(err);
        cleanup();
      }
    };
    try { rec.stop(); } catch { cleanup(); }
  };

  const submit = async (e) => {
    e?.preventDefault?.();
    if (sending) return;
    const trimmed = text.trim();

    // Edit mode: text only
    if (editing) {
      if (!trimmed) return;
      setSending(true);
      try {
        const ok = await onEditSubmit(editing, trimmed);
        if (ok) setText('');
      } finally { setSending(false); }
      return;
    }

    // With attachment: send media (with optional caption)
    if (attachment) {
      setSending(true);
      const toSend = attachment;
      const caption = trimmed;
      // Optimistic clear
      setText('');
      setAttachment(null);
      try {
        await onSendMedia({
          file: toSend.file, kind: toSend.kind,
          name: toSend.name, size: toSend.size,
          caption,
        });
      } finally { setSending(false); }
      return;
    }

    // Plain text
    if (!trimmed) return;
    setSending(true);
    try {
      setText('');
      await onSend(trimmed);
    } finally { setSending(false); }
  };

  const canSend = !!(attachment || text.trim()) && !sending;
  const showMicButton = !editing && !attachment && !text.trim();

  return (
    <>
      {/* Attachment preview strip */}
      {attachment && (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '8px 12px',
          background: T.cardBg,
          borderTop: `1px solid ${T.border}`,
        }}>
          {attachment.kind === 'image' && attachment.previewUrl && (
            <img src={attachment.previewUrl} alt="preview"
                 style={{ width: 52, height: 52, borderRadius: 8, objectFit: 'cover', background: '#000' }} />
          )}
          {attachment.kind === 'video' && attachment.previewUrl && (
            <video src={attachment.previewUrl} muted
                   style={{ width: 52, height: 52, borderRadius: 8, objectFit: 'cover', background: '#000' }} />
          )}
          {(attachment.kind === 'file' || attachment.kind === 'audio') && (
            <div style={{
              width: 52, height: 52, borderRadius: 8,
              background: T.bg, color: T.txt,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              flexShrink: 0,
            }}>
              {attachment.kind === 'audio' ? <Mic size={22} /> : <FileText size={22} />}
            </div>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: 13, fontWeight: 600, color: T.txt,
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>{attachment.name}</div>
            <div style={{ fontSize: 11, color: T.sub, marginTop: 2 }}>
              {formatBytes(attachment.size)}
            </div>
          </div>
          <button type="button" onClick={clearAttachment}
                  style={{ background: 'none', border: 'none', cursor: 'pointer', color: T.sub, padding: 4, display: 'flex' }}
                  aria-label="Remove attachment">
            <X size={18} />
          </button>
        </div>
      )}

      {/* Editing banner */}
      {editing && (
        <div style={{
          padding: '8px 14px', background: T.cardBg,
          borderTop: `1px solid ${T.border}`,
          display: 'flex', alignItems: 'center', gap: 10,
          fontSize: 13, color: T.sub,
        }}>
          <Edit3 size={14} /> Editing message
          <button type="button" onClick={onCancelEdit} style={{
            marginLeft: 'auto', background: 'none', border: 'none',
            color: T.sub, cursor: 'pointer', padding: 4, display: 'flex',
          }}>
            <X size={16} />
          </button>
        </div>
      )}

      {/* Recording UI replaces the normal composer */}
      {recording ? (
        <div style={{
          display: 'flex', alignItems: 'center', gap: 10,
          padding: '12px 14px',
          paddingBottom: 'max(12px, env(safe-area-inset-bottom))',
          borderTop: `1px solid ${T.border}`,
          background: T.cardBg, flexShrink: 0,
        }}>
          <button
            type="button"
            onClick={() => stopRecording(true)}
            style={{
              background: T.bg, border: 'none', cursor: 'pointer',
              width: 38, height: 38, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#ef4444', flexShrink: 0,
            }}
            aria-label="Cancel recording"
          >
            <Trash size={18} />
          </button>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', gap: 10 }}>
            <div style={{
              width: 10, height: 10, borderRadius: '50%',
              background: '#ef4444',
              animation: 'msg-rec-pulse 1s ease-in-out infinite',
            }} />
            <style>{`@keyframes msg-rec-pulse {0%,100%{opacity:1}50%{opacity:.4}}`}</style>
            <div style={{ fontSize: 14, fontWeight: 600, color: T.txt }}>
              Recording… {formatDuration(recSecs)}
            </div>
            <div style={{ fontSize: 11, color: T.sub, marginLeft: 8 }}>
              Release to send
            </div>
          </div>
          <button
            type="button"
            onClick={() => stopRecording(false)}
            style={{
              background: priColor, border: 'none', cursor: 'pointer',
              width: 42, height: 42, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: '#fff', flexShrink: 0,
            }}
            aria-label="Send voice message"
          >
            <Send size={18} />
          </button>
        </div>
      ) : (
        <form
          onSubmit={submit}
          style={{
            display: 'flex', alignItems: 'center', gap: 6,
            padding: '10px 10px',
            paddingBottom: 'max(10px, env(safe-area-inset-bottom))',
            borderTop: `1px solid ${T.border}`,
            background: T.cardBg, flexShrink: 0,
          }}
        >
          {/* Attachment menu (hidden during edit) */}
          {!editing && (
            <div style={{ position: 'relative', flexShrink: 0 }}>
              <button
                type="button"
                onClick={() => setMenuOpen((v) => !v)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer',
                  width: 38, height: 38, borderRadius: '50%',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  color: T.sub,
                }}
                aria-label="Attach"
              >
                <Paperclip size={20} />
              </button>
              {menuOpen && (
                <>
                  <div onClick={() => setMenuOpen(false)}
                       style={{ position: 'fixed', inset: 0, zIndex: 30 }} />
                  <div style={{
                    position: 'absolute', bottom: 46, left: 0, zIndex: 31,
                    background: T.cardBg, border: `1px solid ${T.border}`,
                    borderRadius: 12, boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
                    overflow: 'hidden', minWidth: 170,
                  }}>
                    <button type="button" onClick={() => pickAttachment('image')}
                            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                                     padding: '10px 14px', border: 'none', background: 'none',
                                     cursor: 'pointer', color: T.txt, fontSize: 14, textAlign: 'left' }}>
                      <ImageIcon size={16} /> Photo or video
                    </button>
                    <button type="button" onClick={() => pickAttachment('file')}
                            style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%',
                                     padding: '10px 14px', border: 'none', background: 'none',
                                     cursor: 'pointer', color: T.txt, fontSize: 14, textAlign: 'left' }}>
                      <FileText size={16} /> File
                    </button>
                  </div>
                </>
              )}
              <input
                ref={imageInputRef} type="file" accept="image/*,video/*"
                style={{ display: 'none' }}
                onChange={(e) => handleFilePicked(e, 'any')}
              />
              <input
                ref={fileInputRef} type="file"
                style={{ display: 'none' }}
                onChange={(e) => handleFilePicked(e, 'any')}
              />
            </div>
          )}

          <input
            ref={inputRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            placeholder={editing
              ? 'Edit your message…'
              : (attachment ? 'Add a caption…' : 'Message…')}
            autoComplete="off"
            style={{
              flex: 1,
              padding: '11px 16px',
              borderRadius: 24,
              border: `1px solid ${T.border}`,
              background: T.bg,
              color: T.txt,
              fontSize: 16,
              outline: 'none',
              minWidth: 0,
            }}
          />

          {showMicButton ? (
            <button
              type="button"
              onPointerDown={(e) => {
                // Avoid the synthetic click firing after pointerup
                e.preventDefault();
                try { e.currentTarget.setPointerCapture?.(e.pointerId); } catch {}
                startRecording();
              }}
              onPointerUp={(e) => {
                try { e.currentTarget.releasePointerCapture?.(e.pointerId); } catch {}
                stopRecording(false);
              }}
              onPointerCancel={() => stopRecording(true)}
              onPointerLeave={(e) => {
                // Only cancel if the pointer is actively being held AND not captured.
                // With pointer capture, leave won't fire — so this is a safety net.
                if (e.buttons > 0) stopRecording(true);
              }}
              onContextMenu={(e) => e.preventDefault()}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                width: 42, height: 42, borderRadius: '50%',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                color: priColor, flexShrink: 0,
                touchAction: 'none',
                WebkitUserSelect: 'none', userSelect: 'none',
              }}
              aria-label="Hold to record voice message"
              title="Hold to record"
            >
              <Mic size={22} />
            </button>
          ) : (
            <button
              type="submit"
              disabled={!canSend}
              style={{
                background: canSend ? priColor : T.border,
                color: '#fff',
                border: 'none',
                width: 42, height: 42, borderRadius: '50%',
                cursor: canSend ? 'pointer' : 'not-allowed',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
                transition: 'background 0.15s',
              }}
              aria-label="Send"
            >
              <Send size={18} />
            </button>
          )}
        </form>
      )}
    </>
  );
});

// ─── Thread View (single conversation) ────────────────────────────────────────
function ThreadView({ conversation, onBack, user, T, priColor, onShowProfile, onMessageChanged }) {
  const [messages, setMessages] = useState([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState(null);
  const scrollRef = useRef(null);
  const inputRef = useRef(null);
  const pendingRef = useRef(0); // count of in-flight sends; pauses poll-replace

  const convId = conversation.id;
  const other = conversation.other_user;

  const scrollToBottom = (smooth = true) => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTo({ top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto' });
  };

  const fetchMessages = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      // 60s timeout tolerates Render free-tier cold starts (~30-60s wake).
      // A browser-aborted fetch surfaces as a misleading "CORS error" in the
      // console, so we'd rather wait than fail fast.
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Request timeout')), 60000)
      );
      
      const data = await Promise.race([
        api.request(`/messages/conversations/${convId}/messages/`),
        timeoutPromise
      ]);
      
      const arr = Array.isArray(data) ? data : [];
      setMessages((prev) => {
        // If a send is in flight, don't clobber optimistic messages
        if (pendingRef.current > 0 && prev.length > arr.length) {
          // Keep optimistic messages at the end
          const optimistic = prev.slice(arr.length);
          return [...arr, ...optimistic];
        }
        return arr;
      });
      // Mark as read (fire and forget)
      api.request(`/messages/conversations/${convId}/read/`, { method: 'POST' }).catch(() => {});
    } catch (e) {
      console.error('fetchMessages error', e);
    } finally {
      setLoading(false);
    }
  }, [convId]);

  useEffect(() => { fetchMessages(false); }, [fetchMessages]);

  // Poll every 30 seconds for new messages while thread is open (reduced frequency)
  useEffect(() => {
    if (!convId) return;
    const id = setInterval(() => fetchMessages(true), 30000); // 30 seconds to reduce network load
    return () => clearInterval(id);
  }, [convId, fetchMessages]);

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    if (!loading) scrollToBottom(false);
  }, [messages.length, loading]);

  // Send text message
  const handleSend = async (text) => {
    try {
      pendingRef.current += 1;
      const sent = await api.request(`/messages/conversations/${convId}/messages/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      });
      setMessages((prev) => [...prev, sent]);
      scrollToBottom(false);
      onMessageChanged();
    } catch (e) {
      console.error('Send error', e);
    } finally {
      pendingRef.current -= 1;
    }
  };

  // Send media message
  const handleSendMedia = async ({ file, kind, name, size, duration, caption }) => {
    try {
      pendingRef.current += 1;
      const formData = new FormData();
      formData.append('media', file);
      formData.append('media_type', kind);
      if (caption) formData.append('text', caption);
      if (duration) formData.append('media_duration', duration);
      
      const sent = await api.request(`/messages/conversations/${convId}/messages/`, {
        method: 'POST',
        body: formData,
      });
      setMessages((prev) => [...prev, sent]);
      scrollToBottom(false);
      onMessageChanged();
    } catch (e) {
      console.error('Send media error', e);
    } finally {
      pendingRef.current -= 1;
    }
  };

  // Edit message
  const handleEditSubmit = async (msg, newText) => {
    try {
      await api.request(`/messages/${msg.id}/`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: newText }),
      });
      setMessages((prev) => prev.map(m => m.id === msg.id ? { ...m, text: newText, edited_at: new Date().toISOString() } : m));
      setEditing(null);
      onMessageChanged();
      return true;
    } catch (e) {
      console.error('Edit error', e);
      return false;
    }
  };

  // Delete message
  const handleDelete = async (msg) => {
    try {
      await api.request(`/messages/${msg.id}/`, { method: 'DELETE' });
      setMessages((prev) => prev.map(m => m.id === msg.id ? { ...m, is_deleted: true, text: '' } : m));
      onMessageChanged();
    } catch (e) {
      console.error('Delete error', e);
    }
  };

  return (
    <>
      {/* Thread header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: 12,
        padding: '12px 16px', borderBottom: `1px solid ${T.border}`,
        background: T.cardBg, flexShrink: 0,
      }}>
        <button onClick={onBack} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: T.txt, padding: 6, display: 'flex',
        }}>
          <ChevronLeft size={22} />
        </button>
        <Avatar user={other} size={40} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 15, fontWeight: 700, color: T.txt,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {other?.username || 'Unknown'}
          </div>
          <div style={{ fontSize: 12, color: T.sub }}>
            {other?.first_name && other?.last_name ? `${other.first_name} ${other.last_name}` : ''}
          </div>
        </div>
        <button onClick={() => onShowProfile?.(other)} style={{
          background: 'none', border: 'none', cursor: 'pointer',
          color: T.txt, padding: 6, display: 'flex',
        }}>
          <Edit3 size={18} />
        </button>
      </div>

      {/* Messages list */}
      <div ref={scrollRef} style={{
        flex: 1, overflowY: 'auto', padding: '16px 12px',
        WebkitOverflowScrolling: 'touch', overscrollBehavior: 'contain',
      }}>
        {loading ? (
          <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 16 }}>
            {[1, 2, 3].map(i => (
              <div key={i} style={{
                display: 'flex',
                flexDirection: i % 2 === 0 ? 'row' : 'row-reverse',
                gap: 8,
              }}>
                <div style={{
                  width: 40, height: 40, borderRadius: '50%',
                  background: T.border,
                  flexShrink: 0,
                }} />
                <div style={{
                  maxWidth: '70%',
                  height: 40,
                  background: T.border,
                  borderRadius: 18,
                }} />
              </div>
            ))}
          </div>
        ) : messages.length === 0 ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.sub }}>
            No messages yet. Start the conversation!
          </div>
        ) : (
          messages.map((msg) => (
            <MessageBubble
              key={msg.id}
              msg={{
                ...msg,
                is_own: msg.is_own || msg.sender_id === user?.id || msg.sender?.id === user?.id,
              }}
              T={T}
              onEdit={setEditing}
              onDelete={handleDelete}
              priColor={priColor}
            />
          ))
        )}
      </div>

      {/* Composer */}
      <Composer
        onSend={handleSend}
        onSendMedia={handleSendMedia}
        onEditSubmit={handleEditSubmit}
        onCancelEdit={() => setEditing(null)}
        editing={editing}
        T={T}
        priColor={priColor}
        inputRef={inputRef}
      />
    </>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
function ConvRow({ conv, active, currentUserId, onClick, T }) {
  const other = conv.other_user;
  const isOwn = conv.last_message?.sender === currentUserId;
  
  return (
    <div
      onClick={onClick}
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        padding: '12px 16px',
        cursor: 'pointer',
        background: active ? `${T.pri}15` : 'transparent',
        borderLeft: active ? `3px solid ${T.pri}` : '3px solid transparent',
        transition: 'background 0.15s',
      }}
      onMouseEnter={(e) => { if (!active) e.currentTarget.style.background = T.bg; }}
      onMouseLeave={(e) => { if (!active) e.currentTarget.style.background = 'transparent'; }}
    >
      <Avatar user={other} size={48} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          marginBottom: 2,
        }}>
          <div style={{
            fontSize: 15, fontWeight: 600, color: T.txt,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>
            {other?.username || 'Unknown'}
          </div>
          <div style={{ fontSize: 12, color: T.sub, whiteSpace: 'nowrap' }}>
            {relTime(conv.last_message?.created_at)}
          </div>
        </div>
        <div style={{
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }}>
          <div style={{
            fontSize: 13, color: T.sub,
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            maxWidth: '200px',
          }}>
            {isOwn && 'You: '}{conv.last_message?.text || 'Media'}
          </div>
          {conv.unread_count > 0 && (
            <div style={{
              background: T.pri, color: '#fff', borderRadius: '50%',
              width: 20, height: 20, display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: 11, fontWeight: 700, minWidth: 20,
            }}>
              {conv.unread_count > 9 ? '9+' : conv.unread_count}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export function MessagesPage({ user, onShowProfile, onRequireAuth }) {
  const { colors: T } = useTheme();
  const priColor = T.priGradient || T.pri;
  
  // Redirect to login if not authenticated
  useEffect(() => {
    if (!user) {
      onRequireAuth?.();
    }
  }, [user, onRequireAuth]);
  
  if (!user) {
    return null; // Don't render while redirecting
  }
  
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);
  const [conversations, setConversations] = useState([]);
  const [filteredConversations, setFilteredConversations] = useState([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [activeConv, setActiveConv] = useState(null);
  const [showNewChat, setShowNewChat] = useState(false);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 1024);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Stable fetcher — never re-created, so polling interval stays stable.
  const fetchConversations = useCallback(async (silent = false) => {
    try {
      if (!silent) setLoading(true);
      
      // 60s timeout tolerates Render free-tier cold starts (~30-60s wake).
      const timeoutPromise = new Promise((_, reject) => 
        setTimeout(() => reject(new Error('Request timeout')), 60000)
      );
      
      const data = await Promise.race([
        api.request('/messages/conversations/'),
        timeoutPromise
      ]);
      
      const arr = Array.isArray(data) ? data : [];
      setConversations((prev) => {
        // Shallow compare: same length + same ids + same last_message snapshot + same unread
        if (prev.length === arr.length && 
            prev.every((p, i) => p.id === arr[i]?.id && 
                              p.last_message?.text === arr[i]?.last_message?.text &&
                              p.unread_count === arr[i]?.unread_count)) {
          return prev; // No change, skip update
        }
        return arr;
      });
      
      // Update filtered conversations when conversations change
      if (searchQuery.trim()) {
        const filtered = arr.filter(c => 
          c.other_user?.username?.toLowerCase().includes(searchQuery.toLowerCase())
        );
        setFilteredConversations(filtered);
      } else {
        setFilteredConversations(arr);
      }
      // Keep activeConv meta in sync, but do NOT force a reference change if unchanged
      setActiveConv((curr) => {
        if (!curr) return curr;
        const fresh = arr.find((c) => c.id === curr.id);
        if (!fresh) return curr;
        if (fresh.unread_count === curr.unread_count
            && (fresh.last_message?.id || null) === (curr.last_message?.id || null)
            && (fresh.last_message?.text || '') === (curr.last_message?.text || '')) {
          return curr;
        }
        return fresh;
      });
    } catch (e) {
      console.error('fetchConversations', e);
    } finally {
      if (!silent) setLoading(false);
    }
  }, []);

  useEffect(() => { fetchConversations(false); }, [fetchConversations]);
  useEffect(() => {
    // Disable polling to reduce network load - refresh on tab switch instead
    const id = setInterval(() => fetchConversations(true), 120000); // 2 minutes polling
    return () => clearInterval(id);
  }, [fetchConversations]);
  
  // Filter conversations based on search query
  useEffect(() => {
    if (searchQuery.trim()) {
      const filtered = conversations.filter(c => 
        c.other_user?.username?.toLowerCase().includes(searchQuery.toLowerCase())
      );
      setFilteredConversations(filtered);
    } else {
      setFilteredConversations(conversations);
    }
  }, [searchQuery, conversations]);

  // Stable callback for ThreadView — prevents it from re-rendering every poll tick
  const onMessageChanged = useCallback(() => { fetchConversations(true); }, [fetchConversations]);

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
      alert(e?.error || 'Failed to start conversation');
    }
  };

  // On mobile, push a history entry when opening a thread so hardware/browser
  // back closes the thread instead of leaving the messages page.
  const openConv = useCallback((c) => {
    setActiveConv(c);
    if (window.innerWidth <= 1024) {
      try { window.history.pushState({ _msgThread: true }, '', window.location.href); } catch {}
    }
  }, []);

  const closeThread = useCallback(() => {
    setActiveConv(null);
    // If we pushed a state for this thread, pop it so forward nav isn't littered
    try {
      if (window.history.state && window.history.state._msgThread) {
        window.history.back();
      }
    } catch {}
  }, []);

  useEffect(() => {
    const onPop = () => {
      // If thread is open and user pressed browser back, close thread instead.
      setActiveConv((curr) => (curr ? null : curr));
    };
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  // ── Render ─────────────────────────────────────────────────────────────────
  const inbox = (
    <div style={{
      display: 'flex', flexDirection: 'column',
      width: isMobile ? '100%' : 360,
      borderRight: isMobile ? 'none' : `1px solid ${T.border}`,
      background: T.cardBg,
      height: '100%',
      flexShrink: 0,
    }}>
      {/* Inbox header */}
      <div style={{
        display: 'flex', flexDirection: 'column', gap: 12,
        padding: '16px 18px', borderBottom: `1px solid ${T.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>
            Messages
          </div>
          <button
            onClick={() => setShowNewChat(true)}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              color: T.txt, padding: 6, display: 'flex',
            }}
            aria-label="New message"
            title="New message"
          >
            <PenSquare size={22} />
          </button>
        </div>
        {/* Search input */}
        <div style={{ position: 'relative' }}>
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search conversations..."
            style={{
              width: '100%',
              padding: '10px 12px 10px 36px',
              borderRadius: 20,
              border: `1px solid ${T.border}`,
              background: T.bg,
              color: T.txt,
              fontSize: 14,
              outline: 'none',
            }}
          />
          <Search size={16} style={{
            position: 'absolute', left: 12, top: '50%',
            transform: 'translateY(-50%)', color: T.sub,
          }} />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              style={{
                position: 'absolute', right: 12, top: '50%',
                transform: 'translateY(-50%)',
                background: 'none', border: 'none',
                cursor: 'pointer', color: T.sub, padding: 2,
              }}
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>
      {/* List */}
      <div style={{
        flex: 1, overflowY: 'auto', paddingBottom: 12,
        minHeight: 0,
        WebkitOverflowScrolling: 'touch',
        overscrollBehavior: 'contain',
      }}>
        {loading ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.sub, fontSize: 13 }}>Loading…</div>
        ) : filteredConversations.length === 0 && searchQuery ? (
          <div style={{ padding: 24, textAlign: 'center', color: T.sub, fontSize: 13 }}>
            No conversations match "{searchQuery}"
          </div>
        ) : filteredConversations.length === 0 ? (
          <div style={{
            padding: 24, display: 'flex', flexDirection: 'column',
            alignItems: 'center', gap: 10, color: T.sub, marginTop: 24,
          }}>
            <div style={{ fontSize: 16, fontWeight: 700, color: T.txt }}>No messages yet</div>
            <div style={{ fontSize: 13, textAlign: 'center' }}>
              Start a conversation with anyone on the platform.
            </div>
            <button
              onClick={() => setShowNewChat(true)}
              style={{
                marginTop: 10, background: priColor, color: '#fff',
                border: 'none', padding: '9px 20px', borderRadius: 22,
                fontWeight: 700, fontSize: 13, cursor: 'pointer',
              }}
            >
              Send message
            </button>
          </div>
        ) : (
          <div style={{ padding: '4px 0' }}>
            {filteredConversations.map((c) => (
              <ConvRow
                key={c.id}
                conv={c}
                active={activeConv?.id === c.id}
                currentUserId={user?.id}
                onClick={() => openConv(c)}
                T={T}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div style={{
      display: 'flex',
      height: '100%',
      width: '100%',
      background: T.bg, overflow: 'hidden',
      position: 'relative',
    }}>
      {/* Mobile: inbox in flow; thread as a fixed full-viewport overlay above bottom nav */}
      {isMobile ? (
        <>
          {inbox}
          {activeConv && (
            <div style={{
              position: 'fixed',
              top: 0,
              left: 0,
              right: 0,
              bottom: 68, // Account for AppShell bottom nav height (68px)
              width: '100vw',
              background: T.bg,
              zIndex: 1500, // above AppShell bottom nav (1000)
              display: 'flex',
              flexDirection: 'column',
            }}>
              <ThreadView
                conversation={activeConv}
                onBack={closeThread}
                user={user}
                T={T}
                priColor={priColor}
                onShowProfile={onShowProfile}
                onMessageChanged={onMessageChanged}
              />
            </div>
          )}
        </>
      ) : (
        // Desktop: side-by-side
        <>
          {inbox}
          <div style={{ 
            flex: 1, 
            minWidth: 0, 
            height: '100%',
            display: 'flex',
            flexDirection: 'column'
          }}>
            {activeConv ? (
              <ThreadView
                conversation={activeConv}
                onBack={closeThread}
                user={user}
                T={T}
                priColor={priColor}
                onShowProfile={onShowProfile}
                onMessageChanged={onMessageChanged}
              />
            ) : (
              <div style={{
                height: '100%', display: 'flex', flexDirection: 'column',
                alignItems: 'center', justifyContent: 'center', padding: 24,
                color: T.sub,
              }}>
                <div style={{
                  width: 96, height: 96, borderRadius: '50%',
                  border: `2px solid ${T.border}`,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: 16,
                }}>
                  <Send size={42} color={T.sub} strokeWidth={1.5} />
                </div>
                <div style={{ fontSize: 20, fontWeight: 700, color: T.txt, marginBottom: 6 }}>
                  Your messages
                </div>
                <div style={{ fontSize: 14, marginBottom: 14 }}>
                  Send a message to start a conversation.
                </div>
                <button
                  onClick={() => setShowNewChat(true)}
                  style={{
                    background: priColor, color: '#fff',
                    border: 'none', padding: '10px 22px', borderRadius: 24,
                    fontWeight: 700, fontSize: 14, cursor: 'pointer',
                  }}
                >
                  Send message
                </button>
              </div>
            )}
          </div>
        </>
      )}

      {showNewChat && (
        <NewChatModal
          onClose={() => setShowNewChat(false)}
          onSelectUser={handleStartChat}
          T={T}
        />
      )}
    </div>
  );
}




