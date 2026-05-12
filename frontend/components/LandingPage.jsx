import { useState, useEffect } from "react";
import { Play, Heart, MessageCircle, Share2, TrendingUp, Users, Zap, Trophy } from "lucide-react";
import api from "../api";
import { getRelativeTime } from "../utils/timeUtils";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import config from "../config";

export function LandingPage({ onLogin, onRegister, onShowCampaigns }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [posts, setPosts] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPosts();
  }, []);

  const fetchPosts = async () => {
    try {
      const data = await api.getReels();
      setPosts(data.slice(0, 6)); // Show first 6 posts
    } catch (error) {
      console.error("Failed to fetch posts:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: T.bg }}>
      {/* Hero Section */}
      <div style={{
        background: T.cardBg,
        padding: "100px 20px 80px",
        textAlign: "center",
        borderBottom: `1px solid ${T.border}`,
      }}>
        <div style={{ maxWidth: 800, margin: "0 auto" }}>
          <h1 style={{ 
            fontSize: 48, 
            fontWeight: 800, 
            marginBottom: 16,
            color: T.txt,
            letterSpacing: -0.5,
          }}>
            FlipStar
          </h1>
          <p style={{ fontSize: 18, color: T.sub, marginBottom: 32, lineHeight: 1.6, maxWidth: 500, margin: "0 auto 32px" }}>
            Share your story with the world. Create, connect, and discover content that matters.
          </p>
          <div style={{ display: "flex", gap: 12, justifyContent: "center", flexWrap: "wrap" }}>
            <button
              onClick={onRegister}
              style={{
                padding: "14px 32px",
                background: T.pri,
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                transition: "opacity 0.2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
              onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
            >
              {t('signUp')}
            </button>
            <button
              onClick={onLogin}
              style={{
                padding: "14px 32px",
                background: "transparent",
                color: T.txt,
                border: `1px solid ${T.border}`,
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
            >
              {t('login')}
            </button>
            <button
              onClick={onShowCampaigns}
              style={{
                padding: "14px 24px",
                background: T.cardBg,
                color: T.txt,
                border: `1px solid ${T.border}`,
                borderRadius: 8,
                fontSize: 15,
                fontWeight: 600,
                cursor: "pointer",
                display: "flex",
                alignItems: "center",
                gap: 8,
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
              onMouseLeave={(e) => e.currentTarget.style.background = T.cardBg}
            >
              <Trophy size={18} />
              {t('campaigns')}
            </button>
          </div>
        </div>
      </div>

      {/* Features Section - Simplified */}
      <div style={{ padding: "60px 20px", background: T.bg }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <div style={{ 
            display: "grid", 
            gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))", 
            gap: 24 
          }}>
            <div style={{
              padding: 24,
              borderRadius: 12,
              background: T.cardBg,
              border: `1px solid ${T.border}`,
            }}>
              <Play size={28} color={T.pri} style={{ marginBottom: 16 }} />
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: T.txt }}>
                Share Content
              </h3>
              <p style={{ fontSize: 13, color: T.sub, lineHeight: 1.5 }}>
                Upload videos and images with high-quality support
              </p>
            </div>

            <div style={{
              padding: 24,
              borderRadius: 12,
              background: T.cardBg,
              border: `1px solid ${T.border}`,
            }}>
              <Users size={28} color={T.pri} style={{ marginBottom: 16 }} />
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: T.txt }}>
                Connect
              </h3>
              <p style={{ fontSize: 13, color: T.sub, lineHeight: 1.5 }}>
                Follow friends and build your community
              </p>
            </div>

            <div style={{
              padding: 24,
              borderRadius: 12,
              background: T.cardBg,
              border: `1px solid ${T.border}`,
            }}>
              <Trophy size={28} color={T.pri} style={{ marginBottom: 16 }} />
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 8, color: T.txt }}>
                Compete
              </h3>
              <p style={{ fontSize: 13, color: T.sub, lineHeight: 1.5 }}>
                Join campaigns and win prizes
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Posts Preview Section */}
      <div style={{ padding: "60px 20px", background: T.bg }}>
        <div style={{ maxWidth: 900, margin: "0 auto" }}>
          <h2 style={{ fontSize: 24, fontWeight: 700, textAlign: "center", marginBottom: 8, color: T.txt }}>
            Trending Now
          </h2>
          <p style={{ textAlign: "center", fontSize: 14, color: T.sub, marginBottom: 32 }}>
            Discover popular content on FlipStar
          </p>
          
          {loading ? (
            <div style={{ textAlign: "center", padding: 40, color: T.sub }}>{t('loading')}</div>
          ) : (
            <div style={{ 
              display: "grid", 
              gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", 
              gap: 16 
            }}>
              {posts.map(post => (
                <div key={post.id} style={{
                  borderRadius: 8,
                  overflow: "hidden",
                  border: `1px solid ${T.border}`,
                  background: T.cardBg,
                  cursor: "pointer",
                  transition: "transform 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.transform = "translateY(-2px)";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.transform = "translateY(0)";
                }}
                >
                  {post.media || post.image ? (
                    <div style={{ aspectRatio: "1", background: T.bg, position: "relative" }}>
                      {(post.media?.match(/\.(mp4|webm|ogg)$/i) || post.media?.includes('video')) ? (
                        <video
                          src={post.media?.startsWith('http') ? post.media : `${config.API_BASE_URL.replace('/api', '')}${post.media}`}
                          style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        />
                      ) : (
                        <img
                          src={(post.media || post.image)?.startsWith('http') ? (post.media || post.image) : `${config.API_BASE_URL.replace('/api', '')}${post.media || post.image}`}
                          alt={post.caption}
                          style={{ width: "100%", height: "100%", objectFit: "cover" }}
                        />
                      )}
                    </div>
                  ) : (
                    <div style={{ aspectRatio: "1", background: T.bg, display: "flex", alignItems: "center", justifyContent: "center", fontSize: 32 }}>
                      🎬
                    </div>
                  )}
                  <div style={{ padding: 12 }}>
                    <div style={{ fontSize: 13, color: T.txt, marginBottom: 8, lineHeight: 1.4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                      {post.caption || t('noCaption') || "No caption"}
                    </div>
                    <div style={{ display: "flex", alignItems: "center", gap: 12, fontSize: 12, color: T.sub }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <Heart size={14} />
                        {post.votes || 0}
                      </div>
                      <div style={{ display: "flex", alignItems: "center", gap: 4 }}>
                        <MessageCircle size={14} />
                        {post.comment_count || 0}
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
          
          <div style={{ textAlign: "center", marginTop: 32 }}>
            <button
              onClick={onRegister}
              style={{
                padding: "12px 28px",
                background: T.pri,
                color: "#fff",
                border: "none",
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                transition: "opacity 0.2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
              onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
            >
              {t('signUp')}
            </button>
          </div>
        </div>
      </div>

      {/* CTA Section */}
      <div style={{
        padding: "60px 20px",
        background: T.cardBg,
        borderTop: `1px solid ${T.border}`,
        textAlign: "center",
      }}>
        <div style={{ maxWidth: 500, margin: "0 auto" }}>
          <h2 style={{ fontSize: 24, fontWeight: 700, marginBottom: 12, color: T.txt }}>
            Ready to join?
          </h2>
          <p style={{ fontSize: 14, color: T.sub, marginBottom: 24 }}>
            Start sharing your story today. It's free to get started.
          </p>
          <button
            onClick={onRegister}
            style={{
              padding: "14px 36px",
              background: T.pri,
              color: "#fff",
              border: "none",
              borderRadius: 8,
              fontSize: 15,
              fontWeight: 600,
              cursor: "pointer",
              transition: "opacity 0.2s",
            }}
            onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
            onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
          >
            Create Account
          </button>
        </div>
      </div>

      {/* Footer */}
      <div style={{
        padding: "24px 20px",
        background: "#fff",
        borderTop: `1px solid ${T.border}`,
        textAlign: "center",
      }}>
        <div style={{ fontSize: 12, color: T.sub }}>
          © 2025 FlipStar
        </div>
      </div>
    </div>
  );
}




