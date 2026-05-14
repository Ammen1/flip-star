import { useState, useRef, useEffect } from "react";
import { Phone, Lock, User, Eye, EyeOff, Loader, ChevronLeft, CheckCircle, Mail } from "lucide-react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";

// ── helpers ────────────────────────────────────────────────────────────────
const GOLD = "linear-gradient(to bottom, #D4AF37 0%, #F9E08B 50%, #B8860B 100%)";

const inputStyle = (T, focused) => ({
  width: "100%",
  padding: "13px 16px 13px 46px",
  background: T.cardBg || "#1A1A1A",
  border: `1.5px solid ${focused ? "#F9E08B" : T.border || "#262626"}`,
  borderRadius: 10,
  fontSize: 15,
  color: T.txt || "#fff",
  outline: "none",
  boxSizing: "border-box",
  transition: "border 0.2s",
});

function IconWrap({ children }) {
  return (
    <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}>
      {children}
    </div>
  );
}

function Field({ label, icon, children }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <label style={{ display: "block", fontSize: 12, fontWeight: 700, color: "#F9E08B", marginBottom: 7, letterSpacing: 0.5 }}>
        {label}
      </label>
      <div style={{ position: "relative" }}>
        <IconWrap>{icon}</IconWrap>
        {children}
      </div>
    </div>
  );
}

function GoldBtn({ loading, onClick, disabled, children }) {
  return (
    <button
      onClick={onClick}
      disabled={loading || disabled}
      style={{
        width: "100%", padding: "14px",
        background: loading || disabled ? "#3A3A3A" : GOLD,
        border: "none", borderRadius: 10,
        color: loading || disabled ? "#888" : "#000",
        fontSize: 15, fontWeight: 800,
        cursor: loading || disabled ? "not-allowed" : "pointer",
        display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
        marginBottom: 16, letterSpacing: 0.3,
      }}
    >
      {loading ? <><Loader size={18} style={{ animation: "spin 1s linear infinite" }} /> Working…</> : children}
    </button>
  );
}

function ErrorBox({ msg }) {
  if (!msg) return null;
  return (
    <div style={{ padding: "11px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, fontWeight: 600, marginBottom: 16 }}>
      ⚠️ {msg}
    </div>
  );
}

function StepDot({ active, done }) {
  return (
    <div style={{
      width: done ? 22 : active ? 22 : 10, height: done ? 22 : active ? 22 : 10,
      borderRadius: "50%",
      background: done ? "#F9E08B" : active ? GOLD : "#262626",
      display: "flex", alignItems: "center", justifyContent: "center",
      transition: "all 0.3s",
      fontSize: 11, color: "#000", fontWeight: 700,
    }}>
      {done ? "✓" : active ? "" : ""}
    </div>
  );
}

// ── OTP input: 6 separate digit boxes ──────────────────────────────────────
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
    <div style={{ display: "flex", gap: 10, justifyContent: "center", margin: "24px 0" }}>
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

export function ModernRegisterScreen({ onSuccess, onLogin, onBack }) {
  const { colors: T } = useTheme();
  const [step, setStep] = useState(1); // 1=form, 2=otp
  const [phone, setPhone] = useState("");
  const [otp, setOtp] = useState("");
  const [devCode, setDevCode] = useState(""); // shown on page for testing
  const [verifiedPhone, setVerifiedPhone] = useState("");
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [showConfirm, setShowConfirm] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [resendTimer, setResendTimer] = useState(0);

  useEffect(() => {
    if (resendTimer <= 0) return;
    const t = setTimeout(() => setResendTimer(r => r - 1), 1000);
    return () => clearTimeout(t);
  }, [resendTimer]);

  const [focusedPhone, setFocusedPhone] = useState(false);
  const [focusedUser, setFocusedUser] = useState(false);
  const [focusedEmail, setFocusedEmail] = useState(false);
  const [focusedPwd, setFocusedPwd] = useState(false);
  const [focusedConfirm, setFocusedConfirm] = useState(false);

  // ── Step 1: Validate form then send OTP (app-first registration) ───────────────────────────────
  const handleSendOtp = async () => {
    setError("");
    if (!username) { setError("Please enter a username"); return; }
    if (!email) { setError("Please enter your email"); return; }
    if (!phone) { setError("Please enter your phone number"); return; }
    if (!/^\d{6}$/.test(password)) { setError("Password must be exactly 6 digits"); return; }
    if (password !== confirm) { setError("Passwords do not match"); return; }
    setLoading(true);
    try {
      // Send OTP directly via Onevas (app-first registration)
      const otpRes = await api.sendPhoneOtp(phone);
      setVerifiedPhone(otpRes.phone);
      setResendTimer(60);
      // Dev mode: show OTP on page since SMS not configured yet
      if (otpRes.dev_code) {
        setDevCode(otpRes.dev_code);
      }
      setStep(2);
    } catch (otpErr) {
      // Check for specific error messages
      const errorMessage = otpErr?.response?.data?.error || otpErr?.message || "Failed to send OTP. Check your phone number.";
      if (errorMessage.includes("already registered")) {
        setError("This phone number is already in use. Please use a different number or log in to your existing account.");
      } else {
        setError(errorMessage);
      }
    } finally {
      setLoading(false);
    }
  };

  // ── Step 2: Verify OTP then register ──────────────────────────────────
  const handleVerifyAndRegister = async () => {
    setError("");
    if (otp.length !== 6) { setError("Enter the 6-digit code"); return; }
    setLoading(true);
    try {
      await api.verifyPhoneOtp(verifiedPhone, otp);
      // OTP verified — now create account
      await handleRegisterWithPhone(false); // skip_otp = false (app-first with OTP)
    } catch (e) {
      setError(e?.message || "Invalid code or registration failed.");
    } finally {
      setLoading(false);
    }
  };

  // ── Register with phone (supports both OTP and OTP-less flows) ──────────────────────────────────
  const handleRegisterWithPhone = async (skipOtp = false) => {
    setError("");
    setLoading(true);
    try {
      const res = await api.post('/auth/register-with-phone/', {
        phone: phone,
        username: username,
        password: password,
        email: email,
        skip_otp: skipOtp
      });
      api.setAuthToken(res.token);
      onSuccess({
        id: res.user.id, username: res.user.username, email: res.user.email || "",
        first_name: res.user.first_name || "", last_name: res.user.last_name || "",
        name: res.user.first_name || res.user.username,
        profile_photo: res.user.profile_photo || null, bio: res.user.bio || "",
        followers_count: res.user.followers_count || 0,
        following_count: res.user.following_count || 0,
        is_staff: res.user.is_staff || false,
      });
    } catch (e) {
      setError(e?.response?.data?.error || e?.message || "Registration failed.");
    } finally {
      setLoading(false);
    }
  };

  const wrap = {
    minHeight: "100vh", background: T.bg || "#0D0D0D",
    display: "flex", alignItems: "center", justifyContent: "center",
    padding: "20px 16px",
  };

  return (
    <div style={wrap}>
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

        {/* Step indicator */}
        <div style={{ display: "flex", alignItems: "center", justifyContent: "center", gap: 8, marginBottom: 28 }}>
          <StepDot active={step === 1} done={step > 1} />
          <div style={{ width: 48, height: 2, background: step > 1 ? "#F9E08B" : "#262626", borderRadius: 1, transition: "background 0.3s" }} />
          <StepDot active={step === 2} done={false} />
        </div>

        {/* Card */}
        <div style={{ background: T.cardBg || "#1A1A1A", borderRadius: 18, padding: "28px 24px", border: "1px solid #F9E08B30" }}>

          {/* ── STEP 1: Phone ── */}
          {step === 1 && (
            <>
              <div style={{ textAlign: "center", marginBottom: 24 }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>📱</div>
                <div style={{ fontSize: 22, fontWeight: 900, color: "#F9E08B", marginBottom: 4 }}>Create Account</div>
                <div style={{ fontSize: 13, color: "#F9E08B" }}>Fill in your details to get started</div>
              </div>
              <ErrorBox msg={error} />
              <Field label="Username *" icon={<User size={17} />}>
                <input type="text" value={username} onChange={e => setUsername(e.target.value.toLowerCase().replace(/\s/g, ""))}
                  placeholder="Choose a unique username"
                  style={inputStyle(T, focusedUser)}
                  onFocus={() => setFocusedUser(true)} onBlur={() => setFocusedUser(false)}
                />
              </Field>
              <Field label="Email *" icon={<Mail size={17} />}>
                <input type="email" value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="your@email.com"
                  style={inputStyle(T, focusedEmail)}
                  onFocus={() => setFocusedEmail(true)} onBlur={() => setFocusedEmail(false)}
                />
              </Field>
              <Field label="Phone Number *" icon={<Phone size={17} />}>
                <input type="tel" value={phone} onChange={e => setPhone(e.target.value)}
                  placeholder="09XXXXXXXX or +251XXXXXXXXX"
                  style={inputStyle(T, focusedPhone)}
                  onFocus={() => setFocusedPhone(true)} onBlur={() => setFocusedPhone(false)}
                />
              </Field>
              <Field label="6-Digit PIN *" icon={<Lock size={17} />}>
                <input
                  type={showPwd ? "text" : "password"} inputMode="numeric" maxLength={6}
                  value={password} onChange={e => setPassword(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="••••••"
                  style={{ ...inputStyle(T, focusedPwd), paddingRight: 46 }}
                  onFocus={() => setFocusedPwd(true)} onBlur={() => setFocusedPwd(false)}
                />
                <button type="button" onClick={() => setShowPwd(v => !v)}
                  style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>
                  {showPwd ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </Field>
              <Field label="Confirm PIN *" icon={<Lock size={17} />}>
                <input
                  type={showConfirm ? "text" : "password"} inputMode="numeric" maxLength={6}
                  value={confirm} onChange={e => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 6))}
                  placeholder="••••••"
                  style={{ ...inputStyle(T, focusedConfirm), paddingRight: 46 }}
                  onFocus={() => setFocusedConfirm(true)} onBlur={() => setFocusedConfirm(false)}
                />
                <button type="button" onClick={() => setShowConfirm(v => !v)}
                  style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>
                  {showConfirm ? <EyeOff size={17} /> : <Eye size={17} />}
                </button>
              </Field>
              <GoldBtn loading={loading} onClick={handleSendOtp}>Send OTP →</GoldBtn>
            </>
          )}

          {/* ── STEP 2: OTP Verification ── */}
          {step === 2 && (
            <>
              <div style={{ textAlign: "center", marginBottom: 16 }}>
                <div style={{ fontSize: 36, marginBottom: 8 }}>🔐</div>
                <div style={{ fontSize: 22, fontWeight: 900, color: "#F9E08B", marginBottom: 4 }}>Verify Code</div>
                <div style={{ fontSize: 13, color: "#F9E08B" }}>
                  Code sent to <strong style={{ color: "#fff" }}>{verifiedPhone}</strong>
                </div>
              </div>
              <ErrorBox msg={error} />

              {/* DEV MODE: show OTP on page */}
              {devCode && (
                <div style={{ padding: "12px 16px", background: "#1A2A1A", border: "2px solid #22C55E", borderRadius: 10, color: "#22C55E", fontSize: 14, fontWeight: 700, marginBottom: 16, textAlign: "center" }}>
                  🧪 DEV MODE — Your OTP code is: <span style={{ fontSize: 22, letterSpacing: 4 }}>{devCode}</span>
                </div>
              )}

              <OtpInput value={otp} onChange={setOtp} />
              <GoldBtn loading={loading} onClick={handleVerifyAndRegister} disabled={otp.length < 6}>Verify & Register 🚀</GoldBtn>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                <button onClick={() => { setStep(1); setOtp(""); setError(""); setDevCode(""); }}
                  style={{ background: "none", border: "none", color: "#F9E08B", fontSize: 13, cursor: "pointer", display: "flex", alignItems: "center", gap: 4 }}>
                  <ChevronLeft size={14} /> Go back
                </button>
                {resendTimer > 0 ? (
                  <span style={{ color: "#666", fontSize: 12 }}>Resend in {resendTimer}s</span>
                ) : (
                  <button onClick={handleSendOtp} style={{ background: "none", border: "none", color: "#F9E08B", fontSize: 13, fontWeight: 700, cursor: "pointer" }}>
                    Resend OTP
                  </button>
                )}
              </div>
            </>
          )}

          {/* Footer */}
          <div style={{ textAlign: "center", fontSize: 13, color: "#666", marginTop: 4 }}>
            Already have an account?{" "}
            <button onClick={onLogin} style={{ background: "none", border: "none", color: "#F9E08B", fontWeight: 700, cursor: "pointer", fontSize: 13 }}>
              Log in
            </button>
          </div>
        </div>
      </div>

      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}




