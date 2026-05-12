import { useState, useEffect, useRef, memo } from 'react';
import { createPortal } from 'react-dom';
import { X } from 'lucide-react';
import api from '../api';

/* ─── CONSTANTS ─────────────────────────────── */
const SPIN_SEGMENTS = [
  { label: '10 Coins',  emoji: '🪙', color: '#F59E0B', coins: 10 },
  { label: '25 Coins',  emoji: '💰', color: '#DA9B2A', coins: 25 },
  { label: '5 Coins',   emoji: '🪙', color: '#FCD34D', coins: 5  },
  { label: '50 Coins',  emoji: '🏆', color: '#EF4444', coins: 50 },
  { label: '15 Coins',  emoji: '🪙', color: '#F59E0B', coins: 15 },
  { label: '100 Coins', emoji: '💎', color: '#8B5CF6', coins: 100 },
  { label: '20 Coins',  emoji: '🪙', color: '#DA9B2A', coins: 20 },
  { label: 'XP Boost',  emoji: '⚡', color: '#10B981', coins: 0  },
];

/* ─── FULL-SCREEN MODAL WRAPPER ──────────────── */
const Modal = memo(function Modal({ onClose, children }) {
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);
  return createPortal(
    <div onClick={onClose} style={{
      position:'fixed',top:0,left:0,right:0,bottom:0,
      background:'rgba(0,0,0,.6)',
      display:'flex',alignItems:'flex-end',justifyContent:'center',
      zIndex:99999,
    }}>
      <div onClick={e=>e.stopPropagation()} style={{
        background:'#fff',borderRadius:'24px 24px 0 0',
        width:'100%',maxWidth:480,maxHeight:'80vh',
        paddingBottom:'calc(80px + env(safe-area-inset-bottom, 0px))',
        boxShadow:'0 -8px 40px rgba(0,0,0,.25)',
        display:'flex',flexDirection:'column',
      }}>
        <div style={{width:40,height:4,background:'#E7E5E4',borderRadius:4,margin:'12px auto 0'}}/>
        <div style={{overflowY:'auto',flex:1}}>
          {children}
        </div>
      </div>
    </div>,
    document.body
  );
});

const ModalHeader = memo(function ModalHeader({ title, onClose }) {
  return (
    <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'16px 20px 8px'}}>
      <span style={{fontSize:18,fontWeight:700,color:'#F9E08B'}}>{title}</span>
      <button onClick={onClose} style={{background:'rgba(249,224,139,0.1)',border:'1px solid rgba(249,224,139,0.2)',borderRadius:'50%',width:32,height:32,display:'flex',alignItems:'center',justifyContent:'center',cursor:'pointer'}}>
        <X size={16} color='#F9E08B'/>
      </button>
    </div>
  );
});

/* ─── COINS MODAL ────────────────────────────── */
const CoinsModal = memo(function CoinsModal({ coins, points, onClose }) {
  return (
    <Modal onClose={onClose}>
      <ModalHeader title="💰 Balance" onClose={onClose}/>
      <div style={{padding:'12px 20px'}}>
        {/* Coins Balance */}
        <div style={{background:'linear-gradient(135deg,#F9E08B,#F59E0B)',borderRadius:20,padding:'28px 20px',textAlign:'center',marginBottom:20,boxShadow:'0 8px 32px rgba(249,224,139,0.3)'}}>
          <div style={{fontSize:56,marginBottom:4}}>🪙</div>
          <div style={{fontSize:48,fontWeight:900,color:'#000',lineHeight:1}}>{coins?.balance ?? 0}</div>
          <div style={{fontSize:14,color:'rgba(0,0,0,.75)',marginTop:4,fontWeight:600}}>Available Coins</div>
        </div>
        {/* Points Balance */}
        <div style={{background:'linear-gradient(135deg,#8B5CF6,#6D28D9)',borderRadius:20,padding:'28px 20px',textAlign:'center',marginBottom:20,boxShadow:'0 8px 32px rgba(139,92,246,0.3)'}}>
          <div style={{fontSize:56,marginBottom:4}}>⭐</div>
          <div style={{fontSize:48,fontWeight:900,color:'#000',lineHeight:1}}>{points ?? 0}</div>
          <div style={{fontSize:14,color:'rgba(0,0,0,.75)',marginTop:4,fontWeight:600}}>Available Points (Withdrawable)</div>
        </div>
        <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:12}}>
          {[
            {label:'Total Coins Earned',value:coins?.earned_total??0,color:'#10B981',emoji:'📈'},
            {label:'Total Coins Spent',value:coins?.spent_total??0,color:'#EF4444',emoji:'📉'},
            {label:'Total Points Earned',value:points?.earned_total??0,color:'#8B5CF6',emoji:'⭐'},
            {label:'Total Points Withdrawn',value:points?.withdrawn_total??0,color:'#F59E0B',emoji:'💸'},
          ].map(s=>(
            <div key={s.label} style={{background:s.color+'12',border:`1.5px solid ${s.color}30`,borderRadius:14,padding:'14px 16px',textAlign:'center'}}>
              <div style={{fontSize:24,marginBottom:4}}>{s.emoji}</div>
              <div style={{fontSize:22,fontWeight:800,color:s.color}}>{s.value}</div>
              <div style={{fontSize:11,color:'#78716C',marginTop:2}}>{s.label}</div>
            </div>
          ))}
        </div>
        <div style={{marginTop:16,background:'rgba(139,92,246,0.08)',borderRadius:12,padding:'12px 16px',fontSize:13,color:'#78716C',textAlign:'center',border:'1px solid rgba(139,92,246,0.15)'}}>
          💡 Gifts convert to points. Points can be withdrawn as birr!
        </div>
      </div>
    </Modal>
  );
});

/* ─── STREAK MODAL ───────────────────────────── */
const StreakModal = memo(function StreakModal({ streak, onClaim, onClose }) {
  const [claimed, setClaimed] = useState(false);
  const [claiming, setClaiming] = useState(false);
  const cur = streak?.current ?? 0;

  // Get real calendar days starting from today going back 6 days
  const getRealDays = () => {
    const dayNames = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
    const today = new Date();
    const days = [];
    for (let i = 6; i >= 0; i--) {
      const d = new Date(today);
      d.setDate(today.getDate() - i);
      days.push({
        name: dayNames[d.getDay()],
        date: d.getDate(),
        isToday: i === 0,
        isPast: i > 0,
      });
    }
    return days;
  };
  const realDays = getRealDays();

  const handleClaim = async () => {
    if (claiming) return;
    setClaiming(true);
    try {
      await onClaim();
      setClaimed(true);
    } catch (e) {
      console.error('Claim failed:', e);
    } finally {
      setClaiming(false);
    }
  };

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="🔥 Login Streak" onClose={onClose}/>
      <div style={{padding:'8px 20px 0'}}>
        <div style={{background:'linear-gradient(135deg,#F9E08B,#F59E0B)',borderRadius:20,padding:'24px 20px',textAlign:'center',marginBottom:20,boxShadow:'0 8px 32px rgba(249,224,139,0.3)'}}>
          <div style={{fontSize:52}}>🔥</div>
          <div style={{fontSize:44,fontWeight:900,color:'#000',lineHeight:1}}>{cur}</div>
          <div style={{fontSize:14,color:'rgba(0,0,0,.75)',marginTop:4,fontWeight:600}}>Day Streak</div>
          {(streak?.longest??0) > 0 && (
            <div style={{fontSize:12,color:'rgba(0,0,0,.65)',marginTop:6}}>Best: {streak.longest} days 🏆</div>
          )}
        </div>

        {/* 7-day progress - real calendar days */}
        <div style={{display:'flex',justifyContent:'space-between',marginBottom:20,padding:'0 4px'}}>
          {realDays.map((day, i)=>{
            // Mark days as active based on streak count (last N days)
            const daysFromEnd = 6 - i; // 0 for today, 6 for 6 days ago
            const active = daysFromEnd < cur && daysFromEnd > 0; // Past days within streak
            const isToday = day.isToday;
            return (
              <div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center',gap:4}}>
                <div style={{
                  width:36,height:36,borderRadius:'50%',
                  background: active ? 'linear-gradient(135deg,#F9E08B,#F59E0B)' : isToday ? 'rgba(249,224,139,0.1)' : '#F5F5F4',
                  border: isToday ? '2.5px solid #F9E08B' : active ? 'none' : '2px solid transparent',
                  display:'flex',alignItems:'center',justifyContent:'center',
                  fontSize: isToday ? 12 : 14,
                  fontWeight: 700,
                  color: active ? '#000' : isToday ? '#F9E08B' : '#A8A29E',
                  boxShadow: active ? '0 2px 8px rgba(249,224,139,.35)' : isToday ? '0 2px 8px rgba(249,224,139,.2)' : 'none'
                }}>
                  {active ? '✓' : day.date}
                </div>
                <span style={{fontSize:10,color: active || isToday ? '#F9E08B' : '#A8A29E',fontWeight:600}}>{day.name}</span>
              </div>
            );
          })}
        </div>

        {(streak?.bonus_available && !claimed) ? (
          <button onClick={handleClaim} disabled={claiming} style={{
            width:'100%',padding:'16px',borderRadius:14,border:'none',
            background: claiming ? 'rgba(249,224,139,0.5)' : '#F9E08B',
            color: '#000',fontSize:17,fontWeight:700,
            cursor: claiming ? 'not-allowed' : 'pointer',
            boxShadow: claiming ? 'none' : '0 4px 16px rgba(249,224,139,0.4)'
          }}>
            {claiming ? 'Claiming...' : `Claim +${streak.next_bonus?.coins ?? 0} Coins`}
          </button>
        ) : claimed ? (
          <div style={{textAlign:'center',padding:'16px',background:'#ECFDF5',borderRadius:14,color:'#10B981',fontWeight:700}}>
            ✅ Bonus Claimed!
          </div>
        ) : (
          <div style={{textAlign:'center',padding:'16px',background:'#F5F5F4',borderRadius:14,color:'#78716C',fontSize:14}}>
            Come back tomorrow for your next bonus 🌙
          </div>
        )}
      </div>
    </Modal>
  );
});

/* ─── SPIN MODAL ─────────────────────────────── */
const SpinModal = memo(function SpinModal({ spin, onSpin, onClose }) {
  const [angle, setAngle] = useState(0);
  const [spinning, setSpinning] = useState(false);
  const [result, setResult] = useState(null);
  const wheelRef = useRef(null);
  const n = SPIN_SEGMENTS.length;
  const segAngle = 360 / n;

  const doSpin = async () => {
    if (spinning || !spin?.can_spin) return;
    setSpinning(true);
    setResult(null);
    const extra = 1440 + Math.floor(Math.random() * 360);
    const newAngle = angle + extra;
    setAngle(newAngle);

    // wait for animation
    setTimeout(async () => {
      try {
        const res = await onSpin();
        setResult(res);
      } catch {
        setResult({ reward: { label: 'Try again!', emoji: '😅' }, coins_earned: 0, new_balance: spin?.spins_total ?? 0 });
      } finally {
        setSpinning(false);
      }
    }, 3200);
  };

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="🔄 Daily Spin" onClose={onClose}/>
      <div style={{padding:'8px 20px 0',textAlign:'center'}}>
        {result ? (
          <div style={{padding:'20px 0'}}>
            <div style={{fontSize:72,marginBottom:12}}>{result.reward?.emoji ?? '🎉'}</div>
            <div style={{fontSize:26,fontWeight:800,color:'#DA9B2A',marginBottom:4}}>{result.reward?.label}</div>
            {result.coins_earned > 0 && (
              <div style={{fontSize:16,color:'#10B981',fontWeight:600,marginBottom:4}}>+{result.coins_earned} coins added!</div>
            )}
            <div style={{fontSize:13,color:'#78716C',marginBottom:24}}>New balance: <b>{result.new_balance}</b> 🪙</div>
            <button onClick={onClose} style={{
              width:'100%',padding:'16px',borderRadius:14,border:'none',
              background:'linear-gradient(135deg,#DA9B2A,#F59E0B)',color:'#fff',
              fontSize:16,fontWeight:700,cursor:'pointer',
              boxShadow:'0 4px 16px rgba(218,155,42,.4)'
            }}>
              Awesome! 🎉
            </button>
          </div>
        ) : (
          <>
            {/* Wheel */}
            <div style={{position:'relative',width:240,height:240,margin:'0 auto 20px'}}>
              {/* pointer */}
              <div style={{position:'absolute',top:-10,left:'50%',transform:'translateX(-50%)',zIndex:10,fontSize:24}}>▼</div>
              <svg ref={wheelRef} width={240} height={240} style={{
                transform:`rotate(${angle}deg)`,
                transition: spinning ? 'transform 3.2s cubic-bezier(.17,.67,.12,.99)' : 'none',
                borderRadius:'50%',boxShadow:'0 8px 32px rgba(0,0,0,.2)'
              }}>
                {SPIN_SEGMENTS.map((seg, i) => {
                  const startAngle = (i * segAngle - 90) * (Math.PI / 180);
                  const endAngle = ((i + 1) * segAngle - 90) * (Math.PI / 180);
                  const x1 = 120 + 115 * Math.cos(startAngle);
                  const y1 = 120 + 115 * Math.sin(startAngle);
                  const x2 = 120 + 115 * Math.cos(endAngle);
                  const y2 = 120 + 115 * Math.sin(endAngle);
                  const midAngle = ((i + 0.5) * segAngle - 90) * (Math.PI / 180);
                  const tx = 120 + 75 * Math.cos(midAngle);
                  const ty = 120 + 75 * Math.sin(midAngle);
                  return (
                    <g key={i}>
                      <path d={`M120,120 L${x1},${y1} A115,115 0 0,1 ${x2},${y2} Z`} fill={seg.color} stroke="#fff" strokeWidth={2}/>
                      <text x={tx} y={ty} textAnchor="middle" dominantBaseline="middle" fontSize={18}>{seg.emoji}</text>
                    </g>
                  );
                })}
                <circle cx={120} cy={120} r={20} fill="#fff" stroke="#DA9B2A" strokeWidth={3}/>
                <text x={120} y={120} textAnchor="middle" dominantBaseline="middle" fontSize={16}>⭐</text>
              </svg>
            </div>

            {spin?.can_spin ? (
              <button onClick={doSpin} disabled={spinning} style={{
                width:'100%',padding:'18px',borderRadius:14,border:'none',
                background: spinning ? '#E7E5E4' : 'linear-gradient(135deg,#DA9B2A,#F59E0B)',
                color: spinning ? '#78716C' : '#fff',fontSize:18,fontWeight:800,
                cursor: spinning ? 'not-allowed' : 'pointer',
                boxShadow: spinning ? 'none' : '0 4px 20px rgba(218,155,42,.5)',
                letterSpacing:1
              }}>
                {spinning ? '⏳ Spinning...' : '🔄 SPIN!'}
              </button>
            ) : (
              <div style={{background:'#F5F5F4',borderRadius:14,padding:'16px',color:'#78716C',fontSize:14}}>
                ✅ You already spun today! Come back tomorrow 🌙
              </div>
            )}
            <div style={{fontSize:12,color:'#A8A29E',marginTop:12}}>Total spins: {spin?.spins_total ?? 0}</div>
          </>
        )}
      </div>
    </Modal>
  );
});

/* ─── GIFT MODAL ─────────────────────────────── */
const GiftModal = memo(function GiftModal({ coins, onClose, onRefresh, onShowWallet }) {
  const [recipientId, setRecipientId] = useState('');
  const [amount, setAmount] = useState(10);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [done, setDone] = useState(null);
  const [error, setError] = useState('');

  const send = async () => {
    if (!recipientId.trim()) { setError('Enter a recipient username or ID'); return; }
    if (amount < 1 || amount > (coins?.balance ?? 0)) { setError('Invalid amount'); return; }
    setSending(true); setError('');
    try {
      const res = await api.request('/gamification/gift/', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        body: JSON.stringify({ recipient_username: recipientId, amount, message })
      });
      setDone(res);
      onRefresh();
    } catch(e) { setError(e.message || 'Failed to send gift'); }
    finally { setSending(false); }
  };

  return (
    <Modal onClose={onClose}>
      <ModalHeader title="🎁 Send Coin Gift" onClose={onClose}/>
      <div style={{padding:'8px 20px 20px', maxHeight:'70vh', display:'flex', flexDirection:'column'}}>
        {done ? (
          <div style={{textAlign:'center',padding:'24px 0'}}>
            <div style={{fontSize:64,marginBottom:12}}>🎉</div>
            <div style={{fontSize:20,fontWeight:800,color:'#F9E08B',marginBottom:4}}>Gift Sent!</div>
            <div style={{fontSize:14,color:'#78716C',marginBottom:24}}>
              You sent <b style={{color:'#F9E08B'}}>{done.amount} coins</b> to <b>@{done.recipient?.username}</b>
            </div>
            <button onClick={onClose} style={{width:'100%',padding:'16px',borderRadius:14,border:'none',background:'#F9E08B',color:'#000',fontSize:16,fontWeight:700,cursor:'pointer',boxShadow:'0 4px 16px rgba(249,224,139,0.4)'}}>
              Done 🎊
            </button>
          </div>
        ) : (
          <>
            {/* balance chip */}
            <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',background:'rgba(249,224,139,0.1)',borderRadius:12,padding:'10px 14px',marginBottom:16,border:'1px solid rgba(249,224,139,0.2)', flexShrink: 0}}>
              <span style={{fontSize:13,color:'#78716C'}}>Your balance</span>
              <span style={{fontWeight:800,color:'#F9E08B',fontSize:16}}>🪙 {coins?.balance ?? 0}</span>
            </div>

            <div style={{overflowY:'auto', flex: 1, marginBottom: 16, minHeight: 0}}>
              <label style={{fontSize:13,fontWeight:600,color:'#78716C',display:'block',marginBottom:6}}>Recipient Username</label>
              <input value={recipientId} onChange={e=>setRecipientId(e.target.value)}
                placeholder="e.g. johndoe"
                style={{width:'100%',padding:'13px 14px',borderRadius:12,border:'1.5px solid rgba(249,224,139,0.3)',fontSize:15,marginBottom:14,boxSizing:'border-box',outline:'none'}}
              />

              <label style={{fontSize:13,fontWeight:600,color:'#78716C',display:'block',marginBottom:8}}>Amount</label>
              <div style={{display:'flex',alignItems:'center',gap:12,marginBottom:14}}>
                <button onClick={()=>setAmount(a=>Math.max(1,a-5))}
                  style={{width:40,height:40,borderRadius:10,border:'1.5px solid rgba(249,224,139,0.3)',background:'rgba(249,224,139,0.1)',cursor:'pointer',fontSize:18,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:700,color:'#F9E08B'}}>
                  −
                </button>
                <div style={{flex:1,textAlign:'center',fontSize:28,fontWeight:800,color:'#F9E08B'}}>
                  🪙 {amount}
                </div>
                <button onClick={()=>setAmount(a=>Math.min(coins?.balance??100,a+5))}
                  style={{width:40,height:40,borderRadius:10,border:'1.5px solid rgba(249,224,139,0.3)',background:'rgba(249,224,139,0.1)',cursor:'pointer',fontSize:18,display:'flex',alignItems:'center',justifyContent:'center',fontWeight:700,color:'#F9E08B'}}>
                  +
                </button>
              </div>
              {/* quick amounts */}
              <div style={{display:'flex',gap:8,marginBottom:14}}>
                {[10,25,50,100].map(v=>(
                  <button key={v} onClick={()=>setAmount(Math.min(v,coins?.balance??0))}
                    style={{flex:1,padding:'8px 0',borderRadius:8,border:`1.5px solid ${amount===v?'#F9E08B':'rgba(249,224,139,0.3)'}`,background:amount===v?'rgba(249,224,139,0.15)':'#fff',color:amount===v?'#F9E08B':'#78716C',fontWeight:600,cursor:'pointer',fontSize:13}}>
                    {v}
                  </button>
                ))}
              </div>

              <label style={{fontSize:13,fontWeight:600,color:'#78716C',display:'block',marginBottom:6}}>Message (optional)</label>
              <input value={message} onChange={e=>setMessage(e.target.value)}
                placeholder="Say something nice ✨"
                style={{width:'100%',padding:'13px 14px',borderRadius:12,border:'1.5px solid rgba(249,224,139,0.3)',fontSize:15,marginBottom:16,boxSizing:'border-box',outline:'none'}}
              />

              {error && <div style={{color:'#EF4444',fontSize:13,marginBottom:12,padding:'10px 14px',background:'#FEF2F2',borderRadius:10}}>{error}</div>}
            </div>

            <button onClick={send} disabled={sending}
              style={{width:'100%',padding:'16px',borderRadius:14,border:'none',
                background: sending ? 'rgba(249,224,139,0.5)' : '#F9E08B',
                color: '#000',fontSize:16,fontWeight:700,cursor:sending?'not-allowed':'pointer',
                boxShadow: sending?'none':'0 4px 20px rgba(249,224,139,.4)', flexShrink: 0}}>
              {sending ? 'Sending...' : `🎁 Send ${amount} Coins`}
            </button>
          </>
        )}
      </div>
    </Modal>
  );
});

/* ─── SPIN WHEEL ICON ──────────────────────────── */
const SpinWheelIcon = memo(function SpinWheelIcon({ size = 28, color = '#DA9B2A' }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke={color} strokeWidth="2" fill="none"/>
      <path d="M12 2 L12 12 L19.5 5" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.3"/>
      <path d="M12 12 L19.5 5 L22 12" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.15"/>
      <path d="M12 12 L22 12 L19.5 19" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.3"/>
      <path d="M12 12 L19.5 19 L12 22" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.15"/>
      <path d="M12 12 L12 22 L4.5 19" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.3"/>
      <path d="M12 12 L4.5 19 L2 12" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.15"/>
      <path d="M12 12 L2 12 L4.5 5" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.3"/>
      <path d="M12 12 L4.5 5 L12 2" stroke={color} strokeWidth="1.5" fill={color} fillOpacity="0.15"/>
      <circle cx="12" cy="12" r="3" fill={color}/>
      <path d="M12 0 L10 3 L14 3 Z" fill={color}/>
    </svg>
  );
});

/* ─── ICON CARD ──────────────────────────────────── */
const IconCard = memo(function IconCard({ emoji, icon, value, label, color, badge, onClick, disabled }) {
  return (
    <button onClick={onClick} disabled={disabled} style={{
      flex:1,
      display:'flex',flexDirection:'column',alignItems:'center',gap:4,
      padding:'12px 4px',
      background:'transparent',
      border:'none',
      cursor: disabled ? 'default' : 'pointer',
      position:'relative',
      opacity: disabled ? 0.55 : 1,
    }}>
      {/* icon circle */}
      <div style={{
        width:52,height:52,borderRadius:'50%',
        background:`${color}18`,
        border:`2.5px solid ${color}40`,
        display:'flex',alignItems:'center',justifyContent:'center',
        fontSize:24,
        boxShadow:`0 2px 12px ${color}25`,
        transition:'transform .15s',
      }}>
        {icon || emoji}
      </div>
      {/* badge */}
      {badge && (
        <div style={{
          position:'absolute',top:6,right:'18%',
          width:12,height:12,borderRadius:'50%',
          background:'#EF4444',border:'2px solid #fff',
          boxShadow:'0 1px 4px rgba(239,68,68,.5)'
        }}/>
      )}
      <div style={{fontSize:15,fontWeight:800,color:'#FFFFFF',lineHeight:1}}>{value}</div>
      <div style={{fontSize:10,color:'#C2994B',textTransform:'uppercase',letterSpacing:.5,fontWeight:600}}>{label}</div>
    </button>
  );
});

/* ─── MAIN BAR ───────────────────────────────── */
// Stale-while-revalidate cache: skip the network call if the cached
// payload is younger than CACHE_TTL (shows instantly, refreshes in bg).
const CACHE_TTL_MS = 60 * 1000; // 1 min

export function GamificationBar({ userId, theme, onShowWallet }) {
  const [status, setStatus] = useState(() => {
    // Seed synchronously from cache so the bar paints with real data on
    // the very first render — no skeleton flash when returning to Profile.
    try {
      const raw = sessionStorage.getItem('gamification_status');
      if (!raw) return null;
      const parsed = JSON.parse(raw);
      return parsed?.data || parsed; // support legacy cache shape
    } catch { return null; }
  });
  const [loading, setLoading] = useState(() => {
    try { return !sessionStorage.getItem('gamification_status'); } catch { return true; }
  });
  const [modal, setModal] = useState(null); // 'coins' | 'streak' | 'gift'
  const pri = theme?.pri || '#DA9B2A';

  useEffect(() => {
    // Skip the network fetch entirely if we have a fresh cache.
    try {
      const raw = sessionStorage.getItem('gamification_status');
      if (raw) {
        const parsed = JSON.parse(raw);
        const ts = parsed?.ts || 0;
        if (Date.now() - ts < CACHE_TTL_MS) {
          setLoading(false);
          return; // fresh enough, don't hit the network
        }
      }
    } catch {}
    load();
  }, []);

  const load = async () => {
    if (!status) setLoading(true);
    try {
      const res = await api.request('/gamification/status/');
      setStatus(res);
      // Cache with a timestamp for TTL-based freshness checks.
      sessionStorage.setItem('gamification_status', JSON.stringify({ ts: Date.now(), data: res }));
    } catch { /* silently fail */ }
    setLoading(false);
  };

  const handleLoginBonus = async () => {
    const markClaimed = (s) => s ? {
      ...s,
      login_streak: { ...s.login_streak, bonus_available: false }
    } : s;

    const writeCache = (newStatus) => {
      try {
        sessionStorage.setItem('gamification_status', JSON.stringify({ ts: Date.now(), data: newStatus }));
      } catch {}
    };

    try {
      const res = await api.request('/gamification/login-bonus/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      });
      const newStatus = status ? {
        ...status,
        coins: { ...status.coins, balance: res.new_balance },
        login_streak: { ...status.login_streak, bonus_available: false, current: res.login_streak }
      } : status;
      setStatus(newStatus);
      writeCache(newStatus);
      return res;
    } catch (e) {
      // 400 "already claimed today" — update UI silently so button disappears
      const msg = e?.message || '';
      if (msg.includes('already claimed') || msg.includes('already_claimed')) {
        const newStatus = markClaimed(status);
        setStatus(newStatus);
        writeCache(newStatus);
        return { already_claimed: true };
      }
      console.error('Login bonus claim failed:', e);
      throw e;
    }
  };

  // Spin was removed — only Coins / Streak / Gifts shown.  Keep destructure
  // so an old cache shape doesn't throw on missing keys.
  const { coins={}, login_streak={}, gifts={}, points={} } = status || {};

  if (loading && !status) return (
    <div style={{display:'flex',justifyContent:'space-around',padding:'12px 0',
      background:'#0D0D0D',
      borderTop:`1px solid ${pri}30`,borderBottom:`1px solid ${pri}30`}}>
      {['🪙','🔥','🎁'].map((e,i)=>(
        <div key={i} style={{display:'flex',flexDirection:'column',alignItems:'center',gap:4,padding:'8px 16px'}}>
          <div style={{width:52,height:52,borderRadius:'50%',background:'#1A1A1A',display:'flex',alignItems:'center',justifyContent:'center',fontSize:24,animation:'pulse 1.2s infinite'}}>
            {e}
          </div>
          <div style={{width:24,height:8,background:'#F5F5F4',borderRadius:4,marginTop:2}}/>
          <div style={{width:32,height:6,background:'#F5F5F4',borderRadius:4}}/>
        </div>
      ))}
      <style>{`@keyframes pulse{0%,100%{opacity:1}50%{opacity:.5}}`}</style>
    </div>
  );
  const hasBonus = login_streak?.bonus_available;

  return (
    <>
      {/* Bar — three equal-width cards (Coins · Streak · Gifts).  The
          IconCards use flex:1 so they space evenly regardless of count. */}
      <div style={{
        display:'flex',
        background:'#0D0D0D',
        borderTop:`1px solid ${pri}40`,
        borderBottom:`1px solid ${pri}40`,
        padding:'4px 0',
      }}>
        <IconCard
          emoji="🪙" value={coins?.balance ?? 0} label="Coins" color={pri}
          onClick={()=>setModal('coins')}
        />
        <div style={{width:1,background:'#262626',alignSelf:'stretch',margin:'8px 0'}}/>
        <IconCard
          emoji="🔥" value={`${login_streak?.current ?? 0}d`} label="Streak" color={pri}
          badge={hasBonus}
          onClick={()=>setModal('streak')}
        />
        <div style={{width:1,background:'#262626',alignSelf:'stretch',margin:'8px 0'}}/>
        <IconCard
          emoji="🎁" value={gifts?.received_today ?? 0} label="Gifts" color={pri}
          onClick={()=>setModal('gift')}
        />
      </div>

      {/* Modals — spin modal intentionally removed. */}
      {modal === 'coins'  && <CoinsModal  coins={coins} points={points} onClose={()=>setModal(null)}/>}
      {modal === 'streak' && <StreakModal streak={login_streak} onClaim={handleLoginBonus} onClose={()=>setModal(null)}/>}
      {modal === 'gift'   && <GiftModal  coins={coins} onClose={()=>setModal(null)} onRefresh={load} onShowWallet={onShowWallet}/>}
    </>
  );
}




