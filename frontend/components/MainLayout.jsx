import { useState, useEffect } from "react";
import { Sidebar } from "./Sidebar";
import { FeedPage } from "./FeedPage";
import { useLegacyT } from "../contexts/ThemeContext";

export function MainLayout({ user, onLogout }) {
  const T = useLegacyT();
  const [activeTab, setActiveTab] = useState("feed");
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 1024);

  useEffect(() => {
    const checkMobile = () => setIsMobile(window.innerWidth <= 1024);
    checkMobile();
    window.addEventListener('resize', checkMobile);
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  return (
    <div style={{
      display: "flex",
      height: "100vh",
      background: T.bg,
    }}>
      {/* Sidebar - handles mobile hamburger internally */}
      <Sidebar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        user={user}
        onLogout={onLogout}
      />

      {/* Main Content */}
      <div style={{
        marginLeft: isMobile ? 0 : 280,
        marginTop: isMobile ? 56 : 0,
        flex: 1,
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
      }}>
        <FeedPage tab={activeTab} />
      </div>
    </div>
  );
}




