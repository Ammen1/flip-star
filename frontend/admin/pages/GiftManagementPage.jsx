import { useState, useEffect } from 'react';
import { Upload, X, Plus, Edit2, Trash2, Gift as GiftIcon, Coins, Sparkles, Zap } from 'lucide-react';
import api from '../../api';

export function GiftManagementPage({ theme }) {
  const [gifts, setGifts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showModal, setShowModal] = useState(false);
  const [editingGift, setEditingGift] = useState(null);
  const [previewImage, setPreviewImage] = useState(null);
  const [previewAnimatedImage, setPreviewAnimatedImage] = useState(null);

  const [formData, setFormData] = useState({
    name: '',
    description: '',
    coin_value: 1,
    rarity: 'common',
    category: 'special',
    is_active: true,
    sort_order: 0,
    xp_reward: 0,
    animation_type: '',
    animation_duration: 1.0,
  });

  const [imageFile, setImageFile] = useState(null);
  const [animatedImageFile, setAnimatedImageFile] = useState(null);

  useEffect(() => {
    loadGifts();
  }, []);

  const loadGifts = async () => {
    try {
      const response = await api.request('/admin/gifts/', {
        method: 'GET',
      });
      setGifts(response.results || response);
    } catch (error) {
      console.error('Error loading gifts:', error);
      // Try public endpoint as fallback
      try {
        const publicResponse = await api.request('/gifts/', {
          method: 'GET',
        });
        setGifts(publicResponse.results || publicResponse);
      } catch (publicError) {
        console.error('Error loading gifts from public endpoint:', publicError);
      }
    } finally {
      setLoading(false);
    }
  };

  const handleImageChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImageFile(file);
      setPreviewImage(URL.createObjectURL(file));
    }
  };

  const handleAnimatedImageChange = (e) => {
    const file = e.target.files[0];
    if (file) {
      setAnimatedImageFile(file);
      setPreviewAnimatedImage(URL.createObjectURL(file));
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    
    const data = new FormData();
    Object.keys(formData).forEach(key => {
      data.append(key, formData[key]);
    });
    
    if (imageFile) {
      data.append('image', imageFile);
    }
    
    if (animatedImageFile) {
      data.append('animated_image', animatedImageFile);
    }

    try {
      if (editingGift) {
        await api.request(`/admin/gifts/${editingGift.id}/`, {
          method: 'PATCH',
          body: data,
        });
      } else {
        await api.request('/admin/gifts/', {
          method: 'POST',
          body: data,
        });
      }
      
      closeModal();
      loadGifts();
    } catch (error) {
      console.error('Error saving gift:', error);
      alert('Error saving gift. Please try again.');
    }
  };

  const handleEdit = (gift) => {
    setEditingGift(gift);
    setFormData({
      name: gift.name,
      description: gift.description || '',
      coin_value: gift.coin_value,
      rarity: gift.rarity,
      category: gift.category,
      is_active: gift.is_active,
      sort_order: gift.sort_order,
      xp_reward: gift.xp_reward,
      animation_type: gift.animation_type || '',
      animation_duration: gift.animation_duration,
    });
    setPreviewImage(gift.image_url || null);
    setPreviewAnimatedImage(gift.animated_image_url || null);
    setShowModal(true);
  };

  const handleDelete = async (giftId) => {
    if (!confirm('Are you sure you want to delete this gift?')) return;
    
    try {
      await api.request(`/admin/gifts/${giftId}/`, {
        method: 'DELETE',
      });
      loadGifts();
    } catch (error) {
      console.error('Error deleting gift:', error);
      alert('Error deleting gift. Please try again.');
    }
  };

  const closeModal = () => {
    setShowModal(false);
    setEditingGift(null);
    setFormData({
      name: '',
      description: '',
      coin_value: 1,
      rarity: 'common',
      category: 'special',
      is_active: true,
      sort_order: 0,
      xp_reward: 0,
      animation_type: '',
      animation_duration: 1.0,
    });
    setImageFile(null);
    setAnimatedImageFile(null);
    setPreviewImage(null);
    setPreviewAnimatedImage(null);
  };

  const getRarityColor = (rarity) => {
    const colors = {
      common: theme.sub,
      rare: theme.blue,
      epic: theme.purple,
      legendary: theme.orange,
    };
    return colors[rarity] || theme.sub;
  };

  const getCategoryIcon = (category) => {
    const icons = {
      flowers: '🌹',
      hearts: '❤️',
      gems: '💎',
      special: '⭐',
      animals: '🐻',
      vehicles: '🚗',
    };
    return icons[category] || '🎁';
  };

  if (loading) {
    return (
      <div style={{ color: theme.sub, padding: '32px' }}>
        Loading gifts...
      </div>
    );
  }

  return (
    <div>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '32px',
      }}>
        <div>
          <h1 style={{
            fontSize: '32px',
            fontWeight: '700',
            color: theme.text,
            marginBottom: '8px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}>
            <GiftIcon size={32} />
            Gift Management
          </h1>
          <p style={{ color: theme.sub, fontSize: '14px' }}>
            Configure virtual gifts with coin values and gamification settings
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          style={{
            background: theme.pri,
            color: '#fff',
            border: 'none',
            padding: '12px 24px',
            borderRadius: '8px',
            fontSize: '14px',
            fontWeight: '600',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
          }}
        >
          <Plus size={18} />
          Add New Gift
        </button>
      </div>

      {/* Gift Grid */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
        gap: '20px',
      }}>
        {gifts.map((gift) => (
          <div key={gift.id} style={{
            background: '#ffffff',
            borderRadius: '12px',
            padding: '20px',
            border: '1px solid #E7E5E4',
            position: 'relative',
          }}>
            <div style={{
              position: 'absolute',
              top: '12px',
              right: '12px',
              display: 'flex',
              gap: '8px',
            }}>
              <button
                onClick={() => handleEdit(gift)}
                style={{
                  background: theme.bg,
                  border: `1px solid ${theme.border}`,
                  borderRadius: '6px',
                  padding: '6px',
                  cursor: 'pointer',
                  color: theme.text,
                }}
              >
                <Edit2 size={16} />
              </button>
              <button
                onClick={() => handleDelete(gift.id)}
                style={{
                  background: theme.bg,
                  border: `1px solid ${theme.border}`,
                  borderRadius: '6px',
                  padding: '6px',
                  cursor: 'pointer',
                  color: theme.red,
                }}
              >
                <Trash2 size={16} />
              </button>
            </div>

            <div style={{
              width: '80px',
              height: '80px',
              borderRadius: '12px',
              overflow: 'hidden',
              marginBottom: '16px',
              background: theme.bg,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {gift.image_url ? (
                <img
                  src={gift.image_url}
                  alt={gift.name}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <GiftIcon size={32} color={theme.sub} />
              )}
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '8px',
            }}>
              <span style={{ fontSize: '24px' }}>{getCategoryIcon(gift.category)}</span>
              <h3 style={{
                fontSize: '18px',
                fontWeight: '600',
                color: theme.text,
                margin: 0,
              }}>
                {gift.name}
              </h3>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginBottom: '8px',
            }}>
              <Coins size={16} color={theme.pri} />
              <span style={{
                fontSize: '16px',
                fontWeight: '600',
                color: theme.pri,
              }}>
                {gift.coin_value}
              </span>
              <span style={{ fontSize: '12px', color: theme.sub }}>coins</span>
            </div>

            <div style={{
              display: 'flex',
              gap: '8px',
              flexWrap: 'wrap',
              marginBottom: '12px',
            }}>
              <span style={{
                fontSize: '12px',
                padding: '4px 8px',
                borderRadius: '4px',
                background: theme.bg,
                color: getRarityColor(gift.rarity),
                fontWeight: '500',
              }}>
                {gift.rarity}
              </span>
              <span style={{
                fontSize: '12px',
                padding: '4px 8px',
                borderRadius: '4px',
                background: theme.bg,
                color: theme.sub,
              }}>
                {gift.category}
              </span>
            </div>

            <div style={{
              fontSize: '12px',
              color: theme.sub,
              marginBottom: '8px',
            }}>
              {gift.description || 'No description'}
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '12px',
              color: theme.sub,
            }}>
              <Sparkles size={12} />
              <span>+{gift.xp_reward} XP</span>
              {gift.animation_type && (
                <>
                  <Zap size={12} style={{ marginLeft: '8px' }} />
                  <span>{gift.animation_type}</span>
                </>
              )}
            </div>

            {!gift.is_active && (
              <div style={{
                position: 'absolute',
                top: '0',
                left: '0',
                right: '0',
                bottom: '0',
                background: 'rgba(0,0,0,0.5)',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}>
                <span style={{
                  color: '#fff',
                  fontSize: '14px',
                  fontWeight: '600',
                }}>
                  Inactive
                </span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Add/Edit Modal */}
      {showModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 10000,
          padding: 20,
        }} onClick={() => closeModal()}>
          <div style={{
            background: '#ffffff',
            borderRadius: 16,
            padding: 24,
            width: '100%',
            maxWidth: 500,
            maxHeight: '90vh',
            overflowY: 'auto',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: '24px',
            }}>
              <h2 style={{
                fontSize: '24px',
                fontWeight: '700',
                color: theme.text,
                margin: 0,
              }}>
                {editingGift ? 'Edit Gift' : 'Add New Gift'}
              </h2>
              <button
                onClick={closeModal}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  color: theme.sub,
                }}
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: theme.text,
                  marginBottom: '8px',
                }}>
                  Gift Name *
                </label>
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                  required
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.text,
                    fontSize: '14px',
                  }}
                  placeholder="e.g., Rose, Diamond Heart"
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: theme.text,
                  marginBottom: '8px',
                }}>
                  Description
                </label>
                <textarea
                  value={formData.description}
                  onChange={(e) => setFormData({ ...formData, description: e.target.value })}
                  rows={3}
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.text,
                    fontSize: '14px',
                    resize: 'vertical',
                  }}
                  placeholder="Gift description"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    Coin Value *
                  </label>
                  <input
                    type="number"
                    value={formData.coin_value}
                    onChange={(e) => setFormData({ ...formData, coin_value: parseInt(e.target.value) })}
                    required
                    min="1"
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  />
                </div>

                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    XP Reward
                  </label>
                  <input
                    type="number"
                    value={formData.xp_reward}
                    onChange={(e) => setFormData({ ...formData, xp_reward: parseInt(e.target.value) })}
                    min="0"
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    Rarity
                  </label>
                  <select
                    value={formData.rarity}
                    onChange={(e) => setFormData({ ...formData, rarity: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  >
                    <option value="common">Common</option>
                    <option value="rare">Rare</option>
                    <option value="epic">Epic</option>
                    <option value="legendary">Legendary</option>
                  </select>
                </div>

                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    Category
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  >
                    <option value="special">Special</option>
                    <option value="flowers">Flowers</option>
                    <option value="hearts">Hearts</option>
                    <option value="gems">Gems</option>
                    <option value="animals">Animals</option>
                    <option value="vehicles">Vehicles</option>
                  </select>
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '20px' }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    Sort Order
                  </label>
                  <input
                    type="number"
                    value={formData.sort_order}
                    onChange={(e) => setFormData({ ...formData, sort_order: parseInt(e.target.value) })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  />
                </div>

                <div>
                  <label style={{
                    display: 'block',
                    fontSize: '14px',
                    fontWeight: '500',
                    color: theme.text,
                    marginBottom: '8px',
                  }}>
                    Animation Duration (s)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={formData.animation_duration}
                    onChange={(e) => setFormData({ ...formData, animation_duration: parseFloat(e.target.value) })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: '8px',
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.text,
                      fontSize: '14px',
                    }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: theme.text,
                  marginBottom: '8px',
                }}>
                  Animation Type
                </label>
                <input
                  type="text"
                  value={formData.animation_type}
                  onChange={(e) => setFormData({ ...formData, animation_type: e.target.value })}
                  style={{
                    width: '100%',
                    padding: '12px',
                    borderRadius: '8px',
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.text,
                    fontSize: '14px',
                  }}
                  placeholder="e.g., particle, bounce, pulse"
                />
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: theme.text,
                  marginBottom: '8px',
                }}>
                  Gift Image *
                </label>
                <div style={{
                  border: `2px dashed ${theme.border}`,
                  borderRadius: '8px',
                  padding: '24px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  position: 'relative',
                }}>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleImageChange}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      opacity: 0,
                      cursor: 'pointer',
                    }}
                  />
                  {previewImage ? (
                    <img
                      src={previewImage}
                      alt="Preview"
                      style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '8px' }}
                    />
                  ) : (
                    <div>
                      <Upload size={32} color={theme.sub} style={{ marginBottom: '8px' }} />
                      <div style={{ color: theme.sub, fontSize: '14px' }}>
                        Click to upload gift image
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: '20px' }}>
                <label style={{
                  display: 'block',
                  fontSize: '14px',
                  fontWeight: '500',
                  color: theme.text,
                  marginBottom: '8px',
                }}>
                  Animated Image (Optional)
                </label>
                <div style={{
                  border: `2px dashed ${theme.border}`,
                  borderRadius: '8px',
                  padding: '24px',
                  textAlign: 'center',
                  cursor: 'pointer',
                  position: 'relative',
                }}>
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleAnimatedImageChange}
                    style={{
                      position: 'absolute',
                      top: 0,
                      left: 0,
                      right: 0,
                      bottom: 0,
                      opacity: 0,
                      cursor: 'pointer',
                    }}
                  />
                  {previewAnimatedImage ? (
                    <img
                      src={previewAnimatedImage}
                      alt="Animated Preview"
                      style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: '8px' }}
                    />
                  ) : (
                    <div>
                      <Upload size={32} color={theme.sub} style={{ marginBottom: '8px' }} />
                      <div style={{ color: theme.sub, fontSize: '14px' }}>
                        Click to upload animated version
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: '24px' }}>
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  cursor: 'pointer',
                }}>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    style={{
                      width: '18px',
                      height: '18px',
                      cursor: 'pointer',
                    }}
                  />
                  <span style={{ fontSize: '14px', color: theme.text }}>
                    Active (available for users)
                  </span>
                </label>
              </div>

              <div style={{
                display: 'flex',
                gap: '12px',
                justifyContent: 'flex-end',
              }}>
                <button
                  type="button"
                  onClick={closeModal}
                  style={{
                    background: theme.bg,
                    color: theme.text,
                    border: `1px solid ${theme.border}`,
                    padding: '12px 24px',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  style={{
                    background: theme.pri,
                    color: '#fff',
                    border: 'none',
                    padding: '12px 24px',
                    borderRadius: '8px',
                    fontSize: '14px',
                    fontWeight: '600',
                    cursor: 'pointer',
                  }}
                >
                  {editingGift ? 'Update Gift' : 'Create Gift'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}




