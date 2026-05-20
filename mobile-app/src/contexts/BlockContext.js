import React, { createContext, useContext, useState, useCallback, useEffect } from 'react';
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
  const [loading, setLoading] = useState(true);

  const loadBlockedUsers = useCallback(async () => {
    try {
      setLoading(true);
      const response = await api.request('/blocks/');
      const users = Array.isArray(response) ? response : (response.results || []);
      const blockedIds = new Set(users.map(b => b.blocked?.id || b.blocked_id || b.id));
      const blockedUserObjects = users.map(b => b.blocked || b).filter(Boolean);
      setBlockedUsers(blockedIds);
      setBlockedUsersList(blockedUserObjects);
    } catch (error) {
      console.error('Failed to load blocked users:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const blockUser = useCallback(async (userId) => {
    try {
      if (blockedUsers.has(userId)) {
        console.log('User already blocked:', userId);
        return true;
      }
      
      await api.request('/blocks/block/', {
        method: 'POST',
        body: JSON.stringify({ blocked_user_id: userId })
      });
      setBlockedUsers(prev => new Set([...prev, userId]));
      await loadBlockedUsers();
      return true;
    } catch (error) {
      console.log('Block error:', error);
      if (error.message && error.message.includes('Already blocked')) {
        setBlockedUsers(prev => new Set([...prev, userId]));
        await loadBlockedUsers();
        return true;
      }
      return false;
    }
  }, [blockedUsers, loadBlockedUsers]);

  const unblockUser = useCallback(async (userId) => {
    try {
      await api.request('/blocks/unblock/', {
        method: 'POST',
        body: JSON.stringify({ blocked_user_id: userId })
      });
      setBlockedUsers(prev => {
        const newSet = new Set(prev);
        newSet.delete(userId);
        return newSet;
      });
      await loadBlockedUsers();
      return true;
    } catch (error) {
      console.log('Unblock error:', error);
      return false;
    }
  }, [loadBlockedUsers]);

  const isUserBlocked = useCallback((userId) => {
    return blockedUsers.has(userId);
  }, [blockedUsers]);

  const filterBlockedUsers = useCallback((items) => {
    if (!Array.isArray(items)) return [];
    return items.filter(item => {
      const userId = item.user?.id || item.user_id || item.id;
      return !isUserBlocked(userId);
    });
  }, [isUserBlocked]);

  const refreshBlockedUsers = useCallback(() => {
    return loadBlockedUsers();
  }, [loadBlockedUsers]);

  useEffect(() => {
    loadBlockedUsers();
  }, [loadBlockedUsers]);

  const value = {
    blockedUsers,
    blockedUsersList,
    loading,
    blockUser,
    unblockUser,
    isUserBlocked,
    filterBlockedUsers,
    refreshBlockedUsers,
    loadBlockedUsers
  };

  return (
    <BlockContext.Provider value={value}>
      {children}
    </BlockContext.Provider>
  );
};

export default BlockContext;
