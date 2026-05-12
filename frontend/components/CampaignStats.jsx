import React, { useState, useEffect } from 'react';
import api from '../api';
import { Trophy, Award, TrendingUp, Target, Calendar } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

const CampaignStats = ({ userId }) => {
  const { colors: T } = useTheme();
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => { loadStats(); }, [userId]);

  const loadStats = async () => {
    try {
      setLoading(true);
      const response = await api.request(`/campaigns/profile/${userId || ''}`);
      setStats(response);
    } catch (error) {
      console.error('Error loading campaign stats:', error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div style={{ padding: '32px', textAlign: 'center', color: T.sub, fontSize: 14 }}>
        Loading campaign stats...
      </div>
    );
  }

  if (!stats || stats.campaigns?.length === 0) {
    return (
      <div style={{ padding: '48px 20px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🏆</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.txt, marginBottom: 6 }}>No campaigns yet</div>
        <div style={{ fontSize: 13, color: T.sub }}>Join a campaign to see your stats here!</div>
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <Trophy size={22} color={T.pri} />
        <span style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>Campaign Achievements</span>
      </div>

      {/* Overall Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 24 }}>
        <StatCard icon={<Target size={18} />}    label="Campaigns"   value={stats.total_campaigns || 0}                        pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<Award size={18} />}     label="Total Score" value={stats.total_score || 0}                            pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<TrendingUp size={18} />} label="Best Rank"  value={stats.best_rank ? `#${stats.best_rank}` : '–'}    pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<Calendar size={18} />}  label="Streak"      value={stats.current_streak || 0}                        pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
      </div>

      {/* Campaign List */}
      {stats.campaigns?.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
            Active Campaigns
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {stats.campaigns.map((campaign) => (
              <div key={campaign.campaign_id} style={{
                background: T.bg,
                border: `1.5px solid ${T.border}`,
                borderRadius: 14,
                padding: '14px 16px',
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
              }}>
                <div>
                  <div style={{ fontWeight: 700, fontSize: 14, color: T.txt, marginBottom: 3 }}>
                    {campaign.campaign_title}
                  </div>
                  <div style={{ fontSize: 12, color: T.sub }}>
                    {campaign.posts_count} posts · Rank #{campaign.rank || '–'}
                  </div>
                </div>
                <div style={{
                  background: `${T.pri}18`,
                  color: T.pri,
                  border: `1.5px solid ${T.pri}40`,
                  padding: '6px 14px',
                  borderRadius: 20,
                  fontSize: 13,
                  fontWeight: 700,
                }}>
                  {campaign.total_score} pts
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Badges */}
      {stats.badges?.length > 0 && (
        <div>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
            Badges Earned
          </div>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            {stats.badges.map((badge, idx) => (
              <div key={idx} style={{
                background: `${T.pri}15`,
                color: T.pri,
                border: `1.5px solid ${T.pri}35`,
                padding: '6px 12px',
                borderRadius: 20,
                fontSize: 12,
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: 6,
              }}>
                <Award size={13} />
                {badge.title}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const StatCard = ({ icon, label, value, pri, txt, sub, bg, border }) => (
  <div style={{
    background: bg,
    border: `1.5px solid ${border}`,
    borderRadius: 14,
    padding: '16px 12px',
    textAlign: 'center',
  }}>
    <div style={{ color: pri, marginBottom: 8, display: 'flex', justifyContent: 'center' }}>
      {icon}
    </div>
    <div style={{ fontSize: 22, fontWeight: 800, color: txt, marginBottom: 4 }}>
      {value}
    </div>
    <div style={{ fontSize: 11, color: sub, textTransform: 'uppercase', letterSpacing: 0.5 }}>
      {label}
    </div>
  </div>
);

export default CampaignStats;




