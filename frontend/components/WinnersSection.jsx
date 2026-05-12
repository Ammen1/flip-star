import { useState, useEffect } from "react";
import api from "../api";
import { useTheme } from "../contexts/ThemeContext";

export function WinnersSection() {
  const { colors: T } = useTheme();
  const [winners, setWinners] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchWinners();
  }, []);

  const fetchWinners = async () => {
    try {
      setLoading(true);
      const data = await api.getLatestWinners();
      setWinners(data);
    } catch (error) {
      console.error("Failed to fetch winners:", error);
    } finally {
      setLoading(false);
    }
  };

  // Move early returns to after all hooks
  let content;
  if (loading) {
    content = (
      <div style={{ padding: 20, textAlign: "center", color: T.sub }}>
        Loading winners...
      </div>
    );
  } else if (winners.length === 0) {
    content = (
      <div style={{ padding: 20, textAlign: "center", color: T.sub }}>
        No winners yet
      </div>
    );
  } else {
    content = (
      <div style={{ padding: "20px 0" }}>
        <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 12, padding: "0 20px" }}>
          🏆 Recent Winners
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 12, padding: "0 20px" }}>
          {winners.map((winner, idx) => (
            <div
              key={winner.id}
              style={{
                padding: 12,
                background: idx === 0 
                  ? "linear-gradient(135deg, #FFD700, #FFA500)" 
                  : T.bg,
                borderRadius: 12,
                border: idx === 0 ? "2px solid #FFD700" : `1px solid ${T.border}`,
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: "50%",
                  background: idx === 0 ? "#000" : T.pri + "30",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 16,
                  flexShrink: 0,
                }}>
                  {idx === 0 ? "👑" : "🏅"}
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ 
                    fontSize: 12, 
                    fontWeight: 700, 
                    color: idx === 0 ? "#000" : T.txt,
                    overflow: "hidden", 
                    textOverflow: "ellipsis", 
                    whiteSpace: "nowrap" 
                  }}>
                    {winner.user?.username || "Unknown"}
                  </div>
                  <div style={{ 
                    fontSize: 10, 
                    color: idx === 0 ? "#333" : T.sub,
                    overflow: "hidden", 
                    textOverflow: "ellipsis", 
                    whiteSpace: "nowrap" 
                  }}>
                    {winner.competition?.title || "Competition"}
                  </div>
                </div>
              </div>
              <div style={{ 
                fontSize: 11, 
                color: idx === 0 ? "#000" : T.sub,
                display: "flex",
                alignItems: "center",
                gap: 8,
              }}>
                <span>❤️ {winner.votes_received} votes</span>
                {winner.prize_claimed && <span>✅ Prize claimed</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    );
  }

  return content;
}




