import { useState, useEffect } from 'react';
import api from '../../api';

// Helper Components - MUST be defined before use
function Section({ theme, icon, title, color, children }) {
  return (
    <div style={{ marginBottom: 24 }}>
      <h3 style={{ fontSize: 14, fontWeight: 600, color: color || theme.txt, marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8, paddingBottom: 8, borderBottom: `1px solid ${theme.border}` }}>
        <span>{icon}</span> {title}
      </h3>
      {children}
    </div>
  );
}

function NumberInput({ label, value, onChange, suffix, step = '0.1', theme }) {
  return (
    <div>
      <label style={{ display: 'block', fontSize: 12, fontWeight: 500, color: theme.sub, marginBottom: 6 }}>{label}</label>
      <div style={{ position: 'relative' }}>
        <input
          type="number"
          value={value || 0}
          onChange={(e) => onChange(e.target.value)}
          step={step}
          style={{ width: '100%', padding: '10px 12px', paddingRight: 45, border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 14, color: theme.txt, background: 'rgba(255,255,255,0.06)', outline: 'none', boxSizing: 'border-box' }}
        />
        <span style={{ position: 'absolute', right: 12, top: '50%', transform: 'translateY(-50%)', fontSize: 12, color: theme.sub }}>{suffix}</span>
      </div>
    </div>
  );
}

function getTypeIcon(type) {
  const icons = { daily: '☀️', weekly: '📅', monthly: '📆', grand: '👑' };
  return icons[type] || '🎯';
}

function getTypeDescription(type) {
  const desc = {
    daily: 'Lightweight & gamified. Top scorer selection. No voting.',
    weekly: 'Cumulative & competitive. Streak bonuses + decay. Top scorers only. No randomness.',
    monthly: 'Deep weighting with multipliers. Weekly winner bonuses. Top performers only.',
    grand: 'Two-phase: Qualification scoring → Final judging + public voting (70/30 split).'
  };
  return desc[type] || '';
}

// Daily Campaign Config Component
function DailyConfig({ config, updateField, updateSimple, theme }) {
  if (!config) return null;
  return (
    <div style={{ background: theme.card, borderRadius: 16, padding: 24 }}>
      <Section theme={theme} icon="🏆" title="Winner Selection" color="#10B981">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Daily campaigns use top scorer selection. No voting allowed.
        </p>
      </Section>

      <Section theme={theme} icon="🚫" title="Win Protection" color="#EF4444">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Prevent the same users from winning too frequently.
        </p>
        <NumberInput label="Win Cooldown Period" value={config?.win_cooldown_days} onChange={v => updateSimple('win_cooldown_days', v)} suffix="days" theme={theme} />
      </Section>

      <Section theme={theme} icon="❤️" title="Engagement Points (Per Action)" color="#3B82F6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points awarded for each like, comment, share, and unique gifter on campaign posts.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
          <NumberInput label="Likes" value={config?.engagement?.likes_weight} onChange={v => updateField('engagement', 'likes_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Comments" value={config?.engagement?.comments_weight} onChange={v => updateField('engagement', 'comments_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Shares" value={config?.engagement?.shares_weight} onChange={v => updateField('engagement', 'shares_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Gifts" value={config?.engagement?.gifts_weight} onChange={v => updateField('engagement', 'gifts_weight', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="🎮" title="Gamification Points" color="#8B5CF6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points from app activities: daily spin, receiving coin gifts, login bonuses.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <NumberInput label="Daily Spin Reward" value={config?.gamification?.spin_reward} onChange={v => updateField('gamification', 'spin_reward', v)} suffix="pts" theme={theme} />
          <NumberInput label="Coin Gift Received" value={config?.gamification?.coin_gift} onChange={v => updateField('gamification', 'coin_gift', v)} suffix="pts" theme={theme} />
          <NumberInput label="Login Bonus" value={config?.gamification?.login_bonus} onChange={v => updateField('gamification', 'login_bonus', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="📅" title="Daily Consistency" color="#8fc441">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points for posting content on any given day of the campaign.
        </p>
        <NumberInput label="Points for Daily Post" value={config?.consistency?.daily_post_points} onChange={v => updateField('consistency', 'daily_post_points', v)} suffix="pts" theme={theme} />
      </Section>
    </div>
  );
}

// Weekly Campaign Config Component
function WeeklyConfig({ config, updateField, updateSimple, theme }) {
  if (!config) return null;
  return (
    <div style={{ background: theme.card, borderRadius: 16, padding: 24 }}>
      <Section theme={theme} icon="🏆" title="Winner Selection (Pure Scoring)" color="#10B981">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Weekly campaigns use ONLY top scorers. No randomness. No voting.
        </p>
        <div style={{ padding: 16, background: '#10B98115', borderRadius: 8, borderLeft: '4px solid #10B981' }}>
          <strong style={{ color: '#10B981' }}>Rule:</strong> Users can only win once per weekly cycle. If they already won, they're excluded from future wins even if they rank high.
        </div>
      </Section>

      <Section theme={theme} icon="❤️" title="Engagement Points (Cumulative)" color="#3B82F6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Total engagement points aggregated across the entire week (likes, comments, shares, and unique gifters).
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
          <NumberInput label="Likes" value={config?.engagement?.likes_weight} onChange={v => updateField('engagement', 'likes_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Comments" value={config?.engagement?.comments_weight} onChange={v => updateField('engagement', 'comments_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Shares" value={config?.engagement?.shares_weight} onChange={v => updateField('engagement', 'shares_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Gifts" value={config?.engagement?.gifts_weight} onChange={v => updateField('engagement', 'gifts_weight', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="🎮" title="Gamification Points" color="#8B5CF6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points from spins, coin gifts, and daily participation.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <NumberInput label="Spin Reward" value={config?.gamification?.spin_reward} onChange={v => updateField('gamification', 'spin_reward', v)} suffix="pts" theme={theme} />
          <NumberInput label="Coin Gift" value={config?.gamification?.coin_gift} onChange={v => updateField('gamification', 'coin_gift', v)} suffix="pts" theme={theme} />
          <NumberInput label="Daily Participation" value={config?.gamification?.consistency_boost} onChange={v => updateField('gamification', 'consistency_boost', v)} suffix="pts/day" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="🔥" title="Streak Bonuses" color="#8fc441">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Bonus points for consecutive posting days. Full week = max bonus!
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <NumberInput label="3-Day Streak" value={config?.streak_bonuses?.['3_day']} onChange={v => updateField('streak_bonuses', '3_day', v)} suffix="pts" theme={theme} />
          <NumberInput label="5-Day Streak" value={config?.streak_bonuses?.['5_day']} onChange={v => updateField('streak_bonuses', '5_day', v)} suffix="pts" theme={theme} />
          <NumberInput label="7-Day Streak (Full Week)" value={config?.streak_bonuses?.['7_day']} onChange={v => updateField('streak_bonuses', '7_day', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="📉" title="Decay System" color="#EF4444">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points deducted for days the user didn't post (up to max days).
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          <NumberInput label="Penalty per Missed Day" value={config?.decay?.per_missed_day} onChange={v => updateField('decay', 'per_missed_day', v)} suffix="pts" theme={theme} />
          <NumberInput label="Max Days for Decay" value={config?.decay?.max_days} onChange={v => updateField('decay', 'max_days', v)} suffix="days" theme={theme} />
        </div>
      </Section>
    </div>
  );
}

// Monthly Campaign Config Component
function MonthlyConfig({ config, updateField, updateSimple, theme }) {
  if (!config) return null;
  return (
    <div style={{ background: theme.card, borderRadius: 16, padding: 24 }}>
      <Section theme={theme} icon="🏆" title="Winner Selection" color="#10B981">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Monthly campaigns use weighted scoring with multipliers. Top performers only.
        </p>
        <NumberInput label="Number of Winners" value={config?.winner_count} onChange={v => updateSimple('winner_count', v)} suffix="winners" theme={theme} />
      </Section>

      <Section theme={theme} icon="❤️" title="Engagement Points" color="#3B82F6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Points per engagement action (likes, comments, shares, unique gifters), aggregated across the entire month.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(160px, 1fr))', gap: 16 }}>
          <NumberInput label="Likes" value={config?.engagement?.likes_weight} onChange={v => updateField('engagement', 'likes_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Comments" value={config?.engagement?.comments_weight} onChange={v => updateField('engagement', 'comments_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Shares" value={config?.engagement?.shares_weight} onChange={v => updateField('engagement', 'shares_weight', v)} suffix="pts" theme={theme} />
          <NumberInput label="Gifts" value={config?.engagement?.gifts_weight} onChange={v => updateField('engagement', 'gifts_weight', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="🎁" title="Weekly Winner Bonus" color="#8B5CF6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Extra points awarded to users who won weekly campaigns during this month.
        </p>
        <NumberInput label="Bonus per Weekly Win" value={config?.weekly_winner_bonus} onChange={v => updateSimple('weekly_winner_bonus', v)} suffix="pts" theme={theme} />
      </Section>

      <Section theme={theme} icon="⚡" title="Streak Multipliers (Applied to Total)" color="#8B5CF6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Multipliers applied to final score based on longest posting streak in the month.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 16 }}>
          <NumberInput label="7-Day Streak" value={config?.streak_multipliers?.['7_day']} onChange={v => updateField('streak_multipliers', '7_day', v)} suffix="x" step="0.1" theme={theme} />
          <NumberInput label="14-Day Streake" value={config?.streak_multipliers?.['14_day']} onChange={v => updateField('streak_multipliers', '14_day', v)} suffix="x" step="0.1" theme={theme} />
          <NumberInput label="21-Day Streak" value={config?.streak_multipliers?.['21_day']} onChange={v => updateField('streak_multipliers', '21_day', v)} suffix="x" step="0.1" theme={theme} />
        </div>
      </Section>
    </div>
  );
}

// Grand Campaign Config Component
function GrandConfig({ config, updateField, updateSimple, theme }) {
  if (!config) return null;
  return (
    <div style={{ background: theme.card, borderRadius: 16, padding: 24 }}>
      <Section theme={theme} icon="👑" title="Two-Phase System" color="#10B981">
        <div style={{ display: 'grid', gap: 16 }}>
          <div style={{ padding: 16, background: '#10B98115', borderRadius: 8, borderLeft: '4px solid #10B981' }}>
            <strong style={{ color: '#10B981' }}>Phase 1: Qualification</strong>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: theme.sub }}>
              Top users from ALL monthly campaigns qualify. Weighted scoring determines finalists.
            </p>
          </div>
          <div style={{ padding: 16, background: '#8B5CF615', borderRadius: 8, borderLeft: '4px solid #8B5CF6' }}>
            <strong style={{ color: '#8B5CF6' }}>Phase 2: Final Judging</strong>
            <p style={{ margin: '4px 0 0 0', fontSize: 13, color: theme.sub }}>
              70% Judge Panel Score + 30% Public Vote = Final Winner
            </p>
          </div>
        </div>
      </Section>

      <Section theme={theme} icon="📊" title="Qualification Scoring" color="#3B82F6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          How monthly performance translates to Grand qualification points.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          <NumberInput label="1st Place Monthly" value={config?.qualification_points?.first_place} onChange={v => updateField('qualification_points', 'first_place', v)} suffix="pts" theme={theme} />
          <NumberInput label="2nd Place Monthly" value={config?.qualification_points?.second_place} onChange={v => updateField('qualification_points', 'second_place', v)} suffix="pts" theme={theme} />
          <NumberInput label="3rd Place Monthly" value={config?.qualification_points?.third_place} onChange={v => updateField('qualification_points', 'third_place', v)} suffix="pts" theme={theme} />
          <NumberInput label="Top 10 Finish" value={config?.qualification_points?.top_ten} onChange={v => updateField('qualification_points', 'top_ten', v)} suffix="pts" theme={theme} />
        </div>
      </Section>

      <Section theme={theme} icon="⚖️" title="Final Score Weights" color="#8B5CF6">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          How the final winner is determined.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          <NumberInput label="Judge Panel Score" value={config?.final_weights?.judge_score} onChange={v => updateField('final_weights', 'judge_score', v)} suffix="%" theme={theme} />
          <NumberInput label="Public Vote" value={config?.final_weights?.public_vote} onChange={v => updateField('final_weights', 'public_vote', v)} suffix="%" theme={theme} />
        </div>
        <p style={{ fontSize: 12, color: theme.sub, marginTop: 12 }}>
          Note: Judge + Public must equal 100%
        </p>
      </Section>

      <Section theme={theme} icon="🗳️" title="Voting Phase" color="#8fc441">
        <p style={{ fontSize: 13, color: theme.sub, marginBottom: 16 }}>
          Configure the public voting period.
        </p>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 16 }}>
          <NumberInput label="Voting Duration" value={config?.voting_duration_days} onChange={v => updateSimple('voting_duration_days', v)} suffix="days" theme={theme} />
          <NumberInput label="Votes per User" value={config?.max_votes_per_user} onChange={v => updateSimple('max_votes_per_user', v)} suffix="votes" theme={theme} />
        </div>
      </Section>
    </div>
  );
}

// Main Component
export function CampaignScoringConfigPage({ campaignId, campaignType, onBack, theme }) {
  const [config, setConfig] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState(null);

  useEffect(() => {
    loadConfig();
  }, [campaignId]);

  const loadConfig = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/admin/campaigns/${campaignId}/scoring-config/`);
      setConfig(response);
    } catch (error) {
      console.error('Failed to load scoring config:', error);
      setMessage({ msg_type: 'error', text: 'Failed to load configuration' });
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      const payload = { [campaignType]: config[campaignType] };
      await api.request(`/admin/campaigns/${campaignId}/scoring-config/update/`, {
        method: 'PUT',
        body: JSON.stringify(payload)
      });
      setMessage({ msg_type: 'success', text: 'Configuration saved' });
      setTimeout(() => setMessage(null), 3000);
    } catch (error) {
      console.error('Failed to save:', error);
      setMessage({ msg_type: 'error', text: 'Failed to save' });
    } finally {
      setSaving(false);
    }
  };

  const updateField = (section, field, value) => {
    setConfig(prev => ({
      ...prev,
      [campaignType]: {
        ...prev[campaignType],
        [section]: {
          ...prev[campaignType]?.[section],
          [field]: parseFloat(value) || 0
        }
      }
    }));
  };

  const updateSimple = (field, value) => {
    setConfig(prev => ({
      ...prev,
      [campaignType]: {
        ...prev[campaignType],
        [field]: field.includes('percentage') || field.includes('threshold') || field.includes('days') || field.includes('count')
          ? parseInt(value) || 0 
          : parseFloat(value) || 0
      }
    }));
  };

  if (loading) return <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>Loading...</div>;
  if (!config) return null;

  const typeConfig = config[campaignType];

  return (
    <div>
      <div style={{ marginBottom: 32 }}>
        <button onClick={onBack} style={{ padding: '8px 16px', borderRadius: 6, border: `1px solid ${theme.border}`, background: 'rgba(255,255,255,0.06)', color: theme.txt, cursor: 'pointer', marginBottom: 16 }}>
          ← Back to Campaign
        </button>
        <h1 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: theme.txt }}>
          {getTypeIcon(campaignType)} {campaignType.toUpperCase()} Campaign Scoring
        </h1>
        <p style={{ margin: '8px 0 0 0', fontSize: 14, color: theme.sub }}>
          {getTypeDescription(campaignType)}
        </p>
      </div>

      {message && (
        <div style={{
          padding: 12, borderRadius: 8, marginBottom: 20,
          background: message.msg_type === 'success' ? theme.green + '15' : theme.red + '15',
          border: `1px solid ${message.msg_type === 'success' ? theme.green : theme.red}`,
          color: message.msg_type === 'success' ? theme.green : theme.red
        }}>
          {message.text}
        </div>
      )}

      {campaignType === 'daily' && (
        <DailyConfig config={typeConfig} updateField={updateField} updateSimple={updateSimple} theme={theme} />
      )}
      {campaignType === 'weekly' && (
        <WeeklyConfig config={typeConfig} updateField={updateField} updateSimple={updateSimple} theme={theme} />
      )}
      {campaignType === 'monthly' && (
        <MonthlyConfig config={typeConfig} updateField={updateField} updateSimple={updateSimple} theme={theme} />
      )}
      {campaignType === 'grand' && (
        <GrandConfig config={typeConfig} updateField={updateField} updateSimple={updateSimple} theme={theme} />
      )}

      <div style={{ display: 'flex', gap: 12, marginTop: 32, justifyContent: 'flex-end' }}>
        <button onClick={loadConfig} style={{ padding: '12px 24px', borderRadius: 8, border: `1px solid ${theme.border}`, background: 'rgba(255,255,255,0.06)', color: theme.txt, cursor: 'pointer' }}>
          Reset
        </button>
        <button onClick={handleSave} disabled={saving} style={{ padding: '12px 24px', borderRadius: 8, border: 'none', background: theme.pri, color: 'white', fontWeight: 600, cursor: saving ? 'not-allowed' : 'pointer', opacity: saving ? 0.6 : 1 }}>
          {saving ? 'Saving...' : 'Save Configuration'}
        </button>
      </div>
    </div>
  );
}

// Export alias
export const TypeSpecificScoringConfig = CampaignScoringConfigPage;




