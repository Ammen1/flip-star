import { useState, useEffect } from 'react';
import { Crown, Zap, Star, TrendingUp, DollarSign, Users, Clock, RefreshCw, Calendar, CalendarDays, CalendarRange, Coins } from 'lucide-react';
import api from '../../api';

// Map duration_type → icon, fallback color
const DURATION_ICON = {
  daily: Calendar,
  weekly: CalendarDays,
  monthly: CalendarRange,
  ondemand: Coins,
};
const DURATION_LABEL = {
  daily: 'Daily',
  weekly: 'Weekly',
  monthly: 'Monthly',
  ondemand: 'On-Demand',
};

export function SubscriptionManagement({ theme }) {
  const [analytics, setAnalytics] = useState(null);
  const [chargingAnalytics, setChargingAnalytics] = useState(null);
  const [tiers, setTiers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  useEffect(() => {
    loadAll();
  }, []);

  const loadAll = async ({ silent = false } = {}) => {
    if (silent) setRefreshing(true); else setLoading(true);
    try {
      const [analyticsData, chargingData, tiersData] = await Promise.all([
        api.request('/admin/subscriptions/analytics/').catch(() => null),
        api.request('/admin/subscriptions/charging/').catch(() => null),
        api.request('/subscriptions/tiers/active/').catch(() => []),
      ]);
      setAnalytics(analyticsData);
      setChargingAnalytics(chargingData);
      setTiers(Array.isArray(tiersData) ? tiersData : (tiersData?.results || []));
    } catch (error) {
      console.error('Failed to load subscription data:', error);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Build display plans from real backend tiers
  const tierColors = [theme.pri, theme.blue, theme.green, theme.sub, '#F59E0B', '#8B5CF6'];
  const plans = (tiers || []).map((tier, idx) => {
    const Icon = DURATION_ICON[tier.duration_type] || Star;
    const color = tierColors[idx % tierColors.length];
    const count = analytics?.tier_distribution?.[tier.name] || 0;

    // Build feature list from tier flags + features array
    const flagFeatures = [];
    if (tier.priority_support) flagFeatures.push('Priority support');
    if (tier.custom_themes) flagFeatures.push('Custom themes');
    if (tier.analytics_access) flagFeatures.push('Advanced analytics');
    if (tier.api_access) flagFeatures.push('API access');
    if (tier.ad_free) flagFeatures.push('Ad-free');
    if (tier.watermark_free) flagFeatures.push('No watermark');
    if (tier.hd_quality) flagFeatures.push('HD quality');
    if (tier.download_videos) flagFeatures.push('Download videos');
    const explicitFeatures = Array.isArray(tier.features) ? tier.features : [];
    const features = [...explicitFeatures, ...flagFeatures];

    return {
      id: tier.id,
      name: tier.name,
      description: tier.description,
      icon: Icon,
      color,
      duration: DURATION_LABEL[tier.duration_type] || tier.duration_type,
      durationDays: tier.duration_days,
      price: Number(tier.price_etb || 0),
      priceCoins: tier.price_coins,
      features,
      count,
    };
  });

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        Loading subscription data...
      </div>
    );
  }

  const totalSubscribers = analytics?.total_subscriptions || 0;
  const activeSubscriptions = analytics?.active_subscriptions || 0;
  const expiredSubscriptions = analytics?.expired_subscriptions || 0;
  const trialUsers = analytics?.trial_users || 0;
  const totalRevenue = Number(analytics?.total_revenue || 0);

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32, display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexWrap: 'wrap' }}>
        <div>
          <h1 style={{
            margin: 0,
            fontSize: 32,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 8,
          }}>
            Subscription Management
          </h1>
          <p style={{
            margin: 0,
            fontSize: 16,
            color: theme.sub,
          }}>
            Monitor subscription plans and revenue
          </p>
        </div>
        <button
          onClick={() => loadAll({ silent: true })}
          disabled={refreshing}
          style={{
            display: 'flex', alignItems: 'center', gap: 8,
            padding: '10px 16px', borderRadius: 10,
            background: theme.card, color: theme.txt,
            border: `1px solid ${theme.border}`,
            cursor: refreshing ? 'not-allowed' : 'pointer',
            fontSize: 13, fontWeight: 600,
            opacity: refreshing ? 0.7 : 1,
          }}
        >
          <RefreshCw
            size={14}
            style={{ animation: refreshing ? 'sub-spin 0.9s linear infinite' : 'none' }}
          />
          {refreshing ? 'Refreshing...' : 'Refresh'}
        </button>
        <style>{`@keyframes sub-spin { to { transform: rotate(360deg); } }`}</style>
      </div>

      {/* Revenue Stats */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
        gap: 24,
        marginBottom: 32,
      }}>
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: theme.sub,
            marginBottom: 8,
          }}>
            Total Subscriptions
          </div>
          <div style={{
            fontSize: 32,
            fontWeight: 700,
            color: theme.txt,
          }}>
            {totalSubscribers}
          </div>
        </div>

        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: theme.sub,
            marginBottom: 8,
          }}>
            Active Subscriptions
          </div>
          <div style={{
            fontSize: 32,
            fontWeight: 700,
            color: theme.green,
          }}>
            {activeSubscriptions}
          </div>
        </div>

        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: theme.sub,
            marginBottom: 8,
          }}>
            Trial Users
          </div>
          <div style={{
            fontSize: 32,
            fontWeight: 700,
            color: theme.blue,
          }}>
            {trialUsers}
          </div>
        </div>

        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <div style={{
            fontSize: 14,
            fontWeight: 600,
            color: theme.sub,
            marginBottom: 8,
          }}>
            Total Revenue (ETB)
          </div>
          <div style={{
            fontSize: 32,
            fontWeight: 700,
            color: theme.pri,
          }}>
            {totalRevenue.toFixed(2)}
          </div>
        </div>
      </div>

      {/* Subscription Plans header */}
      <h3 style={{ fontSize: 18, fontWeight: 700, color: theme.txt, marginBottom: 16 }}>
        Subscription Tiers ({plans.length})
      </h3>

      {plans.length === 0 ? (
        <div style={{
          background: theme.card, border: `1px solid ${theme.border}`,
          borderRadius: 12, padding: 32, textAlign: 'center', color: theme.sub,
          marginBottom: 32,
        }}>
          No subscription tiers configured. Create tiers in the Django admin to see them here.
        </div>
      ) : (
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
        gap: 24,
        marginBottom: 32,
      }}>
        {plans.map((plan) => {
          const Icon = plan.icon;
          const percentage = activeSubscriptions > 0 ? ((plan.count / activeSubscriptions) * 100).toFixed(1) : 0;
          
          return (
            <div
              key={plan.name}
              style={{
                background: theme.card,
                borderRadius: 12,
                padding: 24,
                border: `2px solid ${plan.color}`,
                position: 'relative',
                overflow: 'hidden',
              }}
            >
              {/* Background decoration */}
              <div style={{
                position: 'absolute',
                top: -20,
                right: -20,
                width: 100,
                height: 100,
                borderRadius: '50%',
                background: plan.color + '10',
              }} />

              <div style={{
                position: 'relative',
                zIndex: 1,
              }}>
                <div style={{
                  width: 56,
                  height: 56,
                  borderRadius: 12,
                  background: plan.color + '15',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: 16,
                }}>
                  <Icon size={28} color={plan.color} />
                </div>

                <h3 style={{
                  margin: 0,
                  fontSize: 24,
                  fontWeight: 700,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  {plan.name}
                </h3>

                <div style={{
                  fontSize: 18,
                  fontWeight: 600,
                  color: plan.color,
                  marginBottom: 8,
                }}>
                  {plan.price} ETB
                </div>

                {plan.priceCoins && (
                  <div style={{
                    fontSize: 14,
                    color: theme.sub,
                    marginBottom: 8,
                  }}>
                    or {plan.priceCoins} coins
                  </div>
                )}

                <div style={{
                  fontSize: 14,
                  color: theme.sub,
                  marginBottom: 20,
                  textTransform: 'capitalize',
                }}>
                  {plan.duration} • {plan.count} subscribers ({percentage}%)
                </div>

                {/* Progress Bar */}
                <div style={{
                  width: '100%',
                  height: 8,
                  background: theme.bg,
                  borderRadius: 4,
                  overflow: 'hidden',
                  marginBottom: 20,
                }}>
                  <div style={{
                    width: `${percentage}%`,
                    height: '100%',
                    background: plan.color,
                    transition: 'width 0.3s ease',
                  }} />
                </div>

                {/* Features */}
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 8,
                }}>
                  {plan.features.map((feature, index) => (
                    <div
                      key={index}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 8,
                        fontSize: 13,
                        color: theme.sub,
                      }}
                    >
                      <div style={{
                        width: 16,
                        height: 16,
                        borderRadius: '50%',
                        background: plan.color + '20',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 10,
                      }}>
                        ✓
                      </div>
                      {feature}
                    </div>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </div>
      )}

      {/* Charging Analytics */}
      {chargingAnalytics && (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
          marginBottom: 32,
        }}>
          <h3 style={{
            fontSize: 20,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 24,
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}>
            <TrendingUp size={24} color={theme.pri} />
            Real-Time Charging Analytics
          </h3>

          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            gap: 24,
            marginBottom: 32,
          }}>
            <div style={{
              background: `${theme.green}15`,
              borderRadius: 12,
              padding: 20,
              border: `1px solid ${theme.green}`,
            }}>
              <div style={{
                fontSize: 14,
                fontWeight: 600,
                color: theme.green,
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <DollarSign size={18} />
                Monthly Recurring Revenue (MRR)
              </div>
              <div style={{
                fontSize: 28,
                fontWeight: 800,
                color: theme.green,
              }}>
                {chargingAnalytics.active_subscriptions.mrr.toFixed(2)} ETB
              </div>
            </div>

            <div style={{
              background: `${theme.blue}15`,
              borderRadius: 12,
              padding: 20,
              border: `1px solid ${theme.blue}`,
            }}>
              <div style={{
                fontSize: 14,
                fontWeight: 600,
                color: theme.blue,
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <Users size={18} />
                Active Subscriptions
              </div>
              <div style={{
                fontSize: 28,
                fontWeight: 800,
                color: theme.blue,
              }}>
                {chargingAnalytics.active_subscriptions.total}
              </div>
            </div>

            <div style={{
              background: `${theme.pri}15`,
              borderRadius: 12,
              padding: 20,
              border: `1px solid ${theme.pri}`,
            }}>
              <div style={{
                fontSize: 14,
                fontWeight: 600,
                color: theme.pri,
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <Clock size={18} />
                Today's Revenue
              </div>
              <div style={{
                fontSize: 28,
                fontWeight: 800,
                color: theme.pri,
              }}>
                {chargingAnalytics.revenue.today.total.toFixed(2)} ETB
              </div>
              <div style={{
                fontSize: 12,
                color: theme.sub,
                marginTop: 4,
              }}>
                {chargingAnalytics.revenue.today.count} transactions
              </div>
            </div>

            <div style={{
              background: `${theme.sub}15`,
              borderRadius: 12,
              padding: 20,
              border: `1px solid ${theme.sub}`,
            }}>
              <div style={{
                fontSize: 14,
                fontWeight: 600,
                color: theme.sub,
                marginBottom: 8,
                display: 'flex',
                alignItems: 'center',
                gap: 8,
              }}>
                <Star size={18} />
                This Month's Revenue
              </div>
              <div style={{
                fontSize: 28,
                fontWeight: 800,
                color: theme.txt,
              }}>
                {chargingAnalytics.revenue.month.total.toFixed(2)} ETB
              </div>
              <div style={{
                fontSize: 12,
                color: theme.sub,
                marginTop: 4,
              }}>
                {chargingAnalytics.revenue.month.count} transactions
              </div>
            </div>
          </div>

          {/* Revenue by Tier */}
          <div style={{ marginBottom: 32 }}>
            <h4 style={{
              fontSize: 16,
              fontWeight: 600,
              color: theme.txt,
              marginBottom: 16,
            }}>
              Active Subscriptions by Tier
            </h4>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(250px, 1fr))',
              gap: 16,
            }}>
              {chargingAnalytics.active_subscriptions.by_tier.map((tier, index) => (
                <div key={index} style={{
                  background: theme.card,
                  borderRadius: 8,
                  padding: 16,
                  border: `1px solid ${theme.border}`,
                }}>
                  <div style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: theme.txt,
                    marginBottom: 8,
                  }}>
                    {tier.tier__name}
                  </div>
                  <div style={{
                    fontSize: 14,
                    color: theme.sub,
                    marginBottom: 4,
                  }}>
                    {tier.count} subscribers
                  </div>
                  <div style={{
                    fontSize: 20,
                    fontWeight: 700,
                    color: theme.green,
                  }}>
                    {tier.total_revenue.toFixed(2)} ETB
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Recent Transactions */}
          <div>
            <h4 style={{
              fontSize: 16,
              fontWeight: 600,
              color: theme.txt,
              marginBottom: 16,
            }}>
              Recent Transactions
            </h4>
            <div style={{
              background: theme.card,
              borderRadius: 8,
              border: `1px solid ${theme.border}`,
              overflow: 'hidden',
            }}>
              <table style={{
                width: '100%',
                borderCollapse: 'collapse',
              }}>
                <thead>
                  <tr style={{
                    background: theme.bg,
                    borderBottom: `1px solid ${theme.border}`,
                  }}>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                    }}>User</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                    }}>Tier</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                    }}>Amount</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                    }}>Method</th>
                    <th style={{
                      padding: 12,
                      textAlign: 'left',
                      fontSize: 12,
                      fontWeight: 600,
                      color: theme.sub,
                    }}>Date</th>
                  </tr>
                </thead>
                <tbody>
                  {chargingAnalytics.recent_transactions.map((tx, index) => (
                    <tr key={index} style={{
                      borderBottom: index < chargingAnalytics.recent_transactions.length - 1 ? `1px solid ${theme.border}` : 'none',
                    }}>
                      <td style={{ padding: 12, fontSize: 14, color: theme.txt }}>{tx.user}</td>
                      <td style={{ padding: 12, fontSize: 14, color: theme.txt }}>{tx.tier}</td>
                      <td style={{ padding: 12, fontSize: 14, fontWeight: 600, color: theme.green }}>{tx.amount.toFixed(2)} ETB</td>
                      <td style={{ padding: 12, fontSize: 14, color: theme.txt }}>{tx.payment_method}</td>
                      <td style={{ padding: 12, fontSize: 14, color: theme.sub }}>{tx.date}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}


