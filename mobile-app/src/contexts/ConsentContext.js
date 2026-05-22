import React, { createContext, useContext, useState, useEffect } from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';

const ConsentContext = createContext();

export const useConsent = () => {
  const context = useContext(ConsentContext);
  if (!context) {
    throw new Error('useConsent must be used within ConsentProvider');
  }
  return context;
};

export const ConsentProvider = ({ children }) => {
  const [consents, setConsents] = useState({
    camera: false,
    storage: false,
    analytics: false,
    marketing: false,
    functional: true, // Essential for app functionality
    necessary: true   // Required for basic operation
  });

  const [consentHistory, setConsentHistory] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadConsents();
  }, []);

  const loadConsents = async () => {
    try {
      const stored = await AsyncStorage.getItem('userConsents');
      if (stored) {
        setConsents(JSON.parse(stored));
      }
      
      const history = await AsyncStorage.getItem('consentHistory');
      if (history) {
        setConsentHistory(JSON.parse(history));
      }
    } catch (error) {
      console.log('Error loading consents:', error);
    } finally {
      setLoading(false);
    }
  };

  const updateConsent = async (type, granted) => {
    const newConsents = { ...consents, [type]: granted };
    setConsents(newConsents);
    
    try {
      await AsyncStorage.setItem('userConsents', JSON.stringify(newConsents));
      
      // Record consent change
      const historyEntry = {
        type,
        granted,
        timestamp: new Date().toISOString(),
        appVersion: '1.0.0'
      };
      
      const newHistory = [...consentHistory, historyEntry];
      setConsentHistory(newHistory);
      await AsyncStorage.setItem('consentHistory', JSON.stringify(newHistory));
      
      console.log(`[CONSENT] Updated ${type} consent to ${granted}`);
      
    } catch (error) {
      console.log('Error saving consent:', error);
    }
  };

  const withdrawConsent = (type) => {
    updateConsent(type, false);
    
    // Handle consent withdrawal
    switch (type) {
      case 'camera':
        console.log('[CONSENT] Camera consent withdrawn - disabling camera features');
        break;
      case 'storage':
        console.log('[CONSENT] Storage consent withdrawn - limiting storage usage');
        break;
      case 'analytics':
        console.log('[CONSENT] Analytics consent withdrawn - stopping analytics tracking');
        break;
      case 'marketing':
        console.log('[CONSENT] Marketing consent withdrawn - unsubscribing from marketing');
        break;
    }
  };

  const hasConsent = (type) => {
    return consents[type] || false;
  };

  const requestConsent = (type) => {
    return new Promise((resolve) => {
      // This would typically show a modal or navigate to consent screen
      // For now, we'll just resolve with current state
      resolve(consents[type]);
    });
  };

  const resetConsents = async () => {
    const defaultConsents = {
      camera: false,
      storage: false,
      analytics: false,
      marketing: false,
      functional: true,
      necessary: true
    };
    
    setConsents(defaultConsents);
    setConsentHistory([]);
    
    try {
      await AsyncStorage.setItem('userConsents', JSON.stringify(defaultConsents));
      await AsyncStorage.removeItem('consentHistory');
    } catch (error) {
      console.log('Error resetting consents:', error);
    }
  };

  const getConsentSummary = () => {
    return {
      totalConsents: Object.keys(consents).length,
      grantedConsents: Object.values(consents).filter(v => v).length,
      optionalConsents: Object.entries(consents).filter(([key, value]) => 
        key !== 'functional' && key !== 'necessary'
      ),
      lastUpdated: consentHistory.length > 0 ? consentHistory[consentHistory.length - 1].timestamp : null
    };
  };

  if (loading) {
    return null; // Or a loading spinner
  }

  return (
    <ConsentContext.Provider value={{
      consents,
      consentHistory,
      updateConsent,
      withdrawConsent,
      hasConsent,
      requestConsent,
      resetConsents,
      getConsentSummary,
      loading
    }}>
      {children}
    </ConsentContext.Provider>
  );
};
