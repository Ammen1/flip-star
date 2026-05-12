import { useState, useEffect } from 'react';
import { Settings, Save, Key, Database, Bell, Shield, Zap, Globe, Type, Palette, Moon, Sun, Check } from 'lucide-react';
import api from '../../api';
import { AlertModal } from '../components/AlertModal';
import { PRESET_THEMES } from '../../contexts/ThemeContext';

// Available Google Fonts
const AVAILABLE_FONTS = [
  'Inter',
  'Roboto',
  'Open Sans',
  'Lato',
  'Montserrat',
  'Poppins',
  'Nunito',
  'Raleway',
  'Ubuntu',
  'Playfair Display',
  'Merriweather',
  'Source Sans Pro',
  'Oswald',
  'Quicksand',
  'Work Sans',
  'Rubik',
  'Karla',
  'Fira Sans',
  'Barlow',
  'DM Sans',
];

export function SettingsPage({ theme }) {
  const [settings, setSettings] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [alertModal, setAlertModal] = useState({ isOpen: false, title: '', message: '', type: 'info' });
  const [activeTab, setActiveTab] = useState('general');

  useEffect(() => {
    loadSettings();
  }, []);

  // Store settings globally for glass effect access
  useEffect(() => {
    if (settings) {
      window.currentAdminSettings = settings;
    }
  }, [settings]);

  // Load Google Fonts dynamically when settings change
  useEffect(() => {
    if (!settings) return;
    
    const fonts = [
      settings.font_family_primary,
      settings.font_family_secondary,
      settings.font_family_username,
      settings.font_family_caption,
    ].filter((f, i, arr) => f && arr.indexOf(f) === i); // unique fonts only
    
    fonts.forEach(font => {
      if (font && font !== 'Inter') {
        const fontUrl = `https://fonts.googleapis.com/css2?family=${font.replace(/ /g, '+')}:wght@300;400;500;600;700;800;900&display=swap`;
        const existingLink = document.querySelector(`link[href*="${font.replace(/ /g, '+')}"]`);
        
        if (!existingLink) {
          const link = document.createElement('link');
          link.href = fontUrl;
          link.rel = 'stylesheet';
          document.head.appendChild(link);
          console.log('[Admin] Loaded font:', font);
        }
      }
    });
  }, [settings?.font_family_primary, settings?.font_family_secondary, settings?.font_family_username, settings?.font_family_caption]);

  const loadSettings = async () => {
    try {
      const data = await api.request('/admin/settings/');
      setSettings(data);
    } catch (error) {
      console.error('Failed to load settings:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleSave = async () => {
    try {
      setSaving(true);
      await api.request('/admin/settings/update/', {
        method: 'POST',
        body: JSON.stringify(settings)
      });
      // Apply theme to entire app immediately — no reload needed
      try {
        const themeData = {
          preset: settings.theme_preset || 'flipstar',
          darkMode: settings.dark_mode_default || false,
          customPrimary: settings.primary_color_override || null,
        };
        localStorage.setItem('_platform_theme', JSON.stringify(themeData));
        window.dispatchEvent(new StorageEvent('storage', { key: '_platform_theme', newValue: JSON.stringify(themeData) }));
      } catch (_) {}
      setAlertModal({ isOpen: true, title: 'Success', message: 'Settings saved! Theme applied across the app.', type: 'success' });
    } catch (error) {
      console.error('Failed to save settings:', error);
      setAlertModal({ isOpen: true, title: 'Error', message: 'Failed to save settings', type: 'error' });
    } finally {
      setSaving(false);
    }
  };

  const handleChange = (field, value) => {
    setSettings(prev => ({ ...prev, [field]: value }));
  };

  if (loading) {
    return (
      <div style={{ padding: 40, textAlign: 'center', color: theme.sub }}>
        Loading settings...
      </div>
    );
  }

  const tabs = [
    { id: 'general', label: 'General', icon: Settings },
    { id: 'typography', label: 'Typography', icon: Type },
    { id: 'theme', label: 'Theme', icon: Palette },
    { id: 'content', label: 'Content', icon: Globe },
    { id: 'moderation', label: 'Moderation', icon: Shield },
    { id: 'notifications', label: 'Notifications', icon: Bell },
    { id: 'performance', label: 'Performance', icon: Zap },
    { id: 'api', label: 'API', icon: Key },
  ];

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
            Platform Settings
          </h1>
          <p style={{
            margin: 0,
            fontSize: 16,
            color: theme.sub,
          }}>
            Configure your platform settings and preferences
          </p>
        </div>
        <button
          onClick={handleSave}
          disabled={saving}
          style={{
            padding: '12px 24px',
            background: theme.pri,
            border: 'none',
            borderRadius: 8,
            color: '#fff',
            fontSize: 14,
            fontWeight: 600,
            cursor: saving ? 'not-allowed' : 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <Save size={16} />
          {saving ? 'Saving...' : 'Save Changes'}
        </button>
      </div>

      {/* Tabs */}
      <div style={{
        display: 'flex',
        gap: 8,
        marginBottom: 24,
        borderBottom: `1px solid ${theme.border}`,
      }}>
        {tabs.map(tab => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              style={{
                padding: '12px 20px',
                background: 'none',
                border: 'none',
                borderBottom: `2px solid ${isActive ? theme.pri : 'transparent'}`,
                color: isActive ? theme.pri : theme.sub,
                fontSize: 14,
                fontWeight: 600,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 8,
                transition: 'all 0.2s',
              }}
            >
              <Icon size={16} />
              {tab.label}
            </button>
          );
        })}
      </div>

      {/* Settings Content */}
      <div style={{
        background: theme.card,
        borderRadius: 12,
        padding: 32,
        border: `1px solid ${theme.border}`,
      }}>
        {activeTab === 'general' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingField
              label="Platform Name"
              value={settings.platform_name}
              onChange={(v) => handleChange('platform_name', v)}
              theme={theme}
            />
            <SettingField
              label="Platform Description"
              value={settings.platform_description}
              onChange={(v) => handleChange('platform_description', v)}
              multiline
              theme={theme}
            />
            <SettingToggle
              label="Maintenance Mode"
              description="Put the platform in maintenance mode"
              value={settings.maintenance_mode}
              onChange={(v) => handleChange('maintenance_mode', v)}
              theme={theme}
            />
            <SettingToggle
              label="Allow Registrations"
              description="Allow new users to register"
              value={settings.allow_registrations}
              onChange={(v) => handleChange('allow_registrations', v)}
              theme={theme}
            />
            <SettingToggle
              label="Require Email Verification"
              description="Users must verify their email before accessing the platform"
              value={settings.require_email_verification}
              onChange={(v) => handleChange('require_email_verification', v)}
              theme={theme}
            />
          </div>
        )}

        {activeTab === 'typography' && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 400px', gap: 32 }}>
            {/* Left: Controls */}
            <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
              <div style={{
                padding: 16,
                background: `${theme.pri}10`,
                borderRadius: 8,
              }}>
                <p style={{ margin: 0, fontSize: 14, color: theme.sub }}>
                  Customize the fonts used throughout the platform. Changes preview in real-time on the right.
                </p>
              </div>
              
              <FontSelect
              label="Primary Font (Headings & UI)"
              value={settings.font_family_primary || 'Inter'}
              onChange={(v) => handleChange('font_family_primary', v)}
              theme={theme}
            />
            <FontSelect
              label="Secondary Font (Body Text)"
              value={settings.font_family_secondary || 'Inter'}
              onChange={(v) => handleChange('font_family_secondary', v)}
              theme={theme}
            />
            <FontSelect
              label="Username Font"
              value={settings.font_family_username || 'Inter'}
              onChange={(v) => handleChange('font_family_username', v)}
              theme={theme}
            />
            <FontSelect
              label="Caption Font"
              value={settings.font_family_caption || 'Inter'}
              onChange={(v) => handleChange('font_family_caption', v)}
              theme={theme}
            />
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <SettingField
                label="Base Font Size (px)"
                type="number"
                value={settings.font_size_base || 16}
                onChange={(v) => handleChange('font_size_base', parseInt(v))}
                theme={theme}
              />
              <SettingField
                label="Line Height"
                value={settings.line_height || '1.5'}
                onChange={(v) => handleChange('line_height', v)}
                placeholder="1.5"
                theme={theme}
              />
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16 }}>
              <div>
                <label style={{
                  display: 'block',
                  fontSize: 14,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  Heading Font Weight
                </label>
                <select
                  value={settings.font_weight_headings || '700'}
                  onChange={(e) => handleChange('font_weight_headings', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: '#fff',
                  }}
                >
                  <option value="400">Regular (400)</option>
                  <option value="500">Medium (500)</option>
                  <option value="600">Semi-Bold (600)</option>
                  <option value="700">Bold (700)</option>
                  <option value="800">Extra Bold (800)</option>
                  <option value="900">Black (900)</option>
                </select>
              </div>
              <div>
                <label style={{
                  display: 'block',
                  fontSize: 14,
                  fontWeight: 600,
                  color: theme.txt,
                  marginBottom: 8,
                }}>
                  Body Font Weight
                </label>
                <select
                  value={settings.font_weight_body || '400'}
                  onChange={(e) => handleChange('font_weight_body', e.target.value)}
                  style={{
                    width: '100%',
                    padding: '12px',
                    border: `1px solid ${theme.border}`,
                    borderRadius: 8,
                    fontSize: 14,
                    outline: 'none',
                    background: '#fff',
                  }}
                >
                  <option value="300">Light (300)</option>
                  <option value="400">Regular (400)</option>
                  <option value="500">Medium (500)</option>
                  <option value="600">Semi-Bold (600)</option>
                </select>
              </div>
            </div>
            
            <SettingField
              label="Letter Spacing"
              value={settings.letter_spacing || 'normal'}
              onChange={(v) => handleChange('letter_spacing', v)}
              placeholder="normal, 0.5px, -0.02em"
              theme={theme}
            />
            </div>
            
            {/* Right: Live Preview Panel (Sticky) */}
            <div style={{
              position: 'sticky',
              top: 20,
              height: 'fit-content',
            }}>
              <div style={{
                background: '#fff',
                borderRadius: 12,
                border: `2px solid ${theme.border}`,
                overflow: 'hidden',
                boxShadow: '0 4px 20px rgba(0,0,0,0.08)',
              }}>
                <div style={{
                  padding: '16px 20px',
                  background: theme.pri,
                  color: '#fff',
                  fontWeight: 700,
                  fontSize: 16,
                }}>
                  Live Preview
                </div>
                
                <div style={{ padding: 24 }}>
                  {/* Heading Preview */}
                  <div style={{
                    marginBottom: 24,
                    paddingBottom: 24,
                    borderBottom: `1px solid ${theme.border}`,
                  }}>
                    <div style={{
                      fontSize: 11,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      color: theme.sub,
                      marginBottom: 8,
                      fontWeight: 600,
                    }}>
                      Heading Font
                    </div>
                    <h1 style={{
                      fontFamily: `"${settings.font_family_primary || 'Inter'}", sans-serif`,
                      fontWeight: settings.font_weight_headings || '700',
                      fontSize: (settings.font_size_base || 16) * 2,
                      color: theme.txt,
                      margin: '0 0 8px 0',
                      lineHeight: 1.2,
                    }}>
                      Welcome Back!
                    </h1>
                    <h2 style={{
                      fontFamily: `"${settings.font_family_primary || 'Inter'}", sans-serif`,
                      fontWeight: settings.font_weight_headings || '700',
                      fontSize: (settings.font_size_base || 16) * 1.5,
                      color: theme.txt,
                      margin: '0 0 8px 0',
                      lineHeight: 1.3,
                    }}>
                      Section Title
                    </h2>
                    <h3 style={{
                      fontFamily: `"${settings.font_family_primary || 'Inter'}", sans-serif`,
                      fontWeight: settings.font_weight_headings || '700',
                      fontSize: (settings.font_size_base || 16) * 1.125,
                      color: theme.txt,
                      margin: 0,
                      lineHeight: 1.4,
                    }}>
                      Subsection
                    </h3>
                  </div>
                  
                  {/* Body Text Preview */}
                  <div style={{
                    marginBottom: 24,
                    paddingBottom: 24,
                    borderBottom: `1px solid ${theme.border}`,
                  }}>
                    <div style={{
                      fontSize: (settings.font_size_base || 16) * 0.6875,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      color: theme.sub,
                      marginBottom: 8,
                      fontWeight: 600,
                    }}>
                      Body Font
                    </div>
                    <p style={{
                      fontFamily: `"${settings.font_family_secondary || 'Inter'}", sans-serif`,
                      fontWeight: settings.font_weight_body || '400',
                      fontSize: settings.font_size_base || 16,
                      lineHeight: settings.line_height || '1.5',
                      letterSpacing: settings.letter_spacing || 'normal',
                      color: theme.txt,
                      margin: '0 0 12px 0',
                    }}>
                      This is how body text will appear throughout the entire platform. The quick brown fox jumps over the lazy dog.
                    </p>
                    <p style={{
                      fontFamily: `"${settings.font_family_secondary || 'Inter'}", sans-serif`,
                      fontWeight: settings.font_weight_body || '400',
                      fontSize: (settings.font_size_base || 16) * 0.875,
                      lineHeight: settings.line_height || '1.5',
                      letterSpacing: settings.letter_spacing || 'normal',
                      color: theme.sub,
                      margin: 0,
                    }}>
                      Smaller text for descriptions and secondary content.
                    </p>
                  </div>
                  
                  {/* Username Preview */}
                  <div style={{
                    marginBottom: 24,
                    paddingBottom: 24,
                    borderBottom: `1px solid ${theme.border}`,
                  }}>
                    <div style={{
                      fontSize: (settings.font_size_base || 16) * 0.6875,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      color: theme.sub,
                      marginBottom: 12,
                      fontWeight: 600,
                    }}>
                      Username Font
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                      <div style={{
                        width: (settings.font_size_base || 16) * 2.5,
                        height: (settings.font_size_base || 16) * 2.5,
                        borderRadius: '50%',
                        background: theme.pri,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        color: '#fff',
                        fontWeight: 700,
                        fontSize: (settings.font_size_base || 16),
                      }}>
                        JD
                      </div>
                      <div>
                        <div style={{
                          fontFamily: `"${settings.font_family_username || 'Inter'}", sans-serif`,
                          fontWeight: 600,
                          fontSize: (settings.font_size_base || 16) * 0.9375,
                          color: theme.txt,
                          marginBottom: 2,
                        }}>
                          @johndoe
                        </div>
                        <div style={{
                          fontFamily: `"${settings.font_family_secondary || 'Inter'}", sans-serif`,
                          fontSize: (settings.font_size_base || 16) * 0.8125,
                          color: theme.sub,
                        }}>
                          John Doe
                        </div>
                      </div>
                    </div>
                  </div>
                  
                  {/* Caption Preview */}
                  <div>
                    <div style={{
                      fontSize: (settings.font_size_base || 16) * 0.6875,
                      textTransform: 'uppercase',
                      letterSpacing: '0.5px',
                      color: theme.sub,
                      marginBottom: 8,
                      fontWeight: 600,
                    }}>
                      Caption Font
                    </div>
                    <div style={{
                      fontFamily: `"${settings.font_family_caption || 'Inter'}", sans-serif`,
                      fontSize: (settings.font_size_base || 16) * 0.875,
                      lineHeight: 1.6,
                      color: theme.txt,
                    }}>
                      This is a caption or description text that appears under posts and images. It's designed to be readable and complement the main content.
                    </div>
                  </div>
                  
                  {/* Button Preview */}
                  <div style={{ marginTop: 24, paddingTop: 24, borderTop: `1px solid ${theme.border}` }}>
                    <button style={{
                      fontFamily: `"${settings.font_family_secondary || 'Inter'}", sans-serif`,
                      padding: `${(settings.font_size_base || 16) * 0.75}px ${(settings.font_size_base || 16) * 1.5}px`,
                      background: theme.pri,
                      border: 'none',
                      borderRadius: 8,
                      color: '#fff',
                      fontSize: (settings.font_size_base || 16) * 0.875,
                      fontWeight: 600,
                      cursor: 'pointer',
                      width: '100%',
                    }}>
                      Button Text
                    </button>
                  </div>
                </div>
              </div>
              
              {/* Font Info */}
              <div style={{
                marginTop: 16,
                padding: 12,
                background: `${theme.pri}10`,
                borderRadius: 8,
                fontSize: 12,
                color: theme.sub,
              }}>
                <div style={{ marginBottom: 4 }}>
                  <strong>Primary:</strong> {settings.font_family_primary || 'Inter'}
                </div>
                <div style={{ marginBottom: 4 }}>
                  <strong>Secondary:</strong> {settings.font_family_secondary || 'Inter'}
                </div>
                <div style={{ marginBottom: 4 }}>
                  <strong>Username:</strong> {settings.font_family_username || 'Inter'}
                </div>
                <div>
                  <strong>Caption:</strong> {settings.font_family_caption || 'Inter'}
                </div>
              </div>
              
              {/* Debug Info */}
              <div style={{
                marginTop: 16,
                padding: 12,
                background: '#FEF3C7',
                border: '2px solid #F59E0B',
                borderRadius: 8,
                fontSize: 11,
              }}>
                <div style={{ fontWeight: 700, marginBottom: 8, color: '#92400E' }}>
                  ⚠️ Preview Status
                </div>
                <div style={{ color: '#78350F', marginBottom: 4 }}>
                  Fonts loaded in admin panel. After saving, refresh the main app to see changes.
                </div>
                <button
                  onClick={() => {
                    const fonts = [settings.font_family_primary, settings.font_family_secondary, settings.font_family_username, settings.font_family_caption];
                    alert(`Current fonts:\n${fonts.join('\n')}\n\nCheck browser console for font loading status.`);
                  }}
                  style={{
                    marginTop: 8,
                    padding: '6px 12px',
                    background: '#F59E0B',
                    border: 'none',
                    borderRadius: 6,
                    color: '#fff',
                    fontSize: 11,
                    fontWeight: 600,
                    cursor: 'pointer',
                    width: '100%',
                  }}
                >
                  Check Font Status
                </button>
              </div>
            </div>
          </div>
        )}

        {activeTab === 'theme' && (
          <ThemeTab settings={settings} handleChange={handleChange} setSettings={setSettings} theme={theme} />
        )}


        {activeTab === 'content' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingField
              label="Max File Size (MB)"
              type="number"
              value={settings.max_file_size_mb}
              onChange={(v) => handleChange('max_file_size_mb', parseInt(v))}
              theme={theme}
            />
            <SettingField
              label="Allowed Video Formats"
              value={settings.allowed_video_formats}
              onChange={(v) => handleChange('allowed_video_formats', v)}
              placeholder="mp4,mov,avi"
              theme={theme}
            />
            <SettingField
              label="Allowed Image Formats"
              value={settings.allowed_image_formats}
              onChange={(v) => handleChange('allowed_image_formats', v)}
              placeholder="jpg,jpeg,png,gif"
              theme={theme}
            />
            <SettingField
              label="Max Caption Length"
              type="number"
              value={settings.max_caption_length}
              onChange={(v) => handleChange('max_caption_length', parseInt(v))}
              theme={theme}
            />
            <SettingToggle
              label="Enable Comments"
              description="Allow users to comment on posts"
              value={settings.enable_comments}
              onChange={(v) => handleChange('enable_comments', v)}
              theme={theme}
            />
            <SettingToggle
              label="Enable Voting"
              description="Allow users to vote on posts"
              value={settings.enable_voting}
              onChange={(v) => handleChange('enable_voting', v)}
              theme={theme}
            />
          </div>
        )}

        {activeTab === 'moderation' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingToggle
              label="Auto Moderation"
              description="Automatically moderate content using AI"
              value={settings.auto_moderation}
              onChange={(v) => handleChange('auto_moderation', v)}
              theme={theme}
            />
            <SettingToggle
              label="Profanity Filter"
              description="Filter profanity in comments and captions"
              value={settings.profanity_filter}
              onChange={(v) => handleChange('profanity_filter', v)}
              theme={theme}
            />
            <SettingToggle
              label="Spam Detection"
              description="Detect and prevent spam content"
              value={settings.spam_detection}
              onChange={(v) => handleChange('spam_detection', v)}
              theme={theme}
            />
          </div>
        )}

        {activeTab === 'notifications' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingToggle
              label="Email Notifications"
              description="Send email notifications to users"
              value={settings.email_notifications}
              onChange={(v) => handleChange('email_notifications', v)}
              theme={theme}
            />
            <SettingToggle
              label="Push Notifications"
              description="Send push notifications to users"
              value={settings.push_notifications}
              onChange={(v) => handleChange('push_notifications', v)}
              theme={theme}
            />
            <SettingToggle
              label="SMS Notifications"
              description="Send SMS notifications to users"
              value={settings.sms_notifications}
              onChange={(v) => handleChange('sms_notifications', v)}
              theme={theme}
            />
          </div>
        )}

        {activeTab === 'performance' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingToggle
              label="Cache Enabled"
              description="Enable caching for better performance"
              value={settings.cache_enabled}
              onChange={(v) => handleChange('cache_enabled', v)}
              theme={theme}
            />
            <SettingToggle
              label="CDN Enabled"
              description="Use CDN for static assets"
              value={settings.cdn_enabled}
              onChange={(v) => handleChange('cdn_enabled', v)}
              theme={theme}
            />
            {settings.cdn_enabled && (
              <SettingField
                label="CDN URL"
                value={settings.cdn_url || ''}
                onChange={(v) => handleChange('cdn_url', v)}
                placeholder="https://cdn.example.com"
                theme={theme}
              />
            )}
            <SettingToggle
              label="Analytics Enabled"
              description="Track platform analytics"
              value={settings.analytics_enabled}
              onChange={(v) => handleChange('analytics_enabled', v)}
              theme={theme}
            />
            <SettingToggle
              label="Track User Activity"
              description="Track detailed user activity"
              value={settings.track_user_activity}
              onChange={(v) => handleChange('track_user_activity', v)}
              theme={theme}
            />
          </div>
        )}

        {activeTab === 'api' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
            <SettingToggle
              label="API Enabled"
              description="Enable API access"
              value={settings.api_enabled}
              onChange={(v) => handleChange('api_enabled', v)}
              theme={theme}
            />
            <SettingField
              label="API Rate Limit (requests/minute)"
              type="number"
              value={settings.api_rate_limit}
              onChange={(v) => handleChange('api_rate_limit', parseInt(v))}
              theme={theme}
            />
          </div>
        )}
      </div>

      {/* Success/Error Alert Modal */}
      <AlertModal
        isOpen={alertModal.isOpen}
        title={alertModal.title}
        message={alertModal.message}
        type={alertModal.type}
        onClose={() => setAlertModal({ ...alertModal, isOpen: false })}
        showCancel={false}
      />
    </div>
  );
}

// ─── Theme Tab ─────────────────────────────────────────────────────────────────
function applyThemeCSSLive(presetKey, dark, customPrimary) {
  const p = PRESET_THEMES[presetKey] || PRESET_THEMES.flipstar;
  const c = { ...(dark ? p.dark : p.light) };
  if (customPrimary) c.pri = customPrimary;
  const r = document.documentElement;
  r.style.setProperty('--color-primary', c.pri);
  r.style.setProperty('--color-bg', c.bg);
  r.style.setProperty('--color-txt', c.txt);
  r.style.setProperty('--color-sub', c.sub);
  r.style.setProperty('--color-border', c.border);
  r.style.setProperty('--color-card', c.cardBg);
}

// Helper function to convert hex to rgba
function hexToRgba(hex, alpha) {
  if (hex && hex.startsWith('#')) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }
  return hex || 'rgba(0,0,0,0.1)';
}

function ThemeTab({ settings, handleChange, setSettings, theme }) {
  const selectedPreset = settings.theme_preset || 'flipstar';
  const isDark = settings.dark_mode_default ?? false;

  const previewColors = (() => {
    const p = PRESET_THEMES[selectedPreset] || PRESET_THEMES.flipstar;
    const base = isDark ? p.dark : p.light;
    const cp = settings.primary_color_override;
    return cp ? { ...base, pri: cp } : base;
  })();

  const presetKeys = Object.keys(PRESET_THEMES);

  const selectPreset = (key) => {
    const newSettings = { ...settings, theme_preset: key, primary_color_override: null };
    setSettings(newSettings);
    window.currentAdminSettings = newSettings;
    applyThemeCSSLive(key, isDark, null);
  };

  const toggleDarkMode = () => {
    const nd = !isDark;
    const newSettings = { ...settings, dark_mode_default: nd };
    setSettings(newSettings);
    window.currentAdminSettings = newSettings;
    applyThemeCSSLive(selectedPreset, nd, settings.primary_color_override || null);
  };


  const updateCustomColor = (color) => {
    handleChange('primary_color_override', color || null);
    const newSettings = { ...settings, primary_color_override: color || null };
    window.currentAdminSettings = newSettings;
    applyThemeCSSLive(selectedPreset, isDark, color || null);
  };

  return (
    <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 32 }}>
      {/* ── Left: Controls ── */}
      <div>
        {/* Dark mode toggle */}
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '14px 18px', background: theme.bg, borderRadius: 12, border: `1px solid ${theme.border}`, marginBottom: 16 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            {isDark ? <Moon size={18} color={theme.pri} /> : <Sun size={18} color={theme.pri} />}
            <div>
              <div style={{ fontSize: 14, fontWeight: 600, color: theme.txt }}>Dark Mode</div>
              <div style={{ fontSize: 12, color: theme.sub }}>{isDark ? 'Currently showing dark variant' : 'Currently showing light variant'}</div>
            </div>
          </div>
          <button onClick={toggleDarkMode}
            style={{ width: 48, height: 28, borderRadius: 14, background: isDark ? theme.pri : theme.border, border: 'none', cursor: 'pointer', position: 'relative', transition: 'all 0.2s', flexShrink: 0 }}>
            <div style={{ width: 24, height: 24, borderRadius: '50%', background: '#fff', position: 'absolute', top: 2, left: isDark ? 22 : 2, transition: 'all 0.2s' }} />
          </button>
        </div>


        {/* Preset grid */}
        <div style={{ fontSize: 13, fontWeight: 700, color: theme.txt, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Choose Preset</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 10, marginBottom: 28 }}>
          {presetKeys.map(key => {
            const p = PRESET_THEMES[key];
            const c = isDark ? p.dark : p.light;
            const isActive = selectedPreset === key;
            return (
              <button key={key} onClick={() => selectPreset(key)}
                style={{ background: c.cardBg, border: `2px solid ${isActive ? (c.priFallback || c.pri) : theme.border}`, borderRadius: 12, padding: '12px', cursor: 'pointer', textAlign: 'left', position: 'relative', transition: 'all 0.15s', boxShadow: isActive ? `0 0 0 3px ${(c.priFallback || c.pri)}30` : 'none', overflow: 'hidden' }}>
                {/* Swatch row */}
                <div style={{ display: 'flex', gap: 4, marginBottom: 8 }}>
                  <div style={{ width: 20, height: 20, borderRadius: 6, background: c.pri, position: 'relative' }}>
                    {p.gradient && <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(45deg, transparent 30%, rgba(255,255,255,0.3) 50%, transparent 70%)', animation: 'shimmer 2s infinite', borderRadius: 6 }} />}
                  </div>
                  <div style={{ width: 20, height: 20, borderRadius: 6, background: c.bg }} />
                  <div style={{ width: 20, height: 20, borderRadius: 6, background: c.cardBg, border: `1px solid ${c.border}` }} />
                </div>
                <div style={{ fontSize: 12, fontWeight: 700, color: isActive ? (c.priFallback || c.pri) : theme.txt, marginBottom: 2 }}>{p.emoji} {p.name}</div>
                <div style={{ fontSize: 10, color: theme.sub }}>{p.category}{p.gradient ? ' • Gradient' : ''}</div>
                {isActive && (
                  <div style={{ position: 'absolute', top: 8, right: 8, width: 18, height: 18, borderRadius: '50%', background: c.priFallback || c.pri, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <Check size={10} color="#fff" strokeWidth={3} />
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* Custom primary color override */}
        <div style={{ fontSize: 13, fontWeight: 700, color: theme.txt, marginBottom: 12, textTransform: 'uppercase', letterSpacing: '0.5px' }}>Custom Accent Color</div>
        <div style={{ padding: 16, background: theme.bg, borderRadius: 12, border: `1px solid ${theme.border}`, marginBottom: 16 }}>
          <div style={{ fontSize: 13, color: theme.sub, marginBottom: 12 }}>Override the preset's primary color with your own brand color.</div>
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            <input type="color" value={settings.primary_color_override || previewColors.pri}
              onChange={(e) => updateCustomColor(e.target.value)}
              style={{ width: 44, height: 44, border: `1px solid ${theme.border}`, borderRadius: 8, cursor: 'pointer', padding: 2, flexShrink: 0 }} />
            <input type="text" value={settings.primary_color_override || ''}
              onChange={(e) => updateCustomColor(e.target.value)}
              placeholder="Leave blank to use preset color"
              style={{ flex: 1, padding: '10px 12px', border: `1px solid ${theme.border}`, borderRadius: 8, fontSize: 13, outline: 'none', background: theme.card, color: theme.txt }} />
            {settings.primary_color_override && (
              <button onClick={() => updateCustomColor(null)}
                style={{ padding: '10px 14px', background: '#EF444420', border: '1px solid #EF4444', borderRadius: 8, color: '#EF4444', fontSize: 12, fontWeight: 600, cursor: 'pointer' }}>
                Reset
              </button>
            )}
          </div>
        </div>

        {/* Secondary (legacy) */}
        <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 4 }}>
          <input type="color" value={settings.secondary_color || '#F97316'}
            onChange={(e) => handleChange('secondary_color', e.target.value)}
            style={{ width: 36, height: 36, border: `1px solid ${theme.border}`, borderRadius: 6, cursor: 'pointer', padding: 2, flexShrink: 0 }} />
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13, fontWeight: 600, color: theme.txt, marginBottom: 2 }}>Secondary / Accent Color</div>
            <input type="text" value={settings.secondary_color || '#F97316'}
              onChange={(e) => handleChange('secondary_color', e.target.value)}
              style={{ width: '100%', padding: '8px 10px', border: `1px solid ${theme.border}`, borderRadius: 6, fontSize: 13, outline: 'none', background: theme.card, color: theme.txt }} />
          </div>
        </div>
      </div>

      {/* ── Right: Live Preview ── */}
      <div style={{ position: 'sticky', top: 20, height: 'fit-content' }}>
        <div style={{ fontSize: 12, fontWeight: 700, color: theme.sub, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 10 }}>Live Preview</div>
        {/* Phone mockup */}
        <div style={{ background: '#111', borderRadius: 28, padding: '10px 6px', boxShadow: '0 8px 32px rgba(0,0,0,0.3)', width: 220, margin: '0 auto' }}>
          <div style={{ background: previewColors.bg, borderRadius: 22, overflow: 'hidden', minHeight: 380 }}>
            {/* App bar */}
            <div style={{ background: previewColors.cardBg, padding: '14px 14px 10px', borderBottom: `1px solid ${previewColors.border}`, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{ fontSize: 13, fontWeight: 800, color: previewColors.pri }}>FlipStar</div>
              <div style={{ width: 24, height: 24, borderRadius: '50%', background: previewColors.pri + '30', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: 10, height: 10, borderRadius: '50%', background: previewColors.pri }} />
              </div>
            </div>
            {/* Feed cards */}
            {[0,1].map(i => (
              <div key={i} style={{ margin: '10px 10px 0', background: previewColors.cardBg, borderRadius: 12, padding: 10, border: `1px solid ${previewColors.border}` }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 8 }}>
                  <div style={{ width: 24, height: 24, borderRadius: '50%', background: previewColors.pri }} />
                  <div>
                    <div style={{ width: 56, height: 7, background: previewColors.txt + '50', borderRadius: 4, marginBottom: 3 }} />
                    <div style={{ width: 36, height: 5, background: previewColors.sub + '40', borderRadius: 4 }} />
                  </div>
                </div>
                <div style={{ height: 60, background: previewColors.bg, borderRadius: 8, marginBottom: 8 }} />
                <div style={{ display: 'flex', gap: 6 }}>
                  <div style={{ padding: '4px 10px', background: previewColors.pri, borderRadius: 6, color: '#fff', fontSize: 9, fontWeight: 700 }}>Like</div>
                  <div style={{ padding: '4px 10px', background: previewColors.border, borderRadius: 6, color: previewColors.sub, fontSize: 9, fontWeight: 600 }}>Share</div>
                </div>
              </div>
            ))}
            {/* Bottom nav */}
            <div style={{ margin: '12px 0 0', padding: '8px 0', background: previewColors.cardBg, borderTop: `1px solid ${previewColors.border}`, display: 'flex', justifyContent: 'space-around' }}>
              {['🏠','🔍','➕','🔔','👤'].map((icon, i) => (
                <div key={i} style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1 }}>
                  <div style={{ fontSize: 14 }}>{icon}</div>
                  {i === 0 && <div style={{ width: 4, height: 4, borderRadius: '50%', background: previewColors.pri }} />}
                </div>
              ))}
            </div>
          </div>
        </div>
        {/* Swatch strip */}
        <div style={{ marginTop: 14, padding: 12, background: theme.bg, borderRadius: 10, border: `1px solid ${theme.border}` }}>
          {[
            { label: 'Primary', color: previewColors.pri },
            { label: 'Background', color: previewColors.bg },
            { label: 'Card', color: previewColors.cardBg },
            { label: 'Text', color: previewColors.txt },
            { label: 'Border', color: previewColors.border },
          ].map(({ label, color }) => (
            <div key={label} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
              <div style={{ width: 14, height: 14, borderRadius: 4, background: color, border: `1px solid ${theme.border}`, flexShrink: 0 }} />
              <span style={{ fontSize: 11, color: theme.sub, flex: 1 }}>{label}</span>
              <span style={{ fontSize: 10, color: theme.sub, fontFamily: 'monospace' }}>{color}</span>
            </div>
          ))}
        </div>
      </div>
      <style>{`
        @keyframes shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
}

function SettingField({ label, value, onChange, type = 'text', multiline = false, placeholder = '', theme }) {
  return (
    <div>
      <label style={{
        display: 'block',
        fontSize: 14,
        fontWeight: 600,
        color: theme.txt,
        marginBottom: 8,
      }}>
        {label}
      </label>
      {multiline ? (
        <textarea
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          rows={3}
          style={{
            width: '100%',
            padding: '12px',
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            fontSize: 14,
            fontFamily: 'inherit',
            outline: 'none',
            resize: 'vertical',
          }}
        />
      ) : (
        <input
          type={type}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          style={{
            width: '100%',
            padding: '12px',
            border: `1px solid ${theme.border}`,
            borderRadius: 8,
            fontSize: 14,
            outline: 'none',
          }}
        />
      )}
    </div>
  );
}

function SettingToggle({ label, description, value, onChange, theme }) {
  return (
    <div style={{
      display: 'flex',
      justifyContent: 'space-between',
      alignItems: 'center',
      padding: '16px',
      background: theme.bg,
      borderRadius: 8,
    }}>
      <div>
        <div style={{
          fontSize: 14,
          fontWeight: 600,
          color: theme.txt,
          marginBottom: 4,
        }}>
          {label}
        </div>
        <div style={{
          fontSize: 13,
          color: theme.sub,
        }}>
          {description}
        </div>
      </div>
      <button
        onClick={() => onChange(!value)}
        style={{
          width: 48,
          height: 28,
          borderRadius: 14,
          background: value ? theme.pri : theme.border,
          border: 'none',
          cursor: 'pointer',
          position: 'relative',
          transition: 'all 0.2s',
        }}
      >
        <div style={{
          width: 24,
          height: 24,
          borderRadius: '50%',
          background: '#fff',
          position: 'absolute',
          top: 2,
          left: value ? 22 : 2,
          transition: 'all 0.2s',
        }} />
      </button>
    </div>
  );
}

function FontSelect({ label, value, onChange, theme }) {
  return (
    <div>
      <label style={{
        display: 'block',
        fontSize: 14,
        fontWeight: 600,
        color: theme.txt,
        marginBottom: 8,
      }}>
        {label}
      </label>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        style={{
          width: '100%',
          padding: '12px',
          border: `1px solid ${theme.border}`,
          borderRadius: 8,
          fontSize: 14,
          outline: 'none',
          background: '#fff',
          fontFamily: `"${value}", sans-serif`,
        }}
      >
        {AVAILABLE_FONTS.map(font => (
          <option key={font} value={font} style={{ fontFamily: `"${font}", sans-serif` }}>
            {font}
          </option>
        ))}
      </select>
      <div style={{
        marginTop: 8,
        padding: '8px 12px',
        background: theme.bg,
        borderRadius: 6,
        fontFamily: `"${value}", sans-serif`,
        fontSize: 14,
        color: theme.sub,
      }}>
        The quick brown fox jumps over the lazy dog
      </div>
    </div>
  );
}




