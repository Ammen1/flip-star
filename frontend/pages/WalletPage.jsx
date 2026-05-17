import { useState, useEffect } from 'react';
import {
  Wallet, Coins, ArrowDownToLine, ArrowUpFromLine, Gift,
  TrendingUp, TrendingDown, Calendar, Clock, CheckCircle2,
  XCircle, AlertCircle, Loader, ChevronLeft, RefreshCw,
  CreditCard, Smartphone, Building2, ChevronRight, X, Repeat,
} from 'lucide-react';
import api from '../api';

/**
 * Full user wallet with:
 * - Earned vs Purchased balance display
 * - Transaction history (paginated)
 * - Coin → Birr withdrawal flow
 * - Top-up via telebirr (placeholder for payment flow)
 *
 * All amounts shown in coins; conversion to ETB displayed where relevant.
 * No dollar signs anywhere — Birr only.
 */
const CACHE_KEY = 'wallet_cache';
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

function readCache() {
  try {
    const raw = sessionStorage.getItem(CACHE_KEY);
    if (!raw) return null;
    const { ts, summary, config } = JSON.parse(raw);
    if (Date.now() - ts > CACHE_TTL) return null;
    return { summary, config };
  } catch { return null; }
}

function writeCache(summary, config) {
  try {
    sessionStorage.setItem(CACHE_KEY, JSON.stringify({ ts: Date.now(), summary, config }));
  } catch {}
}

export function WalletPage({ theme, onBack, showTopUpOnMount, onShowCoinPurchase }) {
  const T = theme || defaultTheme();
  const [isDesktop, setIsDesktop] = useState(window.innerWidth > 1024);
  const [activeTab, setActiveTab] = useState('overview'); // overview | transactions | withdrawals

  useEffect(() => {
    const handleResize = () => setIsDesktop(window.innerWidth > 1024);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Seed from cache instantly — no loading flash on revisit
  const cached = readCache();
  const [summary, setSummary] = useState(cached?.summary || null);
  const [config, setConfig] = useState(cached?.config || null);
  const [transactions, setTransactions] = useState([]);
  const [withdrawals, setWithdrawals] = useState([]);
  const [loading, setLoading] = useState(!cached); // skip loading if cache hit
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');

  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [showTopUpModal, setShowTopUpModal] = useState(showTopUpOnMount || false);
  const [showReinvestModal, setShowReinvestModal] = useState(false);

  useEffect(() => {
    if (cached) {
      // Cache hit: paint immediately, refresh silently in background
      loadAll(true);
    } else {
      loadAll(false);
    }
  }, []);

  async function loadAll(silent = false) {
    try {
      if (!silent) setLoading(true);
      else setRefreshing(true);
      setError('');
      const [s, c] = await Promise.all([
        api.request('/wallet/'),
        api.request('/wallet/config/'),
      ]);
      setSummary(s);
      setConfig(c);
      writeCache(s, c);
    } catch (err) {
      console.error('Wallet load failed:', err);
      if (!silent) setError(err.message || 'Failed to load wallet');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }

  async function loadTransactions() {
    try {
      const data = await api.request('/wallet/transactions/?page_size=50');
      setTransactions(data.results || []);
    } catch (err) {
      console.error('Transactions load failed:', err);
    }
  }

  async function loadWithdrawals() {
    try {
      const data = await api.request('/wallet/withdrawals/');
      setWithdrawals(data.results || []);
    } catch (err) {
      console.error('Withdrawals load failed:', err);
    }
  }

  function handleTabChange(tab) {
    setActiveTab(tab);
    if (tab === 'transactions' && transactions.length === 0) loadTransactions();
    if (tab === 'withdrawals' && withdrawals.length === 0) loadWithdrawals();
  }

  if (loading) {
    return (
      <div style={{ ...styles.container, background: T.bg }}>
        {/* Header with back button always available */}
        <div style={{ ...styles.header, background: T.card, borderColor: T.border }}>
          {onBack && (
            <button onClick={onBack} style={styles.backBtn}>
              <ChevronLeft size={24} color={T.txt} />
            </button>
          )}
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
            <Wallet size={22} color={T.pri} />
            <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: T.txt }}>My Wallet</h2>
          </div>
        </div>
        {/* Skeleton cards */}
        <div style={{ padding: 16 }}>
          {[1, 2, 3].map(i => (
            <div key={i} style={{ height: 80, borderRadius: 14, background: T.card, marginBottom: 12,
              animation: 'pulse 1.5s ease-in-out infinite alternate' }} />
          ))}
          <style>{`@keyframes pulse{from{opacity:1}to{opacity:0.5}}`}</style>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div style={{ ...styles.container, background: T.bg, padding: 20 }}>
        <div style={{ ...styles.header, background: T.card, borderColor: T.border }}>
          {onBack && (
            <button onClick={onBack} style={styles.backBtn}>
              <ChevronLeft size={24} color={T.txt} />
            </button>
          )}
        </div>
        <div style={{ textAlign: 'center', padding: 40 }}>
          <AlertCircle size={40} color={T.red || '#EF4444'} />
          <p style={{ color: T.txt, marginTop: 16 }}>{error}</p>
          <button onClick={() => loadAll(false)} style={{ ...btnPrimary(T), marginTop: 16 }}>
            <RefreshCw size={16} /> Retry
          </button>
        </div>
      </div>
    );
  }

  const balance = summary?.balance || { total: 0, earned: 0, purchased: 0 };
  const points = summary?.points || { current: 0, earned_total: 0, withdrawn_total: 0 };
  const totals = summary?.totals || {};
  const withdrawal = summary?.withdrawal || {};

  return (
    <div style={{ ...styles.container, background: T.bg, position: 'fixed', inset: 0, zIndex: 50, overflowY: 'auto', left: isDesktop ? 260 : 0 }}>
      {/* Header */}
      <div style={{ ...styles.header, background: T.card, borderColor: T.border }}>
        {onBack && (
          <button onClick={onBack} style={styles.backBtn}>
            <ChevronLeft size={24} color={T.txt} />
          </button>
        )}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flex: 1 }}>
          <Wallet size={22} color={T.pri} />
          <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: T.txt }}>
            My Wallet
          </h2>
        </div>
        <button onClick={() => loadAll(false)} style={styles.iconBtn}>
          <RefreshCw size={18} color={T.sub} className={refreshing ? 'spin' : ''} />
        </button>
      </div>

      {/* Three Horizontal Dashboard Cards */}
      <div style={{
        padding: '16px',
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: 12,
      }}>
        {/* Card 1: Coins */}
        <div style={{
          padding: 18,
          borderRadius: 16,
          background: 'linear-gradient(135deg, #8fc441 0%, #6ba835 100%)',
          color: '#1A1A1A',
          boxShadow: '0 6px 20px rgba(143,196,65,0.25)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 180,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, opacity: 0.85, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            <Coins size={14} /> Coins
          </div>
          <div style={{ fontSize: 32, fontWeight: 900, marginTop: 6, lineHeight: 1 }}>
            {formatNumber(balance.total)}
          </div>
          <div style={{ fontSize: 11, opacity: 0.8, marginTop: 2 }}>Total Coins</div>
          <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid rgba(0,0,0,0.15)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
              <span style={{ opacity: 0.8 }}>Earned</span>
              <strong>{formatNumber(balance.earned)}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ opacity: 0.8 }}>Purchased</span>
              <strong>{formatNumber(balance.purchased)}</strong>
            </div>
          </div>
        </div>

        {/* Card 2: Points */}
        <div style={{
          padding: 18,
          borderRadius: 16,
          background: 'linear-gradient(135deg, #8B5CF6 0%, #6366F1 100%)',
          color: '#fff',
          boxShadow: '0 6px 20px rgba(139,92,246,0.25)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 180,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, opacity: 0.9, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            <Gift size={14} /> Points
          </div>
          <div style={{ fontSize: 32, fontWeight: 900, marginTop: 6, lineHeight: 1 }}>
            {formatNumber(points.current)}
          </div>
          <div style={{ fontSize: 11, opacity: 0.85, marginTop: 2 }}>Current Balance</div>
          <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 4 }}>
              <span style={{ opacity: 0.85 }}>Earned Total</span>
              <strong>{formatNumber(points.earned_total)}</strong>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11 }}>
              <span style={{ opacity: 0.85 }}>From Gifts</span>
              <strong>{formatNumber(points.earned_total)}</strong>
            </div>
          </div>
        </div>

        {/* Card 3: Withdrawal */}
        <div style={{
          padding: 18,
          borderRadius: 16,
          background: 'linear-gradient(135deg, #10B981 0%, #059669 100%)',
          color: '#fff',
          boxShadow: '0 6px 20px rgba(16,185,129,0.25)',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 180,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 12, fontWeight: 700, opacity: 0.9, textTransform: 'uppercase', letterSpacing: 0.5 }}>
            <ArrowUpFromLine size={14} /> Withdraw
          </div>
          <div style={{ fontSize: 32, fontWeight: 900, marginTop: 6, lineHeight: 1 }}>
            {pointsToBirr(points.current, config?.points_per_birr).toFixed(2)}
          </div>
          <div style={{ fontSize: 11, opacity: 0.85, marginTop: 2 }}>ETB Available</div>
          <div style={{ marginTop: 'auto', paddingTop: 12, borderTop: '1px solid rgba(255,255,255,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 11, marginBottom: 6 }}>
              <span style={{ opacity: 0.85 }}>Min</span>
              <strong>{config?.withdrawal_min_points || 100} pts</strong>
            </div>
            <button
              onClick={() => setShowWithdrawModal(true)}
              disabled={(points.current || 0) < (config?.withdrawal_min_points || 100)}
              style={{
                width: '100%',
                padding: '6px 8px',
                borderRadius: 8,
                background: 'rgba(255,255,255,0.2)',
                color: '#fff',
                border: '1px solid rgba(255,255,255,0.3)',
                fontSize: 11,
                fontWeight: 700,
                cursor: (points.current || 0) >= (config?.withdrawal_min_points || 100) ? 'pointer' : 'not-allowed',
                opacity: (points.current || 0) >= (config?.withdrawal_min_points || 100) ? 1 : 0.5,
              }}
            >
              Points → Birr
            </button>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ padding: '0 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <button
          onClick={() => {
            if (onShowCoinPurchase) onShowCoinPurchase();
            else setShowTopUpModal(true);
          }}
          style={btnPrimary(T)}
        >
          <ArrowDownToLine size={18} /> Buy Coins
        </button>
        <button
          onClick={() => setShowReinvestModal(true)}
          style={{
            ...btnSecondary(T),
            background: T.pri,
            color: '#fff',
            borderColor: T.pri,
          }}
        >
          <Repeat size={18} /> Re-invest Points
        </button>
      </div>

      {/* Tab navigation */}
      <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, marginTop: 20, padding: '0 16px' }}>
        {['overview', 'transactions', 'withdrawals'].map((tab) => (
          <button
            key={tab}
            onClick={() => handleTabChange(tab)}
            style={{
              flex: 1,
              padding: '12px 8px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab ? `2px solid ${T.pri}` : '2px solid transparent',
              color: activeTab === tab ? T.pri : T.sub,
              fontSize: 14,
              fontWeight: activeTab === tab ? 700 : 500,
              cursor: 'pointer',
              textTransform: 'capitalize',
            }}
          >
            {tab}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div style={{ padding: 16 }}>
        {activeTab === 'overview' && (
          <OverviewTab
            theme={T}
            totals={totals}
            withdrawal={withdrawal}
            recentTx={summary?.recent_transactions || []}
            config={config}
          />
        )}
        {activeTab === 'transactions' && (
          <TransactionsTab theme={T} transactions={transactions} />
        )}
        {activeTab === 'withdrawals' && (
          <WithdrawalsTab
            theme={T}
            withdrawals={withdrawals}
            onCancel={async (id) => {
              await api.request(`/wallet/withdrawals/${id}/cancel/`, { method: 'POST' });
              loadAll();
              loadWithdrawals();
            }}
          />
        )}
      </div>

      {/* Modals */}
      {showWithdrawModal && (
        <WithdrawModal
          theme={T}
          balance={balance}
          points={points}
          config={config}
          onClose={() => setShowWithdrawModal(false)}
          onSuccess={() => {
            setShowWithdrawModal(false);
            loadAll();
            loadWithdrawals();
          }}
        />
      )}

      {showTopUpModal && (
        <TopUpModal
          theme={T}
          packages={config?.packages || []}
          onClose={() => setShowTopUpModal(false)}
        />
      )}

      {showReinvestModal && (
        <ReinvestModal
          theme={T}
          points={points}
          onClose={() => setShowReinvestModal(false)}
          onSuccess={() => {
            setShowReinvestModal(false);
            loadAll();
          }}
        />
      )}

      <style>{`
        .spin { animation: spin 1s linear infinite; }
        @keyframes spin { 100% { transform: rotate(360deg); } }
      `}</style>
    </div>
  );
}

// ---------------------------------------------------------------
// Tabs
// ---------------------------------------------------------------

function OverviewTab({ theme: T, totals, withdrawal, recentTx, config }) {
  return (
    <div>
      {/* Lifetime stats */}
      <h3 style={{ fontSize: 15, fontWeight: 700, color: T.txt, margin: '0 0 12px 0' }}>
        Lifetime Stats
      </h3>
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 24 }}>
        <StatBox theme={T} icon={<TrendingUp size={18} color="#10B981" />}
                 label="Total Earned" value={formatNumber(totals.lifetime_earned)} sub="coins" />
        <StatBox theme={T} icon={<TrendingDown size={18} color="#EF4444" />}
                 label="Total Spent" value={formatNumber(totals.lifetime_spent)} sub="coins" />
        <StatBox theme={T} icon={<CreditCard size={18} color={T.pri} />}
                 label="Total Bought" value={formatNumber(totals.lifetime_purchased)} sub="coins" />
        <StatBox theme={T} icon={<ArrowUpFromLine size={18} color="#F59E0B" />}
                 label="Total Withdrawn" value={formatNumber(totals.lifetime_withdrawn)} sub="coins" />
      </div>

      {/* Withdrawal status */}
      {!withdrawal.eligible && (
        <div style={{
          background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
          padding: 16, marginBottom: 24, display: 'flex', alignItems: 'center', gap: 12,
        }}>
          <AlertCircle size={20} color="#F59E0B" />
          <div style={{ flex: 1, fontSize: 13, color: T.sub }}>
            Earn <strong style={{ color: T.txt }}>{withdrawal.min_points?.toLocaleString()}</strong> points
            to unlock withdrawal to Birr. You have <strong style={{ color: T.txt }}>
              {/* current earned shown in main balance card */}
            </strong>
          </div>
        </div>
      )}

      {/* Recent transactions */}
      <h3 style={{ fontSize: 15, fontWeight: 700, color: T.txt, margin: '0 0 12px 0' }}>
        Recent Activity
      </h3>
      {recentTx.length === 0 ? (
        <EmptyState theme={T} icon={<Coins size={32} />} title="No transactions yet" />
      ) : (
        <div>
          {recentTx.map((tx) => <TransactionRow key={tx.id} tx={tx} theme={T} />)}
        </div>
      )}
    </div>
  );
}

function TransactionsTab({ theme: T, transactions }) {
  if (transactions.length === 0) {
    return <EmptyState theme={T} icon={<Coins size={32} />} title="No transactions yet"
                       subtitle="Your coin activity will show here." />;
  }
  return (
    <div>
      {transactions.map((tx) => <TransactionRow key={tx.id} tx={tx} theme={T} />)}
    </div>
  );
}

function WithdrawalsTab({ theme: T, withdrawals, onCancel }) {
  if (withdrawals.length === 0) {
    return <EmptyState theme={T} icon={<ArrowUpFromLine size={32} />} title="No withdrawals yet"
                       subtitle="When you convert points to Birr, requests show here." />;
  }
  return (
    <div>
      {withdrawals.map((w) => <WithdrawalRow key={w.id} w={w} theme={T} onCancel={onCancel} />)}
    </div>
  );
}

// ---------------------------------------------------------------
// Components
// ---------------------------------------------------------------

function StatBox({ theme: T, icon, label, value, sub }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12, padding: 14,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
        {icon}
        <span style={{ fontSize: 12, color: T.sub, fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color: T.txt }}>{value}</div>
      <div style={{ fontSize: 11, color: T.sub }}>{sub}</div>
    </div>
  );
}

function TransactionRow({ tx, theme: T }) {
  const isCredit = tx.is_credit;
  const color = isCredit ? '#10B981' : '#EF4444';
  const isGift = tx.type === 'gift_sent' || tx.type === 'gift_received';
  const isPointTx = tx.type === 'gift_received';

  // Build a clear primary label
  let primaryLabel = tx.type_display;
  if (tx.type === 'gift_sent' && tx.other_user) {
    primaryLabel = `Gift sent to @${tx.other_user.username}`;
  } else if (tx.type === 'gift_received' && tx.other_user) {
    primaryLabel = `Gift received from @${tx.other_user.username}`;
  }

  const Icon = isGift ? Gift : (isCredit ? TrendingUp : TrendingDown);
  const unitLabel = isPointTx ? 'points' : 'coins';

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 12, padding: '12px 4px',
      borderBottom: `1px solid ${T.border}`,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        background: color + '15',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
      }}>
        <Icon size={18} color={color} />
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.txt }}>
          {primaryLabel}
        </div>
        <div style={{ fontSize: 12, color: T.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {formatDate(tx.created_at)}{tx.description ? ` • ${tx.description}` : ''}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color }}>
          {isCredit ? '+' : ''}{tx.coins.toLocaleString()}
        </div>
        <div style={{ fontSize: 11, color: T.sub }}>{unitLabel}</div>
      </div>
    </div>
  );
}

function WithdrawalRow({ w, theme: T, onCancel }) {
  const statusInfo = WITHDRAWAL_STATUS[w.status] || { color: T.sub, icon: Clock };
  const Icon = statusInfo.icon;
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
      padding: 14, marginBottom: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 8 }}>
        <Icon size={18} color={statusInfo.color} />
        <span style={{ fontSize: 14, fontWeight: 700, color: statusInfo.color }}>
          {w.status_display}
        </span>
        <span style={{ marginLeft: 'auto', fontSize: 12, color: T.sub }}>
          {formatDate(w.created_at)}
        </span>
      </div>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
        <Gift size={14} color={T.sub} />
        <span style={{ fontSize: 13, color: T.txt }}>
          {w.point_amount?.toLocaleString() || w.coin_amount?.toLocaleString()} points
        </span>
        <ChevronRight size={14} color={T.sub} />
        <span style={{ fontSize: 13, fontWeight: 700, color: T.pri }}>
          {Number(w.net_birr).toFixed(2)} ETB
        </span>
        <span style={{ fontSize: 11, color: T.sub }}>
          (fee {Number(w.fee_birr).toFixed(2)})
        </span>
      </div>
      <div style={{ fontSize: 12, color: T.sub }}>
        {w.payout_method_display} → {w.payout_account}
      </div>
      {w.rejection_reason && (
        <div style={{ marginTop: 8, padding: 8, background: '#FEE2E2', borderRadius: 6, fontSize: 12, color: '#991B1B' }}>
          Rejected: {w.rejection_reason}
        </div>
      )}
      {w.payout_reference && w.status === 'completed' && (
        <div style={{ marginTop: 8, fontSize: 11, color: T.sub }}>
          Reference: <code>{w.payout_reference}</code>
        </div>
      )}
      {w.can_cancel && (
        <button
          onClick={() => {
            if (confirm('Cancel this withdrawal? Points will be refunded.')) onCancel(w.id);
          }}
          style={{ ...btnSecondary(T), marginTop: 10, width: '100%' }}
        >
          Cancel Request
        </button>
      )}
    </div>
  );
}

function EmptyState({ theme: T, icon, title, subtitle }) {
  return (
    <div style={{ textAlign: 'center', padding: '40px 20px', color: T.sub }}>
      <div style={{ marginBottom: 12, opacity: 0.5 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>{title}</div>
      {subtitle && <div style={{ fontSize: 13 }}>{subtitle}</div>}
    </div>
  );
}

// ---------------------------------------------------------------
// Withdraw Modal
// ---------------------------------------------------------------

function WithdrawModal({ theme: T, balance, points, config, onClose, onSuccess }) {
  const [step, setStep] = useState(1); // 1: amount, 2: payout, 3: confirm
  const minPoints = config?.withdrawal_min_points || 100;
  const [amount, setAmount] = useState(minPoints);
  const [payoutMethod, setPayoutMethod] = useState('telebirr');
  const [payoutAccount, setPayoutAccount] = useState('');
  const [payoutAccountName, setPayoutAccountName] = useState('');
  const [preview, setPreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const pointsPerBirr = config?.points_per_birr || 10;
  const feePercent = parseFloat(config?.withdrawal?.fee_percent || '5');
  const availablePoints = points?.current || 0;

  useEffect(() => {
    if (amount > 0) {
      const gross = amount / pointsPerBirr;
      const fee = gross * (feePercent / 100);
      const net = gross - fee;
      setPreview({ gross_birr: gross, fee_birr: fee, net_birr: net });
    }
  }, [amount, pointsPerBirr, feePercent]);

  async function handleSubmit() {
    try {
      setSubmitting(true);
      setError('');
      await api.request('/wallet/withdraw/', {
        method: 'POST',
        body: JSON.stringify({
          point_amount: parseInt(amount),
          payout_method: payoutMethod,
          payout_account: payoutAccount,
          payout_account_name: payoutAccountName,
        }),
      });
      onSuccess();
    } catch (err) {
      setError(err.message || 'Withdrawal failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <Modal onClose={onClose} theme={T} title="Withdraw Points to Birr">
      {step === 1 && (
        <div>
          <div style={{ marginBottom: 16 }}>
            <label style={modalLabel(T)}>Amount in points</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              min={minPoints}
              max={availablePoints}
              style={modalInput(T)}
            />
            <div style={{ fontSize: 12, color: T.sub, marginTop: 4 }}>
              Min: {minPoints.toLocaleString()} • Available: {availablePoints.toLocaleString()} points
            </div>
          </div>

          {preview && (
            <div style={{
              background: T.bg, border: `1px solid ${T.border}`, borderRadius: 12,
              padding: 14, marginBottom: 16,
            }}>
              <Row label="Gross amount" value={`${preview.gross_birr.toFixed(2)} ETB`} theme={T} />
              <Row label={`Service fee (${feePercent}%)`} value={`-${preview.fee_birr.toFixed(2)} ETB`} theme={T} muted />
              <div style={{ borderTop: `1px solid ${T.border}`, margin: '8px 0', paddingTop: 8 }}>
                <Row label="You receive" value={`${preview.net_birr.toFixed(2)} ETB`} theme={T} bold />
              </div>
            </div>
          )}

          <button
            onClick={() => setStep(2)}
            disabled={!amount || amount < minPoints || amount > availablePoints}
            style={{ ...btnPrimary(T), width: '100%' }}
          >
            Continue
          </button>
        </div>
      )}

      {step === 2 && (
        <div>
          <label style={modalLabel(T)}>Payout method</label>
          <div style={{ display: 'grid', gap: 8, marginBottom: 16 }}>
            {[
              { value: 'telebirr', label: 'telebirr', icon: Smartphone },
              { value: 'cbe_birr', label: 'CBE Birr', icon: Smartphone },
              { value: 'bank_transfer', label: 'Bank Transfer', icon: Building2 },
              { value: 'mpesa', label: 'M-Pesa Ethiopia', icon: Smartphone },
            ].map(({ value, label, icon: Icon }) => (
              <button
                key={value}
                onClick={() => setPayoutMethod(value)}
                style={{
                  display: 'flex', alignItems: 'center', gap: 10,
                  padding: 12, borderRadius: 10,
                  border: `2px solid ${payoutMethod === value ? T.pri : T.border}`,
                  background: payoutMethod === value ? T.pri + '10' : 'transparent',
                  cursor: 'pointer', textAlign: 'left',
                }}
              >
                <Icon size={18} color={payoutMethod === value ? T.pri : T.sub} />
                <span style={{ color: T.txt, fontWeight: 600 }}>{label}</span>
              </button>
            ))}
          </div>

          <label style={modalLabel(T)}>
            {payoutMethod === 'bank_transfer' ? 'Account number' : 'Phone number'}
          </label>
          <input
            type="text"
            value={payoutAccount}
            onChange={(e) => setPayoutAccount(e.target.value)}
            placeholder={payoutMethod === 'bank_transfer' ? '1000xxxxxx' : '+251 9xx xxx xxx'}
            style={modalInput(T)}
          />

          <label style={{ ...modalLabel(T), marginTop: 12 }}>Account holder name</label>
          <input
            type="text"
            value={payoutAccountName}
            onChange={(e) => setPayoutAccountName(e.target.value)}
            placeholder="Full name as on account"
            style={modalInput(T)}
          />

          <div style={{ display: 'flex', gap: 10, marginTop: 20 }}>
            <button onClick={() => setStep(1)} style={btnSecondary(T)}>Back</button>
            <button
              onClick={() => setStep(3)}
              disabled={!payoutAccount.trim()}
              style={{ ...btnPrimary(T), flex: 1 }}
            >
              Review
            </button>
          </div>
        </div>
      )}

      {step === 3 && (
        <div>
          <div style={{
            background: T.bg, border: `1px solid ${T.border}`, borderRadius: 12,
            padding: 16, marginBottom: 16,
          }}>
            <Row label="Amount" value={`${Number(amount).toLocaleString()} points`} theme={T} />
            <Row label="You receive" value={`${preview.net_birr.toFixed(2)} ETB`} theme={T} bold />
            <div style={{ borderTop: `1px solid ${T.border}`, margin: '10px 0', paddingTop: 10 }}>
              <Row label="Method" value={payoutMethod.replace('_', ' ')} theme={T} />
              <Row label="Account" value={payoutAccount} theme={T} />
              {payoutAccountName && <Row label="Name" value={payoutAccountName} theme={T} />}
            </div>
          </div>

          <div style={{ fontSize: 12, color: T.sub, marginBottom: 16, lineHeight: 1.5 }}>
            ⏱ Processing takes {config?.withdrawal?.processing_days || 3} business days.
            Points will be deducted now and refunded if rejected.
          </div>

          {error && (
            <div style={{ background: '#FEE2E2', color: '#991B1B', padding: 10, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>
              {error}
            </div>
          )}

          <div style={{ display: 'flex', gap: 10 }}>
            <button onClick={() => setStep(2)} style={btnSecondary(T)} disabled={submitting}>
              Back
            </button>
            <button onClick={handleSubmit} disabled={submitting} style={{ ...btnPrimary(T), flex: 1 }}>
              {submitting ? 'Submitting...' : 'Confirm Withdrawal'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  );
}

// ---------------------------------------------------------------
// Top Up (Buy Coins) Modal
// ---------------------------------------------------------------

function TopUpModal({ theme: T, packages, onClose }) {
  const [selected, setSelected] = useState(null);
  const [phoneNumber, setPhoneNumber] = useState('');
  const [loading, setLoading] = useState(false);

  // Fetch user's phone number when modal opens
  useEffect(() => {
    const fetchPhoneNumber = async () => {
      try {
        console.log('[TopUpModal] Fetching user profile for phone number...');
        const profile = await api.request('/profile/me/');
        console.log('[TopUpModal] Profile data:', profile);
        if (profile && profile.phone_number) {
          console.log('[TopUpModal] Phone number from profile:', profile.phone_number);
          setPhoneNumber(profile.phone_number);
        } else {
          console.log('[TopUpModal] No phone number found in profile');
        }
      } catch (error) {
        console.error('[TopUpModal] Failed to fetch phone number:', error);
      }
    };
    fetchPhoneNumber();
  }, []);

  const handlePurchase = async () => {
    if (!selected || !phoneNumber) return;

    setLoading(true);
    try {
      const response = await fetch(`${window.location.origin}/api/wallet/telebirr/initiate/`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          package_id: selected.id,
          phone_number: phoneNumber,
        }),
      });

      const data = await response.json();

      if (data.success && data.payment_url) {
        // Redirect to telebirr payment page
        window.open(data.payment_url, '_blank');
        onClose();
      } else {
        alert(data.error || 'Payment initiation failed');
      }
    } catch (error) {
      console.error('telebirr payment error:', error);
      alert('Payment initiation failed. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Modal onClose={onClose} theme={T} title="Buy Coins with telebirr">
      {packages.length === 0 ? (
        <EmptyState theme={T} icon={<Gift size={32} />} title="No packages available"
                    subtitle="Check back soon for coin packages." />
      ) : (
        <div style={{ display: 'grid', gap: 10, marginBottom: 16 }}>
          {packages.map((pkg) => (
            <button
              key={pkg.id}
              onClick={() => setSelected(pkg)}
              style={{
                display: 'flex', alignItems: 'center', gap: 12, padding: 14,
                borderRadius: 12,
                border: `2px solid ${selected?.id === pkg.id ? T.pri : T.border}`,
                background: selected?.id === pkg.id ? T.pri + '10' : T.card,
                cursor: 'pointer', textAlign: 'left',
              }}
            >
              <div style={{
                width: 44, height: 44, borderRadius: 12,
                background: T.pri + '15',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Coins size={22} color={T.pri} />
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 16, fontWeight: 700, color: T.txt }}>
                  {pkg.total_coins.toLocaleString()} coins
                </div>
                {pkg.bonus_coins > 0 && (
                  <div style={{ fontSize: 11, color: '#10B981', fontWeight: 600 }}>
                    +{pkg.bonus_coins} bonus
                  </div>
                )}
                <div style={{ fontSize: 12, color: T.sub }}>{pkg.name}</div>
              </div>
              <div style={{ fontSize: 18, fontWeight: 700, color: T.pri }}>
                {Number(pkg.price_etb).toFixed(0)} ETB
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Phone Number Input */}
      <div style={{ marginBottom: 16 }}>
        <label style={{ ...modalLabel(T), marginBottom: 6 }}>Phone Number (for telebirr)</label>
        <input
          type="tel"
          value={phoneNumber}
          onChange={(e) => setPhoneNumber(e.target.value)}
          placeholder="+251 9xx xxx xxx"
          style={modalInput(T)}
        />
      </div>

      <button
        onClick={handlePurchase}
        disabled={!selected || !phoneNumber || loading}
        style={{ ...btnPrimary(T), width: '100%', opacity: (!selected || !phoneNumber || loading) ? 0.5 : 1 }}
      >
        {loading ? 'Processing...' : selected ? `Pay ${Number(selected.price_etb).toFixed(0)} ETB via telebirr` : 'Select a package'}
      </button>
    </Modal>
  );
}

// ---------------------------------------------------------------
// Re-invest Points Modal (Points to Coins)
// ---------------------------------------------------------------

function ReinvestModal({ theme: T, points, onClose, onSuccess }) {
  const [amount, setAmount] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const availablePoints = points?.current || 0;

  const handleReinvest = async () => {
    if (amount < 1 || amount > availablePoints) {
      setError('Invalid amount');
      return;
    }

    try {
      setSubmitting(true);
      setError('');
      await api.request('/wallet/reinvest/', {
        method: 'POST',
        body: JSON.stringify({ points: parseInt(amount) }),
      });
      onSuccess();
    } catch (err) {
      setError(err.message || 'Conversion failed');
    } finally {
      setSubmitting(false);
    }
  };

  const ACCENT = '#8fc441';        // brand green
  const ACCENT_DARK = '#6fa730';
  const SOFT_BG = T.mode === 'dark' ? '#1F2A1A' : '#F4FBEB';
  const SOFT_BORDER = T.mode === 'dark' ? '#2E3D24' : '#D8ECC0';

  return (
    <Modal onClose={onClose} theme={T} title="Re-invest Points to Coins">
      <div>
        {/* Conversion banner */}
        <div style={{
          background: `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
          borderRadius: 14, padding: '14px 16px', marginBottom: 16,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          color: '#fff', boxShadow: '0 4px 14px rgba(143,196,65,0.25)',
        }}>
          <div>
            <div style={{ fontSize: 11, fontWeight: 600, opacity: 0.85, letterSpacing: 0.5 }}>RATE</div>
            <div style={{ fontSize: 16, fontWeight: 800 }}>1 Point → 1 Coin</div>
          </div>
          <div style={{ fontSize: 12, fontWeight: 600, opacity: 0.9 }}>
            {availablePoints.toLocaleString()} pts available
          </div>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={modalLabel(T)}>Points to convert</label>
          <input
            type="number"
            value={amount}
            onChange={(e) => {
              const value = parseInt(e.target.value);
              if (isNaN(value) || value < 0) {
                setAmount(0);
              } else {
                setAmount(value);
              }
            }}
            min="0"
            max={availablePoints}
            style={{
              ...modalInput(T),
              borderColor: SOFT_BORDER,
            }}
          />
        </div>

        <div style={{
          background: SOFT_BG, border: `1px solid ${SOFT_BORDER}`, borderRadius: 12,
          padding: 14, marginBottom: 16,
        }}>
          <Row label="You will receive" value={`${amount.toLocaleString()} coins`} theme={T} bold />
        </div>

        {error && (
          <div style={{ background: '#FEE2E2', color: '#991B1B', padding: 10, borderRadius: 8, marginBottom: 12, fontSize: 13 }}>
            {error}
          </div>
        )}

        <div style={{ display: 'flex', gap: 10 }}>
          <button onClick={onClose} disabled={submitting} style={{
            flex: 1,
            padding: '12px 16px',
            borderRadius: 10,
            border: `1px solid ${T.border}`,
            background: T.bg,
            color: T.txt,
            fontSize: 14,
            fontWeight: 700,
            cursor: submitting ? 'not-allowed' : 'pointer',
          }}>
            Cancel
          </button>
          <button
            onClick={handleReinvest}
            disabled={submitting || amount < 1 || amount > availablePoints}
            style={{
              flex: 1,
              padding: '12px 16px',
              borderRadius: 10,
              border: 'none',
              background: (submitting || amount < 1 || amount > availablePoints)
                ? '#9CA3AF'
                : `linear-gradient(135deg, ${ACCENT} 0%, ${ACCENT_DARK} 100%)`,
              color: '#fff',
              fontSize: 14,
              fontWeight: 700,
              cursor: (submitting || amount < 1 || amount > availablePoints) ? 'not-allowed' : 'pointer',
              boxShadow: '0 4px 12px rgba(143,196,65,0.3)',
            }}
          >
            {submitting ? 'Converting...' : 'Confirm'}
          </button>
        </div>
      </div>
    </Modal>
  );
}

// ---------------------------------------------------------------
// Generic Modal
// ---------------------------------------------------------------

function Modal({ children, onClose, theme: T, title }) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        zIndex: 9999, padding: 16,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: T.card || (T.mode === 'dark' ? '#1a1a1a' : '#ffffff'),
          border: `1px solid ${T.border}`,
          borderRadius: 18, padding: 20,
          width: '100%', maxWidth: 460, maxHeight: '90vh', overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, flex: 1, fontSize: 18, fontWeight: 700, color: T.txt }}>{title}</h3>
          <button
            onClick={onClose}
            aria-label="Close"
            style={{
              background: T.bg,
              border: `1px solid ${T.border}`,
              borderRadius: 999,
              cursor: 'pointer',
              padding: 6,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <X size={18} color={T.txt} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function Row({ label, value, theme: T, muted, bold }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '4px 0' }}>
      <span style={{ fontSize: 13, color: T.sub }}>{label}</span>
      <span style={{
        fontSize: bold ? 16 : 14,
        fontWeight: bold ? 700 : 500,
        color: muted ? T.sub : T.txt,
      }}>{value}</span>
    </div>
  );
}

// ---------------------------------------------------------------
// Helpers / styles
// ---------------------------------------------------------------

const WITHDRAWAL_STATUS = {
  pending: { color: '#F59E0B', icon: Clock },
  approved: { color: '#3B82F6', icon: CheckCircle2 },
  processing: { color: '#3B82F6', icon: Loader },
  completed: { color: '#10B981', icon: CheckCircle2 },
  rejected: { color: '#EF4444', icon: XCircle },
  cancelled: { color: '#6B7280', icon: XCircle },
};

function formatNumber(n) {
  if (n == null) return '0';
  return n.toLocaleString();
}

function coinsToBirr(coins, coinsPerBirr) {
  if (!coinsPerBirr || coinsPerBirr <= 0) return 0;
  return coins / coinsPerBirr;
}

function pointsToBirr(points, pointsPerBirr) {
  if (!pointsPerBirr || pointsPerBirr <= 0) return 0;
  return points / pointsPerBirr;
}

function formatDate(iso) {
  if (!iso) return '';
  const d = new Date(iso);
  return d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}

function defaultTheme() {
  return {
    bg: '#F9FAFB', card: '#FFFFFF', txt: '#111827', sub: '#6B7280',
    border: '#E5E7EB', pri: '#7C3AED', red: '#EF4444',
  };
}

const styles = {
  container: { minHeight: '100vh', paddingBottom: 80 },
  header: {
    display: 'flex', alignItems: 'center', gap: 8,
    padding: '12px 16px', borderBottom: '1px solid',
  },
  backBtn: { background: 'none', border: 'none', cursor: 'pointer', padding: 4 },
  iconBtn: { background: 'none', border: 'none', cursor: 'pointer', padding: 6 },
};

const btnPrimary = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '12px 16px', borderRadius: 12, border: 'none',
  background: T.pri, color: 'white', fontSize: 14, fontWeight: 700,
  cursor: 'pointer',
});

const btnSecondary = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '12px 16px', borderRadius: 12,
  border: `1px solid ${T.border}`, background: T.card, color: T.txt,
  fontSize: 14, fontWeight: 600, cursor: 'pointer',
});

const modalLabel = (T) => ({
  display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6,
});

const modalInput = (T) => ({
  width: '100%', padding: '12px 14px', borderRadius: 10,
  border: `1px solid ${T.border}`, background: T.bg, color: T.txt,
  fontSize: 15, outline: 'none', boxSizing: 'border-box',
});

export default WalletPage;




