import { useState, useEffect } from 'react';
import { Trophy, Search, Filter, TrendingUp, Heart, MessageCircle, Share2, Gift, Crown, Medal } from 'lucide-react';
import api from '../../api';

export function LeaderboardPage({ theme, campaignId, campaign }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedPeriod, setSelectedPeriod] = useState('overall');
  const [searchQuery, setSearchQuery] = useState('');

  const PERIODS = [
    { id: 'overall', label: 'Overall' },
    { id: 'daily', label: 'Daily' },
    { id: 'weekly', label: 'Weekly' },
    { id: 'monthly', label: 'Monthly' },
  ];

  useEffect(() => {
    if (campaignId) {
      loadLeaderboard();
    }
  }, [campaignId, selectedPeriod]);

  const loadLeaderboard = async () => {
    try {
      setLoading(true);
      const data = await api.request(`/campaigns/${campaignId}/leaderboard/?period=${selectedPeriod}`);
      setEntries(data.entries || []);
    } catch (error) {
      console.error('Failed to load leaderboard:', error);
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  const filteredEntries = entries.filter(entry =>
    entry.username?.toLowerCase().includes(searchQuery.toLowerCase())
  );

  const getRankBadge = (rank) => {
    if (rank === 1) return { icon: Crown, color: '#FFD700', label: 'Champion' };
    if (rank === 2) return { icon: Medal, color: '#C0C0C0', label: '2nd' };
    if (rank === 3) return { icon: Medal, color: '#CD7F32', label: '3rd' };
    return null;
  };

  if (!campaignId) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        No campaign selected
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: theme.bg, color: theme.txt }}>
      {/* Header */}
      <div style={{
        padding: '24px 32px',
        borderBottom: `1px solid ${theme.border}`,
        background: theme.card,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 16 }}>
          <Trophy size={28} color={theme.accent} />
          <div>
            <h1 style={{ fontSize: 24, fontWeight: 700, color: theme.txt, margin: 0 }}>
              Leaderboard
            </h1>
            <p style={{ fontSize: 14, color: theme.sub, margin: 0 }}>
              {campaign?.title || 'Campaign Leaderboard'}
            </p>
          </div>
        </div>

        {/* Filters */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {/* Period Tabs */}
          <div style={{ display: 'flex', gap: 8, background: theme.bg, padding: 4, borderRadius: 8 }}>
            {PERIODS.map((period) => (
              <button
                key={period.id}
                onClick={() => setSelectedPeriod(period.id)}
                style={{
                  padding: '8px 16px',
                  borderRadius: 6,
                  border: 'none',
                  background: selectedPeriod === period.id ? theme.accent : 'transparent',
                  color: selectedPeriod === period.id ? '#000' : theme.sub,
                  fontSize: 13,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
              >
                {period.label}
              </button>
            ))}
          </div>

          {/* Search */}
          <div style={{ flex: 1, minWidth: 200, maxWidth: 300 }}>
            <div style={{ position: 'relative' }}>
              <Search size={16} color={theme.sub} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                placeholder="Search users..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                style={{
                  width: '100%',
                  padding: '8px 12px 8px 36px',
                  borderRadius: 8,
                  border: `1px solid ${theme.border}`,
                  background: theme.bg,
                  color: theme.txt,
                  fontSize: 13,
                  outline: 'none',
                  boxSizing: 'border-box',
                }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Content */}
      <div style={{ padding: '24px 32px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: 60, color: theme.sub }}>
            Loading leaderboard...
          </div>
        ) : filteredEntries.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: 60,
            background: theme.card,
            borderRadius: 16,
            border: `1px solid ${theme.border}`,
          }}>
            <Trophy size={48} color={theme.border} style={{ marginBottom: 16 }} />
            <p style={{ fontSize: 16, color: theme.sub, margin: 0 }}>
              No entries yet
            </p>
          </div>
        ) : (
          <>
            {/* Podium View - Top 3 */}
            {filteredEntries.length >= 3 && (
              <div style={{
                display: 'grid',
                gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
                gap: 16,
                marginBottom: 32,
              }}>
                {[2, 1, 3].map((rank) => {
                  const entry = filteredEntries.find(e => e.rank === rank);
                  if (!entry) return null;
                  const badge = getRankBadge(rank);
                  const RankIcon = badge?.icon;
                  const isFirst = rank === 1;

                  return (
                    <div
                      key={entry.id}
                      style={{
                        background: isFirst ? 'linear-gradient(135deg, #FFD700 0%, #b8d97a 100%)' : theme.card,
                        borderRadius: 16,
                        padding: 24,
                        textAlign: 'center',
                        border: isFirst ? 'none' : `1px solid ${theme.border}`,
                        position: 'relative',
                        boxShadow: isFirst ? '0 8px 24px rgba(255, 215, 0, 0.3)' : 'none',
                      }}
                    >
                      {RankIcon && (
                        <div style={{ marginBottom: 12 }}>
                          <RankIcon size={isFirst ? 32 : 24} color={isFirst ? '#000' : badge.color} />
                        </div>
                      )}
                      <div style={{
                        width: isFirst ? 80 : 64,
                        height: isFirst ? 80 : 64,
                        borderRadius: isFirst ? 40 : 32,
                        background: isFirst ? 'rgba(0,0,0,0.1)' : theme.bg,
                        margin: '0 auto 12',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        border: isFirst ? '2px solid #000' : `2px solid ${badge.color}`,
                        fontSize: isFirst ? 32 : 24,
                        fontWeight: 700,
                        color: isFirst ? '#000' : theme.txt,
                      }}>
                        {entry.username?.[0]?.toUpperCase() || '?'}
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: isFirst ? '#000' : theme.txt, marginBottom: 4 }}>
                        {entry.username || 'Anonymous'}
                      </div>
                      <div style={{ fontSize: isFirst ? 28 : 22, fontWeight: 900, color: isFirst ? '#000' : theme.accent, marginBottom: 4 }}>
                        {entry.total_score || 0}
                      </div>
                      <div style={{ fontSize: 12, color: isFirst ? 'rgba(0,0,0,0.7)' : theme.sub }}>
                        pts {isFirst ? '· Champion' : ''}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* Leaderboard List */}
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))',
              gap: 16,
            }}>
              {filteredEntries
                .filter(entry => entry.rank > 3)
                .map((entry) => {
                  const badge = getRankBadge(entry.rank);

                  return (
                    <div
                      key={entry.id}
                      style={{
                        background: theme.card,
                        borderRadius: 12,
                        padding: 20,
                        border: `1px solid ${theme.border}`,
                        display: 'flex',
                        alignItems: 'center',
                        gap: 16,
                        transition: 'all 0.2s',
                      }}
                    >
                      {/* Rank */}
                      <div style={{
                        width: 48,
                        height: 48,
                        borderRadius: 24,
                        background: theme.bg,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 18,
                        fontWeight: 800,
                        color: theme.sub,
                        flexShrink: 0,
                      }}>
                        #{entry.rank}
                      </div>

                      {/* Avatar */}
                      <div style={{
                        width: 48,
                        height: 48,
                        borderRadius: 24,
                        background: theme.bg,
                        border: `2px solid ${badge?.color || theme.border}`,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: 20,
                        fontWeight: 700,
                        color: theme.txt,
                        flexShrink: 0,
                      }}>
                        {entry.username?.[0]?.toUpperCase() || '?'}
                      </div>

                      {/* Info */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontSize: 15, fontWeight: 700, color: theme.txt, marginBottom: 8 }}>
                          {entry.username || 'Anonymous'}
                        </div>
                        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Heart size={12} color="#EF4444" />
                            <span style={{ fontSize: 12, color: theme.sub }}>{entry.likes_count || 0}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <MessageCircle size={12} color="#888" />
                            <span style={{ fontSize: 12, color: theme.sub }}>{entry.comments_count || 0}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Share2 size={12} color="#3B82F6" />
                            <span style={{ fontSize: 12, color: theme.sub }}>{entry.shares_count || 0}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Gift size={12} color={theme.accent} />
                            <span style={{ fontSize: 12, color: theme.sub }}>{entry.gifts_count || 0}</span>
                          </div>
                        </div>
                      </div>

                      {/* Score */}
                      <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div style={{ fontSize: 20, fontWeight: 900, color: theme.accent }}>
                          {entry.total_score || 0}
                        </div>
                        <div style={{ fontSize: 11, color: theme.sub }}>pts</div>
                      </div>
                    </div>
                  );
                })}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
