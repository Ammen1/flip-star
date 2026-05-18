import React, { useState, useEffect, useRef, useCallback, startTransition, memo } from 'react';
import {
  MessageCircle,
  Share2,
  Bookmark,
  MoreVertical,
  Flag,
  Info,
  UserPlus,
  UserCheck,
  Volume2,
  VolumeX,
  Bell,
  Heart,
  Download,
  Link,
  EyeOff,
  AlertTriangle,
  Play,
  Pause,
  Gift,
} from 'lucide-react';
import api from '../api';
import config from '../config';
import { ModernCommentSection } from './ModernCommentSection';
import { WinnersSection } from './WinnersSection';
import { SidebarCampaigns } from './SidebarCampaigns';
import { LikeButton } from './LikeButton';
import { SearchBar } from './SearchBar';
import { UserSuggestions } from './UserSuggestions';
import { AlertModal } from './AlertModal';
import GiftPage from './GiftPage';
import { getRelativeTime } from '../utils/timeUtils';
import { useTheme } from '../contexts/ThemeContext';
import { useLanguage } from '../contexts/LanguageContext';
import realtimeService from '../services/RealtimeService';
import './TikTokLayout.css';
const ShareIconFilled = ({ size = 26, color = '#fff', style = {} }) => (
  <Share2 size={size} color={color} style={style} />
);

// Helper to shuffle array for randomized feed
const shuffleArray = (array) => {
  const newArr = [...array];
  for (let i = newArr.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [newArr[i], newArr[j]] = [newArr[j], newArr[i]];
  }
  return newArr;
};

// CaptionWithLessMore component for truncating long captions
const CaptionWithLessMore = ({ caption, maxLength = 100 }) => {
  const [isExpanded, setIsExpanded] = useState(false);
  
  if (!caption || caption.length <= maxLength) {
    return <span>{caption}</span>;
  }
  
  return (
    <span>
      {isExpanded ? caption : caption.slice(0, maxLength) + '...'}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        style={{
          background: 'none',
          border: 'none',
          color: '#3498db',
          cursor: 'pointer',
          fontSize: 'inherit',
          padding: 0,
          marginLeft: 4,
        }}
      >
        {isExpanded ? 'less' : 'more'}
      </button>
    </span>
  );
};

export const TikTokLayout = memo(function TikTokLayout({
  user,
  activeTab: propActiveTab,
  videosOnly = false,
  initialVideoId = null,
  onLogout,
  onRequireAuth,
  onShowPostPage,
  onShowProfile,
  onShowSettings,
  onShowCampaigns,
  onShowNotifications,
  onShowVideoDetail,
  onShowWallet,
  onShowCoinPurchase,
  unreadNotifCount = 0,
}) {
  console.log('[TikTokLayout] Component mounted, videosOnly:', videosOnly);
  const { colors: T } = useTheme();
  const { t } = useLanguage();

  // Map external tab names to internal tab names
  const mapTabName = (tab) => {
    const tabMap = {
      home: 'home',
      search: 'search',
      explore: 'explore',
      reels: 'reels',
      messages: 'inbox',
      notifications: 'notifications',
      following: 'following',
      bookmarks: 'bookmarks',
      foryou: 'home',
    };
    return tabMap[tab] || 'home';
  };

  const [activeTab, setActiveTab] = useState(
    mapTabName(propActiveTab) || 'home',
  );

  // Update internal state when prop changes
  useEffect(() => {
    if (propActiveTab) {
      setActiveTab(mapTabName(propActiveTab));
    }
  }, [propActiveTab]);

  // ── Feed cache helpers (stale-while-revalidate) ──────────────────────────
  const CACHE_KEY = (tab) => `feed_cache_${tab}`;
  const CACHE_TTL = 2 * 60 * 1000; // 2 min for faster post distribution
  const readFeedCache = (tab) => {
    try {
      const raw = localStorage.getItem(CACHE_KEY(tab));
      if (!raw) return null;
      const { ts, data } = JSON.parse(raw);
      if (Date.now() - ts > CACHE_TTL) { localStorage.removeItem(CACHE_KEY(tab)); return null; }
      return data;
    } catch { return null; }
  };
  const writeFeedCache = (tab, data) => {
    try { localStorage.setItem(CACHE_KEY(tab), JSON.stringify({ ts: Date.now(), data })); } catch {}
  };

  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);
  const [page, setPage] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState(null);
  const LIMIT = 5; // Reduced from 10 to 5 for faster initial load
  const [showMenu, setShowMenu] = useState(null);
  const [showReportModal, setShowReportModal] = useState(null);
  const [showComments, setShowComments] = useState(null);
  const [showGiftModal, setShowGiftModal] = useState(null);
  const [giftReelId, setGiftReelId] = useState(null);
  const [playingVideos, setPlayingVideos] = useState({});
  const [showPauseIcon, setShowPauseIcon] = useState({});
  const [manuallyPaused, setManuallyPaused] = useState({}); // Track user-paused videos
  const [isMobile, setIsMobile] = useState(() => window.innerWidth <= 1024);
  const [audioEnabled, setAudioEnabled] = useState(true);
  const [likeAnimations, setLikeAnimations] = useState({});
  const [doubleTapLike, setDoubleTapLike] = useState({});
  const [alertModal, setAlertModal] = useState({
    isOpen: false,
    title: '',
    message: '',
    type: 'info',
    onConfirm: null,
    showCancel: false,
  });

  // Pull to refresh state
  const [pullDistance, setPullDistance] = useState(0);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const touchStartY = useRef(0);
  const feedContainerRef = useRef(null);
  const PULL_THRESHOLD = 80;

  const videoRefs = useRef({});
  const videoContainerRefs = useRef({});
  const [visibleVideos, setVisibleVideos] = useState({});
  const [videoOrientations, setVideoOrientations] = useState(() => {
    try { return JSON.parse(localStorage.getItem('_vidOrient') || '{}'); } catch { return {}; }
  }); // { [id]: 'portrait' | 'landscape' } — persisted to avoid flicker on refresh
  const activeVideoIdRef = useRef(null); // only this video plays with sound
  // State mirror of `activeVideoIdRef` so React effects can react to changes.
  // The ref is kept for sync reads inside callbacks; the state drives a
  // watchdog effect that hard-mutes every other video whenever the active one
  // changes (defends against IntersectionObserver entry-ordering races that
  // can otherwise leave two videos audible at once during fast scrolling).
  const [activeVideoId, setActiveVideoId] = useState(null);
  const longPressTimer = useRef(null);
  const [longPressMenu, setLongPressMenu] = useState(null); // { videoId, x, y } for long-press context menu

  // Generate video poster thumbnail (returns undefined for local storage)
  const getVideoPoster = (url) => undefined;

  // Mobile detection - runs once on mount and on resize
  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 1024);
    };
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  // Fetch videos based on active tab with pagination
  const fetchVideos = async (pageNum = 1, append = false) => {
    const isFirst = pageNum === 1 && !append;

    if (append) {
      setLoadingMore(true);
    } else {
      // Show cached data immediately so LCP fires without waiting for API
      if (isFirst) {
        const cached = readFeedCache(activeTab);
        if (cached?.length > 0) {
          setVideos(cached);
          setLoading(false); // content visible instantly
        } else {
          setLoading(true);
        }
      }
    }
    
    try {
      let reelsData = [];
      const limit = pageNum === 1 ? 10 : 5; // Load more videos on first page for better user experience
      const offset = (pageNum - 1) * limit;

      // Fetch different content based on active tab
      if (activeTab === 'following') {
        reelsData = await api.request(`/reels/following/?limit=${limit}&offset=${offset}`);
      } else if (activeTab === 'bookmarks') {
        reelsData = await api.request(`/reels/saved/?limit=${limit}&offset=${offset}`);
      } else if (activeTab === 'explore') {
        reelsData = await api.request(`/reels/trending/?limit=${limit}&offset=${offset}`);
      } else {
        // For the initial foryou load, reuse the warm-up fetch fired in index.html
        // so we don't pay the cost of a second cold-start round-trip
        if (isFirst && window.__warmupFeed) {
          const warmup = window.__warmupFeed;
          window.__warmupFeed = null; // consume once
          reelsData = (await warmup) || [];
        } else {
          reelsData = await api.request(`/reels/?limit=${limit}&offset=${offset}`);
        }
      }


      // Handle different response formats (DRF pagination returns {count, next, previous, results})
      const reelsList = Array.isArray(reelsData)
        ? reelsData
        : reelsData.results || [];

      console.log('[TikTokLayout] videosOnly:', videosOnly);
      console.log('[TikTokLayout] reelsList length:', reelsList.length);
      console.log('[TikTokLayout] reelsList sample:', reelsList.slice(0, 3));

      // Filter to show only videos when videosOnly is true (reels tab)
      const filteredList = videosOnly
        ? reelsList.filter(reel => {
            // Must have media and it must be a video file (not image)
            if (!reel.media || reel.media === '') {
              console.log('[TikTokLayout] Filtered out (no media):', reel.id, reel.media);
              return false;
            }
            const isVideoFile = /\.(mp4|webm|ogg|mov|avi|mkv)(\?|$)/i.test(reel.media) ||
                                reel.media.includes('/video/upload/');
            if (!isVideoFile) {
              console.log('[TikTokLayout] Filtered out (not video):', reel.id, reel.media);
            }
            return isVideoFile;
          })
        : reelsList;

      console.log('[TikTokLayout] filteredList length:', filteredList.length);
      
      // Check if there are more videos to load using DRF pagination
      // Only continue if we got a full page AND there's a next link, or if it's the first page with exactly limit items
      const hasMoreVideos = reelsData.next ? true : (pageNum === 1 && filteredList.length === limit);
      setHasMore(hasMoreVideos);

      // Transform backend data to match frontend format
      const formattedVideos = filteredList.map((reel) => {
        const videoUrl = reel.media || reel.image;

        return {
          id: reel.id,
          user: reel.user,
          creator: reel.user?.username || 'Unknown User',
          handle: `@${reel.user?.username || 'unknown'}`,
          avatar: '👤',
          caption: reel.caption,
          hashtags: reel.hashtags_list || [],
          likes: reel.votes || 0,
          comments: reel.comment_count || 0,
          shares: reel.shares,
          gift_count: reel.gift_count || 0,
          imageUrl: (() => {
            const url = reel.media || reel.image;
            if (!url) return null;
            if (
              url.includes('/video/upload/') &&
              !url.match(/\.(mp4|webm|ogg|mov)(\?|$)/i)
            ) {
              return url + '.mp4';
            }
            return url;
          })(),
          liked: reel.is_liked || false,
          saved: reel.is_saved || false,
          created_at: reel.created_at,
          overlayText: (() => {
            if (!reel.overlay_text) return [];
            try { return JSON.parse(reel.overlay_text); } catch { return []; }
          })(),
          is_campaign_post: reel.is_campaign_post || false,
          campaign_id: reel.campaign_id || null,
          campaign: reel.campaign || null,
        };
      });
      
      // Filter to videos only if videosOnly prop is set (Reels tab)
      const filteredVideos = videosOnly
        ? formattedVideos.filter(v => {
            const url = v.imageUrl || '';
            return url.match(/\.(mp4|webm|ogg|mov)(\?|$)/i) ||
                   url.includes('/video/upload/');
          })
        : formattedVideos;
      
      // Shuffle the batch to ensure a randomized/random-feeling order for each user
      const shuffledVideos = shuffleArray(filteredVideos);

      if (append) {
        setVideos(prev => [...prev, ...shuffledVideos]);
      } else {
        setVideos(shuffledVideos);
        // Persist fresh data so next load is instant (stale-while-revalidate)
        if (shuffledVideos.length > 0) {
          writeFeedCache(activeTab, shuffledVideos);
        }
      }
    } catch (error) {
      console.error('Failed to fetch videos:', error);
      // Keep cached data visible if API fails - don't blank the screen
      if (!append) {
        const cached = readFeedCache(activeTab);
        if (!cached?.length) setVideos([]);
      }
    } finally {
      if (append) {
        setLoadingMore(false);
      } else {
        setLoading(false);
      }
    }
  };

  // Tabs whose feed should loop forever (TikTok-style infinite scroll). When
  // the backend reports no more pages, we wrap around and refetch page 1 so
  // the user can keep scrolling indefinitely. Personal feeds like bookmarks
  // and following are NOT looped — there it's correct to show "you're done".
  const LOOPABLE_TABS = new Set(['home', 'reels', 'explore']);

  // Load more videos function
  const loadMoreVideos = () => {
    if (loadingMore) return;
    if (hasMore) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchVideos(nextPage, true);
      return;
    }
    // Reached the end. For loopable tabs, wrap around: reset to page 1, mark
    // the feed as having more, and append a fresh (shuffled) batch.
    if (LOOPABLE_TABS.has(activeTab) && videos.length > 0) {
      setHasMore(true);
      setPage(1);
      fetchVideos(1, true);
    }
  };

  useEffect(() => {
    // Clear current videos immediately when switching tabs to prevent mixing
    setVideos([]);
    setPage(1);
    setHasMore(true);
    initialReorderDoneRef.current = false;
    // Defer video fetch for better INP
    startTransition(() => {
      fetchVideos(1, false);
    });
  }, [activeTab]);

  // Scroll to top + refresh when user taps the already-active tab icon
  useEffect(() => {
    const handleTabReselect = (e) => {
      if (e.detail?.tab !== activeTab) return;
      // Snap back to very first video
      const container = document.querySelector('.video-feed-container');
      if (container) container.scrollTo({ top: 0, behavior: 'smooth' });
      // Refresh feed from page 1
      setPage(1);
      setHasMore(true);
      startTransition(() => fetchVideos(1, false));
    };
    window.addEventListener('tabReselected', handleTabReselect);
    return () => window.removeEventListener('tabReselected', handleTabReselect);
  }, [activeTab]); // eslint-disable-line

  // Deep-link to a specific reel (from home post click, notification, share, etc.)
  // Instead of scrolling after auto-play (which caused a race where videos[0]
  // started playing and the IO sometimes landed on the next video), we REORDER
  // the list so the target becomes videos[0]. This makes deep-links rock solid:
  // the target is at the top of the scroll area, auto-plays, and there's no
  // scroll animation to race with the IntersectionObserver.
  const initialReorderDoneRef = useRef(false);
  const initialVideoIdRef = useRef(null); // Track the initialVideoId to prevent clearing
  useEffect(() => {
    initialReorderDoneRef.current = false;
    initialVideoIdRef.current = initialVideoId;
  }, [initialVideoId]);
  useEffect(() => {
    if (!initialVideoId) return;
    if (initialReorderDoneRef.current) return;
    if (!videos.length) return;

    const idx = videos.findIndex((v) => String(v.id) === String(initialVideoId));
    if (idx === -1) {
      // Target not in current batch (e.g. a brand-new reel that the user just
      // posted). Fetch this specific reel by id and prepend it instead of
      // paging forward, which would never surface a newest-first reel.
      console.log(`Video ${initialVideoId} not found in current batch, fetching directly...`);
      initialReorderDoneRef.current = true; // prevent re-entry
      (async () => {
        try {
          const reel = await api.request(`/reels/${initialVideoId}/`);
          if (!reel || !reel.id) return;
          // Transform the reel to match the video format with campaign fields
          const formattedReel = {
            id: reel.id,
            user: reel.user,
            creator: reel.user?.username || 'Unknown User',
            handle: `@${reel.user?.username || 'unknown'}`,
            avatar: '👤',
            caption: reel.caption,
            hashtags: reel.hashtags_list || [],
            likes: reel.votes || 0,
            comments: reel.comment_count || 0,
            shares: reel.shares,
            gift_count: reel.gift_count || 0,
            imageUrl: (() => {
              const url = reel.media || reel.image;
              if (!url) return null;
              if (
                url.includes('/video/upload/') &&
                !url.match(/\.(mp4|webm|ogg|mov)(\?|$)/i)
              ) {
                return url + '.mp4';
              }
              return url;
            })(),
            liked: reel.is_liked || false,
            saved: reel.is_saved || false,
            created_at: reel.created_at,
            overlayText: (() => {
              if (!reel.overlay_text) return [];
              try { return JSON.parse(reel.overlay_text); } catch { return []; }
            })(),
            is_campaign_post: reel.is_campaign_post || false,
            campaign_id: reel.campaign_id || null,
            campaign: reel.campaign || null,
          };
          setVideos((prev) => {
            // Avoid duplicates if it shows up via another path
            const filtered = prev.filter((v) => String(v.id) !== String(formattedReel.id));
            return [formattedReel, ...filtered];
          });
          const scroller = document.querySelector('.feed-container');
          if (scroller) scroller.scrollTop = 0;
          else window.scrollTo(0, 0);
        } catch (err) {
          console.warn('Failed to fetch target reel directly', err);
        }
      })();
      return;
    }
    if (idx === 0) {
      // Already at the front — nothing to do
      console.log(`Video ${initialVideoId} already at front`);
      initialReorderDoneRef.current = true;
      return;
    }

    // Move target video to index 0
    console.log(`Moving video ${initialVideoId} from index ${idx} to front`);
    setVideos((prev) => {
      const i = prev.findIndex((v) => String(v.id) === String(initialVideoId));
      if (i <= 0) return prev;
      const next = prev.slice();
      const [target] = next.splice(i, 1);
      next.unshift(target);
      return next;
    });
    initialReorderDoneRef.current = true;
  }, [initialVideoId, videos, hasMore, loadingMore, page, fetchVideos]);

  useEffect(() => {
    if (!initialVideoId) return;
    if (initialReorderDoneRef.current) return;
    if (!videos.length) return;

    const idx = videos.findIndex((v) => String(v.id) === String(initialVideoId));
    if (idx === -1) {
      // Handled by the first effect above (fetches the reel directly when missing).
      return;
    }
    if (idx === 0) {
      // Already at the front — nothing to do
      initialReorderDoneRef.current = true;
      return;
    }

    // Move target video to index 0
    setVideos((prev) => {
      const i = prev.findIndex((v) => String(v.id) === String(initialVideoId));
      if (i <= 0) return prev;
      const next = prev.slice();
      const [target] = next.splice(i, 1);
      next.unshift(target);
      return next;
    });
    // Also scroll to top so the user sees it immediately (no smooth scroll so
    // the IO doesn't accidentally trip on intermediate videos during animation)
    const scroller = document.querySelector('.feed-container');
    if (scroller) scroller.scrollTop = 0;
    else window.scrollTo(0, 0);
    
    // Auto-play the target video immediately since IntersectionObserver might not trigger
    setTimeout(() => {
      const targetVideo = videoRefs.current[initialVideoId];
      if (targetVideo && targetVideo.paused) {
        // Reset manual pause flag for the target video
        setManuallyPaused((prev) => ({ ...prev, [initialVideoId]: false }));
        activeVideoIdRef.current = initialVideoId;
        setActiveVideoId(String(initialVideoId));
        // Try unmuted first for better UX
        targetVideo.muted = false;
        targetVideo.play()
          .then(() => {
            setPlayingVideos((prev) => ({ ...prev, [initialVideoId]: true }));
            setShowPauseIcon((prev) => ({ ...prev, [initialVideoId]: false }));
          })
          .catch((err) => {
            if (err.name !== 'AbortError') console.log('Auto-play prevented:', err);
            // Try muted if unmuted failed (browser autoplay policy)
            targetVideo.muted = true;
            targetVideo.play()
              .then(() => {
                setPlayingVideos((prev) => ({ ...prev, [initialVideoId]: true }));
                setShowPauseIcon((prev) => ({ ...prev, [initialVideoId]: false }));
              })
              .catch((e) => console.log('Muted play also prevented:', e));
          });
      }
    }, 500); // Increased delay to ensure DOM is updated after reordering
    
    initialReorderDoneRef.current = true;
  }, [initialVideoId, videos, hasMore, loadingMore, page, fetchVideos]);

  // Remove the HTML skeleton overlay as soon as we have content to show
  useEffect(() => {
    if (videos.length > 0 || !loading) {
      const skeleton = document.getElementById('app-skeleton');
      if (skeleton) {
        skeleton.style.transition = 'opacity 0.2s ease';
        skeleton.style.opacity = '0';
        setTimeout(() => skeleton.remove(), 220);
      }
    }
  }, [videos.length, loading]);

  // Set mounted state after a short delay to prevent brief video flash
  useEffect(() => {
    const timer = setTimeout(() => setMounted(true), 100);
    return () => clearTimeout(timer);
  }, []);

  // Fallback: remove skeleton after 5 seconds even if loading fails
  useEffect(() => {
    const timeout = setTimeout(() => {
      const skeleton = document.getElementById('app-skeleton');
      if (skeleton) {
        skeleton.style.transition = 'opacity 0.2s ease';
        skeleton.style.opacity = '0';
        setTimeout(() => skeleton.remove(), 220);
      }
    }, 5000);
    return () => clearTimeout(timeout);
  }, []);

  // Preload first video's poster with better timing and cleanup
  useEffect(() => {
    if (!videos.length) return;
    const firstUrl = videos[0]?.imageUrl;
    if (!firstUrl) return;
    const poster = getVideoPoster(firstUrl);
    if (!poster) return;
    
    // Remove any existing preload
    const existing = document.head.querySelector(`link[data-video-poster]`);
    if (existing) existing.remove();
    
    // Only preload if we're likely to use it soon
    const link = document.createElement('link');
    link.rel = 'preload';
    link.as = 'image';
    link.href = poster;
    link.setAttribute('data-video-poster', '1');
    
    // Add timeout to remove preload if not used within 5 seconds
    const timeoutId = setTimeout(() => {
      try { link.remove(); } catch {}
    }, 5000);
    
    document.head.appendChild(link);
    
    return () => { 
      clearTimeout(timeoutId);
      try { link.remove(); } catch {} 
    };
  }, [videos[0]?.id]);

  // Scroll listener for infinite scroll
  useEffect(() => {
    const handleScroll = () => {
      const scrollContainer = document.querySelector('.video-feed-container');
      if (!scrollContainer) return;

      const scrollTop = scrollContainer.scrollTop;
      const scrollHeight = scrollContainer.scrollHeight;
      const clientHeight = scrollContainer.clientHeight;

      // Load more when user is 300px from bottom
      if (scrollHeight - scrollTop - clientHeight < 300) {
        loadMoreVideos();
      }
    };

    const scrollContainer = document.querySelector('.video-feed-container');
    if (scrollContainer) {
      scrollContainer.addEventListener('scroll', handleScroll);
      return () => scrollContainer.removeEventListener('scroll', handleScroll);
    }
  }, [loadingMore, hasMore, page]);

  // IntersectionObserver to control video playback AND lazy-load src
  useEffect(() => {
    // Observer for playback (50% visible for better performance)
    const playbackObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const videoId = entry.target.dataset.videoId;
          const videoElement = videoRefs.current[videoId];
          if (!videoElement) return;

          if (entry.isIntersecting && entry.intersectionRatio >= 0.5) {
            // Don't auto-play if user manually paused this video
            if (manuallyPaused[videoId]) {
              return;
            }

            // Mute ALL other playing videos first
            Object.entries(videoRefs.current).forEach(([id, el]) => {
              if (el && id !== videoId) {
                el.muted = true;
                el.pause();
              }
            });
            // Play the active video (always start muted to prevent mixing)
            activeVideoIdRef.current = videoId;
            setActiveVideoId(videoId);
            videoElement.muted = true;
            videoElement
              .play()
              .then(() => {
                setPlayingVideos((prev) => ({ ...prev, [videoId]: true }));
                // Only unmute if audioEnabled is true and this is the active video
                if (audioEnabled && activeVideoIdRef.current === videoId) {
                  videoElement.muted = false;
                }
              })
              .catch((err) => {
                if (err.name === 'AbortError') return; // Ignore play interrupted by pause
                console.log('Play prevented:', err);
              });
            // Hide pause icon when auto-playing
            setShowPauseIcon((prev) => ({ ...prev, [videoId]: false }));
          } else {
            // Only pause if not manually paused (to avoid hiding the pause icon)
            if (!manuallyPaused[videoId]) {
              videoElement.muted = true;
              videoElement.pause();
              setPlayingVideos((prev) => ({ ...prev, [videoId]: false }));
            }
          }
        });
      },
      { threshold: [0, 0.5, 1], rootMargin: '-10% 0px -10% 0px' }
    );

    // Observer for lazy-loading src (preload when 1 screen away)
    const lazyObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          const videoId = entry.target.dataset.videoId;
          if (entry.isIntersecting) {
            setVisibleVideos((prev) => ({ ...prev, [videoId]: true }));
          }
        });
      },
      { rootMargin: '50%' } // Reduced from 100% to 50% for better performance
    );

    Object.keys(videoContainerRefs.current).forEach((videoId) => {
      const container = videoContainerRefs.current[videoId];
      if (container) {
        playbackObserver.observe(container);
        lazyObserver.observe(container);
      }
    });

    return () => {
      playbackObserver.disconnect();
      lazyObserver.disconnect();
    };
  }, [videos, manuallyPaused, audioEnabled]);

  // Watchdog: whenever the active video changes, hard-mute & pause every other
  // video. This is the single source of truth for "only one video plays at a
  // time" and is immune to IntersectionObserver entry-ordering races during
  // fast scrolling that would otherwise leave overlapping audio.
  useEffect(() => {
    if (!activeVideoId) return;
    Object.entries(videoRefs.current).forEach(([id, el]) => {
      if (!el || id === activeVideoId) return;
      try {
        if (!el.muted) el.muted = true;
        if (!el.paused) el.pause();
      } catch (_) {}
    });
  }, [activeVideoId]);

  // Auto-play first video on initial load
  useEffect(() => {
    if (videos.length === 0 || loading) return;

    const firstVideo = videos[0];
    const videoElement = videoRefs.current[firstVideo.id];

    // Small delay to ensure video element is mounted
    const timer = setTimeout(() => {
      if (videoElement && videoElement.paused) {
        // Reset manual pause flag for the first video
        setManuallyPaused((prev) => ({ ...prev, [firstVideo.id]: false }));
        activeVideoIdRef.current = String(firstVideo.id);
        setActiveVideoId(String(firstVideo.id));
        // Start muted to prevent audio mixing
        videoElement.muted = true;
        videoElement.play()
          .then(() => {
            setPlayingVideos((prev) => ({ ...prev, [firstVideo.id]: true }));
            // Only unmute if audioEnabled is true and this is the active video
            if (audioEnabled && activeVideoIdRef.current === String(firstVideo.id)) {
              videoElement.muted = false;
            }
          })
          .catch((err) => {
            if (err.name === 'AbortError') return; // Ignore play interrupted by pause
            console.log('Auto-play prevented:', err);
          });
      }
    }, 300);

    return () => clearTimeout(timer);
  }, [videos.length > 0 && !loading, audioEnabled]); // Only run when videos first load

  const handleCommentPosted = (comment) => {
    // Update the comment count for the specific video
    setVideos((prev) =>
      prev.map((video) =>
        video.id === comment.reel
          ? { ...video, comments: video.comments + 1 }
          : video,
      ),
    );
  };

  const toggleAudio = () => {
    const next = !audioEnabled;
    setAudioEnabled(next);
    // Only unmute the currently active video — all others stay muted
    Object.entries(videoRefs.current).forEach(([id, video]) => {
      if (video) video.muted = id === activeVideoIdRef.current ? !next : true;
    });
  };

  const handleDoubleTap = (videoId) => {
    if (!user) {
      onRequireAuth();
      return;
    }
    
    // Trigger like (only if not already liked)
    const video = videos.find(v => v.id === videoId);
    if (video && !video.liked) {
      handleLike(videoId);
    }
    
    // Show double-tap heart animation (use timestamp key for re-triggering)
    setDoubleTapLike((prev) => ({ ...prev, [videoId]: Date.now() }));
  };

  // ─── Tap / Double-tap disambiguation ──────────────────────────────────────
  // Goal: a SINGLE tap should only toggle play/pause AFTER we're sure no
  // second tap is coming. A DOUBLE tap should like the reel and never
  // briefly flash the pause icon in between, like TikTok / Instagram / YouTube.
  const DOUBLE_TAP_WINDOW = 280; // ms
  const lastTapRef = useRef({});         // per-video timestamp of the previous tap
  const singleTapTimer = useRef({});     // per-video pending single-tap timer
  const lastTouchTimeRef = useRef(0);    // debounces synthetic onClick after touch

  const clearPendingSingleTap = (videoId) => {
    if (singleTapTimer.current[videoId]) {
      clearTimeout(singleTapTimer.current[videoId]);
      singleTapTimer.current[videoId] = null;
    }
  };

  const scheduleSingleTap = (videoId) => {
    clearPendingSingleTap(videoId);
    singleTapTimer.current[videoId] = setTimeout(() => {
      toggleVideoPlayback(videoId);
      singleTapTimer.current[videoId] = null;
    }, DOUBLE_TAP_WINDOW);
  };

  // Mobile: touchend-based detector. Works even when the browser swallows dblclick.
  const handleVideoTouchEnd = (videoId) => {
    lastTouchTimeRef.current = Date.now();
    const now = Date.now();
    const last = lastTapRef.current[videoId] || 0;
    if (now - last < DOUBLE_TAP_WINDOW) {
      // Second tap inside the window → treat as double-tap (like) only.
      lastTapRef.current[videoId] = 0;
      clearPendingSingleTap(videoId);
      handleDoubleTap(videoId);
    } else {
      // First tap → wait to see if a second one is coming. If not, toggle play/pause.
      lastTapRef.current[videoId] = now;
      scheduleSingleTap(videoId);
    }
  };

  // Desktop: delay click so onDoubleClick has a chance to cancel it.
  const handleVideoClick = (videoId) => {
    // A click that arrives right after a touchend is synthetic — ignore it to
    // avoid double-firing with handleVideoTouchEnd.
    if (Date.now() - lastTouchTimeRef.current < 500) return;
    scheduleSingleTap(videoId);
  };

  const handleVideoDoubleClick = (videoId) => {
    clearPendingSingleTap(videoId);
    handleDoubleTap(videoId);
  };

  const handleResumePause = (videoId) => {
    const videoElement = videoRefs.current[videoId];
    if (!videoElement) return;

    if (videoElement.paused) {
      // User is resuming - remove manual pause flag
      setManuallyPaused((prev) => ({ ...prev, [videoId]: false }));
      videoElement.muted = !audioEnabled;
      videoElement.play().catch((err) => {
        if (err.name !== 'AbortError') console.log('Play error:', err);
      });
      setPlayingVideos((prev) => ({ ...prev, [videoId]: true }));
      setShowPauseIcon((prev) => ({ ...prev, [videoId]: false }));
    } else {
      // User is pausing - set manual pause flag
      setManuallyPaused((prev) => ({ ...prev, [videoId]: true }));
      videoElement.pause();
      setPlayingVideos((prev) => ({ ...prev, [videoId]: false }));
      setShowPauseIcon((prev) => ({ ...prev, [videoId]: true }));
    }
  };

  const toggleVideoPlayback = (videoId) => {
    const videoElement = videoRefs.current[videoId];
    if (!videoElement) return;

    if (videoElement.paused) {
      // User is resuming - remove manual pause flag
      setManuallyPaused((prev) => ({ ...prev, [videoId]: false }));
      videoElement.muted = !audioEnabled;
      videoElement.play().catch((err) => {
        if (err.name !== 'AbortError') console.log('Play error:', err);
      });
      setPlayingVideos((prev) => ({ ...prev, [videoId]: true }));
      setShowPauseIcon((prev) => ({ ...prev, [videoId]: false }));
    } else {
      // User is pausing - set manual pause flag
      setManuallyPaused((prev) => ({ ...prev, [videoId]: true }));
      videoElement.pause();
      setPlayingVideos((prev) => ({ ...prev, [videoId]: false }));
      setShowPauseIcon((prev) => ({ ...prev, [videoId]: true }));
    }
  };

  const handleLike = async (videoId) => {
    if (!user) {
      onRequireAuth();
      return;
    }

    // Show heart animation instantly
    setLikeAnimations((prev) => ({ ...prev, [videoId]: Date.now() }));

    // Optimistic UI: update immediately before API call
    setVideos((prev) =>
      prev.map((video) =>
        video.id === videoId
          ? {
              ...video,
              liked: !video.liked,
              likes: video.liked ? video.likes - 1 : video.likes + 1,
            }
          : video,
      ),
    );

    try {
      const response = await api.request(`/reels/${videoId}/vote/`, {
        method: 'POST',
      });

      // Reconcile with server truth
      if (response.voted !== undefined) {
        setVideos((prev) =>
          prev.map((video) =>
            video.id === videoId
              ? {
                  ...video,
                  liked: response.voted,
                  likes: response.votes ?? video.likes,
                }
              : video,
          ),
        );
      }
      // Invalidate any cached reels lists so stale is_liked doesn't return
      api.invalidateCache?.('/reels/');
    } catch (error) {
      // Revert optimistic update on failure
      setVideos((prev) =>
        prev.map((video) =>
          video.id === videoId
            ? {
                ...video,
                liked: !video.liked,
                likes: video.liked ? video.likes - 1 : video.likes + 1,
              }
            : video,
        ),
      );
    }
  };

  const handleSave = async (videoId) => {
    if (!user) {
      onRequireAuth();
      return;
    }

    try {
      const response = await api.request(`/reels/${videoId}/save/`, {
        method: 'POST',
      });

      if (response.saved !== undefined) {
        setVideos((prev) =>
          prev.map((video) =>
            video.id === videoId ? { ...video, saved: response.saved } : video,
          ),
        );
      }
    } catch (error) {
      console.error('Failed to save video:', error);
    }
  };

  // Store follow states separately to persist across video refreshes
  const [followStates, setFollowStates] = useState({});

  const handleFollow = async (userId) => {
    if (!user) {
      onRequireAuth();
      return;
    }

    // Optimistically update local state first
    const currentFollowing = followStates[userId] ?? videos.find(v => v.user?.id === userId)?.user?.is_following;
    const newFollowing = !currentFollowing;
    
    setFollowStates(prev => ({
      ...prev,
      [userId]: newFollowing
    }));

    try {
      const response = await api.request('/follows/toggle/', {
        method: 'POST',
        body: JSON.stringify({ following_id: userId }),
      });

      if (response.following !== undefined) {
        // Update the follow status in the videos
        setVideos((prev) =>
          prev.map((video) =>
            video.user?.id === userId
              ? {
                  ...video,
                  user: { ...video.user, is_following: response.following },
                }
              : video,
          ),
        );
        // Also update followStates to match server response
        setFollowStates(prev => ({
          ...prev,
          [userId]: response.following
        }));
      }
    } catch (error) {
      console.error('Failed to follow user:', error);
      // Revert on error
      setFollowStates(prev => ({
        ...prev,
        [userId]: currentFollowing
      }));
    }
  };

  const submitReport = async (videoId, category) => {
    setShowReportModal(null);
    try {
      await api.request('/reports/create/', {
        method: 'POST',
        body: JSON.stringify({
          reported_reel_id: videoId,
          report_type: category,
          description: `Reported as ${category}`,
        }),
      });
      setAlertModal({
        isOpen: true,
        title: 'Report Submitted',
        message: 'Thank you for your report. We will review it shortly.',
        type: 'success',
        onConfirm: null,
        showCancel: false,
      });
    } catch (error) {
      console.error('Failed to submit report:', error);
      setAlertModal({
        isOpen: true,
        title: 'Error',
        message: 'Failed to submit report. Please try again.',
        type: 'error',
        onConfirm: null,
        showCancel: false,
      });
    }
  };

  const handleNotInterested = async (videoId) => {
    setShowMenu(null);
    try {
      await api.request('/reels/not-interested/', {
        method: 'POST',
        body: JSON.stringify({ reel_id: videoId }),
      });
      // Remove video from feed locally too
      setVideos((prev) => prev.filter((v) => v.id !== videoId));
      setAlertModal({
        isOpen: true,
        title: 'Video Removed',
        message: "This video won't appear in your feed anymore.",
        type: 'info',
        onConfirm: null,
        showCancel: false,
      });
    } catch (error) {
      console.error('Failed to mark not interested:', error);
      // Still remove from local feed even if API fails
      setVideos((prev) => prev.filter((v) => v.id !== videoId));
    }
  };

  const handleShowVideoInfo = (video) => {
    setShowMenu(null);
    setAlertModal({
      isOpen: true,
      title: 'Video Information',
      message: `Creator: ${video.creator}\nLikes: ${video.likes}\nComments: ${video.comments}\nPosted: ${getRelativeTime(video.created_at)}`,
      type: 'info',
      onConfirm: null,
      showCancel: false,
    });
  };

  const handleShare = async (videoId) => {
    setShowMenu(null);
    const postUrl = `${window.location.origin}/post/${videoId}`;
    const video = videos.find((v) => String(v.id) === String(videoId));
    const title = (video?.caption || '').toString().slice(0, 80) || 'Check out this post on FlipStar';

    const showToast = (text) => {
      const toast = document.createElement('div');
      toast.textContent = text;
      toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.85);
        color: #fff;
        padding: 12px 24px;
        border-radius: 24px;
        font-size: 14px;
        font-weight: 600;
        z-index: 10000;
      `;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2000);
    };

    // 1) Native share sheet (mobile + modern browsers) — opens the OS share UI
    //    so the user can pick WhatsApp / Telegram / etc. and the recipient gets
    //    a real /post/<id> link that opens the specific reel.
    if (typeof navigator !== 'undefined' && navigator.share) {
      try {
        await navigator.share({ title, text: title, url: postUrl });
        try { await api.request(`/reels/${videoId}/share/`, { method: 'POST' }); } catch {}
        return;
      } catch (err) {
        if (err?.name === 'AbortError') return; // user dismissed the sheet
        // fall through to clipboard
      }
    }

    // 2) Clipboard fallback (desktop browsers without Web Share API)
    try {
      await navigator.clipboard.writeText(postUrl);
      showToast('🔗 Link copied!');
      try { await api.request(`/reels/${videoId}/share/`, { method: 'POST' }); } catch {}
      return;
    } catch (_) {
      // 3) Legacy fallback for very old browsers / insecure origins
      const ta = document.createElement('textarea');
      ta.value = postUrl;
      document.body.appendChild(ta);
      ta.select();
      try {
        document.execCommand('copy');
        showToast('🔗 Link copied!');
      } catch {
        showToast('Could not copy link');
      }
      document.body.removeChild(ta);
    }
  };

  // Long-press handlers for TikTok-style context menu (separate from 3-dots menu)
  const handleLongPressStart = (videoId, e) => {
    longPressTimer.current = setTimeout(() => {
      setShowMenu(null); // Close dropdown menu if open
      setLongPressMenu(videoId); // Show bottom sheet only
      // Haptic feedback on mobile if available
      if (navigator.vibrate) navigator.vibrate(50);
    }, 500); // 500ms for long press
  };

  const handleLongPressEnd = () => {
    if (longPressTimer.current) {
      clearTimeout(longPressTimer.current);
      longPressTimer.current = null;
    }
  };

  const handleLongPressMove = () => {
    // Cancel long press if user moves finger
    handleLongPressEnd();
  };

  // Download video/image - optimized size like TikTok
  const handleDownload = async (video) => {
    setLongPressMenu(null);
    setShowMenu(null);
    
    let mediaUrl = video.imageUrl?.startsWith('http') 
      ? video.imageUrl 
      : `${config.API_BASE_URL.replace('/api', '')}${video.imageUrl}`;
    
    const isVideo = mediaUrl.includes('.mp4') || mediaUrl.includes('.webm') || 
                    mediaUrl.includes('.mov') || mediaUrl.includes('video');
    
    try {
      // Show downloading toast
      const toast = document.createElement('div');
      toast.textContent = '⬇️ Preparing download...';
      toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 12px 24px;
        border-radius: 24px;
        font-size: 14px;
        font-weight: 600;
        z-index: 10000;
      `;
      document.body.appendChild(toast);
      
      const response = await fetch(mediaUrl);
      const blob = await response.blob();
      
      // Show file size in toast
      const sizeMB = (blob.size / (1024 * 1024)).toFixed(1);
      toast.textContent = `⬇️ Downloading (${sizeMB}MB)...`;
      
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `flipstar_${video.id}.${isVideo ? 'mp4' : 'jpg'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      window.URL.revokeObjectURL(url);
      
      toast.textContent = `✓ Downloaded (${sizeMB}MB)`;
      setTimeout(() => toast.remove(), 2000);
    } catch (err) {
      console.error('Download failed:', err);
      setAlertModal({
        isOpen: true,
        title: 'Download Failed',
        message: 'Could not download the video. Please try again.',
        type: 'error',
        onConfirm: null,
        showCancel: false,
      });
    }
  };

  // Save to favorites (bookmark)
  const handleSaveToFavorites = async (videoId) => {
    setLongPressMenu(null);
    setShowMenu(null);
    
    if (!user) {
      onRequireAuth();
      return;
    }
    
    try {
      await api.request(`/saved/`, {
        method: 'POST',
        body: JSON.stringify({ reel: videoId }),
      });
      
      // Show success toast
      const toast = document.createElement('div');
      toast.textContent = '⭐ Saved to favorites!';
      toast.style.cssText = `
        position: fixed;
        bottom: 80px;
        left: 50%;
        transform: translateX(-50%);
        background: rgba(0, 0, 0, 0.8);
        color: white;
        padding: 12px 24px;
        border-radius: 24px;
        font-size: 14px;
        font-weight: 600;
        z-index: 10000;
        animation: fadeInOut 2s ease-in-out;
      `;
      document.body.appendChild(toast);
      setTimeout(() => toast.remove(), 2000);
    } catch (err) {
      console.error('Save failed:', err);
    }
  };

  const handleHashtagClick = async (hashtag) => {
    try {
      const response = await api.request(`/reels/hashtag/${hashtag}/`);
      const results = response.results || response || [];

      const formattedVideos = results.map((reel) => ({
        id: reel.id,
        user: reel.user,
        creator: reel.user?.username || 'Unknown User',
        handle: `@${reel.user?.username || 'unknown'}`,
        avatar: '👤',
        caption: reel.caption,
        hashtags: reel.hashtags_list || [],
        likes: reel.votes || 0,
        comments: reel.comment_count || 0,
        shares: reel.shares || 0,
        gift_count: reel.gift_count || 0,
        imageUrl: reel.media || reel.image,
        liked: reel.is_liked || false,
        saved: reel.is_saved || false,
        created_at: reel.created_at,
        activeTab,
        is_campaign_post: reel.is_campaign_post || false,
        campaign_id: reel.campaign_id || null,
        campaign: reel.campaign || null,
      })); // Refetch when tab changes;
      setVideos(formattedVideos);
      setActiveTab(`hashtag-${hashtag}`);
    } catch (error) {
      console.error('Failed to search hashtag:', error);
      setAlertModal({
        isOpen: true,
        title: 'Error',
        message: 'Failed to load hashtag posts. Please try again.',
        type: 'error',
        onConfirm: null,
        showCancel: false,
      });
    }
  };

  useEffect(() => {
    fetchVideos();
  }, []);

  // Setup real-time listeners for post updates
  useEffect(() => {
    // Listen for new posts from other tabs
    const handleNewPost = (postData) => {
      console.log('New post received:', postData);
      // Clear cache and refresh feed to show new post
      try {
        localStorage.removeItem(`feed_cache_${activeTab}`);
        fetchVideos(1, false);
      } catch (error) {
        console.error('Error refreshing feed for new post:', error);
      }
    };

    // Listen for feed refresh requests
    const handleFeedRefresh = () => {
      console.log('Feed refresh requested');
      // Clear cache and refresh feed
      try {
        localStorage.removeItem(`feed_cache_${activeTab}`);
        fetchVideos(1, false);
      } catch (error) {
        console.error('Error refreshing feed:', error);
      }
    };

    // Add event listeners
    realtimeService.addEventListener('NEW_POST', handleNewPost);
    realtimeService.addEventListener('FEED_REFRESH', handleFeedRefresh);

    // Cleanup on unmount
    return () => {
      realtimeService.removeEventListener('NEW_POST', handleNewPost);
      realtimeService.removeEventListener('FEED_REFRESH', handleFeedRefresh);
    };
  }, [activeTab]);

  // Expose fetchVideos function so it can be called from parent
  useEffect(() => {
    window.refreshFeed = fetchVideos;
  }, []);

  // Sample user suggestions data
  const userSuggestions = [
    {
      id: 1,
      name: 'John Doe',
      handle: '@johndoe',
      avatar: '👨',
      followers: '10.5K',
    },
    {
      id: 2,
      name: 'Jane Smith',
      handle: '@janesmith',
      avatar: '👩',
      followers: '25.2K',
    },
    {
      id: 3,
      name: 'Mike Johnson',
      handle: '@mikejohnson',
      avatar: '🧑',
      followers: '8.7K',
    },
    {
      id: 4,
      name: 'Sarah Wilson',
      handle: '@sarahwilson',
      avatar: '👩',
      followers: '15.3K',
    },
    {
      id: 5,
      name: 'Fitness Coach',
      handle: '@fitnesscoachjohn',
      avatar: '💪',
      followers: '1.8M',
    },
  ];

  // Pull to refresh handlers
  const handleTouchStart = (e) => {
    const container = feedContainerRef.current || document.querySelector('.video-feed-container');
    if (container && container.scrollTop === 0) {
      touchStartY.current = e.touches[0].clientY;
    }
  };

  const handleTouchMove = (e) => {
    if (isRefreshing) return;
    const container = feedContainerRef.current || document.querySelector('.video-feed-container');
    if (!container) return;
    
    const scrollTop = container.scrollTop;
    if (scrollTop === 0 && touchStartY.current > 0) {
      const currentY = e.touches[0].clientY;
      const distance = Math.max(0, currentY - touchStartY.current);
      if (distance > 0) {
        // Don't preventDefault for passive listeners
        setPullDistance(Math.min(distance, PULL_THRESHOLD * 1.5));
      }
    }
  };

  const handleTouchEnd = async () => {
    if (pullDistance >= PULL_THRESHOLD && !isRefreshing) {
      setIsRefreshing(true);
      setPullDistance(PULL_THRESHOLD);
      // Clear cache and fetch fresh data
      try {
        localStorage.removeItem(CACHE_KEY(activeTab));
        setVideos([]);
        setPage(1);
        await fetchVideos(1, false);
      } catch (e) {
        console.error('Refresh error:', e);
      }
      setTimeout(() => {
        setIsRefreshing(false);
        setPullDistance(0);
      }, 500);
    } else {
      setPullDistance(0);
    }
    touchStartY.current = 0;
  };

  return (
    <div
      style={{
        display: 'flex',
        width: '100%',
        height: '100%',
        position: 'relative',
      }}
    >
      <style>{`
        .video-feed-container::-webkit-scrollbar { display: none; }
        .right-sidebar-container::-webkit-scrollbar { display: none; }
        .feed-action-icon > div > button { filter: drop-shadow(0 1px 8px rgba(0,0,0,0.95)) drop-shadow(0 0 3px rgba(0,0,0,0.8)); }
        .feed-action-icon > div > div:first-child { filter: drop-shadow(0 1px 8px rgba(0,0,0,0.95)) drop-shadow(0 0 3px rgba(0,0,0,0.8)); }
        .feed-action-label { text-shadow: 0 1px 5px rgba(0,0,0,0.95), 0 0 2px rgba(0,0,0,0.8) !important; color: #8fc441 !important; }
        .feed-top-icon { filter: drop-shadow(0 1px 6px rgba(0,0,0,0.95)) drop-shadow(0 0 2px rgba(0,0,0,0.8)); }
      `}</style>
      <div
        ref={feedContainerRef}
        className="video-feed video-feed-container"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        style={{
          flex: 1,
          overflowY: 'auto',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          background: T.bg || '#0D0D0D',
          scrollbarWidth: 'none',
          msOverflowStyle: 'none',
          position: 'relative',
          // Suppress the browser's native pull-to-refresh so our custom
          // in-app pull-to-refresh is the only one that fires.
          overscrollBehaviorY: 'contain',
          touchAction: 'pan-y',
          ...(isMobile ? { scrollSnapType: 'y mandatory', WebkitOverflowScrolling: 'touch' } : {}),
        }}
      >
        {/* Pull to refresh indicator */}
        {pullDistance > 0 && (
          <div style={{
            position: 'absolute',
            top: 0,
            left: 0,
            right: 0,
            height: pullDistance,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'linear-gradient(180deg, rgba(226,179,85,0.15) 0%, transparent 100%)',
            zIndex: 1000,
          }}>
            <div style={{
              width: 32,
              height: 32,
              borderRadius: '50%',
              border: '3px solid #8B5CF6',
              borderTopColor: 'transparent',
              animation: isRefreshing ? 'spin 0.8s linear infinite' : 'none',
              transform: `rotate(${(pullDistance / PULL_THRESHOLD) * 360}deg)`,
              transition: isRefreshing ? 'none' : 'transform 0.1s',
            }} />
          </div>
        )}
        
        <style>{`
          @keyframes spin {
            to { transform: rotate(360deg); }
          }
          @keyframes heartPop {
            0%   { transform: translate(-50%, -50%) scale(0.2) rotate(-15deg); opacity: 0; }
            15%  { transform: translate(-50%, -50%) scale(1.25) rotate(8deg);  opacity: 1; }
            35%  { transform: translate(-50%, -50%) scale(1.0)  rotate(-4deg); opacity: 1; }
            70%  { transform: translate(-50%, -50%) scale(1.05) rotate(0deg);  opacity: 1; }
            100% { transform: translate(-50%, -50%) scale(1.6)  rotate(0deg);  opacity: 0; }
          }
        `}</style>
      
        {/* Feed Header - desktop only; hiding on mobile fixes scroll-snap offset */}
        {!isMobile && <div
          style={{
            width: '100%',
            maxWidth: 600,
            padding: '0 20px',
            marginBottom: 20,
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              fontSize: 24,
              fontWeight: 700,
              color: '#000',
            }}
          >
            {activeTab === 'home' && 'Home'}
            {activeTab === 'reels' && 'Reels'}
            {activeTab === 'following' && 'Following'}
            {activeTab === 'inbox' && 'Messages'}
            {activeTab === 'bookmarks' && 'Saved'}
          </div>

          {/* Search Bar - Only on Explore Tab */}
          {activeTab === 'explore' && (
            <SearchBar
              onUserClick={(user) => {
                console.log('User clicked:', user);
              }}
              onPostClick={(post) => {
                console.log('Post clicked:', post);
              }}
            />
          )}
        </div>}

        {/* Messages tab is now handled by MessagesPage in App.jsx */}
        {activeTab === 'inbox' ? (
          <div style={{ width: '100%', maxWidth: 600, padding: '0 20px' }}>
            <div
              style={{
                background: T.cardBg,
                borderRadius: 16,
                padding: 60,
                textAlign: 'center',
                border: `1px solid ${T.border}`,
              }}
            >
              <div style={{ fontSize: 48, marginBottom: 16 }}>💬</div>
              <p style={{ fontSize: 14, color: T.sub, margin: 0 }}>
                Messaging is now available — use the Messages tab in the navigation.
              </p>
            </div>
          </div>
        ) : (
          <div
            className="video-list-container"
            style={{
              width: '100%',
              maxWidth: 600,
              display: 'flex',
              flexDirection: 'column',
              gap: 20,
              padding: '0 20px',
            }}
          >
            {!mounted || loading ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: isMobile ? 0 : 20 }}>
                {[0, 1].map(i => (
                  <div key={i} className="video-card-snap" style={{
                    background: '#111',
                    borderRadius: isMobile ? 0 : 12,
                    overflow: 'hidden',
                    height: isMobile ? 'calc(100dvh - 70px)' : 750,
                    width: isMobile ? '100vw' : '100%',
                    position: 'relative',
                  }}>
                    <div style={{
                      position: 'absolute', top: 0, left: 0, right: 0, bottom: 0,
                      background: 'linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.04) 50%, transparent 100%)',
                      animation: 'shimmer 1.5s infinite',
                    }} />
                    <div style={{ position: 'absolute', bottom: 80, left: 16, right: 70 }}>
                      <div style={{ width: 100, height: 14, background: 'rgba(255,255,255,0.12)', borderRadius: 7, marginBottom: 10 }} />
                      <div style={{ width: 180, height: 12, background: 'rgba(255,255,255,0.08)', borderRadius: 6, marginBottom: 6 }} />
                      <div style={{ width: 140, height: 12, background: 'rgba(255,255,255,0.05)', borderRadius: 6 }} />
                    </div>
                    <div style={{ position: 'absolute', bottom: 80, right: 12, display: 'flex', flexDirection: 'column', gap: 20, alignItems: 'center' }}>
                      {[0,1,2].map(j => (
                        <div key={j} style={{ width: 36, height: 36, borderRadius: '50%', background: 'rgba(255,255,255,0.1)' }} />
                      ))}
                    </div>
                  </div>
                ))}
                <style>{`@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}`}</style>
              </div>
            ) : videos.length === 0 ? (
              <div
                style={{
                  background: T.bg || '#0D0D0D',
                  borderRadius: 16,
                  padding: 60,
                  textAlign: 'center',
                  border: `1px solid ${T.border}`,
                }}
              >
                <div style={{ fontSize: 64, marginBottom: 20 }}>
                  {activeTab === 'following' && '👥'}
                  {activeTab === 'bookmarks' && '🔖'}
                  {activeTab === 'explore' && '🔍'}
                  {(activeTab === 'home' || activeTab === 'reels') && '🎬'}
                </div>
                <h3
                  style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: T.txt,
                    marginBottom: 8,
                  }}
                >
                  {activeTab === 'following' &&
                    'No posts from followed users yet'}
                  {activeTab === 'bookmarks' && 'No saved posts yet'}
                  {activeTab === 'explore' && 'No trending posts'}
                  {(activeTab === 'home' || activeTab === 'reels') && 'No videos yet'}
                </h3>
                <p style={{ fontSize: 14, color: T.sub, margin: 0 }}>
                  {activeTab === 'following' &&
                    'Follow creators to see their posts here'}
                  {activeTab === 'bookmarks' && 'Save posts to see them here'}
                  {activeTab === 'explore' &&
                    'Check back soon for trending content'}
                  {(activeTab === 'home' || activeTab === 'reels') && 'Be the first to post!'}
                </p>
              </div>
            ) : (
              videos.map((video) => (
                <div
                  key={video.id}
                  className="video-card-snap"
                  onTouchStart={(e) => {
                    // Only trigger long-press on mobile, not when tapping buttons
                    if (e.target.closest('button')) return;
                    handleLongPressStart(video.id, e);
                  }}
                  onTouchEnd={handleLongPressEnd}
                  onTouchMove={handleLongPressMove}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    // Always show bottom sheet style menu (same as mobile)
                    setLongPressMenu(video.id);
                  }}
                  style={{
                    background: isMobile ? (T.bg || '#0D0D0D') : 'transparent',
                    borderRadius: isMobile ? 0 : 12,
                    overflow: 'hidden',
                    aspectRatio: isMobile ? undefined : '9/16',
                    maxHeight: isMobile ? 'calc(100dvh - 70px)' : 750,
                    height: isMobile ? 'calc(100dvh - 70px)' : 'auto',
                    minHeight: isMobile ? 'calc(100dvh - 70px)' : undefined,
                    width: isMobile ? '100vw' : '100%',
                    position: 'relative',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: isMobile ? 0 : 20,
                    scrollSnapAlign: isMobile ? 'start' : undefined,
                    scrollSnapStop: isMobile ? 'always' : undefined,
                    flexShrink: isMobile ? 0 : undefined,
                  }}
                >
                  {/* Mobile top overlay: Bell (left) + MoreVertical (right) */}
                  {isMobile && (
                    <div
                      style={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        zIndex: 20,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        padding: '12px 14px',
                        paddingTop: 'max(12px, env(safe-area-inset-top))',
                        background: 'none',
                        pointerEvents: 'none',
                      }}
                    >
                      <button
                        onClick={() => {
                          if (!user) { onRequireAuth(); return; }
                          onShowNotifications?.();
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 6,
                          pointerEvents: 'all',
                          position: 'relative',
                        }}
                      >
                        <Bell size={26} color="#8fc441" strokeWidth={2} className="feed-top-icon" />
                        {unreadNotifCount > 0 && (
                          <div style={{
                            position: 'absolute', top: 0, right: 0,
                            minWidth: 16, height: 16, borderRadius: 8,
                            background: '#EF4444', color: '#fff',
                            fontSize: 9, fontWeight: 800,
                            display: 'flex', alignItems: 'center', justifyContent: 'center',
                            padding: '0 3px', boxSizing: 'border-box',
                            border: '1.5px solid rgba(0,0,0,0.4)', lineHeight: 1,
                          }}>
                            {unreadNotifCount > 99 ? '99+' : unreadNotifCount}
                          </div>
                        )}
                      </button>
                      <div style={{ position: 'relative' }}>
                        <button
                          onClick={() => setShowMenu(showMenu === video.id ? null : video.id)}
                          style={{
                            background: 'none',
                            border: 'none',
                            cursor: 'pointer',
                            padding: 6,
                            pointerEvents: 'all',
                            filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))',
                          }}
                        >
                          <MoreVertical size={26} color="#8fc441" strokeWidth={2.5} />
                        </button>

                        {/* Mobile 3-Dots Dropdown Menu - Top right like desktop */}
                        {showMenu === video.id && (
                          <>
                            {/* Backdrop to close menu */}
                            <div
                              onClick={() => setShowMenu(null)}
                              style={{
                                position: 'fixed',
                                top: 0,
                                left: 0,
                                right: 0,
                                bottom: 0,
                                zIndex: 998,
                              }}
                            />
                            <div
                              onClick={(e) => e.stopPropagation()}
                              style={{
                                position: 'absolute',
                                top: 40,
                                right: 0,
                                background: T.cardBg,
                                borderRadius: 12,
                                border: `1px solid ${T.border}`,
                                boxShadow: '0 4px 20px rgba(0,0,0,0.25)',
                                minWidth: 180,
                                zIndex: 999,
                                overflow: 'hidden',
                              }}
                            >
                              <button
                                onClick={() => handleShare(video.id)}
                                style={{
                                  width: '100%',
                                  padding: '14px 16px',
                                  background: 'none',
                                  border: 'none',
                                  textAlign: 'left',
                                  fontSize: 14,
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 12,
                                  color: T.txt,
                                }}
                              >
                                <ShareIconFilled size={18} color="#8fc441" /> Share
                              </button>
                              <button
                                onClick={() => handleNotInterested(video.id)}
                                style={{
                                  width: '100%',
                                  padding: '14px 16px',
                                  background: 'none',
                                  border: 'none',
                                  textAlign: 'left',
                                  fontSize: 14,
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 12,
                                  color: T.txt,
                                }}
                              >
                                <EyeOff size={18} style={{ color: '#78716C' }} /> Not Interested
                              </button>
                              <button
                                onClick={() => { setShowMenu(null); setShowReportModal(video.id); }}
                                style={{
                                  width: '100%',
                                  padding: '14px 16px',
                                  background: 'none',
                                  border: 'none',
                                  textAlign: 'left',
                                  fontSize: 14,
                                  cursor: 'pointer',
                                  display: 'flex',
                                  alignItems: 'center',
                                  gap: 12,
                                  color: '#EF4444',
                                  fontWeight: 600,
                                }}
                              >
                                <AlertTriangle size={18} color="#EF4444" /> Report
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Long-Press Menu - TikTok-style full menu (works on both mobile and desktop) */}
                  {longPressMenu === video.id && (
                    <div
                      onClick={() => setLongPressMenu(null)}
                      style={{
                        position: 'fixed',
                        top: 0,
                        left: 0,
                        right: 0,
                        bottom: 0,
                        background: 'rgba(0,0,0,0.5)',
                        zIndex: 9999,
                        display: 'flex',
                        alignItems: 'flex-end',
                        justifyContent: 'center',
                      }}
                    >
                      <div
                        onClick={(e) => e.stopPropagation()}
                        style={{
                          width: '100%',
                          maxWidth: 480,
                          background: T.cardBg,
                          borderRadius: '20px 20px 0 0',
                          padding: '8px 0 40px',
                          paddingBottom: 'max(40px, env(safe-area-inset-bottom, 40px))',
                          boxShadow: '0 -4px 24px rgba(0,0,0,0.15)',
                        }}
                      >
                        <div style={{ width: 36, height: 4, background: '#E7E5E4', borderRadius: 4, margin: '12px auto 16px' }} />
                        {/* TikTok-style grid of action icons */}
                        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, padding: '8px 16px 16px' }}>
                          {[
                            { icon: Link, label: 'Copy Link', color: T.pri, action: () => { setLongPressMenu(null); handleShare(video.id); } },
                            { icon: Bookmark, label: 'Save', color: '#8fc441', action: () => handleSaveToFavorites(video.id) },
                            { icon: Download, label: 'Download', color: '#10B981', action: () => handleDownload(video) },
                            { icon: ShareIconFilled, label: 'Share', color: '#8fc441', action: () => { setLongPressMenu(null); handleShare(video.id); } },
                          ].map((item, idx) => (
                            <button
                              key={idx}
                              onClick={item.action}
                              style={{
                                display: 'flex',
                                flexDirection: 'column',
                                alignItems: 'center',
                                gap: 6,
                                padding: '12px 8px',
                                background: 'none',
                                border: 'none',
                                cursor: 'pointer',
                              }}
                            >
                              <div style={{
                                width: 48,
                                height: 48,
                                borderRadius: '50%',
                                background: `${item.color}15`,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                              }}>
                                <item.icon size={22} color={item.color} />
                              </div>
                              <span style={{ fontSize: 11, color: T.txt, fontWeight: 500 }}>{item.label}</span>
                            </button>
                          ))}
                        </div>
                        {/* Divider */}
                        <div style={{ height: 1, background: T.border, margin: '4px 16px 8px' }} />
                        {/* List options */}
                        <button
                          onClick={() => { setLongPressMenu(null); handleNotInterested(video.id); }}
                          style={{
                            width: '100%',
                            padding: '14px 24px',
                            background: 'none',
                            border: 'none',
                            textAlign: 'left',
                            fontSize: 15,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 14,
                            color: T.txt,
                          }}
                        >
                          <EyeOff size={20} style={{ color: '#78716C' }} /> Not Interested
                        </button>
                        <button
                          onClick={() => { setLongPressMenu(null); setShowReportModal(video.id); }}
                          style={{
                            width: '100%',
                            padding: '14px 24px',
                            background: 'none',
                            border: 'none',
                            textAlign: 'left',
                            fontSize: 15,
                            cursor: 'pointer',
                            display: 'flex',
                            alignItems: 'center',
                            gap: 14,
                            color: '#EF4444',
                          }}
                        >
                          <AlertTriangle size={20} /> Report
                        </button>
                        <button
                          onClick={() => setLongPressMenu(null)}
                          style={{
                            width: '100%',
                            padding: '14px 24px',
                            marginTop: 8,
                            background: '#F5F5F4',
                            border: 'none',
                            textAlign: 'center',
                            fontSize: 15,
                            fontWeight: 600,
                            cursor: 'pointer',
                            color: T.txt,
                          }}
                        >
                          Cancel
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Video/Image Background */}
                  {video.imageUrl ? (
                    video.imageUrl.includes('.mp4') ||
                    video.imageUrl.includes('.webm') ||
                    video.imageUrl.includes('.ogg') ||
                    video.imageUrl.includes('.mov') ||
                    video.imageUrl.includes('video') ? (
                      <div
                        ref={(el) =>
                          (videoContainerRefs.current[video.id] = el)
                        }
                        data-video-id={video.id}
                        style={{
                          position: 'absolute',
                          top: 0,
                          left: 0,
                          right: 0,
                          bottom: 0,
                        }}
                      >
                        {/* Blurred background for landscape videos */}
                        {videoOrientations[video.id] === 'landscape' && (
                          <div
                            style={{
                              position: 'absolute',
                              inset: 0,
                              backgroundImage: getVideoPoster(video.imageUrl)
                                ? `url(${getVideoPoster(video.imageUrl)})`
                                : 'none',
                              backgroundColor: '#111',
                              backgroundSize: 'cover',
                              backgroundPosition: 'center',
                              filter: 'blur(28px)',
                              transform: 'scale(1.15)',
                              zIndex: 0,
                            }}
                          />
                        )}
                        <video
                          key={video.id}
                          ref={(el) => (videoRefs.current[video.id] = el)}
                          src={
                            !video.imageUrl
                              ? undefined
                              : video.imageUrl.startsWith('http')
                                ? video.imageUrl
                                : `${config.API_BASE_URL.replace('/api', '')}${video.imageUrl}`
                          }
                          poster={getVideoPoster(video.imageUrl)}
                          preload={
                            videos.indexOf(video) === 0
                              ? 'metadata'
                              : visibleVideos[video.id]
                                ? 'metadata'
                                : 'none'
                          }
                          loop
                          playsInline
                          autoPlay
                          muted={true}
                          onLoadedMetadata={(e) => {
                            const w = e.target.videoWidth;
                            const h = e.target.videoHeight;
                            if (w && h) {
                              const orient = w > h ? 'landscape' : 'portrait';
                              setVideoOrientations(prev => {
                                const next = { ...prev, [video.id]: orient };
                                try { localStorage.setItem('_vidOrient', JSON.stringify(next)); } catch {}
                                return next;
                              });
                            }
                          }}
                          onLoadedData={(e) => {
                            // keep whatever muted state was set by the playback logic
                          }}
                          onError={(e) => {
                            const code = e.target?.error?.code;
                            if (code === 3 || code === 2) return;
                            e.target.style.display = 'none';
                            const placeholder = e.target.parentElement?.querySelector('.video-error-placeholder');
                            if (placeholder) placeholder.style.display = 'flex';
                          }}
                          style={{
                            position: 'relative',
                            zIndex: 1,
                            width: '100%',
                            height: '100%',
                            objectFit: videoOrientations[video.id] === 'landscape' ? 'contain' : 'cover',
                            objectPosition: 'center',
                            display: 'block',
                            background: 'transparent',
                          }}
                          onClick={() => handleVideoClick(video.id)}
                          onDoubleClick={() => handleVideoDoubleClick(video.id)}
                          onTouchEnd={() => handleVideoTouchEnd(video.id)}
                        >
                          Your browser does not support the video tag.
                        </video>
                        <div
                          className="video-error-placeholder"
                          style={{
                            display: 'none',
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            height: '100%',
                            background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            color: '#8fc441',
                          }}
                        >
                          <span style={{ fontSize: 48, marginBottom: 10 }}>🎬</span>
                          <span style={{ fontSize: 14, opacity: 0.7 }}>Video unavailable</span>
                        </div>

                        {/* Text Overlays from creator */}
                        {video.overlayText && video.overlayText.length > 0 && video.overlayText.map((ov, idx) => (
                          <div
                            key={idx}
                            style={{
                              position: 'absolute',
                              left: `${ov.x || 50}%`,
                              top: `${ov.y || 50}%`,
                              transform: 'translate(-50%, -50%)',
                              pointerEvents: 'none',
                              zIndex: 15,
                            }}
                          >
                            <span style={{
                              fontSize: `${ov.fontSize || 22}px`,
                              fontWeight: 800,
                              color: ov.color || '#fff',
                              textShadow: '0 2px 8px rgba(0,0,0,0.8), 0 0 4px rgba(0,0,0,0.5)',
                              background: 'rgba(0,0,0,0.3)',
                              padding: '4px 12px',
                              borderRadius: 8,
                              whiteSpace: 'pre-wrap',
                              maxWidth: '260px',
                              display: 'inline-block',
                              lineHeight: 1.2,
                              textAlign: ov.align || 'center',
                            }}>
                              {ov.text}
                            </span>
                          </div>
                        ))}

                        {/* Double-tap heart animation */}
                        {doubleTapLike[video.id] && (
                          <div
                            key={doubleTapLike[video.id]}
                            onAnimationEnd={() => setDoubleTapLike((prev) => ({ ...prev, [video.id]: 0 }))}
                            style={{
                              position: 'absolute',
                              top: '50%',
                              left: '50%',
                              transform: 'translate(-50%, -50%)',
                              animation: 'heartPop 0.7s ease-out forwards',
                              pointerEvents: 'none',
                              zIndex: 100,
                              willChange: 'transform, opacity',
                            }}
                          >
                            <Heart size={100} fill="#ff2e63" stroke="none" style={{ filter: 'drop-shadow(0 0 12px rgba(255,46,99,0.6))' }} />
                          </div>
                        )}

                        {/* Pause Icon - Persistent when paused */}
                        {showPauseIcon[video.id] && !playingVideos[video.id] && (
                          <div
                            style={{
                              position: 'absolute',
                              top: '50%',
                              left: '50%',
                              transform: 'translate(-50%, -50%)',
                              pointerEvents: 'none',
                              zIndex: 50,
                            }}
                          >
                            <div
                              style={{
                                background: 'rgba(0, 0, 0, 0.75)',
                                backdropFilter: 'blur(10px)',
                                borderRadius: '50%',
                                width: isMobile ? 70 : 100,
                                height: isMobile ? 70 : 100,
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                boxShadow: isMobile 
                                  ? '0 4px 16px rgba(0, 0, 0, 0.4)' 
                                  : '0 8px 32px rgba(0, 0, 0, 0.4)',
                                border: isMobile 
                                  ? '2px solid rgba(255, 255, 255, 0.2)' 
                                  : '3px solid rgba(255, 255, 255, 0.2)',
                              }}
                            >
                              <Pause
                                size={isMobile ? 32 : 48}
                                strokeWidth={2.5}
                                color="#ffffff"
                                fill="#ffffff"
                                style={{
                                  filter: 'drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3))',
                                }}
                              />
                            </div>
                          </div>
                        )}
                      </div>
                    ) : (
                      <>
                        <img
                          src={
                            video.imageUrl.startsWith('http')
                              ? video.imageUrl
                              : `${config.API_BASE_URL.replace('/api', '')}${video.imageUrl}`
                          }
                          alt={video.caption}
                          style={{
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            height: '100%',
                            objectFit: 'cover',
                            objectPosition: 'center',
                            display: 'block',
                            background: '#000',
                          }}
                          onError={(e) => {
                            e.target.style.display = 'none';
                            const placeholder = e.target.nextElementSibling;
                            if (placeholder) placeholder.style.display = 'flex';
                          }}
                          onDoubleClick={() => handleVideoDoubleClick(video.id)}
                          onTouchEnd={() => handleVideoTouchEnd(video.id)}
                        />
                        <div
                          style={{
                            display: 'none',
                            position: 'absolute',
                            top: 0,
                            left: 0,
                            width: '100%',
                            height: '100%',
                            background: 'linear-gradient(135deg, #1a1a2e 0%, #16213e 100%)',
                            alignItems: 'center',
                            justifyContent: 'center',
                            flexDirection: 'column',
                            color: '#8fc441',
                          }}
                        >
                          <span style={{ fontSize: 48, marginBottom: 10 }}>📷</span>
                          <span style={{ fontSize: 14, opacity: 0.7 }}>Image unavailable</span>
                        </div>
                      </>
                    )
                  ) : (
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        justifyContent: 'center',
                        height: '100%',
                        color: '#fff',
                      }}
                    >
                      🎬
                    </div>
                  )}

                  {/* Three Dots Menu - Top Right (Desktop) */}
                  {!isMobile && (
                    <div
                      style={{
                        position: 'absolute',
                        top: 10,
                        right: 10,
                        zIndex: 10,
                      }}
                    >
                      <button
                        onClick={() => setShowMenu(video.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          cursor: 'pointer',
                          padding: 6,
                          color: '#8fc441',
                          filter: 'drop-shadow(0 2px 4px rgba(0,0,0,0.5))',
                        }}
                      >
                        <MoreVertical size={24} strokeWidth={2.5} />
                      </button>

                      {/* Dropdown Menu */}
                      {showMenu === video.id && (
                        <div
                          style={{
                            position: 'absolute',
                            top: 50,
                            right: 0,
                            background: T.cardBg,
                            borderRadius: 8,
                            border: `1px solid ${T.border}`,
                            boxShadow: '0 4px 12px rgba(0,0,0,0.15)',
                            minWidth: 200,
                            zIndex: 1000,
                          }}
                        >
                          <button
                            onClick={() => handleShowVideoInfo(video)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: T.txt,
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#f5f5f5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Info size={16} />
                            Post Info
                          </button>
                          <button
                            onClick={() => handleShare(video.id)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: T.txt,
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#f5f5f5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Link size={16} />
                            Copy Link
                          </button>
                          <button
                            onClick={() => handleSaveToFavorites(video.id)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: T.txt,
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#f5f5f5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Bookmark size={16} />
                            Save to Favorites
                          </button>
                          <button
                            onClick={() => handleDownload(video)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: T.txt,
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#f5f5f5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Download size={16} />
                            Download
                          </button>
                          <div style={{ height: 1, background: T.border, margin: '4px 0' }} />
                          <button
                            onClick={() => handleNotInterested(video.id)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: T.txt,
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#f5f5f5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Flag size={16} />
                            Not Interested
                          </button>
                          <button
                            onClick={() => setShowReportModal(video.id)}
                            style={{
                              width: '100%',
                              padding: '12px 16px',
                              border: 'none',
                              background: 'none',
                              textAlign: 'left',
                              cursor: 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: 8,
                              fontSize: 14,
                              color: '#e74c3c',
                            }}
                            onMouseEnter={(e) =>
                              (e.target.style.background = '#ffe5e5')
                            }
                            onMouseLeave={(e) =>
                              (e.target.style.background = 'none')
                            }
                          >
                            <Flag size={16} />
                            Report
                          </button>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Creator Info - Bottom Left */}
                  <div
                    style={{
                      position: 'absolute',
                      bottom: 20,
                      left: 20,
                      color: '#fff',
                      textShadow: '0 1px 3px rgba(0,0,0,0.5)',
                      zIndex: 20,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        marginBottom: 8,
                      }}
                    >
                      <span
                        onClick={() => {
                          if (!user) { onRequireAuth(); return; }
                          onShowProfile?.(video.user?.id);
                        }}
                        style={{
                          fontSize: 16,
                          fontWeight: 700,
                          cursor: 'pointer',
                          textDecoration: 'underline',
                          textDecorationColor: 'rgba(255,255,255,0.5)',
                        }}
                      >
                        {video.creator}
                      </span>
                      {user && video.user?.id !== user.id && (
                        <button
                          onClick={() => handleFollow(video.user?.id)}
                          style={{
                            background: (followStates[video.user?.id] ?? video.user?.is_following)
                              ? `${T.pri}26`
                              : T.pri,
                            color: (followStates[video.user?.id] ?? video.user?.is_following) ? T.pri : '#000',
                            border: (followStates[video.user?.id] ?? video.user?.is_following)
                              ? `1.5px solid ${T.pri}99`
                              : 'none',
                            borderRadius: 14,
                            padding: '2px 10px',
                            fontSize: 11,
                            fontWeight: 700,
                            cursor: 'pointer',
                            letterSpacing: 0.3,
                            boxShadow: (followStates[video.user?.id] ?? video.user?.is_following)
                              ? 'none'
                              : `0 2px 8px ${T.pri}73`,
                            transition: 'all 0.2s ease',
                            backdropFilter: (followStates[video.user?.id] ?? video.user?.is_following) ? 'blur(8px)' : 'none',
                            WebkitBackdropFilter: (followStates[video.user?.id] ?? video.user?.is_following) ? 'blur(8px)' : 'none',
                          }}
                        >
                          {(followStates[video.user?.id] ?? video.user?.is_following) ? 'Following' : 'Follow'}
                        </button>
                      )}
                    </div>
                    <div
                      style={{
                        fontSize: 14,
                        marginBottom: 8,
                      }}
                    >
                      <CaptionWithLessMore caption={video.caption} />
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        opacity: 0.8,
                      }}
                    >
                      {getRelativeTime(video.created_at)}
                    </div>
                    {/* Hashtags */}
                    {video.hashtags && video.hashtags.length > 0 && (
                      <div
                        style={{
                          display: 'flex',
                          flexWrap: 'wrap',
                          gap: 8,
                          marginTop: 8,
                        }}
                      >
                        {video.hashtags.map((tag, index) => (
                          <span
                            key={index}
                            onClick={() => handleHashtagClick(tag)}
                            style={{
                              fontSize: 12,
                              color: '#3498db',
                              cursor: 'pointer',
                              textDecoration: 'underline',
                            }}
                          >
                            #{tag}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Actions - Right Side */}
                  <div
                    style={{
                      position: 'absolute',
                      right: 20,
                      bottom: 20,
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 20,
                      alignItems: 'center',
                      zIndex: 20,
                    }}
                    className="feed-action-icon"
                  >
                    {/* Like Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <LikeButton
                        liked={video.liked}
                        count={video.likes === 0 ? '' : video.likes}
                        onLike={() => handleLike(video.id)}
                        size={32}
                        isCampaign={!!(video.is_campaign_post || video.campaign_id || video.campaign)}
                      />
                    </div>

                    {/* Volume Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <button
                        onClick={toggleAudio}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        {audioEnabled ? (
                          <Volume2 size={32} color="#8fc441" strokeWidth={2} />
                        ) : (
                          <VolumeX size={32} color="#8fc441" strokeWidth={2} />
                        )}
                      </button>
                      <div
                        className="feed-action-label"
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: '#8fc441',
                          textAlign: 'center',
                        }}
                      >
                        {audioEnabled ? 'On' : 'Off'}
                      </div>
                    </div>

                    {/* Comment Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <button
                        onClick={() => {
                          if (!user) {
                            onRequireAuth();
                            return;
                          }
                          // Prevent rapid clicking that causes React error #426
                          if (showComments === video.id) return;
                          setShowComments(video.id);
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        <MessageCircle size={32} color="#8fc441" fill="none" strokeWidth={2} />
                      </button>
                      <div
                        className="feed-action-label"
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: '#8fc441',
                          textAlign: 'center',
                        }}
                      >
                        {video.comments === 0 ? '' : video.comments}
                      </div>
                    </div>

                    {/* Share Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <button
                        onClick={() => handleShare(video.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        <ShareIconFilled size={32} color="#8fc441" />
                      </button>
                      <div
                        className="feed-action-label"
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: '#8fc441',
                          textAlign: 'center',
                        }}
                      >
                        {video.shares === 0 ? '' : video.shares}
                      </div>
                    </div>

                    {/* Gift Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <button
                        onClick={() => {
                          if (!user) {
                            onRequireAuth();
                            return;
                          }
                          setGiftReelId(video.id);
                          setShowGiftModal(video.user?.username);
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        <Gift size={32} color="#8fc441" fill="none" strokeWidth={2} />
                      </button>
                      <div
                        className="feed-action-label"
                        style={{
                          fontSize: 12,
                          fontWeight: 700,
                          color: '#8fc441',
                          textAlign: 'center',
                        }}
                      >
                        {video.gift_count === 0 ? '' : video.gift_count}
                      </div>
                    </div>

                    {/* Save Button */}
                    <div
                      style={{
                        display: 'flex',
                        flexDirection: 'column',
                        alignItems: 'center',
                        gap: 4,
                      }}
                    >
                      <button
                        onClick={() => handleSave(video.id)}
                        style={{
                          background: 'none',
                          border: 'none',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        <Bookmark
                          size={32}
                          color={video.saved ? T.pri : '#fff'}
                          fill={video.saved ? T.pri : 'none'}
                        />
                      </button>
                      <div
                        style={{
                          fontSize: 12,
                          fontWeight: 600,
                          color: video.saved ? T.pri : '#fff',
                          textShadow: '0 1px 3px rgba(0,0,0,0.5)',
                          textAlign: 'center',
                        }}
                      >
                        {video.saved ? 'Saved' : 'Save'}
                      </div>
                    </div>
                  </div>
                </div>
              ))
            )}
            
            {/* Loading more indicator */}
            {loadingMore && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  padding: '40px 0',
                  color: '#000',
                }}
              >
                <div style={{ fontSize: 14 }}>Loading more videos...</div>
              </div>
            )}
            
            {/* No more videos indicator — only shown for non-looping feeds.
                Loopable feeds (home/reels/explore) wrap around in
                `loadMoreVideos`, so this message would never make sense. */}
            {!hasMore && videos.length > 0 && !LOOPABLE_TABS.has(activeTab) && (
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'center',
                  alignItems: 'center',
                  padding: '40px 0',
                  color: '#666',
                }}
              >
                <div style={{ fontSize: 14 }}>You've reached the end</div>
              </div>
            )}
          </div>
        )}
      </div>


      {/* Comments Modal */}
      {showComments && (
        <div key={showComments}>
          <ModernCommentSection
            reelId={showComments}
            user={user}
            onClose={() => setShowComments(null)}
            onCommentPosted={handleCommentPosted}
            onShowProfile={(userId) => {
              handleShowProfile(userId);
            }}
            onShowCoinPurchase={onShowCoinPurchase}
          />
        </div>
      )}

      {/* Gift Modal */}
      {showGiftModal && (
        <GiftPage
          username={showGiftModal}
          reelId={giftReelId}
          onClose={() => {
            setShowGiftModal(null);
            setGiftReelId(null);
          }}
          onShowWallet={() => {
            setShowGiftModal(null);
            setGiftReelId(null);
            onShowWallet?.();
          }}
          onShowCoinPurchase={() => {
            setShowGiftModal(null);
            setGiftReelId(null);
            onShowCoinPurchase?.();
          }}
        />
      )}

      {/* Report Category Modal */}
      {showReportModal && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 10000,
          }}
          onClick={() => setShowReportModal(null)}
        >
          <div
            style={{
              background: T.bg || '#0D0D0D',
              borderRadius: 16,
              padding: '24px',
              maxWidth: 400,
              width: '90%',
              boxShadow: '0 8px 32px rgba(0,0,0,0.2)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3
              style={{
                fontSize: 20,
                fontWeight: 700,
                color: T.txt,
                marginBottom: 8,
              }}
            >
              Report Content
            </h3>
            <p
              style={{
                fontSize: 14,
                color: T.sub,
                marginBottom: 20,
              }}
            >
              Why are you reporting this content?
            </p>
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                gap: 8,
              }}
            >
              {[
                { id: 'spam', label: 'Spam or Misleading', icon: '⚠️' },
                {
                  id: 'inappropriate',
                  label: 'Inappropriate Content',
                  icon: '😢',
                },
                { id: 'violence', label: 'Violence or Dangerous', icon: '⚔️' },
                { id: 'hate_speech', label: 'Hate Speech', icon: '🚫' },
                { id: 'copyright', label: 'Copyright Violation', icon: '©️' },
                { id: 'other', label: 'Other', icon: 'Ⓜ' },
              ].map((category) => (
                <button
                  key={category.id}
                  onClick={() => submitReport(showReportModal, category.id)}
                  style={{
                    width: '100%',
                    padding: '14px 16px',
                    marginBottom: 8,
                    border: `1px solid ${T.border}`,
                    borderRadius: 8,
                    background: T.cardBg || '#1A1A1A',
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    fontSize: 14,
                    color: T.txt,
                    transition: 'background 0.2s',
                  }}
                  onMouseEnter={(e) => (e.target.style.background = 'rgba(226,179,85,0.12)')}
                  onMouseLeave={(e) => (e.target.style.background = T.cardBg || '#1A1A1A')}
                >
                  <span style={{ fontSize: 20 }}>{category.icon}</span>
                  <span style={{ fontWeight: 500 }}>{category.label}</span>
                </button>
              ))}

              <button
                onClick={() => setShowReportModal(null)}
                style={{
                  width: '100%',
                  padding: '12px',
                  marginTop: 12,
                  border: 'none',
                  borderRadius: 8,
                  background: T.border,
                  cursor: 'pointer',
                  fontSize: 14,
                  fontWeight: 600,
                  color: T.txt,
                }}
              >
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Alert Modal */}
      <AlertModal
        isOpen={alertModal.isOpen}
        onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
        onConfirm={alertModal.onConfirm}
        showCancel={alertModal.showCancel}
      />
    </div>
  );
});




