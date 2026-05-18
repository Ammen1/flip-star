import { useState, useRef, useEffect } from "react";
import { useLegacyT } from "../contexts/ThemeContext";
import api from "../api";

export function CreateVideoModal({ onClose, onVideoCreated }) {
  const T = useLegacyT();
  const [caption, setCaption] = useState("");
  const [image, setImage] = useState(null);
  const [preview, setPreview] = useState(null);
  const [isVideo, setIsVideo] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [isRecording, setIsRecording] = useState(false);
  const [recordedChunks, setRecordedChunks] = useState([]);
  const [selectedCategory, setSelectedCategory] = useState("");
  const [categories, setCategories] = useState([]);
  const fileInputRef = useRef(null);
  const videoRef = useRef(null);
  const mediaRecorderRef = useRef(null);
  const streamRef = useRef(null);

  useEffect(() => {
    loadCategories();
  }, []);

  async function loadCategories() {
    try {
      const data = await api.request('/categories/');
      setCategories(data.filter(c => c.is_active));
    } catch (e) {
      console.error('Failed to load categories:', e);
    }
  }

  const handleImageSelect = (e) => {
    const file = e.target.files?.[0];
    if (file) {
      setImage(file);
      setIsVideo(file.type.startsWith('video/'));
      const reader = new FileReader();
      reader.onload = (event) => {
        setPreview(event.target?.result);
      };
      reader.readAsDataURL(file);
      setErr("");
    }
  };

  const startRecording = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        videoRef.current.muted = true;
      }
      
      const mediaRecorder = new MediaRecorder(stream);
      mediaRecorderRef.current = mediaRecorder;
      const chunks = [];
      
      mediaRecorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunks.push(e.data);
        }
      };
      
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'video/webm' });
        const url = URL.createObjectURL(blob);
        setPreview(url);
        setIsVideo(true);
        setImage(new File([blob], 'recorded-video.webm', { type: 'video/webm' }));
        setRecordedChunks(chunks);
        
        if (streamRef.current) {
          streamRef.current.getTracks().forEach(track => track.stop());
        }
      };
      
      mediaRecorder.start();
      setIsRecording(true);
      setErr("");
    } catch (err) {
      console.error("Error accessing camera:", err);
      setErr("Could not access camera. Please allow camera permissions.");
    }
  };

  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const handleUpload = async () => {
    if (!image || !caption.trim()) {
      setErr("Please select an image and add a caption");
      return;
    }

    setLoading(true);
    try {
      const formData = new FormData();
      formData.append('file', image);
      formData.append('caption', caption);
      if (selectedCategory) {
        formData.append('category', selectedCategory);
      }

      const response = await api.request('/reels/', {
        method: 'POST',
        body: formData,
      });

      console.log("Video created:", response);
      
      // Call the callback with the new video
      onVideoCreated?.(response);
      
      // Close modal
      onClose();
    } catch(e) {
      console.error("Upload error:", e);
      setErr(e.message || "Failed to upload video");
    } finally {
      setLoading(false);
    }
  };

  return (
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
      zIndex: 2000,
    }}>
      <div style={{
        background: "#fff",
        borderRadius: 16,
        padding: 24,
        maxWidth: 600,
        width: "90%",
        maxHeight: "90vh",
        overflowY: "auto",
      }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 20, fontWeight: 800, color: "#1a1a1a" }}>Create Video 📹</div>
          <button
            onClick={onClose}
            style={{
              background: "none",
              border: "none",
              fontSize: 24,
              cursor: "pointer",
              color: "#666",
            }}
          >
            ✕
          </button>
        </div>

        {/* Image/Video Preview */}
        {isRecording ? (
          <div style={{
            width: "100%",
            height: 300,
            borderRadius: 12,
            background: "#000",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 16,
            overflow: "hidden",
            position: "relative",
          }}>
            <video
              ref={videoRef}
              autoPlay
              muted
              style={{ width: "100%", height: "100%", objectFit: "cover" }}
            />
            <div style={{
              position: "absolute",
              top: 10,
              left: 10,
              background: "rgba(255,0,0,0.8)",
              color: "#fff",
              padding: "4px 12px",
              borderRadius: 20,
              fontSize: 12,
              fontWeight: 600,
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}>
              <span style={{ width: 8, height: 8, background: "#fff", borderRadius: "50%", animation: "pulse 1s infinite" }} />
              REC
            </div>
          </div>
        ) : preview ? (
          <div style={{
            width: "100%",
            height: 300,
            borderRadius: 12,
            background: "#000",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            marginBottom: 16,
            overflow: "hidden",
            position: "relative",
          }}>
            {isVideo ? (
              <video
                src={preview}
                controls
                style={{ width: "100%", height: "100%", objectFit: "cover" }}
              />
            ) : (
              <img src={preview} alt="preview" style={{ width: "100%", height: "100%", objectFit: "cover" }} />
            )}
            <button
              onClick={() => {
                setImage(null);
                setPreview(null);
                setIsVideo(false);
                setRecordedChunks([]);
              }}
              style={{
                position: "absolute",
                top: 10,
                right: 10,
                background: "rgba(0,0,0,0.7)",
                border: "none",
                borderRadius: "50%",
                width: 32,
                height: 32,
                color: "#fff",
                fontSize: 18,
                cursor: "pointer",
              }}
            >
              ✕
            </button>
          </div>
        ) : (
          <div style={{ marginBottom: 16 }}>
            <div
              onClick={() => fileInputRef.current?.click()}
              style={{
                width: "100%",
                height: 300,
                borderRadius: 12,
                border: `2px dashed #ccc`,
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                flexDirection: "column",
                cursor: "pointer",
                background: "#f5f5f5",
                transition: "all .2s",
              }}
              onMouseEnter={(e) => e.currentTarget.style.borderColor = T.pri}
              onMouseLeave={(e) => e.currentTarget.style.borderColor = "#ccc"}
            >
              <div style={{ fontSize: 48, marginBottom: 8 }}>📸</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "#1a1a1a" }}>Click to upload image/video</div>
              <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>or drag and drop</div>
            </div>
          </div>
        )}

        <input
          ref={fileInputRef}
          type="file"
          accept="image/*,video/*"
          onChange={handleImageSelect}
          style={{ display: "none" }}
        />

        {/* Caption Input */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#666", textTransform: "uppercase", display: "block", marginBottom: 6 }}>
            Caption
          </label>
          <textarea
            value={caption}
            onChange={(e) => setCaption(e.target.value)}
            placeholder="Write a caption for your video..."
            style={{
              width: "100%",
              minHeight: 100,
              padding: 12,
              border: `1.5px solid #d0d0d0`,
              borderRadius: 12,
              fontSize: 14,
              fontFamily: "inherit",
              outline: "none",
              resize: "vertical",
              background: "#fff",
              color: "#1a1a1a",
            }}
          />
        </div>

        {/* Category Selector */}
        <div style={{ marginBottom: 16 }}>
          <label style={{ fontSize: 12, fontWeight: 700, color: "#666", textTransform: "uppercase", display: "block", marginBottom: 6 }}>
            Category (Optional)
          </label>
          <select
            value={selectedCategory}
            onChange={(e) => setSelectedCategory(e.target.value)}
            style={{
              width: "100%",
              padding: "12px",
              border: `1.5px solid #d0d0d0`,
              borderRadius: 12,
              fontSize: 14,
              fontFamily: "inherit",
              outline: "none",
              background: "#fff",
              color: "#1a1a1a",
              cursor: "pointer",
            }}
          >
            <option value="">Select a category...</option>
            {categories.map((cat) => (
              <option key={cat.id} value={cat.id}>
                {cat.name}
              </option>
            ))}
          </select>
        </div>

        {/* Error Message */}
        {err && (
          <div style={{
            background: "#FEE2E2",
            borderRadius: 10,
            padding: 12,
            fontSize: 12,
            color: T.red,
            marginBottom: 16,
          }}>
            ⚠️ {err}
          </div>
        )}

        {/* Buttons */}
        <div style={{ display: "flex", gap: 12, flexWrap: "nowrap" }}>
          <button
            onClick={() => {
              if (streamRef.current) {
                streamRef.current.getTracks().forEach(track => track.stop());
              }
              onClose();
            }}
            style={{
              flex: 1,
              minWidth: 0,
              padding: 12,
              background: "#f0f0f0",
              border: "1px solid #d0d0d0",
              borderRadius: 8,
              color: "#1a1a1a",
              fontSize: 14,
              fontWeight: 600,
              cursor: "pointer",
            }}
          >
            Cancel
          </button>
          {!isRecording && !preview && (
            <button
              onClick={startRecording}
              style={{
                flex: 1,
                minWidth: 0,
                padding: 12,
                background: T.pri,
                border: "none",
                borderRadius: 8,
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Record Video 🎥
            </button>
          )}
          {isRecording && (
            <button
              onClick={stopRecording}
              style={{
                flex: 1,
                minWidth: 0,
                padding: 12,
                background: "#EF4444",
                border: "none",
                borderRadius: 8,
                color: "#fff",
                fontSize: 14,
                fontWeight: 600,
                cursor: "pointer",
              }}
            >
              Stop Recording ⏹️
            </button>
          )}
          <button
            onClick={handleUpload}
            disabled={loading || !image || !caption.trim() || isRecording}
            style={{
              flex: 1,
              minWidth: 0,
              padding: 12,
              background: loading ? "#ccc" : T.pri,
              border: "none",
              borderRadius: 8,
              color: "#fff",
              fontSize: 14,
              fontWeight: 600,
              cursor: loading || !image || !caption.trim() || isRecording ? "not-allowed" : "pointer",
              opacity: loading || !image || !caption.trim() || isRecording ? 0.6 : 1,
            }}
          >
            {loading ? "Uploading..." : "Post Video 🚀"}
          </button>
        </div>
      </div>
    </div>
  );
}




