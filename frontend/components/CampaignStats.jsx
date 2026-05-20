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
      const path = userId ? `/campaigns/profile/${userId}/` : '/campaigns/profile/';
      const response = await api.request(path);
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

  const campaigns = stats?.campaigns || [];

  if (!stats || campaigns.length === 0) {
    return (
      <div style={{ padding: '48px 20px', textAlign: 'center' }}>
        <div style={{ fontSize: 48, marginBottom: 12 }}>🏆</div>
        <div style={{ fontSize: 16, fontWeight: 700, color: T.txt, marginBottom: 6 }}>No campaigns yet</div>
        <div style={{ fontSize: 13, color: T.sub }}>Join a campaign to see your stats here!</div>
      </div>
    );
  }

  // Compute aggregates from per-campaign stats (backend returns nested shape)
  const totalScore = campaigns.reduce((sum, c) => sum + (Number(c.stats?.total_score) || 0), 0);
  const ranks = campaigns.map(c => c.stats?.overall_rank).filter(r => r && r > 0);
  const bestRank = ranks.length ? Math.min(...ranks) : null;
  const bestStreak = campaigns.reduce((max, c) => Math.max(max, Number(c.stats?.longest_streak) || 0), 0);

  const formatScore = (v) => {
    const n = Number(v) || 0;
    return n >= 1000 ? n.toFixed(0) : n.toFixed(1).replace(/\.0$/, '');
  };

  return (
    <div>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 20 }}>
        <Trophy size={22} color={T.pri} />
        <span style={{ fontSize: 18, fontWeight: 800, color: T.txt }}>Campaign Achievements</span>
      </div>

      {/* Overall Stats Grid */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 24 }}>
        <StatCard icon={<Target size={18} />}     label="Campaigns"   value={stats.total_campaigns ?? campaigns.length}        pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<Award size={18} />}      label="Total Score" value={formatScore(totalScore)}                           pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<TrendingUp size={18} />} label="Best Rank"   value={bestRank ? `#${bestRank}` : '–'}                  pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
        <StatCard icon={<Calendar size={18} />}   label="Wins"        value={stats.total_wins ?? 0}                            pri={T.pri} txt={T.txt} sub={T.sub} bg={T.bg} border={T.border} />
      </div>

      {/* Campaign List */}
      {campaigns.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div style={{ fontSize: 13, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
            Campaigns Participated
          </div>
          <div style={{ display: 'grid', gap: 10 }}>
            {campaigns.map((c) => {
              const campaign = c.campaign || {};
              const cs = c.stats || {};
              const statusColor = campaign.status === 'active' ? '#10B981'
                : campaign.status === 'voting' ? '#3B82F6'
                : campaign.status === 'upcoming' ? '#F59E0B'
                : '#94A3B8';
              return (
                <div key={campaign.id} style={{
                  background: T.bg,
                  border: `1.5px solid ${T.border}`,
                  borderRadius: 14,
                  padding: '14px 16px',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                  gap: 12,
                }}>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <div style={{ fontWeight: 700, fontSize: 14, color: T.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {campaign.title || 'Untitled'}
                      </div>
                      {campaign.status && (
                        <span style={{
                          fontSize: 9, fontWeight: 800, letterSpacing: 0.5,
                          textTransform: 'uppercase',
                          padding: '2px 6px', borderRadius: 6,
                          background: `${statusColor}22`, color: statusColor,
                          flexShrink: 0,
                        }}>{campaign.status}</span>
                      )}
                    </div>
                    <div style={{ fontSize: 12, color: T.sub, display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                      <span>Rank <b style={{ color: T.txt }}>{cs.overall_rank ? `#${cs.overall_rank}` : '–'}</b></span>
                      <span>·</span>
                      <span>{cs.approved_posts ?? cs.total_posts ?? 0} {((cs.approved_posts ?? cs.total_posts ?? 0) === 1) ? 'post' : 'posts'}</span>
                      {cs.current_streak > 0 && (<><span>·</span><span>🔥 {cs.current_streak}d</span></>)}
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
                    flexShrink: 0,
                  }}>
                    {formatScore(cs.total_score)} pts
                  </div>
                </div>
              );
            })}
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




