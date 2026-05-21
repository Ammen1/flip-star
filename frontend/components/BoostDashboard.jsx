import { useState, useEffect } from "react";
import { Zap, Clock, Users, Eye, Heart, Pause, Play, X } from "lucide-react";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

export function BoostDashboard({ onClose }) {
  const T = useLegacyT();
  const [campaigns, setCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [selectedCampaign, setSelectedCampaign] = useState(null);

  useEffect(() => {
    loadCampaigns();
  }, []);

  const loadCampaigns = async () => {
    setLoading(true);
    try {
      const response = await api.request('/boost/campaigns/my/');
      setCampaigns(response.campaigns || []);
    } catch (err) {
      console.error('Error loading campaigns:', err);
    } finally {
      setLoading(false);
    }
  };

  const handlePause = async (campaignId) => {
    try {
      await api.request(`/boost/campaigns/${campaignId}/pause/`, { method: 'POST' });
      loadCampaigns();
    } catch (err) {
      console.error('Error pausing campaign:', err);
    }
  };

  const handleResume = async (campaignId) => {
    try {
      await api.request(`/boost/campaigns/${campaignId}/resume/`, { method: 'POST' });
      loadCampaigns();
    } catch (err) {
      console.error('Error resuming campaign:', err);
    }
  };

  const handleCancel = async (campaignId) => {
    if (!confirm('Are you sure you want to cancel this boost? You will receive a partial refund.')) return;
    
    try {
      await api.request(`/boost/campaigns/${campaignId}/cancel/`, { method: 'POST' });
      loadCampaigns();
      setSelectedCampaign(null);
    } catch (err) {
      console.error('Error cancelling campaign:', err);
    }
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return '#10B981';
      case 'paused': return '#F59E0B';
      case 'completed': return '#3B82F6';
      case 'cancelled': return '#6B7280';
      case 'exhausted': return '#EF4444';
      default: return '#6B7280';
    }
  };

  const formatDuration = (hours) => {
    if (hours < 24) return hours + 'h';
    const days = Math.floor(hours / 24);
    const remainingHours = hours % 24;
    if (remainingHours === 0) return days + 'd';
    return days + 'd ' + remainingHours + 'h';
  };

  const getPrimaryColor = () => {
    return T.pri || '#8fc441';
  };

  const getPrimaryColor20 = () => {
    const color = T.pri || '#8fc441';
    return color + '20';
  };

  if (loading) {
    return (
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#fff', fontSize: 18 }}>Loading...</div>
      </div>
    );
  }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }}>
      <div style={{ background: T.cardBg || '#1a1a1a', borderRadius: 20, maxWidth: 800, width: '100%', maxHeight: '90vh', overflowY: 'auto', position: 'relative' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottom: '1px solid ' + (T.border || 'rgba(255,255,255,0.1)') }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: getPrimaryColor20(), display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap size={20} color={getPrimaryColor()} />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: T.txt || '#fff' }}>Boost Dashboard</div>
              <div style={{ fontSize: 12, color: T.sub || 'rgba(255,255,255,0.5)' }}>{campaigns.length} active campaign{campaigns.length !== 1 ? 's' : ''}</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8, color: T.sub || 'rgba(255,255,255,0.5)' }}>
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: 20 }}>
          {campaigns.length === 0 ? (
            <div style={{ textAlign: 'center', padding: 60, color: T.sub || 'rgba(255,255,255,0.5)' }}>
              <Zap size={48} style={{ marginBottom: 16, opacity: 0.5 }} />
              <div style={{ fontSize: 16, marginBottom: 8 }}>No active boosts</div>
              <div style={{ fontSize: 14 }}>Boost your posts to reach more people</div>
            </div>
          ) : (
            <div style={{ display: 'grid', gap: 16 }}>
              {campaigns.map(campaign => (
                <div
                  key={campaign.id}
                  onClick={() => setSelectedCampaign(selectedCampaign?.id === campaign.id ? null : campaign)}
                  style={{
                    background: 'rgba(255,255,255,0.03)',
                    border: '1px solid ' + (T.border || 'rgba(255,255,255,0.1)'),
                    borderRadius: 12,
                    padding: 16,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                >
                  {/* Campaign Header */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', marginBottom: 12 }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                        <span style={{ fontSize: 12, fontWeight: 600, color: getStatusColor(campaign.status), textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                          {campaign.status}
                        </span>
                        <span style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)' }}>
                          {formatDuration(campaign.duration_hours)}
                        </span>
                      </div>
                      <div style={{ fontSize: 14, color: T.txt || '#fff', fontWeight: 600, marginBottom: 2 }}>
                        {campaign.reel_caption || 'Untitled Post'}
                      </div>
                      <div style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)' }}>
                        ID: #{campaign.id}
                      </div>
                    </div>
                    {campaign.is_active && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handlePause(campaign.id); }}
                        style={{ background: 'rgba(245,158,11,0.1)', border: '1px solid #F59E0B', borderRadius: 8, padding: 6, cursor: 'pointer' }}
                      >
                        <Pause size={14} color="#F59E0B" />
                      </button>
                    )}
                    {campaign.status === 'paused' && (
                      <button
                        onClick={(e) => { e.stopPropagation(); handleResume(campaign.id); }}
                        style={{ background: 'rgba(16,185,129,0.1)', border: '1px solid #10B981', borderRadius: 8, padding: 6, cursor: 'pointer' }}
                      >
                        <Play size={14} color="#10B981" />
                      </button>
                    )}
                  </div>

                  {/* Progress Bar */}
                  <div style={{ marginBottom: 12 }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                      <span style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)' }}>Progress</span>
                      <span style={{ fontSize: 11, fontWeight: 600, color: T.txt || '#fff' }}>{campaign.progress_percent}%</span>
                    </div>
                    <div style={{ height: 6, background: 'rgba(255,255,255,0.1)', borderRadius: 3, overflow: 'hidden' }}>
                      <div style={{ height: '100%', background: getPrimaryColor(), borderRadius: 3, width: campaign.progress_percent + '%', transition: 'width 0.3s' }} />
                    </div>
                  </div>

                  {/* Stats Grid */}
                  <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 8, marginBottom: 12 }}>
                    <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Eye size={14} color={T.sub || 'rgba(255,255,255,0.5)'} />
                        <span style={{ fontSize: 10, color: T.sub || 'rgba(255,255,255,0.5)' }}>Impressions</span>
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: T.txt || '#fff' }}>{campaign.impressions_served.toLocaleString()}</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Heart size={14} color={T.sub || 'rgba(255,255,255,0.5)'} />
                        <span style={{ fontSize: 10, color: T.sub || 'rgba(255,255,255,0.5)' }}>Engagement</span>
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: T.txt || '#fff' }}>{campaign.engagement_count}</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Clock size={14} color={T.sub || 'rgba(255,255,255,0.5)'} />
                        <span style={{ fontSize: 10, color: T.sub || 'rgba(255,255,255,0.5)' }}>Time Left</span>
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: T.txt || '#fff' }}>{campaign.time_remaining_hours}h</div>
                    </div>
                    <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 10 }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 4 }}>
                        <Zap size={14} color={T.sub || 'rgba(255,255,255,0.5)'} />
                        <span style={{ fontSize: 10, color: T.sub || 'rgba(255,255,255,0.5)' }}>Spent</span>
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: T.txt || '#fff' }}>{Math.round(campaign.coins_spent - campaign.coins_remaining)}</div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {selectedCampaign?.id === campaign.id && (
                    <div style={{ paddingTop: 12, borderTop: '1px solid ' + (T.border || 'rgba(255,255,255,0.1)'), marginTop: 12 }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 12, marginBottom: 12 }}>
                        <div>
                          <div style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 4 }}>Expected Impressions</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>{campaign.expected_impressions.toLocaleString()}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 4 }}>Coins Spent</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>{Math.round(campaign.coins_spent)} / {Math.round(campaign.coins_spent)}</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 4 }}>Engagement Rate</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>{campaign.impressions_served > 0 ? ((campaign.engagement_count / campaign.impressions_served) * 100).toFixed(1) : 0}%</div>
                        </div>
                        <div>
                          <div style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 4 }}>Remaining Coins</div>
                          <div style={{ fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>{Math.round(campaign.coins_remaining)}</div>
                        </div>
                      </div>

                      {campaign.targeting && (
                        <div style={{ background: 'rgba(255,255,255,0.02)', borderRadius: 8, padding: 12, marginBottom: 12 }}>
                          <div style={{ fontSize: 11, fontWeight: 600, color: T.txt || '#fff', marginBottom: 8, display: 'flex', alignItems: 'center', gap: 6 }}>
                            <Users size={12} />
                            Target Audience
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                            {campaign.targeting.gender && (
                              <span style={{ fontSize: 11, background: getPrimaryColor20(), color: getPrimaryColor(), padding: '4px 8px', borderRadius: 4 }}>
                                {campaign.targeting.gender}
                              </span>
                            )}
                            {campaign.targeting.age_min && campaign.targeting.age_max && (
                              <span style={{ fontSize: 11, background: getPrimaryColor20(), color: getPrimaryColor(), padding: '4px 8px', borderRadius: 4 }}>
                                {campaign.targeting.age_min}-{campaign.targeting.age_max} years
                              </span>
                            )}
                            {campaign.targeting.location && (
                              <span style={{ fontSize: 11, background: getPrimaryColor20(), color: getPrimaryColor(), padding: '4px 8px', borderRadius: 4 }}>
                                {campaign.targeting.location}
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      <button
                        onClick={(e) => { e.stopPropagation(); handleCancel(campaign.id); }}
                        style={{
                          width: '100%',
                          padding: 12,
                          background: 'rgba(239,68,68,0.1)',
                          border: '1px solid #EF4444',
                          borderRadius: 8,
                          color: '#EF4444',
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 8,
                        }}
                      >
                        <X size={14} /> Cancel Boost
                      </button>
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
