import { useState, useRef } from "react";
import { ChevronLeft, Image as ImageIcon, Video, Hash, Type, Upload, X, Camera, Film } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import realtimeService from "../services/RealtimeService";

export function ModernPostPage({ user, onBack }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [caption, setCaption] = useState("");
  const [hashtags, setHashtags] = useState([]);
  const [hashtagInput, setHashtagInput] = useState("");
  const [selectedFile, setSelectedFile] = useState(null);
  const [isUploading, setIsUploading] = useState(false);
  const [preview, setPreview] = useState(null);
  const [fileType, setFileType] = useState(null);
  const [showCameraOptions, setShowCameraOptions] = useState(false);
  const videoRef = useRef(null);
  const photoRef = useRef(null);

  const handleHashtagInput = (e) => {
    const value = e.target.value;
    setHashtagInput(value);
    
    // Auto-add hashtag when user presses space or comma
    if (value.endsWith(' ') || value.endsWith(',')) {
      const tag = value.trim().replace(/[,\s]+$/, '');
      if (tag) {
        addHashtag(tag);
        setHashtagInput('');
      }
    }
  };

  const handleHashtagKeyDown = (e) => {
    if (e.key === 'Enter' && hashtagInput.trim()) {
      e.preventDefault();
      addHashtag(hashtagInput.trim());
      setHashtagInput('');
    } else if (e.key === 'Backspace' && !hashtagInput && hashtags.length > 0) {
      // Remove last hashtag if input is empty
      setHashtags(hashtags.slice(0, -1));
    }
  };

  const addHashtag = (tag) => {
    // Remove # if user added it, we'll add it ourselves
    const cleanTag = tag.replace(/^#+/, '');
    if (cleanTag && !hashtags.includes(cleanTag)) {
      setHashtags([...hashtags, cleanTag]);
    }
  };

  const removeHashtag = (index) => {
    setHashtags(hashtags.filter((_, i) => i !== index));
  };

  const handleFileSelect = (e) => {
    const file = e.target.files[0];
    
    if (file) {
      if (!file.type.startsWith('video/') && !file.type.startsWith('image/')) {
        alert("Please select a video or image file");
        return;
      }
      
      if (file.size > 50 * 1024 * 1024) {
        alert("File size must be less than 50MB");
        return;
      }
      
      setSelectedFile(file);
      setFileType(file.type.startsWith('video/') ? 'video' : 'image');
      
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

  const handleTakePhoto = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true });
      if (photoRef.current) {
        photoRef.current.srcObject = stream;
        photoRef.current.play();
        setShowCameraOptions('photo');
      }
    } catch (err) {
      alert("Unable to access camera. Please check permissions.");
      console.error(err);
    }
  };

  const handleCapturePhoto = () => {
    if (photoRef.current) {
      const canvas = document.createElement('canvas');
      canvas.width = photoRef.current.videoWidth;
      canvas.height = photoRef.current.videoHeight;
      const ctx = canvas.getContext('2d');
      ctx.drawImage(photoRef.current, 0, 0);
      
      canvas.toBlob((blob) => {
        const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        setSelectedFile(file);
        setFileType('image');
        setPreview(canvas.toDataURL('image/jpeg'));
        
        // Stop camera stream
        const stream = photoRef.current.srcObject;
        if (stream) {
          stream.getTracks().forEach(track => track.stop());
        }
        setShowCameraOptions(false);
      }, 'image/jpeg', 0.85);
    }
  };

  const handleRecordVideo = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.play();
        setShowCameraOptions('video');
      }
    } catch (err) {
      alert("Unable to access camera and microphone. Please check permissions.");
      console.error(err);
    }
  };

  let mediaRecorder = null;
  let recordedChunks = [];

  const handleStartRecording = () => {
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject;
      recordedChunks = [];
      
      try {
        mediaRecorder = new MediaRecorder(stream, { mimeType: 'video/webm' });
      } catch (e) {
        mediaRecorder = new MediaRecorder(stream);
      }
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          recordedChunks.push(event.data);
        }
      };
      
      mediaRecorder.onstop = () => {
        const blob = new Blob(recordedChunks, { type: 'video/webm' });
        const file = new File([blob], 'video.webm', { type: 'video/webm' });
        setSelectedFile(file);
        setFileType('video');
        createVideoThumbnail(file);
        
        // Stop camera stream
        const stream = videoRef.current.srcObject;
        if (stream) {
          stream.getTracks().forEach(track => track.stop());
        }
        setShowCameraOptions(false);
      };
      
      mediaRecorder.start();
    }
  };

  const handleStopRecording = () => {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
  };

  const handleCancelCamera = () => {
    if (photoRef.current && photoRef.current.srcObject) {
      const stream = photoRef.current.srcObject;
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    }
    if (videoRef.current && videoRef.current.srcObject) {
      const stream = videoRef.current.srcObject;
      if (stream) {
        stream.getTracks().forEach(track => track.stop());
      }
    }
    setShowCameraOptions(false);
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

  const handlePost = async () => {
    if (!selectedFile) {
      alert("Please select a video or image to post");
      return;
    }

    setIsUploading(true);
    
    try {
      const formData = new FormData();
      formData.append("file", selectedFile);
      formData.append("caption", caption);
      formData.append("hashtags", hashtags.join(','));
      
      const response = await api.createPost(formData);
      
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
      
      if (window.refreshFeed) {
        await window.refreshFeed();
      }
      
      onBack();
    } catch (error) {
      console.error("Upload error:", error);
      const errorMessage = error.message || 'Failed to upload post. Please try again.';
      alert(errorMessage);
    } finally {
      setIsUploading(false);
    }
  };

  const clearFile = () => {
    setSelectedFile(null);
    setPreview(null);
    setFileType(null);
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: "#fff",
      overflowY: "auto",
      zIndex: 200,
    }}>
      {/* Header */}
      <div style={{
        position: "sticky",
        top: 0,
        background: "#fff",
        borderBottom: `1px solid ${T.border}`,
        padding: "12px 20px",
        display: "flex",
        alignItems: "center",
        gap: 16,
        zIndex: 10,
      }}>
        <button
          onClick={onBack}
          disabled={isUploading}
          style={{
            background: "none",
            border: "none",
            cursor: isUploading ? "not-allowed" : "pointer",
            padding: 8,
            display: "flex",
            alignItems: "center",
            color: T.txt,
            opacity: isUploading ? 0.5 : 1,
          }}
        >
          <ChevronLeft size={24} />
        </button>
        <div style={{ flex: 1, fontSize: 18, fontWeight: 700, color: T.txt }}>
          Create Post
        </div>
        <button
          onClick={handlePost}
          disabled={isUploading || !selectedFile}
          style={{
            background: (!selectedFile || isUploading) ? T.sub : T.pri,
            border: "none",
            borderRadius: 8,
            padding: "8px 24px",
            color: "#fff",
            fontSize: 14,
            fontWeight: 700,
            cursor: (!selectedFile || isUploading) ? "not-allowed" : "pointer",
            display: "flex",
            alignItems: "center",
            gap: 6,
          }}
        >
          <Upload size={16} />
          {isUploading ? "Posting..." : "Post"}
        </button>
      </div>

      {/* Content */}
      <div style={{ padding: "20px", maxWidth: 800, margin: "0 auto" }}>
        {/* File Upload Area - Three Options */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 12 }}>
            Media
          </label>
          
          {!preview ? (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
              {/* Take Photo */}
              <button
                onClick={handleTakePhoto}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "32px 20px",
                  border: `2px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  background: T.bg,
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = T.pri;
                  e.currentTarget.style.background = T.pri + "10";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = T.border;
                  e.currentTarget.style.background = T.bg;
                }}
              >
                <div style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  background: T.pri + "20",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginBottom: 12,
                }}>
                  <Camera size={24} color={T.pri} />
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                  Take Photo
                </div>
                <div style={{ fontSize: 12, color: T.sub }}>
                  Use camera
                </div>
              </button>

              {/* Record Video */}
              <button
                onClick={handleRecordVideo}
                style={{
                  display: "flex",
                  flexDirection: "column",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "32px 20px",
                  border: `2px solid ${T.border}`,
                  borderRadius: 12,
                  cursor: "pointer",
                  background: T.bg,
                  transition: "all 0.2s",
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.borderColor = T.pri;
                  e.currentTarget.style.background = T.pri + "10";
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.borderColor = T.border;
                  e.currentTarget.style.background = T.bg;
                }}
              >
                <div style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  background: T.pri + "20",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginBottom: 12,
                }}>
                  <Film size={24} color={T.pri} />
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                  Record Video
                </div>
                <div style={{ fontSize: 12, color: T.sub }}>
                  Record up to 60s
                </div>
              </button>

              {/* Upload Photo/Video */}
              <label style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "center",
                padding: "32px 20px",
                border: `2px solid ${T.border}`,
                borderRadius: 12,
                cursor: "pointer",
                background: T.bg,
                transition: "all 0.2s",
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.borderColor = T.pri;
                e.currentTarget.style.background = T.pri + "10";
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.borderColor = T.border;
                e.currentTarget.style.background = T.bg;
              }}
              >
                <div style={{
                  width: 48,
                  height: 48,
                  borderRadius: "50%",
                  background: T.pri + "20",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  marginBottom: 12,
                }}>
                  <Upload size={24} color={T.pri} />
                </div>
                <div style={{ fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 4 }}>
                  Upload Photo/Video
                </div>
                <div style={{ fontSize: 12, color: T.sub }}>
                  From gallery (Max 50MB)
                </div>
                <input
                  type="file"
                  accept="video/*,image/*"
                  onChange={handleFileSelect}
                  style={{ display: "none" }}
                />
              </label>
            </div>
          ) : (
            <div style={{ position: "relative", borderRadius: 12, overflow: "hidden", background: "#000" }}>
              {fileType === 'video' ? (
                <video
                  src={preview}
                  controls
                  style={{
                    width: "100%",
                    maxHeight: 500,
                    objectFit: "contain",
                  }}
                />
              ) : (
                <img
                  src={preview}
                  alt="Preview"
                  style={{
                    width: "100%",
                    maxHeight: 500,
                    objectFit: "contain",
                  }}
                />
              )}
              <button
                onClick={clearFile}
                style={{
                  position: "absolute",
                  top: 12,
                  right: 12,
                  width: 36,
                  height: 36,
                  borderRadius: "50%",
                  background: "rgba(0,0,0,0.7)",
                  border: "none",
                  cursor: "pointer",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  color: "#fff",
                }}
              >
                <X size={20} />
              </button>
            </div>
          )}
        </div>

        {/* Caption */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 8 }}>
            <Type size={18} />
            Caption
          </label>
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="Write a caption..."
            rows={4}
            maxLength={2200}
            style={{
              width: "100%",
              padding: "12px 16px",
              border: `1px solid ${T.border}`,
              borderRadius: 8,
              fontSize: 14,
              outline: "none",
              resize: "vertical",
              fontFamily: "inherit",
              transition: "border 0.2s",
            }}
            onFocus={(e) => e.target.style.borderColor = T.pri}
            onBlur={(e) => e.target.style.borderColor = T.border}
          />
          <div style={{ fontSize: 11, color: T.sub, marginTop: 4, textAlign: "right" }}>
            {caption.length}/2200
          </div>
        </div>

        {/* Hashtags */}
        <div style={{ marginBottom: 24 }}>
          <label style={{ display: "block", fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 12 }}>
            <Hash size={16} style={{ display: "inline", marginRight: 4 }} />
            Hashtags
          </label>
          
          {/* Hashtag chips display */}
          <div style={{
            minHeight: 48,
            padding: "8px",
            border: `1px solid ${T.border}`,
            borderRadius: 8,
            display: "flex",
            flexWrap: "wrap",
            gap: 8,
            alignItems: "center",
            marginBottom: 8,
          }}>
            {hashtags.map((tag, index) => (
              <div
                key={index}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "6px 12px",
                  background: T.pri + "20",
                  borderRadius: 20,
                  fontSize: 13,
                  fontWeight: 500,
                  color: T.txt,
                }}
              >
                <span>#{tag}</span>
                <button
                  onClick={() => removeHashtag(index)}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    padding: 0,
                    display: "flex",
                    color: T.txt,
                    opacity: 0.6,
                  }}
                  onMouseEnter={(e) => e.target.style.opacity = 1}
                  onMouseLeave={(e) => e.target.style.opacity = 0.6}
                >
                  <X size={14} />
                </button>
              </div>
            ))}
            
            {/* Input for new hashtags */}
            <input
              type="text"
              value={hashtagInput}
              onChange={handleHashtagInput}
              onKeyDown={handleHashtagKeyDown}
              placeholder={hashtags.length === 0 ? "Type hashtag and press Enter..." : "Add more..."}
              style={{
                flex: 1,
                minWidth: 150,
                border: "none",
                outline: "none",
                fontSize: 14,
                padding: "6px 8px",
                background: "transparent",
              }}
            />
          </div>
          
          <div style={{ fontSize: 11, color: T.sub }}>
            💡 Type a hashtag and press <strong>Enter</strong> or <strong>Space</strong> to add. Press <strong>Backspace</strong> to remove.
          </div>
        </div>

        {/* Tips */}
        <div style={{
          padding: 16,
          background: T.pri + "10",
          borderRadius: 8,
          border: `1px solid ${T.pri}30`,
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 8 }}>
            💡 Tips for better posts
          </div>
          <ul style={{ fontSize: 12, color: T.sub, paddingLeft: 20, margin: 0 }}>
            <li style={{ marginBottom: 4 }}>Use high-quality images or videos</li>
            <li style={{ marginBottom: 4 }}>Write engaging captions that tell a story</li>
            <li style={{ marginBottom: 4 }}>Add relevant hashtags to reach more people</li>
            <li>Post consistently to grow your audience</li>
          </ul>
        </div>
      </div>

      {/* Camera Modal */}
      {showCameraOptions && (
        <div style={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: "rgba(0,0,0,0.9)",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          zIndex: 1000,
        }}>
          <div style={{
            position: "relative",
            width: "100%",
            maxWidth: 800,
            height: "80vh",
            background: "#000",
            borderRadius: 16,
            overflow: "hidden",
          }}>
            {/* Camera Feed */}
            {showCameraOptions === 'photo' ? (
              <video
                ref={photoRef}
                autoPlay
                playsInline
                muted
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            ) : (
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                }}
              />
            )}

            {/* Recording indicator */}
            {showCameraOptions === 'video' && mediaRecorder?.state === 'recording' && (
              <div style={{
                position: "absolute",
                top: 20,
                left: 20,
                display: "flex",
                alignItems: "center",
                gap: 8,
                background: "rgba(239, 68, 68, 0.9)",
                padding: "8px 16px",
                borderRadius: 20,
              }}>
                <div style={{
                  width: 12,
                  height: 12,
                  borderRadius: "50%",
                  background: "#fff",
                  animation: "pulse 1s infinite",
                }} />
                <span style={{ color: "#fff", fontSize: 14, fontWeight: 600 }}>
                  Recording...
                </span>
              </div>
            )}
            {/* Controls */}
            <div style={{
              position: "absolute",
              bottom: 0,
              left: 0,
              right: 0,
              padding: "20px",
              background: "linear-gradient(to top, rgba(0,0,0,0.8), transparent)",
              display: "flex",
              justifyContent: "center",
              alignItems: "center",
              gap: 20,
            }}>
              <button
                onClick={handleCancelCamera}
                style={{
                  padding: "12px 24px",
                  background: "rgba(255,255,255,0.2)",
                  border: "none",
                  borderRadius: 8,
                  color: "#fff",
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                Cancel
              </button>

              {showCameraOptions === 'photo' ? (
                <button
                  onClick={handleCapturePhoto}
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: "50%",
                    background: "#fff",
                    border: "4px solid rgba(255,255,255,0.3)",
                    cursor: "pointer",
                  }}
                />
              ) : (
                <button
                  onClick={mediaRecorder?.state === 'recording' ? handleStopRecording : handleStartRecording}
                  style={{
                    width: 72,
                    height: 72,
                    borderRadius: "50%",
                    background: mediaRecorder?.state === 'recording' ? '#EF4444' : '#fff',
                    border: "4px solid rgba(255,255,255,0.3)",
                    cursor: "pointer",
                  }}
                />
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
