import config from './config';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const API_BASE_URL = config.API_BASE_URL;

let authToken = null;

// Token management
const TOKEN_KEY = 'authToken';

// Initialize auth token from secure storage
const initAuthToken = async () => {
  try {
    const token = await SecureStore.getItemAsync(TOKEN_KEY);
    if (token) {
      authToken = token;
    }
  } catch (error) {
    console.error('Error loading auth token:', error);
  }
};

// Cache configuration
const _cache = new Map();
const _inflight = new Map();
const CACHE_TTL = 300_000; // 5 minutes default TTL for better performance
const MAX_RETRIES = 1;
const RETRY_DELAY = 500;

function getCached(key) {
  const entry = _cache.get(key);
  if (entry && Date.now() - entry.ts < entry.ttl) return entry.data;
  _cache.delete(key);
  return null;
}

function setCache(key, data, ttl = CACHE_TTL) {
  _cache.set(key, { data, ts: Date.now(), ttl });
}

function invalidateCache(pattern) {
  for (const key of _cache.keys()) {
    if (key.includes(pattern)) _cache.delete(key);
  }
}

async function retryWithBackoff(fn, retries = MAX_RETRIES) {
  for (let i = 0; i < retries; i++) {
    try {
      return await fn();
    } catch (error) {
      if (
        error.name === 'TypeError' || 
        error.message.includes('fetch') || 
        error.message.includes('network') ||
        error.message.includes('502') ||
        error.message.includes('503') ||
        error.message.includes('504') ||
        error.message.includes('HTTP 502') ||
        error.message.includes('HTTP 503') ||
        error.message.includes('HTTP 504')
      ) {
        if (i < retries - 1) {
          await new Promise(resolve => setTimeout(resolve, RETRY_DELAY * (i + 1)));
          continue;
        }
      }
      throw error;
    }
  }
  return fn();
}

const api = {
  setAuthToken: async (token) => {
    authToken = token;
    if (token) {
      await SecureStore.setItemAsync(TOKEN_KEY, token);
    } else {
      await SecureStore.deleteItemAsync(TOKEN_KEY);
    }
    _cache.clear();
  },

  // Test backend connectivity
  testBackend: async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/`, {
        method: 'GET',
        headers: { 'Content-Type': 'application/json' }
      });
      return response.status !== 401;
    } catch (error) {
      console.error('Backend test failed:', error);
      return false;
    }
  },

  getAuthToken: async () => {
    if (!authToken) {
      await initAuthToken();
    }
    return authToken;
  },

  hasToken: async () => {
    if (!authToken) {
      await initAuthToken();
    }
    return !!authToken;
  },

  clearAuth: async () => {
    console.log('Clearing all auth data');
    authToken = null;
    await SecureStore.deleteItemAsync(TOKEN_KEY);
    _cache.clear();
  },

  async request(endpoint, options = {}) {
    // Cache logic
    const isGet = !options.method || options.method.toUpperCase() === 'GET';
    const isRealtime = (
      endpoint.startsWith('/messages/') ||
      endpoint.includes('/notifications/unread') ||
      endpoint.includes('unread-count')
    );
    const cacheable = isGet && !options.skipCache && !isRealtime;
    const cacheKey = cacheable ? endpoint : null;

    if (cacheable && cacheKey) {
      const cached = getCached(cacheKey);
      if (cached) {
        return cached;
      }
    }

    const inflightKey = isGet ? `GET:${endpoint}` : null;
    if (inflightKey && _inflight.has(inflightKey)) {
      return _inflight.get(inflightKey);
    }

    const doRequest = async () => {
      const headers = { ...options.headers };
      if (!options.isFormData) {
        headers['Content-Type'] = 'application/json';
      }

      const currentToken = await this.getAuthToken();
      // Auth endpoints that DO require token
      const isAuthenticatedAuthEndpoint = endpoint.includes('/auth/change-password') || endpoint.includes('/auth/delete-account') || endpoint.includes('/auth/password/change');
      const isPublicEndpoint = (endpoint.includes('/auth/') && !isAuthenticatedAuthEndpoint) || endpoint.includes('/settings/public');
      // Don't send Authorization header for public auth endpoints (like login/register)
      if (currentToken && !isPublicEndpoint) {
        headers['Authorization'] = `Token ${currentToken}`;
      }

      const response = await retryWithBackoff(async () => {
        return await fetch(`${API_BASE_URL}${endpoint}`, {
          ...options,
          headers,
        });
      });

      let data;
      if (response.status === 204) {
        data = { success: true };
      } else {
        try {
          data = await response.json();
        } catch (e) {
          // Include status in error message for retry logic
          const statusPrefix = !response.ok ? `[HTTP ${response.status}] ` : '';
          data = response.ok ? { success: true } : { error: `${statusPrefix}Failed to parse response` };
        }
      }

      if (!response.ok) {
        if (response.status === 401 && headers['Authorization'] && isGet) {
          console.warn('401 on GET with token - retrying without auth');
          const retryHeaders = { ...headers };
          delete retryHeaders['Authorization'];
          const retryResponse = await fetch(`${API_BASE_URL}${endpoint}`, {
            ...options,
            headers: retryHeaders,
          });
          let retryData;
          try { retryData = await retryResponse.json(); } catch (e) { retryData = {}; }
          if (retryResponse.ok) {
            if (cacheable && cacheKey) setCache(cacheKey, retryData);
            return retryData;
          }
          console.warn('Retry also failed - clearing credentials');
          await this.clearAuth();
          throw new Error(JSON.stringify(retryData) || `API Error: ${retryResponse.status}`);
        }
        if (response.status === 401) {
          console.error('🔒 401 Unauthorized - authentication required');
        }
        const silentEndpoints = ['/notifications/me/', '/profile/get_privacy/', '/profile/update_privacy/', '/blocks/', '/gamification/login-bonus/'];
        const isSilent = silentEndpoints.some(e => endpoint.includes(e));
        
        if (!isSilent) {
          console.error(`API Error [${endpoint}]:`, response.status, data);
        }
        const errorMsg = typeof data === 'string' ? data : (data.error || JSON.stringify(data));
        throw new Error(`[HTTP ${response.status}] ${endpoint}: ${errorMsg}`);
      }

      if (cacheable && cacheKey) setCache(cacheKey, data);
      return data;
    };

    const resultPromise = doRequest();
    if (inflightKey) {
      _inflight.set(inflightKey, resultPromise);
      resultPromise.finally(() => {
        if (_inflight.get(inflightKey) === resultPromise) {
          _inflight.delete(inflightKey);
        }
      });
    }
    return resultPromise;
  },

  invalidateCache,

  // Returns cached data immediately (if any) and refreshes in background.
  // onUpdate(freshData) is called when the network response arrives.
  requestStale(endpoint, onUpdate) {
    const cached = getCached(endpoint);
    // Fire network request in background regardless
    this.request(endpoint, { skipCache: true })
      .then(fresh => {
        setCache(endpoint, fresh);
        if (onUpdate) onUpdate(fresh);
      })
      .catch(() => {});
    return cached; // may be null on first load
  },

  // Wake up the Render backend so it's ready before the user hits a real endpoint
  warmUp() {
    fetch(`${API_BASE_URL}/health/`, { method: 'GET' }).catch(() => {});
  },

  // Auth
  register: (username, email, password, firstName = '', lastName = '') =>
    api.request('/auth/register/', {
      method: 'POST',
      body: JSON.stringify({
        username,
        email,
        password,
        first_name: firstName,
        last_name: lastName,
      }),
    }),

  // OTP Phone Registration
  sendPhoneOTP: (phone) =>
    api.request('/auth/send-phone-otp/', {
      method: 'POST',
      body: JSON.stringify({ phone }),
    }),

  verifyPhoneOTP: (phone, code) =>
    api.request('/auth/verify-phone-otp/', {
      method: 'POST',
      body: JSON.stringify({ phone, code }),
    }),

  registerWithPhone: (phone, username, password, email = '') =>
    api.request('/auth/register-with-phone/', {
      method: 'POST',
      body: JSON.stringify({ phone, username, password, email }),
    }),

  login: async (identifier, password) => {
    // Use same endpoint as website - username/password login
    const data = await api.request('/auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username: identifier, password }),
    });
    if (data.token) {
      await api.setAuthToken(data.token);
    }
    return data;
  },

  // Phone + PIN login for OTP-registered users
  loginWithPhonePin: async (phone, pin) => {
    const data = await api.request('/auth/login-with-phone-pin/', {
      method: 'POST',
      body: JSON.stringify({ phone, pin }),
    });
    if (data.token) {
      await api.setAuthToken(data.token);
    }
    return data;
  },

  // Forgot Password
  forgotPasswordRequest: (email) =>
    api.request('/auth/forgot-password/', {
      method: 'POST',
      body: JSON.stringify({ email }),
    }),

  forgotPasswordConfirm: (email, code, new_password) =>
    api.request('/auth/forgot-password/confirm/', {
      method: 'POST',
      body: JSON.stringify({ email, code, new_password }),
    }),

  // Forgot Password (Phone-based with SMS OTP)
  forgotPasswordPhoneRequest: (phone) =>
    api.request('/auth/forgot-password-phone/', {
      method: 'POST',
      body: JSON.stringify({ phone }),
    }),

  forgotPasswordPhoneVerify: (phone, code, new_password) =>
    api.request('/auth/forgot-password-phone/verify/', {
      method: 'POST',
      body: JSON.stringify({ phone, code, new_password }),
    }),

  // Profile
  getProfile: () => api.request('/profile/me/'),

  updateProfile: (data) =>
    api.request('/profile/update_profile/', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }).then(r => { invalidateCache('/profile'); return r; }),

  // Reels
  getReels: () => api.request('/reels/'),

  getReelsFollowing: () => api.request('/reels/following/'),

  getReelsSaved: () => api.request('/reels/saved/'),

  getReelsTrending: () => api.request('/reels/trending/'),

  createPost: async (formData, options = {}) => {
    try {
      console.log('Starting upload with fetch API...');
      console.log('FormData entries being sent:');
      for (let [key, value] of formData._parts) {
        console.log(`${key}:`, value);
      }
      
      const token = await api.getAuthToken();
      
      const response = await fetch(`${API_BASE_URL}/posts/create/`, {
        method: 'POST',
        headers: {
          'Authorization': `Token ${token}`,
          // Don't set Content-Type - let fetch set it automatically for FormData
        },
        body: formData,
      });
      
      console.log('Fetch response status:', response.status);
      console.log('Fetch response headers:', response.headers);
      
      const responseText = await response.text();
      console.log('Fetch response text:', responseText);
      
      let body;
      try {
        body = JSON.parse(responseText);
        console.log('Parsed response body:', body);
      } catch (e) {
        console.log('Failed to parse JSON response:', e);
        body = { error: 'Invalid JSON response', responseText };
      }
      
      if (response.ok) {
        invalidateCache('/reels');
        return body;
      } else {
        console.log('Upload failed:', response.status, body);
        throw body;
      }
    } catch (error) {
      console.error('Upload error:', error);
      throw error;
    }
  },

  voteReel: (reelId) =>
    api.request(`/reels/${reelId}/vote/`, {
      method: 'POST',
    }).then(r => { invalidateCache('/reels'); return r; }),

  postComment: (reelId, text) =>
    api.request(`/reels/${reelId}/comments/`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }).then(r => { invalidateCache(`/reels/${reelId}/comments`); invalidateCache('/reels'); return r; }),

  replyToComment: (commentId, text) =>
    api.request(`/comments/${commentId}/reply/`, {
      method: 'POST',
      body: JSON.stringify({ text }),
    }).then(r => { invalidateCache('/comments'); invalidateCache('/reels'); return r; }),

  likeComment: (commentId) =>
    api.request(`/comments/${commentId}/like/`, {
      method: 'POST',
    }).then(r => { invalidateCache('/comments'); invalidateCache('/reels'); return r; }),

  getComments: (reelId) => api.request(`/reels/${reelId}/comments/`),

  async toggleFollow(userId) {
    return this.request('/follows/toggle/', {
      method: 'POST',
      body: JSON.stringify({ following_id: userId }),
    });
  },

  // Block
  async blockUser(userId) {
    return this.request('/blocks/block/', {
      method: 'POST',
      body: JSON.stringify({ blocked_id: userId }),
    });
  },

  async unblockUser(userId) {
    return this.request('/blocks/unblock/', {
      method: 'POST',
      body: JSON.stringify({ blocked_id: userId }),
    });
  },

  getBlockedUsers: () => 
    api.request('/blocks/').then(r => { invalidateCache('/follows'); return r; }).catch(() => []),

  getFollowers: (userId) => api.request(`/follows/?following=${userId}`),

  getFollowing: (userId) => api.request(`/follows/?follower=${userId}`),

  getUserSuggestions: () => api.request('/follows/suggestions/'),

  deletePost: (reelId) =>
    api.request(`/reels/${reelId}/`, {
      method: 'DELETE',
    }).then(r => { invalidateCache('/reels'); return r; }),

  updatePost: (reelId, data) =>
    api.request(`/reels/${reelId}/`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }).then(r => { invalidateCache('/reels'); return r; }),

  // Notifications
  getUserNotifications: () => api.request('/notifications/'),

  getUnreadNotificationCount: () => api.request('/notifications/unread-count/'),

  markNotificationRead: (notificationId) =>
    api.request(`/notifications/${notificationId}/read/`, { method: 'POST' }),

  markAllNotificationsRead: () =>
    api.request('/notifications/read/', { method: 'POST', body: JSON.stringify({}) }),

  // Search
  search: (query) => api.request(`/search/?q=${encodeURIComponent(query)}`),

  // Explore/Trending
  getTrendingContent: (category = 'all', timeRange = '7d', limit = 12, offset = 0) =>
    api.request(`/explorer/trending/?category=${category}&time_range=${timeRange}&limit=${limit}&offset=${offset}`),

  getTrendingHashtags: (timeRange = '7d', limit = 15) =>
    api.request(`/explorer/trending-hashtags/?time_range=${timeRange}&limit=${limit}`),

  getHashtagContent: (tag, limit = 30) =>
    api.request(`/explorer/hashtag/?tag=${encodeURIComponent(tag)}&limit=${limit}`),

  getUser: (userId) => api.request(`/profile/${userId}/`),

  getUserPosts: (userId) => api.request(`/reels/?user=${userId}`),

  // Saved posts
  getSavedPosts: () => api.request('/reels/?saved=true'),

  toggleSavePost: (reelId) =>
    api.request('/saved/toggle/', {
      method: 'POST',
      body: JSON.stringify({ reel_id: reelId }),
    }),

  // Profile photo
  uploadProfilePhoto: (photoFile) => {
    const formData = new FormData();
    formData.append('photo', {
      uri: photoFile.uri,
      type: photoFile.type || 'image/jpeg',
      name: photoFile.name || 'photo.jpg',
    });

    return api.request('/profile-photo/upload/', {
      method: 'POST',
      body: formData,
      isFormData: true,
    });
  },

  updateUserProfile: (data) => {
    const formData = new FormData();
    // Always append these fields to ensure they are updated correctly
    formData.append('username', data.username || '');
    formData.append('email', data.email || '');
    formData.append('first_name', data.first_name || '');
    formData.append('last_name', data.last_name || '');
    formData.append('bio', data.bio || '');

    if (data.profile_photo) {
      formData.append('profile_photo', {
        uri: Platform.OS === 'ios' ? data.profile_photo.uri.replace('file://', '') : data.profile_photo.uri,
        type: data.profile_photo.type || 'image/jpeg',
        name: data.profile_photo.name || 'photo.jpg',
      });
    }

    return api.request('/profile/update_profile/', {
      method: 'PATCH',
      body: formData,
      isFormData: true,
    });
  },

  updateNotificationSettings: (settings) =>
    api.request('/notifications/me/update/', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  updatePrivacySettings: (settings) =>
    api.request('/profile/privacy/update/', {
      method: 'PUT',
      body: JSON.stringify(settings),
    }),

  changePassword: (currentPassword, newPassword) =>
    api.request('/auth/change-password/', {
      method: 'POST',
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    }),

  deleteAccount: () =>
    api.request('/profile/delete/', {
      method: 'DELETE',
    }),

  downloadData: () =>
    api.request('/profile/download-data/', {
      method: 'POST',
    }),

  // Campaigns
  getCampaigns: () => api.request('/campaigns/'),

  getCampaignsByStatus: (status) => api.request(`/campaigns/?status=${status}`),

  getCampaignDetail: (campaignId) => api.request(`/campaigns/${campaignId}/`),

  getCampaignFeed: (campaignId, filter = 'all') => 
    api.request(`/campaigns/${campaignId}/feed/?filter=${filter}`),

  getCampaignLeaderboard: (campaignId, period = 'overall') => 
    api.request(`/campaigns/${campaignId}/leaderboard/?period=${period}`),

  voteCampaignEntry: (entryId) =>
    api.request(`/campaigns/entries/${entryId}/vote/`, { method: 'POST' }),

  submitCampaignEntry: (campaignId, reelId) =>
    api.request(`/campaigns/${campaignId}/entries/`, {
      method: 'POST',
      body: JSON.stringify({ reel_id: reelId }),
    }),

  getCampaignScoringConfig: (campaignId) =>
    api.request(`/campaigns/${campaignId}/scoring-config/`),

  updateCampaignEngagement: (campaignId) =>
    api.request(`/campaigns/${campaignId}/engagement/update/`, { method: 'POST' }),

  getUserCampaignEntries: (userId) => api.request(`/campaigns/profile/${userId || ''}`),

  // Health check
  healthCheck: () => api.request('/health/'),

  // Public Settings (Admin controlled)
  getPublicSettings: () => api.request('/settings/public/'),

  // ─── Gamification ─────────────────────────────────────────────────────────
  getGamificationStatus: () => api.request('/gamification/status/'),
  claimLoginBonus: () => api.request('/gamification/login-bonus/', { method: 'POST' }),
  sendGift: (recipientUsername, amount, message) => 
    api.request('/gamification/gift/', {
      method: 'POST',
      body: JSON.stringify({ recipient_username: recipientUsername, amount, message })
    }),
  getDailySpin: () => api.request('/gamification/daily-spin/'),
  performSpin: () => api.request('/gamification/perform-spin/', { method: 'POST' }),

  // Wallet
  getWalletBalance: () => api.request('/wallet/'),
  getWalletConfig: () => api.request('/wallet/config/'),
  getCoinPackages: () => api.request('/coins/packages/'),

  // Subscription
  getSubscription: () => api.request('/subscriptions/'),
  getSubscriptionTiers: () => api.request('/subscriptions/tiers/active/'),
  subscribeToTier: (tierId, paymentMethod = 'sms') =>
    api.request('/subscriptions/subscribe/', {
      method: 'POST',
      body: JSON.stringify({
        tier_id: tierId,
        payment_method: paymentMethod,
      }),
    }),
  unsubscribe: () =>
    api.request('/subscriptions/unsubscribe/', {
      method: 'POST',
    }),
  upgradeSubscription: (plan) =>
    api.request('/subscription/upgrade/', {
      method: 'POST',
      body: JSON.stringify({ plan }),
    }),
  upgradeToProPlan: () =>
    api.request('/subscription/upgrade/', {
      method: 'POST',
      body: JSON.stringify({ plan: 'pro' }),
    }),
  upgradeToPremiumPlan: () =>
    api.request('/subscription/upgrade/', {
      method: 'POST',
      body: JSON.stringify({ plan: 'premium' }),
    }),

  // Competitions
  getCompetitions: () => api.request('/competitions/'),
  getActiveCompetitions: () => api.request('/competitions/?is_active=true'),

  // Winners
  getWinners: () => api.request('/winners/'),
  getLatestWinners: () => api.request('/winners/latest/'),

  // Quests
  getQuests: () => api.request('/quests/'),
  completeQuest: (questId) =>
    api.request(`/quests/${questId}/complete/`, {
      method: 'POST',
    }),

  // Reports
  createReport: (reportData) =>
    api.request('/reports/create/', {
      method: 'POST',
      body: JSON.stringify(reportData),
    }),
  getAdminReports: (status = null, type = null) => {
    let url = '/admin/reports/';
    const params = new URLSearchParams();
    if (status) params.append('status', status);
    if (type) params.append('type', type);
    if (params.toString()) url += '?' + params.toString();
    return api.request(url);
  },
  getAdminReportDetail: (reportId) =>
    api.request(`/admin/reports/${reportId}/`),
  updateAdminReport: (reportId, data) =>
    api.request(`/admin/reports/${reportId}/`, {
      method: 'PUT',
      body: JSON.stringify(data),
    }),
  getAdminReportsStats: () => api.request('/admin/reports/stats/'),

  // Trending hashtags
  getTrendingHashtags: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return api.request(`/explorer/trending-hashtags/${qs ? '?' + qs : ''}`);
  },

  // Search by hashtag
  searchByHashtag: (hashtag) =>
    api.request(`/reels/?hashtags__icontains=${encodeURIComponent(hashtag)}`),

  // Delete account
  deleteAccount: () =>
    api.request('/auth/delete-account/', {
      method: 'DELETE',
    }),

  // Download data
  downloadData: () =>
    api.request('/profile/download-data/', {
      method: 'POST',
    }),

};

// Initialize on load
initAuthToken().catch(err => {
  console.error('API: Failed to initialize auth token:', err);
});

export default api;

