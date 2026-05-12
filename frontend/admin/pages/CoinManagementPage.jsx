import { useState, useEffect } from 'react';
import {
  Wallet, Coins, ArrowUpFromLine, Settings, RefreshCw,
  CheckCircle2, XCircle, Clock, Loader, Search, Filter,
  TrendingUp, TrendingDown, User, Save, AlertTriangle, ChevronRight, Gift, Trophy
} from 'lucide-react';
import api from '../../api';

/**
 * Admin Coin Management Page
 *
 * Features:
 * - View/edit WalletConfig (rewards, costs, withdrawal settings)
 * - View/manage withdrawal requests (approve, reject, mark processing, mark completed)
 * - Manual balance adjustment tool (credit/debit user's earned/purchased balance)
 */
export function CoinManagementPage({ theme }) {
  const T = theme || defaultTheme();
  const [activeTab, setActiveTab] = useState('config'); // config | withdrawals | adjust

  const [config, setConfig] = useState(null);
  const [withdrawals, setWithdrawals] = useState([]);
  const [withdrawalSummary, setWithdrawalSummary] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  // Withdrawal filters
  const [statusFilter, setStatusFilter] = useState('');
  const [withdrawalPage, setWithdrawalPage] = useState(1);

  // Balance adjustment form
  const [adjustForm, setAdjustForm] = useState({
    user_id: '',
    amount: '',
    bucket: 'earned',
    reason: 'Admin adjustment',
  });
  const [adjustResult, setAdjustResult] = useState(null);

  useEffect(() => {
    loadConfig();
  }, []);

  useEffect(() => {
    if (activeTab === 'withdrawals') {
      loadWithdrawals();
    }
  }, [activeTab, statusFilter, withdrawalPage]);

  async function loadConfig() {
    try {
      setLoading(true);
      setError('');
      const data = await api.request('/admin/wallet/config/', { skipCache: true });
      setConfig(data.config || data);
    } catch (err) {
      console.error('Config load failed:', err);
      let msg = err.message || 'Failed to load wallet config';
      try { const parsed = JSON.parse(msg); msg = parsed.detail || parsed.error || msg; } catch {}
      setError(msg);
    } finally {
      setLoading(false);
    }
  }

  async function saveConfig() {
    try {
      setSaving(true);
      setError('');
      const flat = {
        welcome_bonus: config.rewards.welcome_bonus,
        daily_login_day1: config.rewards.daily_login_day1,
        daily_login_day2: config.rewards.daily_login_day2,
        daily_login_day3: config.rewards.daily_login_day3,
        daily_login_day4: config.rewards.daily_login_day4,
        daily_login_day5: config.rewards.daily_login_day5,
        daily_login_day6: config.rewards.daily_login_day6,
        daily_login_day7: config.rewards.daily_login_day7,
        daily_post_bonus: config.rewards.daily_post_bonus,
        campaign_join_reward: config.rewards.campaign_join_reward,
        receive_like_reward: config.rewards.receive_like_reward,
        receive_like_daily_cap: config.rewards.receive_like_daily_cap,
        quality_comment_reward: config.rewards.quality_comment_reward,
        quality_comment_daily_cap: config.rewards.quality_comment_daily_cap,
        profile_complete_reward: config.rewards.profile_complete_reward,
        referral_reward: config.rewards.referral_reward,
        campaign_winner_reward: config.rewards.campaign_winner_reward,
        cost_post_create: config.costs.post_create,
        cost_like: config.costs.like,
        cost_comment: config.costs.comment,
        cost_join_campaign: config.costs.join_campaign,
        cost_extra_campaign_entry: config.costs.extra_campaign_entry,
        cost_boost_2hr: config.costs.boost_2hr,
        cost_boost_24hr: config.costs.boost_24hr,
        withdrawal_enabled: config.withdrawal.enabled,
        withdrawal_min_coins: config.withdrawal.min_coins,
        withdrawal_max_coins_per_request: config.withdrawal.max_coins_per_request,
        coins_per_birr: config.withdrawal.coins_per_birr,
        withdrawal_fee_percent: config.withdrawal.fee_percent,
        withdrawal_processing_days: config.withdrawal.processing_days,
        earned_coins_giftable: config.gifting.earned_coins_giftable,
        purchased_coins_giftable: config.gifting.purchased_coins_giftable,
        earned_coins_withdrawable: config.gifting.earned_coins_withdrawable,
        purchased_coins_withdrawable: config.gifting.purchased_coins_withdrawable,
        min_balance_to_post: config.thresholds.min_balance_to_post,
        min_balance_to_join_campaign: config.thresholds.min_balance_to_join_campaign,
        earned_coins_expire_days: config.expiry.earned_coins_expire_days,
        coins_to_points_conversion: config.points?.coins_to_points_conversion || 1,
        points_per_birr: config.points?.points_per_birr || 10,
        withdrawal_min_points: config.points?.withdrawal_min_points || 100,
        withdrawal_max_points_per_request: config.points?.withdrawal_max_points_per_request || 10000,
        daily_winner_points: config.points?.daily_winner_points || 500,
        weekly_winner_points: config.points?.weekly_winner_points || 2000,
        monthly_winner_points: config.points?.monthly_winner_points || 10000,
        grand_finalist_points: config.points?.grand_finalist_points || 5000,
        grand_winner_points: config.points?.grand_winner_points || 50000,
      };
      await api.request('/admin/wallet/config/', {
        method: 'PATCH',
        body: JSON.stringify(flat),
      });
      await loadConfig();
      setAdjustResult({ type: 'success', message: 'Wallet configuration saved' });
    } catch (err) {
      setError(err.message || 'Failed to save config');
      setAdjustResult({ type: 'error', message: err.message });
    } finally {
      setSaving(false);
    }
  }

  async function loadWithdrawals() {
    try {
      const params = new URLSearchParams({ page: withdrawalPage });
      if (statusFilter) params.set('status', statusFilter);
      const data = await api.request(`/admin/wallet/withdrawals/?${params}`);
      setWithdrawals(data.results || []);
      setWithdrawalSummary(data.summary || {});
    } catch (err) {
      console.error('Withdrawals load failed:', err);
    }
  }

  async function handleWithdrawalAction(withdrawalId, action, notes = '', payoutReference = '') {
    try {
      await api.request(`/admin/wallet/withdrawals/${withdrawalId}/action/`, {
        method: 'POST',
        body: JSON.stringify({
          action,
          notes,
          payout_reference: payoutReference,
        }),
      });
      loadWithdrawals();
    } catch (err) {
      alert('Action failed: ' + (err.message || 'Unknown error'));
    }
  }

  async function handleBalanceAdjust() {
    try {
      const { user_id, amount, bucket, reason } = adjustForm;
      if (!user_id || !amount) {
        setAdjustResult({ type: 'error', message: 'User ID and amount are required' });
        return;
      }
      await api.request('/admin/wallet/adjust-balance/', {
        method: 'POST',
        body: JSON.stringify({
          user_id: parseInt(user_id),
          amount: parseInt(amount),
          bucket,
          reason,
        }),
      });
      setAdjustResult({ type: 'success', message: 'Balance adjusted successfully' });
      setAdjustForm({ user_id: '', amount: '', bucket: 'earned', reason: 'Admin adjustment' });
    } catch (err) {
      setAdjustResult({ type: 'error', message: err.message || 'Adjustment failed' });
    }
  }

  if (loading && !config) {
    return <LoadingState theme={T} />;
  }

  return (
    <div style={{ padding: '24px 32px', background: T.bg, minHeight: '100vh' }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 800, color: T.txt }}>
          💰 Coin Management
        </h1>
        <p style={{ margin: '8px 0 0 0', fontSize: 14, color: T.sub }}>
          Configure coin economy, manage withdrawals, and adjust user balances.
        </p>
      </div>

      {/* Tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: `1px solid ${T.border}` }}>
        {[
          { id: 'config', label: 'Configuration', icon: Settings },
          { id: 'withdrawals', label: 'Withdrawals', icon: ArrowUpFromLine },
          { id: 'adjust', label: 'Balance Adjustment', icon: User },
        ].map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            style={{
              padding: '10px 16px',
              background: 'none',
              border: 'none',
              borderBottom: activeTab === tab.id ? `2px solid ${T.pri}` : '2px solid transparent',
              color: activeTab === tab.id ? T.pri : T.sub,
              fontSize: 14,
              fontWeight: activeTab === tab.id ? 700 : 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <tab.icon size={18} /> {tab.label}
          </button>
        ))}
      </div>

      {error && (
        <div style={{
          background: '#FEE2E2', color: '#991B1B', padding: 12, borderRadius: 8,
          marginBottom: 16, fontSize: 14, display: 'flex', alignItems: 'center', gap: 8,
        }}>
          <AlertTriangle size={18} /> {error}
        </div>
      )}

      {activeTab === 'config' && (
        <ConfigTab
          theme={T}
          config={config}
          setConfig={setConfig}
          onSave={saveConfig}
          saving={saving}
          result={adjustResult}
          loading={loading}
          error={error}
          onRetry={loadConfig}
        />
      )}

      {activeTab === 'withdrawals' && (
        <WithdrawalsTab
          theme={T}
          withdrawals={withdrawals}
          summary={withdrawalSummary}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          page={withdrawalPage}
          setPage={setWithdrawalPage}
          onAction={handleWithdrawalAction}
        />
      )}

      {activeTab === 'adjust' && (
        <AdjustTab
          theme={T}
          form={adjustForm}
          setForm={setAdjustForm}
          onSubmit={handleBalanceAdjust}
          result={adjustResult}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------
// Config Tab
// ---------------------------------------------------------------

function ConfigTab({ theme: T, config, setConfig, onSave, saving, result, loading, error, onRetry }) {
  if (loading) return <LoadingState theme={T} />;
  if (!config) return <ErrorState theme={T} error={error} onRetry={onRetry} />;

  const updateField = (section, field, value) => {
    setConfig({ ...config, [section]: { ...config[section], [field]: value } });
  };

  const updateNested = (section, nestedSection, field, value) => {
    setConfig({
      ...config,
      [section]: {
        ...config[section],
        [nestedSection]: { ...config[section][nestedSection], [field]: value },
      },
    });
  };

  return (
    <div>
      {result && (
        <div style={{
          background: result.type === 'success' ? '#D1FAE5' : '#FEE2E2',
          color: result.type === 'success' ? '#065F46' : '#991B1B',
          padding: 12, borderRadius: 8, marginBottom: 16, fontSize: 14,
        }}>
          {result.message}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(350px, 1fr))', gap: 24 }}>
        {/* Earning Rewards */}
        <SectionCard theme={T} title="Earning Rewards" icon={<TrendingUp size={20} color="#10B981" />}>
          <FieldRow theme={T} label="Welcome Bonus" value={config.rewards.welcome_bonus} onChange={(v) => updateField('rewards', 'welcome_bonus', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 1" value={config.rewards.daily_login_day1} onChange={(v) => updateField('rewards', 'daily_login_day1', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 2" value={config.rewards.daily_login_day2} onChange={(v) => updateField('rewards', 'daily_login_day2', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 3" value={config.rewards.daily_login_day3} onChange={(v) => updateField('rewards', 'daily_login_day3', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 4" value={config.rewards.daily_login_day4} onChange={(v) => updateField('rewards', 'daily_login_day4', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 5" value={config.rewards.daily_login_day5} onChange={(v) => updateField('rewards', 'daily_login_day5', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 6" value={config.rewards.daily_login_day6} onChange={(v) => updateField('rewards', 'daily_login_day6', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Login Day 7" value={config.rewards.daily_login_day7} onChange={(v) => updateField('rewards', 'daily_login_day7', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Daily Post Bonus" value={config.rewards.daily_post_bonus} onChange={(v) => updateField('rewards', 'daily_post_bonus', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Campaign Join Reward" value={config.rewards.campaign_join_reward} onChange={(v) => updateField('rewards', 'campaign_join_reward', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Like Received Reward" value={config.rewards.receive_like_reward} onChange={(v) => updateField('rewards', 'receive_like_reward', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Like Daily Cap" value={config.rewards.receive_like_daily_cap} onChange={(v) => updateField('rewards', 'receive_like_daily_cap', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Quality Comment Reward" value={config.rewards.quality_comment_reward} onChange={(v) => updateField('rewards', 'quality_comment_reward', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Quality Comment Daily Cap" value={config.rewards.quality_comment_daily_cap} onChange={(v) => updateField('rewards', 'quality_comment_daily_cap', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Profile Complete Reward" value={config.rewards.profile_complete_reward} onChange={(v) => updateField('rewards', 'profile_complete_reward', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Referral Reward" value={config.rewards.referral_reward} onChange={(v) => updateField('rewards', 'referral_reward', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Campaign Winner Bonus" value={config.rewards.campaign_winner_reward} onChange={(v) => updateField('rewards', 'campaign_winner_reward', parseInt(v) || 0)} />
        </SectionCard>

        {/* Action Costs */}
        <SectionCard theme={T} title="Action Costs" icon={<TrendingDown size={20} color="#EF4444" />}>
          <FieldRow theme={T} label="Create Post Cost" value={config.costs.post_create} onChange={(v) => updateField('costs', 'post_create', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Like Cost" value={config.costs.like} onChange={(v) => updateField('costs', 'like', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Comment Cost" value={config.costs.comment} onChange={(v) => updateField('costs', 'comment', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Join Campaign Cost" value={config.costs.join_campaign} onChange={(v) => updateField('costs', 'join_campaign', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Extra Entry Cost" value={config.costs.extra_campaign_entry} onChange={(v) => updateField('costs', 'extra_campaign_entry', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Boost 2hr Cost" value={config.costs.boost_2hr} onChange={(v) => updateField('costs', 'boost_2hr', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Boost 24hr Cost" value={config.costs.boost_24hr} onChange={(v) => updateField('costs', 'boost_24hr', parseInt(v) || 0)} />
        </SectionCard>

        {/* Withdrawal Settings */}
        <SectionCard theme={T} title="Withdrawal (Coin → Birr)" icon={<ArrowUpFromLine size={20} color="#F59E0B" />}>
          <ToggleField
            label="Enabled"
            checked={config.withdrawal.enabled}
            onChange={(v) => updateField('withdrawal', 'enabled', v)}
            theme={T}
          />
          <FieldRow theme={T} label="Min Coins" value={config.withdrawal.min_coins} onChange={(v) => updateField('withdrawal', 'min_coins', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Max Coins per Request" value={config.withdrawal.max_coins_per_request} onChange={(v) => updateField('withdrawal', 'max_coins_per_request', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Coins per Birr" value={config.withdrawal.coins_per_birr} onChange={(v) => updateField('withdrawal', 'coins_per_birr', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Fee Percent" value={config.withdrawal.fee_percent} onChange={(v) => updateField('withdrawal', 'fee_percent', parseFloat(v) || 0)} />
          <FieldRow theme={T} label="Processing Days" value={config.withdrawal.processing_days} onChange={(v) => updateField('withdrawal', 'processing_days', parseInt(v) || 0)} />
        </SectionCard>

        {/* Points System */}
        <SectionCard theme={T} title="Points System (Points → Birr)" icon={<Coins size={20} color="#8B5CF6" />}>
          <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
            Points are separate from coins. Gifts convert to points. Withdrawals use points only.
          </div>
          <FieldRow theme={T} label="Coins to Points Conversion (1 point per X coins)" value={config.points?.coins_to_points_conversion || 1} onChange={(v) => updateNested('points', '', 'coins_to_points_conversion', parseInt(v) || 1)} />
          <FieldRow theme={T} label="Points per Birr" value={config.points?.points_per_birr || 10} onChange={(v) => updateNested('points', '', 'points_per_birr', parseInt(v) || 10)} />
          <FieldRow theme={T} label="Min Points to Withdraw" value={config.points?.withdrawal_min_points || 100} onChange={(v) => updateNested('points', '', 'withdrawal_min_points', parseInt(v) || 100)} />
          <FieldRow theme={T} label="Max Points per Request" value={config.points?.withdrawal_max_points_per_request || 10000} onChange={(v) => updateNested('points', '', 'withdrawal_max_points_per_request', parseInt(v) || 10000)} />
        </SectionCard>

        {/* Campaign Winner Point Rewards */}
        <SectionCard theme={T} title="Campaign Winner Point Rewards" icon={<Trophy size={20} color="#F59E0B" />}>
          <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
            Points awarded to winners of each campaign type.
          </div>
          <FieldRow theme={T} label="Daily Winner Points" value={config.points?.daily_winner_points || 500} onChange={(v) => updateNested('points', '', 'daily_winner_points', parseInt(v) || 500)} />
          <FieldRow theme={T} label="Weekly Winner Points" value={config.points?.weekly_winner_points || 2000} onChange={(v) => updateNested('points', '', 'weekly_winner_points', parseInt(v) || 2000)} />
          <FieldRow theme={T} label="Monthly Winner Points" value={config.points?.monthly_winner_points || 10000} onChange={(v) => updateNested('points', '', 'monthly_winner_points', parseInt(v) || 10000)} />
          <FieldRow theme={T} label="Grand Finalist Points" value={config.points?.grand_finalist_points || 5000} onChange={(v) => updateNested('points', '', 'grand_finalist_points', parseInt(v) || 5000)} />
          <FieldRow theme={T} label="Grand Winner Points" value={config.points?.grand_winner_points || 50000} onChange={(v) => updateNested('points', '', 'grand_winner_points', parseInt(v) || 50000)} />
        </SectionCard>

        {/* Gifting Policy */}
        <SectionCard theme={T} title="Gifting Policy" icon={<Gift size={20} color="#8B5CF6" />}>
          <ToggleField label="Earned Coins Giftable" checked={config.gifting.earned_coins_giftable} onChange={(v) => updateField('gifting', 'earned_coins_giftable', v)} theme={T} />
          <ToggleField label="Purchased Coins Giftable" checked={config.gifting.purchased_coins_giftable} onChange={(v) => updateField('gifting', 'purchased_coins_giftable', v)} theme={T} />
          <ToggleField label="Earned Coins Withdrawable" checked={config.gifting.earned_coins_withdrawable} onChange={(v) => updateField('gifting', 'earned_coins_withdrawable', v)} theme={T} />
          <ToggleField label="Purchased Coins Withdrawable" checked={config.gifting.purchased_coins_withdrawable} onChange={(v) => updateField('gifting', 'purchased_coins_withdrawable', v)} theme={T} />
        </SectionCard>

        {/* Thresholds */}
        <SectionCard theme={T} title="Balance Thresholds" icon={<Wallet size={20} color="#3B82F6" />}>
          <FieldRow theme={T} label="Min Balance to Post" value={config.thresholds.min_balance_to_post} onChange={(v) => updateField('thresholds', 'min_balance_to_post', parseInt(v) || 0)} />
          <FieldRow theme={T} label="Min Balance to Join Campaign" value={config.thresholds.min_balance_to_join_campaign} onChange={(v) => updateField('thresholds', 'min_balance_to_join_campaign', parseInt(v) || 0)} />
        </SectionCard>

        {/* Expiry */}
        <SectionCard theme={T} title="Expiry" icon={<Clock size={20} color="#6B7280" />}>
          <FieldRow theme={T} label="Earned Coins Expire Days (0 = never)" value={config.expiry.earned_coins_expire_days} onChange={(v) => updateField('expiry', 'earned_coins_expire_days', parseInt(v) || 0)} />
        </SectionCard>
      </div>

      <div style={{ marginTop: 24, display: 'flex', justifyContent: 'flex-end', gap: 12 }}>
        <button onClick={onSave} disabled={saving} style={btnPrimary(T)}>
          {saving ? <><Loader size={16} className="spin" /> Saving...</> : <><Save size={16} /> Save Configuration</>}
        </button>
      </div>

      <div style={{ marginTop: 16, fontSize: 12, color: T.sub }}>
        Last updated: {config.updated_at ? new Date(config.updated_at).toLocaleString() : 'Never'} by {config.updated_by || 'System'}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------
// Withdrawals Tab
// ---------------------------------------------------------------

function WithdrawalsTab({ theme: T, withdrawals, summary, statusFilter, setStatusFilter, page, setPage, onAction }) {
  return (
    <div>
      {/* Summary Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))', gap: 12, marginBottom: 20 }}>
        {[
          { label: 'Pending', value: summary.pending || 0, color: '#F59E0B' },
          { label: 'Approved', value: summary.approved || 0, color: '#3B82F6' },
          { label: 'Processing', value: summary.processing || 0, color: '#8B5CF6' },
          { label: 'Completed', value: summary.completed || 0, color: '#10B981' },
          { label: 'Rejected', value: summary.rejected || 0, color: '#EF4444' },
        ].map((stat) => (
          <div key={stat.label} style={{
            background: T.card, border: `1px solid ${T.border}`, borderRadius: 10,
            padding: 14, display: 'flex', flexDirection: 'column',
          }}>
            <span style={{ fontSize: 12, color: T.sub }}>{stat.label}</span>
            <span style={{ fontSize: 24, fontWeight: 700, color: stat.color }}>{stat.value}</span>
          </div>
        ))}
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 16, alignItems: 'center' }}>
        <Filter size={18} color={T.sub} />
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={{ padding: 8, borderRadius: 8, border: `1px solid ${T.border}`, background: T.card, color: T.txt, fontSize: 14 }}
        >
          <option value="">All Statuses</option>
          <option value="pending">Pending</option>
          <option value="approved">Approved</option>
          <option value="processing">Processing</option>
          <option value="completed">Completed</option>
          <option value="rejected">Rejected</option>
        </select>
        <div style={{ flex: 1 }} />
        <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1} style={btnSecondary(T)}>
          Previous
        </button>
        <span style={{ color: T.sub, fontSize: 14 }}>Page {page}</span>
        <button onClick={() => setPage(page + 1)} style={btnSecondary(T)}>
          Next
        </button>
      </div>

      {/* Withdrawals List */}
      {withdrawals.length === 0 ? (
        <EmptyState theme={T} icon={<ArrowUpFromLine size={32} />} title="No withdrawal requests" />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          {withdrawals.map((w) => (
            <WithdrawalCard key={w.id} w={w} theme={T} onAction={onAction} />
          ))}
        </div>
      )}
    </div>
  );
}

function WithdrawalCard({ w, theme: T, onAction }) {
  const statusInfo = WITHDRAWAL_STATUS[w.status] || { color: T.sub, icon: Clock };
  const Icon = statusInfo.icon;

  const [showActions, setShowActions] = useState(false);
  const [notes, setNotes] = useState('');
  const [payoutRef, setPayoutRef] = useState('');

  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
      padding: 16,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
        <div style={{ width: 40, height: 40, borderRadius: '50%', background: statusInfo.color + '15', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
          <Icon size={20} color={statusInfo.color} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ fontSize: 15, fontWeight: 700, color: T.txt }}>
              {w.user.username}
            </span>
            <span style={{ fontSize: 12, color: T.sub }}>({w.user.email})</span>
          </div>
          <div style={{ fontSize: 12, color: T.sub }}>
            {formatDate(w.created_at)}
          </div>
        </div>
        <div style={{ textAlign: 'right' }}>
          <div style={{ fontSize: 18, fontWeight: 700, color: T.txt }}>
            {w.coin_amount.toLocaleString()} coins
          </div>
          <div style={{ fontSize: 13, color: T.pri, fontWeight: 600 }}>
            → {Number(w.net_birr).toFixed(2)} ETB
          </div>
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12, marginBottom: 12, fontSize: 13, color: T.sub }}>
        <div><span style={{ fontWeight: 600, color: T.txt }}>Method:</span> {w.payout_method_display}</div>
        <div><span style={{ fontWeight: 600, color: T.txt }}>Account:</span> {w.payout_account}</div>
        <div><span style={{ fontWeight: 600, color: T.txt }}>Name:</span> {w.payout_account_name || '-'}</div>
      </div>

      {w.rejection_reason && (
        <div style={{ background: '#FEE2E2', color: '#991B1B', padding: 10, borderRadius: 8, fontSize: 12, marginBottom: 12 }}>
          Rejected: {w.rejection_reason}
        </div>
      )}

      {w.payout_reference && w.status === 'completed' && (
        <div style={{ background: '#D1FAE5', color: '#065F46', padding: 10, borderRadius: 8, fontSize: 12, marginBottom: 12 }}>
          Paid via reference: <code>{w.payout_reference}</code>
        </div>
      )}

      {/* Action Buttons */}
      {w.status === 'pending' && (
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => onAction(w.id, 'approve', notes)} style={btnSuccess(T)}>
            <CheckCircle2 size={16} /> Approve
          </button>
          <button onClick={() => onAction(w.id, 'reject', notes)} style={btnDanger(T)}>
            <XCircle size={16} /> Reject
          </button>
        </div>
      )}

      {w.status === 'approved' && (
        <div style={{ display: 'flex', gap: 8 }}>
          <button onClick={() => onAction(w.id, 'mark_processing')} style={btnSecondary(T)}>
            <Loader size={16} /> Mark Processing
          </button>
        </div>
      )}

      {w.status === 'processing' && (
        <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          <input
            type="text"
            placeholder="Payout reference (e.g., telebirr TX ID)"
            value={payoutRef}
            onChange={(e) => setPayoutRef(e.target.value)}
            style={{ flex: 1, padding: 8, borderRadius: 8, border: `1px solid ${T.border}`, background: T.bg, color: T.txt, fontSize: 13 }}
          />
          <button
            onClick={() => payoutRef ? onAction(w.id, 'mark_completed', '', payoutRef) : null}
            disabled={!payoutRef}
            style={btnSuccess(T)}
          >
            <CheckCircle2 size={16} /> Mark Completed
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------
// Balance Adjustment Tab
// ---------------------------------------------------------------

function AdjustTab({ theme: T, form, setForm, onSubmit, result }) {
  return (
    <div style={{ maxWidth: 500 }}>
      <SectionCard theme={T} title="Manual Balance Adjustment" icon={<User size={20} color="#8B5CF6" />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6 }}>
              User ID
            </label>
            <input
              type="number"
              value={form.user_id}
              onChange={(e) => setForm({ ...form, user_id: e.target.value })}
              placeholder="Enter user ID"
              style={inputStyle(T)}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6 }}>
              Amount (positive to add, negative to deduct)
            </label>
            <input
              type="number"
              value={form.amount}
              onChange={(e) => setForm({ ...form, amount: e.target.value })}
              placeholder="e.g., 100 or -50"
              style={inputStyle(T)}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6 }}>
              Bucket
            </label>
            <select
              value={form.bucket}
              onChange={(e) => setForm({ ...form, bucket: e.target.value })}
              style={inputStyle(T)}
            >
              <option value="earned">Earned Balance</option>
              <option value="purchased">Purchased Balance</option>
            </select>
          </div>

          <div>
            <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 6 }}>
              Reason
            </label>
            <input
              type="text"
              value={form.reason}
              onChange={(e) => setForm({ ...form, reason: e.target.value })}
              placeholder="Reason for adjustment"
              style={inputStyle(T)}
            />
          </div>

          {result && (
            <div style={{
              background: result.type === 'success' ? '#D1FAE5' : '#FEE2E2',
              color: result.type === 'success' ? '#065F46' : '#991B1B',
              padding: 10, borderRadius: 8, fontSize: 13,
            }}>
              {result.message}
            </div>
          )}

          <button onClick={onSubmit} style={btnPrimary(T)}>
            <Save size={16} /> Adjust Balance
          </button>
        </div>
      </SectionCard>

      <div style={{ marginTop: 16, padding: 16, background: '#FEF3C7', borderRadius: 8, fontSize: 12, color: '#92400E' }}>
        <strong>⚠️ Warning:</strong> Manual balance adjustments are logged as admin transactions. Use this feature responsibly and only for legitimate corrections.
      </div>
    </div>
  );
}

// ---------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------

function SectionCard({ theme: T, title, icon, children }) {
  return (
    <div style={{
      background: T.card, border: `1px solid ${T.border}`, borderRadius: 12,
      padding: 16, boxShadow: '0 1px 3px rgba(0,0,0,0.05)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 16 }}>
        {icon}
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: T.txt }}>{title}</h3>
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
        {children}
      </div>
    </div>
  );
}

function FieldRow({ label, value, onChange, type = 'number', theme: T }) {
  const theme = T || defaultTheme();
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <span style={{ fontSize: 13, color: theme.sub, minWidth: 140 }}>{label}</span>
      <input
        type={type}
        value={value ?? ''}
        onChange={(e) => onChange(e.target.value)}
        style={{
          flex: 1, padding: 8, borderRadius: 6, border: `1px solid ${theme.border}`,
          background: theme.bg, color: theme.txt, fontSize: 14,
        }}
      />
    </div>
  );
}

function ToggleField({ label, checked, onChange, theme: T }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <span style={{ fontSize: 13, color: T.sub }}>{label}</span>
      <button
        onClick={() => onChange(!checked)}
        style={{
          width: 44, height: 24, borderRadius: 12, background: checked ? T.pri : '#E5E7EB',
          border: 'none', cursor: 'pointer', position: 'relative', transition: 'background 0.2s',
        }}
      >
        <div style={{
          width: 20, height: 20, borderRadius: '50%', background: 'white',
          position: 'absolute', top: 2, left: checked ? 22 : 2, transition: 'left 0.2s',
          boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
        }} />
      </button>
    </div>
  );
}

function EmptyState({ theme: T, icon, title, subtitle }) {
  return (
    <div style={{ textAlign: 'center', padding: 40, color: T.sub }}>
      <div style={{ marginBottom: 12, opacity: 0.5 }}>{icon}</div>
      <div style={{ fontSize: 15, fontWeight: 600, color: T.txt, marginBottom: 4 }}>{title}</div>
      {subtitle && <div style={{ fontSize: 13 }}>{subtitle}</div>}
    </div>
  );
}

function LoadingState({ theme: T }) {
  return (
    <div style={{ padding: 40, textAlign: 'center', color: T.sub }}>
      <Loader size={32} className="spin" />
      <div style={{ marginTop: 12 }}>Loading...</div>
    </div>
  );
}

function ErrorState({ theme: T, error, onRetry }) {
  return (
    <div style={{ padding: 40, textAlign: 'center' }}>
      <AlertTriangle size={36} color={T.red || '#EF4444'} style={{ marginBottom: 12 }} />
      <div style={{ fontSize: 16, fontWeight: 600, color: T.txt, marginBottom: 8 }}>
        Failed to load configuration
      </div>
      <div style={{ fontSize: 13, color: T.sub, marginBottom: 20, maxWidth: 400, margin: '0 auto 20px' }}>
        {error || 'Could not connect to the server. Please check your connection and try again.'}
      </div>
      {onRetry && (
        <button
          onClick={onRetry}
          style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            padding: '10px 24px', borderRadius: 8, border: 'none',
            background: T.pri || '#7C3AED', color: 'white',
            fontSize: 14, fontWeight: 600, cursor: 'pointer',
          }}
        >
          <RefreshCw size={16} /> Retry
        </button>
      )}
    </div>
  );
}

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleString();
}

function defaultTheme() {
  return {
    bg: '#F9FAFB', card: '#FFFFFF', txt: '#111827', sub: '#6B7280',
    border: '#E5E7EB', pri: '#7C3AED', red: '#EF4444',
  };
}

const WITHDRAWAL_STATUS = {
  pending: { color: '#F59E0B', icon: Clock },
  approved: { color: '#3B82F6', icon: CheckCircle2 },
  processing: { color: '#8B5CF6', icon: Loader },
  completed: { color: '#10B981', icon: CheckCircle2 },
  rejected: { color: '#EF4444', icon: XCircle },
  cancelled: { color: '#6B7280', icon: XCircle },
};

const inputStyle = (T) => ({
  width: '100%', padding: 10, borderRadius: 8, border: `1px solid ${T.border}`,
  background: T.bg, color: T.txt, fontSize: 14, outline: 'none',
});

const btnPrimary = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
  padding: '10px 20px', borderRadius: 8, border: 'none',
  background: T.pri, color: 'white', fontSize: 14, fontWeight: 600, cursor: 'pointer',
});

const btnSecondary = (T) => ({
  padding: 8, borderRadius: 6, border: `1px solid ${T.border}`,
  background: T.card, color: T.txt, fontSize: 13, fontWeight: 500, cursor: 'pointer',
});

const btnSuccess = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  padding: 8, borderRadius: 6, border: 'none', background: '#10B981',
  color: 'white', fontSize: 13, fontWeight: 600, cursor: 'pointer',
});

const btnDanger = (T) => ({
  display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
  padding: 8, borderRadius: 6, border: 'none', background: '#EF4444',
  color: 'white', fontSize: 13, fontWeight: 600, cursor: 'pointer',
});

export default CoinManagementPage;




