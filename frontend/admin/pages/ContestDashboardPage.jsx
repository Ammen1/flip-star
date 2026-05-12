import { useState, useEffect } from 'react';
import { Trophy, Coins, Users, TrendingUp, AlertTriangle, Zap, Calendar, Wallet, Award, Phone, Shield } from 'lucide-react';
import api from '../../api';
import { adminTheme } from '../theme';

export function ContestDashboardPage({ theme }) {
  const [contestData, setContestData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [flashActive, setFlashActive] = useState(false);
  const [flashMultiplier, setFlashMultiplier] = useState(1.5);

  useEffect(() => {
    loadContestData();
  }, []);

  const loadContestData = async () => {
    try {
      const response = await api.request('/admin/contest/dashboard/');
      setContestData(response);
      setFlashActive(response?.is_flash_hour || false);
      setLoading(false);
    } catch (error) {
      console.error('Failed to load contest data:', error);
      setLoading(false);
    }
  };

  const toggleFlash = async () => {
    try {
      const response = await api.request('/admin/contest/flash-toggle/', {
        method: 'POST',
        body: JSON.stringify({
          active: !flashActive,
          multiplier: flashMultiplier,
          start_time: '18:00',
          end_time: '20:00',
        }),
      });
      setFlashActive(response.flash_active);
      loadContestData();
    } catch (error) {
      console.error('Failed to toggle flash:', error);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: adminTheme.spacing['3xl'], color: adminTheme.colors.textPrimary, fontSize: adminTheme.typography.fontSize.base }}>
        Loading contest dashboard...
      </div>
    );
  }

  const budget = contestData?.budget || {};
  const stats = contestData?.stats || {};
  const daysRemaining = contestData?.days_remaining || 0;

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: adminTheme.spacing['2xl'] }}>
        <h1 style={{ margin: 0, fontSize: adminTheme.typography.fontSize['4xl'], fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary, marginBottom: adminTheme.spacing.sm }}>
          90-Day Contest Dashboard
        </h1>
        <p style={{ margin: 0, fontSize: adminTheme.typography.fontSize.lg, color: adminTheme.colors.textSecondary }}>
          {contestData?.contest_name || 'Contest Management'}
        </p>
      </div>

      {/* Countdown & Flash Challenge */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: adminTheme.spacing['2xl'],
        marginBottom: adminTheme.spacing['2xl'],
      }}>
        {/* Days Remaining */}
        <div style={{
          background: adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.xl,
          padding: adminTheme.spacing['2xl'],
          border: `1px solid ${adminTheme.colors.border}`,
          boxShadow: adminTheme.shadows.sm,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: adminTheme.spacing.md, marginBottom: adminTheme.spacing.lg }}>
            <Calendar size={24} color={adminTheme.colors.primary} />
            <span style={{ fontSize: adminTheme.typography.fontSize.base, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textSecondary }}>Contest Timeline</span>
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize['4xl'], fontWeight: adminTheme.typography.fontWeight.bold, color: adminTheme.colors.primary }}>
            {daysRemaining}
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize.base, color: adminTheme.colors.textSecondary }}>Days Remaining</div>
        </div>

        {/* Flash Challenge Toggle */}
        <div style={{
          background: flashActive ? adminTheme.colors.warning + '15' : adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.xl,
          padding: adminTheme.spacing['2xl'],
          border: `2px solid ${flashActive ? adminTheme.colors.warning : adminTheme.colors.border}`,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: adminTheme.spacing.md, marginBottom: adminTheme.spacing.lg }}>
            <Zap size={24} color={flashActive ? adminTheme.colors.warning : adminTheme.colors.textSecondary} />
            <span style={{ fontSize: adminTheme.typography.fontSize.base, fontWeight: adminTheme.typography.fontWeight.semibold, color: flashActive ? adminTheme.colors.warning : adminTheme.colors.textSecondary }}>
              Flash Challenge
            </span>
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize.xl, fontWeight: adminTheme.typography.fontWeight.semibold, color: flashActive ? adminTheme.colors.warning : adminTheme.colors.textPrimary, marginBottom: adminTheme.spacing.sm }}>
            {flashActive ? 'ACTIVE' : 'Inactive'}
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize.base, color: adminTheme.colors.textSecondary, marginBottom: adminTheme.spacing.lg }}>
            {flashActive ? `${flashMultiplier}x Multiplier` : 'Toggle for Happy Hour'}
          </div>
          <button
            onClick={toggleFlash}
            style={{
              padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.xl}`,
              background: flashActive ? adminTheme.colors.error : adminTheme.colors.success,
              border: 'none',
              borderRadius: adminTheme.borderRadius.md,
              color: adminTheme.colors.textLight,
              fontSize: adminTheme.typography.fontSize.base,
              fontWeight: adminTheme.typography.fontWeight.semibold,
              cursor: 'pointer',
              transition: `all ${adminTheme.transitions.base}`,
            }}
          >
            {flashActive ? 'End Flash' : 'Start Flash'}
          </button>
        </div>

        {/* Total Budget */}
        <div style={{
          background: adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.xl,
          padding: adminTheme.spacing['2xl'],
          border: `1px solid ${adminTheme.colors.border}`,
          boxShadow: adminTheme.shadows.sm,
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: adminTheme.spacing.md, marginBottom: adminTheme.spacing.lg }}>
            <Wallet size={24} color={adminTheme.colors.success} />
            <span style={{ fontSize: adminTheme.typography.fontSize.base, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textSecondary }}>Total Budget</span>
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize['3xl'], fontWeight: adminTheme.typography.fontWeight.bold, color: adminTheme.colors.success }}>
            {budget.total?.toLocaleString()} ETB
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize.base, color: adminTheme.colors.textSecondary }}>
            Remaining: {budget.remaining?.toLocaleString()} ETB
          </div>
        </div>
      </div>

      {/* Budget Breakdown */}
      <div style={{
        background: adminTheme.colors.card,
        borderRadius: adminTheme.borderRadius.xl,
        padding: adminTheme.spacing['2xl'],
        border: `1px solid ${adminTheme.colors.border}`,
        marginBottom: adminTheme.spacing['2xl'],
      }}>
        <h3 style={{ margin: 0, fontSize: adminTheme.typography.fontSize.xl, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary, marginBottom: adminTheme.spacing.xl }}>
          Budget Allocation & Spending
        </h3>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: adminTheme.spacing.lg,
        }}>
          {[
            { name: 'Daily', allocated: budget.allocated?.daily, spent: budget.spent?.daily, percent: 30 },
            { name: 'Weekly', allocated: budget.allocated?.weekly, spent: budget.spent?.weekly, percent: 25 },
            { name: 'Monthly', allocated: budget.allocated?.monthly, spent: budget.spent?.monthly, percent: 25 },
            { name: 'Grand Finale', allocated: budget.allocated?.grand, spent: budget.spent?.grand, percent: 20 },
          ].map((item) => (
            <div key={item.name} style={{
              padding: adminTheme.spacing.lg,
              background: adminTheme.colors.background,
              borderRadius: adminTheme.borderRadius.lg,
            }}>
              <div style={{ fontSize: adminTheme.typography.fontSize.xs, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textSecondary, marginBottom: adminTheme.spacing.sm }}>
                {item.name} ({item.percent}%)
              </div>
              <div style={{ fontSize: adminTheme.typography.fontSize.lg, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary, marginBottom: adminTheme.spacing.xs }}>
                {item.allocated?.toLocaleString()} ETB
              </div>
              <div style={{ fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary }}>
                Spent: {item.spent?.toLocaleString()} ETB
              </div>
              {/* Progress bar */}
              <div style={{
                marginTop: adminTheme.spacing.sm,
                height: 6,
                background: adminTheme.colors.border,
                borderRadius: adminTheme.borderRadius.sm,
                overflow: 'hidden',
              }}>
                <div style={{
                  width: `${(item.spent / item.allocated * 100) || 0}%`,
                  height: '100%',
                  background: (item.spent / item.allocated) > 0.8 ? adminTheme.colors.error : adminTheme.colors.primary,
                  borderRadius: adminTheme.borderRadius.sm,
                }} />
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Stats Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: adminTheme.spacing.lg,
        marginBottom: adminTheme.spacing['2xl'],
      }}>
        {[
          { icon: Users, label: 'Participants', value: stats.total_participants, color: adminTheme.colors.info },
          { icon: Trophy, label: 'Total Posts', value: stats.total_posts, color: adminTheme.colors.primary },
          { icon: Coins, label: 'Coins Distributed', value: stats.total_coins_distributed?.toLocaleString(), color: adminTheme.colors.success },
          { icon: Award, label: 'Active Tiers', value: '4', color: adminTheme.colors.warning },
        ].map((stat) => (
          <div key={stat.label} style={{
            background: adminTheme.colors.card,
            borderRadius: adminTheme.borderRadius.lg,
            padding: adminTheme.spacing.xl,
            border: `1px solid ${adminTheme.colors.border}`,
            display: 'flex',
            alignItems: 'center',
            gap: adminTheme.spacing.lg,
            boxShadow: adminTheme.shadows.sm,
          }}>
            <div style={{
              width: 48,
              height: 48,
              borderRadius: adminTheme.borderRadius.lg,
              background: stat.color + '15',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              <stat.icon size={24} color={stat.color} />
            </div>
            <div>
              <div style={{ fontSize: adminTheme.typography.fontSize.xl, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary }}>
                {stat.value || 0}
              </div>
              <div style={{ fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary }}>{stat.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Quick Actions */}
      <div style={{
        display: 'flex',
        gap: adminTheme.spacing.md,
        flexWrap: 'wrap',
      }}>
        <button style={{
          padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.xl}`,
          background: adminTheme.colors.primary,
          border: 'none',
          borderRadius: adminTheme.borderRadius.md,
          color: adminTheme.colors.textLight,
          fontSize: adminTheme.typography.fontSize.base,
          fontWeight: adminTheme.typography.fontWeight.semibold,
          cursor: 'pointer',
          transition: `all ${adminTheme.transitions.base}`,
        }}>
          View Judging Portal
        </button>
        <button style={{
          padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.xl}`,
          background: adminTheme.colors.card,
          border: `2px solid ${adminTheme.colors.border}`,
          borderRadius: adminTheme.borderRadius.md,
          color: adminTheme.colors.textPrimary,
          fontSize: adminTheme.typography.fontSize.base,
          fontWeight: adminTheme.typography.fontWeight.semibold,
          cursor: 'pointer',
          transition: `all ${adminTheme.transitions.base}`,
        }}>
          Anti-Cheat Review
        </button>
        <button style={{
          padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.xl}`,
          background: adminTheme.colors.card,
          border: `2px solid ${adminTheme.colors.border}`,
          borderRadius: adminTheme.borderRadius.md,
          color: adminTheme.colors.textPrimary,
          fontSize: adminTheme.typography.fontSize.base,
          fontWeight: adminTheme.typography.fontWeight.semibold,
          cursor: 'pointer',
          transition: `all ${adminTheme.transitions.base}`,
        }}>
          Leaderboard Settings
        </button>
      </div>
    </div>
  );
}




