import { useState, useEffect } from "react";
import { Phone, Lock, Eye, EyeOff, Loader, X, ChevronLeft } from "lucide-react";
import api from "../api";
import { ForgotPasswordPhone } from "./ForgotPasswordPhone";

const GOLD = "linear-gradient(to bottom, #D4AF37 0%, #F9E08B 50%, #B8860B 100%)";

const inp = (focused) => ({
  width: "100%",
  padding: "13px 16px 13px 46px",
  background: "#1A1A1A",
  border: `1.5px solid ${focused ? "#F9E08B" : "#262626"}`,
  borderRadius: 10,
  fontSize: 15,
  color: "#fff",
  outline: "none",
  boxSizing: "border-box",
  transition: "border 0.2s",
});

export function PhoneLoginModal({ onSuccess, onSignUp, onClose, onForgotPasswordToggle }) {
  const [phone, setPhone] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [showForgot, setShowForgot] = useState(false);
  const [focusPhone, setFocusPhone] = useState(false);
  const [focusPwd, setFocusPwd] = useState(false);

  // Notify parent when forgot password modal state changes
  useEffect(() => {
    onForgotPasswordToggle?.(showForgot);
  }, [showForgot, onForgotPasswordToggle]);

  const handleLogin = async (e) => {
    e?.preventDefault();
    setError("");
    if (!phone || !password) { setError("Please fill in all fields"); return; }
    setLoading(true);
    try {
      const res = await api.post('/auth/login-with-phone/', { phone, password });
      const data = res.data || res;
      api.setAuthToken(data.token);
      const userData = {
        id: data.user.id,
        username: data.user.username,
        email: data.user.email || "",
        first_name: data.user.first_name || "",
        last_name: data.user.last_name || "",
        name: data.user.first_name || data.user.username,
        profile_photo: data.user.profile_photo || null,
        bio: data.user.bio || "",
        followers_count: data.user.followers_count || 0,
        following_count: data.user.following_count || 0,
        is_staff: data.user.is_staff || false,
      };
      onSuccess(userData);
    } catch (e) {
      const msg = e?.response?.data?.error || e?.message || "";
      if (msg.includes("subscription")) {
        setError("No active subscription found. Please subscribe first.");
      } else {
        setError("Invalid phone number or PIN. Please try again.");
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {showForgot && <ForgotPasswordPhone onClose={() => setShowForgot(false)} onSuccess={() => setShowForgot(false)} />}

      <div style={{ minHeight: "100vh", background: "#0D0D0D", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px 0" }}>
        <div style={{ width: "100%", maxWidth: 420 }}>

          {/* Logo Header */}
          <div style={{ 
            height: 90, 
            marginBottom: 24, 
            borderRadius: 12, 
            display: "flex", 
            flexDirection: "row",
            overflow: "hidden",
            position: "relative"
          }}>
            <div style={{ width: "50%", backgroundColor: "#FFFFFF", height: "100%", position: "absolute", left: 0, top: 0 }}></div>
            <div style={{ width: "50%", background: "linear-gradient(to bottom, #0D0D0D, #1A1A1A)", height: "100%", position: "absolute", right: 0, top: 0 }}></div>
            <img src="/assets/logo-ethio-and-flip.png" alt="Logo" style={{ height: 90, width: "100%", objectFit: "contain", position: "relative", zIndex: 1 }} />
          </div>

          {/* Card */}
          <div style={{ background: "#1A1A1A", borderRadius: 18, padding: "28px 24px", border: "1px solid #F9E08B30" }}>
            <div style={{ textAlign: "center", marginBottom: 28 }}>
              <div style={{ fontSize: 26, fontWeight: 900, color: "#F9E08B", marginBottom: 4 }}>Welcome</div>
              <div style={{ fontSize: 13, color: "#aaa" }}>Log in to continue to FlipStar</div>
            </div>

            <form onSubmit={handleLogin}>
              {error && (
                <div style={{ padding: "10px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
                  ⚠️ {error}
                </div>
              )}

              {/* Phone */}
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>Phone Number</label>
                <div style={{ position: "relative" }}>
                  <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Phone size={17} /></div>
                  <input
                    type="tel"
                    value={phone}
                    onChange={e => setPhone(e.target.value)}
                    placeholder="09XXXXXXXX or +251XXXXXXXXX"
                    style={inp(focusPhone)}
                    onFocus={() => setFocusPhone(true)}
                    onBlur={() => setFocusPhone(false)}
                    autoComplete="tel"
                  />
                </div>
              </div>

              {/* PIN */}
              <div style={{ marginBottom: 8 }}>
                <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>PIN</label>
                <div style={{ position: "relative" }}>
                  <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Lock size={17} /></div>
                  <input
                    type={showPassword ? "text" : "password"}
                    inputMode="numeric"
                    maxLength={6}
                    value={password}
                    onChange={e => setPassword(e.target.value.replace(/\D/g, "").slice(0, 6))}
                    placeholder="••••••"
                    style={{ ...inp(focusPwd), paddingRight: 46 }}
                    onFocus={() => setFocusPwd(true)}
                    onBlur={() => setFocusPwd(false)}
                    autoComplete="current-password"
                  />
                  <button type="button" onClick={() => setShowPassword(v => !v)} style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>
                    {showPassword ? <EyeOff size={17} /> : <Eye size={17} />}
                  </button>
                </div>
              </div>

              {/* Login button */}
              <button type="submit" disabled={loading} style={{ width: "100%", padding: "14px", background: loading ? "#3A3A3A" : GOLD, border: "none", borderRadius: 10, color: loading ? "#888" : "#000", fontSize: 15, fontWeight: 800, cursor: loading ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginBottom: 12 }}>
                {loading ? <><Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> Logging in…</> : "Log In"}
              </button>

              {/* Forgot PIN */}
              <div style={{ textAlign: "center", marginBottom: 16 }}>
                <button type="button" onClick={() => setShowForgot(true)} style={{ background: "none", border: "none", color: "#F9E08B", fontSize: 12, fontWeight: 700, cursor: "pointer" }}>
                  Forgot PIN?
                </button>
              </div>
            </form>

            {/* Sign up */}
            <div style={{ textAlign: "center", fontSize: 13, color: "#666" }}>
              Don't have an account?{" "}
              <button type="button" onClick={onSignUp} style={{ background: "none", border: "none", color: "#F9E08B", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
                Subscribe
              </button>
            </div>
          </div>

          {/* Close / Back */}
          {onClose && (
            <div style={{ textAlign: "center", marginTop: 16 }}>
              <button onClick={onClose} style={{ background: "none", border: "none", color: "#aaa", fontSize: 13, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 4 }}>
                <ChevronLeft size={14} /> Back to browsing
              </button>
            </div>
          )}
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </>
  );
}
