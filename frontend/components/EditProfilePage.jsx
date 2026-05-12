import { useState, useEffect, useRef } from "react";
import { ChevronLeft, Camera, Save } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";
import { useLanguage } from "../contexts/LanguageContext";
import config from "../config";

export function EditProfilePage({ user, onBack, onSave }) {
  const { colors: T } = useTheme();
  const { t } = useLanguage();
  const [formData, setFormData] = useState({
    username: user?.username || "",
    email: user?.email || "",
    firstName: user?.first_name || "",
    lastName: user?.last_name || "",
    bio: user?.bio || "",
  });
  const [saving, setSaving] = useState(false);
  const [profilePhoto, setProfilePhoto] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(user?.profile_photo || null);
  const fileInputRef = useRef(null);

  const handleChange = (field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  const handlePhotoSelect = (e) => {
    const file = e.target.files[0];
    if (file) {
      if (file.size > 5 * 1024 * 1024) {
        alert("Photo must be less than 5MB");
        return;
      }
      setProfilePhoto(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setPhotoPreview(reader.result);
      };
      reader.readAsDataURL(file);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      
      // Create FormData for file upload
      const formDataToSend = new FormData();
      // Always send these fields (even if empty string for bio)
      formDataToSend.append('username', formData.username || user?.username || '');
      formDataToSend.append('email', formData.email || user?.email || '');
      formDataToSend.append('first_name', formData.firstName || '');
      formDataToSend.append('last_name', formData.lastName || '');
      formDataToSend.append('bio', formData.bio || '');
      if (profilePhoto) {
        formDataToSend.append('profile_photo', profilePhoto);
      }
      
      console.log('📤 Updating profile...');
      const data = await api.request('/profile/update_profile/', {
        method: 'PATCH',
        body: formDataToSend,
        isFormData: true,
      });
      console.log('✅ Profile updated:', data);
      
      // Update localStorage with new user data
      // Ensure profile_photo has full URL
      let profilePhotoUrl = data.profile_photo;
      if (profilePhotoUrl && !profilePhotoUrl.startsWith('http')) {
        profilePhotoUrl = `${config.API_BASE_URL.replace('/api', '')}${profilePhotoUrl}`;
      }
      
      const updatedUser = { 
        ...user, 
        first_name: data.first_name || '',
        last_name: data.last_name || '',
        bio: data.bio || '',
        profile_photo: profilePhotoUrl,
        username: data.username || user?.username,
        email: data.email || user?.email,
        name: data.first_name || data.username || user?.name,
      };
      localStorage.setItem('user', JSON.stringify(updatedUser));
      
      onSave?.(updatedUser);
      onBack();
    } catch (error) {
      console.error("Failed to update profile:", error);
      // Try to parse error message
      let errorMsg = "Failed to update profile. Please try again.";
      try {
        const errData = JSON.parse(error.message);
        if (errData.error) errorMsg = errData.error;
        else if (errData.detail) errorMsg = errData.detail;
        else if (errData.username) errorMsg = `Username: ${errData.username}`;
        else if (errData.email) errorMsg = `Email: ${errData.email}`;
      } catch {}
      alert(errorMsg);
    } finally {
      setSaving(false);
    }
  };

  const inputStyle = {
    width: "100%",
    padding: "12px 16px",
    border: `1px solid ${T.border}`,
    borderRadius: 8,
    fontSize: 14,
    outline: "none",
    transition: "border 0.2s",
    boxSizing: "border-box",
    background: T.bg,
    color: T.txt,
  };

  return (
    <div style={{
      position: "fixed",
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: T.cardBg,
      zIndex: 200,
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
    }}>
      {/* Header - sticky so always visible */}
      <div style={{
        position: "sticky",
        top: 0,
        flexShrink: 0,
        background: T.cardBg,
        borderBottom: `1px solid ${T.border}`,
        padding: "10px 16px",
        display: "flex",
        alignItems: "center",
        gap: 12,
        zIndex: 100,
      }}>
        <button
          onClick={onBack}
          style={{
            background: "none",
            border: "none",
            cursor: "pointer",
            padding: 6,
            display: "flex",
            alignItems: "center",
            color: T.txt,
            flexShrink: 0,
          }}
        >
          <ChevronLeft size={22} />
        </button>
        <div style={{ flex: 1, fontSize: 17, fontWeight: 700, color: T.txt, minWidth: 0 }}>
          Edit Profile
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            background: T.pri,
            border: "none",
            borderRadius: 8,
            padding: "8px 16px",
            color: "#fff",
            fontSize: 14,
            fontWeight: 700,
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.6 : 1,
            display: "flex",
            alignItems: "center",
            gap: 6,
            flexShrink: 0,
          }}
        >
          <Save size={16} />
          {saving ? "Saving..." : "Save"}
        </button>
      </div>

      {/* Scrollable Content */}
      <div style={{ flex: 1, overflowY: "auto", WebkitOverflowScrolling: "touch", position: "relative" }}>
        <div style={{ padding: "16px", maxWidth: 600, margin: "0 auto", boxSizing: "border-box" }}>
          {/* Profile Photo */}
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div style={{ position: "relative", display: "inline-block" }}>
              {photoPreview ? (
                <img
                  src={photoPreview}
                  alt="Profile"
                  style={{
                    width: 88,
                    height: 88,
                    borderRadius: "50%",
                    objectFit: "cover",
                    border: `3px solid ${T.pri}`,
                  }}
                />
              ) : (
                <div style={{
                  width: 88,
                  height: 88,
                  borderRadius: "50%",
                  background: T.pri + "30",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 36,
                }}>
                  👤
                </div>
              )}
              <button
                type="button"
                onClick={() => fileInputRef.current?.click()}
                style={{
                  position: "absolute",
                  bottom: 0,
                  right: 0,
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: T.pri,
                  border: "2px solid #fff",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  cursor: "pointer",
                  color: "#fff",
                }}
              >
                <Camera size={16} />
              </button>
              <input
                ref={fileInputRef}
                type="file"
                accept="image/*"
                onChange={handlePhotoSelect}
                style={{ display: "none" }}
              />
            </div>
            <div style={{ fontSize: 12, color: T.sub, marginTop: 6 }}>
              Tap to change photo
            </div>
          </div>

          {/* Form Fields */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 6 }}>
                Username
              </label>
              <input
                type="text"
                value={formData.username}
                onChange={(e) => handleChange("username", e.target.value)}
                placeholder="Enter your username"
                style={inputStyle}
                onFocus={(e) => e.target.style.borderColor = T.pri}
                onBlur={(e) => e.target.style.borderColor = T.border}
              />
            </div>

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 6 }}>
                Email
              </label>
              <input
                type="email"
                value={formData.email}
                onChange={(e) => handleChange("email", e.target.value)}
                placeholder="Enter your email"
                style={inputStyle}
                onFocus={(e) => e.target.style.borderColor = T.pri}
                onBlur={(e) => e.target.style.borderColor = T.border}
              />
            </div>

            <div style={{ display: "flex", gap: 12 }}>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 6 }}>
                  First Name
                </label>
                <input
                  type="text"
                  value={formData.firstName}
                  onChange={(e) => handleChange("firstName", e.target.value)}
                  placeholder="First name"
                  style={inputStyle}
                  onFocus={(e) => e.target.style.borderColor = T.pri}
                  onBlur={(e) => e.target.style.borderColor = T.border}
                />
              </div>
              <div style={{ flex: 1 }}>
                <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 6 }}>
                  Last Name
                </label>
                <input
                  type="text"
                  value={formData.lastName}
                  onChange={(e) => handleChange("lastName", e.target.value)}
                  placeholder="Last name"
                  style={inputStyle}
                  onFocus={(e) => e.target.style.borderColor = T.pri}
                  onBlur={(e) => e.target.style.borderColor = T.border}
                />
              </div>
            </div>

            <div>
              <label style={{ display: "block", fontSize: 13, fontWeight: 600, color: T.txt, marginBottom: 6 }}>
                Bio
              </label>
              <textarea
                value={formData.bio}
                onChange={(e) => handleChange("bio", e.target.value)}
                placeholder="Tell us about yourself..."
                rows={3}
                maxLength={150}
                style={{
                  ...inputStyle,
                  resize: "none",
                  fontFamily: "inherit",
                }}
                onFocus={(e) => e.target.style.borderColor = T.pri}
                onBlur={(e) => e.target.style.borderColor = T.border}
              />
              <div style={{ fontSize: 11, color: T.sub, marginTop: 4, textAlign: "right" }}>
                {formData.bio.length}/150
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Sticky bottom save button - always reachable */}
      <div style={{
        position: "sticky",
        bottom: 0,
        flexShrink: 0,
        padding: "12px 16px",
        paddingBottom: "max(12px, env(safe-area-inset-bottom))",
        borderTop: `1px solid ${T.border}`,
        background: T.cardBg,
        zIndex: 50,
      }}>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            width: "100%",
            padding: "14px 20px",
            background: T.pri,
            border: "none",
            borderRadius: 10,
            color: "#fff",
            fontSize: 15,
            fontWeight: 700,
            cursor: saving ? "not-allowed" : "pointer",
            opacity: saving ? 0.6 : 1,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
          }}
        >
          <Save size={18} />
          {saving ? "Saving..." : "Save Changes"}
        </button>
      </div>
    </div>
  );
}




