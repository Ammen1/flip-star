import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const ThemeContext = createContext();

export const useTheme = () => {
  const context = useContext(ThemeContext);
  if (!context) {
    throw new Error('useTheme must be used within a ThemeProvider');
  }
  return context;
};

export const ThemeProvider = ({ children }) => {
  const [darkMode, setDarkMode] = useState(true);
  
  // Light theme colors
  const lightColors = {
    bg: '#FFFFFF',
    cardBg: '#F8F9FA',
    text: '#1A1A1A',
    textSecondary: '#6B7280',
    border: '#E5E7EB',
    primary: '#C8B56A',
    primaryDark: '#B39F5A',
    success: '#22C55E',
    error: '#EF4444',
    warning: '#F59E0B'
  };
  
  // Dark theme colors
  const darkColors = {
    bg: '#0D0D0D',
    cardBg: '#1A1A1A',
    text: '#FFFFFF',
    textSecondary: '#999999',
    border: '#262626',
    primary: '#F9E08B',
    primaryDark: '#C8B56A',
    success: '#22C55E',
    error: '#EF4444',
    warning: '#F59E0B'
  };

  const colors = darkMode ? darkColors : lightColors;

  const toggleDarkMode = async () => {
    const newDarkMode = !darkMode;
    setDarkMode(newDarkMode);
    try {
      await AsyncStorage.setItem('darkMode', JSON.stringify(newDarkMode));
    } catch (error) {
      console.error('Failed to save dark mode setting:', error);
    }
  };

  // Load dark mode preference on mount
  useEffect(() => {
    const loadDarkMode = async () => {
      try {
        const saved = await AsyncStorage.getItem('darkMode');
        if (saved !== null) {
          setDarkMode(JSON.parse(saved));
        }
      } catch (error) {
        console.error('Failed to load dark mode setting:', error);
      }
    };
    loadDarkMode();
  }, []);

  const value = {
    colors,
    darkMode,
    toggleDarkMode,
    setDarkMode
  };

  return (
    <ThemeContext.Provider value={value}>
      {children}
    </ThemeContext.Provider>
  );
};
