import React, { useEffect } from 'react';
import { useAuth } from '../contexts/AuthContext';
import api from '../api';

export default function SubscriptionGate({ children, navigation }) {
  const { user, hasActiveSubscription } = useAuth();

  // Periodically check subscription expiry (every 30 seconds like website)
  useEffect(() => {
    if (!user || !api.hasToken()) return;

    const interval = setInterval(async () => {
      console.log('[SUBSCRIPTION_GATE] Periodic subscription check (30 seconds)...');
      try {
        const status = await api.checkSubscriptionStatus();
        console.log('[SUBSCRIPTION_GATE] Periodic check result:', status);
        
        // Immediately redirect if subscription expired (like website)
        if (!status.has_subscription && navigation) {
          console.log('🔒 Subscription expired, redirecting to subscription page');
          try {
            navigation.reset({
              index: 0,
              routes: [{ name: 'Subscription' }],
            });
          } catch (error) {
            console.log('[SUBSCRIPTION_GATE] Navigation reset error:', error.message);
          }
        }
      } catch (e) {
        // Handle 403 errors - they mean no subscription
        if (e.message?.includes('403') || e.message?.includes('has_subscription":false')) {
          console.log('🔒 403 error - subscription expired, redirecting to subscription page');
          if (navigation) {
            try {
              navigation.reset({
                index: 0,
                routes: [{ name: 'Subscription' }],
              });
            } catch (error) {
              console.log('[SUBSCRIPTION_GATE] Navigation reset error:', error.message);
            }
          }
        } else {
          console.log('[SUBSCRIPTION_GATE] Periodic subscription check failed:', e.message);
        }
      }
    }, 30 * 1000); // 30 seconds

    return () => clearInterval(interval);
  }, [user, navigation]);

  // Always render children - main subscription check is in RootNavigator
  return children;
}
