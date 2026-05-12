import { useState, useEffect } from 'react';
import { Trophy, Plus, Edit, Trash2, Users, Award, BarChart3, X, Calendar, Clock, TrendingUp, Star, Settings, Play, Pause, CheckCircle } from 'lucide-react';
import api from '../../api';
import { ConfirmModal } from '../components/ConfirmModal';
import { GenerationConfigModal } from '../components/GenerationConfigModal';

export function MasterCampaignManagementPage({ theme }) {
  const [masterCampaigns, setMasterCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState(null);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [showStatsModal, setShowStatsModal] = useState(false);
  const [campaignStats, setCampaignStats] = useState(null);
  const [confirmModal, setConfirmModal] = useState({ isOpen: false });
  const [showConfigModal, setShowConfigModal] = useState(false);
  const [configCampaign, setConfigCampaign] = useState(null);

  useEffect(() => {
    loadMasterCampaigns();
  }, [statusFilter]);

  const loadMasterCampaigns = async () => {
    try {
      setLoading(true);
      const filterParam = statusFilter !== 'all' ? `?status=${statusFilter}` : '';
      const response = await api.request(`/admin/master-campaigns/${filterParam}`);
      setMasterCampaigns(response.master_campaigns || []);
    } catch (error) {
      console.error('Failed to load master campaigns:', error);
      setMasterCampaigns([]);
    } finally {
      setLoading(false);
    }
  };

  const handleCreate = () => {
    setEditingCampaign(null);
    setShowCreateModal(true);
  };

  const handleEdit = (campaign) => {
    setEditingCampaign(campaign);
    setShowEditModal(true);
  };

  const handleDelete = (campaign) => {
    setConfirmModal({
      isOpen: true,
      title: 'Delete Master Campaign',
      message: `Are you sure you want to delete "${campaign.title}"? This will also delete all associated sub-campaigns. This action cannot be undone.`,
      type: 'danger',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(`/admin/master-campaigns/${campaign.id}/`, { method: 'DELETE' });
          setMasterCampaigns(prev => prev.filter(c => c.id !== campaign.id));
          setConfirmModal({ isOpen: false });
        } catch (error) {
          console.error('Failed to delete master campaign:', error);
          alert('Failed to delete master campaign');
        }
      }
    });
  };

  const handleViewStats = async (campaign) => {
    try {
      setSelectedCampaign(campaign);
      const response = await api.request(`/admin/master-campaigns/${campaign.id}/stats/`);
      setCampaignStats(response);
      setShowStatsModal(true);
    } catch (error) {
      console.error('Failed to load campaign stats:', error);
      alert('Failed to load campaign statistics');
    }
  };

  const handleGenerateSubCampaigns = (campaign) => {
    setConfigCampaign(campaign);
    setShowConfigModal(true);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'draft': return theme.sub;
      case 'upcoming': return theme.blue;
      case 'active': return theme.green;
      case 'completed': return theme.pri;
      case 'cancelled': return theme.red;
      default: return theme.sub;
    }
  };

  const getStatusIcon = (status) => {
    switch (status) {
      case 'draft': return Edit;
      case 'upcoming': return Clock;
      case 'active': return Play;
      case 'completed': return CheckCircle;
      case 'cancelled': return X;
      default: return Clock;
    }
  };

  const getPhaseColor = (phase) => {
    switch (phase) {
      case 'upcoming': return theme.blue;
      case 'active': return theme.green;
      case 'completed': return theme.sub;
      case 'not_configured': return theme.red;
      default: return theme.sub;
    }
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        Loading master campaigns...
      </div>
    );
  }

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: 32,
      }}>
        <div>
          <h1 style={{
            margin: 0,
            fontSize: 32,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 8,
          }}>
            Master Campaigns (Seasons)
          </h1>
          <p style={{ margin: 0, fontSize: 16, color: theme.sub }}>
            Manage campaign seasons and generate sub-campaigns
          </p>
        </div>
        <button
          onClick={handleCreate}
          style={{
            padding: '12px 24px',
            background: theme.pri,
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            fontSize: 16,
            fontWeight: 600,
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Plus size={20} />
          Create Master Campaign
        </button>
      </div>

      {/* Filter Tabs */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 24,
        borderBottom: `1px solid ${theme.border}`,
        paddingBottom: 12,
      }}>
        {['all', 'draft', 'upcoming', 'active', 'completed', 'cancelled'].map((status) => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            style={{
              padding: '8px 16px',
              background: statusFilter === status ? theme.pri : 'transparent',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 14,
              fontWeight: statusFilter === status ? 600 : 500,
              color: statusFilter === status ? '#fff' : theme.txt,
              textTransform: 'capitalize',
            }}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Master Campaigns List */}
      {masterCampaigns.length === 0 ? (
        <div style={{
          textAlign: 'center',
          padding: 60,
          background: theme.card,
          borderRadius: 12,
          border: `1px solid ${theme.border}`,
        }}>
          <Trophy size={48} style={{ color: theme.sub, marginBottom: 16 }} />
          <h3 style={{ fontSize: 18, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
            No Master Campaigns Found
          </h3>
          <p style={{ fontSize: 14, color: theme.sub, marginBottom: 16 }}>
            Create your first master campaign to start organizing seasonal competitions
          </p>
          <button
            onClick={handleCreate}
            style={{
              padding: '10px 20px',
              background: theme.pri,
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Create Master Campaign
          </button>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(400px, 1fr))',
          gap: 20,
        }}>
          {masterCampaigns.map((campaign) => {
            const StatusIcon = getStatusIcon(campaign.status);
            return (
              <div
                key={campaign.id}
                style={{
                  background: theme.card,
                  borderRadius: 12,
                  border: `1px solid ${theme.border}`,
                  padding: 20,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.boxShadow = '0 4px 12px rgba(0,0,0,0.08)';
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.boxShadow = 'none';
                }}
              >
                {/* Header */}
                <div style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  marginBottom: 16,
                }}>
                  <div style={{ flex: 1 }}>
                    <h3 style={{
                      margin: 0,
                      fontSize: 18,
                      fontWeight: 700,
                      color: theme.txt,
                      marginBottom: 4,
                    }}>
                      {campaign.title}
                    </h3>
                    <p style={{
                      margin: 0,
                      fontSize: 12,
                      color: theme.sub,
                      lineHeight: 1.4,
                    }}>
                      {campaign.description.length > 100 
                        ? `${campaign.description.substring(0, 100)}...`
                        : campaign.description}
                    </p>
                  </div>
                  <div style={{
                    padding: '4px 12px',
                    background: `${getStatusColor(campaign.status)}15`,
                    borderRadius: 20,
                    fontSize: 12,
                    fontWeight: 600,
                    color: getStatusColor(campaign.status),
                    textTransform: 'capitalize',
                    display: 'flex',
                    alignItems: 'center',
                    gap: 4,
                  }}>
                    <StatusIcon size={14} />
                    {campaign.status}
                  </div>
                </div>

                {/* Duration */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 12,
                  fontSize: 13,
                  color: theme.sub,
                }}>
                  <Calendar size={14} />
                  <span>
                    {new Date(campaign.start_date).toLocaleDateString()} - {new Date(campaign.end_date).toLocaleDateString()}
                  </span>
                  <span style={{ marginLeft: 'auto', fontWeight: 600 }}>
                    {campaign.duration_days} days
                  </span>
                </div>

                {/* Current Phase */}
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  marginBottom: 16,
                  fontSize: 13,
                }}>
                  <div style={{
                    width: 8,
                    height: 8,
                    borderRadius: '50%',
                    background: getStatusColor(campaign.status),
                  }} />
                  <span style={{ color: theme.sub }}>Current Status:</span>
                  <span style={{ fontWeight: 600, color: getStatusColor(campaign.status), textTransform: 'capitalize' }}>
                    {campaign.status}
                  </span>
                </div>

                {/* Stats */}
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(4, 1fr)',
                  gap: 8,
                  marginBottom: 16,
                  fontSize: 12,
                }}>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, color: theme.txt }}>{campaign.participant_count}</div>
                    <div style={{ color: theme.sub }}>Participants</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, color: theme.txt }}>{campaign.total_daily_campaigns}</div>
                    <div style={{ color: theme.sub }}>Daily</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, color: theme.txt }}>{campaign.total_weekly_campaigns}</div>
                    <div style={{ color: theme.sub }}>Weekly</div>
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <div style={{ fontWeight: 700, color: theme.txt }}>{campaign.total_grand_campaigns}</div>
                    <div style={{ color: theme.sub }}>Grand</div>
                  </div>
                </div>

                {/* Actions */}
                <div style={{
                  display: 'flex',
                  gap: 8,
                  flexWrap: 'wrap',
                }}>
                  <button
                    onClick={() => handleViewStats(campaign)}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      background: theme.blue,
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                    }}
                  >
                    <BarChart3 size={14} />
                    Stats
                  </button>
                  <button
                    onClick={() => handleGenerateSubCampaigns(campaign)}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      background: theme.green,
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                    }}
                  >
                    <Settings size={14} />
                    Generate
                  </button>
                  <button
                    onClick={() => handleEdit(campaign)}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      background: theme.sub,
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                    }}
                  >
                    <Edit size={14} />
                    Edit
                  </button>
                  <button
                    onClick={() => handleDelete(campaign)}
                    style={{
                      flex: 1,
                      padding: '8px 12px',
                      background: theme.red,
                      color: '#fff',
                      border: 'none',
                      borderRadius: 6,
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      gap: 4,
                    }}
                  >
                    <Trash2 size={14} />
                    Delete
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create/Edit Modal */}
      {(showCreateModal || showEditModal) && (
        <MasterCampaignModal
          theme={theme}
          campaign={editingCampaign}
          onClose={() => {
            setShowCreateModal(false);
            setShowEditModal(false);
            setEditingCampaign(null);
          }}
          onSave={() => {
            loadMasterCampaigns();
            setShowCreateModal(false);
            setShowEditModal(false);
            setEditingCampaign(null);
          }}
        />
      )}

      {/* Stats Modal */}
      {showStatsModal && campaignStats && (
        <MasterCampaignStatsModal
          theme={theme}
          campaign={selectedCampaign}
          stats={campaignStats}
          onClose={() => {
            setShowStatsModal(false);
            setSelectedCampaign(null);
            setCampaignStats(null);
          }}
        />
      )}

      {/* Confirm Modal */}
      {confirmModal.isOpen && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(0,0,0,0.5)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 1000,
          }}
        >
          <div
            style={{
              background: theme.card,
              borderRadius: 12,
              padding: 24,
              maxWidth: 400,
              width: '90%',
            }}
          >
            <h3 style={{
              margin: 0,
              fontSize: 18,
              fontWeight: 700,
              color: theme.txt,
              marginBottom: 12,
            }}>
              {confirmModal.title}
            </h3>
            <p style={{
              margin: 0,
              fontSize: 14,
              color: theme.sub,
              marginBottom: 20,
            }}>
              {confirmModal.message}
            </p>
            <div style={{
              display: 'flex',
              gap: 12,
              justifyContent: 'flex-end',
            }}>
              {confirmModal.showCancel && (
                <button
                  onClick={() => setConfirmModal({ isOpen: false })}
                  style={{
                    padding: '8px 16px',
                    background: 'transparent',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 6,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    color: theme.txt,
                  }}
                >
                  Cancel
                </button>
              )}
              <button
                onClick={() => {
                  console.log('[MODAL] Confirm button clicked');
                  if (confirmModal.onConfirm) {
                    confirmModal.onConfirm();
                  } else {
                    console.log('[MODAL] No onConfirm function found');
                  }
                }}
                style={{
                  padding: '8px 16px',
                  background: confirmModal.type === 'danger' ? theme.red : 
                           confirmModal.type === 'warning' ? theme.orange : theme.pri,
                  border: 'none',
                  borderRadius: 6,
                  fontSize: 14,
                  fontWeight: 600,
                  cursor: 'pointer',
                  color: '#fff',
                }}
              >
                Confirm
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Generation Config Modal */}
      {showConfigModal && configCampaign && (
        <GenerationConfigModal
          campaign={configCampaign}
          theme={theme}
          onClose={() => {
            setShowConfigModal(false);
            setConfigCampaign(null);
          }}
          onSave={() => {
            loadMasterCampaigns();
          }}
        />
      )}
    </div>
  );
}

// Master Campaign Create/Edit Modal Component
function MasterCampaignModal({ theme, campaign, onClose, onSave }) {
  const [formData, setFormData] = useState({
    title: campaign?.title || '',
    description: campaign?.description || '',
    start_date: campaign?.start_date ? new Date(campaign.start_date).toISOString().slice(0, 16) : '',
    end_date: campaign?.end_date ? new Date(campaign.end_date).toISOString().slice(0, 16) : '',
    status: campaign?.status || 'draft',
    auto_generate_daily: campaign?.auto_generate_daily ?? true,
    auto_generate_weekly: campaign?.auto_generate_weekly ?? true,
    auto_generate_monthly: campaign?.auto_generate_monthly ?? true,
    auto_generate_grand: campaign?.auto_generate_grand ?? true,
    min_followers: campaign?.min_followers || 0,
    min_level: campaign?.min_level || 1,
    required_hashtags: campaign?.required_hashtags || '',
  });
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);

    try {
      const url = campaign 
        ? `/admin/master-campaigns/${campaign.id}/`
        : '/admin/master-campaigns/';
      
      const method = campaign ? 'PUT' : 'POST';
      
      await api.request(url, {
        method,
        body: JSON.stringify(formData),
      });
      
      onSave();
    } catch (error) {
      console.error('Failed to save master campaign:', error);
      alert('Failed to save master campaign');
    } finally {
      setLoading(false);
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
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: theme.card,
          borderRadius: 16,
          padding: 24,
          maxWidth: 600,
          width: '90%',
          maxHeight: '80vh',
          overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{
          margin: 0,
          fontSize: 20,
          fontWeight: 700,
          color: theme.txt,
          marginBottom: 20,
        }}>
          {campaign ? 'Edit Master Campaign' : 'Create Master Campaign'}
        </h2>

        <form onSubmit={handleSubmit}>
          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
              Title *
            </label>
            <input
              type="text"
              value={formData.title}
              onChange={(e) => setFormData({ ...formData, title: e.target.value })}
              placeholder="e.g., Season 1 Campaign"
              required
              style={{
                width: '100%',
                padding: 12,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                background: theme.bg,
                color: theme.txt,
              }}
            />
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
              Description *
            </label>
            <textarea
              value={formData.description}
              onChange={(e) => setFormData({ ...formData, description: e.target.value })}
              placeholder="Overall description of the season"
              required
              rows={3}
              style={{
                width: '100%',
                padding: 12,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                background: theme.bg,
                color: theme.txt,
                resize: 'vertical',
              }}
            />
          </div>

          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                Start Date *
              </label>
              <input
                type="datetime-local"
                value={formData.start_date}
                onChange={(e) => setFormData({ ...formData, start_date: e.target.value })}
                required
                style={{
                  width: '100%',
                  padding: 12,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                End Date *
              </label>
              <input
                type="datetime-local"
                value={formData.end_date}
                onChange={(e) => setFormData({ ...formData, end_date: e.target.value })}
                required
                style={{
                  width: '100%',
                  padding: 12,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
              Status
            </label>
            <select
              value={formData.status}
              onChange={(e) => setFormData({ ...formData, status: e.target.value })}
              style={{
                width: '100%',
                padding: 12,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                background: theme.bg,
                color: theme.txt,
              }}
            >
              <option value="draft">Draft</option>
              <option value="upcoming">Upcoming</option>
              <option value="active">Active</option>
              <option value="completed">Completed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <div style={{ marginBottom: 16 }}>
            <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
              Auto-Generation Settings
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={formData.auto_generate_daily}
                  onChange={(e) => setFormData({ ...formData, auto_generate_daily: e.target.checked })}
                />
                Generate Daily Campaigns
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={formData.auto_generate_weekly}
                  onChange={(e) => setFormData({ ...formData, auto_generate_weekly: e.target.checked })}
                />
                Generate Weekly Campaigns
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={formData.auto_generate_monthly}
                  onChange={(e) => setFormData({ ...formData, auto_generate_monthly: e.target.checked })}
                />
                Generate Monthly Campaigns
              </label>
              <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 14 }}>
                <input
                  type="checkbox"
                  checked={formData.auto_generate_grand}
                  onChange={(e) => setFormData({ ...formData, auto_generate_grand: e.target.checked })}
                />
                Generate Grand Campaign
              </label>
            </div>
          </div>

          <div style={{ display: 'flex', gap: 16, marginBottom: 16 }}>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                Min Followers
              </label>
              <input
                type="number"
                value={formData.min_followers}
                onChange={(e) => setFormData({ ...formData, min_followers: parseInt(e.target.value) || 0 })}
                min="0"
                style={{
                  width: '100%',
                  padding: 12,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>
            <div style={{ flex: 1 }}>
              <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                Min Level
              </label>
              <input
                type="number"
                value={formData.min_level}
                onChange={(e) => setFormData({ ...formData, min_level: parseInt(e.target.value) || 1 })}
                min="1"
                style={{
                  width: '100%',
                  padding: 12,
                  border: `1px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt,
                }}
              />
            </div>
          </div>

          <div style={{ marginBottom: 20 }}>
            <label style={{ display: 'block', fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
              Required Hashtags
            </label>
            <input
              type="text"
              value={formData.required_hashtags}
              onChange={(e) => setFormData({ ...formData, required_hashtags: e.target.value })}
              placeholder="comma,separated,hashtags"
              style={{
                width: '100%',
                padding: 12,
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                background: theme.bg,
                color: theme.txt,
              }}
            />
          </div>

          <div style={{
            display: 'flex',
            gap: 12,
            justifyContent: 'flex-end',
          }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '10px 20px',
                background: 'transparent',
                border: `1px solid ${theme.border}`,
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                color: theme.txt,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading}
              style={{
                padding: '10px 20px',
                background: theme.pri,
                border: 'none',
                borderRadius: 8,
                fontSize: 14,
                fontWeight: 600,
                cursor: loading ? 'not-allowed' : 'pointer',
                color: '#fff',
                opacity: loading ? 0.7 : 1,
              }}
            >
              {loading ? 'Saving...' : (campaign ? 'Update' : 'Create')}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}

// Master Campaign Stats Modal Component
function MasterCampaignStatsModal({ theme, campaign, stats, onClose }) {
  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.5)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: theme.card,
          borderRadius: 16,
          padding: 24,
          maxWidth: 800,
          width: '90%',
          maxHeight: '80vh',
          overflow: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{
          margin: 0,
          fontSize: 20,
          fontWeight: 700,
          color: theme.txt,
          marginBottom: 20,
        }}>
          {campaign.title} - Statistics
        </h2>

        {/* Campaign Overview */}
        <div style={{
          background: theme.bg,
          borderRadius: 8,
          padding: 16,
          marginBottom: 20,
        }}>
          <h3 style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            color: theme.txt,
            marginBottom: 12,
          }}>
            Campaign Overview
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: 16,
          }}>
            <div>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Duration</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: theme.txt }}>
                {campaign.duration_days} days
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Status</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: theme.txt }}>
                {campaign.status}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Current Phase</div>
              <div style={{ fontSize: 18, fontWeight: 700, color: theme.txt }}>
                {campaign.current_phase}
              </div>
            </div>
          </div>
        </div>

        {/* Campaign Statistics */}
        <div style={{
          background: theme.bg,
          borderRadius: 8,
          padding: 16,
          marginBottom: 20,
        }}>
          <h3 style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            color: theme.txt,
            marginBottom: 12,
          }}>
            Sub-Campaigns
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(120px, 1fr))',
            gap: 16,
          }}>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.blue }}>
                {stats.campaign_stats.daily}
              </div>
              <div style={{ fontSize: 12, color: theme.sub }}>Daily</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.green }}>
                {stats.campaign_stats.weekly}
              </div>
              <div style={{ fontSize: 12, color: theme.sub }}>Weekly</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.orange }}>
                {stats.campaign_stats.monthly}
              </div>
              <div style={{ fontSize: 12, color: theme.sub }}>Monthly</div>
            </div>
            <div style={{ textAlign: 'center' }}>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.pri }}>
                {stats.campaign_stats.grand}
              </div>
              <div style={{ fontSize: 12, color: theme.sub }}>Grand</div>
            </div>
          </div>
        </div>

        {/* Participant Statistics */}
        <div style={{
          background: theme.bg,
          borderRadius: 8,
          padding: 16,
          marginBottom: 20,
        }}>
          <h3 style={{
            margin: 0,
            fontSize: 16,
            fontWeight: 600,
            color: theme.txt,
            marginBottom: 12,
          }}>
            Participants
          </h3>
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
            gap: 16,
          }}>
            <div>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Total</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.txt }}>
                {stats.participant_stats.total}
              </div>
            </div>
            <div>
              <div style={{ fontSize: 12, color: theme.sub, marginBottom: 4 }}>Active</div>
              <div style={{ fontSize: 24, fontWeight: 700, color: theme.green }}>
                {stats.participant_stats.active}
              </div>
            </div>
          </div>
        </div>

        {/* Top Performers */}
        {stats.participant_stats.top_performers && stats.participant_stats.top_performers.length > 0 && (
          <div style={{
            background: theme.bg,
            borderRadius: 8,
            padding: 16,
            marginBottom: 20,
          }}>
            <h3 style={{
              margin: 0,
              fontSize: 16,
              fontWeight: 600,
              color: theme.txt,
              marginBottom: 12,
            }}>
              Top Performers
            </h3>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {stats.participant_stats.top_performers.map((performer, index) => (
                <div key={performer.user__username} style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  padding: 8,
                  background: theme.card,
                  borderRadius: 6,
                }}>
                  <div style={{
                    width: 24,
                    height: 24,
                    borderRadius: '50%',
                    background: index === 0 ? theme.pri : index === 1 ? theme.sub : theme.border,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 12,
                    fontWeight: 700,
                    color: '#fff',
                  }}>
                    {index + 1}
                  </div>
                  <div style={{ flex: 1 }}>
                    <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>
                      {performer.user__username}
                    </div>
                    <div style={{ fontSize: 12, color: theme.sub }}>
                      {performer.total_posts} posts
                    </div>
                  </div>
                  <div style={{
                    fontSize: 16,
                    fontWeight: 700,
                    color: theme.txt,
                  }}>
                    {performer.total_score}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div style={{
          display: 'flex',
          justifyContent: 'flex-end',
        }}>
          <button
            onClick={onClose}
            style={{
              padding: '10px 20px',
              background: theme.pri,
              border: 'none',
              borderRadius: 8,
              fontSize: 14,
              fontWeight: 600,
              cursor: 'pointer',
              color: '#fff',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}




