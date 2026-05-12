import { useState, useEffect } from 'react';
import { Trophy, Award, Users, Clock, ChevronRight, ChevronLeft, Calendar, Flame } from 'lucide-react';
import api from '../api';
import config from '../config.js';
import { useTheme } from '../contexts/ThemeContext';

const BRAND = '#F9E08B';

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

// Inject animations once
if (!document.head.querySelector('style[data-campaigns-v2]')) {
  const style = document.createElement('style');
  style.setAttribute('data-campaigns-v2', 'true');
  style.textContent = `
    @keyframes camp-shimmer {
      0% { background-position: -1000px 0; }
      100% { background-position: 1000px 0; }
    }
    @keyframes camp-float {
      0%, 100% { transform: translateY(0); }
      50% { transform: translateY(-6px); }
    }
    @keyframes camp-pulse {
      0%, 100% { opacity: 0.8; transform: scale(1); }
      50% { opacity: 1; transform: scale(1.05); }
    }
    @keyframes camp-fade-up {
      from { opacity: 0; transform: translateY(20px); }
      to { opacity: 1; transform: translateY(0); }
    }
    .camp-card {
      animation: camp-fade-up 0.4s ease-out backwards;
      transition: transform 0.3s cubic-bezier(0.4, 0, 0.2, 1), box-shadow 0.3s ease, border-color 0.3s ease;
    }
    .camp-card:hover {
      transform: translateY(-6px);
      box-shadow: 0 20px 40px rgba(249, 224, 139, 0.25), 0 8px 16px rgba(0,0,0,0.1) !important;
    }
    .camp-card:hover .camp-card-img { transform: scale(1.08); }
    .camp-card-img { transition: transform 0.5s cubic-bezier(0.4, 0, 0.2, 1); }
    .camp-cta { transition: transform 0.2s ease, box-shadow 0.2s ease; }
    .camp-cta:hover { transform: translateY(-1px); box-shadow: 0 8px 24px rgba(249, 224, 139, 0.5) !important; }
    .camp-cta:active { transform: translateY(0); }
    .camp-tab { transition: all 0.2s ease; }
    .camp-tab:hover:not(.active) { transform: translateY(-1px); }
  `;
  document.head.appendChild(style);
}

const STATUS_META = {
  active:    { color: '#10B981', label: 'Active', icon: Flame },
  voting:    { color: '#3B82F6', label: 'Voting', icon: Award },
  upcoming:  { color: '#F59E0B', label: 'Soon',   icon: Clock },
  completed: { color: '#94A3B8', label: 'Ended',  icon: Calendar },
};

export function CampaignsPage({ onCampaignClick, onBack }) {
  const { colors: T } = useTheme();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [isMobile, setIsMobile] = useState(window.innerWidth <= 768);

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => { loadCampaigns(); }, [filter]);

  const loadCampaigns = async () => {
    try {
      setLoading(true);
      const status = filter === 'all' ? '' : filter;
      const data = await api.request(`/campaigns/?status=${status}`);
      setCampaigns(Array.isArray(data) ? data : (data.results || []));
    } catch (error) {
      console.error('Failed to load campaigns:', error);
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  };

  const getTimeRemaining = (endDate) => {
    if (!endDate) return '—';
    const diff = new Date(endDate) - new Date();
    if (diff <= 0) return 'Ended';
    const days = Math.floor(diff / 86400000);
    const hours = Math.floor((diff % 86400000) / 3600000);
    if (days > 0) return `${days}d ${hours}h`;
    return `${hours}h`;
  };

  const TABS = [
    { id: 'all',       label: 'All',       icon: Trophy },
    { id: 'active',    label: 'Active',    icon: Flame },
    { id: 'voting',    label: 'Voting',    icon: Award },
    { id: 'upcoming',  label: 'Soon',      icon: Clock },
    { id: 'completed', label: 'Completed', icon: Calendar },
  ];

  return (
    <div style={{
      minHeight: '100vh',
      background: T.bg,
      padding: isMobile ? '0' : '20px 24px',
      boxSizing: 'border-box',
    }}>
      <div style={{ maxWidth: 1200, margin: '0 auto' }}>
        {/* Sticky header on mobile */}
        <div style={{
          position: isMobile ? 'sticky' : 'relative',
          top: 0,
          zIndex: 10,
          background: T.bg,
          padding: isMobile ? '12px 16px 8px' : '0 0 16px',
          borderBottom: isMobile ? `1px solid ${T.border}` : 'none',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <button
              onClick={onBack}
              style={{
                background: 'none', border: 'none', cursor: 'pointer',
                padding: 4, display: 'flex', color: T.txt,
              }}
            >
              <ChevronLeft size={24} strokeWidth={2.5} />
            </button>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <Trophy size={20} color={BRAND} strokeWidth={2.5} />
              <span style={{ fontSize: isMobile ? 18 : 22, fontWeight: 800, color: BRAND }}>
                Campaigns
              </span>
            </div>
          </div>

          {/* Filter pills */}
          <div style={{
            display: 'flex',
            gap: 6,
            overflowX: 'auto',
            paddingBottom: 4,
            scrollbarWidth: 'none',
            msOverflowStyle: 'none',
          }}>
            <style>{`.camp-filter-row::-webkit-scrollbar { display: none; }`}</style>
            <div className="camp-filter-row" style={{ display: 'flex', gap: 6 }}>
              {TABS.map(tab => {
                const Icon = tab.icon;
                const isActive = filter === tab.id;
                return (
                  <button
                    key={tab.id}
                    className={'camp-tab' + (isActive ? ' active' : '')}
                    onClick={() => setFilter(tab.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: 5,
                      padding: '7px 12px', borderRadius: 18,
                      background: isActive ? BRAND : T.cardBg,
                      border: `1.5px solid ${isActive ? BRAND : T.border}`,
                      color: isActive ? '#000' : T.txt,
                      fontSize: 12, fontWeight: 700,
                      cursor: 'pointer', whiteSpace: 'nowrap', flexShrink: 0,
                      boxShadow: isActive ? `0 4px 12px ${BRAND}40` : 'none',
                    }}
                  >
                    <Icon size={13} strokeWidth={2.5} />
                    {tab.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Hero (desktop only) */}
        {!isMobile && (
          <div style={{
            position: 'relative',
            textAlign: 'center',
            margin: '8px 0 24px',
            padding: '28px 20px',
            background: `linear-gradient(135deg, ${BRAND}15, ${BRAND}05)`,
            borderRadius: 16,
            border: `1px solid ${BRAND}25`,
            overflow: 'hidden',
          }}>
            <div style={{
              position: 'absolute', top: -40, right: -40,
              width: 160, height: 160, borderRadius: '50%',
              background: `radial-gradient(circle, ${BRAND}30, transparent 70%)`,
              animation: 'camp-pulse 4s ease-in-out infinite',
            }} />
            <div style={{
              width: 56, height: 56, margin: '0 auto 12px',
              borderRadius: '50%',
              background: `linear-gradient(135deg, ${BRAND}, #F59E0B)`,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: `0 8px 24px ${BRAND}50`,
              animation: 'camp-float 3s ease-in-out infinite',
            }}>
              <Trophy size={28} color="#000" strokeWidth={2.5} />
            </div>
            <h1 style={{ margin: 0, fontSize: 26, fontWeight: 900, color: T.txt, letterSpacing: '-0.02em' }}>
              Win Real Prizes
            </h1>
            <p style={{ margin: '6px 0 0', fontSize: 13, color: T.sub, maxWidth: 480, marginInline: 'auto' }}>
              Join campaigns, submit your best content, and win amazing rewards.
            </p>
          </div>
        )}

        {/* Body */}
        <div style={{ padding: isMobile ? '12px 12px 80px' : '0' }}>
          {loading ? (
            <div style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
            }}>
              {[1, 2, 3, 4].map(i => (
                <div key={i} style={{
                  background: T.cardBg,
                  borderRadius: 14,
                  border: `1px solid ${T.border}`,
                  overflow: 'hidden',
                }}>
                  <div style={{
                    height: 140,
                    background: `linear-gradient(90deg, ${T.bg} 0%, ${T.border} 50%, ${T.bg} 100%)`,
                    backgroundSize: '1000px 100%',
                    animation: 'camp-shimmer 2s infinite',
                  }} />
                  <div style={{ padding: 14 }}>
                    <div style={{
                      height: 14, width: '70%', borderRadius: 6, marginBottom: 8,
                      background: `linear-gradient(90deg, ${T.bg} 0%, ${T.border} 50%, ${T.bg} 100%)`,
                      backgroundSize: '1000px 100%', animation: 'camp-shimmer 2s infinite',
                    }} />
                    <div style={{
                      height: 36, borderRadius: 8,
                      background: `linear-gradient(90deg, ${T.bg} 0%, ${T.border} 50%, ${T.bg} 100%)`,
                      backgroundSize: '1000px 100%', animation: 'camp-shimmer 2s infinite',
                    }} />
                  </div>
                </div>
              ))}
            </div>
          ) : campaigns.length === 0 ? (
            <div style={{
              padding: '60px 20px',
              textAlign: 'center',
              background: T.cardBg,
              borderRadius: 14,
              border: `1px dashed ${T.border}`,
            }}>
              <div style={{
                width: 64, height: 64, margin: '0 auto 12px',
                borderRadius: '50%',
                background: `${BRAND}15`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Trophy size={28} color={BRAND} />
              </div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: T.txt }}>
                No {filter !== 'all' ? filter : ''} campaigns
              </h3>
              <p style={{ margin: '6px 0 0', fontSize: 13, color: T.sub }}>
                Check back later for new opportunities!
              </p>
            </div>
          ) : (
            <div style={{
              display: 'grid',
              gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(290px, 1fr))',
              gap: 14,
            }}>
              {campaigns.map((campaign, idx) => {
                const meta = STATUS_META[campaign.status] || STATUS_META.completed;
                const StatusIcon = meta.icon;

                return (
                  <div
                    key={campaign.id}
                    className="camp-card"
                    onClick={() => onCampaignClick?.(campaign.id)}
                    style={{
                      background: T.cardBg,
                      borderRadius: 14,
                      overflow: 'hidden',
                      border: `1px solid ${T.border}`,
                      cursor: 'pointer',
                      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
                      animationDelay: `${Math.min(idx, 6) * 50}ms`,
                    }}
                  >
                    {/* Image / Gradient header */}
                    <div style={{
                      width: '100%',
                      height: 150,
                      position: 'relative',
                      overflow: 'hidden',
                      background: campaign.image
                        ? '#000'
                        : `linear-gradient(135deg, ${BRAND}30, #F59E0B30)`,
                    }}>
                      {campaign.image ? (
                        <div className="camp-card-img" style={{
                          width: '100%', height: '100%',
                          background: `url(${mediaUrl(campaign.image)}) center/cover`,
                        }} />
                      ) : (
                        <div style={{
                          width: '100%', height: '100%',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                        }}>
                          <Trophy size={56} color={BRAND} opacity={0.5} strokeWidth={1.5} />
                        </div>
                      )}

                      {/* Gradient overlay */}
                      <div style={{
                        position: 'absolute', inset: 0,
                        background: 'linear-gradient(180deg, transparent 50%, rgba(0,0,0,0.55) 100%)',
                      }} />

                      {/* Status pill */}
                      <div style={{
                        position: 'absolute', top: 10, left: 10,
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '4px 10px', borderRadius: 12,
                        background: meta.color,
                        color: '#fff',
                        fontSize: 10, fontWeight: 800,
                        textTransform: 'uppercase', letterSpacing: '0.5px',
                        boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
                      }}>
                        <StatusIcon size={10} strokeWidth={3} />
                        {meta.label}
                      </div>

                      {/* Campaign type pill */}
                      {campaign.campaign_type && (
                        <div style={{
                          position: 'absolute', top: 10, right: 10,
                          padding: '4px 10px', borderRadius: 12,
                          background: 'rgba(0,0,0,0.6)',
                          backdropFilter: 'blur(8px)',
                          color: '#fff',
                          fontSize: 10, fontWeight: 700,
                          textTransform: 'capitalize', letterSpacing: '0.3px',
                        }}>
                          {campaign.campaign_type}
                        </div>
                      )}

                      {/* Time left badge */}
                      <div style={{
                        position: 'absolute', bottom: 10, right: 10,
                        display: 'flex', alignItems: 'center', gap: 4,
                        padding: '4px 10px', borderRadius: 12,
                        background: 'rgba(0,0,0,0.6)',
                        backdropFilter: 'blur(8px)',
                        color: '#fff', fontSize: 11, fontWeight: 700,
                      }}>
                        <Clock size={11} strokeWidth={2.5} />
                        {getTimeRemaining(campaign.voting_end || campaign.entry_deadline)}
                      </div>
                    </div>

                    {/* Content */}
                    <div style={{ padding: 14 }}>
                      <h3 style={{
                        margin: 0,
                        fontSize: 15, fontWeight: 800,
                        color: T.txt, lineHeight: 1.3,
                        marginBottom: 6,
                        display: '-webkit-box',
                        WebkitLineClamp: 1,
                        WebkitBoxOrient: 'vertical',
                        overflow: 'hidden',
                      }}>
                        {campaign.title}
                      </h3>

                      {campaign.description && (
                        <p style={{
                          margin: 0,
                          fontSize: 12, color: T.sub,
                          lineHeight: 1.5,
                          marginBottom: 10,
                          display: '-webkit-box',
                          WebkitLineClamp: 2,
                          WebkitBoxOrient: 'vertical',
                          overflow: 'hidden',
                        }}>
                          {campaign.description}
                        </p>
                      )}

                      {/* Prize */}
                      <div style={{
                        display: 'flex', alignItems: 'center', gap: 10,
                        padding: '10px 12px',
                        background: `linear-gradient(135deg, ${BRAND}18, ${BRAND}08)`,
                        border: `1px solid ${BRAND}30`,
                        borderRadius: 10,
                        marginBottom: 10,
                      }}>
                        <div style={{
                          width: 32, height: 32, borderRadius: '50%',
                          background: `linear-gradient(135deg, ${BRAND}, #F59E0B)`,
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          flexShrink: 0,
                          boxShadow: `0 2px 8px ${BRAND}50`,
                        }}>
                          <Award size={16} color="#000" strokeWidth={2.5} />
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{
                            fontSize: 9, color: T.sub, fontWeight: 700,
                            textTransform: 'uppercase', letterSpacing: '0.5px',
                          }}>
                            Prize
                          </div>
                          <div style={{
                            fontSize: 16, fontWeight: 900,
                            color: BRAND, lineHeight: 1.1,
                          }}>
                            {campaign.prize_value ? `${campaign.prize_value} ETB` : (campaign.prize_title || '—')}
                          </div>
                        </div>
                      </div>

                      {/* Stats row */}
                      <div style={{
                        display: 'flex',
                        gap: 8,
                        marginBottom: 12,
                      }}>
                        <div style={{ flex: 1, textAlign: 'center', padding: '6px 4px', background: T.bg, borderRadius: 8 }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: T.txt }}>
                            {campaign.total_entries || 0}
                          </div>
                          <div style={{ fontSize: 9, color: T.sub, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                            Entries
                          </div>
                        </div>
                        <div style={{ flex: 1, textAlign: 'center', padding: '6px 4px', background: T.bg, borderRadius: 8 }}>
                          <div style={{ fontSize: 14, fontWeight: 800, color: T.txt }}>
                            {campaign.total_votes || 0}
                          </div>
                          <div style={{ fontSize: 9, color: T.sub, fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.4px' }}>
                            Votes
                          </div>
                        </div>
                      </div>

                      {/* CTA */}
                      <button
                        className="camp-cta"
                        style={{
                          width: '100%', padding: '10px',
                          background: BRAND,
                          border: 'none', borderRadius: 10,
                          color: '#000',
                          fontSize: 13, fontWeight: 800,
                          cursor: 'pointer',
                          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
                          boxShadow: `0 4px 12px ${BRAND}40`,
                        }}
                      >
                        View Campaign
                        <ChevronRight size={16} strokeWidth={3} />
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}




