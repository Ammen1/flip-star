import { useState, useCallback, useRef } from "react";
import { Heart } from "lucide-react";

// Static styles injected once, not per render
let stylesInjected = false;
function injectStyles() {
  if (stylesInjected) return;
  stylesInjected = true;
  const style = document.createElement('style');
  style.textContent = `
    .like-btn{background:transparent;border:none;cursor:pointer;padding:0;display:flex;align-items:center;justify-content:center;will-change:transform;transform:translate3d(0,0,0)}
    .like-btn:active{transform:scale(0.85) translate3d(0,0,0)}
    .like-btn svg{will-change:transform;transition:transform .15s cubic-bezier(.175,.885,.32,1.275),fill .1s,stroke .1s}
    .like-pop svg{animation:likePop .35s cubic-bezier(.175,.885,.32,1.275)}
    .like-burst{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;opacity:0}
    .like-burst.active{animation:heartBurst .6s ease-out forwards}
    @keyframes likePop{0%{transform:scale(1)}30%{transform:scale(1.35)}60%{transform:scale(.95)}100%{transform:scale(1)}}
    @keyframes heartBurst{0%{opacity:.9;transform:translate(-50%,-50%) scale(0)}40%{opacity:.7;transform:translate(-50%,-50%) scale(1.4)}100%{opacity:0;transform:translate(-50%,-50%) scale(2)}}
  `;
  document.head.appendChild(style);
}

export function LikeButton({ liked, count, onLike, size = 24 }) {
  const [burstKey, setBurstKey] = useState(0);
  const [popping, setPopping] = useState(false);
  const btnRef = useRef(null);

  // Inject styles once on first mount
  if (!stylesInjected) injectStyles();

  const handleClick = useCallback(() => {
    // Trigger pop animation
    setPopping(true);
    // Trigger burst only on like (not unlike)
    if (!liked) {
      setBurstKey(k => k + 1);
    }
    onLike();
  }, [liked, onLike]);

  return (
    <div style={{ position: "relative", display: "flex", flexDirection: "column", alignItems: "center", gap: 6 }}>
      <button
        ref={btnRef}
        className={`like-btn${popping ? ' like-pop' : ''}`}
        onClick={handleClick}
        onAnimationEnd={() => setPopping(false)}
      >
        <Heart
          size={size}
          fill={liked ? "#E2B355" : "none"}
          stroke={liked ? "#E2B355" : "#fff"}
          strokeWidth={2}
        />
      </button>

      <div
        key={burstKey}
        className={`like-burst${burstKey > 0 ? ' active' : ''}`}
      >
        <Heart size={size * 1.8} fill="#E2B355" stroke="none" />
      </div>

      <div style={{ fontSize: 12, fontWeight: 700, color: "#fff", textAlign: "center" }}>{count}</div>
    </div>
  );
}




