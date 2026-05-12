import { useState, useEffect } from 'react';
import { X, Settings, Calendar, TrendingUp, Award } from 'lucide-react';
import api from '../../api';
import { adminTheme } from '../theme';

export function GenerationConfigModal({ campaign, onClose, onSave, theme }) {
  // Calculate smart defaults based on campaign duration
  const getSmartDefaults = () => {
    if (!campaign?.start_date || !campaign?.end_date) {
      return { daily: 0, weekly: 0, monthly: 0, grand: 1 };
    }
    
    const start = new Date(campaign.start_date);
    const end = new Date(campaign.end_date);
    const diffDays = Math.ceil((end - start) / (1000 * 60 * 60 * 24)) + 1;
    
    // Smart defaults based on duration
    let daily = 0, weekly = 0, monthly = 0;
    
    if (diffDays <= 7) {
      // 1 week or less: all daily
      daily = diffDays;
      weekly = 0;
      monthly = 0;
    } else if (diffDays <= 30) {
      // 1 month or less: some daily + weekly
      daily = Math.min(10, diffDays); // Max 10 daily
      weekly = Math.floor(diffDays / 7);
      monthly = 0;
    } else if (diffDays <= 90) {
      // 3 months or less: weekly + monthly
      daily = 0;
      weekly = Math.floor(diffDays / 7);
      monthly = Math.floor(diffDays / 30);
    } else {
      // More than 3 months: weekly + monthly
      daily = 0;
      weekly = Math.min(12, Math.floor(diffDays / 7)); // Max 12 weekly
      monthly = Math.floor(diffDays / 30);
    }
    
    return { daily, weekly, monthly, grand: 1 };
  };
  
  const smartDefaults = getSmartDefaults();
  
  const [config, setConfig] = useState({
    auto_generate_daily: campaign?.auto_generate_daily ?? (smartDefaults.daily > 0),
    auto_generate_weekly: campaign?.auto_generate_weekly ?? (smartDefaults.weekly > 0),
    auto_generate_monthly: campaign?.auto_generate_monthly ?? (smartDefaults.monthly > 0),
    auto_generate_grand: campaign?.auto_generate_grand ?? true,
    daily_campaign_count: campaign?.daily_campaign_count ?? smartDefaults.daily,
    weekly_campaign_count: campaign?.weekly_campaign_count ?? smartDefaults.weekly,
    monthly_campaign_count: campaign?.monthly_campaign_count ?? smartDefaults.monthly,
    grand_campaign_count: campaign?.grand_campaign_count ?? smartDefaults.grand,
  });

  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  // Calculate max possible campaigns based on date range
  const getMaxCampaigns = (type) => {
    if (!campaign?.start_date || !campaign?.end_date) return 0;
    
    const start = new Date(campaign.start_date);
    const end = new Date(campaign.end_date);
    const diffTime = Math.abs(end - start);
    const diffDays = Math.ceil(diffTime / (1000 * 60 * 60 * 24));
    
    switch(type) {
      case 'daily':
        return diffDays + 1;
      case 'weekly':
        return Math.ceil(diffDays / 7);
      case 'monthly':
        return Math.ceil(diffDays / 30);
      case 'grand':
        return 1;
      default:
        return 0;
    }
  };

  const handleSave = async () => {
    setLoading(true);
    setError('');
    
    try {
      const response = await api.request(`/admin/master-campaigns/${campaign.id}/config/`, {
        method: 'PUT',
        body: JSON.stringify(config)
      });
      
      onSave(response);
      onClose();
    } catch (err) {
      console.error('Failed to update configuration:', err);
      setError('Failed to update configuration. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const handleGenerate = async () => {
    setLoading(true);
    setError('');
    
    try {
      // First save the configuration
      await api.request(`/admin/master-campaigns/${campaign.id}/config/`, {
        method: 'PUT',
        body: JSON.stringify(config)
      });
      
      // Then trigger generation with cleanup flag
      const response = await api.request(`/admin/master-campaigns/${campaign.id}/generate/`, {
        method: 'POST',
        body: JSON.stringify({
          generate_daily: config.auto_generate_daily,
          generate_weekly: config.auto_generate_weekly,
          generate_monthly: config.auto_generate_monthly,
          generate_grand: config.auto_generate_grand,
          cleanup_excess: true  // New flag to remove excess campaigns
        })
      });
      
      onSave(response);
      onClose();
    } catch (err) {
      console.error('Failed to generate campaigns:', err);
      setError(err.message || 'Failed to generate campaigns. Please try again.');
    } finally {
      setLoading(false);
    }
  };

  const campaignTypes = [
    {
      key: 'daily',
      label: 'Daily Campaigns',
      icon: Calendar,
      color: adminTheme.colors.info,
      description: 'One campaign per day',
      max: getMaxCampaigns('daily'),
      current: campaign?.total_daily_campaigns || 0
    },
    {
      key: 'weekly',
      label: 'Weekly Campaigns',
      icon: TrendingUp,
      color: adminTheme.colors.success,
      description: 'One campaign per week',
      max: getMaxCampaigns('weekly'),
      current: campaign?.total_weekly_campaigns || 0
    },
    {
      key: 'monthly',
      label: 'Monthly Campaigns',
      icon: Calendar,
      color: adminTheme.colors.warning,
      description: 'One campaign per month',
      max: getMaxCampaigns('monthly'),
      current: campaign?.total_monthly_campaigns || 0
    },
    {
      key: 'grand',
      label: 'Grand Campaign',
      icon: Award,
      color: adminTheme.colors.primary,
      description: 'Final championship',
      max: 1,
      current: campaign?.total_grand_campaigns || 0
    }
  ];

  return (
    <div
      className="admin-modal-overlay"
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.55)',
        backdropFilter: 'blur(4px)',
        WebkitBackdropFilter: 'blur(4px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        padding: adminTheme.spacing.xl,
      }}
      onClick={loading ? undefined : onClose}
    >
      <div
        className="admin-modal-content"
        role="dialog"
        aria-modal="true"
        style={{
          background: adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.xl,
          width: '100%',
          maxWidth: 640,
          maxHeight: '90vh',
          overflow: 'auto',
          boxShadow: adminTheme.shadows.xl,
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: adminTheme.spacing.xl,
          borderBottom: `1px solid ${adminTheme.colors.border}`
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{
              width: 40,
              height: 40,
              borderRadius: adminTheme.borderRadius.full,
              background: `${adminTheme.colors.primary}15`,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center'
            }}>
              <Settings size={20} color={adminTheme.colors.primary} />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: adminTheme.typography.fontSize.xl, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary }}>
                Generation Configuration
              </h2>
              <p style={{ margin: 0, fontSize: adminTheme.typography.fontSize.sm, color: adminTheme.colors.textSecondary }}>
                Configure sub-campaign generation
              </p>
            </div>
          </div>
          <button onClick={onClose} style={{
            width: 32,
            height: 32,
            borderRadius: adminTheme.borderRadius.full,
            background: adminTheme.colors.background,
            border: 'none',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <X size={16} color={adminTheme.colors.textSecondary} />
          </button>
        </div>

        {/* Error */}
        {error && (
          <div style={{
            margin: adminTheme.spacing.xl,
            padding: adminTheme.spacing.md,
            background: '#FEE2E2',
            border: '1px solid #FCA5A5',
            borderRadius: adminTheme.borderRadius.md,
            color: '#DC2626',
            fontSize: adminTheme.typography.fontSize.base
          }}>
            {error}
          </div>
        )}

        {/* Summary */}
        <div style={{
          margin: `${adminTheme.spacing.xl} ${adminTheme.spacing.xl} 0`,
          padding: adminTheme.spacing.lg,
          background: adminTheme.colors.primary + '10',
          border: `1px solid ${adminTheme.colors.primary}30`,
          borderRadius: adminTheme.borderRadius.md,
        }}>
          <div style={{ fontSize: adminTheme.typography.fontSize.sm, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary, marginBottom: adminTheme.spacing.sm }}>
            📊 Generation Summary
          </div>
          <div style={{ fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary, lineHeight: 1.6 }}>
            Campaign Duration: <strong>{campaign?.duration_days || 0} days</strong><br/>
            Total to Generate: <strong>
              {(config.auto_generate_daily ? (config.daily_campaign_count || getMaxCampaigns('daily')) : 0) +
               (config.auto_generate_weekly ? (config.weekly_campaign_count || getMaxCampaigns('weekly')) : 0) +
               (config.auto_generate_monthly ? (config.monthly_campaign_count || getMaxCampaigns('monthly')) : 0) +
               (config.auto_generate_grand ? config.grand_campaign_count : 0)} campaigns
            </strong>
            {' '}(
              {config.auto_generate_daily && `${config.daily_campaign_count || getMaxCampaigns('daily')} daily`}
              {config.auto_generate_daily && (config.auto_generate_weekly || config.auto_generate_monthly || config.auto_generate_grand) && ', '}
              {config.auto_generate_weekly && `${config.weekly_campaign_count || getMaxCampaigns('weekly')} weekly`}
              {config.auto_generate_weekly && (config.auto_generate_monthly || config.auto_generate_grand) && ', '}
              {config.auto_generate_monthly && `${config.monthly_campaign_count || getMaxCampaigns('monthly')} monthly`}
              {config.auto_generate_monthly && config.auto_generate_grand && ', '}
              {config.auto_generate_grand && `${config.grand_campaign_count} grand`}
            )
          </div>
        </div>

        {/* Campaign Types */}
        <div style={{ padding: adminTheme.spacing.xl }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: adminTheme.spacing.lg }}>
            {campaignTypes.map(type => {
              const IconComponent = type.icon;
              return (
              <div key={type.key} style={{
                background: adminTheme.colors.background,
                borderRadius: adminTheme.borderRadius.md,
                padding: adminTheme.spacing.lg,
                border: `1px solid ${adminTheme.colors.border}`
              }}>
                <div style={{ display: 'flex', alignItems: 'flex-start', gap: adminTheme.spacing.md, marginBottom: adminTheme.spacing.lg }}>
                  <div style={{
                    width: 36,
                    height: 36,
                    borderRadius: adminTheme.borderRadius.full,
                    background: `${type.color}15`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    flexShrink: 0
                  }}>
                    <IconComponent size={18} color={type.color} />
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: adminTheme.spacing.sm, marginBottom: adminTheme.spacing.xs }}>
                      <h3 style={{ margin: 0, fontSize: adminTheme.typography.fontSize.base, fontWeight: adminTheme.typography.fontWeight.semibold, color: adminTheme.colors.textPrimary }}>
                        {type.label}
                      </h3>
                      <label style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 6,
                        cursor: 'pointer'
                      }}>
                        <input
                          type="checkbox"
                          checked={config[`auto_generate_${type.key}`]}
                          onChange={(e) => setConfig({
                            ...config,
                            [`auto_generate_${type.key}`]: e.target.checked
                          })}
                          style={{ cursor: 'pointer' }}
                        />
                        <span style={{ fontSize: adminTheme.typography.fontSize.sm, color: adminTheme.colors.textSecondary }}>Enable</span>
                      </label>
                    </div>
                    <p style={{ margin: 0, fontSize: adminTheme.typography.fontSize.sm, color: adminTheme.colors.textSecondary }}>
                      {type.description}
                    </p>
                  </div>
                </div>

                {config[`auto_generate_${type.key}`] && (
                  <div>
                    <label style={{
                      display: 'block',
                      fontSize: adminTheme.typography.fontSize.sm,
                      fontWeight: adminTheme.typography.fontWeight.medium,
                      color: adminTheme.colors.textPrimary,
                      marginBottom: adminTheme.spacing.xs
                    }}>
                      Number of {type.label} (0 = all possible)
                    </label>
                    <div style={{ marginBottom: adminTheme.spacing.sm, fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary }}>
                      Current: <strong>{type.current}</strong> {type.label.toLowerCase()}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: adminTheme.spacing.md }}>
                      <input
                        type="number"
                        min="0"
                        max={type.max}
                        value={config[`${type.key}_campaign_count`]}
                        onChange={(e) => setConfig({
                          ...config,
                          [`${type.key}_campaign_count`]: parseInt(e.target.value) || 0
                        })}
                        style={{
                          flex: 1,
                          padding: `${adminTheme.spacing.xs} ${adminTheme.spacing.md}`,
                          borderRadius: adminTheme.borderRadius.sm,
                          border: `1px solid ${adminTheme.colors.border}`,
                          background: adminTheme.colors.card,
                          color: adminTheme.colors.textPrimary,
                          fontSize: adminTheme.typography.fontSize.base
                        }}
                        placeholder={`Suggested: ${smartDefaults[type.key]}`}
                      />
                      <span style={{ fontSize: adminTheme.typography.fontSize.sm, color: adminTheme.colors.textSecondary }}>
                        Max: {type.max}
                      </span>
                    </div>
                    {(() => {
                      const targetCount = config[`${type.key}_campaign_count`] || type.max;
                      const diff = targetCount - type.current;
                      if (diff > 0) {
                        return (
                          <p style={{ margin: `${adminTheme.spacing.xs} 0 0`, fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.success }}>
                            ➕ Will add {diff} {type.label.toLowerCase()}
                          </p>
                        );
                      } else if (diff < 0) {
                        return (
                          <p style={{ margin: `${adminTheme.spacing.xs} 0 0`, fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.error }}>
                            ➖ Will remove {Math.abs(diff)} {type.label.toLowerCase()} (farthest dates first)
                          </p>
                        );
                      } else {
                        return (
                          <p style={{ margin: `${adminTheme.spacing.xs} 0 0`, fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary }}>
                            ✓ No change needed
                          </p>
                        );
                      }
                    })()}
                    {config[`${type.key}_campaign_count`] === 0 && (
                      <p style={{ margin: `${adminTheme.spacing.xs} 0 0`, fontSize: adminTheme.typography.fontSize.xs, color: type.color }}>
                        Will generate all {type.max} {type.label.toLowerCase()}
                      </p>
                    )}
                    {smartDefaults[type.key] > 0 && config[`${type.key}_campaign_count`] !== smartDefaults[type.key] && (
                      <p style={{ margin: `${adminTheme.spacing.xs} 0 0`, fontSize: adminTheme.typography.fontSize.xs, color: adminTheme.colors.textSecondary }}>
                        💡 Suggested: {smartDefaults[type.key]} based on campaign duration
                      </p>
                    )}
                  </div>
                )}
              </div>
              );
            })}
          </div>
        </div>

        {/* Actions */}
        <div style={{
          display: 'flex',
          gap: adminTheme.spacing.md,
          padding: adminTheme.spacing.xl,
          borderTop: `1px solid ${adminTheme.colors.border}`
        }}>
          <button onClick={onClose} disabled={loading} style={{
            flex: 1,
            padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
            borderRadius: adminTheme.borderRadius.md,
            border: `1px solid ${adminTheme.colors.border}`,
            background: adminTheme.colors.background,
            color: adminTheme.colors.textPrimary,
            fontSize: adminTheme.typography.fontSize.base,
            fontWeight: adminTheme.typography.fontWeight.semibold,
            cursor: loading ? 'not-allowed' : 'pointer',
            opacity: loading ? 0.55 : 1,
            transition: `all ${adminTheme.transitions.base}`,
          }}>
            Cancel
          </button>
          <button onClick={handleSave} disabled={loading} style={{
            flex: 1,
            padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
            borderRadius: adminTheme.borderRadius.md,
            border: `1px solid ${adminTheme.colors.border}`,
            background: adminTheme.colors.background,
            color: adminTheme.colors.textPrimary,
            fontSize: adminTheme.typography.fontSize.base,
            fontWeight: adminTheme.typography.fontWeight.semibold,
            cursor: loading ? 'not-allowed' : 'pointer',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: adminTheme.spacing.sm,
            transition: `all ${adminTheme.transitions.base}`,
          }}>
            {loading && <span className="admin-spinner sm" />}
            {loading ? 'Saving...' : 'Save Config'}
          </button>
          <button onClick={handleGenerate} disabled={loading} style={{
            flex: 1.2,
            padding: `${adminTheme.spacing.sm} ${adminTheme.spacing.lg}`,
            borderRadius: adminTheme.borderRadius.md,
            border: 'none',
            background: adminTheme.colors.primary,
            color: adminTheme.colors.textLight,
            fontSize: adminTheme.typography.fontSize.base,
            fontWeight: adminTheme.typography.fontWeight.semibold,
            cursor: loading ? 'not-allowed' : 'pointer',
            boxShadow: `0 4px 12px ${adminTheme.colors.primary}33`,
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: adminTheme.spacing.sm,
            transition: `all ${adminTheme.transitions.base}`,
          }}>
            {loading && <span className="admin-spinner sm" style={{ borderTopColor: '#fff', borderColor: 'rgba(255,255,255,0.4)' }} />}
            {loading ? 'Generating...' : 'Save & Generate'}
          </button>
        </div>
      </div>
    </div>
  );
}




