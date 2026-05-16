import { useState, useEffect } from "react";
import { VideoCard } from "./VideoCard";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

export function FeedPage({ tab }) {
  const T = useLegacyT();
  const [videos, setVideos] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadVideos();
  }, [tab]);

  const loadVideos = async () => {
    setLoading(true);
    try {
      console.log('[FEED] Loading reels from API...');
      const response = await api.request('/reels/');
      console.log('[FEED] API response:', response);
      
      const reels = response.results || response || [];
      console.log('[FEED] Reels count:', reels.length);
      
      // Transform reels to match VideoCard expected format
      const transformedVideos = reels.map(reel => {
        console.log('[FEED] Reel:', {
          id: reel.id,
          image: reel.image,
          media: reel.media,
          thumbnail: reel.thumbnail,
          user: reel.user?.username
        });
        return {
          id: reel.id,
          creator: reel.user?.username || reel.user?.first_name || 'User',
          handle: reel.user?.username || 'user',
          caption: reel.caption || '',
          likes: reel.votes || 0,
          comments: reel.comments_count || 0,
          shares: 0,
          image: reel.image,
          media: reel.media,
          thumbnail: reel.thumbnail,
          overlay_text: reel.overlay_text || '',
          user: reel.user,
        };
      });
      
      console.log('[FEED] Transformed videos:', transformedVideos);
      setVideos(transformedVideos);
    } catch (error) {
      console.error("[FEED] Error loading videos:", error);
      setVideos([]);
    } finally {
      setLoading(false);
    }
  };

  const handleLike = (videoId) => {
    setVideos(videos.map(v => 
      v.id === videoId ? { ...v, likes: v.likes + 1 } : v
    ));
  };

  const handleShare = (videoId) => {
    setVideos(videos.map(v => 
      v.id === videoId ? { ...v, shares: v.shares + 1 } : v
    ));
  };

  if (loading) {
    return (
      <div style={{
        flex: 1,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: T.bg,
        fontSize: 18,
        color: T.sub,
      }}>
        Loading feed...
      </div>
    );
  }

  if (videos.length === 0) {
    return (
      <div style={{
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        background: T.bg,
        padding: 40,
        textAlign: "center",
      }}>
        <div style={{ fontSize: 60, marginBottom: 20 }}>📹</div>
        <div style={{ fontSize: 20, fontWeight: 700, color: T.txt, marginBottom: 10 }}>
          No videos yet
        </div>
        <div style={{ fontSize: 14, color: T.sub }}>
          Create your first post to see it here!
        </div>
      </div>
    );
  }

  return (
    <div style={{
      flex: 1,
      overflowY: "auto",
      padding: "20px",
      background: T.bg,
    }}>
      {/* Header */}
      <div style={{
        marginBottom: 30,
        paddingBottom: 20,
        borderBottom: `1px solid ${T.border}`,
      }}>
        <div style={{ fontSize: 24, fontWeight: 800, color: T.txt }}>
          {tab === "feed" && "For You"}
          {tab === "following" && "Following"}
          {tab === "explore" && "Explore"}
          {tab === "likes" && "Your Likes"}
          {tab === "bookmarks" && "Bookmarks"}
        </div>
        <div style={{ fontSize: 14, color: T.sub, marginTop: 8 }}>
          {videos.length} video{videos.length !== 1 ? 's' : ''} found
        </div>
      </div>

      {/* Videos Grid */}
      <div style={{
        display: "grid",
        gridTemplateColumns: "repeat(auto-fill, minmax(300px, 1fr))",
        gap: 20,
      }}>
        {videos.map(video => (
          <VideoCard
            key={video.id}
            video={video}
            onLike={() => handleLike(video.id)}
            onShare={() => handleShare(video.id)}
          />
        ))}
      </div>

      {loading && (
        <div style={{ textAlign: "center", padding: 40, color: T.sub }}>
          <div style={{ fontSize: 40, marginBottom: 10 }}>⏳</div>
          <div>Loading videos...</div>
        </div>
      )}

      {!loading && videos.length === 0 && (
        <div style={{ textAlign: "center", padding: 40, color: T.sub }}>
          <div style={{ fontSize: 40, marginBottom: 10 }}>📭</div>
          <div>No videos yet</div>
        </div>
      )}
    </div>
  );
}




