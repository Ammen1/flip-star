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
    <div style={{ padding: '24px 32px', background: theme.bg, minHeight: '100vh' }}>
      <div style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        marginBottom: '24px',
      }}>
        <div>
          <h1 style={{
            fontSize: '28px',
            fontWeight: '700',
            color: theme.txt,
            marginBottom: '8px',
            display: 'flex',
            alignItems: 'center',
            gap: '12px',
          }}>
            <GiftIcon size={28} />
            Gift Management
          </h1>
          <p style={{ color: theme.sub, fontSize: '13px' }}>
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
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '16px',
      }}>
        {gifts.map((gift) => (
          <div key={gift.id} style={{
            background: theme.card,
            borderRadius: '12px',
            padding: '16px',
            border: `1px solid ${theme.border}`,
            position: 'relative',
            boxShadow: '0 1px 3px rgba(0, 0, 0, 0.1)',
            transition: 'all 0.2s ease',
            cursor: 'pointer',
          }} onMouseEnter={(e) => {
            e.currentTarget.style.transform = 'translateY(-2px)';
            e.currentTarget.style.boxShadow = '0 4px 12px rgba(0, 0, 0, 0.15)';
          }} onMouseLeave={(e) => {
            e.currentTarget.style.transform = 'translateY(0)';
            e.currentTarget.style.boxShadow = '0 1px 3px rgba(0, 0, 0, 0.1)';
          }}>
            <div style={{
              position: 'absolute',
              top: '12px',
              right: '12px',
              display: 'flex',
              gap: '6px',
              zIndex: 2,
            }}>
              <button
                onClick={(e) => { e.stopPropagation(); handleEdit(gift); }}
                style={{
                  background: theme.bg,
                  border: `1px solid ${theme.border}`,
                  borderRadius: '6px',
                  padding: '6px',
                  cursor: 'pointer',
                  color: theme.txt,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = theme.border;
                  e.currentTarget.style.borderColor = theme.pri;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = theme.bg;
                  e.currentTarget.style.borderColor = theme.border;
                }}
              >
                <Edit2 size={14} />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); handleDelete(gift.id); }}
                style={{
                  background: theme.bg,
                  border: `1px solid ${theme.border}`,
                  borderRadius: '6px',
                  padding: '6px',
                  cursor: 'pointer',
                  color: theme.red,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = theme.red + '10';
                  e.currentTarget.style.borderColor = theme.red;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = theme.bg;
                  e.currentTarget.style.borderColor = theme.border;
                }}
              >
                <Trash2 size={14} />
              </button>
            </div>

            <div style={{
              width: '70px',
              height: '70px',
              borderRadius: '12px',
              overflow: 'hidden',
              marginBottom: '12px',
              background: theme.bg,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: `1px solid ${theme.border}`,
            }}>
              {gift.image_url ? (
                <img
                  src={gift.image_url}
                  alt={gift.name}
                  style={{ width: '100%', height: '100%', objectFit: 'cover' }}
                />
              ) : (
                <GiftIcon size={28} color={theme.sub} />
              )}
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              marginBottom: '8px',
            }}>
              <span style={{ fontSize: '20px' }}>{getCategoryIcon(gift.category)}</span>
              <h3 style={{
                fontSize: '15px',
                fontWeight: '700',
                color: theme.txt,
                margin: 0,
                lineHeight: 1.2,
              }}>
                {gift.name}
              </h3>
            </div>

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              marginBottom: '8px',
              padding: '8px',
              background: theme.bg,
              borderRadius: '6px',
              border: `1px solid ${theme.border}`,
            }}>
              <Coins size={14} color={theme.pri} />
              <span style={{
                fontSize: '15px',
                fontWeight: '700',
                color: theme.pri,
              }}>
                {gift.coin_value}
              </span>
              <span style={{ fontSize: '11px', color: theme.sub, fontWeight: '500' }}>coins</span>
            </div>

            <div style={{
              display: 'flex',
              gap: '6px',
              flexWrap: 'wrap',
              marginBottom: '8px',
            }}>
              <span style={{
                fontSize: '10px',
                padding: '4px 8px',
                borderRadius: '12px',
                background: getRarityColor(gift.rarity) + '15',
                color: getRarityColor(gift.rarity),
                fontWeight: '600',
                textTransform: 'capitalize',
                border: `1px solid ${getRarityColor(gift.rarity)}30`,
              }}>
                {gift.rarity}
              </span>
              <span style={{
                fontSize: '10px',
                padding: '4px 8px',
                borderRadius: '12px',
                background: theme.bg,
                color: theme.sub,
                fontWeight: '600',
                textTransform: 'capitalize',
                border: `1px solid ${theme.border}`,
              }}>
                {gift.category}
              </span>
            </div>

            {gift.description && (
              <div style={{
                fontSize: '11px',
                color: theme.sub,
                marginBottom: '8px',
                lineHeight: 1.4,
                display: '-webkit-box',
                WebkitLineClamp: 2,
                WebkitBoxOrient: 'vertical',
                overflow: 'hidden',
              }}>
                {gift.description}
              </div>
            )}

            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              fontSize: '11px',
              color: theme.sub,
              fontWeight: '500',
            }}>
              <Sparkles size={12} color={theme.purple} />
              <span>+{gift.xp_reward} XP</span>
              {gift.animation_type && (
                <>
                  <Zap size={12} color={theme.yellow} style={{ marginLeft: '8px' }} />
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
                background: 'rgba(0,0,0,0.6)',
                borderRadius: '12px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                backdropFilter: 'blur(4px)',
              }}>
                <span style={{
                  color: '#fff',
                  fontSize: '14px',
                  fontWeight: '700',
                  padding: '8px 16px',
                  background: 'rgba(0,0,0,0.8)',
                  borderRadius: '6px',
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
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(0, 0, 0, 0.7)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          padding: 20,
        }} onClick={() => closeModal()}>
          <div style={{
            background: theme.card,
            borderRadius: 16,
            padding: 32,
            width: '100%',
            maxWidth: 600,
            maxHeight: '90vh',
            overflowY: 'auto',
            border: `1px solid ${theme.border}`,
            boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          }} onClick={(e) => e.stopPropagation()}>
            <div style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 24,
              paddingBottom: 16,
              borderBottom: `1px solid ${theme.border}`,
            }}>
              <h2 style={{
                fontSize: 24,
                fontWeight: 700,
                color: theme.txt,
                margin: 0,
              }}>
                {editingGift ? 'Edit Gift' : 'Add New Gift'}
              </h2>
              <button
                onClick={closeModal}
                style={{
                  background: 'transparent',
                  border: 'none',
                  cursor: 'pointer',
                  color: theme.sub,
                  padding: 8,
                  borderRadius: 8,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => {
                  e.currentTarget.style.background = theme.bg;
                  e.currentTarget.style.color = theme.txt;
                }}
                onMouseLeave={(e) => {
                  e.currentTarget.style.background = 'transparent';
                  e.currentTarget.style.color = theme.sub;
                }}
              >
                <X size={24} />
              </button>
            </div>

            <form onSubmit={handleSubmit}>
              <div style={{ marginBottom: 20 }}>
                <label style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
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
                    borderRadius: 8,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 14,
                    outline: 'none',
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  placeholder="e.g., Rose, Diamond Heart"
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
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
                    borderRadius: 8,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 14,
                    outline: 'none',
                    resize: 'vertical',
                    transition: 'border-color 0.2s',
                    fontFamily: 'inherit',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  placeholder="Gift description"
                />
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
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
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  />
                </div>

                <div>
                  <label style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
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
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  />
                </div>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
                  }}>
                    Rarity
                  </label>
                  <select
                    value={formData.rarity}
                    onChange={(e) => setFormData({ ...formData, rarity: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
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
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
                  }}>
                    Category
                  </label>
                  <select
                    value={formData.category}
                    onChange={(e) => setFormData({ ...formData, category: e.target.value })}
                    style={{
                      width: '100%',
                      padding: '12px',
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      cursor: 'pointer',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
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

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 20 }}>
                <div>
                  <label style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
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
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  />
                </div>

                <div>
                  <label style={{
                    display: 'block',
                    fontSize: 13,
                    fontWeight: 600,
                    color: theme.txt,
                    marginBottom: 8,
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
                      borderRadius: 8,
                      border: `1px solid ${theme.border}`,
                      background: theme.bg,
                      color: theme.txt,
                      fontSize: 14,
                      outline: 'none',
                      transition: 'border-color 0.2s',
                    }}
                    onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                    onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  />
                </div>
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
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
                    borderRadius: 8,
                    border: `1px solid ${theme.border}`,
                    background: theme.bg,
                    color: theme.txt,
                    fontSize: 14,
                    outline: 'none',
                    transition: 'border-color 0.2s',
                  }}
                  onFocus={(e) => { e.target.style.borderColor = theme.pri; }}
                  onBlur={(e) => { e.target.style.borderColor = theme.border; }}
                  placeholder="e.g., particle, bounce, pulse"
                />
              </div>

              <div style={{ marginBottom: 20 }}>
                <label style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  Gift Image *
                </label>
                <div style={{
                  border: `2px dashed ${theme.border}`,
                  borderRadius: 12,
                  padding: 32,
                  textAlign: 'center',
                  cursor: 'pointer',
                  position: 'relative',
                  transition: 'all 0.2s',
                  background: theme.bg,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = theme.pri; e.currentTarget.style.background = theme.pri + '05'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border; e.currentTarget.style.background = theme.bg; }}>
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
                      style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: 8 }}
                    />
                  ) : (
                    <div>
                      <Upload size={40} color={theme.sub} style={{ marginBottom: 12 }} />
                      <div style={{ color: theme.txt, fontSize: 14, fontWeight: 500 }}>
                        Click to upload gift image
                      </div>
                      <div style={{ color: theme.sub, fontSize: 12, marginTop: 4 }}>
                        PNG, JPG up to 5MB
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 24 }}>
                <label style={{
                  display: 'block',
                  fontSize: 13,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  Animated Image (Optional)
                </label>
                <div style={{
                  border: `2px dashed ${theme.border}`,
                  borderRadius: 12,
                  padding: 32,
                  textAlign: 'center',
                  cursor: 'pointer',
                  position: 'relative',
                  transition: 'all 0.2s',
                  background: theme.bg,
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = theme.pri; e.currentTarget.style.background = theme.pri + '05'; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border; e.currentTarget.style.background = theme.bg; }}>
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
                      style={{ maxWidth: '100%', maxHeight: '200px', borderRadius: 8 }}
                    />
                  ) : (
                    <div>
                      <Upload size={40} color={theme.sub} style={{ marginBottom: 12 }} />
                      <div style={{ color: theme.txt, fontSize: 14, fontWeight: 500 }}>
                        Click to upload animated version
                      </div>
                      <div style={{ color: theme.sub, fontSize: 12, marginTop: 4 }}>
                        GIF, PNG up to 5MB
                      </div>
                    </div>
                  )}
                </div>
              </div>

              <div style={{ marginBottom: 24 }}>
                <label style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                  cursor: 'pointer',
                  padding: '12px',
                  background: theme.bg,
                  borderRadius: 8,
                  border: `1px solid ${theme.border}`,
                  transition: 'all 0.2s',
                }}
                onMouseEnter={(e) => { e.currentTarget.style.borderColor = theme.pri; }}
                onMouseLeave={(e) => { e.currentTarget.style.borderColor = theme.border; }}>
                  <input
                    type="checkbox"
                    checked={formData.is_active}
                    onChange={(e) => setFormData({ ...formData, is_active: e.target.checked })}
                    style={{
                      width: 20,
                      height: 20,
                      cursor: 'pointer',
                    }}
                  />
                  <span style={{ fontSize: 14, color: theme.txt, fontWeight: 500 }}>
                    Active (available for users)
                  </span>
                </label>
              </div>

              <div style={{
                display: 'flex',
                gap: 12,
                justifyContent: 'flex-end',
                paddingTop: 16,
                borderTop: `1px solid ${theme.border}`,
              }}>
                <button
                  type="button"
                  onClick={closeModal}
                  style={{
                    background: 'transparent',
                    color: theme.txt,
                    border: `1px solid ${theme.border}`,
                    padding: '12px 24px',
                    borderRadius: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.background = theme.bg; }}
                  onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; }}
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
                    borderRadius: 8,
                    fontSize: 14,
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                    boxShadow: `0 4px 6px -1px ${theme.pri}40`,
                  }}
                  onMouseEnter={(e) => { e.currentTarget.style.transform = 'translateY(-1px)'; e.currentTarget.style.boxShadow = `0 6px 8px -1px ${theme.pri}50`; }}
                  onMouseLeave={(e) => { e.currentTarget.style.transform = 'translateY(0)'; e.currentTarget.style.boxShadow = `0 4px 6px -1px ${theme.pri}40`; }}
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




