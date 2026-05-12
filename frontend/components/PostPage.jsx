import { useState } from "react";
import { ChevronLeft } from "lucide-react";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";
import realtimeService from "../services/RealtimeService";

export function PostPage({ user, onBack }) {
  const T = useLegacyT();
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [showSubscriptionModal, setShowSubscriptionModal] = useState(false);

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    console.log("File selected:", file);
    console.log("File type:", file?.type);
    console.log("File size:", file?.size);
    console.log("File name:", file?.name);
    
    if (file) {
      // Check if it's a video or image
      if (!file.type.startsWith('video/') && !file.type.startsWith('image/')) {
        alert("Please select a video or image file");
        return;
      }
      
      // Check file size (50MB limit)
      if (file.size > 50 * 1024 * 1024) {
        alert("File size must be less than 50MB");
        return;
      }
      
      setSelectedFile(file);
      
      // Handle different file types
      if (file.type.startsWith('video/')) {
        // For videos, create a thumbnail
        createVideoThumbnail(file);
      } else {
        // For images, use FileReader as before
        const reader = new FileReader();
        reader.onloadend = () => {
          setPreview(reader.result);
        };
        reader.readAsDataURL(file);
      }
    }
  };

  const createVideoThumbnail = (file) => {
    const video = document.createElement('video');
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    
    video.preload = 'metadata';
    video.src = URL.createObjectURL(file);
    
    video.onloadedmetadata = () => {
      // Set canvas dimensions to match video
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      
      // Seek to 1 second (or first frame if video is shorter)
      const seekTime = Math.min(1, video.duration);
      video.currentTime = seekTime;
    };
    
    video.onseeked = () => {
      // Draw the video frame to canvas
      ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
      
      // Convert canvas to blob and then to data URL
      canvas.toBlob((blob) => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setPreview(reader.result);
        };
        reader.readAsDataURL(blob);
      }, 'image/jpeg', 0.8);
      
      // Clean up the object URL
      URL.revokeObjectURL(video.src);
    };
    
    video.onerror = () => {
      console.error('Error loading video for thumbnail generation');
      // Fallback: use a generic video icon or first frame approach
      const reader = new FileReader();
      reader.onloadend = () => {
        setPreview(reader.result);
      };
      reader.readAsDataURL(file);
    };
  };

  const handleTestPost = async () => {
    console.log("Testing post without file...");
    try {
      // Create a simple text file for testing
      const testBlob = new Blob(['test content'], { type: 'text/plain' });
      const testFile = new File([testBlob], 'test.txt', { type: 'text/plain' });
      
      const formData = new FormData();
      formData.append("file", testFile);
      formData.append("caption", "Test post");
      
      console.log("Test FormData created");
      const response = await api.createPost(formData);
      console.log("Test post successful:", response);
      
      alert("Test post successful!");
      
      if (window.refreshFeed) {
        window.refreshFeed();
      }
      
      onBack();
    } catch (error) {
      console.error("Test post error:", error);
      alert("Test post failed: " + JSON.stringify(error));
    }
  };

  const handlePost = async () => {
    if (!selectedFile) {
      alert("Please select a video or image to post");
      return;
    }

    setIsUploading(true);
    
    try {
      console.log("Starting post upload...");
      console.log("Selected file:", selectedFile);
      console.log("Caption:", caption);
      
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("caption", caption);
      formData.append("hashtags", hashtags);
      
      console.log("FormData created, calling API...");
      const response = await api.createPost(formData);
      console.log("API response:", response);
      
      // Broadcast new post to all users for real-time updates
      if (response && response.id) {
        realtimeService.broadcastNewPost({
          id: response.id,
          user: user,
          caption: caption,
          media: response.media || response.image,
          created_at: response.created_at || new Date().toISOString()
        });
        
        // Also broadcast feed refresh to ensure all tabs update
        realtimeService.broadcastFeedRefresh();
      }
      
      alert("Post uploaded successfully!");
      
      // Reset form
      setCaption("");
      setHashtags("");
      setSelectedFile(null);
      setPreview(null);
      
      // Refresh the feed to show the new post
      if (window.refreshFeed) {
        console.log("Calling refreshFeed...");
        await window.refreshFeed();
      }
      
      // Redirect to reels page after successful upload
      if (window.navigateToReels) {
        console.log("Navigating to reels...");
        window.navigateToReels();
      } else {
        onBack();
      }
    } catch (error) {
      console.error("Upload error:", error);
      console.error("Error details:", JSON.stringify(error, null, 2));
      
      // Check if it's a subscription error
      if (error.error === 'Subscription required' || error.message?.includes('subscribe')) {
        setShowSubscriptionModal(true);
        return;
      }
      
      const errorMessage = typeof error === 'string' ? JSON.parse(error).error : error.message || 'Failed to upload post. Please try again.';
      alert(errorMessage);
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "linear-gradient(160deg, #fff7ed 0%, #fef3c7 50%, #ffedd5 100%)",
      zIndex: 4000,
      display: "flex",
      flexDirection: "column",
      overflowY: "auto",
    }}>
      {/* Decorative bg blobs */}
      <div style={{ position: "fixed", top: -80, right: -80, width: 260, height: 260, borderRadius: "50%", background: "radial-gradient(circle, rgba(217,155,42,0.18) 0%, transparent 70%)", pointerEvents: "none" }} />
      <div style={{ position: "fixed", bottom: -60, left: -60, width: 220, height: 220, borderRadius: "50%", background: "radial-gradient(circle, rgba(217,155,42,0.15) 0%, transparent 70%)", pointerEvents: "none" }} />

      {/* Back button */}
      <button
        onClick={onBack}
        style={{
          position: "absolute",
          top: 16,
          left: 16,
          background: "rgba(255,255,255,0.7)",
          border: "none",
          fontSize: 18,
          cursor: "pointer",
          color: "#92400e",
          padding: "6px 12px",
          zIndex: 10,
          lineHeight: 1,
          borderRadius: 10,
          backdropFilter: "blur(6px)",
          boxShadow: "0 2px 8px rgba(0,0,0,0.08)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
        }}
      >
        <ChevronLeft size={20} />
      </button>

      {!selectedFile ? (
        /* ── Selection screen ── */
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          padding: "100px 20px 40px",
          width: "100%",
          maxWidth: 480,
          margin: "0 auto",
        }}>
          {/* Camera hero icon */}
          <div style={{ position: "relative", marginBottom: 18 }}>
            <div style={{
              width: 88,
              height: 88,
              background: "linear-gradient(135deg, #f59e0b, #d97706)",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              boxShadow: "0 10px 30px rgba(217,155,42,0.4), 0 0 0 8px rgba(217,155,42,0.1)",
            }}>
              <img 
                src="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='%23D99B2A'%3E%3Cpath d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm5 11h-4v4h-2v-4H7v-2h4V7h2v4h4v2z'/%3E%3C/svg%3E"
                alt="Create"
                style={{
                  width: 38,
                  height: 38,
                  borderRadius: '50%',
                  objectFit: 'cover'
                }} 
              />
            </div>
            <div style={{
              position: "absolute",
              top: -4,
              right: -4,
              width: 28,
              height: 28,
              background: "linear-gradient(135deg, #fbbf24, #f59e0b)",
              borderRadius: "50%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              fontSize: 14,
              border: "2.5px solid #fff",
              boxShadow: "0 2px 8px rgba(251,191,36,0.5)",
            }}>
              ✦
            </div>
          </div>

          <div style={{ fontSize: 26, fontWeight: 800, color: "#1a1a2e", marginBottom: 6, letterSpacing: -0.5 }}>
            Create Post
          </div>
          <div style={{ fontSize: 14, color: "#6b7280", marginBottom: 32, textAlign: "center", lineHeight: 1.5 }}>
            Choose how you want to share your moment
          </div>

          {/* ── Large card 1: Take Image/Video ── */}
          <div
            onClick={() => document.getElementById("camera-input").click()}
            style={{
              width: "100%",
              borderRadius: 24,
              marginBottom: 16,
              background: "linear-gradient(145deg, #78350f 0%, #92400e 40%, #b45309 100%)",
              padding: "32px 28px",
              cursor: "pointer",
              position: "relative",
              overflow: "hidden",
              boxShadow: "0 12px 40px rgba(217,155,42,0.45)",
              transition: "transform 0.18s, box-shadow 0.18s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = "translateY(-3px)";
              e.currentTarget.style.boxShadow = "0 18px 50px rgba(217,155,42,0.55)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = "0 12px 40px rgba(217,155,42,0.45)";
            }}
          >
            {/* Decorative circles */}
            <div style={{ position: "absolute", top: -30, right: -30, width: 120, height: 120, borderRadius: "50%", background: "rgba(217,155,42,0.15)", pointerEvents: "none" }} />
            <div style={{ position: "absolute", bottom: -20, left: -20, width: 80, height: 80, borderRadius: "50%", background: "rgba(217,155,42,0.1)", pointerEvents: "none" }} />
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", position: "relative" }}>
              <div style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                background: "rgba(255,255,255,0.12)",
                border: "1.5px solid rgba(255,255,255,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: 16,
                backdropFilter: "blur(4px)",
              }}>
                <svg width="30" height="30" fill="none" viewBox="0 0 24 24">
                  <path d="M12 15.5A3.5 3.5 0 1 0 12 8.5a3.5 3.5 0 0 0 0 7z" fill="#fff"/>
                  <path d="M9 3L7.17 5H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-3.17L15 3H9z" stroke="#fff" strokeWidth="1.8" fill="none" strokeLinejoin="round"/>
                </svg>
              </div>
              <div style={{ fontSize: 19, fontWeight: 800, color: "#fff", marginBottom: 6, letterSpacing: -0.2 }}>
                Take Image/Video
              </div>
              <div style={{ fontSize: 13, color: "rgba(251,191,36,0.85)", lineHeight: 1.4 }}>
                Use your camera · Capture instantly
              </div>
            </div>
          </div>

          {/* ── Large card 2: Upload Image/Video ── */}
          <div
            onClick={() => document.getElementById("media-input").click()}
            style={{
              width: "100%",
              borderRadius: 24,
              background: "linear-gradient(145deg, #92400e 0%, #b45309 40%, #d97706 100%)",
              padding: "32px 28px",
              cursor: "pointer",
              position: "relative",
              overflow: "hidden",
              boxShadow: "0 12px 40px rgba(217,155,42,0.45)",
              transition: "transform 0.18s, box-shadow 0.18s",
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.transform = "translateY(-3px)";
              e.currentTarget.style.boxShadow = "0 18px 50px rgba(217,155,42,0.55)";
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.transform = "translateY(0)";
              e.currentTarget.style.boxShadow = "0 12px 40px rgba(217,155,42,0.45)";
            }}
          >
            {/* Decorative circles */}
            <div style={{ position: "absolute", top: -30, right: -30, width: 120, height: 120, borderRadius: "50%", background: "rgba(217,155,42,0.12)", pointerEvents: "none" }} />
            <div style={{ position: "absolute", bottom: -20, left: -20, width: 80, height: 80, borderRadius: "50%", background: "rgba(217,155,42,0.08)", pointerEvents: "none" }} />
            <div style={{ display: "flex", flexDirection: "column", alignItems: "center", textAlign: "center", position: "relative" }}>
              <div style={{
                width: 64,
                height: 64,
                borderRadius: "50%",
                background: "rgba(255,255,255,0.12)",
                border: "1.5px solid rgba(255,255,255,0.2)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                marginBottom: 16,
                backdropFilter: "blur(4px)",
              }}>
                <svg width="30" height="30" fill="none" viewBox="0 0 24 24">
                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <polyline points="17 8 12 3 7 8" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                  <line x1="12" y1="3" x2="12" y2="15" stroke="#fff" strokeWidth="2" strokeLinecap="round"/>
                </svg>
              </div>
              <div style={{ fontSize: 19, fontWeight: 800, color: "#fff", marginBottom: 6, letterSpacing: -0.2 }}>
                Upload Image/Video
              </div>
              <div style={{ fontSize: 13, color: "rgba(251,191,36,0.85)", lineHeight: 1.4 }}>
                From gallery · MP4, MOV, JPG, PNG
              </div>
            </div>
          </div>

          {/* Hidden file inputs */}
          <input id="camera-input" type="file" accept="image/*,video/*" capture="environment" onChange={handleFileSelect} style={{ display: "none" }} />
          <input id="media-input" type="file" accept="image/*,video/*" onChange={handleFileSelect} style={{ display: "none" }} />
        </div>
      ) : (
        /* ── Form screen (after file selected) ── */
        <div style={{ display: "flex", flexDirection: "column", flex: 1 }}>
          {/* Header */}
          <div style={{
            display: "flex",
            alignItems: "center",
            padding: "16px 20px",
            borderBottom: "1px solid #e0e4ff",
            background: "#fff",
            boxShadow: "0 1px 3px rgba(0,0,0,0.06)",
          }}>
            <div style={{ width: 40 }} />
            <div style={{ flex: 1, textAlign: "center", fontSize: 17, fontWeight: 700, color: "#1a1a2e" }}>
              New Post
            </div>
            <button
              onClick={handlePost}
              disabled={isUploading}
              style={{
                padding: "9px 22px",
                background: !isUploading ? "linear-gradient(135deg, #f59e0b, #d97706)" : "#e5e7eb",
                border: "none",
                borderRadius: 10,
                color: !isUploading ? "#fff" : "#9ca3af",
                fontSize: 14,
                fontWeight: 700,
                cursor: !isUploading ? "pointer" : "not-allowed",
                transition: "opacity 0.2s",
              }}
              onMouseEnter={(e) => { if (!isUploading) e.currentTarget.style.opacity = "0.88"; }}
              onMouseLeave={(e) => { if (!isUploading) e.currentTarget.style.opacity = "1"; }}
            >
              {isUploading ? "Posting..." : "Share"}
            </button>
          </div>

          <div style={{ flex: 1, overflowY: "auto", padding: "20px", maxWidth: 600, margin: "0 auto", width: "100%" }}>
            {/* Preview */}
            <div style={{
              width: "100%",
              aspectRatio: "1/1",
              background: "#f3f4f6",
              borderRadius: 16,
              overflow: "hidden",
              marginBottom: 20,
              position: "relative",
              border: "2px solid #e0e4ff",
            }}>
              <img
                src={preview}
                alt="Preview"
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
              <button
                onClick={() => { setSelectedFile(null); setPreview(null); }}
                style={{
                  position: "absolute",
                  top: 12,
                  right: 12,
                  background: "rgba(0,0,0,0.65)",
                  border: "none",
                  borderRadius: 8,
                  width: 32,
                  height: 32,
                  color: "#fff",
                  fontSize: 16,
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                }}
              >
                ✕
              </button>
            </div>

            {/* Caption */}
            <div style={{ marginBottom: 18 }}>
              <label style={{ fontSize: 13, fontWeight: 700, color: "#92400e", display: "block", marginBottom: 8 }}>Caption</label>
              <textarea
                placeholder="Write a caption..."
                value={caption}
                onChange={(e) => setCaption(e.target.value)}
                style={{
                  width: "100%",
                  minHeight: 90,
                  padding: "13px 14px",
                  border: "1.5px solid #e0e4ff",
                  borderRadius: 12,
                  fontSize: 14,
                  resize: "vertical",
                  outline: "none",
                  fontFamily: "inherit",
                  background: "#fff",
                  color: "#1a1a2e",
                  transition: "border-color 0.2s",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => e.currentTarget.style.borderColor = "#f59e0b"}
                onBlur={(e) => e.currentTarget.style.borderColor = "#e0e4ff"}
              />
            </div>

            {/* Hashtags */}
            <div style={{ marginBottom: 18 }}>
              <label style={{ fontSize: 13, fontWeight: 700, color: "#92400e", display: "block", marginBottom: 8 }}>Hashtags</label>
              <input
                type="text"
                placeholder="#fashion, #style, #trending"
                value={hashtags}
                onChange={(e) => setHashtags(e.target.value)}
                style={{
                  width: "100%",
                  padding: "13px 14px",
                  border: "1.5px solid #e0e4ff",
                  borderRadius: 12,
                  fontSize: 14,
                  outline: "none",
                  fontFamily: "inherit",
                  background: "#fff",
                  color: "#1a1a2e",
                  transition: "border-color 0.2s",
                  boxSizing: "border-box",
                }}
                onFocus={(e) => e.currentTarget.style.borderColor = "#f59e0b"}
                onBlur={(e) => e.currentTarget.style.borderColor = "#e0e4ff"}
              />
              <div style={{ fontSize: 12, color: "#9ca3af", marginTop: 5 }}>Separate with commas</div>
            </div>

            {/* Post Settings */}
            <div style={{ padding: "16px 20px", background: "#fff", borderRadius: 16, border: "1.5px solid #e0e4ff" }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: "#f59e0b", marginBottom: 14, textTransform: "uppercase", letterSpacing: 0.6 }}>Post Settings</div>
              <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
                {[["Allow comments"], ["Allow duets"], ["Allow stitches"]].map(([label]) => (
                  <div key={label} style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                    <span style={{ fontSize: 14, color: "#1a1a2e" }}>{label}</span>
                    <input type="checkbox" defaultChecked style={{ cursor: "pointer", width: 18, height: 18, accentColor: "#f59e0b" }} />
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Subscription Modal */}
      {showSubscriptionModal && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0,0,0,0.7)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 5000,
        }}>
          <div style={{
            background: T.cardBg,
            borderRadius: 16,
            padding: 32,
            maxWidth: 500,
            width: "90%",
          }}>
            <div style={{ fontSize: 22, fontWeight: 700, color: T.txt, marginBottom: 12, textAlign: "center" }}>🔒 Subscription Required</div>
            <div style={{ fontSize: 14, color: T.sub, marginBottom: 24, textAlign: "center", lineHeight: 1.6 }}>
              To upload videos and images, you need to subscribe to our Pro or Premium plan.
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 12, marginBottom: 20 }}>
              <div style={{
                padding: 20,
                background: T.bg,
                borderRadius: 12,
                border: `2px solid ${T.border}`,
              }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: T.txt, marginBottom: 4 }}>⭐ Pro Plan</div>
                <div style={{ fontSize: 13, color: T.sub, marginBottom: 16 }}>Upload unlimited videos & images</div>
                <button
                  onClick={async () => {
                    try {
                      await api.upgradeToProPlan();
                      alert("Successfully upgraded to Pro!");
                      setShowSubscriptionModal(false);
                    } catch (e) {
                      alert("Failed to upgrade: " + e.message);
                    }
                  }}
                  style={{
                    width: "100%",
                    padding: 12,
                    background: T.pri,
                    border: "none",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "opacity 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
                >
                  Upgrade to Pro
                </button>
              </div>
              <div style={{
                padding: 20,
                background: "linear-gradient(135deg, #FFD700, #FFA500)",
                borderRadius: 12,
              }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: "#000", marginBottom: 4 }}>💎 Premium Plan</div>
                <div style={{ fontSize: 13, color: "#333", marginBottom: 16 }}>All Pro features + priority support</div>
                <button
                  onClick={async () => {
                    try {
                      await api.upgradeToPremiumPlan();
                      alert("Successfully upgraded to Premium!");
                      setShowSubscriptionModal(false);
                    } catch (e) {
                      alert("Failed to upgrade: " + e.message);
                    }
                  }}
                  style={{
                    width: "100%",
                    padding: 12,
                    background: "#000",
                    border: "none",
                    borderRadius: 8,
                    color: "#fff",
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: "pointer",
                    transition: "opacity 0.2s",
                  }}
                  onMouseEnter={(e) => e.currentTarget.style.opacity = "0.9"}
                  onMouseLeave={(e) => e.currentTarget.style.opacity = "1"}
                >
                  Upgrade to Premium
                </button>
              </div>
            </div>
            <button
              onClick={() => setShowSubscriptionModal(false)}
              style={{
                width: "100%",
                padding: 12,
                background: "transparent",
                border: `1px solid ${T.border}`,
                borderRadius: 8,
                color: T.txt,
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
                transition: "background 0.2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.background = T.bg}
              onMouseLeave={(e) => e.currentTarget.style.background = "transparent"}
            >
              Maybe Later
            </button>
          </div>
        </div>
      )}
    </div>
  );
}




