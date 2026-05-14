import { useState, useEffect } from 'react';
import { Gift, Coins, Flame, Calendar, RotateCw, Sparkles, CheckCircle, X, RefreshCw, Crown, Star } from 'lucide-react';
import api from '../../api';

// Gamification Dashboard Component
export function GamificationDashboard({ userId, theme, onShowWallet }) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [showSpinModal, setShowSpinModal] = useState(false);
  const [showGiftModal, setShowGiftModal] = useState(false);
  const [spinning, setSpinning] = useState(false);
  const [spinResult, setSpinResult] = useState(null);

  useEffect(() => {
    loadStatus();
  }, []);

  const loadStatus = async () => {
    try {
      setLoading(true);
      setError(null);
      const response = await api.request('/gamification/status/');
      setStatus(response);
    } catch (err) {
      console.error('Failed to load gamification status:', err);
      
      // Better error messages
      if (err.message?.includes('401') || err.message?.includes('Unauthorized')) {
        setError('Please log in to access gamification features');
      } else if (err.message?.includes('403') || err.message?.includes('Forbidden')) {
        setError('Access denied. Please check your account status.');
      } else {
        setError(err.message || 'Failed to load gamification data');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleSpin = async () => {
    if (spinning) return;
    setSpinning(true);
    try {
      const response = await api.request('/gamification/spin/', { method: 'POST' });
      setSpinResult(response);
      setStatus(prev => ({
        ...prev,
        coins: { ...prev.coins, balance: response.new_balance },
        spin: { ...prev.spin, can_spin: false, spins_total: response.spins_total }
      }));
    } catch (error) {
      console.error('Spin failed:', error);
    } finally {
      setSpinning(false);
    }
  };

  const handleClaimLogin = async () => {
    try {
      const response = await api.request('/gamification/login-bonus/', { method: 'POST' });
      setStatus(prev => ({
        ...prev,
        coins: { ...prev.coins, balance: response.new_balance },
        login_streak: { ...prev.login_streak, bonus_available: false, current: response.login_streak }
      }));
    } catch (error) {
      console.error('Claim failed:', error);
    }
  };

  if (loading) return <div style={{ padding: 20, textAlign: 'center', color: theme.sub }}>Loading gamification...</div>;
  
  if (error) return (
    <div style={{ padding: 20, textAlign: 'center' }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>⚠️</div>
      <div style={{ color: theme.red, fontSize: 14, marginBottom: 12 }}>
        {error}
      </div>
      <div style={{ fontSize: 12, color: theme.sub, marginBottom: 12 }}>
        Make sure you're logged in and the gamification system is active
      </div>
      <button 
        onClick={loadStatus}
        style={{
          padding: '10px 20px',
          borderRadius: 8,
          border: 'none',
          background: theme.pri,
          color: 'white',
          cursor: 'pointer',
          fontSize: 14
        }}
      >
        Retry
      </button>
    </div>
  );
  
  if (!status) return (
    <div style={{ padding: 20, textAlign: 'center', color: theme.sub }}>
      <div style={{ fontSize: 32, marginBottom: 8 }}>🎮</div>
      <div>Gamification data not available</div>
    </div>
  );

  return (
    <div style={{ padding: '20px 0' }}>
      {/* Coins & Streak Header */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
        gap: 12,
        marginBottom: 24
      }}>
        <StatCard
          icon={<Coins size={24} color={theme.pri} />}
          value={status.coins.balance}
          label="Coins"
          theme={theme}
          accent={theme.pri}
        />
        <StatCard
          icon={<Flame size={24} color="#EF4444" />}
          value={status.login_streak.current}
          label="Day Streak"
          theme={theme}
          accent="#EF4444"
        />
        <StatCard
          icon={<Calendar size={24} color="#3B82F6" />}
          value={status.login_streak.longest}
          label="Best Streak"
          theme={theme}
          accent="#3B82F6"
        />
        <StatCard
          icon={<Gift size={24} color="#8B5CF6" />}
          value={status.gifts.received_today}
          label="Gifts Today"
          theme={theme}
          accent="#8B5CF6"
        />
      </div>

      {/* Action Buttons */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 16 }}>
        {/* Daily Spin */}
        <ActionCard
          title="Daily Spin"
          subtitle={status.spin.can_spin ? "Spin for free coins!" : "Come back tomorrow"}
          icon={<RefreshCw size={32} color={status.spin.can_spin ? theme.pri : theme.sub} />}
          disabled={!status.spin.can_spin}
          onClick={() => setShowSpinModal(true)}
          theme={theme}
          highlight={status.spin.can_spin}
        />

        {/* Login Bonus */}
        <ActionCard
          title="Login Bonus"
          subtitle={status.login_streak.bonus_available 
            ? `Day ${status.login_streak.current + 1}: +${status.login_streak.next_bonus.coins} coins`
            : "Already claimed today"
          }
          icon={<CheckCircle size={32} color={status.login_streak.bonus_available ? "#10B981" : theme.sub} />}
          disabled={!status.login_streak.bonus_available}
          onClick={handleClaimLogin}
          theme={theme}
          highlight={status.login_streak.bonus_available}
        />

        {/* Send Gift */}
        <ActionCard
          title="Send Gift"
          subtitle={`${10 - status.gifts.sent_today} gifts remaining today`}
          icon={<Gift size={32} color="#8B5CF6" />}
          disabled={status.gifts.sent_today >= 10}
          onClick={() => setShowGiftModal(true)}
          theme={theme}
        />
      </div>

      {/* Spin Modal */}
      {showSpinModal && (
        <SpinModal
          theme={theme}
          onClose={() => {
            setShowSpinModal(false);
            setSpinResult(null);
          }}
          onSpin={handleSpin}
          spinning={spinning}
          result={spinResult}
          canSpin={status.spin.can_spin}
          rewards={status.spin.rewards_preview}
        />
      )}

      {/* Gift Modal */}
      {showGiftModal && (
        <GiftModal
          theme={theme}
          onClose={() => setShowGiftModal(false)}
          onSuccess={loadStatus}
          coins={status.coins.balance}
          onShowWallet={onShowWallet}
        />
      )}
    </div>
  );
}

function StatCard({ icon, value, label, theme, accent }) {
  return (
    <div style={{
      background: theme.card,
      borderRadius: 12,
      padding: 16,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      gap: 8,
      border: `1px solid ${theme.border}`,
      minHeight: 100
    }}>
      <div style={{
        width: 48,
        height: 48,
        borderRadius: 12,
        background: accent + '15',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0
      }}>
        {icon}
      </div>
      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 2 }}>{value}</div>
        <div style={{ fontSize: 13, color: theme.sub, fontWeight: 500 }}>{label}</div>
      </div>
    </div>
  );
}

function ActionCard({ title, subtitle, icon, disabled, onClick, theme, highlight }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        background: theme.card,
        border: `2px solid ${disabled ? theme.border : highlight ? theme.pri : theme.border}`,
        borderRadius: 16,
        padding: 20,
        display: 'flex',
        alignItems: 'center',
        gap: 16,
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.6 : 1,
        width: '100%',
        textAlign: 'left',
        transition: 'all 0.2s',
        boxShadow: highlight ? `0 4px 12px ${theme.pri}30` : 'none'
      }}
    >
      <div style={{
        width: 56,
        height: 56,
        borderRadius: 14,
        background: highlight ? theme.pri + '15' : theme.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        flexShrink: 0
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 16, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
          {title}
        </div>
        <div style={{ fontSize: 13, color: disabled ? theme.sub : highlight ? theme.pri : theme.sub }}>
          {subtitle}
        </div>
      </div>
    </button>
  );
}

function SpinModal({ theme, onClose, onSpin, spinning, result, canSpin, rewards }) {
  const [rotation, setRotation] = useState(0);
  const [nameRotation, setNameRotation] = useState(0);

  const handleSpinClick = () => {
    if (!canSpin || spinning) return;
    
    // Real random rotation: 5-10 full rotations plus random position
    const baseRotations = 5 + Math.floor(Math.random() * 6); // 5-10 rotations
    const randomPosition = Math.random() * 360; // Random final position
    const totalRotation = baseRotations * 360 + randomPosition;
    
    setRotation(prev => prev + totalRotation);
    setNameRotation(prev => prev + totalRotation);
    onSpin();
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.8)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: 20
    }} onClick={onClose}>
      <div style={{
        background: theme.card,
        borderRadius: 20,
        padding: 28,
        maxWidth: 420,
        width: '100%',
        textAlign: 'center',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
      }} onClick={e => e.stopPropagation()}>
        <div style={{ marginBottom: 20 }}>
          <h2 style={{ margin: '0 0 6px 0', color: '#8fc441', fontSize: 22, fontWeight: 700 }}>
            Daily Spin 🎰
          </h2>
          <p style={{ margin: 0, color: theme.sub, fontSize: 13 }}>
            {result ? 'Congratulations!' : 'Spin the wheel to win coins!'}
          </p>
        </div>

        {!result ? (
          <>
            {/* Wheel Visual */}
            <div style={{
              width: 260,
              height: 260,
              margin: '0 auto 20',
              position: 'relative'
            }}>
              <div style={{
                width: '100%',
                height: '100%',
                borderRadius: '50%',
                background: `conic-gradient(
                  #8fc441 0deg 60deg,
                  #3B82F6 60deg 120deg,
                  #10B981 120deg 180deg,
                  #F59E0B 180deg 240deg,
                  #EF4444 240deg 300deg,
                  #8B5CF6 300deg 360deg
                )`,
                transform: `rotate(${rotation}deg)`,
                transition: spinning ? 'transform 3s cubic-bezier(0.23, 1, 0.32, 1)' : 'none',
                boxShadow: '0 8px 32px rgba(0,0,0,0.2)'
              }} />
              {/* Pointer */}
              <div style={{
                position: 'absolute',
                top: -10,
                left: '50%',
                transform: 'translateX(-50%)',
                width: 0,
                height: 0,
                borderLeft: '15px solid transparent',
                borderRight: '15px solid transparent',
                borderTop: '30px solid #8fc441'
              }} />
              {/* Center with spinning icon */}
              <div style={{
                position: 'absolute',
                top: '50%',
                left: '50%',
                transform: 'translate(-50%, -50%)',
                width: 56,
                height: 56,
                borderRadius: '50%',
                background: theme.card,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 16px rgba(0,0,0,0.15)'
              }}>
                <RefreshCw 
                  size={26} 
                  color="#8fc441"
                  style={{
                    transform: `rotate(${rotation}deg)`,
                    transition: spinning ? 'transform 3s cubic-bezier(0.23, 1, 0.32, 1)' : 'none'
                  }}
                />
              </div>
            </div>

            {/* Rewards Preview */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(3, 1fr)',
              gap: 8,
              marginBottom: 20
            }}>
              {rewards?.slice(0, 6).map((reward, idx) => (
                <div key={idx} style={{
                  background: theme.bg,
                  borderRadius: 10,
                  padding: 10,
                  fontSize: 12,
                  color: theme.sub,
                  border: '1px solid ' + theme.border
                }}>
                  <div style={{ fontSize: 22, marginBottom: 6 }}>{reward.emoji}</div>
                  {reward.label}
                </div>
              ))}
            </div>

            <button
              onClick={handleSpinClick}
              disabled={!canSpin || spinning}
              style={{
                width: '100%',
                padding: 14,
                borderRadius: 12,
                border: 'none',
                background: canSpin ? '#8fc441' : theme.border,
                color: canSpin ? '#000' : theme.sub,
                fontSize: 16,
                fontWeight: 700,
                cursor: canSpin ? 'pointer' : 'not-allowed',
                boxShadow: canSpin ? '0 4px 16px rgba(249, 224, 139, 0.4)' : 'none'
              }}
            >
              {spinning ? 'Spinning...' : canSpin ? 'SPIN!' : 'Already Spun Today'}
            </button>
          </>
        ) : (
          <div style={{
            padding: '36px 20px',
            background: 'linear-gradient(135deg, rgba(249, 224, 139, 0.15), rgba(249, 224, 139, 0.05))',
            borderRadius: 16,
            marginBottom: 20,
            border: '1px solid rgba(249, 224, 139, 0.2)'
          }}>
            <div style={{ fontSize: 56, marginBottom: 14 }}>
              {result.reward.emoji}
            </div>
            <div 
              style={{ 
                fontSize: 26, 
                fontWeight: 700, 
                color: '#8fc441', 
                marginBottom: 6,
                transform: `rotate(${nameRotation}deg)`,
                transition: 'transform 3s cubic-bezier(0.23, 1, 0.32, 1)',
                display: 'inline-block'
              }}
            >
              {result.reward.label}
            </div>
            <div style={{ fontSize: 15, color: theme.txt, marginBottom: 14 }}>
              +{result.coins_earned} coins added!
            </div>
            <div style={{ fontSize: 13, color: theme.sub }}>
              New balance: <strong style={{ color: '#8fc441' }}>{result.new_balance}</strong> coins
            </div>
          </div>
        )}

        {result && (
          <>
            {/* Upsell Section */}
            <div style={{
              background: 'linear-gradient(135deg, rgba(249, 224, 139, 0.1), rgba(249, 224, 139, 0.05))',
              borderRadius: 12,
              padding: 16,
              marginBottom: 20,
              textAlign: 'left',
              border: '1px solid rgba(249, 224, 139, 0.15)'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                <Crown size={18} color="#8fc441" />
                <h4 style={{ margin: 0, fontSize: 15, color: theme.txt, fontWeight: 700 }}>
                  Want More Spins?
                </h4>
              </div>
              <p style={{ margin: '0 0 12px 0', fontSize: 12, color: theme.sub, lineHeight: 1.4 }}>
                Get unlimited spins and bonus rewards with our premium features!
              </p>
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  style={{
                    flex: 1,
                    padding: 8,
                    borderRadius: 8,
                    border: '1px solid #8fc441',
                    background: theme.card,
                    color: '#8fc441',
                    fontSize: 12,
                    fontWeight: 600,
                    cursor: 'pointer'
                  }}
                  onClick={() => {
                    window.location.href = '/coins';
                  }}
                >
                  <Coins size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                  Buy Coins
                </button>
                <button
                  style={{
                    flex: 1,
                    padding: 8,
                    borderRadius: 8,
                    border: 'none',
                    background: '#8fc441',
                    color: '#000',
                    fontSize: 12,
                    fontWeight: 700,
                    cursor: 'pointer'
                  }}
                  onClick={() => {
                    window.location.href = '/subscription';
                  }}
                >
                  <Star size={12} style={{ marginRight: 4, verticalAlign: 'middle' }} />
                  Go Premium
                </button>
              </div>
            </div>
            
            <button
              onClick={onClose}
              style={{
                width: '100%',
                padding: 12,
                borderRadius: 10,
                border: '1px solid ' + theme.border,
                background: theme.card,
                color: theme.txt,
                fontSize: 15,
                fontWeight: 600,
                cursor: 'pointer'
              }}
            >
              Awesome!
            </button>
          </>
        )}
      </div>
    </div>
  );
}

function GiftModal({ theme, onClose, onSuccess, coins, onShowWallet }) {
  const [recipient, setRecipient] = useState('');
  const [amount, setAmount] = useState(10);
  const [message, setMessage] = useState('');
  const [sending, setSending] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');

  const handleSend = async () => {
    if (!recipient || amount < 1 || amount > coins) {
      setError('Invalid recipient or amount');
      return;
    }
    
    setSending(true);
    setError('');
    
    try {
      const response = await api.request('/gamification/gift/', {
        method: 'POST',
        body: JSON.stringify({
          recipient_username: recipient,
          amount: parseInt(amount),
          message: message
        })
      });
      setResult(response);
      onSuccess();
    } catch (err) {
      setError(err.message || 'Failed to send gift');
    } finally {
      setSending(false);
    }
  };

  return (
    <div style={{
      position: 'fixed',
      top: 0,
      left: 0,
      right: 0,
      bottom: 0,
      background: 'rgba(0,0,0,0.8)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'center',
      zIndex: 1000,
      padding: 20
    }} onClick={onClose}>
      <div style={{
        background: theme.card,
        borderRadius: 20,
        padding: 24,
        maxWidth: 400,
        width: '100%',
        boxShadow: '0 20px 60px rgba(0,0,0,0.3)'
      }} onClick={e => e.stopPropagation()}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 20 }}>
          <h2 style={{ margin: 0, color: '#8fc441', fontSize: 18, fontWeight: 700 }}>Send Coin Gift 🎁</h2>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer' }}>
            <X size={20} color={theme.sub} />
          </button>
        </div>

        {result ? (
          <div style={{ textAlign: 'center', padding: '24px 0' }}>
            <div style={{ fontSize: 48, marginBottom: 16 }}>🎉</div>
            <div style={{ fontSize: 16, color: theme.txt, marginBottom: 6, fontWeight: 600 }}>
              Gift sent to {result.recipient.username}!
            </div>
            <div style={{ color: '#8fc441', fontSize: 18, fontWeight: 700 }}>{result.amount} coins</div>
          </div>
        ) : (
          <>
            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>
                Your Balance
              </label>
              <div style={{ fontSize: 22, fontWeight: 700, color: '#8fc441' }}>
                {coins} coins
              </div>
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>
                Recipient Username
              </label>
              <input
                type="text"
                value={recipient}
                onChange={e => setRecipient(e.target.value)}
                placeholder="Enter username (e.g., johndoe)"
                style={{
                  width: '100%',
                  padding: 12,
                  border: '1px solid ' + theme.border,
                  borderRadius: 10,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt
                }}
              />
            </div>

            <div style={{ marginBottom: 16 }}>
              <label style={{ display: 'block', fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>
                Amount (1-100)
              </label>
              <input
                type="number"
                value={amount}
                onChange={e => setAmount(parseInt(e.target.value) || 0)}
                min={1}
                max={100}
                style={{
                  width: '100%',
                  padding: 12,
                  border: '1px solid ' + theme.border,
                  borderRadius: 10,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt
                }}
              />
            </div>

            <div style={{ marginBottom: 20 }}>
              <label style={{ display: 'block', fontSize: 12, color: theme.sub, marginBottom: 6, fontWeight: 600 }}>
                Message (optional)
              </label>
              <input
                type="text"
                value={message}
                onChange={e => setMessage(e.target.value)}
                placeholder="Add a friendly message..."
                style={{
                  width: '100%',
                  padding: 12,
                  border: '1px solid ' + theme.border,
                  borderRadius: 10,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt
                }}
              />
            </div>

            {error && (
              <div style={{ color: '#EF4444', fontSize: 12, marginBottom: 16 }}>
                {error}
              </div>
            )}

            <button
              onClick={handleSend}
              disabled={sending || !recipient || amount < 1 || amount > coins}
              style={{
                width: '100%',
                padding: 14,
                borderRadius: 10,
                border: 'none',
                background: '#8fc441',
                color: '#000',
                fontSize: 15,
                fontWeight: 700,
                cursor: sending ? 'not-allowed' : 'pointer',
                opacity: sending ? 0.7 : 1,
                boxShadow: '0 4px 16px rgba(249, 224, 139, 0.4)'
              }}
            >
              {sending ? 'Sending...' : `Send ${amount} Coins`}
            </button>
          </>
        )}
      </div>
    </div>
  );
}




