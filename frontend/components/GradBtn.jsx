import { useLegacyT } from "../contexts/ThemeContext";

export function GradBtn({ children, onClick, disabled, style={}, small }) {
  const T = useLegacyT();
  
  return (
    <button onClick={onClick} disabled={disabled} style={{
      width:"100%",
      padding: small ? "10px 16px" : "14px 20px",
      background: `linear-gradient(135deg, ${T.pri}, ${T.priD})`,
      border:"none",
      borderRadius:14,
      color:"#fff",
      fontSize: small ? 13 : 15,
      fontWeight:700,
      cursor: disabled ? "not-allowed" : "pointer",
      opacity: disabled ? 0.6 : 1,
      transition:"all .2s",
      ...style
    }}>
      {children}
    </button>
  );
}




