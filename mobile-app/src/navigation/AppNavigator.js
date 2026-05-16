import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { View, Text, StyleSheet, ActivityIndicator, Linking } from 'react-native';
import { NavigationContainer } from '@react-navigation/native';
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs';
import { createStackNavigator } from '@react-navigation/stack';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../api';

import { AuthProvider, useAuth } from '../contexts/AuthContext';
import { AppAlertProvider } from '../components/AppAlert';
import { LanguageProvider } from '../contexts/LanguageContext';
import { ThemeProvider, useTheme } from '../contexts/ThemeContext';
import { BlockProvider } from '../contexts/BlockContext';

// Import screens directly (no lazy loading) to prevent blank screen flash
import LoginScreen from '../screens/auth/LoginScreen';
import RegisterScreen from '../screens/auth/RegisterScreen';
import HomeScreen from '../screens/HomeScreen';
import ReelsScreen from '../screens/ReelsScreen';
import CreateScreen from '../screens/CreateScreen';
import MessagesScreen from '../screens/MessagesScreen';
import ProfileScreen from '../screens/ProfileScreen';
import ExploreScreen from '../screens/ExploreScreen';
import EditProfileScreen from '../screens/EditProfileScreen';
import SettingsScreen from '../screens/SettingsScreen';
import FollowListScreen from '../screens/FollowListScreen';
import CampaignsScreen from '../screens/CampaignsScreen';
import CampaignDetailScreen from '../screens/CampaignDetailScreen';
import LeaderboardScreen from '../screens/LeaderboardScreen';
import WalletScreen from '../screens/WalletScreen';
import SubscriptionScreen from '../screens/SubscriptionScreen';
import GamificationScreen from '../screens/GamificationScreen';
import NotificationsScreen from '../screens/NotificationsScreen';
import WebsiteCoinScreen from '../screens/WebsiteCoinScreen';
import CoinPurchaseScreen from '../screens/CoinPurchaseScreen';

// Configure deep linking
const linking = {
  prefixes: [
    'https://uat.flipstar.et', 
    'uat.flipstar.et', 
    'https://flipstar.app', 
    'flipstar.app',
    'flipstar://'
  ],
  config: {
    screens: {
      MainTabs: {
        screens: {
          Home: 'home',
          Reels: 'reels',
        },
      },
      ReelsDetail: {
        path: 'post/:id',
        parse: {
          id: (id) => parseInt(id, 10),
        },
      },
    },
  },
};

// ReelsDetail wrapper to avoid navigation conflicts
function ReelsDetailWrapper({ route }) {
  const { id, initialVideoId } = route.params || {};
  const videoId = initialVideoId || id;
  console.log('ReelsDetailWrapper - received params:', route.params);
  console.log('ReelsDetailWrapper - using videoId:', videoId);
  
  // Ensure we have a valid video ID
  if (!videoId) {
    console.log('No video ID found, navigating to Home');
    return <HomeScreen />;
  }
  
  return <ReelsScreen route={{ params: { initialVideoId: videoId, fromDeepLink: true } }} />;
}

const GOLD = '#C8B56A';
const BG = '#0B0B0C';

const Tab = createBottomTabNavigator();
const Stack = createStackNavigator();

function MainTabs() {
  const { user } = useAuth();
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const [unreadMessages, setUnreadMessages] = useState(0);

  const fetchUnread = useCallback(async () => {
    try {
      const data = await api.request('/messages/unread-count/').catch(() => null);
      if (data?.unread_count !== undefined) setUnreadMessages(data.unread_count);
    } catch {}
  }, []);

  useEffect(() => {
    fetchUnread();
    const interval = setInterval(fetchUnread, 30000);
    return () => clearInterval(interval);
  }, [fetchUnread]);
  return (
    <Tab.Navigator
      screenOptions={({ route }) => ({
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.text,
        tabBarStyle: {
          backgroundColor: colors.cardBg,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: colors.primary + '30',
          height: 60 + insets.bottom,
          paddingBottom: insets.bottom,
          paddingTop: 8,
        },
        tabBarLabelStyle: { fontSize: 10, fontWeight: '600' },
        gestureEnabled: false,
        swipeEnabled: false,
        tabBarIcon: ({ focused, color, size }) => {
          const icons = {
            Home:     focused ? 'home'          : 'home-outline',
            Reels:    focused ? 'film'          : 'film-outline',
            Create:   'add',
            Messages: focused ? 'chatbubble'    : 'chatbubble-outline',
            Profile:  focused ? 'person'        : 'person-outline',
          };
          if (route.name === 'Create') {
            return (
              <View style={{ width: 44, height: 44, borderRadius: 22, backgroundColor: colors.primary, justifyContent: 'center', alignItems: 'center', marginBottom: 4, elevation: 8, shadowColor: colors.primary, shadowOffset: { width: 0, height: 4 }, shadowOpacity: 0.5, shadowRadius: 8 }}>
                <Ionicons name="add" size={26} color="#000" />
              </View>
            );
          }
          if (route.name === 'Messages' && unreadMessages > 0) {
            return (
              <View>
                <Ionicons name={focused ? 'chatbubble' : 'chatbubble-outline'} size={size} color={color} />
                <View style={{ position: 'absolute', top: -4, right: -6, backgroundColor: colors.error, borderRadius: 8, minWidth: 16, height: 16, justifyContent: 'center', alignItems: 'center', paddingHorizontal: 3 }}>
                  <Text style={{ color: '#fff', fontSize: 9, fontWeight: '800' }}>{unreadMessages > 99 ? '99+' : unreadMessages}</Text>
                </View>
              </View>
            );
          }
          return <Ionicons name={icons[route.name]} size={size} color={color} />;
        },
        tabBarLabel: ({ color }) => {
          if (route.name === 'Create') return null;
          const labels = { Home: 'Home', Reels: 'Reels', Messages: 'Messages', Profile: 'Profile' };
          return <Text style={{ fontSize: 10, color, fontWeight: '600' }}>{labels[route.name]}</Text>;
        },
      })}
    >
      <Tab.Screen name="Home"     component={HomeScreen} />
      <Tab.Screen name="Reels"    component={ReelsScreen} />
      <Tab.Screen name="Create"   component={CreateScreen} />
      <Tab.Screen 
        name="Messages" 
        component={MessagesScreen}
        listeners={({ navigation }) => ({
          tabPress: (e) => {
            if (!user) {
              e.preventDefault();
              navigation.navigate('Login');
            }
          },
        })}
      />
      <Tab.Screen name="Profile"  component={ProfileScreen} />
    </Tab.Navigator>
  );
}

function MainStack() {
  const { colors } = useTheme();
  
  return (
    <Stack.Navigator 
      screenOptions={{ 
        headerShown: false, 
        cardStyle: { backgroundColor: colors.bg },
        gestureEnabled: false,
        animationEnabled: true,
      }}
    >
      <Stack.Screen name="MainTabs"        component={MainTabs} />
      <Stack.Screen name="Explore"         component={ExploreScreen} />
      <Stack.Screen name="ReelsDetail"     component={ReelsDetailWrapper} />
      <Stack.Screen name="ProfileStack"    component={ProfileScreen} options={{ headerShown: false }} />
      <Stack.Screen name="EditProfile"     component={EditProfileScreen} />
      <Stack.Screen name="Settings"        component={SettingsScreen} />
      <Stack.Screen name="MessagesStack"   component={MessagesScreen} options={{ headerShown: false }} />
      <Stack.Screen name="FollowList"      component={FollowListScreen} />
      <Stack.Screen name="Campaigns"       component={CampaignsScreen} />
      <Stack.Screen name="CampaignDetail"  component={CampaignDetailScreen} />
      <Stack.Screen name="Leaderboard"    component={LeaderboardScreen} />
      <Stack.Screen name="Wallet"          component={WalletScreen} />
      <Stack.Screen name="Subscription"    component={SubscriptionScreen} />
      <Stack.Screen name="Gamification"    component={GamificationScreen} />
      <Stack.Screen name="Notifications"   component={NotificationsScreen} />
      <Stack.Screen name="WebsiteCoin"     component={WebsiteCoinScreen} />
      <Stack.Screen name="CoinPurchase"    component={CoinPurchaseScreen} />
    </Stack.Navigator>
  );
}

function AuthStack() {
  return (
    <Stack.Navigator screenOptions={{ headerShown: false }}>
      <Stack.Screen name="Login"    component={LoginScreen} />
      <Stack.Screen name="Register" component={RegisterScreen} />
    </Stack.Navigator>
  );
}

function RootNavigator() {
  const { user, loading } = useAuth();
  const { colors } = useTheme();
  
  if (loading) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: colors.bg }}>
        <ActivityIndicator size="large" color={colors.primary} />
      </View>
    );
  }
  return user ? <MainStack /> : <AuthStack />;
}

function AppNavigatorContent() {
  const { colors } = useTheme();
  
  // Wake up the backend immediately on app open (Render free tier cold starts)
  React.useEffect(() => { api.warmUp(); }, []);
  
  // Handle incoming deep links
  const handleDeepLink = useCallback(({ url }) => {
    // Parse the URL to extract post ID
    const match = url.match(/\/post\/(\d+)/);
    if (match) {
      const postId = parseInt(match[1], 10);
      console.log('Deep link to post:', postId);
      // Navigation will be handled by the linking config
    }
  }, []);

  const linkingConfig = React.useMemo(() => ({
    ...linking,
    subscribe: (listener) => {
      const onReceiveURL = ({ url }) => {
        handleDeepLink({ url });
        listener(url);
      };
      
      // Listen for incoming links
      const subscription = Linking.addEventListener('url', onReceiveURL);
      
      // Check if app was opened with a URL
      Linking.getInitialURL().then((url) => {
        if (url) {
          listener(url);
        }
      });
      
      return () => {
        subscription?.remove();
      };
    },
  }), [handleDeepLink]);

  const navTheme = React.useMemo(() => ({
    dark: true,
    colors: {
      primary: colors.primary,
      background: colors.bg,
      card: colors.cardBg,
      text: colors.text,
      border: colors.border,
      notification: colors.primary,
    },
  }), [colors]);

  return (
    <GestureHandlerRootView style={{ flex: 1, backgroundColor: colors.bg }}>
      <AuthProvider>
        <BlockProvider>
          <AppAlertProvider>
            <NavigationContainer linking={linkingConfig} theme={navTheme}>
              <RootNavigator />
            </NavigationContainer>
          </AppAlertProvider>
        </BlockProvider>
      </AuthProvider>
    </GestureHandlerRootView>
  );
}

export default function AppNavigator() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <AppNavigatorContent />
      </LanguageProvider>
    </ThemeProvider>
  );
}
