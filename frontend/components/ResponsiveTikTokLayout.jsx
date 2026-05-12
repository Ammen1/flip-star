import { useState, useEffect } from "react";
import { TikTokLayout } from "./TikTokLayout";

export function ResponsiveTikTokLayout(props) {
  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    const checkMobile = () => {
      setIsMobile(window.innerWidth <= 1024);
    };
    
    checkMobile();
    window.addEventListener('resize', checkMobile);
    
    return () => window.removeEventListener('resize', checkMobile);
  }, []);

  if (isMobile) {
    return (
      <div style={{
        width: '100vw',
        height: '100vh',
        overflow: 'hidden',
        position: 'fixed',
        top: 0,
        left: 0,
      }}>
        <style>{`
          @media (max-width: 1024px) {
            .left-sidebar, .right-sidebar {
              display: none !important;
            }
            .video-feed {
              margin-left: 0 !important;
              margin-right: 0 !important;
              width: 100vw !important;
              max-width: 100vw !important;
            }
            .video-container {
              width: 100vw !important;
              max-width: 100vw !important;
              height: 100vh !important;
              border-radius: 0 !important;
              margin: 0 !important;
            }
            .video-actions {
              right: 16px !important;
              bottom: 140px !important;
            }
            .video-info {
              padding: 16px !important;
              max-width: calc(100vw - 100px) !important;
            }
          }
          
          @media (orientation: landscape) and (max-width: 1024px) {
            .video-container {
              height: 100vh !important;
            }
            .video-actions {
              right: 12px !important;
              bottom: 100px !important;
              gap: 12px !important;
            }
          }
        `}</style>
        <TikTokLayout {...props} />
      </div>
    );
  }

  return <TikTokLayout {...props} />;
}




