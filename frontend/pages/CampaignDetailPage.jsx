import { useState, useEffect } from 'react';
import { Trophy, Calendar, Award, Users, Clock, Upload, Video, Check, X, Heart, Share2, ArrowLeft, AlertCircle, Star, Zap, TrendingUp, Medal, Crown, Target, Flame, List, BarChart3, FileText, MessageCircle, ChevronDown, Gift } from 'lucide-react';
import api from '../api';
import config from '../config.js';
import { useTheme } from '../contexts/ThemeContext';

const mediaUrl = (url) => {
  if (!url) return null;
  if (url.startsWith('http')) return url;
  return `${config.API_BASE_URL.replace('/api', '')}${url}`;
};

export function CampaignDetailPage({ campaignId, onBack, onShowLeaderboard, onShowFeed }) {
  const { colors: T } = useTheme();
  const [campaign, setCampaign] = useState(null);
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showSubmitModal, setShowSubmitModal] = useState(false);
  const [userEntry, setUserEntry] = useState(null);
  const [isMobile, setIsMobile] = useState(typeof window !== 'undefined' && window.innerWidth <= 768);
  const [openSections, setOpenSections] = useState({ desc: true, reqs: false, timeline: false, scoring: false });

  useEffect(() => {
    const onResize = () => setIsMobile(window.innerWidth <= 768);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  useEffect(() => {
    if (campaignId) {
      loadCampaignDetails();
    }
  }, [campaignId]);

  const loadCampaignDetails = async () => {
    try {
      setLoading(true);
      const data = await api.request(`/campaigns/${campaignId}/`);
      setCampaign(data);
      setEntries(data.entries || []);
      // Check if user has already entered
      const userHasEntered = data.entries?.some(entry => entry.user?.id === data.current_user_id);
      setUserEntry(userHasEntered ? data.entries.find(entry => entry.user?.id === data.current_user_id) : null);
    } catch (error) {
      console.error('Failed to load campaign:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleVote = async (entryId) => {
    try {
      await api.request(`/campaigns/entries/${entryId}/vote/`, {
        method: 'POST'
      });
      // Reload to get updated rankings
      loadCampaignDetails();
    } catch (error) {
      console.error('Failed to vote:', error);
      alert(error.message || 'Failed to vote. Please try again.');
    }
  };

  const formatDate = (dateString) => {
    if (!dateString) return 'N/A';
    const date = new Date(dateString);
    
    // Validate date
    if (isNaN(date.getTime())) {
      console.warn('Invalid date:', dateString);
      return 'N/A';
    }
    
    return date.toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' });
  };

  const getTimeRemaining = (endDate) => {
    if (!endDate) return 'N/A';
    const now = new Date();
    const end = new Date(endDate);
    
    // Validate date
    if (isNaN(end.getTime())) {
      console.warn('Invalid end date:', endDate);
      return 'N/A';
    }
    
    const diff = end - now;
    
    if (diff <= 0) return 'Ended';
    
    const days = Math.floor(diff / (1000 * 60 * 60 * 24));
    const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
    
    if (days > 0) return `${days} days ${hours} hours`;
    return `${hours} hours`;
  };

  const canSubmit = () => {
    if (!campaign) return false;
    const now = new Date();
    const start = new Date(campaign.start_date);
    const deadline = new Date(campaign.entry_deadline);
    
    // Validate dates
    if (isNaN(start.getTime()) || isNaN(deadline.getTime())) {
      console.warn('Invalid campaign dates:', { start_date: campaign.start_date, entry_deadline: campaign.entry_deadline });
      return false;
    }
    
    return campaign.status === 'active' && now >= start && now <= deadline && !userEntry;
  };

  const canVote = () => {
    if (!campaign) return false;
    const now = new Date();
    const votingStart = new Date(campaign.voting_start);
    const votingEnd = new Date(campaign.voting_end);
    
    // Validate dates
    if (isNaN(votingStart.getTime()) || isNaN(votingEnd.getTime())) {
      console.warn('Invalid voting dates:', { voting_start: campaign.voting_start, voting_end: campaign.voting_end });
      return false;
    }
    
    return campaign.status === 'voting' && now >= votingStart && now <= votingEnd;
  };

  if (loading) {
    return (
      <div style={{
        minHeight: '100vh',
        background: T.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <div style={{ color: T.sub }}>Loading campaign...</div>
      </div>
    );
  }

  if (!campaign) {
    return (
      <div style={{
        minHeight: '100vh',
        background: T.bg,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}>
        <div style={{ textAlign: 'center' }}>
          <AlertCircle size={48} color={T.red} style={{ marginBottom: 16 }} />
          <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: T.txt, marginBottom: 8 }}>
            Campaign Not Found
          </h2>
          <button
            onClick={onBack}
            style={{
              marginTop: 16,
              padding: '12px 24px',
              background: T.pri,
              border: 'none',
              borderRadius: 8,
              color: '#fff',
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Back to Campaigns
          </button>
        </div>
      </div>
    );
  }

  const BRAND = '#b8d97a';
  const toggleSection = (k) => setOpenSections(s => ({ ...s, [k]: !s[k] }));

  const Accordion = ({ id, icon: Icon, title, subtitle, children, defaultColor }) => {
    const open = openSections[id];
    return (
      <div style={{
        background: T.cardBg || '#fff',
        borderRadius: 12,
        border: `1px solid ${T.border}`,
        overflow: 'hidden',
        marginBottom: 10,
      }}>
        <button
          onClick={() => toggleSection(id)}
          style={{
            width: '100%',
            display: 'flex', alignItems: 'center', gap: 12,
            padding: '14px 16px',
            background: 'none', border: 'none', cursor: 'pointer',
            textAlign: 'left',
          }}
        >
          <div style={{
            width: 32, height: 32, borderRadius: 10,
            background: (defaultColor || BRAND) + '22',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <Icon size={16} color={defaultColor || BRAND} strokeWidth={2.5} />
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.txt }}>{title}</div>
            {subtitle && <div style={{ fontSize: 11, color: T.sub, marginTop: 2 }}>{subtitle}</div>}
          </div>
          <div style={{
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.25s ease',
            color: T.sub,
            display: 'flex',
          }}>
            <ChevronDown size={18} />
          </div>
        </button>
        {open && (
          <div style={{ padding: '0 16px 16px', borderTop: `1px solid ${T.border}` }}>
            <div style={{ paddingTop: 12 }}>{children}</div>
          </div>
        )}
      </div>
    );
  };

  const hasRequirements = (campaign.min_followers > 0 || campaign.min_level > 0 || campaign.min_votes_per_reel > 0 || campaign.required_hashtags || campaign.winner_count > 0);

  const CTAButton = () => {
    if (canSubmit()) {
      return (
        <button
          onClick={() => {
            if (!api.hasToken()) { alert('Please log in to submit an entry.'); return; }
            setShowSubmitModal(true);
          }}
          style={{
            width: '100%',
            padding: '14px',
            background: `linear-gradient(135deg, ${BRAND}, #8fc441)`,
            border: 'none', borderRadius: 12,
            color: '#000', fontSize: 15, fontWeight: 800,
            cursor: 'pointer',
            display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
            boxShadow: `0 6px 20px ${BRAND}55`,
          }}
        >
          <Upload size={18} strokeWidth={2.5} />
          Join Campaign
        </button>
      );
    }
    if (userEntry) {
      return (
        <div style={{
          width: '100%', padding: '12px 16px',
          background: 'rgba(16,185,129,0.15)',
          border: '1.5px solid #10B981',
          borderRadius: 12,
          color: '#10B981',
          fontSize: 14, fontWeight: 700,
          display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
        }}>
          <Check size={16} strokeWidth={3} />
          You're in! Rank #{userEntry.rank || '—'}
        </div>
      );
    }
    return (
      <div style={{
        width: '100%', padding: '12px 16px',
        background: T.bg,
        border: `1.5px solid ${T.border}`,
        borderRadius: 12,
        color: T.sub,
        fontSize: 14, fontWeight: 700,
        display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 8,
      }}>
        <AlertCircle size={16} />
        {campaign.status === 'completed' ? 'Campaign Ended' : campaign.status === 'upcoming' ? 'Starts Soon' : 'Not Accepting Entries'}
      </div>
    );
  };

  return (
    <div style={{
      minHeight: '100vh',
      background: T.bg,
      padding: isMobile ? '0 0 100px' : '16px 24px 80px',
      boxSizing: 'border-box',
    }}>
      <div style={{ maxWidth: 820, margin: '0 auto' }}>
        {/* Sticky Header */}
        <div style={{
          position: 'sticky', top: 0, zIndex: 20,
          background: T.bg,
          padding: isMobile ? '10px 12px' : '0 0 12px',
          borderBottom: isMobile ? `1px solid ${T.border}` : 'none',
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <button
            onClick={onBack}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              padding: 4, display: 'flex', color: T.txt, flexShrink: 0,
            }}
          >
            <ArrowLeft size={22} strokeWidth={2.5} />
          </button>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{
              fontSize: isMobile ? 15 : 17, fontWeight: 800, color: T.txt,
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {campaign.title}
            </div>
          </div>
          <div style={{
            padding: '4px 10px', borderRadius: 10,
            background: campaign.status === 'active' ? 'rgba(16,185,129,0.15)' :
                        campaign.status === 'voting' ? 'rgba(59,130,246,0.15)' :
                        campaign.status === 'upcoming' ? 'rgba(245,158,11,0.15)' : 'rgba(148,163,184,0.15)',
            color: campaign.status === 'active' ? '#10B981' :
                   campaign.status === 'voting' ? '#3B82F6' :
                   campaign.status === 'upcoming' ? '#8fc441' : '#94A3B8',
            fontSize: 10, fontWeight: 800,
            textTransform: 'uppercase', letterSpacing: '0.5px',
            flexShrink: 0,
          }}>
            {campaign.status}
          </div>
        </div>

        <div style={{ padding: isMobile ? '12px' : '0' }}>
          {/* HERO: Image + Prize overlay */}
          <div style={{
            position: 'relative',
            borderRadius: 16,
            overflow: 'hidden',
            marginBottom: 14,
            border: `1px solid ${T.border}`,
            background: campaign.image ? '#000' : `linear-gradient(135deg, ${BRAND}30, #8fc44130)`,
            aspectRatio: isMobile ? '16/10' : '16/7',
          }}>
            {campaign.image ? (
              <div style={{
                position: 'absolute', inset: 0,
                background: `url(${mediaUrl(campaign.image)}) center/cover`,
              }} />
            ) : (
              <div style={{
                position: 'absolute', inset: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <Trophy size={64} color={BRAND} opacity={0.4} strokeWidth={1.5} />
              </div>
            )}
            <div style={{
              position: 'absolute', inset: 0,
              background: 'linear-gradient(180deg, rgba(0,0,0,0.1) 0%, rgba(0,0,0,0.75) 100%)',
            }} />
            {/* Prize overlay */}
            <div style={{
              position: 'absolute', bottom: 0, left: 0, right: 0,
              padding: '14px 16px',
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <div style={{
                width: 42, height: 42, borderRadius: '50%',
                background: `linear-gradient(135deg, ${BRAND}, #8fc441)`,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                boxShadow: `0 4px 16px ${BRAND}70`,
                flexShrink: 0,
              }}>
                <Award size={22} color="#000" strokeWidth={2.5} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{
                  fontSize: 10, color: 'rgba(255,255,255,0.8)',
                  fontWeight: 700, textTransform: 'uppercase', letterSpacing: '1px',
                }}>
                  Prize Pool
                </div>
                <div style={{
                  fontSize: 22, fontWeight: 900,
                  color: BRAND, lineHeight: 1.1,
                }}>
                  {campaign.prize_value ? `${campaign.prize_value} ETB` : (campaign.prize_title || '—')}
                </div>
              </div>
              <div style={{
                display: 'flex', alignItems: 'center', gap: 5,
                padding: '6px 10px', borderRadius: 10,
                background: 'rgba(0,0,0,0.5)', backdropFilter: 'blur(8px)',
                color: '#fff', fontSize: 11, fontWeight: 800,
                flexShrink: 0,
              }}>
                <Clock size={12} strokeWidth={2.5} />
                {getTimeRemaining(campaign.voting_end || campaign.entry_deadline)}
              </div>
            </div>
          </div>

          {/* Quick Stats Row */}
          <div style={{
            display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
            gap: 8, marginBottom: 14,
          }}>
            {[
              { label: 'Entries',    value: campaign.total_entries || 0, color: '#3B82F6', icon: Users },
              { label: 'Total Votes', value: campaign.total_votes || 0,   color: '#EF4444', icon: Flame },
              { label: 'Winners',    value: campaign.winner_count || 1,  color: BRAND,     icon: Crown },
            ].map((s, i) => {
              const I = s.icon;
              return (
                <div key={i} style={{
                  padding: '10px 8px',
                  background: T.cardBg || '#fff',
                  borderRadius: 10,
                  border: `1px solid ${T.border}`,
                  textAlign: 'center',
                }}>
                  <div style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    gap: 4, marginBottom: 4,
                  }}>
                    <I size={11} color={s.color} strokeWidth={2.5} />
                    <span style={{ fontSize: 9, color: T.sub, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                      {s.label}
                    </span>
                  </div>
                  <div style={{ fontSize: 16, fontWeight: 900, color: s.color }}>
                    {s.value}
                  </div>
                </div>
              );
            })}
          </div>

          {/* Primary CTA */}
          <div style={{ marginBottom: 14 }}>
            <CTAButton />
          </div>

          {/* Secondary actions */}
          <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <button
              onClick={() => onShowLeaderboard?.()}
              style={{
                flex: 1, padding: '10px 12px',
                background: T.cardBg || '#fff',
                border: `1px solid ${T.border}`,
                borderRadius: 10,
                color: T.txt, fontSize: 13, fontWeight: 700,
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              <BarChart3 size={15} />
              Leaderboard
            </button>
            <button
              onClick={() => onShowFeed?.()}
              style={{
                flex: 1, padding: '10px 12px',
                background: T.cardBg || '#fff',
                border: `1px solid ${T.border}`,
                borderRadius: 10,
                color: T.txt, fontSize: 13, fontWeight: 700,
                cursor: 'pointer',
                display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 6,
              }}
            >
              <List size={15} />
              Feed
            </button>
          </div>

          {/* Your entry (compact) */}
          {userEntry && (
            <div style={{
              background: 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(249,224,139,0.08))',
              border: '1.5px solid #10B981',
              borderRadius: 12,
              padding: 14,
              marginBottom: 14,
              display: 'flex', alignItems: 'center', gap: 12,
            }}>
              <div style={{
                width: 38, height: 38, borderRadius: '50%',
                background: '#10B981',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                flexShrink: 0,
              }}>
                <Check size={18} color="#fff" strokeWidth={3} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 14, fontWeight: 800, color: T.txt }}>
                  Your Entry is Live 🎉
                </div>
                <div style={{ fontSize: 11, color: T.sub, marginTop: 2 }}>
                  {userEntry.vote_count || 0} votes · Rank #{userEntry.rank || '—'}
                </div>
              </div>
            </div>
          )}

          {/* ─── ACCORDIONS ──────────────────────────── */}

          <Accordion id="desc" icon={FileText} title="About this Campaign" subtitle="Description & rules" defaultColor={BRAND}>
            <p style={{ margin: 0, fontSize: 13, color: T.sub, lineHeight: 1.6, whiteSpace: 'pre-wrap' }}>
              {campaign.description || 'No description provided.'}
            </p>
            <div style={{
              marginTop: 12, padding: 10,
              background: `${BRAND}15`, borderRadius: 8,
              fontSize: 11, color: T.txt, lineHeight: 1.5,
              display: 'flex', alignItems: 'flex-start', gap: 8,
            }}>
              <Target size={14} color={BRAND} style={{ flexShrink: 0, marginTop: 1 }} />
              <span>
                Type: <b>{campaign.campaign_type === 'grand' ? 'Grand Campaign' : campaign.campaign_type === 'daily' ? 'Daily' : campaign.campaign_type === 'weekly' ? 'Weekly' : 'Monthly'}</b>
                {campaign.prize_title && <> · <b>{campaign.prize_title}</b></>}
              </span>
            </div>
          </Accordion>

          {hasRequirements && (
            <Accordion id="reqs" icon={Target} title="Entry Requirements" subtitle="What you need to qualify" defaultColor="#3B82F6">
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                {campaign.required_hashtags && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: T.bg, borderRadius: 8 }}>
                    <span style={{ fontSize: 11, color: T.sub, fontWeight: 600, minWidth: 110 }}>Required tags</span>
                    <span style={{ fontSize: 13, fontWeight: 700, color: BRAND }}>{campaign.required_hashtags}</span>
                  </div>
                )}
                {campaign.min_followers > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: T.bg, borderRadius: 8 }}>
                    <span style={{ fontSize: 11, color: T.sub, fontWeight: 600, minWidth: 110 }}>Min followers</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#3B82F6' }}>{campaign.min_followers}+</span>
                  </div>
                )}
                {campaign.min_level > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: T.bg, borderRadius: 8 }}>
                    <span style={{ fontSize: 11, color: T.sub, fontWeight: 600, minWidth: 110 }}>Min level</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#8fc441' }}>Level {campaign.min_level}</span>
                  </div>
                )}
                {campaign.min_votes_per_reel > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: T.bg, borderRadius: 8 }}>
                    <span style={{ fontSize: 11, color: T.sub, fontWeight: 600, minWidth: 110 }}>Min votes/reel</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#EF4444' }}>{campaign.min_votes_per_reel}+</span>
                  </div>
                )}
                {campaign.winner_count > 0 && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '8px 10px', background: T.bg, borderRadius: 8 }}>
                    <span style={{ fontSize: 11, color: T.sub, fontWeight: 600, minWidth: 110 }}>Winners</span>
                    <span style={{ fontSize: 13, fontWeight: 800, color: '#10B981' }}>{campaign.winner_count}</span>
                  </div>
                )}
              </div>
            </Accordion>
          )}

          <Accordion id="timeline" icon={Calendar} title="Timeline" subtitle="Key dates" defaultColor="#8B5CF6">
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
              {[
                { label: 'Starts',          date: campaign.start_date,      color: '#10B981' },
                { label: 'Entry Deadline',  date: campaign.entry_deadline,  color: '#8fc441' },
                { label: 'Voting Begins',   date: campaign.voting_start,    color: '#3B82F6' },
                { label: 'Voting Ends',     date: campaign.voting_end,      color: '#EF4444' },
              ].map((t, i) => (
                <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <div style={{ width: 8, height: 8, borderRadius: '50%', background: t.color, flexShrink: 0 }} />
                  <span style={{ fontSize: 12, color: T.sub, fontWeight: 600, minWidth: 110 }}>{t.label}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: T.txt }}>{formatDate(t.date)}</span>
                </div>
              ))}
            </div>
          </Accordion>

          <Accordion id="scoring" icon={TrendingUp} title="How Scoring Works" subtitle="Engagement + votes" defaultColor="#EC4899">
            <div style={{ fontSize: 13, color: T.sub, lineHeight: 1.6 }}>
              <p style={{ margin: '0 0 8px' }}>
                Your total score is calculated from <b style={{ color: T.txt }}>likes, comments, shares, votes, and gifts</b> on your entry during the campaign period.
              </p>
              <div style={{
                display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8, marginTop: 10,
              }}>
                {[
                  { label: 'Likes',    icon: Heart,         color: '#EF4444' },
                  { label: 'Comments', icon: MessageCircle, color: '#3B82F6' },
                  { label: 'Shares',   icon: Share2,        color: '#8B5CF6' },
                  { label: 'Votes',    icon: Award,         color: BRAND     },
                  { label: 'Gifts',    icon: Gift,          color: '#8fc441' },
                ].map((m, i) => {
                  const I = m.icon;
                  return (
                    <div key={i} style={{
                      display: 'flex', alignItems: 'center', gap: 8,
                      padding: '8px 10px', background: T.bg, borderRadius: 8,
                    }}>
                      <I size={14} color={m.color} />
                      <span style={{ fontSize: 12, color: T.txt, fontWeight: 600 }}>{m.label}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          </Accordion>

          {/* ─── LEADERBOARD ────────────────────────── */}
          <div style={{ marginTop: 20 }}>
            <div style={{
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              marginBottom: 12,
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <Trophy size={18} color={BRAND} strokeWidth={2.5} />
                <h2 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: T.txt }}>
                  {canVote() ? 'Vote for Favorites' : 'Leaderboard'}
                </h2>
              </div>
              <div style={{ fontSize: 11, color: T.sub, fontWeight: 600 }}>
                {entries.length} {entries.length === 1 ? 'entry' : 'entries'}
              </div>
            </div>

            {entries.length === 0 ? (
              <div style={{
                padding: '36px 20px',
                textAlign: 'center',
                background: T.cardBg || '#fff',
                borderRadius: 12,
                border: `1px dashed ${T.border}`,
              }}>
                <Video size={36} color={T.sub} style={{ opacity: 0.4, marginBottom: 10 }} />
                <div style={{ fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 4 }}>
                  No entries yet
                </div>
                <div style={{ fontSize: 12, color: T.sub }}>
                  Be the first to submit!
                </div>
              </div>
            ) : (
              <div style={{
                display: 'grid',
                gridTemplateColumns: isMobile ? '1fr' : 'repeat(auto-fill, minmax(280px, 1fr))',
                gap: 14,
              }}>
                {entries.map(entry => (
                  <CampaignEntryCard
                    key={entry.id}
                    entry={entry}
                    theme={T}
                    canVote={canVote()}
                    onVote={() => handleVote(entry.id)}
                  />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Submit Modal */}
        {showSubmitModal && (
          <SubmitEntryModal
            theme={T}
            campaign={campaign}
            campaignId={campaignId}
            onClose={() => setShowSubmitModal(false)}
            onSuccess={() => {
              setShowSubmitModal(false);
              loadCampaignDetails();
            }}
          />
        )}
      </div>
    </div>
  );
}

function CampaignEntryCard({ entry, theme: T, canVote, onVote }) {
  const [hasVoted, setHasVoted] = useState(entry.user_voted);
  const [isHovered, setIsHovered] = useState(false);
  const [voteCount, setVoteCount] = useState(entry.vote_count);

  const handleVote = () => {
    if (!canVote || hasVoted) return;
    setHasVoted(true);
    setVoteCount(voteCount + 1);
    onVote();
  };

  const getRankBadge = () => {
    if (!entry.rank || entry.rank > 3) return null;
    const badges = {
      1: { color: '#FFD700', icon: 'ðŸ¥‡', label: '1st Place' },
      2: { color: '#C0C0C0', icon: 'ðŸ¥ˆ', label: '2nd Place' },
      3: { color: '#CD7F32', icon: 'ðŸ¥‰', label: '3rd Place' },
    };
    return badges[entry.rank];
  };

  const rankBadge = getRankBadge();

  return (
    <div 
      style={{
        background: T.cardBg || '#fff',
        borderRadius: 16,
        overflow: 'hidden',
        border: rankBadge ? `2px solid ${rankBadge.color}` : `1px solid ${T.border}`,
        boxShadow: isHovered ? `0 8px 24px ${rankBadge ? rankBadge.color + '40' : 'rgba(0,0,0,0.1)'}` : '0 2px 8px rgba(0,0,0,0.05)',
        transform: isHovered ? 'translateY(-4px)' : 'translateY(0)',
        transition: 'all 0.3s ease',
        position: 'relative',
      }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
    >
      {rankBadge && (
        <div style={{
          position: 'absolute',
          top: 12,
          right: 12,
          padding: '6px 12px',
          background: rankBadge.color,
          borderRadius: 20,
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          zIndex: 10,
          boxShadow: '0 4px 12px rgba(0,0,0,0.3)',
        }}>
          <span style={{ fontSize: 16 }}>{rankBadge.icon}</span>
          <span style={{ fontSize: 12, fontWeight: 700, color: '#fff' }}>{rankBadge.label}</span>
        </div>
      )}
      
      {entry.reel?.thumbnail ? (
        <div style={{ position: 'relative', minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
          <img
            src={mediaUrl(entry.reel.thumbnail)}
            alt="Entry"
            style={{
              maxWidth: '100%',
              maxHeight: 400,
              objectFit: 'contain',
            }}
          />
        </div>
      ) : entry.reel?.media ? (
        <div style={{ position: 'relative', minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
          {entry.reel.media.endsWith('.mp4') || entry.reel.media.endsWith('.mov') ? (
            <video
              src={mediaUrl(entry.reel.media)}
              style={{
                maxWidth: '100%',
                maxHeight: 400,
                objectFit: 'contain',
                background: '#000',
              }}
              controls
            />
          ) : (
            <img
              src={mediaUrl(entry.reel.media)}
              alt="Entry"
              style={{
                maxWidth: '100%',
                maxHeight: 400,
                objectFit: 'contain',
              }}
            />
          )}
        </div>
      ) : entry.reel?.image && (
        <div style={{ position: 'relative', minHeight: 280, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#000' }}>
          <img
            src={mediaUrl(entry.reel.image)}
            alt="Entry"
            style={{
              maxWidth: '100%',
              maxHeight: 400,
              objectFit: 'contain',
            }}
          />
        </div>
      )}
      
      <div style={{ padding: 16 }}>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 12,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
          }}>
            <div style={{
              width: 42,
              height: 42,
              borderRadius: '50%',
              background: 'linear-gradient(135deg, #8fc441, #8fc441)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontSize: 16,
              fontWeight: 700,
              color: '#fff',
              border: '2px solid #b8d97a',
              boxShadow: '0 2px 8px rgba(0,0,0,0.1)',
            }}>
              {entry.user.username[0].toUpperCase()}
            </div>
            <div>
              <div style={{
                fontSize: 14,
                fontWeight: 700,
                color: T.txt,
              }}>
                @{entry.user.username}
              </div>
              {entry.rank && (
                <div style={{
                  fontSize: 11,
                  color: rankBadge ? rankBadge.color : T.pri,
                  fontWeight: 700,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 4,
                }}>
                  <TrendingUp size={12} />
                  Rank #{entry.rank}
                </div>
              )}
            </div>
          </div>
          {entry.is_winner && (
            <div style={{
              padding: '4px 10px',
              background: 'linear-gradient(135deg, #8fc441, #8fc441)',
              borderRadius: 12,
              fontSize: 11,
              fontWeight: 700,
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              gap: 4,
            }}>
              <Crown size={12} />
              WINNER
            </div>
          )}
        </div>

        <p style={{
          margin: 0,
          fontSize: 14,
          color: T.sub,
          marginBottom: 16,
          lineHeight: 1.5,
        }}>
          {entry.reel?.caption || 'No caption'}
        </p>

        <div style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingTop: 12,
          borderTop: `1px solid ${T.border}`,
        }}>
          <div style={{
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            padding: '8px 12px',
            background: hasVoted ? 'rgba(239,68,68,0.15)' : T.bg,
            borderRadius: 20,
            border: hasVoted ? `2px solid #EF4444` : `1px solid ${T.border}`,
          }}>
            <Heart 
              size={20} 
              color="#EF4444" 
              fill={hasVoted ? "#EF4444" : 'none'}
              style={{
                transition: 'all 0.3s ease',
                transform: hasVoted ? 'scale(1.2)' : 'scale(1)',
              }}
            />
            <span style={{
              fontSize: 18,
              fontWeight: 800,
              color: hasVoted ? "#EF4444" : T.txt,
            }}>
              {voteCount}
            </span>
            <span style={{
              fontSize: 11,
              color: T.sub,
              fontWeight: 600,
            }}>
              votes
            </span>
          </div>

          {canVote && (
            <button
              onClick={handleVote}
              disabled={hasVoted}
              style={{
                padding: '10px 20px',
                background: hasVoted 
                  ? `#10B981` 
                  : `linear-gradient(135deg, ${T.pri}, #8fc441)`,
                border: 'none',
                borderRadius: 20,
                color: '#fff',
                fontSize: 13,
                fontWeight: 700,
                cursor: hasVoted ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 6,
                boxShadow: hasVoted ? 'none' : `0 4px 12px ${T.pri}40`,
                opacity: hasVoted ? 0.7 : 1,
                transition: 'all 0.3s ease',
              }}
            >
              {hasVoted ? (
                <>
                  <Check size={16} strokeWidth={3} />
                  Voted
                </>
              ) : (
                <>
                  <Heart size={16} />
                  Vote
                </>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function SubmitEntryModal({ theme: T, campaign, campaignId, onClose, onSuccess }) {
  const [selectedReel, setSelectedReel] = useState(null);
  const [userReels, setUserReels] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState('');
  const [showCreateNew, setShowCreateNew] = useState(false);
  const [newReelFile, setNewReelFile] = useState(null);
  const [newReelCaption, setNewReelCaption] = useState('');
  const [showCamera, setShowCamera] = useState(false);
  const [stream, setStream] = useState(null);

  useEffect(() => {
    loadUserReels();
  }, []);

  const loadUserReels = async () => {
    if (!api.hasToken()) {
      setLoading(false);
      setError('Please log in to submit a campaign entry.');
      return;
    }
    try {
      // Get current user's ID first
      const userResponse = await api.request('/profile/me/');
      const userId = userResponse.id;
      
      // Fetch only current user's reels
      const response = await api.request(`/reels/?user=${userId}`);
      setUserReels(response.results || []);
    } catch (error) {
      console.error('Failed to load reels:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleFileChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setNewReelFile(file);
      setShowCreateNew(true);
    }
  };

  const startCamera = async () => {
    try {
      // Check if mediaDevices is available
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        setError('Your browser does not support camera access. Please use Chrome, Firefox, or Edge.');
        return;
      }

      // First, try to enumerate devices to check if cameras are available
      let devices = [];
      try {
        devices = await navigator.mediaDevices.enumerateDevices();
        const videoDevices = devices.filter(d => d.kind === 'videoinput');
        console.log('Available video devices:', videoDevices);
        if (videoDevices.length === 0) {
          throw new Error('No camera devices found on this system');
        }
      } catch (enumError) {
        console.warn('Could not enumerate devices:', enumError);
        // Continue anyway - this might be a permission issue that will be resolved by getUserMedia
      }

      let mediaStream = null;
      let lastError = null;

      // Strategy: Start with the most flexible constraints first, then get stricter
      const constraintAttempts = [
        // Attempt 1: Most flexible - just request video and audio
        {
          name: 'Basic video/audio',
          constraints: { video: true, audio: true }
        },
        // Attempt 2: With facingMode
        {
          name: 'With facingMode',
          constraints: { video: { facingMode: 'user' }, audio: true }
        }
      ];

      for (const attempt of constraintAttempts) {
        try {
          console.log(`Attempting camera with: ${attempt.name}`, attempt.constraints);
          mediaStream = await navigator.mediaDevices.getUserMedia(attempt.constraints);
          console.log(`Camera access successful with: ${attempt.name}`);
          break; // Success! Exit the loop
        } catch (error) {
          lastError = error;
          console.warn(`Camera attempt failed (${attempt.name}):`, error.name, error.message);
          // Continue to next attempt
        }
      }

      if (!mediaStream) {
        throw lastError || new Error('Camera access failed after all attempts');
      }

      setStream(mediaStream);
      setShowCamera(true);
      setShowCreateNew(true);
    } catch (error) {
      console.error('Camera access denied:', error);

      // Show user-friendly error message based on error type
      let errorMessage = 'Camera access failed. ';
      switch (error.name) {
        case 'NotAllowedError':
        case 'PermissionDeniedError':
          errorMessage += 'Camera permission was denied. Please:\n\n1. Click the lock/info icon in your browser address bar\n2. Allow camera access\n3. Refresh the page and try again';
          break;
        case 'NotFoundError':
          errorMessage += 'No camera found on this device. Please:\n\n1. Ensure your camera is connected and not in use by another app\n2. Check if your camera is enabled in system settings\n3. Try refreshing the page and allowing camera permissions when prompted\n4. If using a laptop, make sure the camera is not covered or disabled';
          break;
        case 'NotReadableError':
          errorMessage += 'Camera is already in use by another application (Zoom, Teams, another browser tab, etc.).\n\nPlease close other apps using the camera and try again.';
          break;
        case 'OverconstrainedError':
          errorMessage += 'Your camera does not support the requested resolution. The app will try with lower quality automatically.';
          break;
        case 'TypeError':
          errorMessage += 'Camera not supported in this browser. Please use Chrome, Firefox, or Edge.';
          break;
        default:
          errorMessage += `Please check your permissions and try again.\n\nError: ${error.message}`;
      }
      setError(errorMessage);
    }
  };

  const stopCamera = () => {
    if (stream) {
      stream.getTracks().forEach(track => track.stop());
      setStream(null);
    }
    setShowCamera(false);
  };

  const startRecording = async () => {
    if (!stream) return;
    
    try {
      const mediaRecorder = new MediaRecorder(stream, {
        mimeType: 'video/webm'
      });
      
      const chunks = [];
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          chunks.push(event.data);
        }
      };
      
      mediaRecorder.onstop = () => {
        const blob = new Blob(chunks, { type: 'video/webm' });
        const file = new File([blob], `camera_recording_${Date.now()}.webm`, { type: 'video/webm' });
        setNewReelFile(file);
        stopCamera();
      };
      
      mediaRecorder.start();
      
      // Stop recording after 30 seconds or when user clicks stop
      setTimeout(() => {
        if (mediaRecorder.state === 'recording') {
          mediaRecorder.stop();
        }
      }, 30000);
      
      // Store mediaRecorder instance for stopping
      window.currentMediaRecorder = mediaRecorder;
      
    } catch (error) {
      console.error('Error starting recording:', error);
      setError('Failed to start recording. Please try again.');
    }
  };
  
  const stopRecording = () => {
    if (window.currentMediaRecorder && window.currentMediaRecorder.state === 'recording') {
      window.currentMediaRecorder.stop();
    }
  };

  const handleCreateAndSubmit = async () => {
    if (!api.hasToken()) {
      setError('Please log in to submit a campaign entry.');
      return;
    }
    if (!newReelFile) {
      setError('Please select a file to upload');
      return;
    }

    try {
      setSubmitting(true);
      setError('');
      
      // Create new reel
      const formData = new FormData();
      formData.append('media', newReelFile);
      formData.append('caption', newReelCaption || 'Campaign Entry');
      
      const newReel = await api.request('/reels/', {
        method: 'POST',
        body: formData,
        isFormData: true
      });
      
      // Submit to campaign
      await api.request(`/campaigns/${campaignId}/enter/`, {
        method: 'POST',
        body: JSON.stringify({ reel_id: newReel.id })
      });
      
      console.log('Entry submitted successfully!');
      onSuccess();
    } catch (error) {
      console.error('Error submitting entry:', error);
      setError(error.message || 'Failed to submit entry');
    } finally {
      setSubmitting(false);
    }
  };

  const handleSubmit = async () => {
    if (showCreateNew) {
      return handleCreateAndSubmit();
    }
    
    if (!selectedReel) {
      setError('Please select a reel to submit');
      return;
    }

    try {
      setSubmitting(true);
      setError('');
      await api.request(`/campaigns/${campaignId}/enter/`, {
        method: 'POST',
        body: JSON.stringify({ reel_id: selectedReel })
      });
      console.log('Entry submitted successfully!');
      onSuccess();
    } catch (error) {
      console.error('Error submitting entry:', error);
      setError(error.message || 'Failed to submit entry');
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.7)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: '#fff',
          borderRadius: 16,
          padding: 32,
          width: '100%',
          maxWidth: 600,
          maxHeight: '80vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{
          margin: 0,
          fontSize: 24,
          fontWeight: 700,
          color: T.txt,
          marginBottom: 8,
        }}>
          Submit Your Entry
        </h2>
        <p style={{
          margin: 0,
          fontSize: 14,
          color: T.sub,
          marginBottom: 16,
        }}>
          {showCreateNew ? 'Upload new content for this campaign' : 'Select existing reel or create new'}
        </p>
        
        {/* Toggle Buttons */}
        <div style={{
          display: 'flex',
          gap: 12,
          marginBottom: 24,
        }}>
          <button
            onClick={() => setShowCreateNew(false)}
            style={{
              flex: 1,
              padding: '12px 16px',
              background: !showCreateNew ? T.pri : 'transparent',
              border: `2px solid ${T.pri}`,
              borderRadius: 8,
              color: !showCreateNew ? '#fff' : T.pri,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            📚 Use Existing
          </button>
          <button
            onClick={() => setShowCreateNew(true)}
            style={{
              flex: 1,
              padding: '12px 16px',
              background: showCreateNew ? T.pri : 'transparent',
              border: `2px solid ${T.pri}`,
              borderRadius: 8,
              color: showCreateNew ? '#fff' : T.pri,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            🎬 Create New
          </button>
        </div>

        {error && (
          <div style={{
            padding: 12,
            background: 'rgba(239,68,68,0.15)',
            border: `1px solid #EF4444`,
            borderRadius: 8,
            color: '#EF4444',
            fontSize: 14,
            marginBottom: 20,
          }}>
            {error}
          </div>
        )}

        {showCreateNew ? (
          <div>
            {/* Campaign Requirements */}
            {campaign && (
              <div style={{
                padding: 16,
                background: 'rgba(59,130,246,0.1)',
                borderRadius: 12,
                border: '2px solid rgba(59,130,246,0.3)',
                marginBottom: 20,
              }}>
                <h4 style={{ margin: 0, fontSize: 14, fontWeight: 700, color: T.txt, marginBottom: 12 }}>
                  📋 Campaign Requirements
                </h4>
                <div style={{ fontSize: 13, color: T.sub, lineHeight: 1.8 }}>
                  {campaign.required_hashtags && (
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ color: T.txt }}>Required Hashtags:</strong> {campaign.required_hashtags}
                    </div>
                  )}
                  {campaign.min_followers > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ color: T.txt }}>Min Followers:</strong> {campaign.min_followers}
                    </div>
                  )}
                  {campaign.min_level > 0 && (
                    <div style={{ marginBottom: 8 }}>
                      <strong style={{ color: T.txt }}>Min Level:</strong> {campaign.min_level}
                    </div>
                  )}
                  {campaign.min_votes_per_reel > 0 && (
                    <div>
                      <strong style={{ color: T.txt }}>Min Votes Required:</strong> {campaign.min_votes_per_reel}
                    </div>
                  )}
                </div>
              </div>
            )}
            
            {/* Upload or Record Options */}
            <div style={{
              display: 'flex',
              gap: 12,
              marginBottom: 20,
            }}>
              <button
                onClick={() => document.getElementById('campaign-file-upload').click()}
                style={{
                  flex: 1,
                  padding: '14px 16px',
                  background: T.cardBg || '#fff',
                  border: `2px solid ${T.border}`,
                  borderRadius: 12,
                  color: T.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Upload size={18} />
                Upload File
              </button>
              <button
                onClick={startCamera}
                style={{
                  flex: 1,
                  padding: '14px 16px',
                  background: T.cardBg || '#fff',
                  border: `2px solid ${T.border}`,
                  borderRadius: 12,
                  color: T.txt,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
              >
                <Video size={18} />
                Record Video
              </button>
            </div>
            
            {/* Camera or File Upload Area */}
            <div style={{
              marginBottom: 20,
              padding: 24,
              border: `2px dashed ${T.border}`,
              borderRadius: 12,
              textAlign: 'center',
              background: newReelFile ? `${T.green}10` : T.bg,
              position: 'relative',
              minHeight: 200,
            }}
            >
              {showCamera && stream ? (
                <div style={{ position: 'relative', width: '100%', height: '300px' }}>
                  <video
                    ref={(videoEl) => {
                      if (videoEl && stream) {
                        videoEl.srcObject = stream;
                      }
                    }}
                    autoPlay
                    playsInline
                    muted
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'contain',
                      background: '#000',
                      borderRadius: 8,
                    }}
                  />
                  <div style={{
                    position: 'absolute',
                    bottom: 10,
                    right: 10,
                    background: 'rgba(0,0,0,0.7)',
                    color: '#fff',
                    padding: '8px 12px',
                    borderRadius: 20,
                    fontSize: 12,
                    fontWeight: 600,
                  }}>
                    Recording...
                  </div>
                </div>
              ) : newReelFile ? (
                <div>
                  <Check size={48} color={T.green} style={{ marginBottom: 12 }} />
                  <p style={{ margin: 0, color: T.txt, fontWeight: 600 }}>
                    {newReelFile.name}
                  </p>
                  <p style={{ margin: 0, fontSize: 12, color: T.sub, marginTop: 4 }}>
                    Click to change file
                  </p>
                </div>
              ) : (
                <div>
                  <Upload size={48} color={T.sub} style={{ marginBottom: 12 }} />
                  <p style={{ margin: 0, color: T.txt, fontWeight: 600, marginBottom: 4 }}>
                    Click to upload photo or video
                  </p>
                  <p style={{ margin: 0, fontSize: 12, color: T.sub }}>
                    MP4, MOV, JPG, PNG up to 100MB
                  </p>
                </div>
              )}
              <input
                id="campaign-file-upload"
                type="file"
                accept="image/*,video/*"
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />
            </div>
            
            <div style={{ marginBottom: 20 }}>
              <label style={{
                display: 'block',
                fontSize: 14,
                fontWeight: 600,
                color: T.txt,
                marginBottom: 8,
              }}>
                Caption {campaign?.required_hashtags ? '(Include required hashtags)' : '(optional)'}
              </label>
              <textarea
                value={newReelCaption}
                onChange={(e) => setNewReelCaption(e.target.value)}
                placeholder={campaign?.required_hashtags ? `Add caption with: ${campaign.required_hashtags}` : "Add a caption for your entry..."}
                rows={3}
                style={{
                  width: '100%',
                  padding: 12,
                  border: `2px solid ${T.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
              />
              {campaign?.required_hashtags && (
                <div style={{
                  fontSize: 12,
                  color: T.sub,
                  marginTop: 6,
                }}>
                  💡 Tip: Copy and paste: {campaign.required_hashtags}
                </div>
              )}
            </div>
          </div>
        ) : loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: T.sub }}>
            Loading your reels...
          </div>
        ) : userReels.length === 0 ? (
          <div style={{
            padding: 40,
            textAlign: 'center',
            background: T.bg,
            borderRadius: 12,
          }}>
            <Video size={48} color={T.sub} style={{ marginBottom: 16 }} />
            <p style={{ margin: 0, color: T.sub, marginBottom: 20 }}>
              You don't have any reels yet. Create one first!
            </p>
            <button
              onClick={() => {
                onClose();
                // Navigate to create post - will be handled by parent component
                window.dispatchEvent(new CustomEvent('navigateToCreatePost'));
              }}
              style={{
                padding: '12px 24px',
                background: 'linear-gradient(135deg, #8fc441, #8fc441)',
                border: 'none',
                borderRadius: 12,
                color: '#fff',
                fontSize: 15,
                fontWeight: 700,
                cursor: 'pointer',
                boxShadow: '0 4px 12px rgba(218,155,42,0.4)',
              }}
            >
              🎬 Create Reel Now
            </button>
          </div>
        ) : (
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))',
            gap: 12,
            marginBottom: 24,
          }}>
            {userReels.map(reel => (
              <div
                key={reel.id}
                onClick={() => setSelectedReel(reel.id)}
                style={{
                  position: 'relative',
                  aspectRatio: '9/16',
                  borderRadius: 12,
                  overflow: 'hidden',
                  cursor: 'pointer',
                  border: selectedReel === reel.id ? `3px solid ${T.pri}` : `1px solid ${T.border}`,
                }}
              >
                {reel.image ? (
                  <img
                    src={mediaUrl(reel.image)}
                    alt=""
                    style={{
                      width: '100%',
                      height: '100%',
                      objectFit: 'cover',
                    }}
                  />
                ) : (
                  <div style={{
                    width: '100%',
                    height: '100%',
                    background: T.bg,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <Video size={32} color={T.sub} />
                  </div>
                )}
                {selectedReel === reel.id && (
                  <div style={{
                    position: 'absolute',
                    top: 8,
                    right: 8,
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    background: T.pri,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}>
                    <Check size={16} color="#fff" />
                  </div>
                )}
              </div>
            ))}
          </div>
        )}

        <div style={{
          display: 'flex',
          gap: 12,
          paddingTop: 24,
          borderTop: `1px solid ${T.border}`,
        }}>
          <button
            onClick={onClose}
            style={{
              flex: 1,
              padding: 14,
              background: T.cardBg,
              border: `2px solid ${T.border}`,
              borderRadius: 8,
              color: T.txt,
              fontSize: 15,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={(showCreateNew ? !newReelFile : !selectedReel) || submitting}
            style={{
              flex: 1,
              padding: 14,
              background: ((showCreateNew ? newReelFile : selectedReel) && !submitting) ? T.pri : T.sub + '30',
              border: 'none',
              borderRadius: 8,
              color: ((showCreateNew ? newReelFile : selectedReel) && !submitting) ? '#fff' : T.sub,
              fontSize: 15,
              fontWeight: 600,
              cursor: ((showCreateNew ? newReelFile : selectedReel) && !submitting) ? 'pointer' : 'not-allowed',
            }}
          >
            {submitting ? 'Submitting...' : showCreateNew ? '🚀 Create & Submit' : 'Submit Entry'}
          </button>
        </div>
      </div>
    </div>
  );
}



