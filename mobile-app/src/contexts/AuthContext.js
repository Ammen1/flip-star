import React, { createContext, useContext, useState, useEffect, useMemo } from 'react';
import api from '../api';

const AuthContext = createContext();

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used within an AuthProvider');
  return context;
};

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [loading, setLoading] = useState(true);
  const [subscriptionStatus, setSubscriptionStatus] = useState(null);
  const [subscriptionChecked, setSubscriptionChecked] = useState(false);

  useEffect(() => { loadUser(); }, []);

  // Check subscription status when user changes
  useEffect(() => {
    if (user && !subscriptionChecked) {
      checkSubscriptionStatus();
    } else if (!user) {
      setSubscriptionStatus(null);
      setSubscriptionChecked(false);
    }
  }, [user]);

  const checkSubscriptionStatus = async () => {
    try {
      const status = await api.checkSubscriptionStatus();
      console.log('[AUTH] Subscription status:', status);
      setSubscriptionStatus(status);
      setSubscriptionChecked(true);
    } catch (error) {
      console.log('[AUTH] Failed to check subscription status:', error);
      // Handle 403 errors - they mean no subscription
      if (error.message?.includes('403') || error.message?.includes('has_subscription":false')) {
        console.log('🔒 [AUTH] 403 error - user has no subscription');
        setSubscriptionStatus({ has_subscription: false });
      } else {
        // On other errors, assume no subscription
        setSubscriptionStatus({ has_subscription: false });
      }
      setSubscriptionChecked(true);
    }
  };

  // Refresh subscription status
  const refreshSubscriptionStatus = async () => {
    try {
      const status = await api.checkSubscriptionStatus();
      console.log('[AUTH] Subscription status refreshed:', status);
      setSubscriptionStatus(status);
      setSubscriptionChecked(true);
      
      // Log when subscription expires
      if (!status.has_subscription) {
        console.log('🔒 [AUTH] User has no active subscription after refresh');
      }
    } catch (error) {
      console.log('[AUTH] Failed to refresh subscription status:', error);
      // Handle 403 errors - they mean no subscription
      if (error.message?.includes('403') || error.message?.includes('has_subscription":false')) {
        console.log('🔒 [AUTH] 403 error - user has no subscription');
        setSubscriptionStatus({ has_subscription: false });
      } else {
        // On other errors, assume no subscription
        setSubscriptionStatus({ has_subscription: false });
      }
      setSubscriptionChecked(true);
    }
  };

  const loadUser = async () => {
    try {
      const token = await api.getAuthToken();
      if (token) {
        const userData = await api.getProfile();
        setUser(userData);
      }
    } catch {
      // Token invalid — clear it
      await api.clearAuth();
    } finally {
      setLoading(false);
    }
  };

  const login = async (identifier, password) => {
    const data = await api.login(identifier, password);
    if (data.token) await api.setAuthToken(data.token);
    setUser(data.user);
    return data;
  };

  const register = async (payload) => {
    // payload: { fullName, phone, password } from RegisterScreen
    const { fullName, phone, password, first_name, last_name } = payload;

    // Generate a username from full name + timestamp suffix
    const baseUsername = (fullName || 'user')
      .toLowerCase()
      .replace(/\s+/g, '_')
      .replace(/[^a-z0-9_]/g, '');
    const username = `${baseUsername}_${Date.now().toString().slice(-4)}`;

    const data = await api.request('/auth/register-with-phone/', {
      method: 'POST',
      body: JSON.stringify({
        phone,
        username,
        password,
        first_name: first_name || (fullName || '').split(' ')[0] || '',
        last_name: last_name || (fullName || '').split(' ').slice(1).join(' ') || '',
        email: '',
        skip_otp: true,
      }),
    });

    if (data.token) await api.setAuthToken(data.token);
    setUser(data.user);
    return data;
  };

  const logout = async () => {
    await api.clearAuth();
    setUser(null);
    setSubscriptionStatus(null);
    setSubscriptionChecked(false);
  };

  const contextValue = useMemo(
    () => ({ 
      user, 
      loading, 
      subscriptionStatus, 
      subscriptionChecked, 
      hasActiveSubscription: subscriptionStatus?.has_subscription || false,
      login, 
      register, 
      logout, 
      loadUser,
      refreshSubscriptionStatus 
    }),
    [user, loading, subscriptionStatus, subscriptionChecked, login, register, logout, loadUser, refreshSubscriptionStatus]
  );

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};
