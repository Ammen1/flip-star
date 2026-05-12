import { useLegacyT } from "../contexts/ThemeContext";

export function SplashScreen({ onLogin, onRegister }) {
  const T = useLegacyT();

  return (
    <div style={{ minHeight:"100vh", background:`linear-gradient(135deg, ${T.dark}, #1a2f1f)`, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"20px" }}>
      <div style={{ textAlign:"center" }}>
        <div style={{ fontSize:80, marginBottom:20 }}>⭐</div>
        <div style={{ fontSize:42, fontWeight:900, color:"#fff", marginBottom:8 }}>Selfie Star</div>
        <div style={{ fontSize:16, color:"rgba(255,255,255,0.7)", marginBottom:40 }}>Share · Win · Shine</div>
        
        <button onClick={onRegister} style={{ width:"100%", maxWidth:300, padding:"16px", background:T.pri, border:"none", borderRadius:14, color:"#fff", fontSize:16, fontWeight:700, cursor:"pointer", marginBottom:12 }}>
          Create Account 🚀
        </button>
        
        <button onClick={onLogin} style={{ width:"100%", maxWidth:300, padding:"16px", background:"rgba(255,255,255,0.15)", border:"2px solid rgba(255,255,255,0.3)", borderRadius:14, color:"#fff", fontSize:16, fontWeight:700, cursor:"pointer" }}>
          Log In
        </button>
      </div>
    </div>
  );
}




