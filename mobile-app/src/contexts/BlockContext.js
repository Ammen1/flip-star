import React, { createContext, useContext, useState, useEffect } from 'react';
import api from '../api';

const BlockContext = createContext();

export const useBlock = () => {
  const context = useContext(BlockContext);
  if (!context) {
    throw new Error('useBlock must be used within a BlockProvider');
  }
  return context;
};

export const BlockProvider = ({ children }) => {
  const [blockedUsers, setBlockedUsers] = useState(new Set());
  const [blockedUsersList, setBlockedUsersList] = useState([]);
  const [loading, setLoading] = useState(false);

  // Load blocked users on mount
  useEffect(() => {
    loadBlockedUsers();
  }, []);

  const loadBlockedUsers = async () => {
    try {
      setLoading(true);
      const data = await api.getBlockedUsers();
      const users = Array.isArray(data) ? data : (data.results || []);
      const blockedIds = new Set(users.map(b => b.blocked?.id || b.blocked_id || b.id));
      const blockedUserObjects = users.map(b => b.blocked || b).filter(Boolean);
      setBlockedUsers(blockedIds);
      setBlockedUsersList(blockedUserObjects);
    } catch (error) {
      console.log('Failed to load blocked users:', error);
    } finally {
      setLoading(false);
    }
  };

  const blockUser = async (userId) => {
    try {
      // Check if already blocked
      if (blockedUsers.has(userId)) {
        console.log('User already blocked:', userId);
        return true; // Already blocked, consider it successful
      }
      
      await api.blockUser(userId);
      setBlockedUsers(prev => new Set([...prev, userId]));
      // Refresh the list to get the full user object
      await loadBlockedUsers();
      return true;
    } catch (error) {
      console.log('Block error:', error);
      // If error is "Already blocked", update state and return success
      if (error.message && error.message.includes('Already blocked')) {
        setBlockedUsers(prev => new Set([...prev, userId]));
        // Refresh the list to get the full user object
        await loadBlockedUsers();
        return true;
      }
      return false;
    }
  };

  const unblockUser = async (userId) => {
    try {
      await api.unblockUser(userId);
      setBlockedUsers(prev => {
        const newSet = new Set(prev);
        newSet.delete(userId);
        return newSet;
      });
      // Refresh the list to update the display
      await loadBlockedUsers();
      return true;
    } catch (error) {
      console.log('Unblock error:', error);
      return false;
    }
  };

  const isUserBlocked = (userId) => {
    return blockedUsers.has(userId);
  };

  const filterBlockedUsers = (items) => {
    if (!Array.isArray(items)) return items;
    return items.filter(item => {
      const userId = item.user?.id || item.id || item.user_id;
      return !isUserBlocked(userId);
    });
  };

  const value = {
    blockedUsers,
    blockedUsersList,
    loading,
    blockUser,
    unblockUser,
    isUserBlocked,
    filterBlockedUsers,
    refreshBlockedUsers: loadBlockedUsers,
  };

  return (
    <BlockContext.Provider value={value}>
      {children}
    </BlockContext.Provider>
  );
};
