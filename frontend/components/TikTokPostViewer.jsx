import { useState, useEffect, useRef, useCallback } from 'react';
import { X, Heart, MessageCircle, Share2, Bookmark, ChevronLeft, ChevronRight } from 'lucide-react';
import config from '../config';
import { getRelativeTime } from '../utils/timeUtils';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';

// TikTok-style scrollable post detail for ProfilePage
export function TikTokPostViewer({ posts, initialIndex, user, profileUser, onClose, onDeletePost, onEditPost, isOwnProfile, onNavigate }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [currentIndex, setCurrentIndex] = useState(initialIndex);
  const [isPlaying, setIsPlaying] = useState(true);
  const [showComments, setShowComments] = useState(false);
  const [liked, setLiked] = useState(false);
  const [likeCount, setLikeCount] = useState(0);
  const videoRef = useRef(null);
  const containerRef = useRef(null);

  const currentPost = posts[currentIndex];
  const hasNext = currentIndex < posts.length - 1;
  const hasPrev = currentIndex > 0;

  // Auto-play video when changing posts
  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.currentTime = 0;
      if (isPlaying) {
        videoRef.current.play().catch(() => {});
      }
    }
  }, [currentIndex, isPlaying]);

  // Sync like state with current post
  useEffect(() => {
    if (currentPost) {
      setLiked(currentPost.is_liked || false);
      setLikeCount(currentPost.votes || 0);
    }
  }, [currentPost]);

  const handleLike = () => {
    setLiked(!liked);
    setLikeCount(prev => liked ? prev - 1 : prev + 1);
  };

  const handleComment = () => {
    setShowComments(true);
  };

  // Handle keyboard navigation
  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === 'ArrowDown' || e.key === 'ArrowRight') {
        e.preventDefault();
        goToNext();
      } else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') {
        e.preventDefault();
        goToPrev();
      } else if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [currentIndex, posts.length]);

  const goToNext = useCallback(() => {
    if (hasNext) {
      setCurrentIndex(prev => prev + 1);
      onNavigate?.(currentIndex + 1);
    }
  }, [hasNext, currentIndex, onNavigate]);

  const goToPrev = useCallback(() => {
    if (hasPrev) {
      setCurrentIndex(prev => prev - 1);
      onNavigate?.(currentIndex - 1);
    }
  }, [hasPrev, currentIndex, onNavigate]);

  // Touch/swipe handling - only vertical
  const touchStartY = useRef(0);
  const touchStartX = useRef(0);
  const handleTouchStart = (e) => {
    touchStartY.current = e.touches[0].clientY;
    touchStartX.current = e.touches[0].clientX;
  };

  const handleTouchEnd = (e) => {
    const diffY = touchStartY.current - e.changedTouches[0].clientY;
    const diffX = touchStartX.current - e.changedTouches[0].clientX;
    
    // Only allow vertical swipe if horizontal movement is minimal
    if (Math.abs(diffX) < 30 && Math.abs(diffY) > 50) {
      if (diffY > 0) goToNext();
      else goToPrev();
    }
  };

  // Prevent horizontal scroll/swipe
  const handleTouchMove = (e) => {
    // Allow vertical scroll only
    const touchX = e.touches[0].clientX;
    const touchY = e.touches[0].clientY;
    const diffX = Math.abs(touchX - touchStartX.current);
    const diffY = Math.abs(touchY - touchStartY.current);
    
    // If horizontal movement is greater than vertical, prevent it
    if (diffX > diffY && diffX > 10) {
      e.preventDefault();
    }
  };

  // Wheel/scroll handling - using useEffect to add non-passive listener
  const wheelTimeout = useRef(null);
  
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    
    const handleWheel = (e) => {
      e.preventDefault();
      if (wheelTimeout.current) return;
      
      wheelTimeout.current = setTimeout(() => {
        wheelTimeout.current = null;
      }, 300);

      if (e.deltaY > 0) goToNext();
      else goToPrev();
    };
    
    // Add listener with passive: false to allow preventDefault
    container.addEventListener('wheel', handleWheel, { passive: false });
    return () => container.removeEventListener('wheel', handleWheel);
  }, [goToNext, goToPrev]);

  const mediaUrl = currentPost?.media || currentPost?.image || '';
  const fullUrl = mediaUrl.startsWith('http') ? mediaUrl : `${config.API_BASE_URL.replace('/api', '')}${mediaUrl}`;
  const isVideo = mediaUrl.match(/\.(mp4|webm|ogg|mov)$/i) || mediaUrl.includes('video');
  const videoUrl = fullUrl;

  const handleVideoClick = () => {
    if (videoRef.current) {
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
      } else {
        videoRef.current.play().catch((err) => {
          if (err.name !== 'AbortError') console.log('Play error:', err);
        });
        setIsPlaying(true);
      }
    }
  };

  if (!currentPost) return null;

  return (
    <div 
      ref={containerRef}
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: '#000',
        zIndex: 1000,
        display: 'flex',
        overflow: 'hidden',
        touchAction: 'pan-y',
      }}
      onTouchStart={handleTouchStart}
      onTouchEnd={handleTouchEnd}
      onTouchMove={handleTouchMove}
    >
      <style>{`
        @keyframes fadeOut {
          0% { opacity: 1; }
          70% { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes slideIn {
          from { opacity: 0; transform: translateY(20px); }
          to { opacity: 1; transform: translateY(0); }
        }
        .slide-in {
          animation: slideIn 0.3s ease-out;
        }
      `}</style>

      {/* Close Button */}
      <button
        onClick={onClose}
        style={{
          position: 'absolute',
          top: 8,
          left: 8,
          zIndex: 100,
          width: 32,
          height: 32,
          minWidth: 32,
          minHeight: 32,
          borderRadius: '50%',
          background: 'rgba(0,0,0,0.5)',
          border: 'none',
          cursor: 'pointer',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: '#fff',
          backdropFilter: 'blur(10px)',
          padding: 0,
        }}
      >
        <X size={18} />
      </button>

      {/* Progress Indicator */}
      <div style={{
        position: 'absolute',
        top: 8,
        right: 8,
        zIndex: 100,
        background: 'rgba(0,0,0,0.6)',
        padding: '4px 10px',
        borderRadius: 14,
        color: '#fff',
        fontSize: 12,
        fontWeight: 600,
      }}>
        {currentIndex + 1} / {posts.length}
      </div>

      {/* Main Content - Video/Image */}
      <div 
        className="slide-in"
        style={{
          flex: 1,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          position: 'relative',
          cursor: isVideo ? 'pointer' : 'default',
          overflow: 'hidden',
        }}
        onClick={isVideo ? handleVideoClick : undefined}
      >
        {isVideo ? (
          <video
            ref={videoRef}
            src={videoUrl}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
            }}
            autoPlay
            loop
            playsInline
            muted={true}
          />
        ) : (
          <img
            src={fullUrl}
            alt={currentPost.caption}
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'contain',
            }}
          />
        )}

        {/* Pause indicator */}
        {isVideo && !isPlaying && (
          <div style={{
            position: 'absolute',
            top: '50%',
            left: '50%',
            transform: 'translate(-50%, -50%)',
            width: 80,
            height: 80,
            borderRadius: '50%',
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}>
            <div style={{
              width: 0,
              height: 0,
              borderTop: '15px solid transparent',
              borderBottom: '15px solid transparent',
              borderLeft: '25px solid #fff',
              marginLeft: 5,
            }} />
          </div>
        )}
      </div>

      {/* Bottom Info Panel */}
      <div style={{
        position: 'absolute',
        right: 0,
        bottom: 0,
        left: 0,
        padding: '16px 20px 80px',
        paddingBottom: 'calc(80px + env(safe-area-inset-bottom, 0px))',
        background: 'linear-gradient(transparent 0%, rgba(0,0,0,0.7) 30%, rgba(0,0,0,0.85) 100%)',
        color: '#fff',
        zIndex: 50,
      }}>
        {/* User Info */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: 12,
          marginBottom: 12,
        }}>
          {profileUser?.profile_photo ? (
            <img
              src={profileUser.profile_photo.startsWith('http') ? profileUser.profile_photo : `${config.API_BASE_URL.replace('/api', '')}${profileUser.profile_photo}`}
              alt="Profile"
              style={{
                width: 40,
                height: 40,
                borderRadius: '50%',
                objectFit: 'cover',
                border: '2px solid #fff',
                flexShrink: 0,
              }}
            />
          ) : (
            <div style={{
              width: 40,
              height: 40,
              borderRadius: '50%',
              background: 'rgba(255,255,255,0.2)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 18,
              border: '2px solid #fff',
              flexShrink: 0,
            }}>
              👤
            </div>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ 
              fontSize: 15, 
              fontWeight: 700,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}>
              @{profileUser?.username}
            </div>
            <div style={{ fontSize: 12, opacity: 0.8 }}>
              {getRelativeTime(new Date(currentPost.created_at || currentPost.timestamp))}
            </div>
          </div>
        </div>

        {/* Caption */}
        {currentPost.caption && (
          <div style={{
            fontSize: 14,
            lineHeight: 1.5,
            marginBottom: 14,
            maxHeight: 72,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            display: '-webkit-box',
            WebkitLineClamp: 3,
            WebkitBoxOrient: 'vertical',
          }}>
            <span style={{ fontWeight: 700 }}>{profileUser?.username} </span>
            {currentPost.caption}
          </div>
        )}

        {/* Action Buttons */}
        <div style={{
          display: 'flex',
          gap: 20,
          alignItems: 'center',
        }}>
          <button
            onClick={handleLike}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: 0,
            }}
          >
            <Heart size={22} fill={liked ? "#fff" : "none"} color="#fff" />
            <span style={{ fontSize: 14, fontWeight: 700 }}>{likeCount}</span>
          </button>
          <button
            onClick={handleComment}
            style={{
              background: 'none',
              border: 'none',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
              padding: 0,
            }}
          >
            <MessageCircle size={22} color="#fff" />
            <span style={{ fontSize: 14, fontWeight: 700 }}>{currentPost.comments_count || 0}</span>
          </button>
          
          {/* Edit/Delete for own profile */}
          {isOwnProfile && (
            <>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onEditPost?.(currentPost.id);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#fff',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                ✏️ Edit
              </button>
              <button
                onClick={(e) => {
                  e.stopPropagation();
                  onDeletePost?.(currentPost.id);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  color: '#FF4444',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                🗑️ Delete
              </button>
            </>
          )}
        </div>
      </div>

      {/* Swipe hint for mobile */}
      <div style={{
        position: 'absolute',
        bottom: 120,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 40,
        background: 'rgba(0,0,0,0.5)',
        padding: '8px 16px',
        borderRadius: 20,
        color: '#fff',
        fontSize: 12,
        display: window.innerWidth <= 768 ? 'flex' : 'none',
        alignItems: 'center',
        gap: 8,
        animation: 'fadeOut 3s forwards',
      }}>
        👆 Swipe to navigate
      </div>
    </div>
  );
}




