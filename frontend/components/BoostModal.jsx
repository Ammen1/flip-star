import { useState, useEffect } from "react";
import { X, Zap, Clock, Users, Target, ChevronRight, Check } from "lucide-react";
import api from "../api";
import { useLegacyT } from "../contexts/ThemeContext";

export function BoostModal({ reelId, onClose, onSuccess }) {
  const T = useLegacyT();
  const [config, setConfig] = useState(null);
  const [selectedDuration, setSelectedDuration] = useState(24);
  const [selectedGender, setSelectedGender] = useState('all');
  const [selectedAgeMin, setSelectedAgeMin] = useState('');
  const [selectedAgeMax, setSelectedAgeMax] = useState('');
  const [selectedLocation, setSelectedLocation] = useState('');
  const [calculatedCost, setCalculatedCost] = useState(null);
  const [userCoins, setUserCoins] = useState(0);
  const [loading, setLoading] = useState(false);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    loadConfig();
    loadUserCoins();
  }, []);

  useEffect(() => {
    if (config) {
      calculateCost();
    }
  }, [selectedDuration, selectedGender, selectedAgeMin, selectedAgeMax, selectedLocation, config]);

  const loadConfig = async () => {
    setLoading(true);
    try {
      const response = await api.request('/boost/config/');
      setConfig(response);
    } catch (err) {
      console.error('Error loading boost config:', err);
    } finally {
      setLoading(false);
    }
  };

  const loadUserCoins = async () => {
    try {
      const response = await api.request('/wallet/');
      setUserCoins(response.coins || 0);
    } catch (err) {
      console.error('Error loading user coins:', err);
    }
  };

  const calculateCost = async () => {
    try {
      const response = await api.request('/boost/calculate-cost/', {
        method: 'POST',
        body: JSON.stringify({
          duration_hours: selectedDuration,
          target_gender: selectedGender,
          target_age_min: selectedAgeMin || null,
          target_age_max: selectedAgeMax || null,
          target_location: selectedLocation || null,
        }),
      });
      setCalculatedCost(response);
    } catch (err) {
      console.error('Error calculating cost:', err);
    }
  };

  const handleCreateBoost = async () => {
    if (!calculatedCost || calculatedCost.cost > userCoins) {
      setError('Insufficient coins');
      return;
    }

    setCreating(true);
    setError('');
    try {
      const response = await api.request('/boost/campaigns/', {
        method: 'POST',
        body: JSON.stringify({
          reel_id: reelId,
          duration_hours: selectedDuration,
          target_gender: selectedGender,
          target_age_min: selectedAgeMin || null,
          target_age_max: selectedAgeMax || null,
          target_location: selectedLocation || null,
        }),
      });

      if (response.success) {
        onSuccess();
      } else {
        setError(response.error || 'Failed to create boost');
      }
    } catch (err) {
      console.error('Error creating boost:', err);
      setError('Failed to create boost. Please try again.');
    } finally {
      setCreating(false);
    }
  };

  const durationOptions = [
    { hours: 1, label: '1 Hour', icon: Clock },
    { hours: 6, label: '6 Hours', label_extra: '17% off', icon: Clock },
    { hours: 12, label: '12 Hours', label_extra: '33% off', icon: Clock },
    { hours: 24, label: '24 Hours', label_extra: '42% off', icon: Clock },
    { hours: 72, label: '3 Days', label_extra: '56% off', icon: Clock },
    { hours: 168, label: '7 Days', label_extra: '71% off', icon: Clock },
  ];

  if (loading) {
    return (
      <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ color: '#fff', fontSize: 18 }}>Loading...</div>
      </div>
    );
  }

  return (
    <div style={{ position: 'fixed', top: 0, left: 0, right: 0, bottom: 0, zIndex: 99999, background: 'rgba(0,0,0,0.8)', display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 20 }} onClick={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div style={{ background: T.cardBg || '#1a1a1a', borderRadius: 20, maxWidth: 500, width: '100%', maxHeight: '90vh', overflowY: 'auto', position: 'relative' }}>
        {/* Header */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: 20, borderBottom: `1px solid ${T.border || 'rgba(255,255,255,0.1)'}` }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
            <div style={{ width: 40, height: 40, borderRadius: 12, background: `${T.pri || '#8fc441'}20`, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <Zap size={20} color={T.pri || '#8fc441'} />
            </div>
            <div>
              <div style={{ fontSize: 18, fontWeight: 700, color: T.txt || '#fff' }}>Boost Your Post</div>
              <div style={{ fontSize: 12, color: T.sub || 'rgba(255,255,255,0.5)' }}>Reach more people with coins</div>
            </div>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 8, color: T.sub || 'rgba(255,255,255,0.5)' }}>
            <X size={24} />
          </button>
        </div>

        {/* Content */}
        <div style={{ padding: 20 }}>
          {/* Duration Selection */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.txt || '#fff', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Clock size={16} color={T.pri || '#8fc441'} />
              Select Duration
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
              {durationOptions.map(option => {
                const Icon = option.icon;
                const isSelected = selectedDuration === option.hours;
                return (
                  <button
                    key={option.hours}
                    onClick={() => setSelectedDuration(option.hours)}
                    style={{
                      background: isSelected ? `${T.pri || '#8fc441'}20` : 'rgba(255,255,255,0.05)',
                      border: isSelected ? `2px solid ${T.pri || '#8fc441'}` : '2px solid transparent',
                      borderRadius: 12,
                      padding: 16,
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.2s',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
                      <Icon size={16} color={isSelected ? T.pri || '#8fc441' : T.sub || 'rgba(255,255,255,0.5)'} />
                      <span style={{ fontSize: 14, fontWeight: 600, color: T.txt || '#fff' }}>{option.label}</span>
                    </div>
                    {option.label_extra && (
                      <span style={{ fontSize: 11, color: T.pri || '#8fc441', fontWeight: 600 }}>{option.label_extra}</span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Target Audience (Optional) */}
          <div style={{ marginBottom: 24 }}>
            <div style={{ fontSize: 14, fontWeight: 700, color: T.txt || '#fff', marginBottom: 12, display: 'flex', alignItems: 'center', gap: 8 }}>
              <Target size={16} color={T.pri || '#8fc441'} />
              Target Audience (Optional)
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 10 }}>
              {/* Gender */}
              <div>
                <label style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 6, display: 'block' }}>Gender</label>
                <select
                  value={selectedGender}
                  onChange={(e) => setSelectedGender(e.target.value)}
                  style={{
                    width: '100%',
                    padding: 10,
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8,
                    color: T.txt || '#fff',
                    fontSize: 13,
                    outline: 'none',
                  }}
                >
                  <option value="all">All</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </select>
              </div>
              {/* Age Range */}
              <div>
                <label style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 6, display: 'block' }}>Age Range</label>
                <div style={{ display: 'flex', gap: 8 }}>
                  <input
                    type="number"
                    placeholder="Min"
                    value={selectedAgeMin}
                    onChange={(e) => setSelectedAgeMin(e.target.value)}
                    style={{
                      width: '100%',
                      padding: 10,
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8,
                      color: T.txt || '#fff',
                      fontSize: 13,
                      outline: 'none',
                    }}
                  />
                  <input
                    type="number"
                    placeholder="Max"
                    value={selectedAgeMax}
                    onChange={(e) => setSelectedAgeMax(e.target.value)}
                    style={{
                      width: '100%',
                      padding: 10,
                      background: 'rgba(255,255,255,0.05)',
                      border: '1px solid rgba(255,255,255,0.1)',
                      borderRadius: 8,
                      color: T.txt || '#fff',
                      fontSize: 13,
                      outline: 'none',
                    }}
                  />
                </div>
              </div>
              {/* Location */}
              <div style={{ gridColumn: 'span 2' }}>
                <label style={{ fontSize: 11, color: T.sub || 'rgba(255,255,255,0.5)', marginBottom: 6, display: 'block' }}>Location (City)</label>
                <input
                  type="text"
                  placeholder="e.g., Addis Ababa"
                  value={selectedLocation}
                  onChange={(e) => setSelectedLocation(e.target.value)}
                  style={{
                    width: '100%',
                    padding: 10,
                    background: 'rgba(255,255,255,0.05)',
                    border: '1px solid rgba(255,255,255,0.1)',
                    borderRadius: 8,
                    color: T.txt || '#fff',
                    fontSize: 13,
                    outline: 'none',
                  }}
                />
              </div>
            </div>
          </div>

          {/* Cost Summary */}
          {calculatedCost && (
            <div style={{ background: `${T.pri || '#8fc441'}10`, borderRadius: 12, padding: 16, marginBottom: 20, border: `1px solid ${T.pri || '#8fc441'}30` }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: T.txt || '#fff' }}>Your Balance</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: T.txt || '#fff' }}>{userCoins} coins</div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: T.txt || '#fff' }}>Boost Cost</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: T.pri || '#8fc441' }}>{Math.round(calculatedCost.cost)} coins</div>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
                <div style={{ fontSize: 13, color: T.txt || '#fff' }}>Expected Reach</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: T.pri || '#8fc441' }}>~{calculatedCost.expected_impressions.toLocaleString()} impressions</div>
              </div>
              <div style={{ height: 1, background: 'rgba(255,255,255,0.1)', margin: '12px 0' }} />
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ fontSize: 13, fontWeight: 600, color: T.txt || '#fff' }}>Remaining After Boost</div>
                <div style={{ fontSize: 16, fontWeight: 700, color: userCoins >= calculatedCost.cost ? T.txt || '#fff' : '#EF4444' }}>
                  {Math.round(userCoins - calculatedCost.cost)} coins
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div style={{ background: 'rgba(239,68,68,0.1)', borderRadius: 8, padding: 12, marginBottom: 20, border: '1px solid #EF4444' }}>
              <div style={{ fontSize: 13, color: '#EF4444' }}>{error}</div>
            </div>
          )}

          {/* Action Buttons */}
          <div style={{ display: 'flex', gap: 12 }}>
            <button
              onClick={onClose}
              style={{
                flex: 1,
                padding: 14,
                background: 'rgba(255,255,255,0.05)',
                border: 'none',
                borderRadius: 12,
                color: T.txt || '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel
            </button>
            <button
              onClick={handleCreateBoost}
              disabled={creating || !calculatedCost || calculatedCost.cost > userCoins}
              style={{
                flex: 1,
                padding: 14,
                background: creating || !calculatedCost || calculatedCost.cost > userCoins ? 'rgba(255,255,255,0.1)' : T.pri || '#8fc441',
                border: 'none',
                borderRadius: 12,
                color: creating || !calculatedCost || calculatedCost.cost > userCoins ? 'rgba(255,255,255,0.3)' : '#fff',
                fontSize: 14,
                fontWeight: 600,
                cursor: creating || !calculatedCost || calculatedCost.cost > userCoins ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: 8,
              }}
            >
              {creating ? 'Creating...' : <><Zap size={16} /> Boost Post</>}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
