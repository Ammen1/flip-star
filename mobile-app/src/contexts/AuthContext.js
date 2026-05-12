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

  useEffect(() => { loadUser(); }, []);

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
  };

  const contextValue = useMemo(
    () => ({ user, loading, login, register, logout, loadUser }),
    [user, loading, login, register, logout, loadUser]
  );

  return (
    <AuthContext.Provider value={contextValue}>
      {children}
    </AuthContext.Provider>
  );
};
