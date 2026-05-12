import { useState } from "react";
import { Phone, Lock, Eye, EyeOff, Loader, X, ChevronLeft, MessageSquare } from "lucide-react";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

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

export function ForgotPasswordPhone({ onClose, onSuccess }) {
  const T = useLegacyT();
  const [step, setStep] = useState(1);
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [pwd, setPwd] = useState("");
  const [confirm, setConfirm] = useState("");
  const [showPwd, setShowPwd] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const [devCode, setDevCode] = useState("");
  const [focusPhone, setFocusPhone] = useState(false);
  const [focusCode, setFocusCode] = useState(false);
  const [focusPwd, setFocusPwd] = useState(false);
  const [focusConfirm, setFocusConfirm] = useState(false);

  const sendCode = async () => {
    setError(""); setMsg(""); setDevCode("");
    if (!phone) { setError("Enter your phone number"); return; }
    const cleanPhone = phone.replace(/[^\d]/g, '');
    if (!/^\d{9,15}$/.test(cleanPhone)) { setError("Enter a valid phone number"); return; }
    setLoading(true);
    try {
      const res = await api.forgotPasswordPhoneRequest(phone);
      const data = res.data || res;
      setMsg("Reset code sent via SMS!");
      if (data.dev_code) {
        setDevCode(data.dev_code);
        setMsg(`Reset code sent! Dev code: ${data.dev_code}`);
      }
      setStep(2);
    } catch (e) {
      const err = e?.response?.data?.error || e?.message || "Failed to send code";
      setError(err);
    } finally { setLoading(false); }
  };

  const confirmReset = async () => {
    setError(""); setMsg("");
    if (code.length !== 6) { setError("Enter the 6-digit code"); return; }
    if (!/^\d{6}$/.test(pwd)) { setError("New PIN must be exactly 6 digits"); return; }
    if (pwd !== confirm) { setError("PINs do not match"); return; }
    setLoading(true);
    try {
      await api.forgotPasswordPhoneVerify(phone, code, pwd);
      setStep(3);
    } catch (e) {
      const err = e?.response?.data?.error || e?.message || "Invalid or expired code";
      setError(err);
    } finally { setLoading(false); }
  };

  return (
    <div onClick={onClose} style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.85)", zIndex: 10000, display: "flex", alignItems: "flex-end", justifyContent: "center" }}>
      <div onClick={e => e.stopPropagation()} style={{ background: "#111", borderRadius: "18px 18px 0 0", width: "100%", maxWidth: 500, maxHeight: "88vh", overflowY: "auto", padding: "24px 20px 40px" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 20 }}>
          <div style={{ fontSize: 20, fontWeight: 900, color: "#F9E08B" }}>
            {step === 1 ? "Forgot PIN" : step === 2 ? "Enter Reset Code" : "PIN Reset!"}
          </div>
          <button onClick={onClose} style={{ background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}><X size={22} /></button>
        </div>
        {error && <div style={{ padding: "10px 14px", background: "#2D1010", border: "1px solid #EF4444", borderRadius: 8, color: "#EF4444", fontSize: 13, marginBottom: 12 }}>⚠️ {error}</div>}
        {msg && <div style={{ padding: "10px 14px", background: "#1A2A1A", border: "1px solid #22C55E", borderRadius: 8, color: "#22C55E", fontSize: 13, marginBottom: 12 }}>{msg}</div>}

        {step === 1 && (
          <>
            <div style={{ fontSize: 13, color: "#aaa", marginBottom: 16 }}>Enter your registered phone number. A 6-digit reset code will be sent via SMS.</div>
            <div style={{ position: "relative", marginBottom: 16 }}>
              <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Phone size={17} /></div>
              <input
                type="tel"
                placeholder="09XXXXXXXX or +251XXXXXXXXX"
                value={phone}
                onChange={e => setPhone(e.target.value)}
                style={inp(focusPhone)}
                onFocus={() => setFocusPhone(true)}
                onBlur={() => setFocusPhone(false)}
                onKeyDown={e => e.key === "Enter" && sendCode()}
              />
            </div>
            <button onClick={sendCode} disabled={loading} style={{ width: "100%", padding: "13px", background: GOLD, border: "none", borderRadius: 10, color: "#000", fontSize: 15, fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              {loading ? <><Loader size={16} style={{ animation: "spin 1s linear infinite" }} /> Sending…</> : "Send Reset Code"}
            </button>
          </>
        )}
        {step === 2 && (
          <>
            <div style={{ fontSize: 13, color: "#aaa", marginBottom: 16 }}>Enter the code sent to <strong style={{ color: "#fff" }}>{phone}</strong> and your new 6-digit PIN.</div>
            <div style={{ position: "relative", marginBottom: 16 }}>
              <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><MessageSquare size={17} /></div>
              <input
                type="text"
                inputMode="numeric"
                maxLength={6}
                placeholder="6-digit code"
                value={code}
                onChange={e => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                style={inp(focusCode)}
                onFocus={() => setFocusCode(true)}
                onBlur={() => setFocusCode(false)}
              />
            </div>
            <div style={{ position: "relative", marginBottom: 16 }}>
              <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Lock size={17} /></div>
              <input
                type={showPwd ? "text" : "password"}
                inputMode="numeric"
                maxLength={6}
                placeholder="New 6-digit PIN"
                value={pwd}
                onChange={e => setPwd(e.target.value.replace(/\D/g, "").slice(0, 6))}
                style={{ ...inp(focusPwd), paddingRight: 46 }}
                onFocus={() => setFocusPwd(true)}
                onBlur={() => setFocusPwd(false)}
              />
              <button type="button" onClick={() => setShowPwd(v => !v)} style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", background: "none", border: "none", cursor: "pointer", color: "#F9E08B" }}>{showPwd ? <EyeOff size={16} /> : <Eye size={16} />}</button>
            </div>
            <div style={{ position: "relative", marginBottom: 16 }}>
              <div style={{ position: "absolute", left: 14, top: "50%", transform: "translateY(-50%)", color: "#F9E08B", display: "flex" }}><Lock size={17} /></div>
              <input
                type="password"
                inputMode="numeric"
                maxLength={6}
                placeholder="Confirm new PIN"
                value={confirm}
                onChange={e => setConfirm(e.target.value.replace(/\D/g, "").slice(0, 6))}
                style={inp(focusConfirm)}
                onFocus={() => setFocusConfirm(true)}
                onBlur={() => setFocusConfirm(false)}
              />
            </div>
            <button onClick={confirmReset} disabled={loading} style={{ width: "100%", padding: "13px", background: GOLD, border: "none", borderRadius: 10, color: "#000", fontSize: 15, fontWeight: 800, cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", gap: 8 }}>
              {loading ? <><Loader size={16} style={{ animation: "spin 1s linear infinite" }} /> Resetting…</> : "Reset PIN"}
            </button>
            <button onClick={() => { setStep(1); setCode(""); setError(""); setMsg(""); setDevCode(""); }} style={{ background: "none", border: "none", color: "#F9E08B", fontSize: 13, cursor: "pointer", marginTop: 12, display: "flex", alignItems: "center", gap: 4 }}>
              <ChevronLeft size={14} /> Back
            </button>
          </>
        )}
        {step === 3 && (
          <div style={{ textAlign: "center", padding: "20px 0" }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>✅</div>
            <div style={{ fontSize: 18, fontWeight: 800, color: "#F9E08B", marginBottom: 8 }}>PIN Reset!</div>
            <div style={{ fontSize: 13, color: "#aaa", marginBottom: 24 }}>You can now log in with your new PIN.</div>
            <button onClick={() => { onClose(); onSuccess && onSuccess(); }} style={{ padding: "12px 32px", background: GOLD, border: "none", borderRadius: 10, color: "#000", fontSize: 15, fontWeight: 800, cursor: "pointer" }}>Go to Login</button>
          </div>
        )}
      </div>
      <style>{`@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }`}</style>
    </div>
  );
}
