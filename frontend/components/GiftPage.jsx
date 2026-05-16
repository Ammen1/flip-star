import { useState, useEffect } from 'react';
import { Gift, Send, X } from 'lucide-react';
import api from '../api';
import { useTheme } from '../contexts/ThemeContext';

const CATEGORY_ICONS = {
  flowers: '🌹',
  hearts: '❤️',
  gems: '💎',
  special: '⭐',
  animals: '🐻',
  vehicles: '🚗',
};

const RARITY_COLORS = {
  common: '#A0A0A0',
  rare: '#3B82F6',
  epic: '#8B5CF6',
  legendary: '#F59E0B',
};

export default function GiftPage({ username, reelId, onClose, onShowWallet }) {
  console.log('[GiftPage] Received reelId:', reelId);
  const { colors: T } = useTheme();
  const [gifts, setGifts] = useState([
    { id: 1, name: 'Rose', description: 'A beautiful red rose', coin_value: 10, rarity: 'common', category: 'flowers' },
    { id: 2, name: 'Heart', description: 'A heart symbol', coin_value: 20, rarity: 'common', category: 'hearts' },
    { id: 3, name: 'Medal', description: 'A gold medal', coin_value: 50, rarity: 'rare', category: 'special' },
    { id: 4, name: 'Diamond', description: 'A sparkling diamond', coin_value: 100, rarity: 'epic', category: 'gems' },
    { id: 5, name: 'Teddy Bear', description: 'A cute teddy bear', coin_value: 30, rarity: 'common', category: 'animals' },
  ]);
  const [selectedGift, setSelectedGift] = useState(null);
  const [quantity, setQuantity] = useState(1);
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const [success, setSuccess] = useState(false);
  const [coinBalance, setCoinBalance] = useState(0);
  const [showRechargeDialog, setShowRechargeDialog] = useState(false);
  const [rechargeError, setRechargeError] = useState(null);
  const [showtelebirrPayment, setShowtelebirrPayment] = useState(false);
  const [telebirrPaymentUrl, settelebirrPaymentUrl] = useState(null);
  const [walletConfig, setWalletConfig] = useState(null);

  useEffect(() => {
    loadGifts();
    loadCoinBalance();
    loadWalletConfig();
  }, []);

  const loadGifts = async () => {
    try {
      const response = await api.request('/gifts/');
      const giftsData = response.results || response;
      console.log('Loaded gifts:', giftsData);
      setGifts(giftsData);
    } catch (error) {
      console.error('Error loading gifts:', error);
      // Keep using default gifts if API fails
    }
  };

  const loadCoinBalance = async () => {
    try {
      const response = await api.request('/wallet/');
      setCoinBalance(response.balance?.purchased || 0);
    } catch (error) {
      console.error('Error loading coin balance:', error);
    }
  };

  const loadWalletConfig = async () => {
    try {
      const response = await api.request('/wallet/config/');
      setWalletConfig(response);
    } catch (error) {
      console.error('Error loading wallet config:', error);
    }
  };

  const categories = ['all', ...new Set(gifts.map(g => g.category))];
  
  const filteredGifts = selectedCategory === 'all' 
    ? gifts 
    : gifts.filter(g => g.category === selectedCategory);

  const handleSendGift = async () => {
    if (!username || !selectedGift) return;

    const totalCost = selectedGift.coin_value * quantity;
    
    // Validate against wallet config limits
    if (walletConfig?.gifting) {
      const pointsCost = Math.floor(totalCost / (walletConfig.coins_to_points_conversion || 1));
      
      // Check minimum points per transaction
      if (pointsCost < walletConfig.gifting.min_points_per_transaction) {
        alert(`Minimum ${walletConfig.gifting.min_points_per_transaction} points required per transaction`);
        return;
      }
      
      // Check maximum points per transaction
      if (pointsCost > walletConfig.gifting.max_points_per_transaction) {
        alert(`Maximum ${walletConfig.gifting.max_points_per_transaction} points allowed per transaction`);
        return;
      }
    }
    
    if (totalCost > coinBalance) {
      // Show recharge dialog with automatic telebirr payment option
      setRechargeError({
        needs_recharge: true,
        required_coins: totalCost,
        current_purchased_coins: coinBalance,
        current_earned_coins: 0,
      });
      setShowRechargeDialog(true);
      return;
    }

    setLoading(true);
    try {
      console.log('[GiftPage] Sending gift with reelId:', reelId);
      await api.request('/gifts/send/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          gift_id: selectedGift.id,
          recipient_username: username,
          quantity: quantity,
          message: message,
          reel_id: reelId,
        }),
      });
      setSuccess(true);
      setTimeout(() => {
        setSuccess(false);
        onClose?.();
      }, 2000);
    } catch (err) {
      console.error('Gift send error:', err);
      const errorData = err.response?.data || err;

      if (errorData.needs_recharge) {
        setRechargeError(errorData);
        setShowRechargeDialog(true);
      } else {
        alert(errorData.error || 'Failed to send gift');
      }
    } finally {
      setLoading(false);
    }
  };

  const handletelebirrPayment = async (packageId, phoneNumber) => {
    try {
      const response = await api.request('/wallet/telebirr/initiate/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          package_id: packageId,
          phone_number: phoneNumber,
        }),
      });

      if (response.success && response.payment_url) {
        // Redirect to telebirr payment page
        settelebirrPaymentUrl(response.payment_url);
        setShowtelebirrPayment(true);
        window.open(response.payment_url, '_blank');
      } else {
        alert(response.error || 'Payment initiation failed');
      }
    } catch (error) {
      console.error('telebirr payment error:', error);
      alert('Payment initiation failed. Please try again.');
    }
  };

  // surface = one step above the modal card so inset elements are always visible
  const card = T?.cardBg || '#1A1A1A';
  const surface = T?.border || '#333';
  const txt = T?.txt || '#fff';
  const sub = T?.sub || '#999';
  const pri = T?.pri || '#8fc441';
  const border = T?.border || '#333';

  const inputStyle = {
    width: '100%',
    padding: '12px 14px',
    borderRadius: 10,
    border: `1.5px solid ${border}`,
    background: surface,
    color: txt,
    fontSize: 14,
    outline: 'none',
    boxSizing: 'border-box',
  };

  const secondaryBtn = {
    flex: 1,
    padding: '12px',
    borderRadius: 10,
    border: `1.5px solid ${border}`,
    background: surface,
    color: txt,
    fontSize: 14,
    fontWeight: 600,
    cursor: 'pointer',
  };

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.72)', zIndex: 10000, display: 'flex', alignItems: 'flex-end', justifyContent: 'center', padding: 0 }} onClick={onClose}>
      <div onClick={e => e.stopPropagation()} style={{ background: card, borderTopLeftRadius: 20, borderTopRightRadius: 20, padding: 16, maxWidth: 480, width: '100%', maxHeight: '85vh', overflowY: 'auto', boxShadow: '0 -8px 32px rgba(0,0,0,0.6)', border: `1px solid ${border}` }}>
        {/* Compact Header: Title + Recipient + Balance */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, minWidth: 0, flex: 1 }}>
            <Gift size={18} color={pri} />
            <div style={{ fontSize: 15, fontWeight: 700, color: txt, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              Gift to <span style={{ color: pri }}>@{username}</span>
            </div>
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{ fontSize: 13, fontWeight: 700, color: pri, whiteSpace: 'nowrap' }}>🪙 {coinBalance}</div>
            <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4, color: sub, display: 'flex' }}>
              <X size={18} />
            </button>
          </div>
        </div>

        {success ? (
          <div style={{ textAlign: 'center', padding: '32px 16px' }}>
            <div style={{ fontSize: 48, marginBottom: 12 }}>🎁</div>
            <div style={{ fontSize: 16, fontWeight: 700, color: txt, marginBottom: 4 }}>Gift Sent!</div>
            <div style={{ fontSize: 13, color: sub }}>Your gift has been sent successfully</div>
          </div>
        ) : (
          <>
            {/* Category Filter - compact horizontal scroll */}
            <div style={{ display: 'flex', gap: 6, overflowX: 'auto', marginBottom: 10, paddingBottom: 2, scrollbarWidth: 'none' }}>
              {categories.map(cat => (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  style={{
                    padding: '5px 10px',
                    borderRadius: 14,
                    border: `1px solid ${selectedCategory === cat ? pri : border}`,
                    background: selectedCategory === cat ? `${pri}22` : surface,
                    color: selectedCategory === cat ? pri : txt,
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    whiteSpace: 'nowrap',
                    flexShrink: 0,
                  }}
                >
                  {cat !== 'all' && CATEGORY_ICONS[cat]} {cat.charAt(0).toUpperCase() + cat.slice(1)}
                </button>
              ))}
            </div>

            {/* Gift Selection - compact 4-col grid */}
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 6, marginBottom: 12 }}>
              {filteredGifts.map(gift => (
                <button
                  key={gift.id}
                  onClick={() => { setSelectedGift(gift); setQuantity(1); }}
                  style={{
                    padding: '8px 4px',
                    borderRadius: 10,
                    border: `1.5px solid ${selectedGift?.id === gift.id ? pri : border}`,
                    background: selectedGift?.id === gift.id ? `${pri}22` : surface,
                    cursor: 'pointer',
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    gap: 2,
                  }}
                >
                  <div style={{ fontSize: 24, height: 32, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    {gift.image_url ? (
                      <img src={gift.image_url} alt={gift.name} style={{ width: 28, height: 28, objectFit: 'contain' }} />
                    ) : (
                      CATEGORY_ICONS[gift.category] || '🎁'
                    )}
                  </div>
                  <div style={{ fontSize: 11, fontWeight: 700, color: pri }}>{gift.coin_value}🪙</div>
                </button>
              ))}
            </div>

            {/* Quantity + Message inline row when gift selected */}
            {selectedGift && (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 10, marginBottom: 10, padding: '8px 12px', background: surface, borderRadius: 10, border: `1px solid ${border}` }}>
                <div style={{ fontSize: 13, color: txt, fontWeight: 600 }}>{selectedGift.name}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  <button onClick={() => setQuantity(Math.max(1, quantity - 1))} style={{ width: 28, height: 28, borderRadius: 6, border: `1px solid ${border}`, background: card, color: txt, fontSize: 16, fontWeight: 700, cursor: 'pointer' }}>−</button>
                  <div style={{ minWidth: 20, textAlign: 'center', fontSize: 14, fontWeight: 700, color: txt }}>{quantity}</div>
                  <button 
                    onClick={() => {
                      const newQuantity = quantity + 1;
                      const totalCost = selectedGift.coin_value * newQuantity;
                      const pointsCost = Math.floor(totalCost / (walletConfig?.coins_to_points_conversion || 1));
                      const maxPoints = walletConfig?.gifting?.max_points_per_transaction || 5000;
                      if (pointsCost <= maxPoints) {
                        setQuantity(newQuantity);
                      } else {
                        alert(`Maximum ${maxPoints} points allowed per transaction`);
                      }
                    }}
                    style={{ width: 28, height: 28, borderRadius: 6, border: `1px solid ${border}`, background: card, color: txt, fontSize: 16, fontWeight: 700, cursor: 'pointer' }}
                  >+</button>
                </div>
              </div>
            )}

            {/* Message - 1 row */}
            <input
              type="text"
              value={message}
              onChange={(e) => setMessage(e.target.value)}
              placeholder="Add a message (optional)..."
              style={{ ...inputStyle, padding: '10px 12px', fontSize: 13, marginBottom: 10 }}
            />

            {/* Transfer Rules Info */}
            {walletConfig?.gifting && (
              <div style={{ fontSize: 11, color: sub, marginBottom: 10, padding: '8px 12px', background: `${border}22`, borderRadius: 8, border: `1px solid ${border}` }}>
                <div style={{ fontWeight: 600, marginBottom: 4, color: txt }}>Transfer Rules:</div>
                <div>• Min: {walletConfig.gifting.min_points_per_transaction} pts per transaction</div>
                <div>• Max: {walletConfig.gifting.max_points_per_transaction} pts per transaction</div>
                <div>• Max to one creator: {walletConfig.gifting.max_points_to_recipient_per_day} pts/day</div>
                <div>• Max total sent: {walletConfig.gifting.max_total_points_sent_per_day} pts/day</div>
              </div>
            )}

            {/* Send Button */}
            <button
              onClick={handleSendGift}
              disabled={loading || !selectedGift}
              style={{
                width: '100%',
                padding: '12px',
                borderRadius: 10,
                border: 'none',
                background: loading || !selectedGift ? border : pri,
                color: loading || !selectedGift ? sub : '#000',
                fontSize: 14,
                fontWeight: 700,
                cursor: loading || !selectedGift ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 6,
                boxShadow: loading || !selectedGift ? 'none' : `0 4px 16px ${pri}40`,
              }}
            >
              {loading ? 'Sending...' : (
                <>
                  <Send size={16} />
                  Send {selectedGift ? `· 🪙 ${selectedGift.coin_value * quantity}` : 'Gift'}
                </>
              )}
            </button>
          </>
        )}

        {/* Recharge Dialog */}
        {showRechargeDialog && rechargeError && (
          <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.82)', zIndex: 20000, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 16 }}>
            <div style={{ background: card, borderRadius: 16, padding: 18, maxWidth: 380, width: '100%', boxShadow: '0 24px 64px rgba(0,0,0,0.7)', border: `1px solid ${border}` }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12 }}>
                <div style={{ fontSize: 28 }}>💰</div>
                <div>
                  <div style={{ fontSize: 15, fontWeight: 700, color: txt }}>Insufficient Coins</div>
                  <div style={{ fontSize: 12, color: sub }}>Need 🪙 {rechargeError.required_coins} · Have 🪙 {rechargeError.current_purchased_coins}</div>
                </div>
              </div>

              <input
                type="tel"
                placeholder="Phone for telebirr (+251 9xx xxx xxx)"
                id="telebirr-phone"
                style={{ ...inputStyle, padding: '10px 12px', fontSize: 13, marginBottom: 10 }}
              />

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 12 }}>
                {[
                  { coins: 100, etb: 10, pkgId: 1 },
                  { coins: 500, etb: 50, pkgId: 2 },
                ].map(pkg => (
                  <button
                    key={pkg.pkgId}
                    onClick={() => {
                      const phone = document.getElementById('telebirr-phone')?.value;
                      if (!phone) { alert('Please enter your phone number'); return; }
                      handletelebirrPayment(pkg.pkgId, phone);
                    }}
                    style={{
                      padding: '10px 8px',
                      borderRadius: 8,
                      border: `1.5px solid ${border}`,
                      background: surface,
                      color: txt,
                      fontSize: 13,
                      fontWeight: 700,
                      cursor: 'pointer',
                      textAlign: 'center',
                    }}
                  >
                    🪙 {pkg.coins} <span style={{ fontSize: 11, color: sub, fontWeight: 500 }}>· {pkg.etb} ETB</span>
                  </button>
                ))}
              </div>

              <div style={{ display: 'flex', gap: 8 }}>
                <button onClick={() => setShowRechargeDialog(false)} style={{ ...secondaryBtn, padding: '10px', fontSize: 13 }}>
                  Cancel
                </button>
                <button
                  onClick={() => { setShowRechargeDialog(false); onShowWallet?.(); }}
                  style={{ flex: 1, padding: '10px', borderRadius: 10, border: 'none', background: pri, color: '#000', fontSize: 13, fontWeight: 700, cursor: 'pointer' }}
                >
                  Open Wallet
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}




