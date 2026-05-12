import { useState, useEffect } from 'react';
import { Users, FileVideo, ThumbsUp, MessageCircle, TrendingUp, Activity } from 'lucide-react';
import api from '../../api';

export function AdminDashboard({ theme }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboardData();
  }, []);

  const loadDashboardData = async () => {
    try {
      const response = await api.request('/admin/dashboard/');
      setStats(response);
    } catch (error) {
      console.error('Failed to load dashboard:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        Loading dashboard...
      </div>
    );
  }

  const statCards = [
    {
      title: 'Total Users',
      value: stats?.users?.total || 0,
      change: `+${stats?.users?.new_today || 0} today`,
      icon: Users,
      color: theme.blue,
      bg: `${theme.blue}15`
    },
    {
      title: 'Total Reels',
      value: stats?.content?.total_reels || 0,
      change: `+${stats?.content?.reels_today || 0} today`,
      icon: FileVideo,
      color: theme.purple,
      bg: `${theme.purple}15`
    },
    {
      title: 'Total Votes',
      value: stats?.engagement?.total_votes || 0,
      change: `+${stats?.engagement?.votes_today || 0} today`,
      icon: ThumbsUp,
      color: theme.green,
      bg: `${theme.green}15`
    },
    {
      title: 'Total Comments',
      value: stats?.content?.total_comments || 0,
      change: `+${stats?.content?.comments_today || 0} today`,
      icon: MessageCircle,
      color: theme.orange,
      bg: `${theme.orange}15`
    },
    {
      title: 'Active Users (30d)',
      value: stats?.users?.active_month || 0,
      change: `${stats?.users?.active_week || 0} this week`,
      icon: Activity,
      color: theme.pri,
      bg: `${theme.pri}15`
    },
    {
      title: 'Total Follows',
      value: stats?.engagement?.total_follows || 0,
      change: `+${stats?.engagement?.follows_today || 0} today`,
      icon: TrendingUp,
      color: theme.red,
      bg: `${theme.red}15`
    },
  ];

  return (
    <div>
      {/* Header */}
      <div style={{ marginBottom: 32 }}>
        <h1 style={{
          margin: 0,
          fontSize: 32,
          fontWeight: 700,
          color: theme.txt,
          marginBottom: 8,
        }}>
          Dashboard
        </h1>
        <p style={{
          margin: 0,
          fontSize: 16,
          color: theme.sub,
        }}>
          Welcome back! Here's what's happening with your platform.
        </p>
      </div>

      {/* Stats Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: 24,
        marginBottom: 32,
      }}>
        {statCards.map((card, index) => {
          const Icon = card.icon;
          return (
            <div
              key={index}
              style={{
                background: theme.card,
                border: `1px solid ${theme.border}`,
                borderRadius: 12,
                padding: '20px',
                cursor: 'pointer',
                transition: 'all 0.3s ease',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.boxShadow = '0 8px 24px rgba(0,0,0,0.1)';
                e.currentTarget.style.transform = 'translateY(-4px)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.boxShadow = 'none';
                e.currentTarget.style.transform = 'translateY(0)';
              }}
            >
              <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 16 }}>
                <div>
                  <div style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: theme.sub,
                    marginBottom: 8,
                  }}>
                    {card.title}
                  </div>
                  <div style={{
                    fontSize: 32,
                    fontWeight: 700,
                    color: theme.txt,
                  }}>
                    {card.value.toLocaleString()}
                  </div>
                </div>
                <div style={{
                  width: 48,
                  height: 48,
                  borderRadius: 12,
                  background: card.bg,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  color: card.color,
                }}>
                  <Icon size={24} />
                </div>
              </div>
              <div style={{
                fontSize: 13,
                fontWeight: 600,
                color: card.color,
              }}>
                {card.change}
              </div>
            </div>
          );
        })}
      </div>

      {/* Two Column Layout */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))',
        gap: 24,
      }}>
        {/* Top Creators */}
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <h2 style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 20,
          }}>
            Top Creators
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {stats?.top_creators?.slice(0, 5).map((creator, index) => (
              <div
                key={creator.id}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: 12,
                  background: theme.bg,
                  borderRadius: 8,
                }}
              >
                <div style={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  background: theme.pri,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 14,
                  fontWeight: 700,
                  color: '#fff',
                }}>
                  {index + 1}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{
                    fontSize: 14,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 2,
                  }}>
                    {creator.username}
                  </div>
                  <div style={{
                    fontSize: 12,
                    color: theme.sub,
                  }}>
                    {creator.reel_count} reels • {creator.followers} followers
                  </div>
                </div>
                <div style={{
                  fontSize: 16,
                  fontWeight: 700,
                  color: theme.pri,
                }}>
                  {creator.total_votes.toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Trending Reels */}
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <h2 style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 20,
          }}>
            Trending Reels (7 days)
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {stats?.trending_reels?.slice(0, 5).map((reel) => (
              <div
                key={reel.id}
                style={{
                  padding: 12,
                  background: theme.bg,
                  borderRadius: 8,
                }}
              >
                <div style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  {reel.caption}
                </div>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  fontSize: 12,
                  color: theme.sub,
                }}>
                  <span>by @{reel.user}</span>
                  <div style={{ display: 'flex', gap: 16 }}>
                    <span>❤️ {reel.votes}</span>
                    <span>💬 {reel.comments}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Subscription Stats */}
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 24,
          border: `1px solid ${theme.border}`,
        }}>
          <h2 style={{
            margin: 0,
            fontSize: 18,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 20,
          }}>
            Subscription Distribution
          </h2>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {stats?.subscriptions?.map((sub) => {
              const colors = {
                free: theme.sub,
                pro: theme.blue,
                premium: theme.pri
              };
              const color = colors[sub.plan] || theme.sub;
              
              return (
                <div key={sub.plan} style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <div style={{
                    width: 12,
                    height: 12,
                    borderRadius: '50%',
                    background: color,
                  }} />
                  <div style={{ flex: 1 }}>
                    <div style={{
                      fontSize: 14,
                      fontWeight: 600,
                      color: theme.txt,
                      textTransform: 'capitalize',
                    }}>
                      {sub.plan}
                    </div>
                  </div>
                  <div style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: theme.txt,
                  }}>
                    {sub.count}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}




