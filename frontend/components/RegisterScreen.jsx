import { useState, useRef } from "react";
import { ChevronLeft } from "lucide-react";
import { Inp } from "./Inp";
import { GradBtn } from "./GradBtn";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

const PLANS = [
  { id:"free", name:"Explorer", am:"ተመራማሪ", emoji:"🌱", price:"Free", period:"", color:"#10B981", popular:false, features:["1 post/day","Basic analytics","Community access"] },
  { id:"pro", name:"Star", am:"ኮከብ", emoji:"⭐", price:"500 ETB", period:"/mo", color:"#8fc441", popular:true, features:["Unlimited posts","Advanced analytics","Priority support","Monetization"] },
  { id:"premium", name:"Legend", am:"ታላቅ", emoji:"👑", price:"1000 ETB", period:"/mo", color:"#7C3AED", popular:false, features:["Everything in Star","Custom branding","Direct messaging","Exclusive events"] },
];

export function RegisterScreen({ onSuccess, onLogin, onBack }) {
  const T = useLegacyT();
  const [step, setStep] = useState(0);
  const [form, setForm] = useState({ name:"", pw:"", phone:"", country:"+251" });
  const [otp, setOtp] = useState(["","","","",""]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [mc, setMc] = useState({ sms:true, email:true, push:true, inApp:true });
  const [plan, setPlan] = useState("free");
  const [showPw, setShowPw] = useState(false);
  const otpRefs = useRef([]);
  const set = (k,v) => setForm(f=>({...f,[k]:v}));
  const steps = ["Details","Phone","Verify","Privacy","Plan"];

  const sendOtp = async () => {
    setLoading(true);
    try {
      // Check if user has active SMS subscription (OTP-less flow)
      const fullPhone = form.country + form.phone;
      const res = await api.post('/auth/login-with-phone/', { phone: fullPhone, password: 'check' });
      
      // If user has SMS subscription, skip OTP verification
      if (res.data.requires_registration) {
        setErr("");
        setStep(3); // Skip OTP step, go to privacy
      } else {
        // No SMS subscription, send OTP
        const otpRes = await api.post('/auth/send-phone-otp/', { phone: fullPhone });
        if (otpRes.data.message) {
          setErr("");
          setStep(2);
        } else {
          setErr("Failed to send OTP");
        }
      }
    } catch (e) {
      // If no SMS subscription found, send OTP normally
      try {
        const fullPhone = form.country + form.phone;
        const otpRes = await api.post('/auth/send-phone-otp/', { phone: fullPhone });
        if (otpRes.data.message) {
          setErr("");
          setStep(2);
        } else {
          setErr("Failed to send OTP");
        }
      } catch (otpErr) {
        // Check for specific error messages
        const errorMessage = otpErr.response?.data?.error || otpErr.message || "Failed to send OTP. Please try again.";
        if (errorMessage.includes("already registered")) {
          setErr("This phone number is already in use. Please use a different number or log in to your existing account.");
        } else {
          setErr(errorMessage);
        }
      }
    }
    setLoading(false);
  };
  
  const finish = async () => {
    setLoading(true);
    try {
      // Validate all fields
      if (!form.name || !form.pw) {
        throw new Error('All fields are required');
      }
      
      if (form.pw.length < 8) {
        throw new Error('Password must be at least 8 characters');
      }

      // Create unique username by adding timestamp
      const baseUsername = form.name.replace(/\s+/g, '').toLowerCase();
      const timestamp = Date.now().toString().slice(-6);
      const username = `${baseUsername}${timestamp}`;
      
      const firstName = form.name.split(" ")[0];
      const lastName = form.name.split(" ").slice(1).join(" ") || "";
      const fullPhone = form.country + form.phone;
      
      console.log('Registering with:', { username, firstName, lastName, password: form.pw, phone: fullPhone });
      
      // Check if user skipped OTP (has SMS subscription)
      const skippedOtp = step === 3; // If went directly from phone to privacy, OTP was skipped
      
      // Use register_with_phone endpoint with skip_otp parameter
      const res = await api.post('/auth/register-with-phone/', {
        phone: fullPhone,
        username: username,
        password: form.pw,
        skip_otp: skippedOtp
      });
      
      console.log('Registration successful:', res);
      api.setToken(res.token);
      onSuccess({
        name:form.name||"Creator",
        init:(form.name||"C").slice(0,2).toUpperCase(),
        phone:fullPhone,
        plan,
        marketingChoices:mc,
        id: res.user.id
      });
    } catch(e) {
      console.error('Registration error:', e);
      setErr(e.response?.data?.error || e.message || "Signup failed");
      setLoading(false);
    }
  };

  return (
    <div style={{ minHeight:"100vh", background:T.dark, display:"flex", flexDirection:"column" }}>
      <div style={{ padding:"50px 24px 0" }}>
        <button onClick={step===0?onBack:()=>setStep(step-1)} style={{ background:"rgba(255,255,255,0.12)", border:"none", borderRadius:"50%", width:36, height:36, cursor:"pointer", display:"flex", alignItems:"center", justifyContent:"center", color:"#fff" }}>
          <ChevronLeft size={20} />
        </button>
        {/* Logo Header */}
        <div style={{ 
          height: 90, 
          marginTop: 20, 
          borderRadius: 12, 
          display: "flex", 
          flexDirection: "row",
          overflow: "hidden",
          position: "relative"
        }}>
          <div style={{ width: "50%", backgroundColor: "#FFFFFF", height: "100%", position: "absolute", left: 0, top: 0 }}></div>
          <div style={{ width: "50%", backgroundColor: "#000000", height: "100%", position: "absolute", right: 0, top: 0 }}></div>
          <img src="/assets/green-logo.jpg" alt="Logo" style={{ height: 90, width: "100%", objectFit: "contain", position: "relative", zIndex: 1 }} />
        </div>
        <div style={{ marginTop:14, padding:"0 4px" }}>
          <div style={{ fontSize:12, color:"rgba(255,255,255,0.5)", fontWeight:600, marginBottom:7 }}>STEP {step+1} OF {steps.length}</div>
          <div style={{ display:"flex", gap:4 }}>
            {steps.map((_,i)=><div key={i} style={{ flex:1, height:4, borderRadius:4, background:i<=step?T.pri:"rgba(255,255,255,0.15)", transition:"background .3s" }} />)}
          </div>
        </div>
      </div>
      <div style={{ flex:1, background:"#fff", borderRadius:"28px 28px 0 0", marginTop:22, padding:"26px 22px 40px" }}>
        {step===0 && (
          <>
            <div style={{ fontSize:19, fontWeight:800, color:T.txt, marginBottom:4 }}>Create your account 🌟</div>
            <div style={{ fontSize:13, color:T.sub, marginBottom:20 }}>Join thousands of creators</div>
            <Inp label="Full Name" value={form.name} onChange={e=>set("name",e.target.value)} placeholder="Your full name" icon="👤" />
            <Inp label="Password" type={showPw?"text":"password"} value={form.pw} onChange={e=>set("pw",e.target.value)} placeholder="Min 8 characters" icon="🔒" right={<span onClick={()=>setShowPw(!showPw)} style={{ cursor:"pointer" }}>{showPw?"🙈":"👁️"}</span>} />
            {form.pw && <div style={{ display:"flex", gap:4, marginBottom:14 }}>{["Weak","Fair","Strong","Very Strong"].map((_,i)=>{ const s=form.pw.length<6?0:form.pw.length<10?1:form.pw.length<14?2:3; return <div key={i} style={{ flex:1, height:4, borderRadius:4, background:i<=s?["#EF4444","#8fc441","#8fc441","#10B981"][s]:"#E5E7EB" }} />; })}</div>}
            <GradBtn onClick={()=>{ if(!form.name||!form.pw){setErr("Fill all fields");return;} setErr(""); setStep(1); }} disabled={!form.name||!form.pw}>Continue →</GradBtn>
            {err&&<div style={{ marginTop:10, fontSize:12, color:T.red, textAlign:"center" }}>⚠️ {err}</div>}
            <div style={{ textAlign:"center", marginTop:14, fontSize:13, color:T.sub }}>Have an account? <span onClick={onLogin} style={{ color:T.pri, fontWeight:700, cursor:"pointer" }}>Log in</span></div>
          </>
        )}
        {step===1 && (
          <>
            <div style={{ fontSize:19, fontWeight:800, color:T.txt, marginBottom:4 }}>Add your number 📱</div>
            <div style={{ fontSize:13, color:T.sub, marginBottom:20, lineHeight:1.5 }}>SMS verification & notifications. You can opt out anytime.</div>
            <div style={{ marginBottom:14 }}>
              <div style={{ fontSize:11, fontWeight:700, color:T.sub, letterSpacing:"0.5px", marginBottom:6 }}>Country Code</div>
              <select value={form.country} onChange={e=>set("country",e.target.value)} style={{ width:"100%", border:`1.5px solid ${T.border}`, borderRadius:14, padding:"12px 14px", fontSize:14, outline:"none", fontFamily:"inherit", color:T.txt, background:"#fff" }}>
                {[["+251","🇪🇹 Ethiopia"],["+254","🇰🇪 Kenya"],["+27","🇿🇦 South Africa"],["+234","🇳🇬 Nigeria"],["+1","🇺🇸 USA"],["+44","🇬🇧 UK"]].map(([v,l])=>(<option key={v} value={v}>{l}</option>))}
              </select>
            </div>
            <Inp label="Mobile Number" type="tel" value={form.phone} onChange={e=>set("phone",e.target.value)} placeholder="091 000 0000" icon="📞" />
            <GradBtn onClick={()=>{ if(!form.phone){setErr("Enter your phone number");return;} setErr(""); sendOtp(); }} disabled={loading||!form.phone}>{loading?"Sending…":"Send Code 📲"}</GradBtn>
            <button onClick={()=>setStep(3)} style={{ width:"100%", background:"none", border:"none", marginTop:10, fontSize:13, color:T.sub, cursor:"pointer", fontWeight:600 }}>Skip for now →</button>
          </>
        )}
        {step===2 && (
          <>
            <div style={{ fontSize:19, fontWeight:800, color:T.txt, marginBottom:4 }}>Verify your number 🔐</div>
            <div style={{ fontSize:13, color:T.sub, marginBottom:6 }}>5-digit code sent to</div>
            <div style={{ fontSize:15, fontWeight:700, color:T.pri, marginBottom:20 }}>{form.country} {form.phone}</div>
            <div style={{ display:"flex", gap:10, justifyContent:"center", marginBottom:20 }}>
              {otp.map((d,i)=>(
                <input key={i} ref={el=>otpRefs.current[i]=el} type="text" maxLength={1} value={d}
                  onChange={e=>{ const v=e.target.value.replace(/\D/g,""); const n=[...otp]; n[i]=v; setOtp(n); if(v&&i<4) otpRefs.current[i+1]?.focus(); }}
                  onKeyDown={e=>{ if(e.key==="Backspace"&&!otp[i]&&i>0) otpRefs.current[i-1]?.focus(); }}
                  style={{ width:52, height:58, borderRadius:14, border:`2px solid ${d?T.pri:T.border}`, textAlign:"center", fontSize:22, fontWeight:800, color:T.pri, outline:"none", background:d?"#F0F9E8":"#fff" }} />
              ))}
            </div>
            {err&&<div style={{ background:T.redL, borderRadius:10, padding:"8px 12px", fontSize:12, color:T.red, textAlign:"center", marginBottom:12 }}>⚠️ {err}</div>}
            <GradBtn onClick={verifyOtp} disabled={loading||otp.join("").length<5}>{loading?"Verifying…":"Verify ✓"}</GradBtn>
            <div style={{ display:"flex", gap:10, marginTop:12, justifyContent:"center" }}>
              <button onClick={()=>{ setOtp(["","","","",""]); sendOtp(); }} style={{ background:"none", border:"none", color:T.pri, fontSize:13, fontWeight:700, cursor:"pointer" }}>Resend</button>
            </div>
          </>
        )}
        {step===3 && (
          <>
            <div style={{ fontSize:19, fontWeight:800, color:T.txt, marginBottom:4 }}>Your privacy matters 🔒</div>
            <div style={{ fontSize:13, color:T.sub, marginBottom:18, lineHeight:1.5 }}>Choose how we can contact you.</div>
            {[{key:"sms",icon:"📱",title:"SMS Notifications"},{key:"email",icon:"📧",title:"Email Updates"},{key:"push",icon:"🔔",title:"Push Notifications"},{key:"inApp",icon:"💬",title:"In-App"}].map(item=>(
              <div key={item.key} onClick={()=>setMc(p=>({...p,[item.key]:!p[item.key]}))} style={{ display:"flex", alignItems:"center", gap:12, background:mc[item.key]?"#F0F9E8":T.bg, borderRadius:14, padding:"11px 13px", border:`1.5px solid ${mc[item.key]?T.pri:T.border}`, cursor:"pointer", marginBottom:10 }}>
                <span style={{ fontSize:22 }}>{item.icon}</span>
                <div style={{ flex:1 }}>
                  <div style={{ fontSize:13, fontWeight:700, color:T.txt }}>{item.title}</div>
                </div>
                <div style={{ width:44, height:24, borderRadius:12, background:mc[item.key]?T.pri:"#D1D5DB", display:"flex", alignItems:"center", padding:"3px", transition:"background .2s", flexShrink:0 }}>
                  <div style={{ width:18, height:18, borderRadius:"50%", background:"#fff", transform:mc[item.key]?"translateX(20px)":"none", transition:"transform .2s" }} />
                </div>
              </div>
            ))}
            <GradBtn onClick={()=>setStep(4)} style={{marginTop:20}}>Continue →</GradBtn>
          </>
        )}
        {step===4 && (
          <>
            <div style={{ fontSize:19, fontWeight:800, color:T.txt, marginBottom:4 }}>Choose your plan 🚀</div>
            <div style={{ fontSize:13, color:T.sub, marginBottom:18 }}>Upgrade anytime</div>
            {PLANS.map(p=>(
              <div key={p.id} onClick={()=>setPlan(p.id)} style={{ borderRadius:18, border:`2px solid ${plan===p.id?p.color:T.border}`, background:plan===p.id?p.color+"10":"#fff", padding:"13px 15px", cursor:"pointer", marginBottom:11, position:"relative", overflow:"hidden" }}>
                {p.popular && <div style={{ position:"absolute", top:0, right:0, background:`linear-gradient(135deg,${T.pri},${T.dark})`, color:"#fff", fontSize:10, fontWeight:800, padding:"4px 12px", borderRadius:"0 18px 0 12px" }}>POPULAR</div>}
                <div style={{ display:"flex", alignItems:"center", gap:12 }}>
                  <div style={{ width:44, height:44, borderRadius:12, background:p.color+"18", display:"flex", alignItems:"center", justifyContent:"center", fontSize:22, flexShrink:0 }}>{p.emoji}</div>
                  <div style={{ flex:1 }}>
                    <div style={{ fontSize:16, fontWeight:800, color:T.txt }}>{p.name}</div>
                    <div style={{ fontSize:13, color:p.color, fontWeight:700 }}>{p.price}<span style={{ fontSize:11, color:T.sub, fontWeight:500 }}>{p.period}</span></div>
                  </div>
                  <div style={{ width:22, height:22, borderRadius:"50%", border:`2px solid ${plan===p.id?p.color:T.border}`, background:plan===p.id?p.color:"transparent", display:"flex", alignItems:"center", justifyContent:"center", fontSize:11, color:"#fff" }}>{plan===p.id?"✓":""}</div>
                </div>
              </div>
            ))}
            {err&&<div style={{ background:T.redL, borderRadius:10, padding:"8px 12px", fontSize:12, color:T.red, textAlign:"center", marginBottom:12 }}>⚠️ {err}</div>}
            <GradBtn onClick={finish} disabled={loading}>{loading?"Setting up…":`Start with ${PLANS.find(p=>p.id===plan)?.name} 🌟`}</GradBtn>
          </>
        )}
      </div>
    </div>
  );
}




