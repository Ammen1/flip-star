import { useState, useEffect } from 'react';
import { Activity, Database, Zap, TrendingUp } from 'lucide-react';
import api from '../../api';
import { adminTheme } from '../theme';

export function PerformancePage({ theme }) {
  const [performance, setPerformance] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadPerformance();
    const interval = setInterval(loadPerformance, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadPerformance = async () => {
    try {
      const data = await api.request('/admin/performance/');
      setPerformance(data);
    } catch (error) {
      console.error('Failed to load performance:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: adminTheme.spacing['3xl'], textAlign: 'center', color: adminTheme.colors.textSecondary, fontSize: adminTheme.typography.fontSize.base }}>
        Loading performance data...
      </div>
    );
  }

  const current = performance?.current || {};
  const weeklyTrend = performance?.weekly_trend || [];
  const systemHealth = performance?.system_health || {};

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: adminTheme.spacing['2xl'] }}>
        <h1 style={{
          margin: 0,
          fontSize: adminTheme.typography.fontSize['4xl'],
          fontWeight: adminTheme.typography.fontWeight.semibold,
          color: adminTheme.colors.textPrimary,
          marginBottom: adminTheme.spacing.sm,
        }}>
          Platform Performance
        </h1>
        <p style={{
          margin: 0,
          fontSize: adminTheme.typography.fontSize.lg,
          color: adminTheme.colors.textSecondary,
        }}>
          Real-time platform metrics and system health
        </p>
      </div>

      {/* Current Metrics */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: adminTheme.spacing['2xl'],
        marginBottom: adminTheme.spacing['2xl'],
      }}>
        <MetricCard
          label="Total Users"
          value={current.total_users || 0}
          change={`+${current.active_today || 0} today`}
          icon={Activity}
          color={adminTheme.colors.info}
          theme={adminTheme.colors}
        />
        <MetricCard
          label="Total Reels"
          value={current.total_reels || 0}
          change={`+${current.reels_today || 0} today`}
          icon={TrendingUp}
          color={adminTheme.colors.secondary}
          theme={adminTheme.colors}
        />
        <MetricCard
          label="Total Votes"
          value={current.total_votes || 0}
          change={`+${current.votes_today || 0} today`}
          icon={Zap}
          color={adminTheme.colors.success}
          theme={adminTheme.colors}
        />
        <MetricCard
          label="DB Queries"
          value={current.db_queries || 0}
          change="Current session"
          icon={Database}
          color={adminTheme.colors.warning}
          theme={adminTheme.colors}
        />
      </div>

      {/* System Health */}
      <div style={{
        background: adminTheme.colors.card,
        borderRadius: adminTheme.borderRadius.lg,
        padding: adminTheme.spacing['2xl'],
        border: `1px solid ${adminTheme.colors.border}`,
        marginBottom: adminTheme.spacing['2xl'],
      }}>
        <h2 style={{
          margin: 0,
          fontSize: adminTheme.typography.fontSize.xl,
          fontWeight: adminTheme.typography.fontWeight.semibold,
          color: adminTheme.colors.textPrimary,
          marginBottom: adminTheme.spacing.xl,
        }}>
          System Health
        </h2>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
          gap: adminTheme.spacing.lg,
        }}>
          {Object.entries(systemHealth).map(([key, status]) => (
            <div
              key={key}
              style={{
                padding: adminTheme.spacing.lg,
                background: adminTheme.colors.background,
                borderRadius: adminTheme.borderRadius.md,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
              }}
            >
              <span style={{
                fontSize: adminTheme.typography.fontSize.base,
                fontWeight: adminTheme.typography.fontWeight.semibold,
                color: adminTheme.colors.textPrimary,
                textTransform: 'capitalize',
              }}>
                {key}
              </span>
              <span style={{
                padding: `${adminTheme.spacing.xs} ${adminTheme.spacing.lg}`,
                borderRadius: adminTheme.borderRadius.full,
                fontSize: adminTheme.typography.fontSize.xs,
                fontWeight: adminTheme.typography.fontWeight.semibold,
                background: status === 'healthy' ? adminTheme.colors.success + '20' : adminTheme.colors.error + '20',
                color: status === 'healthy' ? adminTheme.colors.success : adminTheme.colors.error,
              }}>
                {status}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Weekly Trend */}
      {weeklyTrend.length > 0 && (
        <div style={{
          background: adminTheme.colors.card,
          borderRadius: adminTheme.borderRadius.lg,
          padding: adminTheme.spacing['2xl'],
          border: `1px solid ${adminTheme.colors.border}`,
        }}>
          <h2 style={{
            margin: 0,
            fontSize: adminTheme.typography.fontSize.xl,
            fontWeight: adminTheme.typography.fontWeight.semibold,
            color: adminTheme.colors.textPrimary,
            marginBottom: adminTheme.spacing.xl,
          }}>
            7-Day Trend
          </h2>
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse' }}>
              <thead>
                <tr style={{ background: adminTheme.colors.background }}>
                  <th style={headerStyle}>Date</th>
                  <th style={headerStyle}>Active Users</th>
                  <th style={headerStyle}>New Reels</th>
                  <th style={headerStyle}>New Votes</th>
                  <th style={headerStyle}>API Calls</th>
                  <th style={headerStyle}>Avg Response (ms)</th>
                </tr>
              </thead>
              <tbody>
                {weeklyTrend.map((day, index) => (
                  <tr key={day.date} style={{
                    borderTop: index > 0 ? `1px solid ${adminTheme.colors.border}` : 'none',
                  }}>
                    <td style={cellStyle}>{new Date(day.date).toLocaleDateString()}</td>
                    <td style={cellStyle}>{day.active_users}</td>
                    <td style={cellStyle}>{day.new_reels}</td>
                    <td style={cellStyle}>{day.new_votes}</td>
                    <td style={cellStyle}>{day.api_calls}</td>
                    <td style={cellStyle}>{day.avg_response_time_ms.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

function MetricCard({ label, value, change, icon: Icon, color, theme }) {
  return (
    <div style={{
      background: adminTheme.colors.card,
      borderRadius: adminTheme.borderRadius.lg,
      padding: adminTheme.spacing['2xl'],
      border: `1px solid ${adminTheme.colors.border}`,
      boxShadow: adminTheme.shadows.sm,
    }}>
      <div style={{
        display: 'flex',
        alignItems: 'flex-start',
        justifyContent: 'space-between',
        marginBottom: adminTheme.spacing.lg,
      }}>
        <div>
          <div style={{
            fontSize: adminTheme.typography.fontSize.base,
            fontWeight: adminTheme.typography.fontWeight.semibold,
            color: adminTheme.colors.textSecondary,
            marginBottom: adminTheme.spacing.sm,
          }}>
            {label}
          </div>
          <div style={{
            fontSize: adminTheme.typography.fontSize['4xl'],
            fontWeight: adminTheme.typography.fontWeight.semibold,
            color: adminTheme.colors.textPrimary,
          }}>
            {value.toLocaleString()}
          </div>
        </div>
        <div style={{
          width: 48,
          height: 48,
          borderRadius: adminTheme.borderRadius.lg,
          background: color + '15',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}>
          <Icon size={24} color={color} />
        </div>
      </div>
      <div style={{
        fontSize: adminTheme.typography.fontSize.sm,
        fontWeight: adminTheme.typography.fontWeight.semibold,
        color: color,
      }}>
        {change}
      </div>
    </div>
  );
}

const headerStyle = {
  padding: `${adminTheme.spacing.md} ${adminTheme.spacing.lg}`,
  textAlign: 'left',
  fontSize: adminTheme.typography.fontSize.sm,
  fontWeight: adminTheme.typography.fontWeight.semibold,
  color: adminTheme.colors.textSecondary,
  textTransform: 'uppercase',
  letterSpacing: '0.5px',
};

const cellStyle = {
  padding: `${adminTheme.spacing.md} ${adminTheme.spacing.lg}`,
  fontSize: adminTheme.typography.fontSize.base,
  color: adminTheme.colors.textPrimary,
};




