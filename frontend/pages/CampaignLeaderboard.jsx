import React, { useState, useEffect } from 'react';
import api from '../api';
import config from '../config';
import { ArrowLeft, Trophy, Medal, TrendingUp, Crown, Heart, MessageCircle, Share2, Gift } from 'lucide-react';
import { useTheme } from '../contexts/ThemeContext';

const BACKEND = config.API_BASE_URL.replace('/api', '');

function mediaUrl(url) {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return BACKEND + url;
}

const PERIODS = [
  { id: 'daily', label: 'Today' },
  { id: 'weekly', label: 'This Week' },
  { id: 'monthly', label: 'This Month' },
  { id: 'overall', label: 'All Time' },
];

const MEDAL = { 1: '#FFD700', 2: '#A8A8A8', 3: '#CD7F32' };

const CampaignLeaderboard = ({ campaignId, onBack }) => {
  const { colors: T } = useTheme();
  const [loading, setLoading] = useState(true);
  const [campaign, setCampaign] = useState(null);
  const [period, setPeriod] = useState('overall');
  const [leaderboard, setLeaderboard] = useState([]);

  useEffect(() => { loadData(); }, [campaignId, period]);

  const loadData = async () => {
    try {
      setLoading(true);
      const [campaignRes, lbRes] = await Promise.all([
        api.request(`/campaigns/${campaignId}/`),
        api.request(`/campaigns/${campaignId}/leaderboard/?period=${period}`)
      ]);
      setCampaign(campaignRes);
      setLeaderboard(lbRes.entries || []);
    } catch (err) {
      console.error('Error loading leaderboard:', err);
    } finally {
      setLoading(false);
    }
  };

  const top3 = leaderboard.slice(0, 3);
  const rest = leaderboard.slice(3);

  return (
    <div style={{ minHeight: '100vh', background: T.bg, boxSizing: 'border-box' }}>
      {/* Header */}
      <div style={{
        background: T.card, borderBottom: `1px solid ${T.border}`,
        padding: '16px 24px',
      }}>
        <div style={{ maxWidth: 700, margin: '0 auto' }}>
          <button
            onClick={() => onBack?.()}
            style={{
              display: 'flex', alignItems: 'center', gap: 6,
              background: 'transparent', border: 'none', cursor: 'pointer',
              color: T.sub, fontSize: 14, fontWeight: 600, padding: '4px 0', marginBottom: 10,
            }}
          >
            <ArrowLeft size={16} /> Back to Campaign
          </button>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 14 }}>
            <div style={{
              width: 40, height: 40, borderRadius: '50%', flexShrink: 0,
              background: `linear-gradient(135deg, ${T.pri}, #8fc441)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <TrendingUp size={20} color="#fff" />
            </div>
            <div>
              <h1 style={{ margin: 0, fontSize: 20, fontWeight: 800, color: T.txt }}>Leaderboard</h1>
              <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 2 }}>
                <p style={{ margin: 0, fontSize: 13, color: T.sub }}>{campaign?.title}</p>
                {campaign?.campaign_type && (
                  <span style={{
                    padding: '2px 6px',
                    background: `${T.pri}15`,
                    color: T.pri,
                    borderRadius: 4,
                    fontSize: 10,
                    fontWeight: 700,
                    textTransform: 'uppercase',
                  }}>
                    {campaign.campaign_type === 'grand' ? 'Grand' : 
                     campaign.campaign_type === 'daily' ? 'Daily' : 
                     campaign.campaign_type === 'weekly' ? 'Weekly' : 'Monthly'}
                  </span>
                )}
              </div>
            </div>
          </div>
          {/* Period tabs */}
          <div style={{ display: 'flex', gap: 6, overflowX: 'auto' }}>
            {PERIODS.map(p => (
              <button
                key={p.id}
                onClick={() => setPeriod(p.id)}
                style={{
                  padding: '7px 16px',
                  background: period === p.id ? T.pri : T.card,
                  color: period === p.id ? '#fff' : T.sub,
                  border: `1.5px solid ${period === p.id ? T.pri : T.border}`,
                  borderRadius: 20, cursor: 'pointer',
                  fontSize: 13, fontWeight: 600, whiteSpace: 'nowrap',
                }}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div style={{ maxWidth: 700, margin: '0 auto', padding: '24px 24px 60px' }}>
        {loading ? (
          <div style={{ textAlign: 'center', padding: '60px 0', color: T.sub, fontSize: 15 }}>
            Loading rankings...
          </div>
        ) : leaderboard.length === 0 ? (
          <div style={{
            background: T.card, borderRadius: 14, padding: '48px 24px',
            textAlign: 'center', border: `1px solid ${T.border}`,
          }}>
            <Trophy size={44} color={T.pri} style={{ marginBottom: 16, opacity: 0.4 }} />
            <h3 style={{ margin: '0 0 8px', fontSize: 18, fontWeight: 700, color: T.txt }}>No Rankings Yet</h3>
            <p style={{ margin: 0, color: T.sub, fontSize: 14 }}>Be the first to participate!</p>
          </div>
        ) : (
          <>
            {/* Podium – top 3 */}
            {top3.length >= 1 && (
              <div style={{
                background: T.card, borderRadius: 14, border: `1px solid ${T.border}`,
                padding: '28px 24px 24px', marginBottom: 16,
              }}>
                <p style={{ margin: '0 0 20px', fontSize: 13, fontWeight: 700, color: T.sub, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                  Top Performers
                </p>
                <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'center', gap: 16 }}>
                  {/* 2nd */}
                  {top3[1] && (
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{
                        width: 64, height: 64, borderRadius: '50%', margin: '0 auto 10px',
                        background: `linear-gradient(135deg, #A8A8A8, #D0D0D0)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 26, fontWeight: 800, color: '#fff',
                        border: '3px solid #A8A8A8',
                        overflow: 'hidden',
                      }}>
                        {top3[1].profile_photo ? (
                          <img src={mediaUrl(top3[1].profile_photo)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          top3[1].username?.[0]?.toUpperCase()
                        )}
                      </div>
                      <Medal size={18} color="#A8A8A8" style={{ marginBottom: 4 }} />
                      <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 2 }}>{top3[1].username}</div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: '#A8A8A8' }}>{top3[1].total_score || top3[1].score}</div>
                      <div style={{ fontSize: 11, color: T.sub }}>pts</div>
                    </div>
                  )}
                  {/* 1st */}
                  {top3[0] && (
                    <div style={{ flex: 1, textAlign: 'center', marginBottom: 12 }}>
                      <Crown size={28} color="#FFD700" style={{ marginBottom: 6 }} />
                      <div style={{
                        width: 80, height: 80, borderRadius: '50%', margin: '0 auto 10px',
                        background: `linear-gradient(135deg, ${T.pri}, #8fc441)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 32, fontWeight: 800, color: '#fff',
                        border: `4px solid ${T.pri}`,
                        boxShadow: `0 8px 24px ${T.pri}50`,
                        overflow: 'hidden',
                      }}>
                        {top3[0].profile_photo ? (
                          <img src={mediaUrl(top3[0].profile_photo)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          top3[0].username?.[0]?.toUpperCase()
                        )}
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 800, color: T.txt, marginBottom: 2 }}>{top3[0].username}</div>
                      <div style={{ fontSize: 22, fontWeight: 900, color: '#fff' }}>{top3[0].total_score || top3[0].score}</div>
                      <div style={{ fontSize: 11, color: T.sub }}>pts · Champion</div>
                    </div>
                  )}
                  {/* 3rd */}
                  {top3[2] && (
                    <div style={{ flex: 1, textAlign: 'center' }}>
                      <div style={{
                        width: 64, height: 64, borderRadius: '50%', margin: '0 auto 10px',
                        background: `linear-gradient(135deg, #CD7F32, #E5A572)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 26, fontWeight: 800, color: '#fff',
                        border: '3px solid #CD7F32',
                        overflow: 'hidden',
                      }}>
                        {top3[2].profile_photo ? (
                          <img src={mediaUrl(top3[2].profile_photo)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          top3[2].username?.[0]?.toUpperCase()
                        )}
                      </div>
                      <Medal size={18} color="#CD7F32" style={{ marginBottom: 4 }} />
                      <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 2 }}>{top3[2].username}</div>
                      <div style={{ fontSize: 18, fontWeight: 800, color: '#CD7F32' }}>{top3[2].total_score || top3[2].score}</div>
                      <div style={{ fontSize: 11, color: T.sub }}>pts</div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* Full list */}
            {leaderboard.length > 0 && (
              <div style={{ background: T.card, borderRadius: 14, border: `1px solid ${T.border}`, overflow: 'hidden' }}>
                {leaderboard.map((entry, idx) => {
                  const rank = entry.rank || idx + 1;
                  const medalColor = MEDAL[rank];
                  return (
                    <div
                      key={entry.user_id || idx}
                      style={{
                        display: 'flex', alignItems: 'center', gap: 14,
                        padding: '14px 18px',
                        borderBottom: idx < leaderboard.length - 1 ? `1px solid ${T.border}` : 'none',
                        background: rank === 1 ? `${T.pri}08` : T.card,
                      }}
                    >
                      {/* Rank number */}
                      <div style={{ width: 32, textAlign: 'center', flexShrink: 0 }}>
                        {rank <= 3 ? (
                          rank === 1 ? <Trophy size={20} color="#FFD700" /> :
                          rank === 2 ? <Medal size={20} color="#A8A8A8" /> :
                                       <Medal size={20} color="#CD7F32" />
                        ) : (
                          <span style={{ fontSize: 15, fontWeight: 700, color: T.sub }}>#{rank}</span>
                        )}
                      </div>
                      {/* Avatar */}
                      <div style={{
                        width: 38, height: 38, borderRadius: '50%', flexShrink: 0,
                        background: medalColor
                          ? `linear-gradient(135deg, ${medalColor}, ${medalColor}bb)`
                          : `linear-gradient(135deg, ${T.pri}60, #8fc44160)`,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        color: '#fff', fontSize: 15, fontWeight: 800,
                        overflow: 'hidden',
                      }}>
                        {entry.profile_photo ? (
                          <img src={mediaUrl(entry.profile_photo)} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
                        ) : (
                          entry.username?.[0]?.toUpperCase()
                        )}
                      </div>
                      {/* Name */}
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div style={{ fontWeight: 700, fontSize: 15, color: T.txt, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {entry.username}
                        </div>
                        <div style={{ display: 'flex', gap: 10, marginTop: 4, flexWrap: 'wrap' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Heart size={11} color="#EF4444" />
                            <span style={{ fontSize: 12, color: T.sub }}>{entry.likes_count === 0 ? 1 : entry.likes_count}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <MessageCircle size={11} color="#888" />
                            <span style={{ fontSize: 12, color: T.sub }}>{entry.comments_count === 0 ? 1 : entry.comments_count}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Share2 size={11} color="#3B82F6" />
                            <span style={{ fontSize: 12, color: T.sub }}>{entry.shares_count === 0 ? 1 : entry.shares_count}</span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                            <Gift size={11} color="#8fc441" />
                            <span style={{ fontSize: 12, color: T.sub }}>{entry.gifts_count === 0 ? 1 : entry.gifts_count}</span>
                          </div>
                          {entry.post_count > 0 && (
                            <span style={{ fontSize: 12, color: T.sub }}>{entry.post_count} posts</span>
                          )}
                        </div>
                      </div>
                      {/* Score */}
                      <div style={{ textAlign: 'right', flexShrink: 0 }}>
                        <div style={{ fontSize: 18, fontWeight: 800, color: rank <= 3 ? T.pri : T.txt }}>
                          {(entry.total_score || entry.score) === 0 ? 1 : (entry.total_score || entry.score)}
                        </div>
                        <div style={{ fontSize: 11, color: T.sub }}>points</div>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
};

export default CampaignLeaderboard;




