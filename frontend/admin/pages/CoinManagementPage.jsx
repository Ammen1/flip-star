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
  const [activeTab, setActiveTab] = useState(() => localStorage.getItem('adminCoinTab') || 'config'); // config | withdrawals | adjust

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
    localStorage.setItem('adminCoinTab', activeTab);
  }, [activeTab]);

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
        cost_post_create: config.costs.post_create || 0,
        cost_like: config.costs.like || 0,
        cost_comment: config.costs.comment || 0,
        cost_share: config.costs.share || 0,
        cost_gift: config.costs.gift || 0,
        cost_join_campaign: config.costs.join_campaign || 0,
        cost_extra_campaign_entry: config.costs.extra_campaign_entry || 0,
        cost_boost_1hr: config.costs.boost_1hr || 0,
        cost_boost_2hr: config.costs.boost_2hr || 0,
        cost_boost_24hr: config.costs.boost_24hr || 0,
        cost_trending_1hr: config.costs.trending_1hr || 0,
        cost_trending_24hr: config.costs.trending_24hr || 0,
        cost_post_create_non_campaign: config.costs.post_create_non_campaign || 0,
        cost_like_non_campaign: config.costs.like_non_campaign || 0,
        cost_comment_non_campaign: config.costs.comment_non_campaign || 0,
        cost_share_non_campaign: config.costs.share_non_campaign || 0,
        cost_gift_non_campaign: config.costs.gift_non_campaign || 0,
        cost_boost_1hr_non_campaign: config.costs.boost_1hr_non_campaign || 0,
        cost_boost_2hr_non_campaign: config.costs.boost_2hr_non_campaign || 0,
        cost_boost_24hr_non_campaign: config.costs.boost_24hr_non_campaign || 0,
        cost_trending_1hr_non_campaign: config.costs.trending_1hr_non_campaign || 0,
        cost_trending_24hr_non_campaign: config.costs.trending_24hr_non_campaign || 0,
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
        gift_min_points_per_transaction: config.gifting.min_points_per_transaction || 10,
        gift_max_points_per_transaction: config.gifting.max_points_per_transaction || 5000,
        gift_max_points_to_recipient_per_day: config.gifting.max_points_to_recipient_per_day || 5000,
        gift_max_total_points_sent_per_day: config.gifting.max_total_points_sent_per_day || 10000,
        min_balance_to_post: config.thresholds.min_balance_to_post,
        min_balance_to_join_campaign: config.thresholds.min_balance_to_join_campaign,
        earned_coins_expire_days: config.expiry.earned_coins_expire_days,
        coins_to_points_conversion: config.points?.coins_to_points_conversion ?? 1,
        points_per_birr: config.points?.points_per_birr ?? 10,
        withdrawal_min_points: config.points?.withdrawal_min_points ?? 1000,
        withdrawal_max_points_per_request: config.points?.withdrawal_max_points_per_request ?? 50000,
        daily_winner_points: config.points?.daily_winner_points ?? 500,
        weekly_winner_points: config.points?.weekly_winner_points ?? 2000,
        monthly_winner_points: config.points?.monthly_winner_points ?? 10000,
        grand_finalist_points: config.points?.grand_finalist_points ?? 5000,
        grand_winner_points: config.points?.grand_winner_points ?? 50000,
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
  const [activeSubTab, setActiveSubTab] = useState(() => localStorage.getItem('adminCoinConfigSubTab') || 'earned');

  useEffect(() => {
    localStorage.setItem('adminCoinConfigSubTab', activeSubTab);
  }, [activeSubTab]);

  if (loading) return <LoadingState theme={T} />;
  if (!config) return <ErrorState theme={T} error={error} onRetry={onRetry} />;

  const updateField = (section, field, value) => {
    setConfig({ 
      ...config, 
      [section]: { 
        ...(config[section] || {}), 
        [field]: value 
      } 
    });
  };

  const updateNested = (section, nestedSection, field, value) => {
    setConfig({
      ...config,
      [section]: {
        ...(config[section] || {}),
        [nestedSection]: { ...(config[section]?.[nestedSection] || {}), [field]: value },
      },
    });
  };

  const subTabs = [
    { id: 'earned', label: 'Earned Coins', icon: TrendingUp },
    { id: 'action', label: 'Campaign Action Costs', icon: TrendingDown },
    { id: 'non_campaign_action', label: 'Non-Campaign Action Costs', icon: TrendingDown },
    { id: 'withdrawal', label: 'Withdrawal', icon: ArrowUpFromLine },
    { id: 'points', label: 'Points System', icon: Coins },
    { id: 'gifting', label: 'Gifting', icon: Gift },
    { id: 'other', label: 'Other Settings', icon: Settings },
  ];

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

      {/* Sub-tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 24, borderBottom: `1px solid ${T.border}`, flexWrap: 'wrap' }}>
        {subTabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveSubTab(tab.id)}
            style={{
              padding: '8px 14px',
              background: 'none',
              border: 'none',
              borderBottom: activeSubTab === tab.id ? `2px solid ${T.pri}` : '2px solid transparent',
              color: activeSubTab === tab.id ? T.pri : T.sub,
              fontSize: 13,
              fontWeight: activeSubTab === tab.id ? 600 : 500,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <tab.icon size={16} /> {tab.label}
          </button>
        ))}
      </div>

      {/* Sub-tab content */}
      {activeSubTab === 'earned' && (
        <EarnedCoinsSubTab theme={T} config={config} updateField={updateField} />
      )}

      {activeSubTab === 'action' && (
        <ActionCostsSubTab theme={T} config={config} updateField={updateField} />
      )}

      {activeSubTab === 'non_campaign_action' && (
        <NonCampaignActionCostsSubTab theme={T} config={config} updateField={updateField} />
      )}

      {activeSubTab === 'withdrawal' && (
        <WithdrawalSubTab theme={T} config={config} updateField={updateField} updateNested={updateNested} />
      )}

      {activeSubTab === 'points' && (
        <PointsSubTab theme={T} config={config} updateField={updateField} />
      )}

      {activeSubTab === 'gifting' && (
        <GiftingSubTab theme={T} config={config} updateField={updateField} />
      )}

      {activeSubTab === 'other' && (
        <OtherSettingsSubTab theme={T} config={config} updateField={updateField} />
      )}

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
// Sub-tab: Earned Coins
// ---------------------------------------------------------------

function EarnedCoinsSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
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
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Action Costs
// ---------------------------------------------------------------

function ActionCostsSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Campaign Action Costs" icon={<TrendingDown size={20} color="#EF4444" />}>
        <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
          Costs for actions on campaign posts
        </div>
        <FieldRow theme={T} label="Create Post Cost" value={config.costs.post_create} onChange={(v) => updateField('costs', 'post_create', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Like Cost" value={config.costs.like} onChange={(v) => updateField('costs', 'like', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Comment Cost" value={config.costs.comment} onChange={(v) => updateField('costs', 'comment', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Share Cost" value={config.costs.share} onChange={(v) => updateField('costs', 'share', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Gift Cost" value={config.costs.gift} onChange={(v) => updateField('costs', 'gift', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Join Campaign Cost" value={config.costs.join_campaign} onChange={(v) => updateField('costs', 'join_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Extra Entry Cost" value={config.costs.extra_campaign_entry} onChange={(v) => updateField('costs', 'extra_campaign_entry', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 1hr Cost" value={config.costs.boost_1hr} onChange={(v) => updateField('costs', 'boost_1hr', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 2hr Cost" value={config.costs.boost_2hr} onChange={(v) => updateField('costs', 'boost_2hr', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 24hr Cost" value={config.costs.boost_24hr} onChange={(v) => updateField('costs', 'boost_24hr', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Trending 1hr Cost" value={config.costs.trending_1hr} onChange={(v) => updateField('costs', 'trending_1hr', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Trending 24hr Cost" value={config.costs.trending_24hr} onChange={(v) => updateField('costs', 'trending_24hr', parseInt(v) || 0)} />
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Non-Campaign Action Costs
// ---------------------------------------------------------------

function NonCampaignActionCostsSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Non-Campaign Action Costs" icon={<TrendingDown size={20} color="#8B5CF6" />}>
        <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
          Costs for actions on non-campaign posts
        </div>
        <FieldRow theme={T} label="Create Post Cost" value={config.costs.post_create_non_campaign} onChange={(v) => updateField('costs', 'post_create_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Like Cost" value={config.costs.like_non_campaign} onChange={(v) => updateField('costs', 'like_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Comment Cost" value={config.costs.comment_non_campaign} onChange={(v) => updateField('costs', 'comment_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Share Cost" value={config.costs.share_non_campaign} onChange={(v) => updateField('costs', 'share_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Gift Cost" value={config.costs.gift_non_campaign} onChange={(v) => updateField('costs', 'gift_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 1hr Cost" value={config.costs.boost_1hr_non_campaign} onChange={(v) => updateField('costs', 'boost_1hr_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 2hr Cost" value={config.costs.boost_2hr_non_campaign} onChange={(v) => updateField('costs', 'boost_2hr_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Boost 24hr Cost" value={config.costs.boost_24hr_non_campaign} onChange={(v) => updateField('costs', 'boost_24hr_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Trending 1hr Cost" value={config.costs.trending_1hr_non_campaign} onChange={(v) => updateField('costs', 'trending_1hr_non_campaign', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Trending 24hr Cost" value={config.costs.trending_24hr_non_campaign} onChange={(v) => updateField('costs', 'trending_24hr_non_campaign', parseInt(v) || 0)} />
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Withdrawal
// ---------------------------------------------------------------

function WithdrawalSubTab({ theme: T, config, updateField, updateNested }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Withdrawal (Coin → Birr)" icon={<ArrowUpFromLine size={20} color="#8fc441" />}>
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
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Points System
// ---------------------------------------------------------------

function PointsSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Points System (Points → Birr)" icon={<Coins size={20} color="#8B5CF6" />}>
        <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
          Points are separate from coins. Gifts convert to points. Withdrawals use points only.
        </div>
        <FieldRow theme={T} label="Coins to Points Conversion (1 point per X coins)" value={config.points?.coins_to_points_conversion || 1} onChange={(v) => updateField('points', 'coins_to_points_conversion', parseInt(v) || 1)} />
        <FieldRow theme={T} label="Points per Birr" value={config.points?.points_per_birr || 10} onChange={(v) => updateField('points', 'points_per_birr', parseInt(v) || 10)} />
        <FieldRow theme={T} label="Min Points to Withdraw" value={config.points?.withdrawal_min_points || 1000} onChange={(v) => updateField('points', 'withdrawal_min_points', parseInt(v) || 1000)} />
        <FieldRow theme={T} label="Max Points per Request" value={config.points?.withdrawal_max_points_per_request || 50000} onChange={(v) => updateField('points', 'withdrawal_max_points_per_request', parseInt(v) || 50000)} />
      </SectionCard>

      <SectionCard theme={T} title="Campaign Winner Point Rewards" icon={<Trophy size={20} color="#8fc441" />}>
        <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
          Points awarded to winners of each campaign type.
        </div>
        <FieldRow theme={T} label="Daily Winner Points" value={config.points?.daily_winner_points || 500} onChange={(v) => updateField('points', 'daily_winner_points', parseInt(v) || 500)} />
        <FieldRow theme={T} label="Weekly Winner Points" value={config.points?.weekly_winner_points || 2000} onChange={(v) => updateField('points', 'weekly_winner_points', parseInt(v) || 2000)} />
        <FieldRow theme={T} label="Monthly Winner Points" value={config.points?.monthly_winner_points || 10000} onChange={(v) => updateField('points', 'monthly_winner_points', parseInt(v) || 10000)} />
        <FieldRow theme={T} label="Grand Finalist Points" value={config.points?.grand_finalist_points || 5000} onChange={(v) => updateField('points', 'grand_finalist_points', parseInt(v) || 5000)} />
        <FieldRow theme={T} label="Grand Winner Points" value={config.points?.grand_winner_points || 50000} onChange={(v) => updateField('points', 'grand_winner_points', parseInt(v) || 50000)} />
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Gifting
// ---------------------------------------------------------------

function GiftingSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Gifting Policy" icon={<Gift size={20} color="#8B5CF6" />}>
        <ToggleField label="Earned Coins Giftable" checked={config.gifting.earned_coins_giftable} onChange={(v) => updateField('gifting', 'earned_coins_giftable', v)} theme={T} />
        <ToggleField label="Purchased Coins Giftable" checked={config.gifting.purchased_coins_giftable} onChange={(v) => updateField('gifting', 'purchased_coins_giftable', v)} theme={T} />
        <ToggleField label="Earned Coins Withdrawable" checked={config.gifting.earned_coins_withdrawable} onChange={(v) => updateField('gifting', 'earned_coins_withdrawable', v)} theme={T} />
        <ToggleField label="Purchased Coins Withdrawable" checked={config.gifting.purchased_coins_withdrawable} onChange={(v) => updateField('gifting', 'purchased_coins_withdrawable', v)} theme={T} />
      </SectionCard>

      <SectionCard theme={T} title="Gift Transfer Restrictions (Points)" icon={<Trophy size={20} color="#8fc441" />}>
        <div style={{ fontSize: 12, color: T.sub, marginBottom: 12, fontStyle: 'italic' }}>
          Limits for gift/point transfers between users
        </div>
        <FieldRow theme={T} label="Min Points per Transaction" value={config.gifting.min_points_per_transaction || 10} onChange={(v) => updateField('gifting', 'min_points_per_transaction', parseInt(v) || 10)} />
        <FieldRow theme={T} label="Max Points per Transaction" value={config.gifting.max_points_per_transaction || 5000} onChange={(v) => updateField('gifting', 'max_points_per_transaction', parseInt(v) || 5000)} />
        <FieldRow theme={T} label="Max Points to One Creator/Day" value={config.gifting.max_points_to_recipient_per_day || 5000} onChange={(v) => updateField('gifting', 'max_points_to_recipient_per_day', parseInt(v) || 5000)} />
        <FieldRow theme={T} label="Max Total Points Sent/Day" value={config.gifting.max_total_points_sent_per_day || 10000} onChange={(v) => updateField('gifting', 'max_total_points_sent_per_day', parseInt(v) || 10000)} />
      </SectionCard>
    </div>
  );
}

// ---------------------------------------------------------------
// Sub-tab: Other Settings
// ---------------------------------------------------------------

function OtherSettingsSubTab({ theme: T, config, updateField }) {
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: 24 }}>
      <SectionCard theme={T} title="Balance Thresholds" icon={<Wallet size={20} color="#3B82F6" />}>
        <FieldRow theme={T} label="Min Balance to Post" value={config.thresholds.min_balance_to_post} onChange={(v) => updateField('thresholds', 'min_balance_to_post', parseInt(v) || 0)} />
        <FieldRow theme={T} label="Min Balance to Join Campaign" value={config.thresholds.min_balance_to_join_campaign} onChange={(v) => updateField('thresholds', 'min_balance_to_join_campaign', parseInt(v) || 0)} />
      </SectionCard>

      <SectionCard theme={T} title="Expiry" icon={<Clock size={20} color="#6B7280" />}>
        <FieldRow theme={T} label="Earned Coins Expire Days (0 = never)" value={config.expiry.earned_coins_expire_days} onChange={(v) => updateField('expiry', 'earned_coins_expire_days', parseInt(v) || 0)} />
      </SectionCard>
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
          { label: 'Pending', value: summary.pending || 0, color: '#8fc441' },
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
// Balance Adjustment Tab
// ---------------------------------------------------------------

function AdjustTab({ theme: T, form, setForm, onSubmit, result, setResult }) {
  const [searchQuery, setSearchQuery] = useState('');
  const [searchType, setSearchType] = useState('both'); // both, id
  const [searching, setSearching] = useState(false);
  const [userData, setUserData] = useState(null);
  const [transactions, setTransactions] = useState([]);
  const [transactionsLoading, setTransactionsLoading] = useState(false);
  const [adjustmentType, setAdjustmentType] = useState('coins'); // coins, points
  const [adjustmentAction, setAdjustmentAction] = useState('add'); // add, subtract

  const searchUser = async () => {
    if (!searchQuery.trim()) {
      setResult && setResult({ type: 'error', message: 'Please enter a search term' });
      return;
    }
    try {
      setSearching(true);
      setUserData(null);
      setTransactions([]);
      console.log('Searching for user:', searchType, searchQuery);
      let user;
      
      if (searchType === 'id') {
        const data = await api.request(`/admin/users/${searchQuery}/`);
        user = data;
      } else {
        // For both phone and username, try phone variants first, then username
        const variants = [
          searchQuery,
          searchQuery.startsWith('0') ? '+251' + searchQuery.substring(1) : searchQuery,
          searchQuery.startsWith('0') ? '251' + searchQuery.substring(1) : searchQuery,
          searchQuery.startsWith('+251') ? searchQuery.substring(4) : searchQuery,
          searchQuery.startsWith('251') ? searchQuery.substring(3) : searchQuery,
        ];
        
        // Try phone number variants
        for (const variant of variants) {
          const data = await api.request(`/admin/users/?search=${variant}`);
          console.log('Search results for variant:', variant, data);
          if (data.users && data.users.length > 0) {
            user = data.users[0];
            break;
          }
        }
        
        // If not found by phone, try username search
        if (!user) {
          const data = await api.request(`/admin/users/?search=${searchQuery}`);
          console.log('Search results by username:', data);
          user = data.users?.[0] || data;
        }
      }
      
      console.log('Found user:', user);
      
      if (user && user.id) {
        setUserData(user);
        setForm({ ...form, user_id: user.id });
        
        // Load user's wallet data using admin endpoint
        try {
          const walletData = await api.request(`/admin/wallet/user/${user.id}/`);
          setUserData(prev => ({ ...prev, wallet: walletData }));
        } catch (walletErr) {
          console.error('Wallet data load failed:', walletErr);
          // Set empty wallet if endpoint doesn't exist
          setUserData(prev => ({ ...prev, wallet: { balance: { total: 0, earned: 0, purchased: 0 }, points: { current: 0 } } }));
        }
        
        // Load recent transactions using admin endpoint
        loadUserTransactions(user.id);
      } else {
        setResult && setResult({ type: 'error', message: 'User not found' });
      }
    } catch (err) {
      console.error('User search failed:', err);
      setResult && setResult({ type: 'error', message: 'User not found' });
    } finally {
      setSearching(false);
    }
  };

  const loadUserTransactions = async (userId) => {
    setTransactionsLoading(true);
    try {
      const txData = await api.request(`/admin/wallet/transactions/?user_id=${userId}&page_size=50`);
      setTransactions(txData.results || []);
    } catch (txErr) {
      console.error('Transaction history load failed:', txErr);
      setTransactions([]);
    } finally {
      setTransactionsLoading(false);
    }
  };

  const handleAdjust = async () => {
    if (!userData) {
      setResult && setResult({ type: 'error', message: 'Please search and select a user first' });
      return;
    }
    
    if (!form.amount || form.amount === '') {
      setResult && setResult({ type: 'error', message: 'Please enter an amount' });
      return;
    }
    
    // Convert amount based on action
    const amount = adjustmentAction === 'subtract' ? -Math.abs(parseFloat(form.amount)) : Math.abs(parseFloat(form.amount));
    
    // Set bucket based on adjustment type
    const bucket = adjustmentType === 'points' ? 'points' : form.bucket;
    
    // Update form with correct bucket and amount
    setForm({ ...form, amount: amount.toString(), bucket });
    
    // Call onSubmit with updated form
    await onSubmit();
    
    // Reload data after adjustment
    if (userData) {
      await loadUserTransactions(userData.id);
      try {
        const walletData = await api.request(`/admin/wallet/user/${userData.id}/`);
        setUserData(prev => ({ ...prev, wallet: walletData }));
      } catch (walletErr) {
        console.error('Wallet data reload failed:', walletErr);
      }
    }
  };

  const getTransactionIcon = (type) => {
    switch (type) {
      case 'credit':
      case 'reward':
      case 'deposit':
        return <ArrowUpFromLine size={16} color="#10B981" />;
      case 'debit':
      case 'withdrawal':
      case 'purchase':
        return <TrendingDown size={16} color="#EF4444" />;
      default:
        return <Clock size={16} color={T.sub} />;
    }
  };

  const formatTransactionType = (type) => {
    return type ? type.charAt(0).toUpperCase() + type.slice(1).replace(/_/g, ' ') : 'Unknown';
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      {/* User Search Section */}
      <SectionCard theme={T} title="User Search" icon={<Search size={20} color="#8B5CF6" />}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          {/* Search Type Tabs */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
            {[
              { id: 'both', label: 'Phone/Username' },
              { id: 'id', label: 'User ID' },
            ].map((type) => (
              <button
                key={type.id}
                onClick={() => setSearchType(type.id)}
                style={{
                  padding: '8px 16px',
                  borderRadius: 8,
                  border: `1px solid ${searchType === type.id ? T.pri : T.border}`,
                  background: searchType === type.id ? `${T.pri}22` : T.bg,
                  color: searchType === type.id ? T.pri : T.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {type.label}
              </button>
            ))}
          </div>

          {/* Search Input */}
          <div style={{ display: 'flex', gap: 8 }}>
            <input
              type={searchType === 'id' ? 'number' : 'text'}
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder={searchType === 'id' ? 'Enter user ID' : 'Enter phone number or username'}
              onKeyPress={(e) => e.key === 'Enter' && searchUser()}
              style={{
                flex: 1,
                padding: '12px 16px',
                borderRadius: 8,
                border: `1px solid ${T.border}`,
                background: T.bg,
                color: T.txt,
                fontSize: 14,
              }}
            />
            <button
              onClick={searchUser}
              disabled={searching}
              style={{
                padding: '12px 20px',
                background: T.pri,
                border: 'none',
                borderRadius: 8,
                color: '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: searching ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}
            >
              {searching ? <Loader size={16} className="spin" /> : <Search size={16} />}
              {searching ? 'Searching...' : 'Search'}
            </button>
          </div>

          {result && (
            <div style={{
              background: result.type === 'success' ? '#D1FAE5' : '#FEE2E2',
              color: result.type === 'success' ? '#065F46' : '#991B1B',
              padding: 12, borderRadius: 8, fontSize: 13,
            }}>
              {result.message}
            </div>
          )}
        </div>
      </SectionCard>

      {/* User Info and Balances */}
      {userData && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 24 }}>
          {/* User Profile Card */}
          <SectionCard theme={T} title="User Profile" icon={<User size={20} color="#8B5CF6" />}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                {userData.profile_photo ? (
                  <img
                    src={userData.profile_photo}
                    alt={userData.username}
                    style={{ width: 64, height: 64, borderRadius: '50%', objectFit: 'cover' }}
                  />
                ) : (
                  <div style={{
                    width: 64, height: 64, borderRadius: '50%',
                    background: T.pri, display: 'flex', alignItems: 'center', justifyContent: 'center',
                    color: '#fff', fontSize: 24, fontWeight: 700,
                  }}>
                    {userData.username?.[0]?.toUpperCase() || 'U'}
                  </div>
                )}
                <div>
                  <div style={{ fontSize: 18, fontWeight: 700, color: T.txt, marginBottom: 4 }}>
                    {userData.username || 'Unknown'}
                  </div>
                  <div style={{ fontSize: 13, color: T.sub, marginBottom: 2 }}>
                    ID: {userData.id}
                  </div>
                  {userData.phone && (
                    <div style={{ fontSize: 13, color: T.sub }}>
                      {userData.phone}
                    </div>
                  )}
                </div>
              </div>

              {userData.wallet && (
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  <div style={{ padding: 12, background: T.card, borderRadius: 8, border: `1px solid ${T.border}` }}>
                    <div style={{ fontSize: 12, color: T.sub, marginBottom: 8 }}>Coin Balances</div>
                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 8 }}>
                      <div>
                        <div style={{ fontSize: 11, color: T.sub }}>Total</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: T.txt }}>
                          {userData.wallet.balance?.total || 0}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: T.sub }}>Earned</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: '#10B981' }}>
                          {userData.wallet.balance?.earned || 0}
                        </div>
                      </div>
                      <div>
                        <div style={{ fontSize: 11, color: T.sub }}>Purchased</div>
                        <div style={{ fontSize: 16, fontWeight: 700, color: '#3B82F6' }}>
                          {userData.wallet.balance?.purchased || 0}
                        </div>
                      </div>
                    </div>
                  </div>

                  <div style={{ padding: 12, background: T.card, borderRadius: 8, border: `1px solid ${T.border}` }}>
                    <div style={{ fontSize: 12, color: T.sub, marginBottom: 8 }}>Points Balance</div>
                    <div style={{ fontSize: 20, fontWeight: 700, color: T.txt }}>
                      {userData.wallet.points?.current || 0}
                    </div>
                  </div>
                </div>
              )}
            </div>
          </SectionCard>

          {/* Balance Adjustment Form */}
          <SectionCard theme={T} title="Balance Adjustment" icon={<Wallet size={20} color="#8B5CF6" />}>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
              {/* Balance Type Selection */}
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setAdjustmentType('coins')}
                  style={{
                    flex: 1,
                    padding: '12px 16px',
                    background: adjustmentType === 'coins' ? T.pri : T.bg,
                    border: adjustmentType === 'coins' ? 'none' : `1px solid ${T.border}`,
                    borderRadius: 8,
                    color: adjustmentType === 'coins' ? '#fff' : T.txt,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <Coins size={16} />
                  Coins
                </button>
                <button
                  onClick={() => setAdjustmentType('points')}
                  style={{
                    flex: 1,
                    padding: '12px 16px',
                    background: adjustmentType === 'points' ? T.pri : T.bg,
                    border: adjustmentType === 'points' ? 'none' : `1px solid ${T.border}`,
                    borderRadius: 8,
                    color: adjustmentType === 'points' ? '#fff' : T.txt,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <Trophy size={16} />
                  Points
                </button>
              </div>

              {/* Add/Subtract Selection */}
              <div style={{ display: 'flex', gap: 8 }}>
                <button
                  onClick={() => setAdjustmentAction('add')}
                  style={{
                    flex: 1,
                    padding: '12px 16px',
                    background: adjustmentAction === 'add' ? '#10B981' : T.bg,
                    border: adjustmentAction === 'add' ? 'none' : `1px solid ${T.border}`,
                    borderRadius: 8,
                    color: adjustmentAction === 'add' ? '#fff' : T.txt,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <TrendingUp size={16} />
                  Add
                </button>
                <button
                  onClick={() => setAdjustmentAction('subtract')}
                  style={{
                    flex: 1,
                    padding: '12px 16px',
                    background: adjustmentAction === 'subtract' ? '#EF4444' : T.bg,
                    border: adjustmentAction === 'subtract' ? 'none' : `1px solid ${T.border}`,
                    borderRadius: 8,
                    color: adjustmentAction === 'subtract' ? '#fff' : T.txt,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: 8,
                  }}
                >
                  <TrendingDown size={16} />
                  Subtract
                </button>
              </div>

              {/* Amount Input */}
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 8 }}>
                  Amount
                </label>
                <input
                  type="number"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  placeholder="Enter amount"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    background: T.bg,
                    color: T.txt,
                    fontSize: 14,
                  }}
                />
              </div>

              {/* Bucket Selection for Coins */}
              {adjustmentType === 'coins' && (
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 8 }}>
                    Balance Bucket
                  </label>
                  <select
                    value={form.bucket}
                    onChange={(e) => setForm({ ...form, bucket: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '12px 16px',
                      borderRadius: 8,
                      border: `1px solid ${T.border}`,
                      background: T.bg,
                      color: T.txt,
                      fontSize: 14,
                    }}
                  >
                    <option value="earned">Earned Balance</option>
                    <option value="purchased">Purchased Balance</option>
                  </select>
                </div>
              )}

              {/* Reason Input */}
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: T.sub, marginBottom: 8 }}>
                  Reason for Adjustment
                </label>
                <input
                  type="text"
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  placeholder="Enter reason (e.g., Refund, Bonus, Correction)"
                  style={{
                    width: '100%',
                    padding: '12px 16px',
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                    background: T.bg,
                    color: T.txt,
                    fontSize: 14,
                  }}
                />
              </div>

              {/* Submit Button */}
              <button
                onClick={handleAdjust}
                style={{
                  width: '100%',
                  padding: '14px 20px',
                  background: T.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 15,
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Save size={18} />
                {adjustmentAction === 'add' ? 'Add' : 'Subtract'} {adjustmentType}
              </button>
            </div>
          </SectionCard>
        </div>
      )}

      {/* Transaction History */}
      {userData && (
        <SectionCard theme={T} title="Transaction History" icon={<Clock size={20} color="#8B5CF6" />}>
          {transactionsLoading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 40, color: T.sub }}>
              <Loader size={24} className="spin" style={{ marginRight: 8 }} />
              Loading transactions...
            </div>
          ) : transactions.length === 0 ? (
            <div style={{ padding: 40, textAlign: 'center', color: T.sub }}>
              No transactions found
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {transactions.map((tx, index) => (
                <div
                  key={tx.id || index}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: 12,
                    background: T.card,
                    borderRadius: 8,
                    border: `1px solid ${T.border}`,
                  }}
                >
                  <div style={{
                    width: 36, height: 36, borderRadius: '50%',
                    background: tx.type === 'credit' || tx.type === 'reward' ? '#D1FAE5' : '#FEE2E2',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    {getTransactionIcon(tx.type)}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: T.txt, marginBottom: 2 }}>
                      {formatTransactionType(tx.type)}
                    </div>
                    <div style={{ fontSize: 12, color: T.sub }}>
                      {tx.description || tx.reason || 'No description'}
                    </div>
                  </div>
                  <div style={{ textAlign: 'right' }}>
                    <div style={{
                      fontSize: 14, fontWeight: 700,
                      color: tx.type === 'credit' || tx.type === 'reward' ? '#10B981' : '#EF4444',
                      marginBottom: 2,
                    }}>
                      {tx.type === 'credit' || tx.type === 'reward' ? '+' : '-'}{tx.amount || 0}
                    </div>
                    <div style={{ fontSize: 11, color: T.sub }}>
                      {tx.created_at ? new Date(tx.created_at).toLocaleDateString() : 'N/A'}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      )}

      {/* Warning Message */}
      <div style={{ padding: 16, background: '#FEF3C7', borderRadius: 8, fontSize: 12, color: '#92400E', display: 'flex', alignItems: 'center', gap: 8 }}>
        <AlertTriangle size={16} />
        <strong>Warning:</strong> Manual balance adjustments are logged as admin transactions. Use this feature responsibly and only for legitimate corrections.
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
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 8 }}>
      <span style={{ fontSize: 13, color: theme.txt, minWidth: 140, fontWeight: 500 }}>{label}</span>
      <input
        type={type}
        value={value !== undefined && value !== null ? value : ''}
        onChange={(e) => onChange(e.target.value)}
        placeholder="0"
        style={{
          flex: 1, padding: '10px 12px', borderRadius: 6, border: `1px solid ${theme.border}`,
          background: theme.card, color: theme.txt, fontSize: 14, fontWeight: 500,
          outline: 'none', transition: 'border-color 0.2s',
        }}
        onFocus={(e) => e.target.style.borderColor = theme.pri}
        onBlur={(e) => e.target.style.borderColor = theme.border}
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
  pending: { color: '#8fc441', icon: Clock },
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




