import { useState, useEffect } from 'react';
import {
  Wallet, Coins, ArrowDownToLine, ArrowUpFromLine, Gift,
  TrendingUp, TrendingDown, Calendar, Clock, CheckCircle2,
  XCircle, AlertCircle, Loader, ChevronLeft, RefreshCw,
  CreditCard, Smartphone, Building2, ChevronRight, X,
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

export function WalletPage({ theme, onBack }) {
  const T = theme || defaultTheme();
  const [activeTab, setActiveTab] = useState('overview'); // overview | transactions | withdrawals

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
  const [showTopUpModal, setShowTopUpModal] = useState(false);

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
  const totals = summary?.totals || {};
  const withdrawal = summary?.withdrawal || {};

  return (
    <div style={{ ...styles.container, background: T.bg }}>
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

      {/* Balance Card */}
      <div style={{
        margin: '16px',
        padding: 24,
        borderRadius: 20,
        background: `linear-gradient(135deg, ${T.pri} 0%, #6366F1 100%)`,
        color: 'white',
        boxShadow: '0 10px 30px rgba(0,0,0,0.15)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, opacity: 0.9, fontSize: 13 }}>
          <Coins size={16} /> Total Balance
        </div>
        <div style={{ fontSize: 42, fontWeight: 800, marginTop: 4, marginBottom: 4 }}>
          {formatNumber(balance.total)}
        </div>
        <div style={{ fontSize: 13, opacity: 0.9 }}>
          ≈ {coinsToBirr(balance.total, config?.coins_per_birr).toFixed(2)} ETB (Birr)
        </div>

        {/* Two-bucket breakdown */}
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 12,
          marginTop: 20,
          padding: '16px 0 0 0',
          borderTop: '1px solid rgba(255,255,255,0.2)',
        }}>
          <div>
            <div style={{ fontSize: 11, opacity: 0.85, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Earned
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2 }}>
              {formatNumber(balance.earned)}
            </div>
            <div style={{ fontSize: 11, opacity: 0.8 }}>Withdrawable to Birr</div>
          </div>
          <div>
            <div style={{ fontSize: 11, opacity: 0.85, textTransform: 'uppercase', letterSpacing: 0.5 }}>
              Purchased
            </div>
            <div style={{ fontSize: 22, fontWeight: 700, marginTop: 2 }}>
              {formatNumber(balance.purchased)}
            </div>
            <div style={{ fontSize: 11, opacity: 0.8 }}>For gifts & boosts</div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div style={{ padding: '0 16px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
        <button onClick={() => setShowTopUpModal(true)} style={btnPrimary(T)}>
          <ArrowDownToLine size={18} /> Buy Coins
        </button>
        <button
          onClick={() => setShowWithdrawModal(true)}
          disabled={!withdrawal.eligible}
          style={{
            ...btnSecondary(T),
            opacity: withdrawal.eligible ? 1 : 0.5,
            cursor: withdrawal.eligible ? 'pointer' : 'not-allowed',
          }}
          title={!withdrawal.eligible ? `Need ${withdrawal.min_coins} earned coins to withdraw` : ''}
        >
          <ArrowUpFromLine size={18} /> Withdraw to Birr
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
            Earn <strong style={{ color: T.txt }}>{withdrawal.min_coins?.toLocaleString()}</strong> coins
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
                       subtitle="When you convert coins to Birr, requests show here." />;
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
        {isCredit ? <TrendingUp size={18} color={color} /> : <TrendingDown size={18} color={color} />}
      </div>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 14, fontWeight: 600, color: T.txt }}>
          {tx.type_display}
        </div>
        <div style={{ fontSize: 12, color: T.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {tx.description || formatDate(tx.created_at)}
        </div>
      </div>
      <div style={{ textAlign: 'right' }}>
        <div style={{ fontSize: 15, fontWeight: 700, color }}>
          {isCredit ? '+' : ''}{tx.coins.toLocaleString()}
        </div>
        <div style={{ fontSize: 11, color: T.sub }}>coins</div>
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
        <Coins size={14} color={T.sub} />
        <span style={{ fontSize: 13, color: T.txt }}>
          {w.coin_amount.toLocaleString()} coins
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
            if (confirm('Cancel this withdrawal? Coins will be refunded.')) onCancel(w.id);
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

function WithdrawModal({ theme: T, balance, config, onClose, onSuccess }) {
  const [step, setStep] = useState(1); // 1: amount, 2: payout, 3: confirm
  const [amount, setAmount] = useState(config?.withdrawal?.min_coins || 1000);
  const [payoutMethod, setPayoutMethod] = useState('telebirr');
  const [payoutAccount, setPayoutAccount] = useState('');
  const [payoutAccountName, setPayoutAccountName] = useState('');
  const [preview, setPreview] = useState(null);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');

  const minCoins = config?.withdrawal?.min_coins || 1000;
  const coinsPerBirr = config?.coins_per_birr || 100;
  const feePercent = parseFloat(config?.withdrawal?.fee_percent || '5');

  useEffect(() => {
    if (amount > 0) {
      const gross = amount / coinsPerBirr;
      const fee = gross * (feePercent / 100);
      const net = gross - fee;
      setPreview({ gross_birr: gross, fee_birr: fee, net_birr: net });
    }
  }, [amount, coinsPerBirr, feePercent]);

  async function handleSubmit() {
    try {
      setSubmitting(true);
      setError('');
      await api.request('/wallet/withdraw/', {
        method: 'POST',
        body: JSON.stringify({
          coin_amount: parseInt(amount),
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
    <Modal onClose={onClose} theme={T} title="Withdraw to Birr">
      {step === 1 && (
        <div>
          <div style={{ marginBottom: 16 }}>
            <label style={modalLabel(T)}>Amount in coins</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              min={minCoins}
              max={balance.earned}
              style={modalInput(T)}
            />
            <div style={{ fontSize: 12, color: T.sub, marginTop: 4 }}>
              Min: {minCoins.toLocaleString()} • Available: {balance.earned.toLocaleString()} coins
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
            disabled={!amount || amount < minCoins || amount > balance.earned}
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
            <Row label="Amount" value={`${amount.toLocaleString()} coins`} theme={T} />
            <Row label="You receive" value={`${preview.net_birr.toFixed(2)} ETB`} theme={T} bold />
            <div style={{ borderTop: `1px solid ${T.border}`, margin: '10px 0', paddingTop: 10 }}>
              <Row label="Method" value={payoutMethod.replace('_', ' ')} theme={T} />
              <Row label="Account" value={payoutAccount} theme={T} />
              {payoutAccountName && <Row label="Name" value={payoutAccountName} theme={T} />}
            </div>
          </div>

          <div style={{ fontSize: 12, color: T.sub, marginBottom: 16, lineHeight: 1.5 }}>
            ⏱ Processing takes {config?.withdrawal?.processing_days || 3} business days.
            Coins will be deducted now and refunded if rejected.
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
          background: T.card, borderRadius: 18, padding: 20,
          width: '100%', maxWidth: 460, maxHeight: '90vh', overflow: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
          <h3 style={{ margin: 0, flex: 1, fontSize: 18, fontWeight: 700, color: T.txt }}>{title}</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <X size={20} color={T.sub} />
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
    position: 'sticky', top: 0, zIndex: 10,
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




