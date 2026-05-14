import { useState } from "react";
import { ChevronLeft } from "lucide-react";
import { Inp } from "./Inp";
import { GradBtn } from "./GradBtn";
import { ForgotPasswordPhone } from "./ForgotPasswordPhone";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

export function LoginScreen({ onSuccess, onRegister, onBack }) {
  const T = useLegacyT();
  const [phone, setPhone] = useState("");
  const [pin, setPin] = useState("");
  const [showPin, setShowPin] = useState(false);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [showForgotPassword, setShowForgotPassword] = useState(false);

  const go = async () => {
    if(!phone||!pin){setErr("Fill all fields");return;}
    // Validate phone number (basic validation)
    if(!/^\d{10,15}$/.test(phone.replace(/[^\d]/g, ''))){setErr("Enter a valid phone number");return;}
    // Validate 6-digit PIN
    if(!/^\d{6}$/.test(pin)){setErr("PIN must be 6 digits");return;}
    setErr("");
    setLoading(true);
    try {
      // Try login with phone number and PIN
      const cleanPhone = phone.replace(/[^\d]/g, '');
      console.log('Attempting login with:', { phone: cleanPhone, pin });
      
      try {
        const res = await api.loginWithPhone(cleanPhone, pin);
        console.log('Login successful:', res);
        api.setToken(res.token);
        onSuccess({
          phone: cleanPhone,
          name: res.user.first_name || "Creator",
          init: (res.user.first_name || "C").slice(0,2).toUpperCase(),
          plan:"free",
          email:"",
          marketingChoices:{sms:true,email:true,push:true,inApp:true},
          id: res.user.id
        });
      } catch(e) {
        // If login fails, show the error
        throw e;
      }
    } catch(e) {
      console.error('Login error:', e);
      setErr(e.message || "Login failed - check your phone number and PIN");
      setLoading(false);
    }
  };

  return (
    <>
      {showForgotPassword && (
        <ForgotPasswordPhone 
          onClose={() => setShowForgotPassword(false)}
          onSuccess={() => setShowForgotPassword(false)}
        />
      )}
      <div style={{ minHeight:"100vh", background:T.dark, display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"52px 24px 0" }}>
        <button onClick={onBack} style={{ background:"rgba(255,255,255,0.12)", border:"none", borderRadius:"50%", width:36, height:36, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff" }}>
          <ChevronLeft size={20} />
        </button>
        {/* Co-Branded Logo Header */}
        <div style={{ 
          position: "relative", 
          height: 90, 
          marginTop: 20, 
          borderRadius: 12, 
          overflow: "hidden",
          display: "flex"
        }}>
          {/* Left White Section - Ethio Logo */}
          <div style={{ 
            flex: 1, 
            background: "#FFFFFF", 
            display: "flex", 
            alignItems: "center", 
            justifyContent: "center",
            position: "relative",
            zIndex: 2
          }}>
            <img src="/static/images/ethio-logo.png" alt="Ethio Telecom" style={{ width: 80, height: 50, objectFit: "contain" }} />
          </div>

          {/* Right Dark Section - FlipStar Logo */}
          <div style={{ 
            flex: 1, 
            background: "linear-gradient(to bottom, #0D0D0D, #1A1A1A)", 
            display: "flex", 
            alignItems: "center", 
            justifyContent: "center"
          }}>
            <img src="/static/images/flipstar-logo.png" alt="FlipStar" style={{ width: 80, height: 50, objectFit: "contain" }} />
          </div>

          {/* Gold Diagonal Line SVG Overlay */}
          <svg 
            height="100%" 
            width="100" 
            style={{ 
              position: "absolute", 
              left: "50%", 
              transform: "translateX(-50%)", 
              top: 0,
              zIndex: 3 
            }}
            preserveAspectRatio="none"
          >
            {/* White path covering left side of diagonal */}
            <path
              d="M 0,0 L 55,0 L 20,90 L 0,90 Z"
              fill="#FFFFFF"
            />
            {/* Gold diagonal line */}
            <line
              x1="20"
              y1="90"
              x2="55"
              y2="0"
              stroke="#D4AF37"
              strokeWidth="12.5"
              strokeLinecap="round"
            />
          </svg>
        </div>
      </div>
      <div style={{ flex:1, background:"#fff", borderRadius:"28px 28px 0 0", marginTop:30, padding:"28px 24px 40px" }}>
        <Inp label="Phone Number" type="tel" value={phone} onChange={e=>setPhone(e.target.value)} placeholder="+1234567890" icon="📱" />
        <Inp label="PIN" type={showPin?"text":"password"} value={pin} onChange={e=>setPin(e.target.value)} placeholder="Enter 6-digit PIN" icon="🔒" right={<span onClick={()=>setShowPin(!showPin)} style={{ cursor:"pointer" }}>{showPin?"🙈":"👁️"}</span>} />
        {err&&<div style={{ background:T.redL, borderRadius:10, padding:"8px 12px", fontSize:12, color:T.red, fontWeight:600, marginBottom:12 }}>⚠️ {err}</div>}
        <div style={{ textAlign:"right", marginBottom:16 }}><span onClick={() => setShowForgotPassword(true)} style={{ fontSize:12, color:T.pri, fontWeight:700, cursor:"pointer" }}>Forgot PIN?</span></div>
        <GradBtn onClick={go} disabled={loading}>{loading?"Logging in…":"Log In 🚀"}</GradBtn>
        <div style={{ textAlign:"center", marginTop:16, fontSize:13, color:T.sub }}>Don't have an account? <span onClick={onRegister} style={{ color:T.pri, fontWeight:700, cursor:"pointer" }}>Sign up free</span></div>
      </div>
    </div>
    </>
  );
}




