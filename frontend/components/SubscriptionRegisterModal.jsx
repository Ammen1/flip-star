import { useState, useRef, useEffect } from "react";
import { Phone, Lock, User, Eye, EyeOff, Loader, ChevronLeft } from "lucide-react";
import api from "../api";

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

function OtpInput({ value, onChange }) {
  const refs = [useRef(), useRef(), useRef(), useRef(), useRef(), useRef()];
  const digits = (value + "      ").slice(0, 6).split("");

  const handle = (i, e) => {
    const v = e.target.value.replace(/\D/g, "").slice(-1);
    const arr = digits.map((d) => d.trim());
    arr[i] = v;
    onChange(arr.join("").replace(/ /g, ""));
    if (v && i < 5) refs[i + 1].current?.focus();
    if (!v && e.nativeEvent.inputType === "deleteContentBackward" && i > 0) refs[i - 1].current?.focus();
  };

  return (
    <div style={{ display: "flex", gap: 10, justifyContent: "center", margin: "16px 0 24px" }}>
      {digits.map((d, i) => (
        <input
          key={i}
          ref={refs[i]}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={d.trim()}
          onChange={(e) => handle(i, e)}
          style={{
            width: 46, height: 54, borderRadius: 10, textAlign: "center",
            fontSize: 22, fontWeight: 800, color: "#fff",
            background: "#1A1A1A",
            border: `2px solid ${d.trim() ? "#F9E08B" : "#262626"}`,
            outline: "none", caretColor: "#F9E08B",
          }}
        />
      ))}
    </div>
  );
}

/**
 * Shown when user arrives via Onevas SMS link:
 * ?subscription_tp=true&phone=251XXXXXXXXX&otp=XXXXXX
 *
 * Fields: Username, Phone (pre-filled), OTP (pre-filled / editable), Password
 * Calls POST /api/auth/login-with-subscription-otp/
 */
export function SubscriptionRegisterModal({ prefillPhone, prefillOtp, onSuccess, onBackToLogin }) {
  const [username, setUsername] = useState("");
  const [phone, setPhone] = useState(prefillPhone || "");
  const [otp, setOtp] = useState(prefillOtp || "");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [focusUser, setFocusUser] = useState(false);
  const [focusPhone, setFocusPhone] = useState(false);
  const [focusPwd, setFocusPwd] = useState(false);
  const [focusConfirm, setFocusConfirm] = useState(false);

  useEffect(() => {
    if (prefillPhone) setPhone(prefillPhone);
    if (prefillOtp) setOtp(prefillOtp);
  }, [prefillPhone, prefillOtp]);

  const handleRegister = async (e) => {
    e?.preventDefault();
    setError("");

    if (!username) { setError("Please enter a username"); return; }
    if (!phone) { setError("Please enter your phone number"); return; }
    if (otp.length !== 6) { setError("Please enter the 6-digit OTP from your SMS"); return; }
    if (!/^\d{6}$/.test(password)) { setError("PIN must be exactly 6 digits"); return; }
    if (password !== confirm) { setError("PINs do not match"); return; }

    setLoading(true);
    try {
      const res = await api.post('/auth/login-with-subscription-otp/', {
        phone,
        username,
        otp,
        password,
      });
      const data = res.data || res;
      api.setAuthToken(data.token);
      onSuccess({
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
      });
      // Clean URL params after success
      window.history.replaceState({}, '', window.location.pathname);
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || "Registration failed. Check your OTP and try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight: "100vh", background: "#0D0D0D", display: "flex", alignItems: "center", justifyContent: "center", padding: "20px 16px" }}>
      <div style={{ width: "100%", maxWidth: 420 }}>

        {/* Logo Header */}
        <div style={{ 
          background: "#FFFFFF", 
          height: 90, 
          marginBottom: 24, 
          borderRadius: 12, 
          display: "flex", 
          alignItems: "center", 
          justifyContent: "center"
        }}>
          <img src="/assets/70x20.png" alt="Logo" style={{ width: 380, height: 80, objectFit: "contain" }} />
        </div>

        {/* Card */}
        <div style={{ background: "#1A1A1A", borderRadius: 18, padding: "28px 24px", border: "1px solid #F9E08B30" }}>
          <div style={{ textAlign: "center", marginBottom: 24 }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>🎉</div>
            <div style={{ fontSize: 22, fontWeight: 900, color: "#F9E08B", marginBottom: 4 }}>Complete Registration</div>
            <div style={{ fontSize: 13, color: "#aaa" }}>Your subscription is confirmed! Set up your account below.</div>
          </div>

          {/* Success badge */}
          <div style={{ padding: "10px 14px", background: "#1A2A1A", border: "1px solid #22C55E", borderRadius: 8, color: "#22C55E", fontSize: 13, fontWeight: 600, marginBottom: 20, textAlign: "center" }}>
            ✅ Subscription active — Enter your OTP from the SMS
          </div>

          <form onSubmit={handleRegister}>
            {error && (
              <div style={{ padding: "10px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
                ⚠️ {error}
              </div>
            )}

            {/* Username */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>Username *</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><User size={17} /></div>
                <input
                  type="text"
                  value={username}
                  onChange={e => setUsername(e.target.value.toLowerCase().replace(/\s/g, ""))}
                  placeholder="Choose a unique username"
                  style={inp(focusUser)}
                  onFocus={() => setFocusUser(true)}
                  onBlur={() => setFocusUser(false)}
                />
              </div>
            </div>

            {/* Phone */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>Phone Number *</label>
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
                />
              </div>
            </div>

            {/* OTP */}
            <div style={{ marginBottom: 8 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 4, letterSpacing: 0.5 }}>OTP from SMS *</label>
              <div style={{ fontSize: 12, color: "#aaa", marginBottom: 4 }}>Enter the 6-digit code you received via SMS</div>
              <OtpInput value={otp} onChange={setOtp} />
            </div>

            {/* Password */}
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>PIN *</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Lock size={17} /></div>
                <input
                  type={showPwd ? "text" : "password"}
                  inputMode="numeric"
                  maxLength={6}
                  value={password}
                  onChange={e => setPassword(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="••••••"
                  style={{ ...inp(focusPwd), paddingRight: 46 }}
                  onFocus={() => setFocusPwd(true)}
                  onBlur={() => setFocusPwd(false)}
                />
                <button type="button" onClick={() => setShowPwd(v => !v)} style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>
                  {showPwd ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            {/* Confirm */}
            <div style={{ marginBottom: 24 }}>
              <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>Confirm PIN *</label>
              <div style={{ position: "relative" }}>
                <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Lock size={17} /></div>
                <input
                  type={showConfirm ? "text" : "password"}
                  inputMode="numeric"
                  maxLength={6}
                  value={confirm}
                  onChange={e => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="••••••"
                  style={{ ...inp(focusConfirm), paddingRight: 46 }}
                  onFocus={() => setFocusConfirm(true)}
                  onBlur={() => setFocusConfirm(false)}
                />
                <button type="button" onClick={() => setShowConfirm(v => !v)} style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>
                  {showConfirm ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </div>
            </div>

            <button type="submit" disabled={loading || otp.length < 6} style={{ width: "auto", padding: "14px 24px", background: loading || otp.length < 6 ? "#3A3A3A" : GOLD, border: "none", borderRadius: 10, color: loading || otp.length < 6 ? "#888" : "#000", fontSize: 15, fontWeight: 800, cursor: loading || otp.length < 6 ? "not-allowed" : "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginBottom: 16 }}>
              {loading ? <><Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> Creating Account…</> : "Create Account & Login 🚀"}
            </button>
          </form>

          <div style={{ textAlign: "center", fontSize: 13, color: "#666" }}>
            Already have an account?{" "}
            <button onClick={onBackToLogin} style={{ background: "none", border: "none", color: "#F9E08B", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>Log in</button>
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
