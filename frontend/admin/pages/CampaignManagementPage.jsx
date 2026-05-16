import { useState, useEffect } from 'react';
import { Trophy, Plus, Edit, Trash2, Users, Award, BarChart3, X, TrendingUp, Star, CheckCircle, Clock, XCircle, Crown } from 'lucide-react';
import api from '../../api';
import { ConfirmModal } from '../components/ConfirmModal';
import { EditCampaignModal } from './EditCampaignModal';

export function CampaignManagementPage({ theme, onManageCampaign }) {
  const [campaigns, setCampaigns] = useState([]);
  const [masterCampaigns, setMasterCampaigns] = useState([]);
  const [selectedMasterCampaign, setSelectedMasterCampaign] = useState(null);
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('all');
  const [campaignTypeFilter, setCampaignTypeFilter] = useState('all');
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editingCampaign, setEditingCampaign] = useState(null);
  const [selectedCampaign, setSelectedCampaign] = useState(null);
  const [analyticsCampaign, setAnalyticsCampaign] = useState(null);
  const [confirmModal, setConfirmModal] = useState({ isOpen: false });
  const [successModal, setSuccessModal] = useState({ isOpen: false, campaign: null });

  useEffect(() => {
    loadCampaigns();
    loadMasterCampaigns();
  }, [statusFilter, selectedMasterCampaign, campaignTypeFilter]);

  const loadCampaigns = async () => {
    try {
      setLoading(true);
      let filterParams = [];
      if (statusFilter !== 'all') filterParams.push(`status=${statusFilter}`);
      if (selectedMasterCampaign) filterParams.push(`master_campaign=${selectedMasterCampaign}`);
      if (campaignTypeFilter !== 'all') filterParams.push(`campaign_type=${campaignTypeFilter}`);
      
      const filterParam = filterParams.length > 0 ? `?${filterParams.join('&')}` : '';
      const response = await api.request(`/admin/campaigns/${filterParam}`);
      setCampaigns(response.campaigns || []);
    } catch (error) {
      console.error('Failed to load campaigns:', error);
      // Clear campaigns on error to avoid stale data
      setCampaigns([]);
    } finally {
      setLoading(false);
    }
  };

  const loadMasterCampaigns = async () => {
    try {
      const response = await api.request('/admin/master-campaigns/');
      setMasterCampaigns(response.master_campaigns || []);
      // Auto-select first master campaign if none selected
      if (!selectedMasterCampaign && response.master_campaigns && response.master_campaigns.length > 0) {
        setSelectedMasterCampaign(response.master_campaigns[0].id);
      }
    } catch (error) {
      console.error('Failed to load master campaigns:', error);
      setMasterCampaigns([]);
    }
  };

  const handleDelete = (campaign) => {
    const deleteUrl = `/admin/campaigns/${campaign.id}/delete/`;
    
    setConfirmModal({
      isOpen: true,
      title: 'Delete Campaign',
      message: `Are you sure you want to delete "${campaign.title}"? This action cannot be undone.`,
      type: 'danger',
      showCancel: true,
      onConfirm: async () => {
        try {
          await api.request(deleteUrl, { method: 'DELETE' });
          // Immediately remove from list
          setCampaigns(prev => prev.filter(c => c.id !== campaign.id));
          // Show success notification
          setConfirmModal({ 
            isOpen: true, 
            title: 'Success', 
            message: `Campaign "${campaign.title}" deleted successfully!`,
            type: 'success',
            showCancel: false,
            onConfirm: () => setConfirmModal({ isOpen: false })
          });
        } catch (error) {
          console.error('[DELETE] Failed:', error);
          
          if (error.status === 404) {
            // Already gone, remove from list
            setCampaigns(prev => prev.filter(c => c.id !== campaign.id));
            setConfirmModal({ 
              isOpen: true, 
              title: 'Campaign Removed', 
              message: 'Campaign was already deleted.',
              type: 'info',
              showCancel: false,
              onConfirm: () => setConfirmModal({ isOpen: false })
            });
          } else {
            setConfirmModal({ 
              isOpen: true, 
              title: 'Error', 
              message: 'Failed to delete campaign. Please try again.',
              type: 'error',
              showCancel: false,
              onConfirm: () => setConfirmModal({ isOpen: false })
            });
          }
        }
      },
      onCancel: () => setConfirmModal({ isOpen: false })
    });
  };

  const handleAnnounceWinners = (campaign) => {
    setConfirmModal({
      isOpen: true,
      title: 'Announce Winners',
      message: `Announce winners for "${campaign.title}"? Top ${campaign.winner_count} entries will be selected.`,
      type: 'success',
      onConfirm: async () => {
        try {
          await api.request(`/admin/campaigns/${campaign.id}/announce-winners/`, { method: 'POST' });
          loadCampaigns();
        } catch (error) {
          console.error('Failed to announce winners:', error);
        }
      }
    });
  };

  const handleStatusChange = async (campaignId, newStatus) => {
    try {
      // Find campaign to check type
      const campaign = campaigns.find(c => c.id === campaignId);
      
      // If grand campaign, allow manual voting phase change
      // For others, don't allow manual voting phase
      if (newStatus === 'voting' && campaign?.campaign_type !== 'grand') {
         setConfirmModal({
            isOpen: true,
            title: 'Invalid Action',
            message: 'Only Grand Campaigns can enter a voting phase.',
            type: 'error',
            showCancel: false,
            onConfirm: () => setConfirmModal({ isOpen: false })
          });
          return;
      }
      
      await api.request(`/admin/campaigns/${campaignId}/update/`, {
        method: 'PATCH',
        body: JSON.stringify({ status: newStatus })
      });
      // Update local state immediately
      setCampaigns(prev => prev.map(c => 
        c.id === campaignId ? { ...c, status: newStatus } : c
      ));
      // Show success message
      setConfirmModal({
        isOpen: true,
        title: 'Success',
        message: `Campaign status updated to "${newStatus}"`,
        type: 'success',
        showCancel: false,
        onConfirm: () => setConfirmModal({ isOpen: false })
      });
    } catch (error) {
      console.error('Failed to update campaign status:', error);
      if (error.status === 404) {
        setCampaigns(prev => prev.filter(c => c.id !== campaignId));
        setConfirmModal({
          isOpen: true,
          title: 'Campaign Not Found',
          message: 'Campaign no longer exists.',
          type: 'error',
          showCancel: false,
          onConfirm: () => setConfirmModal({ isOpen: false })
        });
      } else {
        setConfirmModal({
          isOpen: true,
          title: 'Error',
          message: 'Failed to update campaign status. Please try again.',
          type: 'error',
          showCancel: false,
          onConfirm: () => setConfirmModal({ isOpen: false })
        });
      }
    }
  };

  const handleEditCampaign = (campaign) => {
    setEditingCampaign(campaign);
    setShowEditModal(true);
  };

  const getStatusColor = (status) => {
    switch (status) {
      case 'active': return theme.green;
      case 'voting': return theme.blue;
      case 'completed': return theme.sub;
      case 'draft': return theme.orange;
      case 'cancelled': return theme.red;
      default: return theme.sub;
    }
  };

  return (
    <div>
      {/* Header */}
      <div style={{
        display: 'flex',
        flexDirection: window.innerWidth < 768 ? 'column' : 'row',
        justifyContent: 'space-between',
        alignItems: window.innerWidth < 768 ? 'flex-start' : 'center',
        marginBottom: 32,
        gap: 16,
      }}>
        <div>
          <h1 style={{
            margin: 0,
            fontSize: window.innerWidth < 768 ? 24 : 32,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 8,
          }}>
            Campaign Management
          </h1>
          <p style={{
            margin: 0,
            fontSize: window.innerWidth < 768 ? 14 : 16,
            color: theme.sub,
          }}>
            Create and manage sub-campaigns under master campaigns
          </p>
          
          {/* Master Campaign Selector */}
          {masterCampaigns.length > 0 && (
            <div style={{ marginTop: 12 }}>
              <label style={{ 
                display: 'block', 
                fontSize: 12, 
                fontWeight: 600, 
                color: theme.txt, 
                marginBottom: 4 
              }}>
                Master Campaign:
              </label>
              <select
                value={selectedMasterCampaign || ''}
                onChange={(e) => setSelectedMasterCampaign(parseInt(e.target.value) || null)}
                style={{
                  padding: '8px 12px',
                  border: `1px solid ${theme.border}`,
                  borderRadius: 6,
                  fontSize: 14,
                  background: theme.bg,
                  color: theme.txt,
                  minWidth: 200,
                }}
              >
                <option value="">Select Master Campaign</option>
                {masterCampaigns.map((mc) => (
                  <option key={mc.id} value={mc.id}>
                    {mc.title} ({mc.status})
                  </option>
                ))}
              </select>
            </div>
          )}
          
          {masterCampaigns.length === 0 && (
            <div style={{
              marginTop: 12,
              padding: 8,
              background: `${theme.orange}15`,
              border: `1px solid ${theme.orange}`,
              borderRadius: 6,
              fontSize: 12,
              color: theme.orange,
            }}>
              <strong>No Master Campaigns Found</strong><br />
              Please create a Master Campaign first to manage sub-campaigns.
            </div>
          )}
        </div>
        
        <button
          onClick={() => setShowCreateModal(true)}
          disabled={!selectedMasterCampaign}
          style={{
            padding: '12px 24px',
            background: selectedMasterCampaign ? '#2563EB' : '#333333',
            border: 'none',
            borderRadius: 8,
            color: '#FFFFFF',
            fontSize: 14,
            fontWeight: 600,
            cursor: selectedMasterCampaign ? 'pointer' : 'not-allowed',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
            width: window.innerWidth < 768 ? '100%' : 'auto',
            justifyContent: 'center',
            opacity: selectedMasterCampaign ? 1 : 0.6,
          }}
        >
          <Plus size={16} />
          Create Campaign
        </button>
      </div>

      {/* Filters */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 24,
        overflowX: 'auto',
        paddingBottom: 8,
      }}>
        {['all', 'draft', 'active', 'voting', 'completed'].map(status => (
          <button
            key={status}
            onClick={() => setStatusFilter(status)}
            style={{
              padding: '8px 16px',
              background: statusFilter === status ? '#2563EB20' : '#1A1A1A',
              border: `1px solid ${statusFilter === status ? '#2563EB' : '#333333'}`,
              borderRadius: 8,
              color: statusFilter === status ? '#2563EB' : '#FFFFFF',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              textTransform: 'capitalize',
              whiteSpace: 'nowrap',
            }}
          >
            {status}
          </button>
        ))}
      </div>

      {/* Campaign Type Filter */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 24,
        overflowX: 'auto',
        paddingBottom: 8,
      }}>
        {[
          { value: 'all', label: 'All Types', icon: '🎯' },
          { value: 'daily', label: 'Daily', icon: '📅' },
          { value: 'weekly', label: 'Weekly', icon: '📊' },
          { value: 'monthly', label: 'Monthly', icon: '📆' },
          { value: 'grand', label: 'Grand', icon: '👑' }
        ].map(type => (
          <button
            key={type.value}
            onClick={() => setCampaignTypeFilter(type.value)}
            style={{
              padding: '8px 16px',
              background: campaignTypeFilter === type.value ? '#3B82F620' : '#1A1A1A',
              border: `1px solid ${campaignTypeFilter === type.value ? '#3B82F6' : '#333333'}`,
              borderRadius: 8,
              color: campaignTypeFilter === type.value ? '#3B82F6' : '#FFFFFF',
              fontSize: 13,
              fontWeight: 600,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            <span>{type.icon}</span>
            {type.label}
          </button>
        ))}
      </div>

      {/* Campaigns Grid */}
      {loading ? (
        <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
          Loading campaigns...
        </div>
      ) : campaigns.length === 0 ? (
        <div style={{
          background: theme.card,
          borderRadius: 12,
          padding: 60,
          textAlign: 'center',
          border: `1px solid ${theme.border}`,
        }}>
          <Trophy size={48} color={theme.sub} style={{ marginBottom: 16 }} />
          <h3 style={{ margin: 0, fontSize: 18, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
            No campaigns yet
          </h3>
          <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
            Create your first campaign to get started
          </p>
        </div>
      ) : (
        <div style={{
          display: 'grid',
          gridTemplateColumns: window.innerWidth < 768 ? '1fr' : 'repeat(auto-fill, minmax(350px, 1fr))',
          gap: 24,
        }}>
          {campaigns.map(campaign => {
            const statusColor = getStatusColor(campaign.status);
            
            return (
              <div
                key={campaign.id}
                style={{
                  background: theme.card,
                  borderRadius: 12,
                  overflow: 'hidden',
                  border: `1px solid ${theme.border}`,
                }}
              >
                {campaign.image && (
                  <div style={{
                    width: '100%',
                    height: 200,
                    background: `url(${campaign.image}) center/cover`,
                  }} />
                )}
                
                <div style={{ padding: 20 }}>
                  <div style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    marginBottom: 12,
                  }}>
                    <div style={{ flex: 1 }}>
                      <h3 style={{
                        margin: 0,
                        fontSize: 18,
                        fontWeight: 700,
                        color: theme.txt,
                      }}>
                        {campaign.title}
                      </h3>
                      {campaign.campaign_type && (
                        <div style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: 4,
                          padding: '2px 8px',
                          borderRadius: 4,
                          fontSize: 10,
                          fontWeight: 700,
                          textTransform: 'uppercase',
                          background: campaign.campaign_type === 'daily' ? theme.blue + '20' :
                                     campaign.campaign_type === 'weekly' ? theme.green + '20' :
                                     campaign.campaign_type === 'monthly' ? theme.orange + '20' :
                                     campaign.campaign_type === 'grand' ? theme.pri + '20' : theme.sub + '20',
                          color: campaign.campaign_type === 'daily' ? theme.blue :
                                 campaign.campaign_type === 'weekly' ? theme.green :
                                 campaign.campaign_type === 'monthly' ? theme.orange :
                                 campaign.campaign_type === 'grand' ? theme.pri : theme.sub,
                          marginTop: 4,
                        }}>
                          {campaign.campaign_type === 'daily' ? '📅' :
                           campaign.campaign_type === 'weekly' ? '📊' :
                           campaign.campaign_type === 'monthly' ? '📆' :
                           campaign.campaign_type === 'grand' ? '👑' : '🎯'}
                          {campaign.campaign_type}
                        </div>
                      )}
                    </div>
                    <span style={{
                      padding: '4px 8px',
                      borderRadius: 4,
                      fontSize: 11,
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      background: statusColor + '20',
                      color: statusColor,
                      marginLeft: 8,
                    }}>
                      {campaign.status}
                    </span>
                  </div>
                  
                  <div style={{ marginBottom: 12 }}>
                    <label style={{ display: 'block', fontSize: 11, fontWeight: 600, color: theme.sub, marginBottom: 6 }}>
                      Change Status:
                    </label>
                    <select
                      value={campaign.status}
                      onChange={(e) => handleStatusChange(campaign.id, e.target.value)}
                      style={{
                        width: '100%',
                        padding: '6px 10px',
                        border: `2px solid ${theme.border}`,
                        borderRadius: 6,
                        fontSize: 13,
                        fontWeight: 600,
                        color: theme.txt,
                        background: '#fff',
                        cursor: 'pointer',
                        outline: 'none',
                      }}
                    >
                      <option value="draft">📝 Draft</option>
                      <option value="active">✅ Active (Accepting Entries)</option>
                      <option value="voting">🗳️ Voting Phase</option>
                      <option value="completed">🏁 Completed</option>
                      <option value="cancelled">❌ Cancelled</option>
                    </select>
                  </div>
                  
                  <p style={{
                    margin: 0,
                    fontSize: 14,
                    color: theme.sub,
                    marginBottom: 16,
                    lineHeight: 1.5,
                  }}>
                    {campaign.description.substring(0, 100)}...
                  </p>
                  
                  <div style={{
                    display: 'flex',
                    gap: 16,
                    marginBottom: 16,
                    padding: '12px 0',
                    borderTop: `1px solid ${theme.border}`,
                    borderBottom: `1px solid ${theme.border}`,
                  }}>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, color: theme.sub, marginBottom: 4 }}>
                        Prize
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: theme.pri }}>
                        {campaign.prize_value} ETB
                      </div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, color: theme.sub, marginBottom: 4 }}>
                        Entries
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: theme.txt }}>
                        {campaign.total_entries}
                      </div>
                    </div>
                    <div style={{ flex: 1 }}>
                      <div style={{ fontSize: 11, color: theme.sub, marginBottom: 4 }}>
                        Votes
                      </div>
                      <div style={{ fontSize: 16, fontWeight: 700, color: theme.txt }}>
                        {campaign.total_votes}
                      </div>
                    </div>
                  </div>
                  
                  <div style={{ display: 'flex', gap: 8, marginBottom: 8 }}>
                    <button
                      onClick={() => setSelectedCampaign(campaign)}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: '#3B82F615',
                        border: 'none',
                        borderRadius: 6,
                        color: '#3B82F6',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                      }}
                    >
                      <Users size={14} />
                      View Entries
                    </button>
                    <button
                      onClick={() => setAnalyticsCampaign(campaign)}
                      style={{
                        flex: 1,
                        padding: '8px',
                        background: '#8B5CF615',
                        border: 'none',
                        borderRadius: 6,
                        color: '#8B5CF6',
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: 'pointer',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: 6,
                      }}
                    >
                      <BarChart3 size={14} />
                      Analytics
                    </button>
                    {campaign.status === 'voting' && !campaign.winners_announced && (
                      <button
                        onClick={() => handleAnnounceWinners(campaign)}
                        style={{
                          flex: 1,
                          padding: '8px',
                          background: '#10B98115',
                          border: 'none',
                          borderRadius: 6,
                          color: '#10B981',
                          fontSize: 13,
                          fontWeight: 600,
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          gap: 6,
                        }}
                      >
                        <Award size={14} />
                        Winners
                      </button>
                    )}
                  </div>
                  
                  {/* Campaign Management Actions */}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button
                      onClick={() => onManageCampaign?.(campaign.id, 'scoring', campaign.campaign_type)}
                      style={{
                        flex: 1,
                        padding: '6px',
                        background: '#8B5CF615',
                        border: 'none',
                        borderRadius: 6,
                        color: theme.txt,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      ⚙️ Scoring
                    </button>
                    <button
                      onClick={() => onManageCampaign?.(campaign.id, 'themes')}
                      style={{
                        flex: 1,
                        padding: '6px',
                        background: '#8fc44115',
                        border: 'none',
                        borderRadius: 6,
                        color: theme.txt,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      📅 Themes
                    </button>
                    <button
                      onClick={() => onManageCampaign?.(campaign.id, 'moderation')}
                      style={{
                        flex: 1,
                        padding: '6px',
                        background: '#10B98115',
                        border: 'none',
                        borderRadius: 6,
                        color: theme.txt,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      ✅ Moderation
                    </button>
                    <button
                      onClick={() => onManageCampaign?.(campaign.id, 'leaderboard', campaign.campaign_type, campaign)}
                      style={{
                        flex: 1,
                        padding: '6px',
                        background: '#C8B56A15',
                        border: 'none',
                        borderRadius: 6,
                        color: theme.txt,
                        fontSize: 12,
                        fontWeight: 600,
                        cursor: 'pointer',
                      }}
                    >
                      🏆 Leaderboard
                    </button>
                  </div>
                  
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    <button
                      onClick={() => handleEditCampaign(campaign)}
                      style={{
                        padding: '8px',
                        background: '#8fc44115',
                        border: 'none',
                        borderRadius: 6,
                        color: '#8fc441',
                        cursor: 'pointer',
                      }}
                    >
                      <Edit size={14} />
                    </button>
                    <button
                      onClick={() => handleDelete(campaign)}
                      style={{
                        padding: '8px',
                        background: '#EF444415',
                        border: 'none',
                        borderRadius: 6,
                        color: '#EF4444',
                        cursor: 'pointer',
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Campaign Modal */}
      {showCreateModal && (
        <CreateCampaignModal
          theme={theme}
          selectedMasterCampaign={selectedMasterCampaign}
          onClose={() => setShowCreateModal(false)}
          onSuccess={(response) => {
            setShowCreateModal(false);
            loadCampaigns();
          }}
        />
      )}

      {/* Success Modal */}
      {successModal.isOpen && (
        <SuccessModal
          theme={theme}
          campaign={successModal.campaign}
          onClose={() => setSuccessModal({ isOpen: false, campaign: null })}
        />
      )}

      {/* Edit Campaign Modal */}
      {showEditModal && editingCampaign && (
        <EditCampaignModal
          theme={theme}
          campaign={editingCampaign}
          selectedMasterCampaign={selectedMasterCampaign}
          onClose={() => {
            setShowEditModal(false);
            setEditingCampaign(null);
          }}
          onSuccess={(result) => {
            setShowEditModal(false);
            setEditingCampaign(null);
            if (result === 'CAMPAIGN_NOT_FOUND') {
              // Remove the stale campaign from the list
              setCampaigns(prev => prev.filter(c => c.id !== editingCampaign.id));
            } else {
              loadCampaigns();
            }
          }}
        />
      )}

      {/* Campaign Entries Modal */}
      {selectedCampaign && (
        <CampaignEntriesModal
          theme={theme}
          campaign={selectedCampaign}
          onClose={() => setSelectedCampaign(null)}
        />
      )}

      {/* Campaign Analytics Modal */}
      {analyticsCampaign && (
        <CampaignAnalyticsModal
          theme={theme}
          campaign={analyticsCampaign}
          onClose={() => setAnalyticsCampaign(null)}
        />
      )}

      {/* Confirm Modal */}
      <ConfirmModal
        theme={theme}
        {...confirmModal}
        onClose={() => setConfirmModal({ isOpen: false })}
      />
    </div>
  );
}

function CreateCampaignModal({ theme, onClose, onSuccess, selectedMasterCampaign }) {
  const [masterCampaigns, setMasterCampaigns] = useState([]);
  const [formData, setFormData] = useState({
    title: '',
    description: '',
    campaign_type: 'grand',
    master_campaign: selectedMasterCampaign || '',
    prize_title: '',
    prize_description: '',
    prize_value: '',
    status: 'active',
    min_followers: 0,
    min_level: 1,
    min_votes_per_reel: 0,
    required_hashtags: '',
    start_date: '',
    entry_deadline: '',
    voting_start: '',
    voting_end: '',
    winner_count: 1,
  });
  const [imageFile, setImageFile] = useState(null);
  const [imagePreview, setImagePreview] = useState(null);
  const [error, setError] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);

  useEffect(() => {
    loadMasterCampaigns();
  }, []);

  const loadMasterCampaigns = async () => {
    try {
      const response = await api.request('/admin/master-campaigns/');
      setMasterCampaigns(response.master_campaigns || []);
    } catch (error) {
      console.error('Failed to load master campaigns:', error);
      setMasterCampaigns([]);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (isSubmitting) return;
    setError('');
    setIsSubmitting(true);
    
    try {
      // Create FormData for file upload
      const formDataToSend = new FormData();
      
      // Add all form fields
      formDataToSend.append('title', formData.title);
      formDataToSend.append('description', formData.description);
      formDataToSend.append('campaign_type', formData.campaign_type);
      formDataToSend.append('master_campaign', formData.master_campaign);
      formDataToSend.append('prize_title', formData.prize_title);
      formDataToSend.append('prize_description', formData.prize_description || formData.prize_title);
      formDataToSend.append('prize_value', formData.prize_value);
      formDataToSend.append('status', formData.status);
      formDataToSend.append('min_followers', formData.min_followers);
      formDataToSend.append('min_level', formData.min_level);
      formDataToSend.append('min_votes_per_reel', formData.min_votes_per_reel);
      formDataToSend.append('winner_count', formData.winner_count);
      formDataToSend.append('required_hashtags', formData.required_hashtags);
      
      // Convert dates to ISO format
      if (formData.start_date) {
        formDataToSend.append('start_date', new Date(formData.start_date).toISOString());
      }
      if (formData.entry_deadline) {
        formDataToSend.append('entry_deadline', new Date(formData.entry_deadline).toISOString());
      }
      if (formData.voting_start) {
        formDataToSend.append('voting_start', new Date(formData.voting_start).toISOString());
      }
      if (formData.voting_end) {
        formDataToSend.append('voting_end', new Date(formData.voting_end).toISOString());
      }
      
      // Add image if selected
      if (imageFile) {
        console.log('Adding image to FormData:', imageFile.name, imageFile.type, imageFile.size);
        formDataToSend.append('image', imageFile);
        console.log('FormData entries after adding image:');
        for (let [key, value] of formDataToSend.entries()) {
          console.log(`  ${key}:`, value instanceof File ? `File(${value.name}, ${value.type}, ${value.size})` : value);
        }
      } else {
        console.log('No image file to upload');
      }
      
      const response = await api.request('/admin/campaigns/create/', {
        method: 'POST',
        body: formDataToSend,
        isFormData: true
      });
      setIsSubmitting(false);
      onSuccess(response);
    } catch (error) {
      setIsSubmitting(false);
      console.error('Failed to create campaign:', error);
      const errorMsg = typeof error === 'string' ? error : error.message || 'Failed to create campaign';
      setError(errorMsg);
    }
  };
  
  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      console.log('File selected:', file.name, file.type, file.size);
      
      // Validate file type
      const allowedTypes = ['image/jpeg', 'image/jpg', 'image/png', 'image/gif', 'image/webp', 'video/mp4', 'video/webm', 'video/ogg', 'video/mov'];
      if (!allowedTypes.includes(file.type)) {
        setError('Invalid file type. Please upload an image (JPEG, PNG, GIF, WebP) or video (MP4, WebM, OGG, MOV).');
        return;
      }
      
      // Validate file size (50MB limit)
      const maxSize = 50 * 1024 * 1024; // 50MB
      if (file.size > maxSize) {
        setError('File too large. Please upload a file smaller than 50MB.');
        return;
      }
      
      setImageFile(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result);
        console.log('Preview set successfully');
      };
      reader.onerror = () => {
        setError('Failed to preview file. Please try another file.');
      };
      reader.readAsDataURL(file);
    }
  };

  const isMobile = window.innerWidth < 768;

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
        overflowY: 'auto',
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
          maxHeight: '90vh',
          overflowY: 'auto',
          boxShadow: '0 20px 60px rgba(0,0,0,0.3)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: 0, fontSize: 28, fontWeight: 700, color: theme.txt, marginBottom: 8 }}>
          Create New Campaign
        </h2>
        <p style={{ margin: 0, fontSize: 14, color: theme.sub, marginBottom: 32 }}>
          Set up a prize competition for your users
        </p>
        
        {error && (
          <div style={{
            padding: 12,
            background: theme.red + '15',
            border: `1px solid ${theme.red}`,
            borderRadius: 8,
            color: theme.red,
            fontSize: 14,
            marginBottom: 20,
          }}>
            {error}
          </div>
        )}
        
        <form onSubmit={handleSubmit}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
            {/* Basic Info */}
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                Campaign Type *
              </label>
              <select
                value={formData.campaign_type}
                onChange={(e) => setFormData({ ...formData, campaign_type: e.target.value })}
                required
                style={{
                  width: '100%',
                  padding: 12,
                  border: `2px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                  background: '#fff',
                }}
                onFocus={(e) => e.target.style.borderColor = theme.pri}
                onBlur={(e) => e.target.style.borderColor = theme.border}
              >
                <option value="daily">Daily Campaign (Scoring Only)</option>
                <option value="weekly">Weekly Campaign (Scoring Only)</option>
                <option value="monthly">Monthly Campaign (Scoring Only)</option>
                <option value="grand">Grand Campaign (Voting + Scoring)</option>
              </select>
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                Master Campaign *
              </label>
              <select
                value={formData.master_campaign}
                onChange={(e) => setFormData({ ...formData, master_campaign: e.target.value })}
                required
                style={{
                  width: '100%',
                  padding: 12,
                  border: `2px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                  background: '#fff',
                }}
                onFocus={(e) => e.target.style.borderColor = theme.pri}
                onBlur={(e) => e.target.style.borderColor = theme.border}
              >
                <option value="">Select Master Campaign</option>
                {masterCampaigns.map((mc) => (
                  <option key={mc.id} value={mc.id}>
                    {mc.title} ({mc.status})
                  </option>
                ))}
              </select>
              {masterCampaigns.length === 0 && (
                <div style={{
                  marginTop: 4,
                  fontSize: 12,
                  color: theme.red,
                }}>
                  No master campaigns available. Please create one first.
                </div>
              )}
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                Campaign Title *
              </label>
              <input
                type="text"
                placeholder="e.g., Summer Photo Contest 2024"
                value={formData.title}
                onChange={(e) => setFormData({ ...formData, title: e.target.value })}
                required
                style={{
                  width: '100%',
                  padding: 12,
                  border: `2px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  outline: 'none',
                  transition: 'border-color 0.2s',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => e.target.style.borderColor = theme.pri}
                onBlur={(e) => e.target.style.borderColor = theme.border}
              />
            </div>
            
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                Description *
              </label>
              <textarea
                placeholder="Describe your campaign..."
                value={formData.description}
                onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                required
                rows={3}
                style={{
                  width: '100%',
                  padding: 12,
                  border: `2px solid ${theme.border}`,
                  borderRadius: 8,
                  fontSize: 14,
                  fontFamily: 'inherit',
                  outline: 'none',
                  resize: 'vertical',
                  boxSizing: 'border-box',
                }}
                onFocus={(e) => e.target.style.borderColor = theme.pri}
                onBlur={(e) => e.target.style.borderColor = theme.border}
              />
            </div>
            
            {/* Banner Image/Video */}
            <div>
              <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                Campaign Banner (Image or Video)
              </label>
              <input
                type="file"
                accept="image/*,video/*"
                onChange={handleImageChange}
                style={{ display: 'none' }}
                id="campaign-image-upload"
              />
              <div 
                onClick={() => document.getElementById('campaign-image-upload').click()}
                style={{
                  border: `2px dashed ${theme.border}`,
                  borderRadius: 8,
                  padding: 20,
                  textAlign: 'center',
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                  background: imagePreview ? 'transparent' : theme.bg,
                }}
                onDragOver={(e) => {
                  e.preventDefault();
                  e.currentTarget.style.borderColor = theme.pri;
                }}
                onDragLeave={(e) => {
                  e.currentTarget.style.borderColor = theme.border;
                }}
                onDrop={(e) => {
                  e.preventDefault();
                  e.currentTarget.style.borderColor = theme.border;
                  const file = e.dataTransfer.files[0];
                  if (file) {
                    handleImageChange({ target: { files: [file] } });
                  }
                }}
              >
                {imagePreview ? (
                  <div style={{ position: 'relative' }}>
                    <img src={imagePreview} alt="Preview" style={{
                      maxWidth: '100%',
                      maxHeight: 200,
                      borderRadius: 8,
                    }} />
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setImageFile(null);
                        setImagePreview(null);
                      }}
                      style={{
                        position: 'absolute',
                        top: 8,
                        right: 8,
                        padding: '4px 8px',
                        background: theme.red,
                        color: '#fff',
                        border: 'none',
                        borderRadius: 4,
                        fontSize: 12,
                        cursor: 'pointer',
                      }}
                    >
                      Remove
                    </button>
                  </div>
                ) : (
                  <>
                    <div style={{ fontSize: 40, marginBottom: 8 }}>🖼️</div>
                    <div style={{ fontSize: 14, color: theme.txt, marginBottom: 4 }}>
                      Click to upload or drag and drop
                    </div>
                    <div style={{ fontSize: 12, color: theme.sub }}>
                      PNG, JPG, GIF or MP4 (Max 10MB)
                    </div>
                  </>
                )}
              </div>
              <div style={{ marginTop: 8, fontSize: 12, color: theme.sub, textAlign: 'center' }}>
                Optional: Add an eye-catching banner to attract participants
              </div>
            </div>
            
            {/* Prize Info */}
            <div style={{ 
              padding: 16, 
              background: theme.pri + '08', 
              borderRadius: 8,
              border: `1px solid ${theme.pri}30`,
            }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: theme.txt, marginBottom: 16 }}>
                Prize Details
              </h3>
              
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                  Prize Title *
                </label>
                <input
                  type="text"
                  placeholder="e.g., 25000 Birr Cash Prize"
                  value={formData.prize_title}
                  onChange={(e) => setFormData({ ...formData, prize_title: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: 12,
                    border: `2px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                  onFocus={(e) => e.target.style.borderColor = theme.pri}
                  onBlur={(e) => e.target.style.borderColor = theme.border}
                />
              </div>
              
              <div style={{ marginBottom: 16 }}>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                  Prize Description
                </label>
                <textarea
                  placeholder="Describe the prize details..."
                  value={formData.prize_description}
                  onChange={(e) => setFormData({ ...formData, prize_description: e.target.value })}
                  rows={2}
                  style={{
                    width: '100%',
                    padding: 12,
                    border: `2px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    fontFamily: 'inherit',
                    outline: 'none',
                    resize: 'vertical',
                    boxSizing: 'border-box',
                  }}
                  onFocus={(e) => e.target.style.borderColor = theme.pri}
                  onBlur={(e) => e.target.style.borderColor = theme.border}
                />
              </div>
              
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                  Prize Value (Birr) *
                </label>
                <input
                  type="number"
                  placeholder="500"
                  value={formData.prize_value}
                  onChange={(e) => setFormData({ ...formData, prize_value: e.target.value })}
                  required
                  min="0"
                  step="0.01"
                  style={{
                    width: '100%',
                    padding: 12,
                    border: `2px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                  onFocus={(e) => e.target.style.borderColor = theme.pri}
                  onBlur={(e) => e.target.style.borderColor = theme.border}
                />
              </div>
            </div>
            
            {/* Timeline */}
            <div>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: theme.txt, marginBottom: 16 }}>
                Campaign Timeline
              </h3>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
                {/* Start Date */}
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Start Date & Time *
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 8 }}>
                    <input
                      type="date"
                      value={formData.start_date.split('T')[0] || ''}
                      onChange={(e) => {
                        const time = formData.start_date.split('T')[1] || '09:00';
                        setFormData({ ...formData, start_date: `${e.target.value}T${time}` });
                      }}
                      required
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    />
                    <select
                      value={formData.start_date.split('T')[1]?.split(':')[0] || '09'}
                      onChange={(e) => {
                        const date = formData.start_date.split('T')[0] || '';
                        const mins = formData.start_date.split(':')[1] || '00';
                        setFormData({ ...formData, start_date: `${date}T${e.target.value}:${mins}` });
                      }}
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    >
                      {[...Array(12)].map((_, i) => {
                        const hour = i + 1;
                        return <option key={hour} value={hour.toString().padStart(2, '0')}>{hour}:00 AM</option>;
                      })}
                      {[...Array(12)].map((_, i) => {
                        const hour = i + 13;
                        return <option key={hour} value={hour.toString().padStart(2, '0')}>{i + 1}:00 PM</option>;
                      })}
                    </select>
                  </div>
                </div>
                
                {/* Entry Deadline */}
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Entry Deadline *
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 8 }}>
                    <input
                      type="date"
                      value={formData.entry_deadline.split('T')[0] || ''}
                      onChange={(e) => {
                        const time = formData.entry_deadline.split('T')[1] || '23:59';
                        setFormData({ ...formData, entry_deadline: `${e.target.value}T${time}` });
                      }}
                      required
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    />
                    <select
                      value={formData.entry_deadline.split('T')[1]?.split(':')[0] || '23'}
                      onChange={(e) => {
                        const date = formData.entry_deadline.split('T')[0] || '';
                        const mins = formData.entry_deadline.split(':')[1] || '59';
                        setFormData({ ...formData, entry_deadline: `${date}T${e.target.value}:${mins}` });
                      }}
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    >
                      {[...Array(12)].map((_, i) => {
                        const hour = i + 1;
                        return <option key={hour} value={hour.toString().padStart(2, '0')}>{hour}:00 AM</option>;
                      })}
                      {[...Array(12)].map((_, i) => {
                        const hour = i + 13;
                        return <option key={hour} value={hour.toString().padStart(2, '0')}>{i + 1}:00 PM</option>;
                      })}
                    </select>
                  </div>
                </div>
                
                {/* Voting Start */}
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Voting Start *
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 8 }}>
                    <input
                      type="date"
                      value={formData.voting_start.split('T')[0] || ''}
                      onChange={(e) => {
                        const time = formData.voting_start.split('T')[1] || '00:00';
                        setFormData({ ...formData, voting_start: `${e.target.value}T${time}` });
                      }}
                      required
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    />
                    <select
                      value={formData.voting_start.split('T')[1]?.split(':')[0] || '00'}
                      onChange={(e) => {
                        const date = formData.voting_start.split('T')[0] || '';
                        const mins = formData.voting_start.split(':')[1] || '00';
                        setFormData({ ...formData, voting_start: `${date}T${e.target.value}:${mins}` });
                      }}
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    >
                      {[...Array(12)].map((_, i) => {
                        const hour = i === 0 ? 12 : i;
                        return <option key={i} value={i.toString().padStart(2, '0')}>{hour}:00 AM</option>;
                      })}
                      {[...Array(12)].map((_, i) => {
                        const hour = i === 0 ? 12 : i;
                        return <option key={i + 12} value={(i + 12).toString().padStart(2, '0')}>{hour}:00 PM</option>;
                      })}
                    </select>
                  </div>
                </div>
                
                {/* Voting End */}
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Voting End *
                  </label>
                  <div style={{ display: 'grid', gridTemplateColumns: '2fr 1fr 1fr', gap: 8 }}>
                    <input
                      type="date"
                      value={formData.voting_end.split('T')[0] || ''}
                      onChange={(e) => {
                        const time = formData.voting_end.split('T')[1] || '23:59';
                        setFormData({ ...formData, voting_end: `${e.target.value}T${time}` });
                      }}
                      required
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    />
                    <select
                      value={formData.voting_end.split('T')[1]?.split(':')[0] || '23'}
                      onChange={(e) => {
                        const date = formData.voting_end.split('T')[0] || '';
                        const mins = formData.voting_end.split(':')[1] || '59';
                        setFormData({ ...formData, voting_end: `${date}T${e.target.value}:${mins}` });
                      }}
                      style={{
                        padding: 12,
                        border: `2px solid ${theme.border}`,
                        borderRadius: 8,
                        fontSize: 14,
                        outline: 'none',
                      }}
                    >
                      {[...Array(12)].map((_, i) => {
                        const hour = i === 0 ? 12 : i;
                        return <option key={i} value={i.toString().padStart(2, '0')}>{hour}:00 AM</option>;
                      })}
                      {[...Array(12)].map((_, i) => {
                        const hour = i === 0 ? 12 : i;
                        return <option key={i + 12} value={(i + 12).toString().padStart(2, '0')}>{hour}:00 PM</option>;
                      })}
                    </select>
                  </div>
                </div>
              </div>
            </div>
            
            {/* Entry Criteria */}
            <div style={{ 
              padding: 16, 
              background: theme.blue + '08', 
              borderRadius: 8,
              border: `1px solid ${theme.blue}30`,
            }}>
              <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700, color: theme.txt, marginBottom: 16 }}>
                Entry Requirements
              </h3>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Min Followers
                  </label>
                  <input
                    type="number"
                    placeholder="0"
                    value={formData.min_followers}
                    onChange={(e) => setFormData({ ...formData, min_followers: parseInt(e.target.value) || 0 })}
                    min="0"
                    style={{
                      width: '100%',
                      padding: 12,
                      border: `2px solid ${theme.border}`,
                      borderRadius: 8,
                      fontSize: 14,
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
                
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Min Level
                  </label>
                  <input
                    type="number"
                    placeholder="0"
                    value={formData.min_level}
                    onChange={(e) => setFormData({ ...formData, min_level: parseInt(e.target.value) || 0 })}
                    min="0"
                    style={{
                      width: '100%',
                      padding: 12,
                      border: `2px solid ${theme.border}`,
                      borderRadius: 8,
                      fontSize: 14,
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
              
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 }}>
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Min Votes Per Reel
                  </label>
                  <input
                    type="number"
                    placeholder="0"
                    value={formData.min_votes_per_reel}
                    onChange={(e) => setFormData({ ...formData, min_votes_per_reel: parseInt(e.target.value) || 0 })}
                    min="0"
                    style={{
                      width: '100%',
                      padding: 12,
                      border: `2px solid ${theme.border}`,
                      borderRadius: 8,
                      fontSize: 14,
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
                
                <div>
                  <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                    Number of Winners *
                  </label>
                  <input
                    type="number"
                    placeholder="3"
                    value={formData.winner_count}
                    onChange={(e) => setFormData({ ...formData, winner_count: parseInt(e.target.value) || 1 })}
                    min="1"
                    required
                    style={{
                      width: '100%',
                      padding: 12,
                      border: `2px solid ${theme.border}`,
                      borderRadius: 8,
                      fontSize: 14,
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
              
              <div>
                <label style={{ display: 'block', fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 8 }}>
                  Required Hashtags (comma separated)
                </label>
                <input
                  type="text"
                  placeholder="#contest, #giveaway, #challenge"
                  value={formData.required_hashtags}
                  onChange={(e) => setFormData({ ...formData, required_hashtags: e.target.value })}
                  style={{
                    width: '100%',
                    padding: 12,
                    border: `2px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    boxSizing: 'border-box',
                  }}
                />
              </div>
            </div>
            
            <div style={{ display: 'flex', gap: 12, marginTop: 32, paddingTop: 24, borderTop: `1px solid ${theme.border}` }}>
              <button
                type="button"
                onClick={onClose}
                style={{
                  flex: 1,
                  padding: 14,
                  background: '#fff',
                  border: `2px solid ${theme.border}`,
                  borderRadius: 8,
                  color: theme.txt,
                  fontSize: 15,
                  fontWeight: 600,
                  cursor: 'pointer',
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => e.target.style.background = theme.bg}
                onMouseLeave={(e) => e.target.style.background = '#fff'}
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                style={{
                  flex: 1,
                  padding: 14,
                  background: isSubmitting ? theme.sub : theme.pri,
                  border: 'none',
                  borderRadius: 8,
                  color: '#fff',
                  fontSize: 15,
                  fontWeight: 600,
                  cursor: isSubmitting ? 'not-allowed' : 'pointer',
                  transition: 'all 0.2s',
                  boxShadow: isSubmitting ? 'none' : `0 4px 12px ${theme.pri}40`,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: 8,
                }}
                onMouseEnter={(e) => !isSubmitting && (e.target.style.transform = 'translateY(-1px)')}
                onMouseLeave={(e) => e.target.style.transform = 'translateY(0)'}
              >
                {isSubmitting ? (
                  <>
                    <div style={{
                      width: 18,
                      height: 18,
                      border: '2px solid #fff',
                      borderTopColor: 'transparent',
                      borderRadius: '50%',
                      animation: 'spin 1s linear infinite',
                    }} />
                    Creating...
                  </>
                ) : 'Create Campaign'}
              </button>
            </div>
          </div>
        </form>
      </div>
    </div>
  );
}

function CampaignEntriesModal({ theme, campaign, onClose }) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadEntries();
  }, []);

  const loadEntries = async () => {
    try {
      const data = await api.request(`/admin/campaigns/${campaign.id}/entries/`);
      setEntries(data);
    } catch (error) {
      console.error('Failed to load entries:', error);
    } finally {
      setLoading(false);
    }
  };

  const isMobile = window.innerWidth < 768;

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
        alignItems: isMobile ? 'flex-end' : 'center',
        justifyContent: 'center',
        zIndex: 9999,
        padding: isMobile ? 0 : 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: theme.card,
          borderRadius: isMobile ? '20px 20px 0 0' : 12,
          padding: isMobile ? 20 : 32,
          width: '100%',
          maxWidth: 800,
          maxHeight: isMobile ? '90vh' : '80vh',
          overflowY: 'auto',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <h2 style={{ margin: 0, fontSize: 24, fontWeight: 700, color: theme.txt, marginBottom: 24 }}>
          {campaign.title} - Entries ({entries.length})
        </h2>
        
        {loading ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
            Loading entries...
          </div>
        ) : entries.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
            No entries yet
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {entries.map((entry, index) => (
              <div
                key={entry.id}
                style={{
                  padding: 16,
                  background: theme.bg,
                  borderRadius: 8,
                  display: 'flex',
                  gap: 16,
                  alignItems: 'center',
                }}
              >
                <div style={{
                  width: 40,
                  height: 40,
                  borderRadius: '50%',
                  background: entry.is_winner ? theme.pri : theme.sub + '30',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: 18,
                  fontWeight: 700,
                  color: entry.is_winner ? '#fff' : theme.txt,
                  flexShrink: 0,
                }}>
                  {entry.rank || index + 1}
                </div>
                
                {entry.reel.image && (
                  <div style={{
                    width: 60,
                    height: 60,
                    borderRadius: 8,
                    background: `url(${entry.reel.image}) center/cover`,
                    flexShrink: 0,
                  }} />
                )}
                
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt, marginBottom: 4 }}>
                    @{entry.user.username}
                  </div>
                  <div style={{ fontSize: 13, color: theme.sub, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {entry.reel.caption}
                  </div>
                </div>
                
                <div style={{ textAlign: 'right', flexShrink: 0 }}>
                  <div style={{ fontSize: 18, fontWeight: 700, color: theme.pri }}>
                    {entry.vote_count}
                  </div>
                  <div style={{ fontSize: 11, color: theme.sub }}>
                    votes
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function SuccessModal({ theme, campaign, onClose }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onClose();
    }, 3000);
    return () => clearTimeout(timer);
  }, [onClose]);

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        zIndex: 10000,
        padding: 20,
        animation: 'fadeIn 0.3s ease',
      }}
      onClick={onClose}
    >
      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes scaleIn {
          from { transform: scale(0.8); opacity: 0; }
          to { transform: scale(1); opacity: 1; }
        }
        @keyframes checkmark {
          0% { transform: scale(0) rotate(-45deg); }
          50% { transform: scale(1.2) rotate(-45deg); }
          100% { transform: scale(1) rotate(-45deg); }
        }
        @keyframes spin {
          to { transform: rotate(360deg); }
        }
      `}</style>
      <div
        style={{
          background: '#fff',
          borderRadius: 20,
          padding: '40px 48px',
          width: '100%',
          maxWidth: 420,
          textAlign: 'center',
          boxShadow: '0 25px 80px rgba(0,0,0,0.3)',
          animation: 'scaleIn 0.4s cubic-bezier(0.34, 1.56, 0.64, 1)',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Success Icon */}
        <div
          style={{
            width: 80,
            height: 80,
            borderRadius: '50%',
            background: `linear-gradient(135deg, ${theme.green}20, ${theme.green}40)`,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 24px',
            position: 'relative',
          }}
        >
          <div
            style={{
              width: 36,
              height: 18,
              borderLeft: `5px solid ${theme.green}`,
              borderBottom: `5px solid ${theme.green}`,
              transform: 'rotate(-45deg)',
              marginTop: -8,
              animation: 'checkmark 0.5s cubic-bezier(0.34, 1.56, 0.64, 1) 0.2s both',
            }}
          />
        </div>

        {/* Title */}
        <h2
          style={{
            margin: 0,
            fontSize: 26,
            fontWeight: 700,
            color: theme.txt,
            marginBottom: 12,
          }}
        >
          Campaign Created! 🎉
        </h2>

        {/* Message */}
        <p
          style={{
            margin: 0,
            fontSize: 15,
            color: theme.sub,
            lineHeight: 1.6,
            marginBottom: 24,
          }}
        >
          "{campaign?.title || 'Your campaign'}" has been successfully created and is now live!
        </p>

        {/* Campaign ID Badge */}
        {campaign?.id && (
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 8,
              padding: '8px 16px',
              background: theme.pri + '10',
              borderRadius: 20,
              fontSize: 13,
              fontWeight: 600,
              color: theme.pri,
              marginBottom: 24,
            }}
          >
            <Trophy size={14} />
            Campaign ID: #{campaign.id}
          </div>
        )}

        {/* Progress Bar */}
        <div
          style={{
            width: '100%',
            height: 4,
            background: theme.border,
            borderRadius: 2,
            overflow: 'hidden',
            marginBottom: 16,
          }}
        >
          <div
            style={{
              width: '100%',
              height: '100%',
              background: `linear-gradient(90deg, ${theme.green}, ${theme.pri})`,
              borderRadius: 2,
              animation: 'progress 3s linear',
            }}
          />
        </div>
        <style>{`
          @keyframes progress {
            from { width: 100%; }
            to { width: 0%; }
          }
        `}</style>

        {/* Auto close hint */}
        <p
          style={{
            margin: 0,
            fontSize: 12,
            color: theme.sub,
          }}
        >
          Closing automatically in 3 seconds...
        </p>

        {/* Close Button */}
        <button
          onClick={onClose}
          style={{
            marginTop: 20,
            padding: '12px 32px',
            background: theme.pri,
            border: 'none',
            borderRadius: 10,
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            cursor: 'pointer',
            transition: 'all 0.2s',
            boxShadow: `0 4px 12px ${theme.pri}40`,
          }}
          onMouseEnter={(e) => {
            e.target.style.transform = 'translateY(-2px)';
            e.target.style.boxShadow = `0 6px 20px ${theme.pri}60`;
          }}
          onMouseLeave={(e) => {
            e.target.style.transform = 'translateY(0)';
            e.target.style.boxShadow = `0 4px 12px ${theme.pri}40`;
          }}
        >
          Got it!
        </button>
      </div>
    </div>
  );
}

function CampaignAnalyticsModal({ theme, campaign, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    api.request(`/admin/campaigns/${campaign.id}/analytics/`)
      .then(res => { setData(res); setLoading(false); })
      .catch(err => { setError(err.message || 'Failed to load analytics'); setLoading(false); });
  }, [campaign.id]);

  const isMobile = window.innerWidth < 768;

  const StatBox = ({ icon, label, value, color }) => (
    <div style={{
      background: theme.bg,
      border: `1.5px solid ${theme.border}`,
      borderRadius: 10,
      padding: '14px 16px',
      display: 'flex',
      alignItems: 'center',
      gap: 12,
    }}>
      <div style={{
        width: 36, height: 36, borderRadius: '50%',
        background: (color || theme.pri) + '20',
        display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
      }}>
        {icon}
      </div>
      <div>
        <div style={{ fontSize: 20, fontWeight: 800, color: theme.txt }}>{value}</div>
        <div style={{ fontSize: 11, color: theme.sub, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5 }}>{label}</div>
      </div>
    </div>
  );

  return (
    <div
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(0,0,0,0.6)',
        display: 'flex', alignItems: isMobile ? 'flex-end' : 'center', justifyContent: 'center',
        zIndex: 9999, padding: isMobile ? 0 : 20,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: theme.card,
          borderRadius: isMobile ? '20px 20px 0 0' : 16,
          padding: isMobile ? 20 : 32,
          width: '100%', maxWidth: 860,
          maxHeight: isMobile ? '92vh' : '85vh',
          overflowY: 'auto',
        }}
        onClick={e => e.stopPropagation()}
      >
        {/* Header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 24 }}>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <BarChart3 size={22} color={theme.purple} />
              <h2 style={{ margin: 0, fontSize: 22, fontWeight: 800, color: theme.txt }}>Campaign Analytics</h2>
            </div>
            <div style={{ fontSize: 14, color: theme.sub, marginTop: 4 }}>{campaign.title}</div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 4 }}>
            <X size={20} color={theme.sub} />
          </button>
        </div>

        {loading ? (
          <div style={{ padding: 60, textAlign: 'center', color: theme.sub }}>Loading analytics…</div>
        ) : error ? (
          <div style={{ padding: 40, textAlign: 'center', color: theme.red }}>{error}</div>
        ) : (
          <>
            {/* ── Participation Stats ── */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: theme.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
                Participation
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
                <StatBox icon={<Users size={18} color={theme.blue} />}        label="Participants"  value={data.participation.total_participants} color={theme.blue} />
                <StatBox icon={<TrendingUp size={18} color={theme.pri} />}    label="Total Posts"   value={data.participation.total_posts}        color={theme.pri} />
                <StatBox icon={<CheckCircle size={18} color={theme.green} />} label="Approved"      value={data.participation.approved_posts}     color={theme.green} />
                <StatBox icon={<Clock size={18} color={theme.orange} />}      label="Pending"       value={data.participation.pending_posts}      color={theme.orange} />
                <StatBox icon={<XCircle size={18} color={theme.red} />}       label="Rejected"      value={data.participation.rejected_posts}     color={theme.red} />
              </div>
            </div>

            {/* ── Score Statistics ── */}
            <div style={{ marginBottom: 24 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: theme.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
                Average Scores (approved posts)
              </div>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px, 1fr))', gap: 10 }}>
                {[
                  { label: 'Total Score',  value: data.score_statistics.average_total_score.toFixed(1),   color: theme.pri },
                  { label: 'Creativity',   value: data.score_statistics.average_creativity.toFixed(1),     color: theme.purple },
                  { label: 'Engagement',   value: data.score_statistics.average_engagement.toFixed(1),     color: theme.blue },
                  { label: 'Quality',      value: data.score_statistics.average_quality.toFixed(1),        color: theme.green },
                ].map(s => (
                  <div key={s.label} style={{
                    background: s.color + '10',
                    border: `1.5px solid ${s.color}30`,
                    borderRadius: 10,
                    padding: '14px 16px',
                    textAlign: 'center',
                  }}>
                    <div style={{ fontSize: 26, fontWeight: 900, color: s.color }}>{s.value}</div>
                    <div style={{ fontSize: 11, color: theme.sub, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginTop: 4 }}>{s.label}</div>
                  </div>
                ))}
              </div>
            </div>

            {/* ── Top Performers ── */}
            {data.top_performers?.length > 0 && (
              <div style={{ marginBottom: 24 }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: theme.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
                  Top 10 Performers
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {data.top_performers.map((p, idx) => (
                    <div key={p.username} style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 14px',
                      background: idx < 3 ? theme.pri + '10' : theme.bg,
                      border: `1px solid ${idx < 3 ? theme.pri + '30' : theme.border}`,
                      borderRadius: 8,
                    }}>
                      <div style={{
                        width: 28, height: 28, borderRadius: '50%', flexShrink: 0,
                        background: idx === 0 ? '#FFD700' : idx === 1 ? '#C0C0C0' : idx === 2 ? '#CD7F32' : theme.border,
                        display: 'flex', alignItems: 'center', justifyContent: 'center',
                        fontSize: 12, fontWeight: 900,
                        color: idx < 3 ? '#000' : theme.sub,
                      }}>
                        {idx < 3 ? <Crown size={13} /> : idx + 1}
                      </div>
                      <div style={{ flex: 1, fontWeight: 600, color: theme.txt, fontSize: 14 }}>@{p.username}</div>
                      <div style={{ fontSize: 12, color: theme.sub }}>{p.posts_count} posts</div>
                      {p.rank && <div style={{ fontSize: 12, color: theme.sub }}>Rank #{p.rank}</div>}
                      <div style={{
                        background: theme.pri + '20', color: theme.pri,
                        padding: '4px 10px', borderRadius: 20,
                        fontSize: 13, fontWeight: 700,
                      }}>
                        {p.total_score.toFixed(0)} pts
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* ── Themes Breakdown ── */}
            {data.themes?.length > 0 && (
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: theme.sub, textTransform: 'uppercase', letterSpacing: 0.8, marginBottom: 12 }}>
                  Theme Participation
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {data.themes.map(t => (
                    <div key={t.week_number} style={{
                      display: 'flex', alignItems: 'center', gap: 12,
                      padding: '10px 14px',
                      background: t.is_active ? theme.green + '10' : theme.bg,
                      border: `1px solid ${t.is_active ? theme.green + '40' : theme.border}`,
                      borderRadius: 8,
                    }}>
                      <div style={{
                        fontSize: 11, fontWeight: 700, color: t.is_active ? theme.green : theme.sub,
                        background: (t.is_active ? theme.green : theme.sub) + '20',
                        padding: '3px 8px', borderRadius: 10,
                        flexShrink: 0,
                      }}>
                        {t.is_active ? '● ACTIVE' : `Week ${t.week_number}`}
                      </div>
                      <div style={{ flex: 1, fontWeight: 600, color: theme.txt, fontSize: 14 }}>{t.title}</div>
                      <div style={{
                        background: theme.blue + '20', color: theme.blue,
                        padding: '4px 10px', borderRadius: 20,
                        fontSize: 13, fontWeight: 700,
                      }}>
                        {t.posts_count} posts
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}




