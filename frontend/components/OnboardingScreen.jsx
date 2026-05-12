import { useState } from "react";
import { GradBtn } from "./GradBtn";
import { useLegacyT } from "../contexts/ThemeContext";

export function OnboardingScreen({ user, onDone }) {
  const T = useLegacyT();
  const [step, setStep] = useState(0);
  const steps = [
    { title: "Welcome to Selfie Star! 🌟", desc: "Share your best moments and win amazing prizes", emoji: "📸" },
    { title: "Earn XP & Level Up 🚀", desc: "Complete quests and challenges to climb the leaderboard", emoji: "⭐" },
    { title: "Vote & Win 🏆", desc: "Vote on reels from other creators and earn rewards", emoji: "🎯" },
    { title: "Join the Community 👥", desc: "Connect with creators and build your audience", emoji: "💫" },
  ];

  return (
    <div style={{ minHeight:"100vh", background:T.dark, display:"flex", flexDirection:"column", alignItems:"center", justifyContent:"center", padding:"20px" }}>
      <div style={{ textAlign:"center", maxWidth:400 }}>
        <div style={{ fontSize:80, marginBottom:20, animation:"bounce 2s infinite" }}>{steps[step].emoji}</div>
        <div style={{ fontSize:28, fontWeight:900, color:"#fff", marginBottom:12 }}>{steps[step].title}</div>
        <div style={{ fontSize:16, color:"rgba(255,255,255,0.7)", marginBottom:40, lineHeight:1.6 }}>{steps[step].desc}</div>
        
        <div style={{ display:"flex", gap:4, justifyContent:"center", marginBottom:40 }}>
          {steps.map((_,i)=><div key={i} style={{ width:8, height:8, borderRadius:"50%", background:i===step?T.pri:"rgba(255,255,255,0.3)", transition:"background .3s" }} />)}
        </div>

        {step < steps.length - 1 ? (
          <GradBtn onClick={()=>setStep(step+1)}>Next →</GradBtn>
        ) : (
          <GradBtn onClick={onDone}>Start Creating 🎬</GradBtn>
        )}
      </div>
      <style>{`@keyframes bounce { 0%, 100% { transform: translateY(0); } 50% { transform: translateY(-20px); } }`}</style>
    </div>
  );
}




