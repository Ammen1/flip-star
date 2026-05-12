import { useState, useRef } from "react";
import { Heart, MessageCircle, Share2, Bookmark, MoreHorizontal } from "lucide-react";
import config from "../config";
import { useLegacyT } from "../contexts/ThemeContext";

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

// Mirrors overlayCSS from EnhancedPostPage
const overlayCSS = (ov) => {
  const base = { 
    fontWeight: 800, 
    fontSize: `${ov.fontSize || 22}px`, 
    color: ov.color || '#fff', 
    textAlign: ov.align || 'center', 
    whiteSpace: 'pre-wrap', 
    maxWidth: '260px', 
    display: 'inline-block',
    lineHeight: 1.2,
    userSelect: 'none'
  };
  switch (ov.style) {
    case 'plain':     return { ...base, textShadow: '0 2px 8px rgba(0,0,0,0.9)', background: 'transparent', padding: '4px 6px', borderRadius: 0 };
    case 'outline':   return { ...base, textShadow: 'none', WebkitTextStroke: `2px ${ov.color}`, color: 'transparent', background: 'transparent', padding: '4px 6px' };
    case 'neon':      return { ...base, textShadow: `0 0 8px ${ov.color}, 0 0 20px ${ov.color}, 0 0 40px ${ov.color}`, background: 'transparent', padding: '4px 6px' };
    case 'highlight': return { ...base, background: ov.color, color: (ov.color === '#fff' || ov.color === '#ffffff') ? '#000' : '#fff', padding: '4px 12px', borderRadius: 6 };
    default:          return { ...base, background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(4px)', padding: '4px 10px', borderRadius: 8, textShadow: '0 1px 4px rgba(0,0,0,0.6)' };
  }
};

const LONG_PRESS_MS = 500;

export function VideoCard({ video, onLike, onComment, onShare }) {
  const T = useLegacyT();
  const [liked, setLiked] = useState(false);
  const [showComments, setShowComments] = useState(false);
  const [showMenu, setShowMenu] = useState(false);
  const [toast, setToast] = useState('');
  const longPressTimer = useRef(null);

  // Parse overlays from JSON string
  let overlays = [];
  try { if (video?.overlay_text) overlays = JSON.parse(video.overlay_text); } catch {}

  const handleLike = () => { setLiked(!liked); onLike?.(); };

  const showToast = (msg) => {
    setToast(msg);
    setTimeout(() => setToast(''), 2200);
  };

  // Long-press handlers
  const onPressStart = (e) => {
    longPressTimer.current = setTimeout(() => {
      setShowMenu(true);
      if (navigator.vibrate) navigator.vibrate(40);
    }, LONG_PRESS_MS);
  };
  const onPressEnd = () => { clearTimeout(longPressTimer.current); };

  const handleCopyLink = () => {
    const url = `${window.location.origin}/post/${video.id}`;
    navigator.clipboard?.writeText(url).then(() => showToast('🔗 Link copied!')).catch(() => showToast('Could not copy'));
    setShowMenu(false);
  };

  const handleShare = () => {
    const url = `${window.location.origin}/post/${video.id}`;
    if (navigator.share) {
      navigator.share({ title: video.caption || 'Check this out', url }).catch(() => {});
    } else {
      navigator.clipboard?.writeText(url).then(() => showToast('🔗 Link copied!'));
    }
    setShowMenu(false);
  };

  const handleDownload = () => {
    const src = mediaUrl(video.media || video.image);
    if (!src) { showToast('No media to download'); return; }
    const a = document.createElement('a');
    a.href = src; a.download = `flipstar_${video.id}`; a.target = '_blank';
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    showToast('⬇️ Downloading...');
    setShowMenu(false);
  };

  const handleNotInterested = () => { showToast('Got it — fewer like this'); setShowMenu(false); };

  return (
    <div style={{ background: T?.cardBg || '#1A1A1A', borderRadius: 16, overflow: "hidden", marginBottom: 20, position: "relative", display: "flex", flexDirection: "column", maxWidth: 560, border: '1.5px solid rgba(226,179,85,0.22)' }}>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', padding: '6px 10px', gap: 8, flexShrink: 0 }}>
        <div style={{ width: 28, height: 28, minWidth: 28, minHeight: 28, borderRadius: '50%', overflow: 'hidden', background: (T?.pri || '#000') + '30', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 14, border: `1px solid ${(T?.pri || '#000')}20`, flexShrink: 0 }}>
          {video?.avatar ? <img src={mediaUrl(video.avatar)} alt="" style={{ width:'100%', height:'100%', objectFit:'cover' }} /> : '👤'}
        </div>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T?.txt || '#000' }}>
            {video?.creator || "Creator"}
          </div>
          <div style={{ fontSize: 11, color: T?.sub || '#666' }}>@{video?.handle || "handle"}</div>
        </div>
        <button
          onClick={() => setShowMenu(true)}
          style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: T?.sub || '#666', display: 'flex', alignItems: 'center' }}
        >
          <MoreHorizontal size={18} />
        </button>
      </div>

      {/* Media area */}
      <div
        style={{ 
          position: 'relative', 
          width: '100%', 
          background: 'transparent',
          flex: '1 1 auto',
          minHeight: 320,
          maxHeight: 450,
          aspectRatio: '4 / 5',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '0',
          overflow: 'hidden'
        }}
        onMouseDown={onPressStart} 
        onMouseUp={onPressEnd} 
        onMouseLeave={onPressEnd}
        onTouchStart={onPressStart} 
        onTouchEnd={onPressEnd} 
        onTouchCancel={onPressEnd}
      >
        {video?.thumbnail
          ? <img src={mediaUrl(video.thumbnail)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
          : video?.image
            ? <img src={mediaUrl(video.image)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
            : video?.media
              ? <video src={mediaUrl(video.media)} controls playsInline autoPlay muted loop style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              : <div style={{ textAlign:"center", color:"#666", padding: 40 }}><div style={{ fontSize:60 }}>?</div><div>No media</div></div>
        }

        {/* Text overlays rendered from stored JSON */}
        {overlays.map((ov, i) => (
          <div key={i} style={{ position:'absolute', left:`${ov.x}%`, top:`${ov.y}%`, transform:'translate(-50%,-50%)', pointerEvents:'none', zIndex:5 }}>
            <span style={overlayCSS(ov)}>{ov.text}</span>
          </div>
        ))}
      </div>

      {/* Actions + caption */}
      <div style={{ padding: '4px 10px 8px', flexShrink: 0, overflow: 'hidden' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div style={{ display: 'flex', gap: 2 }}>
            {/* Like */}
            <button
              onClick={handleLike}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '4px 6px', borderRadius: 8,
                display: 'flex', alignItems: 'center', gap: 3,
              }}
            >
              <Heart
                size={16}
                fill={liked ? '#EF4444' : 'none'}
                color={liked ? '#EF4444' : T?.txt || '#000'}
              />
              <span style={{ fontSize: 11, color: T?.sub || '#666', fontWeight: 600 }}>{video?.likes || 0}</span>
            </button>
            {/* Comment */}
            <button
              onClick={() => setShowComments(!showComments)}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '4px 6px', borderRadius: 8,
                display: 'flex', alignItems: 'center', gap: 3,
              }}
            >
              <MessageCircle size={16} color={T?.priFallback || '#E2B355'} />
              <span style={{ fontSize: 11, color: T?.priFallback || '#E2B355', fontWeight: 600 }}>{video?.comments || 0}</span>
            </button>
            {/* Share */}
            <button
              onClick={handleShare}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: '4px 6px', borderRadius: 8,
                display: 'flex', alignItems: 'center', gap: 3,
              }}
            >
              <Share2 size={16} color={T?.priFallback || '#E2B355'} />
              <span style={{ fontSize: 11, color: T?.priFallback || '#E2B355', fontWeight: 600 }}>{video?.shares || 0}</span>
            </button>
          </div>
          {/* Save */}
          <button
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: '4px 6px', borderRadius: 8,
            }}
          >
            <Bookmark
              size={16}
              fill={false}
              color={T?.priFallback || '#E2B355'}
            />
          </button>
        </div>

        {/* Caption */}
        {video?.caption && (
          <div
            style={{
              fontSize: 12, color: T?.txt || '#000', marginTop: 4, lineHeight: 1.3,
              display: '-webkit-box',
              WebkitBoxOrient: 'vertical',
              WebkitLineClamp: 2,
              overflow: 'hidden',
              wordBreak: 'break-word',
            }}
          >
            <span style={{ fontWeight: 700 }}>{video?.creator} </span>
            {video?.caption}
          </div>
        )}
      </div>

      {/* ── Long-press context menu ── */}
      {showMenu && (
        <div style={{ position:'fixed', top:0, left: window.innerWidth <= 1024 ? 0 : 260, right: 0, bottom: 0, zIndex:9800, background:'rgba(0,0,0,0.6)', display:'flex', alignItems:'flex-end' }}
          onClick={() => setShowMenu(false)}>
          <div style={{ width:'100%', background:'#1a1a1a', borderRadius:'24px 24px 0 0', padding:'20px 16px 36px', fontFamily:'system-ui,sans-serif' }}
            onClick={e => e.stopPropagation()}>
            {/* Handle */}
            <div style={{ width:36, height:4, borderRadius:2, background:'rgba(255,255,255,0.25)', margin:'0 auto 20px' }} />
            {/* Media thumbnail header */}
            <div style={{ display:'flex', alignItems:'center', gap:12, marginBottom:18, paddingBottom:16, borderBottom:'1px solid rgba(255,255,255,0.08)' }}>
              <div style={{ width:52, height:52, borderRadius:10, overflow:'hidden', background:'#000', flexShrink:0 }}>
                {video?.thumbnail ? <img src={mediaUrl(video.thumbnail)} alt="" style={{ maxWidth:'100%', maxHeight:'100%', objectFit:'contain' }} /> : video?.image && <img src={mediaUrl(video.image)} alt="" style={{ maxWidth:'100%', maxHeight:'100%', objectFit:'contain' }} />}
              </div>
              <div>
                <div style={{ fontSize:14, fontWeight:700, color:'#fff' }}>{video?.creator}</div>
                <div style={{ fontSize:12, color:'rgba(255,255,255,0.5)', marginTop:2 }}>{video?.caption?.slice(0,50) || 'No caption'}</div>
              </div>
            </div>
            {/* Action grid */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:16 }}>
              {[
                { icon:'⬇️', label:'Save', action: handleDownload },
                { icon:'🔗', label:'Copy link', action: handleCopyLink },
                { icon:'📤', label:'Share', action: handleShare },
                { icon:'🚫', label:'Not interested', action: handleNotInterested },
              ].map(item => (
                <button key={item.label} onClick={item.action}
                  style={{ background:'rgba(255,255,255,0.07)', border:'none', borderRadius:16, padding:'16px 8px', cursor:'pointer', display:'flex', flexDirection:'column', alignItems:'center', gap:8 }}>
                  <span style={{ fontSize:26 }}>{item.icon}</span>
                  <span style={{ fontSize:11, fontWeight:600, color:'rgba(255,255,255,0.8)', textAlign:'center' }}>{item.label}</span>
                </button>
              ))}
            </div>
            <button onClick={() => setShowMenu(false)}
              style={{ width:'100%', padding:14, background:'rgba(255,255,255,0.07)', border:'none', borderRadius:16, fontSize:15, fontWeight:700, color:'#fff', cursor:'pointer' }}>
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* ── Toast ── */}
      {toast && (
        <div style={{ position:'fixed', top:60, left:'50%', transform:'translateX(-50%)', zIndex:99999,
          background:'rgba(20,20,20,0.95)', borderRadius:24, padding:'10px 22px',
          color:'#fff', fontSize:14, fontWeight:700, boxShadow:'0 4px 20px rgba(0,0,0,0.4)',
          backdropFilter:'blur(12px)', whiteSpace:'nowrap' }}>
          {toast}
        </div>
      )}
    </div>
  );
}




